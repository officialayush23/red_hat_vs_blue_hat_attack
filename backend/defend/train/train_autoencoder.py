"""
Stage 5 (Blue Team) -- trains the Autoencoder for unknown/zero-day fraud
detection: trained ONLY on legitimate (is_fraud == 0) REAL transactions
(docs/TECHNICAL_SPEC.md Section 5 -- "trained only on legitimate
transactions, reconstruction error as anomaly score"). Every generated
attack row is fraud by construction, so filtering to is_fraud == 0 on the
shared train split (defend/train/dataset.py) already excludes all of them
without a separate check -- this model never sees a synthetic row during
training.

Evaluated on the SAME validation split as train_xgboost.py / train_lightgbm.py
(mixed legit + fraud, real + train-portion-generated) so all three models'
ROC-AUC/PR-AUC numbers in docs/EVALUATION_RESULTS.md are directly
comparable -- same held-out rows, same metrics code (evaluation/metrics.py).

Needs PyTorch, installed separately per docs/TRAINING_SETUP.md Section 2
(CUDA-specific wheel) -- not in requirements.txt for that reason. Uses the
GPU automatically if torch.cuda.is_available(), falls back to CPU
otherwise; either way this is a small MLP and trains in minutes, not hours,
even on the full ~6.9M-row PaySim+IEEE-CIS legitimate-transaction set.

Categorical features are one-hot encoded here (unlike XGBoost/LightGBM's
native category support) -- plain feedforward layers need numeric input.
Numeric/boolean features are mean-imputed and standardized using
statistics fit on the legitimate TRAINING rows only, to avoid leaking
anything from the fraud or validation rows into the normalization.

Usage:
    python backend/defend/train/train_autoencoder.py
    python backend/defend/train/train_autoencoder.py --epochs 30 --batch-size 4096
"""

import argparse
import gc
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset
except ImportError:
    print(
        "PyTorch is not installed in this environment. Install it with the CUDA-specific\n"
        "command from docs/TRAINING_SETUP.md Section 2 (checks your driver's CUDA version\n"
        "and gives the matching pytorch.org install command), then re-run this script.",
        file=sys.stderr,
    )
    sys.exit(1)

from defend.train.dataset import (  # noqa: E402
    BOOLEAN_FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES, load_training_pool, train_val_split,
)
from evaluation.metrics import best_f1_threshold, compute_binary_metrics, record_result  # noqa: E402

MODELS_DIR = BACKEND_DIR / "defend" / "models"
RESULTS_JSON = MODELS_DIR / "metrics.json"
RESULTS_MD = BACKEND_DIR.parent / "docs" / "EVALUATION_RESULTS.md"

NUMERIC_COLS = NUMERIC_FEATURES + BOOLEAN_FEATURES


def fit_preprocessor(df: pd.DataFrame) -> dict:
    means, stds = {}, {}
    for c in NUMERIC_COLS:
        mean = float(df[c].mean(skipna=True)) if df[c].notna().any() else 0.0
        std = float(df[c].std(skipna=True))
        means[c] = mean
        stds[c] = std if std and std > 1e-6 else 1.0
    cat_vocab = {c: sorted(v for v in df[c].dropna().unique().tolist()) for c in CATEGORICAL_FEATURES}
    return {"numeric_cols": NUMERIC_COLS, "cat_cols": CATEGORICAL_FEATURES, "means": means, "stds": stds, "cat_vocab": cat_vocab}


