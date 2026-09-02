"""
Section 8 step 4 (docs/TECHNICAL_SPEC.md) -- the Stage 7 harness that was
the one genuinely missing piece as of 2026-08-30: scores the already-frozen
XGBoost / LightGBM / Autoencoder models (trained by train_xgboost.py /
train_lightgbm.py / train_autoencoder.py, Stage 5 -- NOT retrained here,
per step 2 "freeze the models, no further training after this point")
against data/processed/attacks_held_out.parquet -- combinations from
evaluation/split_policy.py's held_out_only buckets, which those frozen
models never saw during training (attacks_train.parquet is a disjoint
file, built from a disjoint combination bucket -- see split_policy.py).

Records real precision/recall/F1/ROC-AUC/PR-AUC/false-positive-rate,
overall AND broken out per attack family (transaction_fraud,
account_takeover, synthetic_identity, mule_network), to
backend/defend/models/metrics.json and docs/EVALUATION_RESULTS.md --
whatever the real numbers turn out to be, per Principle 11.

Two honest caveats, stated here rather than hidden:

1. attacks_held_out.parquet has no legitimate (is_fraud=0) rows of its own
   -- every row in it is fraud by construction (inject_attacks.py). Recall
   needs no negatives, but precision/FPR do, so this script reuses the
   ordinary Stage-5 validation split's legitimate rows (dataset.py's
   train_val_split, same seed=42) as the bonafide comparison set. Those
   rows were never used in a gradient update for any of the three models,
   but XGBoost/LightGBM's early stopping DID monitor them during training
   (eval_set) -- a mild, standard, well-understood form of peeking, not a
   held-out set as clean as attacks_held_out.parquet itself. Recorded
   here plainly rather than presented as equally clean.
2. attack_cases (and therefore evaluation_results, which has a hard
   foreign key to it) is keyed one row per CASE, but
   attacks_held_out.parquet is one row per TRANSACTION -- a mule_network
   or synthetic_identity case is a multi-transaction sequence, so several
   parquet rows share one case_id. The real per-row/per-family metrics
   below are computed at transaction-row granularity (matching how these
   models were trained -- dataset.py's pool is row-level too). The
   Supabase per-case evidence write aggregates each case's rows to a
   single score (max across its rows -- "was any transaction in this
   case's sequence flagged") so one evaluation_results row maps cleanly
   to one attack_cases row; this is a coarser view than the row-level
   numbers this script prints and records locally, and is only as good as
   Phase 1.5's attack_cases backfill (backfill_attack_cases.py) already
   having those case_ids loaded.

Usage:
    python backend/evaluation/run_adversarial_eval.py
    python backend/evaluation/run_adversarial_eval.py --skip-autoencoder
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import gc  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from defend.train.dataset import load_training_pool, train_val_split  # noqa: E402
from defend.train.preprocessor import TabularPreprocessor  # noqa: E402
from evaluation.metrics import compute_binary_metrics, record_result  # noqa: E402
from evaluation.supabase_results import explain_persistence_failure, record_run_and_results  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
HELD_OUT_PATH = PROCESSED_DIR / "attacks_held_out.parquet"
MODELS_DIR = BACKEND_DIR / "defend" / "models"
RESULTS_JSON = MODELS_DIR / "metrics.json"
RESULTS_MD = REPO_ROOT / "docs" / "EVALUATION_RESULTS.md"
PREPROCESSOR_PATH = MODELS_DIR / "tabular_preprocessor.joblib"

ATTACK_FAMILIES = ("transaction_fraud", "account_takeover", "synthetic_identity", "mule_network")


def _load_frozen_xgboost():
    import xgboost as xgb
    path = MODELS_DIR / "xgboost.json"
    model = xgb.XGBClassifier(enable_categorical=True, tree_method="hist")
    model.load_model(str(path))
    return model


def _load_frozen_lightgbm():
    import lightgbm as lgb
    path = MODELS_DIR / "lightgbm.txt"
    return lgb.Booster(model_file=str(path))


def _load_frozen_autoencoder():
    """Returns (score_fn, ok). score_fn(df) -> np.ndarray of reconstruction
    error. ok=False (score_fn=None) if PyTorch isn't installed in this
    environment -- XGBoost/LightGBM still get scored either way; this
    mirrors train_autoencoder.py's own graceful-exit-on-missing-torch
    behavior instead of crashing the whole harness over one model."""
    try:
        import torch  # noqa: F401
        from defend.train.train_autoencoder import Autoencoder, reconstruction_error, transform
    except (ImportError, SystemExit):
        print(
            "  PyTorch not available in this environment -- skipping Autoencoder "
            "(XGBoost/LightGBM below are unaffected). Run this script in the same "
            "environment as train_autoencoder.py to include it.",
            file=sys.stderr,
        )
        return None, False

    ckpt = torch.load(MODELS_DIR / "autoencoder.pt", map_location="cpu", weights_only=False)
    model = Autoencoder(ckpt["input_dim"], hidden_dims=ckpt["hidden_dims"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    spec = ckpt["prep_spec"]

    def score_fn(df: pd.DataFrame) -> np.ndarray:
        X = transform(df, spec)
        return reconstruction_error(model, X, torch.device("cpu"))

    return score_fn, True


def _frozen_threshold(model_name: str) -> float:
    data = json.loads(RESULTS_JSON.read_text())
    if model_name not in data:
        raise FileNotFoundError(
            f"No Stage-5 metrics.json entry for '{model_name}'. Run its train_*.py script first."
        )
    return float(data[model_name]["decision_threshold"])


def _append_results_md(model_name: str, overall: dict, per_family: dict, n_legit: int) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS_MD.exists():
        RESULTS_MD.write_text(
            "# Evaluation Results\n\n"
            "Recorded automatically by each training/evaluation script -- do not hand-edit\n"
            "numbers here, re-run the script instead.\n"
        )
    lines = [
        f"\n## {model_name} -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)\n",
        f"- Precision: {overall['precision']:.4f}",
        f"- Recall: {overall['recall']:.4f}",
        f"- F1: {overall['f1']:.4f}",
        f"- ROC-AUC: {overall['roc_auc']:.4f}",
        f"- PR-AUC: {overall['pr_auc']:.4f}",
        f"- False positive rate (against Stage-5 validation-split legit rows): {overall['false_positive_rate']:.4%}",
        f"- n_legit={n_legit}, n_fraud={overall['n_samples'] - n_legit} "
        f"(held-out combinations only, transaction-row granularity)",
    ]
    for fam, m in per_family.items():
        lines.append(f"- {fam} recall: {m['recall']:.4f} (n_fraud_rows={m['n_positive']})")
    lines.append(
        "- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion "
        "(seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this "
        "script's module docstring for the full caveat."
    )
    lines.append("")
    with open(RESULTS_MD, "a") as f:
        f.write("\n".join(lines))


def _evaluate_model(model_name: str, score_fn, legit_X, held_out_X, held_out_families) -> tuple[dict, dict, np.ndarray]:
    """held_out_X: feature-only frame passed straight to score_fn (must have
    exactly the columns the frozen model expects -- no attack_family/case_id
    riding along, or XGBoost/LightGBM's column-count/name validation breaks).
    held_out_families: attack_family labels for the SAME rows, same order/
    index, passed separately rather than embedded -- kept as two arguments
    instead of one frame so this works identically whether score_fn wants a
    strict feature-only frame (XGBoost/LightGBM) or a raw frame with extra
    columns it internally ignores (Autoencoder's transform())."""
    threshold = _frozen_threshold(model_name)
    legit_scores = score_fn(legit_X)
    held_scores = score_fn(held_out_X)

    y_true = np.concatenate([np.zeros(len(legit_scores)), np.ones(len(held_scores))])
    y_score = np.concatenate([legit_scores, held_scores])
    overall = compute_binary_metrics(y_true, y_score, threshold=threshold)
    print(f"  Overall: precision={overall['precision']:.4f} recall={overall['recall']:.4f} "
          f"roc_auc={overall['roc_auc']:.4f} fpr={overall['false_positive_rate']:.4f}")

    held_out_families = pd.Series(held_out_families).reset_index(drop=True)
    per_family = {}
    for fam in ATTACK_FAMILIES:
        idx = (held_out_families == fam).to_numpy()
        if not idx.any():
            continue
        fam_scores = held_scores[idx]
        combined_true = np.concatenate([np.zeros(len(legit_scores)), np.ones(len(fam_scores))])
        combined_score = np.concatenate([legit_scores, fam_scores])
        per_family[fam] = compute_binary_metrics(combined_true, combined_score, threshold=threshold)
        print(f"    {fam}: recall={per_family[fam]['recall']:.4f} (n={len(fam_scores)})")

    record_result(
        RESULTS_JSON, f"{model_name}_adversarial_eval", overall,
        extra={
            "n_legit": len(legit_scores),
            "n_fraud": len(held_scores),
            "per_family_recall": {fam: m["recall"] for fam, m in per_family.items()},
            "decision_threshold_reused_from_stage5": threshold,
            "note": "Section 8 step 4 -- frozen model, held-out combinations it never trained on "
                    "(evaluation/split_policy.py's held_out_only buckets).",
        },
    )
    _append_results_md(model_name, overall, per_family, len(legit_scores))
    return overall, per_family, held_scores


def _persist_to_supabase(model_name: str, threshold: float, held_out_df, held_scores) -> None:
    """Best-effort, matching the pattern in eval_phishing_classifier.py /
    eval_document_consistency.py / eval_voice_spoof.py: a Supabase hiccup
    here never invalidates the real numbers already recorded above.
    Aggregates transaction-row scores up to one row per case_id (max
    score across the case's sequence) since evaluation_results.case_id has
    a hard FK to attack_cases, which is case-granular. Legit Stage-5
    validation rows are real PaySim/IEEE-CIS transactions, not synthetic
    attack_cases rows, so they have no case_id to write here -- this
    persists the fraud side of the evaluation only; the real
    precision/recall/FPR numbers already recorded (which DO include the
    legit side) remain the authoritative record in metrics.json /
    EVALUATION_RESULTS.md."""
    try:
        from db.supabase_client import get_service_client
        client = get_service_client()

        case_df = held_out_df[["case_id"]].copy()
        case_df["score"] = held_scores
        agg = case_df.groupby("case_id", as_index=False)["score"].max()

        cases = [
            {"case_id": row.case_id, "score": float(row.score), "threshold": threshold,
             "is_fraud": True, "evidence": [f"{model_name}_score={row.score:.4f}"]}
            for row in agg.itertuples()
        ]
        run_id = record_run_and_results(
            client, run_type="adversarial_held_out", model_name=model_name, cases=cases,
        )
        print(f"  Supabase: evaluation_run {run_id} (adversarial_held_out, {len(cases)} per-case results, "
              f"{model_name})")
    except Exception as exc:
        # 2026-09-01: this branch fired silently for four models x two runs.
        # The held-out parquet was regenerated at 05:57, attack_cases was last
        # backfilled at 05:22, and case_id is uuid4().hex[:12] -- so not one of
        # the 2000 scored ids existed in attack_cases and the FK rejected every
        # batch. The only trace was this stderr line, inside a subprocess whose
        # stderr Colab never surfaced. It is a stdout banner now.
        print("\n  !! SUPABASE PERSISTENCE FAILED -- metrics.json / EVALUATION_RESULTS.md were "
              "still written, but NO per-case rows reached the database.", flush=True)
        print(f"  !! {type(exc).__name__}: {exc}", flush=True)
        # Advice derived from the exception TYPE, not a fixed guess -- see
        # explain_persistence_failure()'s docstring for the run this fixed.
        print(f"  !! {explain_persistence_failure(exc)}", flush=True)
        print(f"  Supabase per-case persistence skipped (non-fatal): {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-autoencoder", action="store_true", help="Skip Autoencoder even if PyTorch is available")
    args = parser.parse_args()

    if not HELD_OUT_PATH.exists():
        raise FileNotFoundError(f"{HELD_OUT_PATH} not found. Run generate/inject_attacks.py first.")

    print("Loading Stage-5 training pool to derive the legitimate comparison set "
          "(train_val_split's validation portion, seed=42)...")
    pool = load_training_pool()
    X_train, X_val, y_train, y_val = train_val_split(pool)
    legit_X = X_val[(y_val == 0).to_numpy()].copy()
    print(f"  {len(legit_X):,} legitimate rows available as the bonafide comparison set")
    # Free the ~6.95M-row pool and the discarded train-portion split before
    # doing anything else (model loading, held-out scoring) -- this run OOM'd
    # once already on this machine allocating just 53MB during the cast
    # above, so peak memory matters from here on.
    del pool, X_train, y_train, X_val, y_val
    gc.collect()

    print(f"Loading held-out adversarial set from {HELD_OUT_PATH} "
          "(combinations these frozen models never trained on)...")
    held_out_raw = pd.read_parquet(HELD_OUT_PATH)
    print(f"  {len(held_out_raw):,} rows across {held_out_raw['case_id'].nunique():,} cases, "
          f"{len(ATTACK_FAMILIES)} families")
    if not PREPROCESSOR_PATH.exists():
        raise FileNotFoundError(
            f"{PREPROCESSOR_PATH} not found. Run defend/train/fit_preprocessor.py first "
            f"(fits the shared categorical vocabulary from the same source data these "
            f"models trained on -- see defend/train/preprocessor.py's module docstring)."
        )
    prep = TabularPreprocessor.load(PREPROCESSOR_PATH)
    held_out_X = prep.transform_tree(held_out_raw)

    held_out_families = held_out_raw["attack_family"]

    print("\n=== XGBoost ===")
    xgb_model = _load_frozen_xgboost()
    xgb_score_fn = lambda df: xgb_model.predict_proba(df)[:, 1]  # noqa: E731
    _, _, xgb_held_scores = _evaluate_model("xgboost", xgb_score_fn, legit_X, held_out_X, held_out_families)
    _persist_to_supabase("xgboost", _frozen_threshold("xgboost"), held_out_raw, xgb_held_scores)

    print("\n=== LightGBM ===")
    lgb_booster = _load_frozen_lightgbm()
    lgb_score_fn = lambda df: lgb_booster.predict(df)  # noqa: E731
    _, _, lgb_held_scores = _evaluate_model("lightgbm", lgb_score_fn, legit_X, held_out_X, held_out_families)
    _persist_to_supabase("lightgbm", _frozen_threshold("lightgbm"), held_out_raw, lgb_held_scores)

    if not args.skip_autoencoder:
        print("\n=== Autoencoder ===")
        ae_score_fn, ok = _load_frozen_autoencoder()
        if ok:
            _, _, ae_held_scores = _evaluate_model("autoencoder", ae_score_fn, legit_X, held_out_raw, held_out_families)
            _persist_to_supabase("autoencoder", _frozen_threshold("autoencoder"), held_out_raw, ae_held_scores)
    else:
        print("\n=== Autoencoder === (skipped: --skip-autoencoder)")

    print(f"\nDone. Recorded results to {RESULTS_JSON} and {RESULTS_MD}.")
    print("This closes Section 8 step 4. Next: step 5 (identify the weakest family/combination -- "
          "read the per-family recall numbers just written) feeds Task #35's LLM strategist / "
          "rule-based fallback, per docs/AGENTIC_CONTRACT.md Section 1.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nEVAL FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
