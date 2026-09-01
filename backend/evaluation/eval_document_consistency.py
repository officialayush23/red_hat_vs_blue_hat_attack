"""
Principle 11 evidence gate for the document_consistency detector
(defend/pretrained/document_consistency_detector.py): scores our own
bonafide (fully consistent, document_gen.generate_bonafide_documents) and
fraud (tampered invoices, generate_document_attacks.py) documents, records
real precision/recall/ROC-AUC/PR-AUC -- whatever they turn out to be -- to
backend/defend/models/metrics.json and docs/EVALUATION_RESULTS.md.
Structurally identical to eval_voice_spoof.py; see that file for the
general pattern this follows.

Reports the held_out split separately from train -- held_out's
"amount + beneficiary + QR tampered together" combination is the
multi-field simultaneous case (Section 4a); train only ever tampers one
field at a time, so a recall gap between splits here is itself a real
finding, same as for voice_spoof and the tabular families.

Caveat recorded, not hidden: the field-extraction regexes in
document_consistency_detector.py are keyed to this project's own
document_gen.py label format -- this evaluates "can PaddleOCR + our own
consistency logic catch tampering on documents we render," not general
real-world invoice fraud detection.

NOT executable in the cloud sandbox this was authored in -- depends on
document_consistency_detector.py (paddleocr/paddlepaddle/opencv) and real
generated images from generate_document_attacks.py.

Usage:
    python backend/evaluation/eval_document_consistency.py
"""

import hashlib
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import time  # noqa: E402

import numpy as np  # noqa: E402

from db.supabase_client import get_service_client  # noqa: E402
from defend.pretrained.document_consistency_detector import DocumentConsistencyDetector  # noqa: E402
from evaluation.metrics import best_f1_threshold, compute_binary_metrics, record_result  # noqa: E402
from evaluation.supabase_results import record_run_and_results  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
BONAFIDE_DIR = REPO_ROOT / "data" / "generated" / "document_bonafide"
DOCUMENT_ATTACKS_DIR = REPO_ROOT / "data" / "generated" / "document_attacks"
MODELS_DIR = BACKEND_DIR / "defend" / "models"
RESULTS_JSON = MODELS_DIR / "metrics.json"
# Resumable score checkpoints -- see _score_with_progress. Kept out of
# data/generated/ so storage_sync bundles never carry them.
CACHE_DIR = BACKEND_DIR / ".eval_cache"
RESULTS_MD = BACKEND_DIR.parent / "docs" / "EVALUATION_RESULTS.md"


def _append_results_md(overall: dict, per_split: dict, n_bonafide: int, threshold: float) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS_MD.exists():
        RESULTS_MD.write_text(
            "# Evaluation Results\n\n"
            "Recorded automatically by each training/evaluation script -- do not hand-edit\n"
            "numbers here, re-run the script instead.\n"
        )
    lines = [
        "\n## document_consistency_detector (PaddleOCR-VL + QR cross-check) "
        "-- Principle 11 evidence-gate run\n",
        f"- Decision threshold: {threshold:.4f} (best_f1_threshold on bonafide + train-split fraud "
        f"only, then applied unchanged to held_out -- same calibrate-on-train/apply-to-held_out "
        f"pattern as run_adversarial_eval.py's frozen tabular thresholds, not re-picked on held_out)",
        f"- Precision: {overall['precision']:.4f}",
        f"- Recall: {overall['recall']:.4f}",
        f"- F1: {overall['f1']:.4f}",
        f"- ROC-AUC: {overall['roc_auc']:.4f}",
        f"- PR-AUC: {overall['pr_auc']:.4f}",
        f"- False positive rate (bonafide flagged as tampered): {overall['false_positive_rate']:.4%}",
        f"- n_bonafide={n_bonafide} (self-generated, see script docstring), "
        f"n_fraud={overall['n_samples'] - n_bonafide}",
    ]
    for split, m in per_split.items():
        lines.append(f"- {split} split recall: {m['recall']:.4f} (n={m['n_positive']})")
    lines.append("")
    with open(RESULTS_MD, "a") as f:
        f.write("\n".join(lines))


