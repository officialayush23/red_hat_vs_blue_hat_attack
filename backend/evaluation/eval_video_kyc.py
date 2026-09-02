"""
Principle 11 evidence gate for the video-KYC identity-consistency detector
(defend/pretrained/video_kyc_detector.py). Structurally different from
eval_voice_spoof.py / eval_document_consistency.py in one way: those two
score a separate bonafide pool against a separate attack pool built by two
different generation scripts. Here, bonafide AND fraud cases both live
together as case JSONs under data/generated/video_kyc_attacks/<split>/
(generate_video_kyc_attacks.py writes both kinds, is_fraud tells them
apart) -- because a video-KYC "case" is inherently a (video, claimed
identity) pair either way, not a raw clip plus a separately-tracked ground
truth pool.

Designed to run against a PARTIAL, still-growing case set without
crashing: generate_video_kyc_attacks.py is explicitly incremental (see its
own docstring) -- the user is generating reference photos/videos in
batches, so at any given moment train or held_out may have only a few
cases, or may not yet contain both classes. This script calibrates its
decision threshold on train only if train actually has both a bonafide and
a fraud case (best_f1_threshold needs both classes to mean anything); if
not, it falls back to an uncalibrated 0.5 and prints a clear warning
instead of raising -- the honest thing to record when there isn't yet
enough data to calibrate, not a crash. Per-split metrics are computed for
whichever splits have at least one case; a split with only one class still
gets precision/recall/F1 (compute_binary_metrics already returns
roc_auc/pr_auc as None for that case, see evaluation/metrics.py) instead
of being skipped outright, so partial evidence is still real evidence.

Re-run this after every generate_video_kyc_attacks.py run that reports new
cases -- numbers will visibly firm up as train/held_out fill in, and that
progression is worth keeping in docs/EVALUATION_RESULTS.md rather than
only recording a final number.

NOT executable in the cloud sandbox this was authored in -- depends on
facenet-pytorch/torch and real generated media that (as of this writing)
only partially exists.

Usage:
    python backend/evaluation/eval_video_kyc.py
"""

import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402

from db.supabase_client import get_service_client  # noqa: E402
from defend.pretrained.video_kyc_detector import VideoKycDetector  # noqa: E402
from evaluation.metrics import best_f1_threshold, compute_binary_metrics, record_result  # noqa: E402
from evaluation.supabase_results import record_run_and_results  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
CASE_DIR = REPO_ROOT / "data" / "generated" / "video_kyc_attacks"
MODELS_DIR = BACKEND_DIR / "defend" / "models"
RESULTS_JSON = MODELS_DIR / "metrics.json"
RESULTS_MD = BACKEND_DIR.parent / "docs" / "EVALUATION_RESULTS.md"


def _score_with_progress(detector: VideoKycDetector, cases: list) -> tuple:
    """Mirrors eval_document_consistency.py's per-case timing print --
    video frame sampling + face embedding is slow enough on CPU that a
    working-but-slow run and a hung one look identical without this."""
    scores = []
    evidences = []
    for i, case in enumerate(cases, 1):
        # A path stored in a JSON file written on Windows is backslash-separated;
        # PurePosixPath does not split on it, so this join silently produces one
        # bogus component on Linux/Colab. Same fix as eval_document_consistency.py.
        video_path = REPO_ROOT / case["video_path"].replace("\\", "/")
        reference_photo_path = REPO_ROOT / case["reference_photo_path"].replace("\\", "/")
        t0 = time.monotonic()
        score, evidence = detector.score_with_evidence(video_path, reference_photo_path)
        dt = time.monotonic() - t0
        scores.append(score)
        evidences.append(evidence)
        label = "fraud" if case["is_fraud"] else "bonafide"
        print(f"  [{case['split_portion']}/{label}] {i}/{len(cases)}  {case['customer_id']}  ({dt:.1f}s)", flush=True)
    return np.array(scores, dtype="float64"), evidences


def _append_results_md(overall: dict, per_split: dict, threshold: float, calibrated: bool, n_cases: int) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS_MD.exists():
        RESULTS_MD.write_text(
            "# Evaluation Results\n\n"
            "Recorded automatically by each training/evaluation script -- do not hand-edit\n"
            "numbers here, re-run the script instead.\n"
        )
    calib_note = ("best_f1_threshold on train-split cases only, then applied unchanged to held_out"
                  if calibrated else
                  "UNCALIBRATED FALLBACK (0.5) -- train split did not yet contain both a bonafide "
                  "and a fraud case at the time of this run; re-run once it does")
    lines = [
        "\n## video_kyc_detector (facenet-pytorch MTCNN + InceptionResnetV1/VGGFace2) "
        "-- Principle 11 evidence-gate run\n",
        f"- Decision threshold: {threshold:.4f} ({calib_note})",
        f"- n_cases={n_cases} (dataset still growing -- see script docstring)",
        f"- Precision: {overall['precision']:.4f}",
        f"- Recall: {overall['recall']:.4f}",
        f"- F1: {overall['f1']:.4f}",
        f"- ROC-AUC: {overall['roc_auc']:.4f}" if overall['roc_auc'] is not None else "- ROC-AUC: n/a (single class present)",
        f"- PR-AUC: {overall['pr_auc']:.4f}" if overall['pr_auc'] is not None else "- PR-AUC: n/a (single class present)",
        f"- False positive rate (bonafide flagged as impersonation): {overall['false_positive_rate']:.4%}",
    ]
    for split, m in per_split.items():
        lines.append(f"- {split} split (n={m['n_samples']}, n_positive={m['n_positive']}): "
                     f"recall={m['recall']:.4f}, precision={m['precision']:.4f}")
    lines.append("")
    with open(RESULTS_MD, "a") as f:
        f.write("\n".join(lines))


