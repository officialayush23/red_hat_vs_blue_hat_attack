"""
Shared metrics computation -- precision/recall/F1/ROC-AUC/PR-AUC/false
positive rate, used by every training script (Stage 5) and, later, the
adversarial evaluation harness (Stage 7). One place so "how we compute a
metric" can't drift between models (docs/TECHNICAL_SPEC.md Section 8 step
4 names this exact metric set).
"""

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    average_precision_score, confusion_matrix, f1_score,
    precision_recall_curve, precision_score, recall_score, roc_auc_score,
)


def compute_binary_metrics(y_true, y_score, threshold: float = 0.5) -> dict:
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    y_pred = (y_score >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    multi_class_present = len(np.unique(y_true)) > 1

    return {
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_score)) if multi_class_present else None,
        "pr_auc": float(average_precision_score(y_true, y_score)) if multi_class_present else None,
        "false_positive_rate": float(fpr),
        "n_samples": int(len(y_true)),
        "n_positive": int(y_true.sum()),
        "true_positives": int(tp), "false_positives": int(fp),
        "true_negatives": int(tn), "false_negatives": int(fn),
    }


def best_f1_threshold(y_true, y_score) -> float:
    """Threshold that maximizes F1 on (y_true, y_score) -- used to pick an
    operating point for the confusion-matrix-based metrics above. ROC-AUC
    and PR-AUC themselves don't need a threshold; this is only for
    precision/recall/F1 at a single reported cutoff.
    """
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    if not len(thresholds):
        return 0.5
    f1 = 2 * precision * recall / (precision + recall + 1e-12)
    return float(thresholds[np.argmax(f1[:-1])])


def record_result(results_path, model_name: str, metrics: dict, extra: dict | None = None) -> None:
    """Upsert one model's metrics into a shared JSON results file (keyed by
    model_name, so re-running a training script updates its own entry
    without disturbing the others).
    """
    results_path = Path(results_path)
    data = json.loads(results_path.read_text()) if results_path.exists() else {}
    entry = {"metrics": metrics}
    if extra:
        entry.update(extra)
    data[model_name] = entry
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(data, indent=2))
