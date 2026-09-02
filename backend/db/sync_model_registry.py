"""
Upserts backend/defend/models/metrics.json (written by every train_*.py
script via evaluation/metrics.py's record_result()) into the Supabase
`model_registry` table -- the evidence cards Principle 11 requires.

This is intentionally a thin sync, not a source of truth: metrics.json
stays the source of truth (it's what every training script writes to
directly, on the user's own machine), this script just mirrors it into the
DB so the dashboard/model registry can read it without a backend process
having local filesystem access to metrics.json at request time.

Only models with a MODEL_META entry are marked "validated" here --
everything else (OCR, phishing, GNN, video-KYC, photo) stays
"experimental" until its own training/evaluation script upserts real
numbers AND gets a MODEL_META entry, per Principle 11. Re-run this after
every training/evaluation run to keep the registry current.

Usage:
    python backend/db/sync_model_registry.py
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from db.supabase_client import get_service_client  # noqa: E402

METRICS_PATH = BACKEND_DIR / "defend" / "models" / "metrics.json"

# Static metadata per model -- the parts metrics.json doesn't carry.
MODEL_META = {
    "xgboost": {
        "purpose": "Primary tabular classifier -- transaction + account-takeover signals",
        "dataset": "PaySim + IEEE-CIS + Stage 4 train-portion generated attacks",
        "signal_category": "transaction",
        "artifact_path": "backend/defend/models/xgboost.json",
    },
    "lightgbm": {
        "purpose": "Same feature space as XGBoost, different learner -- ensemble diversity",
        "dataset": "PaySim + IEEE-CIS + Stage 4 train-portion generated attacks",
        "signal_category": "transaction",
        "artifact_path": "backend/defend/models/lightgbm.txt",
    },
    "autoencoder": {
        "purpose": "Unknown/zero-day fraud -- trained only on legitimate transactions, reconstruction error as anomaly score",
        "dataset": "PaySim + IEEE-CIS legitimate transactions only",
        "signal_category": "behavioral",
        "artifact_path": "backend/defend/models/autoencoder.pt",
    },
    "voice_spoof_detector": {
        "purpose": "Pretrained inference -- scores voice_scam attack audio for spoof/deepfake probability "
                   "(garystafford/wav2vec2-deepfake-voice-detector, Apache 2.0)",
        "dataset": "Bonafide: small LibriSpeech sample. Spoof: our own Chatterbox-generated voice_scam cases "
                   "(generate/generate_voice_attacks.py) -- Principle 11 evidence-gate run, not the model's own training data",
        "signal_category": "voice",
        "artifact_path": None,  # pretrained, no local weights committed
    },
    "document_consistency_detector": {
        # 2026-09-02: was "PaddleOCR-VL". The measured winner is rapidocr
        # (recall 1.0000 / FPR 0.1600 on n=680, vs paddlevl's 0.9125 / 0.2500
        # on n=120), and this string is what the Model Performance page labels
        # the model with -- so it named the losing engine on every card.
        "purpose": "Pretrained inference -- rapidocr (PP-OCR ONNX) extracts printed invoice fields, cross-checked "
                   "against the invoice's own QR-encoded payload for tampering "
                   "(defend/pretrained/document_consistency_detector.py)",
        "dataset": "Bonafide: self-generated fully-consistent invoices. Fraud: our own tampered document_fraud "
                   "cases (generate/generate_document_attacks.py) -- Principle 11 evidence-gate run",
        "signal_category": "document",
        "artifact_path": None,  # pretrained, no local weights committed
    },
    # 2026-08-31: the four entries below give the frontend's Model Performance
    # page real held-out/adversarial numbers to show (not the same-distribution
    # validation numbers) -- same models as above, scored against combinations
    # they never saw during training (evaluation/run_adversarial_eval.py /
    # eval_video_kyc.py / eval_phishing_classifier.py's evidence-gate split).
    "xgboost_adversarial_eval": {
        "purpose": "XGBoost, Section 8 step 4 -- frozen model scored on held-out-only combinations it never trained on",
        "dataset": "Held-out-only combinations, evaluation/split_policy.py's FAMILIES",
        "signal_category": "transaction",
        "artifact_path": "backend/defend/models/xgboost.json",
    },
    "lightgbm_adversarial_eval": {
        "purpose": "LightGBM, Section 8 step 4 -- frozen model scored on held-out-only combinations it never trained on",
        "dataset": "Held-out-only combinations, evaluation/split_policy.py's FAMILIES",
        "signal_category": "transaction",
        "artifact_path": "backend/defend/models/lightgbm.txt",
    },
    "autoencoder_adversarial_eval": {
        "purpose": "Autoencoder, Section 8 step 4 -- frozen model scored on held-out-only combinations it never trained on",
        "dataset": "Held-out-only combinations, evaluation/split_policy.py's FAMILIES",
        "signal_category": "behavioral",
        "artifact_path": "backend/defend/models/autoencoder.pt",
    },
    "video_kyc_detector": {
        "purpose": "Pretrained face-embedding inference (facenet-pytorch, MTCNN+InceptionResnetV1/VGGFace2) -- "
                   "identity mismatch between a video-KYC submission and the customer's reference photo",
        "dataset": "Bonafide + lookalike-impostor video pairs (generate/generate_video_kyc_attacks.py) -- "
                   "Principle 11 evidence-gate run",
        "signal_category": "identity",
        "artifact_path": None,  # pretrained, no local weights committed
    },
    "phishing_classifier_evidence_gate": {
        "purpose": "TF-IDF + urgency/actionability/credential/reassurance/URL-shape features + LogisticRegression, "
                   "trained on real difraud/difraud data, scored here against our own generated phishing_scam "
                   "artifacts it never trained on",
        "dataset": "generate/generate_phishing_attacks.py cases -- Principle 11 evidence-gate run",
        "signal_category": "text",
        "artifact_path": "backend/defend/models/phishing_classifier.joblib",
    },
    "gnn_colab_round5_reported": {
        "purpose": "2-layer directional GraphSAGE + MLP edge classifier (round 5: real graph-topology + temporal/"
                   "velocity + port-numbering features, train-period z-score normalization) -- mule-network "
                   "laundering-edge detection",
        "dataset": "IBM Transactions for Anti-Money Laundering (AML), HI-Small",
        "signal_category": "graph",
        "artifact_path": "backend/defend/models/gnn.pt",
    },
}


def main() -> None:
    if not METRICS_PATH.exists():
        raise FileNotFoundError(f"{METRICS_PATH} not found. Run the train_*.py scripts first.")

    metrics = json.loads(METRICS_PATH.read_text())
    client = get_service_client()

    rows = []
    for model_id, entry in metrics.items():
        meta = MODEL_META.get(model_id, {})
        rows.append({
            "id": model_id,
            "purpose": meta.get("purpose"),
            "dataset": meta.get("dataset"),
            "training_summary": f"n_train={entry.get('n_train')}, n_val={entry.get('n_val')}, "
                                 f"decision_threshold={entry.get('decision_threshold')}",
            "signal_category": meta.get("signal_category"),
            "validation_metrics": entry.get("metrics"),
            "test_metrics": None,  # filled once evaluation/run_adversarial_eval.py (Stage 7) exists
            "status": "validated" if model_id in MODEL_META else "experimental",
            "version": "phase1_frozen",
            "artifact_path": meta.get("artifact_path"),
        })

    if rows:
        client.table("model_registry").upsert(rows, on_conflict="id").execute()
    print(f"Synced {len(rows)} model_registry rows from {METRICS_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nSYNC FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