def main() -> None:
    case_paths = sorted(CASE_DIR.glob("*/*.json"))
    if not case_paths:
        raise FileNotFoundError(
            f"No video-KYC cases under {CASE_DIR}. Run generate/generate_video_kyc_attacks.py "
            f"first -- it needs at least 2 identities with both a reference photo and a bonafide "
            f"video on disk before it can author any case."
        )
    cases = [json.loads(p.read_text()) for p in case_paths]
    print(f"Loaded {len(cases)} video-KYC cases "
          f"({sum(1 for c in cases if not c['is_fraud'])} bonafide, "
          f"{sum(1 for c in cases if c['is_fraud'])} fraud)")

    detector = VideoKycDetector()
    scores, evidence = _score_with_progress(detector, cases)
    y_true = np.array([1.0 if c["is_fraud"] else 0.0 for c in cases])

    # Calibrate on train only if train actually has both classes -- with a dataset
    # this small and still growing, that's a real possibility, not a hypothetical.
    train_idx = [i for i, c in enumerate(cases) if c["split_portion"] == "train"]
    train_true, train_scores = y_true[train_idx], scores[train_idx]
    calibrated = len(train_idx) > 0 and len(set(train_true.tolist())) > 1
    if calibrated:
        threshold = best_f1_threshold(train_true, train_scores)
        print(f"Calibrated decision threshold (best-F1 on train-split cases, n={len(train_idx)}): {threshold:.4f}")
    else:
        threshold = 0.5
        print(f"WARNING: train split has {len(train_idx)} case(s) and does not yet contain both a "
              f"bonafide and a fraud case -- using an UNCALIBRATED 0.5 threshold. Re-run once train "
              f"has both classes; this run's numbers are real but the threshold is a placeholder.")

    overall = compute_binary_metrics(y_true, scores, threshold=threshold)
    print(f"Overall metrics:\n{json.dumps(overall, indent=2)}")

    per_split = {}
    for split in ("train", "held_out"):
        idx = [i for i, c in enumerate(cases) if c["split_portion"] == split]
        if not idx:
            continue
        per_split[split] = compute_binary_metrics(y_true[idx], scores[idx], threshold=threshold)
        print(f"  {split} (n={len(idx)}): recall={per_split[split]['recall']:.4f}, "
              f"precision={per_split[split]['precision']:.4f}")

    record_result(
        RESULTS_JSON, "video_kyc_detector", overall,
        extra={
            "decision_threshold": threshold,
            "threshold_calibrated": calibrated,
            "n_cases": len(cases),
            "n_bonafide": int((~y_true.astype(bool)).sum()),
            "n_fraud": int(y_true.astype(bool).sum()),
            "held_out_recall": per_split.get("held_out", {}).get("recall"),
            "train_recall": per_split.get("train", {}).get("recall"),
            "note": ("pretrained face-embedding inference (facenet-pytorch, MTCNN+InceptionResnetV1/"
                     "VGGFace2), no training -- evidence-gate run per Principle 11. Dataset is "
                     "incrementally generated (see generate_video_kyc_attacks.py); this run's n_cases "
                     "reflects the media available at run time, not a final fixed set. "
                     + ("Threshold calibrated via best_f1_threshold on train-split cases only." if calibrated
                        else "Threshold is an UNCALIBRATED 0.5 fallback -- train split lacked both "
                             "classes at run time, see threshold_calibrated=false.")),
        },
    )
    _append_results_md(overall, per_split, threshold, calibrated, len(cases))
    print(f"Recorded results to {RESULTS_JSON} and {RESULTS_MD}")

    # Task #32: per-case results into Supabase for the evidence viewer.
    # Best-effort, non-fatal -- see eval_phishing_classifier.py for why.
    try:
        client = get_service_client()
        records = [
            {"case_id": cases[i]["case_id"], "score": float(scores[i]), "threshold": threshold,
             "is_fraud": bool(cases[i]["is_fraud"]), "evidence": evidence[i]}
            for i in range(len(cases))
        ]
        for split in ("train", "held_out"):
            idx = [i for i, c in enumerate(cases) if c["split_portion"] == split]
            if not idx:
                continue
            run_type = "adversarial_train_eval" if split == "train" else "adversarial_held_out"
            run_id = record_run_and_results(
                client, run_type=run_type, model_name="video_kyc_detector",
                cases=[records[i] for i in idx],
            )
            print(f"  Supabase: evaluation_run {run_id} ({run_type}, {len(idx)} per-case results)")
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
