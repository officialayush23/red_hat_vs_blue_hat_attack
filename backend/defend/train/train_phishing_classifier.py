"""
Stage 5 (Blue Team) -- trains a TF-IDF + LogisticRegression phishing/scam
text classifier on REAL labeled data (difraud/difraud, MIT license,
confirmed 2026-08-30 -- docs/TECHNICAL_SPEC.md Section 5), evaluates on
difraud's own validation split (an ordinary train/val split, same
"Stage 5, not adversarial" convention as train_xgboost.py), and saves the
frozen model.

Deliberately TF-IDF + LogisticRegression, not a transformer -- per
docs/TECHNICAL_SPEC.md Section 5 this is the documented fallback path,
chosen ON PURPOSE here (not as a downgrade) to keep this script entirely
off GPU/torch/transformers, after this project's extended GPU-driver saga
this same session (four distinct low-level CUDA/cudnn errors on
paddleocr_env, a torch/nccl collision on Colab). A linear bag-of-words
model is also a reasonable real-world baseline for short scam text and
trains on CPU in seconds.

v2 (2026-08-30): plain TF-IDF alone scored ROC-AUC 0.59 / 70% FPR on our
own generated bonafide messages (a real evidence-gate finding, see
evaluation/eval_phishing_classifier.py and backend/_diag_phishing_fp.py) --
banking-topic vocabulary is shared between legitimate notifications and
phishing text, so bag-of-words alone conflates topic with intent. Fixed
by adding hand-engineered urgency/actionability features
(defend/text_features.py, hstacked onto the TF-IDF matrix) -- the actual
differentiator between "we received your payment" and "verify your
payment immediately."

Uses two of difraud's seven domains -- "phishing" (email-shaped) and
"sms" -- combined into one pool, since our own generated artifacts
(generate/generate_phishing_attacks.py) span both channels
(phishing_text_gen.CHANNELS = ("sms", "email")) and a classifier that's
only ever seen one channel would be evaluated out-of-distribution on the
other.

Downloads difraud's train.jsonl/validation.jsonl for both domains directly
from Hugging Face on first run (cached under data/raw/difraud/, which is
already gitignored) -- these are plain-text jsonl files of scam/phishing
message content, so Hugging Face's automated content scanner flags the
phishing/ files "unsafe" (a keyword-based content flag, not a malware
verdict); safe to download, this is exactly the labeled fraud-text data
the classifier is meant to learn from.

Usage:
    python backend/defend/train/train_phishing_classifier.py
"""

import json
import sys
from pathlib import Path

import joblib
import requests
from scipy.sparse import hstack

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from defend.text_features import build_hand_features  # noqa: E402
from evaluation.metrics import best_f1_threshold, compute_binary_metrics, record_result  # noqa: E402

from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw" / "difraud"
MODELS_DIR = BACKEND_DIR / "defend" / "models"
RESULTS_JSON = MODELS_DIR / "metrics.json"
RESULTS_MD = BACKEND_DIR.parent / "docs" / "EVALUATION_RESULTS.md"

HF_BASE = "https://huggingface.co/datasets/difraud/difraud/resolve/main"
DOMAINS = ("phishing", "sms")
SPLITS = ("train", "validation")


