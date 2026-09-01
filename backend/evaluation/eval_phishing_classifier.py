"""
Principle 11 evidence gate for the phishing_classifier (TF-IDF +
LogisticRegression, trained on real difraud/difraud data by
defend/train/train_phishing_classifier.py): scores our own self-generated
bonafide (data/generated/phishing_bonafide/) and phishing_scam attack
cases (data/generated/phishing_attacks/{train,held_out}/, from
generate/generate_phishing_attacks.py) and records real
precision/recall/ROC-AUC/PR-AUC -- whatever they turn out to be -- to
backend/defend/models/metrics.json and docs/EVALUATION_RESULTS.md.
Structurally identical to eval_document_consistency.py; see that file for
the general pattern this follows.

This is the actual generalization test: the classifier trains only on
difraud/difraud's real-world phishing/sms text, and never sees our own
generated artifacts until this evaluation. Per Principle 13 (attack labels
are evaluation-only metadata, never a detector input), the case JSON's
"is_fraud"/"split_portion"/"attack_family" fields are read here, in the
eval harness, and nowhere inside the classifier itself -- the classifier
only ever sees the raw "subject"+"body" text, exactly like a live scoring
call would pass it.

Reports the held_out split separately from train -- held_out includes two
combinations the classifier's training data has no equivalent shape for:
"employer_hr"/"lottery_prize" impersonation targets (novel to difraud) and
hinglish code-mixed text (difraud is English-only) -- see
evaluation/split_policy.py's phishing_scam entry. A recall gap here is a
real, expected finding: it is precisely the "can this generalize past
what it was trained on" question Section 8 exists to ask.

Usage:
    python backend/evaluation/eval_phishing_classifier.py
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from scipy.sparse import hstack

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from db.supabase_client import get_service_client  # noqa: E402
from defend.text_features import FEATURE_NAMES, build_hand_features  # noqa: E402
from evaluation.metrics import compute_binary_metrics, record_result  # noqa: E402
from evaluation.supabase_results import record_run_and_results  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
BONAFIDE_DIR = REPO_ROOT / "data" / "generated" / "phishing_bonafide"
ATTACKS_DIR = REPO_ROOT / "data" / "generated" / "phishing_attacks"
MODELS_DIR = BACKEND_DIR / "defend" / "models"
MODEL_PATH = MODELS_DIR / "phishing_classifier.joblib"
RESULTS_JSON = MODELS_DIR / "metrics.json"
RESULTS_MD = BACKEND_DIR.parent / "docs" / "EVALUATION_RESULTS.md"


def _case_text(case: dict) -> str:
    """Same text a live API call would score: subject (email only) + body.
    Deliberately does NOT touch case['is_fraud']/['split_portion']/
    ['attack_family'] -- Principle 13."""
    subject = case.get("subject", "")
    body = case.get("body", "")
    return f"{subject}\n{body}".strip() if subject else body


def _score_texts(vectorizer, model, texts: list[str]) -> np.ndarray:
    """Must build features identically to train_phishing_classifier.py
    (TF-IDF hstacked with defend.text_features.build_hand_features) --
    both import from the same module so this can't silently drift."""
    X_tfidf = vectorizer.transform(texts)
    X = hstack([X_tfidf, build_hand_features(texts)]).tocsr()
    return model.predict_proba(X)[:, 1]


def _evidence_for(text: str) -> list:
    """Task #32: which of text_features.py's signals actually fired for
    THIS case -- the detector's own reasoning trace, for the evidence
    viewer. Nonzero features only, so a clean message shows an empty list
    rather than a wall of zeros."""
    row = build_hand_features([text]).toarray()[0]
    return [f"{name}={int(v)}" for name, v in zip(FEATURE_NAMES, row) if v]


def _append_results_md(overall: dict, per_split: dict, n_bonafide: int) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS_MD.exists():
        RESULTS_MD.write_text(
            "# Evaluation Results\n\n"
            "Recorded automatically by each training/evaluation script -- do not hand-edit\n"
            "numbers here, re-run the script instead.\n"
        )
    columns = [("overall", overall)] + list(per_split.items())
    header = "| Metric | " + " | ".join(name.replace("_", "-") for name, _ in columns) + " |"
    sep = "|---|" + "---|" * len(columns)
    metric_rows = [
        ("Precision", "precision", "{:.4f}"), ("Recall", "recall", "{:.4f}"),
        ("F1", "f1", "{:.4f}"), ("ROC-AUC", "roc_auc", "{:.4f}"), ("PR-AUC", "pr_auc", "{:.4f}"),
        ("FPR (bonafide flagged as phishing)", "false_positive_rate", "{:.2%}"),
        ("n_positive (phishing cases in this column)", "n_positive", "{:d}"),
    ]
    table_lines = [header, sep]
    for label, key, fmt in metric_rows:
        cells = [fmt.format(m[key]) for _, m in columns]
        table_lines.append(f"| {label} | " + " | ".join(cells) + " |")

    lines = [
        "\n## phishing_classifier (TF-IDF + intent/URL features + LogisticRegression) "
        "-- Principle 11 evidence-gate run\n",
        f"n_bonafide={n_bonafide} (self-generated, negative control -- see script docstring). "
        f"'overall' = bonafide vs. all generated phishing cases; 'train' / 'held_out' = bonafide vs. "
        f"just that split's phishing cases (bonafide is the shared negative class in every column, "
        f"so a bare per-column precision/recall on bonafide alone isn't mathematically meaningful).\n",
    ]
    lines.extend(table_lines)
    lines.append(
        "\n- Caveat: classifier trains only on real difraud/difraud text (Stage 5); this scores it "
        "against our own generated phishing_scam artifacts it has never seen -- a genuine "
        "generalization test, not a data-leakage-inflated number."
    )
    lines.append("")
    with open(RESULTS_MD, "a") as f:
        f.write("\n".join(lines))