def transform(df: pd.DataFrame, spec: dict) -> np.ndarray:
    """Real fix for a genuine `Unable to allocate 1.05 GiB for an array with
    shape (5539427, 51)` crash on the full 6.96M-row pool: this used to build
    a Python list of small per-column float32 blocks, then call
    `np.concatenate(blocks, axis=1)` at the very end -- meaning the full list
    of blocks (already ~1 GiB combined) and the freshly concatenated output
    array (another ~1 GiB) were BOTH resident in memory at once for the one
    moment concatenate needs, on top of `pool`/`X_train_df` never being freed
    in main() below (same underlying discipline gap as build_features.py's
    documented earlier OOM crash and dataset.py's/build_features.py's dtype
    ones this session -- large intermediates never explicitly released).
    Pre-allocating the output array once and filling columns in place avoids
    ever holding both the parts and the whole simultaneously; the `del
    pool` / `del X_train_df` cleanup in main() below is the other half of
    this same fix.
    """
    n_rows = len(df)
    cat_widths = [len(spec["cat_vocab"][c]) for c in spec["cat_cols"]]
    total_width = len(spec["numeric_cols"]) + sum(cat_widths)
    out = np.empty((n_rows, total_width), dtype="float32")

    col_idx = 0
    for c in spec["numeric_cols"]:
        # Bug #6 (docs/DATASETS.md): this used to index df[c] unconditionally
        # and crashed any caller whose dataframe didn't have 100% column
        # parity with training time -- e.g. evaluation/adaptive_weakness_round.py's
        # round-2 cases, generated for a family with no real graph structure,
        # legitimately have no graph_* columns at all (same "leave null when
        # the row's source has no real graph" convention as every other
        # dataset-specific column in this codebase). preprocessor.py's
        # transform_tree() already guards this exact case for XGBoost/
        # LightGBM; mirror that guard here instead of hard-crashing --
        # missing means "no signal for this row", which is precisely what
        # fillna(spec["means"][c]) already does for a present-but-NaN
        # column, so a genuinely-absent column gets the same neutral
        # treatment as an all-NaN one, not a special case.
        col = pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=df.index)
        col = col.fillna(spec["means"][c])
        out[:, col_idx] = ((col - spec["means"][c]) / spec["stds"][c]).to_numpy(dtype="float32", copy=False)
        col_idx += 1

    for c, width in zip(spec["cat_cols"], cat_widths):
        vocab = spec["cat_vocab"][c]
        # Mask out-of-vocab values to NaN before constructing the Categorical --
        # pandas deprecated (and will eventually error on) building a Categorical
        # directly from values not present in the given categories. Cast to plain
        # object dtype first: df[c] is itself already "category"-typed (dataset.py)
        # with a category list covering the WHOLE pool (train+val, real+generated),
        # so a masked-but-still-Categorical Series keeps that full category list as
        # metadata even though every out-of-vocab cell is now NaN -- pandas' new
        # deprecation check inspects that stale category list, not just the present
        # values, and still warns. Dropping to plain object dtype removes that
        # metadata entirely so only the actual (in-vocab-or-NaN) values remain.
        masked = df[c].where(df[c].isin(vocab)).astype(object)
        codes = pd.Categorical(masked, categories=vocab).codes  # vectorized; -1 for missing/unseen
        block = out[:, col_idx:col_idx + width]
        block.fill(0.0)
        valid = codes >= 0
        block[np.nonzero(valid)[0], codes[valid]] = 1.0
        col_idx += width

    return out


class Autoencoder(nn.Module):
    def __init__(self, input_dim: int, hidden_dims=(32, 8)):
        super().__init__()
        h1, h2 = hidden_dims
        self.encoder = nn.Sequential(nn.Linear(input_dim, h1), nn.ReLU(), nn.Linear(h1, h2), nn.ReLU())
        self.decoder = nn.Sequential(nn.Linear(h2, h1), nn.ReLU(), nn.Linear(h1, input_dim))

    def forward(self, x):
        return self.decoder(self.encoder(x))


def reconstruction_error(model: Autoencoder, X: np.ndarray, device, batch_size: int = 8192) -> np.ndarray:
    model.eval()
    errors = []
    with torch.no_grad():
        for i in range(0, len(X), batch_size):
            batch = torch.from_numpy(X[i:i + batch_size]).to(device)
            recon = model(batch)
            mse = ((recon - batch) ** 2).mean(dim=1)
            errors.append(mse.cpu().numpy())
    return np.concatenate(errors)


