"""
Phase 2.5 (Task #32) -- reads backend/defend/models/metrics.json (the local
file every train_*.py / eval_*.py script upserts into) and backfills the
Supabase `model_registry` table, so the dashboard's model-status view has
real data instead of mock rows.

Status assignment follows Principle 11 literally, not a blanket label:
'validated' only for a model that has a real run against a real, frozen
held-out/evidence-gate set recorded --
  - document_consistency_detector, voice_spoof_detector: pretrained
    inference, evidence-gate run against our own generated bonafide+attack
    set is the ONLY evaluation they have, so that run is what validates them.
  - phishing_classifier: has BOTH a Stage 5 ordinary train/val run (on real
    difraud data) AND a Principle 11 evidence-gate run (against our own
    generated phishing_scam cases, metrics.json key
    'phishing_classifier_evidence_gate') -- collapsed into ONE registry row
    here (id='phishing_classifier'), validation_metrics=Stage 5 numbers,
    test_metrics=evidence-gate numbers. It's 'validated' because the
    evidence-gate run happened and is real -- Principle 11 requires a real
    run with recorded numbers, not good numbers.
  - xgboost / lightgbm / autoencoder: 'validated' as of 2026-08-30 --
    evaluation/run_adversarial_eval.py (Stage 7) now exists and has scored
    all three against data/processed/attacks_held_out.parquet
    (metrics.json keys '<model>_adversarial_eval'). validation_metrics
    stays the Stage 5 train/val numbers; test_metrics is now the real
    Stage 7 adversarial numbers, not None. If a given model's
    '<model>_adversarial_eval' key is missing (e.g. run_adversarial_eval.py
    hasn't been (re)run since a retrain), this script honestly falls back
    to 'experimental' for that one model rather than assuming it's still
    valid -- never carries forward a stale 'validated' label.
  - fusion: the real Section 6 fusion layer (defend/fusion.py), evaluated
    by evaluation/eval_fusion.py against the SAME held-out set as the
    three models above. Only added when 'fusion_adversarial_eval' exists
    in metrics.json -- not backfilled as a placeholder before that script
    has actually run.

Idempotent -- re-running overwrites (upsert on id), safe after any
train_*.py / eval_*.py re-run.

Usage:
    python backend/db/backfill_model_registry.py
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from db.supabase_client import get_service_client  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
METRICS_PATH = BACKEND_DIR / "defend" / "models" / "metrics.json"

# id -> (signal_category, purpose, artifact_path)
TABULAR_MODELS = {
    "xgboost": ("transaction", "Primary transaction-fraud gradient-boosted classifier", "backend/defend/models/xgboost.json"),
    "lightgbm": ("transaction", "Secondary transaction-fraud gradient-boosted classifier", "backend/defend/models/lightgbm.txt"),
    "autoencoder": ("transaction", "Unsupervised reconstruction-error anomaly detector", "backend/defend/models/autoencoder.pt"),
}


def _build_rows(data: dict) -> list:
    rows = []

    for model_id, (category, purpose, artifact_path) in TABULAR_MODELS.items():
        if model_id not in data:
            continue
        entry = data[model_id]
        adversarial = data.get(f"{model_id}_adversarial_eval")
        rows.append({
            "id": model_id,
            "purpose": purpose,
            "dataset": "real (PaySim/IEEE-CIS) + train-portion generated attacks",
            "training_summary": f"Stage 5 ordinary train/val split -- n_train={entry.get('n_train')}, "
                                 f"n_val={entry.get('n_val')}, threshold={entry.get('decision_threshold')}"
                                 + (f". Stage 7 adversarial: held-out recall {adversarial['metrics']['recall']:.4f}, "
                                    f"per-family {adversarial.get('per_family_recall')}" if adversarial else ""),
            "signal_category": category,
            "validation_metrics": entry["metrics"],
            "test_metrics": adversarial["metrics"] if adversarial else None,
            "status": "validated" if adversarial else "experimental",
            "version": "v1",
            "artifact_path": artifact_path,
        })

    if "fusion_adversarial_eval" in data:
        fusion = data["fusion_adversarial_eval"]
        rows.append({
            "id": "fusion",
            "purpose": "Section 6 real fusion layer -- weighted combination of XGBoost/LightGBM/Autoencoder "
                       "signals, weights from each model's real Stage-5 ROC-AUC",
            "dataset": "same held-out set as the individual tabular models (data/processed/attacks_held_out.parquet)",
            "training_summary": f"weights={fusion.get('weights')}, threshold_source={fusion.get('threshold_source')}, "
                                 f"per_family_recall={fusion.get('per_family_recall')}",
            "signal_category": "transaction",
            "validation_metrics": None,
            "test_metrics": fusion["metrics"],
            "status": "validated",
            "version": "v1 (weighted average, no behavioral corroboration validated yet -- see defend/fusion.py)",
            "artifact_path": "backend/defend/fusion.py",
        })

    if "gnn_adversarial_eval" in data:
        gnn_eval = data["gnn_adversarial_eval"]
        gnn_train = data.get("gnn", {})
        local_reverify = data.get("gnn_adversarial_eval_local_reverify")
        summary = (f"2-layer GraphSAGE encoder + MLP edge classifier, trained on Colab. "
                   f"IBM AML held-out (Colab): {gnn_train.get('metrics', {})}. "
                   f"mule_network held-out recall (Colab-reported): "
                   f"{gnn_eval.get('per_family_recall', {}).get('mule_network')}.")
        if local_reverify:
            summary += (f" Independently re-verified locally: recall="
                        f"{local_reverify['metrics'].get('recall')} -- see docs/DATASETS.md.")
        rows.append({
            "id": "gnn",
            "purpose": "Mule-network fraud-ring detection via account-transaction graph structure (Task #33)",
            "dataset": gnn_train.get("trained_on", "IBM Transactions for Anti-Money Laundering (AML), HI-Small"),
            "training_summary": summary,
            "signal_category": "graph",
            "validation_metrics": gnn_train.get("metrics"),
            "test_metrics": gnn_eval["metrics"],
            "status": "validated",
            "version": "v1 (GraphSAGE, trained on Colab -- see notebooks/train_gnn_mule_network.ipynb)",
            "artifact_path": "backend/defend/models/gnn.pt",
        })

    if "voice_spoof_detector" in data:
        entry = data["voice_spoof_detector"]
        rows.append({
            "id": "voice_spoof_detector",
            "purpose": "Cloned/synthetic voice detection (pretrained wav2vec2)",
            "dataset": f"self-generated evidence-gate set: n_bonafide={entry.get('n_bonafide')}, n_spoof={entry.get('n_spoof')}",
            "training_summary": entry.get("note", ""),
            "signal_category": "voice",
            "validation_metrics": None,
            "test_metrics": entry["metrics"],
            "status": "validated",
            "version": "garystafford/wav2vec2-deepfake-voice-detector",
            "artifact_path": "backend/defend/pretrained/voice_spoof_detector.py",
        })

    if "document_consistency_detector" in data:
        entry = data["document_consistency_detector"]
        rows.append({
            "id": "document_consistency_detector",
            "purpose": "Tampered invoice / QR-payload consistency detection (pretrained OCR-VL + rule-based cross-check)",
            "dataset": f"self-generated evidence-gate set: n_bonafide={entry.get('n_bonafide')}, n_fraud={entry.get('n_fraud')}",
            "training_summary": entry.get("note", ""),
            "signal_category": "document",
            "validation_metrics": None,
            "test_metrics": entry["metrics"],
            "status": "validated",
            "version": "PaddleOCR-VL + custom QR cross-check",
            "artifact_path": "backend/defend/pretrained/document_consistency_detector.py",
        })

    if "phishing_classifier" in data:
        stage5 = data["phishing_classifier"]
        gate = data.get("phishing_classifier_evidence_gate", {})
        rows.append({
            "id": "phishing_classifier",
            "purpose": "Phishing/scam SMS & email text classification",
            "dataset": stage5.get("trained_on", "difraud/difraud phishing + sms domains"),
            "training_summary": f"TF-IDF + urgency/actionability/credential/URL-shape features + LogisticRegression. "
                                 f"Stage 5: n_train={stage5.get('n_train')}, n_val={stage5.get('n_val')}. "
                                 f"Evidence gate: n_bonafide={gate.get('n_bonafide')}, n_fraud={gate.get('n_fraud')}, "
                                 f"held_out_recall={gate.get('held_out_recall')}.",
            "signal_category": "text",
            "validation_metrics": stage5["metrics"],
            "test_metrics": gate.get("metrics"),
            "status": "validated" if gate else "experimental",
            "version": "v2 (intent + URL features)",
            "artifact_path": "backend/defend/models/phishing_classifier.joblib",
        })

    return rows


def main() -> None:
    if not METRICS_PATH.exists():
        raise FileNotFoundError(f"{METRICS_PATH} not found. Run at least one train_*.py / eval_*.py script first.")
    data = json.loads(METRICS_PATH.read_text())
    rows = _build_rows(data)
    if not rows:
        print("No recognized model entries in metrics.json -- nothing to backfill.")
        return

    client = get_service_client()
    client.table("model_registry").upsert(rows, on_conflict="id").execute()
    print(f"Upserted {len(rows)} model_registry rows:")
    for r in rows:
        print(f"  {r['id']:35s} status={r['status']:12s} signal={r['signal_category']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nBACKFILL FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
