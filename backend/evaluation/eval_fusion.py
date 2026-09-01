"""
Section 6 evidence gate: does the real fusion layer (defend/fusion.py)
actually outperform its best individual signal? Reuses the exact
frozen-model-loading, preprocessing, and legit-baseline machinery
evaluation/run_adversarial_eval.py already built and verified
(2026-08-30) -- scores the SAME data/processed/attacks_held_out.parquet
set with XGBoost, LightGBM, and Autoencoder simultaneously, combines
their per-row scores via defend.fusion.fuse_tabular_scores(), and reports
precision/recall/F1/ROC-AUC/PR-AUC/FPR for the fused score exactly like
run_adversarial_eval.py already does per individual model -- directly
comparable, same held-out rows, same legit baseline, same metrics code.

The fusion decision threshold is picked on the Stage-5 VALIDATION split's
fused scores (a large, real, held-out-from-training set, ~1.39M rows) via
best_f1_threshold -- not on attacks_held_out.parquet itself, which would
overfit the threshold to the very data being evaluated. That threshold is
then applied, fixed, to the adversarial held-out numbers reported below --
the same discipline run_adversarial_eval.py already applies by reusing
each individual model's Stage-5 threshold rather than re-deriving one on
the test set.

Honest scope: this validates the WEIGHTED multi-model combination only.
defend.fusion.behavioral_adjustment() (Customer Universe corroboration)
is NOT exercised here -- attack_cases.customer_id linkage doesn't exist
yet for generated cases (Phase 2.5), so there's no real linked data to
test it against. See defend/fusion.py's module docstring.

Usage:
    python backend/evaluation/eval_fusion.py
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from defend.fusion import compute_fusion_weights, fuse_tabular_scores  # noqa: E402
from defend.train.dataset import load_training_pool, train_val_split  # noqa: E402
from defend.train.preprocessor import TabularPreprocessor  # noqa: E402
from evaluation.metrics import best_f1_threshold, compute_binary_metrics, record_result  # noqa: E402
from evaluation.supabase_results import record_run_and_results  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
HELD_OUT_PATH = PROCESSED_DIR / "attacks_held_out.parquet"
MODELS_DIR = BACKEND_DIR / "defend" / "models"
RESULTS_JSON = MODELS_DIR / "metrics.json"
RESULTS_MD = REPO_ROOT / "docs" / "EVALUATION_RESULTS.md"
PREPROCESSOR_PATH = MODELS_DIR / "tabular_preprocessor.joblib"

ATTACK_FAMILIES = ("transaction_fraud", "account_takeover", "synthetic_identity", "mule_network")


def _load_frozen_models():
    import xgboost as xgb
    import lightgbm as lgb

    xgb_model = xgb.XGBClassifier(enable_categorical=True, tree_method="hist")
    xgb_model.load_model(str(MODELS_DIR / "xgboost.json"))
    lgb_booster = lgb.Booster(model_file=str(MODELS_DIR / "lightgbm.txt"))

    ae_score_fn = None
    try:
        import torch
        from defend.train.train_autoencoder import Autoencoder, reconstruction_error, transform

        ckpt = torch.load(MODELS_DIR / "autoencoder.pt", map_location="cpu", weights_only=False)
        ae_model = Autoencoder(ckpt["input_dim"], hidden_dims=ckpt["hidden_dims"])
        ae_model.load_state_dict(ckpt["state_dict"])
        ae_model.eval()
        spec = ckpt["prep_spec"]

        def ae_score_fn(df: pd.DataFrame) -> np.ndarray:
            X = transform(df, spec)
            return reconstruction_error(ae_model, X, torch.device("cpu"))
    except (ImportError, SystemExit):
        print("  PyTorch not available -- fusion will run XGBoost+LightGBM only "
              "(weights renormalize automatically, see fuse_tabular_scores).", file=sys.stderr)

    def score_all(tree_X: pd.DataFrame, raw_df: pd.DataFrame) -> dict:
        scores = {
            "xgboost": xgb_model.predict_proba(tree_X)[:, 1],
            "lightgbm": lgb_booster.predict(tree_X),
        }
        if ae_score_fn is not None:
            scores["autoencoder"] = ae_score_fn(raw_df)
        return scores

    return score_all


def _fuse_rows(per_model_scores: dict, weights: dict) -> np.ndarray:
    """Vectorized equivalent of calling defend.fusion.fuse_tabular_scores()
    per row -- same weighted-average logic (renormalized over whichever
    models are present), just without a Python-level loop over up to
    ~1.39M rows. Returns scores in [0,1], matching individual model
    probabilities (fuse_tabular_scores' own 0-100 scaling is for display/
    decision-band purposes, not needed internally here)."""
    models = list(per_model_scores.keys())
    active = np.array([weights[m] for m in models], dtype="float64")
    active = active / active.sum()
    stacked = np.stack([np.asarray(per_model_scores[m], dtype="float64") for m in models], axis=1)
    return stacked @ active


def _append_results_md(overall: dict, per_family: dict, weights: dict, threshold: float, n_legit: int) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "\n## fusion (XGBoost + LightGBM + Autoencoder, weighted by real Stage-5 ROC-AUC) "
        "-- Section 6 evidence gate, held-out combinations\n",
        f"- Weights: {', '.join(f'{m}={w:.4f}' for m, w in weights.items())}",
        f"- Threshold: {threshold:.4f} (picked on Stage-5 validation's fused scores, not on held-out data itself)",
        f"- Precision: {overall['precision']:.4f}",
        f"- Recall: {overall['recall']:.4f}",
        f"- F1: {overall['f1']:.4f}",
        f"- ROC-AUC: {overall['roc_auc']:.4f}",
        f"- PR-AUC: {overall['pr_auc']:.4f}",
        f"- False positive rate: {overall['false_positive_rate']:.4%}",
        f"- n_legit={n_legit}, n_fraud={overall['n_samples'] - n_legit} (held-out combinations, transaction-row granularity)",
    ]
    for fam, m in per_family.items():
        lines.append(f"- {fam} recall: {m['recall']:.4f} (n_fraud_rows={m['n_positive']})")
    lines.append(
        "- Compare against the individual xgboost_adversarial_eval / lightgbm_adversarial_eval / "
        "autoencoder_adversarial_eval sections above -- same held-out rows, same legit baseline, "
        "so this is a fair apples-to-apples fusion-vs-best-single-model comparison."
    )
    lines.append(
        "- Scope: weighted multi-model combination only. Customer-behavior corroboration "
        "(defend.fusion.behavioral_adjustment) is NOT exercised here -- no real customer_id "
        "linkage exists yet for generated cases (Phase 2.5). See defend/fusion.py."
    )
    lines.append("")
    with open(RESULTS_MD, "a") as f:
        f.write("\n".join(lines))


def main() -> None:
    if not HELD_OUT_PATH.exists():
        raise FileNotFoundError(f"{HELD_OUT_PATH} not found. Run generate/inject_attacks.py first.")
    if not PREPROCESSOR_PATH.exists():
        raise FileNotFoundError(f"{PREPROCESSOR_PATH} not found. Run defend/train/fit_preprocessor.py first.")

    weights = compute_fusion_weights()
    print(f"Fusion weights (from real Stage-5 ROC-AUC): {weights}")

    prep = TabularPreprocessor.load(PREPROCESSOR_PATH)
    score_all = _load_frozen_models()

    print("Loading Stage-5 training pool to pick a fusion threshold on real validation data "
          "(not on the held-out set itself)...")
    pool = load_training_pool()
    X_train, X_val, y_train, y_val = train_val_split(pool)
    val_tree_X = X_val  # already in the exact dtype shape train_val_split/dataset.py produces
    val_scores = score_all(val_tree_X, val_tree_X)
    val_fused = _fuse_rows(val_scores, weights)
    threshold = best_f1_threshold(y_val.to_numpy(), val_fused)
    print(f"  Fusion threshold picked on Stage-5 validation: {threshold:.4f}")

    legit_val_X = X_val[(y_val == 0).to_numpy()].copy()
    del pool, X_train, y_train, X_val, y_val, val_tree_X, val_scores, val_fused
    import gc
    gc.collect()

    print(f"Loading held-out adversarial set from {HELD_OUT_PATH}...")
    held_out_raw = pd.read_parquet(HELD_OUT_PATH)
    held_out_X = prep.transform_tree(held_out_raw)
    held_out_families = held_out_raw["attack_family"]
    print(f"  {len(held_out_raw):,} rows across {held_out_raw['case_id'].nunique():,} cases")

    legit_scores = score_all(legit_val_X, legit_val_X)
    legit_fused = _fuse_rows(legit_scores, weights)
    held_scores = score_all(held_out_X, held_out_raw)
    held_fused = _fuse_rows(held_scores, weights)

    y_true = np.concatenate([np.zeros(len(legit_fused)), np.ones(len(held_fused))])
    y_score = np.concatenate([legit_fused, held_fused])
    overall = compute_binary_metrics(y_true, y_score, threshold=threshold)
    print(f"\nFusion overall: precision={overall['precision']:.4f} recall={overall['recall']:.4f} "
          f"roc_auc={overall['roc_auc']:.4f} fpr={overall['false_positive_rate']:.4f}")

    per_family = {}
    for fam in ATTACK_FAMILIES:
        idx = (held_out_families == fam).to_numpy()
        if not idx.any():
            continue
        fam_fused = held_fused[idx]
        combined_true = np.concatenate([np.zeros(len(legit_fused)), np.ones(len(fam_fused))])
        combined_score = np.concatenate([legit_fused, fam_fused])
        per_family[fam] = compute_binary_metrics(combined_true, combined_score, threshold=threshold)
        print(f"  {fam}: recall={per_family[fam]['recall']:.4f} (n={len(fam_fused)})")

    record_result(
        RESULTS_JSON, "fusion_adversarial_eval", overall,
        extra={
            "weights": weights,
            "threshold_source": "Stage-5 validation fused scores (best_f1_threshold), not held-out data",
            "n_legit": len(legit_fused),
            "n_fraud": len(held_fused),
            "per_family_recall": {fam: m["recall"] for fam, m in per_family.items()},
            "note": "Section 6 evidence gate -- weighted XGBoost+LightGBM+Autoencoder fusion, same "
                    "held-out set as the individual *_adversarial_eval entries, for direct comparison.",
        },
    )
    _append_results_md(overall, per_family, weights, threshold, len(legit_fused))

    try:
        client_cases = held_out_raw[["case_id"]].copy()
        client_cases["score"] = held_fused
        agg = client_cases.groupby("case_id", as_index=False)["score"].max()
        from db.supabase_client import get_service_client
        client = get_service_client()
        cases = [
            {"case_id": row.case_id, "score": float(row.score), "threshold": threshold,
             "is_fraud": True, "evidence": [f"fusion_score={row.score:.4f} weights={weights}"]}
            for row in agg.itertuples()
        ]
        run_id = record_run_and_results(client, run_type="adversarial_held_out", model_name="fusion", cases=cases)
        print(f"  Supabase: evaluation_run {run_id} (adversarial_held_out, {len(cases)} per-case results, fusion)")
    except Exception as exc:
        # Loud, on stdout, and flagged as a FAILURE -- not a quiet stderr
        # aside. This exact handler hid a 100% persistence failure on
        # 2026-09-01: every insert was rejected by evaluation_results'
        # foreign key to attack_cases because the backfill for this family
        # had never run, and the only trace was a stderr line inside a
        # subprocess whose stderr was not shown. metrics.json looked
        # perfect while Supabase received nothing.
        print("\n  !! SUPABASE PERSISTENCE FAILED -- metrics.json was still written, but NO "
              "per-case rows reached the database.", flush=True)
        print(f"  !! {type(exc).__name__}: {exc}", flush=True)
        print("  !! If this mentions a foreign key on case_id, this family's cases are missing "
              "from attack_cases: run `python generate/run_all_generation.py "
              "--only backfill_attack_cases,backfill_phase2_artifacts` and re-run this eval.",
              flush=True)
        print(f"  Supabase per-case persistence skipped (non-fatal): {exc}", file=sys.stderr)

    print(f"\nDone. Recorded results to {RESULTS_JSON} and {RESULTS_MD}.")
    print("Compare fusion_adversarial_eval against xgboost_adversarial_eval / lightgbm_adversarial_eval / "
          "autoencoder_adversarial_eval in EVALUATION_RESULTS.md -- this is the real answer to "
          "'does fusion help.'")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nEVAL FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