def _append_results_md(metrics: dict, threshold: float, n_train: int, n_val: int) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS_MD.exists():
        RESULTS_MD.write_text(
            "# Evaluation Results\n\n"
            "Recorded automatically by each training/evaluation script -- do not hand-edit\n"
            "numbers here, re-run the script instead.\n"
        )
    section = (
        f"\n## Autoencoder -- validation split (Stage 5, ordinary train/val, not adversarial)\n\n"
        f"- Anomaly-score threshold (reconstruction MSE): {threshold:.6f}\n"
        f"- Precision: {metrics['precision']:.4f}\n"
        f"- Recall: {metrics['recall']:.4f}\n"
        f"- F1: {metrics['f1']:.4f}\n"
        f"- ROC-AUC: {metrics['roc_auc']:.4f}\n"
        f"- PR-AUC: {metrics['pr_auc']:.4f}\n"
        f"- False positive rate: {metrics['false_positive_rate']:.4%}\n"
        f"- Trained on {n_train:,} legitimate rows only / Validation set: {metrics['n_samples']:,} rows "
        f"({metrics['n_positive']:,} fraud)\n"
    )
    with open(RESULTS_MD, "a") as f:
        f.write(section)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--lr", type=float, default=1e-3)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    if device.type == "cuda":
        print(f"  {torch.cuda.get_device_name(0)}")

    print("Loading training pool (real data + train-portion generated attacks)...")
    pool = load_training_pool()
    X_train_df, X_val_df, y_train, y_val = train_val_split(pool)
    del pool  # its data is already copied into X_train_df/X_val_df -- fully redundant from here on
    gc.collect()

    legit_mask = (y_train == 0).to_numpy()
    legit_train_df = X_train_df[legit_mask]
    print(f"  {len(legit_train_df):,} legitimate rows for training "
          f"(excludes all fraud, real and generated -- generated rows are 100% fraud by construction)")
    del X_train_df  # legit_train_df is a copy of the rows we need; the rest (fraud rows) is dead weight
    gc.collect()

    spec = fit_preprocessor(legit_train_df)
    X_train = transform(legit_train_df, spec)
    del legit_train_df
    gc.collect()
    X_val = transform(X_val_df, spec)
    del X_val_df
    gc.collect()
    input_dim = X_train.shape[1]
    print(f"  input dimension after encoding: {input_dim}")

    model = Autoencoder(input_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = nn.MSELoss()

    loader = DataLoader(TensorDataset(torch.from_numpy(X_train)), batch_size=args.batch_size, shuffle=True)

    print(f"Training Autoencoder for {args.epochs} epochs...")
    model.train()
    for epoch in range(args.epochs):
        total_loss, n_batches = 0.0, 0
        for (batch,) in loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            recon = model(batch)
            loss = loss_fn(recon, batch)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1
        print(f"  epoch {epoch + 1}/{args.epochs}  mean reconstruction MSE: {total_loss / n_batches:.6f}")

    val_scores = reconstruction_error(model, X_val, device)
    threshold = best_f1_threshold(y_val, val_scores)
    metrics = compute_binary_metrics(y_val, val_scores, threshold=threshold)
    print(f"Validation metrics (threshold={threshold:.6f}):\n{json.dumps(metrics, indent=2)}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "autoencoder.pt"
    torch.save(
        {"state_dict": model.state_dict(), "input_dim": input_dim, "hidden_dims": (32, 8), "prep_spec": spec},
        str(model_path),
    )
    print(f"Saved model to {model_path}")

    record_result(
        RESULTS_JSON, "autoencoder", metrics,
        extra={"decision_threshold": threshold, "n_train": len(X_train), "n_val": len(X_val)},
    )
    _append_results_md(metrics, threshold, len(X_train), len(X_val))
    print(f"Recorded results to {RESULTS_JSON} and {RESULTS_MD}")
    print("\nDone. Model frozen. Phase 1 core models (XGBoost, LightGBM, Autoencoder) are all trained.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nTRAINING FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