def _download_if_missing(domain: str, split: str) -> Path:
    dest = RAW_DIR / domain / f"{split}.jsonl"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{HF_BASE}/{domain}/{split}.jsonl"
    print(f"Downloading {url} ...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    print(f"  saved {dest} ({len(resp.content):,} bytes)")
    return dest


def _load_jsonl(path: Path) -> tuple[list[str], list[int]]:
    texts, labels = [], []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            texts.append(row["text"])
            labels.append(int(row["label"]))
    return texts, labels


def _load_pool(split: str) -> tuple[list[str], list[int]]:
    texts, labels = [], []
    for domain in DOMAINS:
        path = _download_if_missing(domain, split)
        t, l = _load_jsonl(path)
        texts.extend(t)
        labels.extend(l)
        print(f"  {domain}/{split}.jsonl: {len(t):,} rows, {sum(l):,} deceptive ({sum(l) / len(l):.2%})")
    return texts, labels


def _append_results_md(metrics: dict, threshold: float, n_train: int, n_val: int) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS_MD.exists():
        RESULTS_MD.write_text(
            "# Evaluation Results\n\n"
            "Recorded automatically by each training/evaluation script -- do not hand-edit\n"
            "numbers here, re-run the script instead.\n"
        )
    section = (
        f"\n## phishing_classifier (TF-IDF + LogisticRegression) "
        f"-- validation split (Stage 5, ordinary train/val, not adversarial)\n\n"
        f"- Trained on: difraud/difraud phishing + sms domains (real labeled data, MIT license)\n"
        f"- Threshold: {threshold:.4f}\n"
        f"- Precision: {metrics['precision']:.4f}\n"
        f"- Recall: {metrics['recall']:.4f}\n"
        f"- F1: {metrics['f1']:.4f}\n"
        f"- ROC-AUC: {metrics['roc_auc']:.4f}\n"
        f"- PR-AUC: {metrics['pr_auc']:.4f}\n"
        f"- False positive rate: {metrics['false_positive_rate']:.4%}\n"
        f"- Train set: {n_train:,} rows / Validation set: {metrics['n_samples']:,} rows "
        f"({metrics['n_positive']:,} deceptive)\n"
    )
    with open(RESULTS_MD, "a") as f:
        f.write(section)


def main() -> None:
    print("Loading difraud/difraud training pool (phishing + sms domains, train split)...")
    X_train_text, y_train = _load_pool("train")
    print(f"  total train: {len(X_train_text):,} rows")

    print("Loading difraud/difraud validation pool (phishing + sms domains, validation split)...")
    X_val_text, y_val = _load_pool("validation")
    print(f"  total val: {len(X_val_text):,} rows")

    print("Vectorizing (TF-IDF, unigrams+bigrams, max_features=30000)...")
    vectorizer = TfidfVectorizer(max_features=30000, ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    X_train_tfidf = vectorizer.fit_transform(X_train_text)
    X_val_tfidf = vectorizer.transform(X_val_text)

    print("Adding hand-engineered urgency/actionability features (defend/text_features.py)...")
    X_train = hstack([X_train_tfidf, build_hand_features(X_train_text)]).tocsr()
    X_val = hstack([X_val_tfidf, build_hand_features(X_val_text)]).tocsr()

    print("Training LogisticRegression (class_weight=balanced)...")
    model = LogisticRegression(max_iter=1000, class_weight="balanced", C=1.0, random_state=42)
    model.fit(X_train, y_train)

    val_scores = model.predict_proba(X_val)[:, 1]
    threshold = best_f1_threshold(y_val, val_scores)
    metrics = compute_binary_metrics(y_val, val_scores, threshold=threshold)
    print(f"Validation metrics (threshold={threshold:.4f}):\n{json.dumps(metrics, indent=2)}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "phishing_classifier.joblib"
    joblib.dump({"vectorizer": vectorizer, "model": model, "threshold": threshold}, model_path)
    print(f"Saved model to {model_path}")

    record_result(
        RESULTS_JSON, "phishing_classifier", metrics,
        extra={
            "decision_threshold": threshold,
            "n_train": len(X_train_text),
            "n_val": len(X_val_text),
            "trained_on": "difraud/difraud phishing + sms domains (real labeled data, MIT license)",
        },
    )
    _append_results_md(metrics, threshold, len(X_train_text), len(X_val_text))
    print(f"Recorded results to {RESULTS_JSON} and {RESULTS_MD}")
    print("\nDone. Model frozen. Next: evaluation/eval_phishing_classifier.py "
          "(evidence-gate run against our own generated phishing_scam cases).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nTRAINING FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
