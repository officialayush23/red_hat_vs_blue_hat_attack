"""
Stage 5 (Blue Team) -- trains LightGBM on the same training pool and
validation split as train_xgboost.py (defend/train/dataset.py). This is
the "ensemble diversity, not redundancy" model from docs/TECHNICAL_SPEC.md
Section 5 -- a different learner over the same feature space, not a
retrain of the same algorithm.

Same freeze discipline as train_xgboost.py: re-running overwrites the
saved model, do that deliberately once Stage 7 has scored a frozen
version.

LightGBM's sklearn API natively handles pandas 'category' dtype columns
(passed via categorical_feature) -- same reasoning as XGBoost's
enable_categorical, no one-hot encoding needed here either.

Usage:
    python backend/defend/train/train_lightgbm.py
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

import lightgbm as lgb  # noqa: E402

from defend.train.dataset import CATEGORICAL_FEATURES, load_training_pool, train_val_split  # noqa: E402
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

    model = lgb.LGBMClassifier(
        n_estimators=300,
        num_leaves=63,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        class_weight="balanced",
        random_state=42,
        verbosity=-1,
    )
    print("Training LightGBM...")
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        eval_metric="average_precision",
        categorical_feature=CATEGORICAL_FEATURES,
        callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)],
    )

    val_scores = model.predict_proba(X_val)[:, 1]
    threshold = best_f1_threshold(y_val, val_scores)
    metrics = compute_binary_metrics(y_val, val_scores, threshold=threshold)
    print(f"Validation metrics (threshold={threshold:.4f}):\n{json.dumps(metrics, indent=2)}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "lightgbm.txt"
    model.booster_.save_model(str(model_path))
    print(f"Saved model to {model_path}")

    record_result(
        RESULTS_JSON, "lightgbm", metrics,
        extra={"decision_threshold": threshold, "n_train": len(X_train), "n_val": len(X_val)},
    )
    _append_results_md("LightGBM", metrics, threshold, len(X_train), len(X_val))
    print(f"Recorded results to {RESULTS_JSON} and {RESULTS_MD}")
    print("\nDone. Model frozen. Next: train_autoencoder.py.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nTRAINING FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