def main() -> None:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"{MODEL_PATH} not found. Run defend/train/train_phishing_classifier.py first."
        )
    bundle = joblib.load(MODEL_PATH)
    vectorizer, model = bundle["vectorizer"], bundle["model"]

    # tools/storage_sync.py drops a `.storage_bundle.json` marker into every
    # directory it manages, so a bare *.json glob picks it up as a phantom entry
    # after a `storage_sync.py pull` -- on Colab, never locally. Same guard
    # synthetic_customers.load_roster() already carries.
    bonafide_paths = sorted(p for p in BONAFIDE_DIR.glob("*.json") if not p.name.startswith("."))
    if not bonafide_paths:
        raise FileNotFoundError(
            f"No bonafide messages under {BONAFIDE_DIR}. Run generate/generate_phishing_attacks.py "
            f"first (it generates these as a side effect)."
        )
    case_paths = sorted(ATTACKS_DIR.glob("*/*.json"))
    if not case_paths:
        raise FileNotFoundError(
            f"No generated phishing_scam cases under {ATTACKS_DIR}. Run "
            f"generate/generate_phishing_attacks.py first."
        )

    bonafide_cases = [json.loads(p.read_text()) for p in bonafide_paths]
    bonafide_texts = [_case_text(c) for c in bonafide_cases]
    print(f"Scoring {len(bonafide_texts)} bonafide messages...")
    bonafide_scores = _score_texts(vectorizer, model, bonafide_texts)

    cases = [json.loads(p.read_text()) for p in case_paths]
    fraud_texts = [_case_text(c) for c in cases]
    print(f"Scoring {len(fraud_texts)} generated phishing_scam cases...")
    fraud_scores = _score_texts(vectorizer, model, fraud_texts)

    y_true = np.concatenate([np.zeros(len(bonafide_scores)), np.ones(len(fraud_scores))])
    y_score = np.concatenate([bonafide_scores, fraud_scores])
    overall = compute_binary_metrics(y_true, y_score, threshold=bundle.get("threshold", 0.5))
    print(f"Overall metrics:\n{json.dumps(overall, indent=2)}")

    per_split = {}
    for split in ("train", "held_out"):
        idx = [i for i, c in enumerate(cases) if c["split_portion"] == split]
        if not idx:
            continue
        split_scores = fraud_scores[idx]
        combined_true = np.concatenate([np.zeros(len(bonafide_scores)), np.ones(len(split_scores))])
        combined_score = np.concatenate([bonafide_scores, split_scores])
        per_split[split] = compute_binary_metrics(combined_true, combined_score, threshold=bundle.get("threshold", 0.5))
        m = per_split[split]
        print(f"  {split} (n={len(idx)}): precision={m['precision']:.4f} recall={m['recall']:.4f} "
              f"f1={m['f1']:.4f} roc_auc={m['roc_auc']:.4f} pr_auc={m['pr_auc']:.4f} fpr={m['false_positive_rate']:.4f}")

    record_result(
        RESULTS_JSON, "phishing_classifier_evidence_gate", overall,
        extra={
            "n_bonafide": len(bonafide_scores),
            "n_fraud": len(fraud_scores),
            "per_split_metrics": per_split,
            "held_out_recall": per_split.get("held_out", {}).get("recall"),
            "train_recall": per_split.get("train", {}).get("recall"),
            "note": "TF-IDF + urgency/actionability/credential/reassurance/URL-shape features + "
                    "LogisticRegression, trained on real difraud/difraud data (Stage 5), scored here "
                    "against our own generated phishing_scam artifacts it never trained on -- "
                    "evidence-gate run per Principle 11.",
        },
    )
    _append_results_md(overall, per_split, len(bonafide_scores))
    print(f"Recorded results to {RESULTS_JSON} and {RESULTS_MD}")

    # Task #32: per-case results into Supabase for the evidence viewer.
    # Best-effort -- the real evidence-gate numbers above are already
    # recorded locally regardless of whether this succeeds, so a Supabase
    # hiccup here doesn't invalidate or block the actual evaluation.
    try:
        client = get_service_client()
        threshold = bundle.get("threshold", 0.5)
        bonafide_records = [
            {"case_id": bonafide_cases[i]["case_id"], "score": float(bonafide_scores[i]),
             "threshold": threshold, "is_fraud": False, "evidence": _evidence_for(bonafide_texts[i])}
            for i in range(len(bonafide_cases))
        ]
        for split in ("train", "held_out"):
            idx = [i for i, c in enumerate(cases) if c["split_portion"] == split]
            if not idx:
                continue
            split_records = [
                {"case_id": cases[i]["case_id"], "score": float(fraud_scores[i]),
                 "threshold": threshold, "is_fraud": True, "evidence": _evidence_for(fraud_texts[i])}
                for i in idx
            ]
            run_type = "adversarial_train_eval" if split == "train" else "adversarial_held_out"
            run_id = record_run_and_results(
                client, run_type=run_type, model_name="phishing_classifier",
                cases=bonafide_records + split_records,
            )
            print(f"  Supabase: evaluation_run {run_id} ({run_type}, "
                  f"{len(bonafide_records) + len(split_records)} per-case results)")
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


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nEVAL FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
