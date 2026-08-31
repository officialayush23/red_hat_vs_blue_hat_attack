"""
Stage 5 (Blue Team) -- trains XGBoost on the real + train-portion-generated
training pool (defend/train/dataset.py), evaluates on an ordinary
stratified VALIDATION split of that pool (NOT the adversarial held-out set
-- see dataset.py's docstring), and saves the frozen model.

Per docs/TECHNICAL_SPEC.md Principle 10 ("no model ships without numbers")
and Section 8 step 2 ("train... freeze the models -- no further training
after this point"): re-running this script overwrites the saved model, so
do that deliberately (e.g. after changing the feature set), not as casual
iteration once evaluation/run_adversarial_eval.py (Stage 7) has scored a
specific frozen version.

Uses XGBoost's native pandas-category support (enable_categorical=True)
instead of one-hot encoding -- keeps the feature count small and lets
missing-for-this-dataset columns (e.g. card_type on a PaySim row) go
through as genuine missing values, which XGBoost's split-finding handles
directly rather than needing an imputed placeholder.

Usage:
    python backend/defend/train/train_xgboost.py
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

import xgboost as xgb  # noqa: E402

from defend.train.dataset import load_training_pool, train_val_split  # noqa: E402
from evaluation.metrics import best_f1_threshold, compute_binary_metrics, record_result  # noqa: E402

MODELS_DIR = BACKEND_DIR / "defend" / "models"
RESULTS_JSON = MODELS_DIR / "metrics.json"
RESULTS_MD = BACKEND_DIR.parent / "docs" / "EVALUATION_RESULTS.md"


def _append_results_md(model_name: str, metrics: dict, threshold: float, n_train: int, n_val: int) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS_MD.exists():
        RESULTS_MD.write_text(
            "# Evaluation Results\n\n"
            "Recorded automatically by each training/evaluation script -- do not hand-edit\n"
            "numbers here, re-run the script instead.\n"
        )
    section = (
        f"\n## {model_name} -- validation split (Stage 5, ordinary train/val, not adversarial)\n\n"
        f"- Threshold: {threshold:.4f}\n"
        f"- Precision: {metrics['precision']:.4f}\n"
        f"- Recall: {metrics['recall']:.4f}\n"
        f"- F1: {metrics['f1']:.4f}\n"
        f"- ROC-AUC: {metrics['roc_auc']:.4f}\n"
        f"- PR-AUC: {metrics['pr_auc']:.4f}\n"
        f"- False positive rate: {metrics['false_positive_rate']:.4%}\n"
        f"- Train set: {n_train:,} rows / Validation set: {metrics['n_samples']:,} rows "
        f"({metrics['n_positive']:,} fraud)\n"
    )
    with open(RESULTS_MD, "a") as f:
        f.write(section)


def main() -> None:
    print("Loading training pool (real data + train-portion generated attacks)...")
    pool = load_training_pool()
    print(f"  {len(pool):,} rows, fraud rate {pool['is_fraud'].mean():.4%}")

    X_train, X_val, y_train, y_val = train_val_split(pool)
    print(f"  train: {len(X_train):,} rows, val: {len(X_val):,} rows")

    pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="aucpr",
        enable_categorical=True,
        tree_method="hist",
        random_state=42,
        scale_pos_weight=pos_weight,
        early_stopping_rounds=30,
    )
    print(f"Training XGBoost (scale_pos_weight={pos_weight:.2f})...")
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    val_scores = model.predict_proba(X_val)[:, 1]
    threshold = best_f1_threshold(y_val, val_scores)
    metrics = compute_binary_metrics(y_val, val_scores, threshold=threshold)
    print(f"Validation metrics (threshold={threshold:.4f}):\n{json.dumps(metrics, indent=2)}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "xgboost.json"
    model.save_model(str(model_path))
    print(f"Saved model to {model_path}")

    record_result(
        RESULTS_JSON, "xgboost", metrics,
        extra={"decision_threshold": threshold, "n_train": len(X_train), "n_val": len(X_val)},
    )
    _append_results_md("XGBoost", metrics, threshold, len(X_train), len(X_val))
    print(f"Recorded results to {RESULTS_JSON} and {RESULTS_MD}")
    print("\nDone. Model frozen. Next: train_lightgbm.py, then train_autoencoder.py.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nTRAINING FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