def _cache_path(backend: str) -> Path:
    """One checkpoint file per OCR backend -- scores from different engines
    are different measurements and must never be mixed."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"document_scores_{backend}.json"


def _load_cache(backend: str) -> dict:
    f = _cache_path(backend)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}   # a truncated checkpoint is worth nothing, not worth crashing over


def _score_with_progress(detector, paths: list, label: str) -> tuple:
    """Scores every image, printing per-image timing, and CHECKPOINTS AS IT GOES.

    The timing print exists because a single OCR forward pass can take long
    enough on CPU that a working run and a hung one look identical on screen.

    The checkpoint exists because of 2026-09-01: a Colab runtime hit its usage
    limit at image 290 of 680 and every one of those ~10 minutes of real
    scoring was lost, because results only existed in memory until the very
    end of the run. Scoring is deterministic and pure (Principle 13: the
    detector sees a file path and nothing else), so a score computed once is
    valid forever -- there is no reason to ever compute one twice.

    Keyed by (backend, image path). Re-running after any interruption resumes
    where it stopped; re-running a completed backend is nearly instant, which
    also makes the bake-off cheap to repeat.
    """
    backend = getattr(detector, "backend_name", "unknown")
    cache = _load_cache(backend)
    cache_file = _cache_path(backend)

    scores, evidences = [], []
    computed = 0
    for i, path in enumerate(paths, 1):
        key = str(path)
        hit = cache.get(key)
        if hit is not None:
            scores.append(hit["score"])
            evidences.append(hit["evidence"])
            continue

        t0 = time.monotonic()
        score, evidence = detector.score_with_evidence(path)
        dt = time.monotonic() - t0
        scores.append(score)
        evidences.append(evidence)
        cache[key] = {"score": float(score), "evidence": list(evidence)}
        computed += 1
        # Flush every image. A checkpoint that is only written every N images
        # loses up to N images to a kill -9, and Colab does not warn first.
        cache_file.write_text(json.dumps(cache))
        print(f"  [{label}] {i}/{len(paths)}  ({dt:.1f}s this image)", flush=True)

    reused = len(paths) - computed
    if reused:
        print(f"  [{label}] reused {reused} cached score(s) from {cache_file.name}; "
              f"computed {computed}", flush=True)
    return np.array(scores, dtype="float64"), evidences


def main() -> None:
    if not BONAFIDE_DIR.exists() or not any(BONAFIDE_DIR.glob("*.png")):
        raise FileNotFoundError(
            f"No bonafide documents under {BONAFIDE_DIR}. Run generate/generate_document_attacks.py "
            f"first (it generates these as a side effect)."
        )
    case_paths = sorted(DOCUMENT_ATTACKS_DIR.glob("*/*.json"))
    if not case_paths:
        raise FileNotFoundError(
            f"No generated document_fraud cases under {DOCUMENT_ATTACKS_DIR}. Run "
            f"generate/generate_document_attacks.py first."
        )

    detector = DocumentConsistencyDetector()

    bonafide_paths = sorted(BONAFIDE_DIR.glob("*.png"))
    print(f"Scoring {len(bonafide_paths)} bonafide documents...")
    bonafide_scores, bonafide_evidence = _score_with_progress(detector, bonafide_paths, "bonafide")

    cases = [json.loads(p.read_text()) for p in case_paths]
    # image_path values were written with the OS-native separator at
    # generation time (generate_document_attacks.py ran on Windows here,
    # so these are backslash-separated). PurePosixPath doesn't treat
    # backslash as a separator, so REPO_ROOT / c["image_path"] on Linux/
    # Colab silently appends the whole string as one bogus path component
    # instead of joining real subdirectories -- confirmed by a real run
    # (FileNotFoundError: '/content/data\\generated\\document_attacks\\...').
    # Normalizing here (not at generation time) fixes it on every platform
    # without touching or regenerating any already-written case JSON.
    image_paths = [REPO_ROOT / c["image_path"].replace("\\", "/") for c in cases]
    print(f"Scoring {len(image_paths)} generated (tampered) documents...")
    fraud_scores, fraud_evidence = _score_with_progress(detector, image_paths, "fraud")

    # Calibrate the decision threshold on bonafide + TRAIN-split fraud cases only
    # (best_f1_threshold -- same helper run_adversarial_eval.py/eval_fusion.py use
    # for every other detector), then apply that ONE fixed threshold everywhere
    # below including held_out. Previously hardcoded 0.5 -- an unexamined default,
    # same real gap as eval_voice_spoof.py's pre-fix version.
    train_idx = [i for i, c in enumerate(cases) if c["split_portion"] == "train"]
    train_fraud_scores = fraud_scores[train_idx]
    calib_true = np.concatenate([np.zeros(len(bonafide_scores)), np.ones(len(train_fraud_scores))])
    calib_score = np.concatenate([bonafide_scores, train_fraud_scores])
    threshold = best_f1_threshold(calib_true, calib_score)
    print(f"Calibrated decision threshold (best-F1 on bonafide + train-split fraud): {threshold:.4f}")

    y_true = np.concatenate([np.zeros(len(bonafide_scores)), np.ones(len(fraud_scores))])
    y_score = np.concatenate([bonafide_scores, fraud_scores])
    overall = compute_binary_metrics(y_true, y_score, threshold=threshold)
    print(f"Overall metrics:\n{json.dumps(overall, indent=2)}")

    per_split = {}
    for split in ("train", "held_out"):
        idx = [i for i, c in enumerate(cases) if c["split_portion"] == split]
        if not idx:
            continue
        split_scores = fraud_scores[idx]
        split_y_true = np.ones(len(split_scores))
        combined_true = np.concatenate([np.zeros(len(bonafide_scores)), split_y_true])
        combined_score = np.concatenate([bonafide_scores, split_scores])
        per_split[split] = compute_binary_metrics(combined_true, combined_score, threshold=threshold)
        print(f"  {split} (n={len(idx)}): recall={per_split[split]['recall']:.4f}")

    # The OCR engine is part of the model's identity, so it is part of the
    # metrics key. document_consistency_detector's recorded numbers (recall
    # 0.9125, n=120) were measured with PaddleOCR-VL; a run on rapidocr or
    # tesseract is a different detector and must not silently overwrite
    # them. The canonical key is kept for the paddlevl backend so existing
    # history and the frontend's PRIMARY_MODEL_IDS entry stay valid.
    backend = getattr(detector, "backend_name", "unknown")
    metrics_key = ("document_consistency_detector" if backend == "paddlevl"
                   else f"document_consistency_detector_{backend}")
    print(f"\nOCR backend: {backend} -> recording as '{metrics_key}'")

    record_result(
        RESULTS_JSON, metrics_key, overall,
        extra={
            "ocr_backend": backend,
            "decision_threshold": threshold,
            "n_bonafide": len(bonafide_scores),
            "n_fraud": len(fraud_scores),
            "held_out_recall": per_split.get("held_out", {}).get("recall"),
            "train_recall": per_split.get("train", {}).get("recall"),
            "note": ("pretrained OCR-VL + our own QR cross-check logic, no training -- "
                     "evidence-gate run per Principle 11. Threshold calibrated via "
                     "best_f1_threshold on bonafide + train-split fraud only (round 2), then "
                     "applied unchanged to held_out -- round 1 used an uncalibrated 0.5 default. "
                     f"OCR read by the '{backend}' backend (see "
                     "defend/pretrained/document_consistency_detector.py's backend notes)."),
        },
    )
    _append_results_md(overall, per_split, len(bonafide_scores), threshold)
    print(f"Recorded results to {RESULTS_JSON} and {RESULTS_MD}")

    # Task #32: per-case results into Supabase for the evidence viewer.
    # Best-effort, non-fatal -- see eval_phishing_classifier.py for why.
    try:
        client = get_service_client()
        # BONAFIDE ARE PARTITIONED, NOT REPEATED (2026-09-01).
        #
        # This block used to pass `bonafide_records + split_records` to BOTH
        # the train and the held_out run, so all 200 legitimate invoices were
        # written twice -- 400 evaluation_results rows against 200
        # attack_cases. Every aggregate over this table then counted the legit
        # population double, which deflates any FPR computed from the rows
        # rather than from metrics.json.
        #
        # Repeating them is not the only thing that would be wrong: dropping
        # them from one run would leave that run with no negatives at all, so
        # its precision would be undefined. So each bonafide case is assigned
        # to exactly ONE split, deterministically by a hash of its own id and
        # in proportion to how much fraud each split holds. Every run keeps
        # real negatives, no row is duplicated, and the assignment is
        # reproducible on any machine without storing a mapping.
        #
        # NOTE: per-run precision is therefore computed against a SUBSET of
        # the negatives. metrics.json remains the authoritative record -- it
        # is computed over the full bonafide set. These rows exist for the
        # evidence viewer, which needs one row per case, not two.
        split_of = {}
        counts = {sp: sum(1 for c in cases if c["split_portion"] == sp)
                  for sp in ("train", "held_out")}
        total_fraud = sum(counts.values()) or 1
        for i, bp in enumerate(bonafide_paths):
            bucket = int(hashlib.sha256(bp.stem.encode()).hexdigest()[:8], 16) % total_fraud
            split_of[i] = "train" if bucket < counts["train"] else "held_out"

        for split in ("train", "held_out"):
            idx = [i for i, c in enumerate(cases) if c["split_portion"] == split]
            if not idx:
                continue
            bonafide_records = [
                {"case_id": bonafide_paths[i].stem, "score": float(bonafide_scores[i]),
                 "threshold": threshold, "is_fraud": False, "evidence": bonafide_evidence[i]}
                for i in range(len(bonafide_paths)) if split_of[i] == split
            ]
            split_records = [
                {"case_id": cases[i]["case_id"], "score": float(fraud_scores[i]),
                 "threshold": threshold, "is_fraud": True, "evidence": fraud_evidence[i]}
                for i in idx
            ]
            run_type = "adversarial_train_eval" if split == "train" else "adversarial_held_out"
            run_id = record_run_and_results(
                client, run_type=run_type, model_name="document_consistency_detector",
                cases=bonafide_records + split_records,
            )
            print(f"  Supabase: evaluation_run {run_id} ({run_type}, "
                  f"{len(split_records)} fraud + {len(bonafide_records)} bonafide = "
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
