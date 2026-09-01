"""
Principle 11 evidence gate for the voice_spoof detector
(defend/pretrained/voice_spoof_detector.py): scores our own bonafide
(LibriSpeech, real human speech) and spoof (our generated voice_scam
attack audio, generate_voice_attacks.py) clips, records real precision/
recall/ROC-AUC/PR-AUC -- whatever they turn out to be -- to
backend/defend/models/metrics.json (same file/shape train_*.py write to)
and docs/EVALUATION_RESULTS.md. "Validated" per Principle 11 means this
ran and recorded a real number, not that the number is good.

Reports the held_out split separately from train -- held_out's
family_emergency/low-urgency/cloned_customer combination is the "novel
framing designed to read as legitimate" case (Section 4a); how much the
detector's recall drops on held_out vs. train is itself a finding worth
having, the same way it is for the tabular models.

Sample size caveat (written into the recorded results, not hidden): the
bonafide class comes from a small (~40-clip) LibriSpeech sample
(librispeech_bonafide.py) -- real evaluation, but limited statistical
power. Worth expanding before this becomes a load-bearing claim in the
Solution Walkthrough.

NOT executable in the cloud sandbox this was authored in -- depends on
voice_spoof_detector.py (torch/transformers) and real generated audio
from generate_voice_attacks.py. Structurally follows train_xgboost.py's
recording pattern.

Usage:
    python backend/evaluation/eval_voice_spoof.py
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402

from db.supabase_client import get_service_client  # noqa: E402
from defend.pretrained.voice_spoof_detector import VoiceSpoofDetector  # noqa: E402
from evaluation.metrics import best_f1_threshold, compute_binary_metrics, record_result  # noqa: E402
from evaluation.supabase_results import record_run_and_results  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
BONAFIDE_DIR = REPO_ROOT / "data" / "generated" / "voice_bonafide"
VOICE_ATTACKS_DIR = REPO_ROOT / "data" / "generated" / "voice_attacks"
MODELS_DIR = BACKEND_DIR / "defend" / "models"
RESULTS_JSON = MODELS_DIR / "metrics.json"
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
        "\n## voice_spoof_detector (garystafford/wav2vec2-deepfake-voice-detector) "
        "-- Principle 11 evidence-gate run\n",
        f"- Decision threshold: {threshold:.4f} (best_f1_threshold on bonafide + train-split spoof "
        f"only, then applied unchanged to held_out -- same calibrate-on-train/apply-to-held_out "
        f"pattern as run_adversarial_eval.py's frozen tabular thresholds, not re-picked on held_out)",
        f"- Precision: {overall['precision']:.4f}",
        f"- Recall: {overall['recall']:.4f}",
        f"- F1: {overall['f1']:.4f}",
        f"- ROC-AUC: {overall['roc_auc']:.4f}",
        f"- PR-AUC: {overall['pr_auc']:.4f}",
        f"- False positive rate (bonafide flagged as spoof): {overall['false_positive_rate']:.4%}",
        f"- n_bonafide={n_bonafide} (LibriSpeech sample -- small-N caveat, see script docstring), "
        f"n_spoof={overall['n_samples'] - n_bonafide}",
    ]
    for split, m in per_split.items():
        lines.append(f"- {split} split recall: {m['recall']:.4f} (n={m['n_positive']})")
    lines.append("")
    with open(RESULTS_MD, "a") as f:
        f.write("\n".join(lines))


def main() -> None:
    if not BONAFIDE_DIR.exists() or not any(BONAFIDE_DIR.glob("*.wav")):
        raise FileNotFoundError(
            f"No bonafide clips under {BONAFIDE_DIR}. Run generate/generate_voice_attacks.py first "
            f"(it fetches these as a side effect), or call librispeech_bonafide.fetch_bonafide_clips directly."
        )
    case_paths = sorted(VOICE_ATTACKS_DIR.glob("*/*.json"))
    if not case_paths:
        raise FileNotFoundError(
            f"No generated voice_scam cases under {VOICE_ATTACKS_DIR}. Run "
            f"generate/generate_voice_attacks.py first."
        )

    detector = VoiceSpoofDetector()

    bonafide_paths = sorted(BONAFIDE_DIR.glob("*.wav"))
    print(f"Scoring {len(bonafide_paths)} bonafide clips...")
    bonafide_scores = detector.score_batch(bonafide_paths)

    cases = [json.loads(p.read_text()) for p in case_paths]
    audio_paths = [REPO_ROOT / c["audio_path"] for c in cases]
    print(f"Scoring {len(audio_paths)} generated (spoof) clips...")
    spoof_scores = detector.score_batch(audio_paths)

    # Calibrate the decision threshold on bonafide + TRAIN-split spoof cases only
    # (best_f1_threshold -- the same helper run_adversarial_eval.py/eval_fusion.py
    # already use for every other detector in this project), then apply that ONE
    # fixed threshold everywhere below, including held_out -- held_out must never
    # contribute to picking its own threshold, or the held_out number stops being
    # a real generalization test. Previously this hardcoded 0.5, which is why the
    # first evidence-gate run showed a 50% FPR on bonafide clips: 0.5 was never a
    # calibrated cutoff for this detector's real score distribution, just an
    # unexamined default.
    train_idx = [i for i, c in enumerate(cases) if c["split_portion"] == "train"]
    train_spoof_scores = spoof_scores[train_idx]
    calib_true = np.concatenate([np.zeros(len(bonafide_scores)), np.ones(len(train_spoof_scores))])
    calib_score = np.concatenate([bonafide_scores, train_spoof_scores])
    threshold = best_f1_threshold(calib_true, calib_score)
    print(f"Calibrated decision threshold (best-F1 on bonafide + train-split spoof): {threshold:.4f}")

    y_true = np.concatenate([np.zeros(len(bonafide_scores)), np.ones(len(spoof_scores))])
    y_score = np.concatenate([bonafide_scores, spoof_scores])
    overall = compute_binary_metrics(y_true, y_score, threshold=threshold)
    print(f"Overall metrics:\n{json.dumps(overall, indent=2)}")

    per_split = {}
    for split in ("train", "held_out"):
        idx = [i for i, c in enumerate(cases) if c["split_portion"] == split]
        if not idx:
            continue
        split_scores = spoof_scores[idx]
        split_y_true = np.ones(len(split_scores))
        # recall-only view for a pure-positive-class slice -- roc/pr AUC need both classes,
        # so compute those against the shared bonafide pool instead.
        combined_true = np.concatenate([np.zeros(len(bonafide_scores)), split_y_true])
        combined_score = np.concatenate([bonafide_scores, split_scores])
        per_split[split] = compute_binary_metrics(combined_true, combined_score, threshold=threshold)
        print(f"  {split} (n={len(idx)}): recall={per_split[split]['recall']:.4f}")

    # Same rule as the document detector: the model is part of the model's
    # identity, so it is part of the metrics key. Only the default checkpoint
    # writes voice_spoof_detector; a challenger set via VOICE_MODEL_ID writes
    # its own entry, so a bake-off produces comparable numbers on identical
    # cases instead of one run overwriting another.
    from defend.pretrained.voice_spoof_detector import DEFAULT_MODEL_ID, MODEL_ID
    _slug = MODEL_ID.split("/")[-1].replace("-", "_").lower()
    metrics_key = ("voice_spoof_detector" if MODEL_ID == DEFAULT_MODEL_ID
                   else f"voice_spoof_detector_{_slug}")
    print(f"\nSpoof model: {MODEL_ID} -> recording as '{metrics_key}'")

    record_result(
        RESULTS_JSON, metrics_key, overall,
        extra={
            "model_id": MODEL_ID,
            "decision_threshold": threshold,
            "n_bonafide": len(bonafide_scores),
            "n_spoof": len(spoof_scores),
            "held_out_recall": per_split.get("held_out", {}).get("recall"),
            "train_recall": per_split.get("train", {}).get("recall"),
            "note": ("pretrained inference, no training -- evidence-gate run per Principle 11. "
                     "Threshold calibrated via best_f1_threshold on bonafide + train-split spoof "
                     "only (round 2), then applied unchanged to held_out -- round 1 used an "
                     f"uncalibrated 0.5 default. Scored by '{MODEL_ID}'."),
        },
    )
    _append_results_md(overall, per_split, len(bonafide_scores), threshold)
    print(f"Recorded results to {RESULTS_JSON} and {RESULTS_MD}")

    # Task #32: per-case results into Supabase for the evidence viewer.
    # Best-effort, non-fatal -- see eval_phishing_classifier.py for why.
    # No field-level decomposition available here (voice_spoof_detector's
    # score() is a single transformer probability, no internal comparison
    # to expose) -- evidence is honestly just the raw score.
    try:
        client = get_service_client()
        bonafide_records = [
            {"case_id": bonafide_paths[i].stem, "score": float(bonafide_scores[i]),
             "threshold": threshold, "is_fraud": False,
             "evidence": [f"wav2vec2_spoof_probability={bonafide_scores[i]:.4f}"]}
            for i in range(len(bonafide_paths))
        ]
        for split in ("train", "held_out"):
            idx = [i for i, c in enumerate(cases) if c["split_portion"] == split]
            if not idx:
                continue
            split_records = [
                {"case_id": cases[i]["case_id"], "score": float(spoof_scores[i]),
                 "threshold": threshold, "is_fraud": True,
                 "evidence": [f"wav2vec2_spoof_probability={spoof_scores[i]:.4f}"]}
                for i in idx
            ]
            run_type = "adversarial_train_eval" if split == "train" else "adversarial_held_out"
            run_id = record_run_and_results(
                client, run_type=run_type, model_name="voice_spoof_detector",
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
