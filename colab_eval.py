"""Colab-only evidence-gate run for document_consistency_detector -- mirrors
backend/evaluation/eval_document_consistency.py's exact logic (same detector
code, same metric computation, same per-split breakdown; the detector and
metrics files packaged alongside this script are the real, unmodified repo
files, not reimplemented) -- adapted only for Colab's flat upload layout
instead of the real repo's absolute paths, and matching image to case JSON
by same-directory/same-basename instead of re-parsing the JSON's embedded
Windows-style repo-relative path (data\\generated\\document_attacks\\...),
which won't resolve on Colab's Linux filesystem anyway.

Written 2026-08-30 after four consecutive distinct low-level GPU errors on
Windows + RTX 3050 + paddlepaddle-gpu (WinError 127 DLL collision -> cudnn
version mismatch -> opencv-python/opencv-contrib-python collision ->
CUDNN_STATUS_INTERNAL_ERROR_HOST_ALLOCATION_FAILED -> CUDNN_STATUS_EXECUTION_FAILED),
each fixed in turn but a new one appearing every time -- real evidence
(pagefile: 10.8GB allocated, ~2.3GB peak used; RAM: 7.3GB free) ruled out
the two most likely systemic causes, so the remaining explanation is the
Windows paddlepaddle-gpu wheel itself being unstable on this GPU/driver
combination. Colab is Linux with a real free-tier GPU and none of the
Windows DLL-search-order machinery that caused most of this.

Usage in a fresh Colab notebook (T4 runtime):
    !tar xzf colab_document_fraud_package.tar.gz
    !nvidia-smi   # confirm the driver's CUDA version before picking an index
    !pip install -q "paddleocr[doc-parser]" scikit-learn
    !pip install -q paddlepaddle-gpu -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
    !pip install -q "nvidia-cudnn-cu12==9.9.0.52" --force-reinstall --no-deps
    !python colab_eval.py
Then download colab_results.json (left panel -> Files -> right-click ->
Download) and paste its content back for recording into the real repo's
metrics.json / docs/EVALUATION_RESULTS.md.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from document_consistency_detector import DocumentConsistencyDetector  # noqa: E402
from metrics import compute_binary_metrics  # noqa: E402

BONAFIDE_DIR = Path("document_bonafide")
ATTACKS_DIR = Path("document_attacks")


def score_with_progress(detector, paths, label):
    scores = []
    for i, path in enumerate(paths, 1):
        t0 = time.monotonic()
        scores.append(detector.score(path))
        print(f"  [{label}] {i}/{len(paths)}  ({time.monotonic() - t0:.1f}s this image)", flush=True)
    return np.array(scores, dtype="float64")


def main():
    if not BONAFIDE_DIR.exists():
        raise FileNotFoundError(f"{BONAFIDE_DIR} not found -- did you tar xzf the package first?")

    detector = DocumentConsistencyDetector()

    bonafide_paths = sorted(BONAFIDE_DIR.glob("*.png"))
    print(f"Scoring {len(bonafide_paths)} bonafide documents...")
    bonafide_scores = score_with_progress(detector, bonafide_paths, "bonafide")

    case_paths = sorted(ATTACKS_DIR.glob("*/*.json"))
    cases = [json.loads(p.read_text()) for p in case_paths]
    # Image sits beside its case JSON, same basename -- simpler and more
    # robust on Colab's Linux fs than resolving the JSON's embedded
    # Windows-style repo-relative image_path.
    image_paths = [p.with_suffix(".png") for p in case_paths]
    print(f"Scoring {len(image_paths)} generated (tampered) documents...")
    fraud_scores = score_with_progress(detector, image_paths, "fraud")

    y_true = np.concatenate([np.zeros(len(bonafide_scores)), np.ones(len(fraud_scores))])
    y_score = np.concatenate([bonafide_scores, fraud_scores])
    overall = compute_binary_metrics(y_true, y_score, threshold=0.5)
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
        per_split[split] = compute_binary_metrics(combined_true, combined_score, threshold=0.5)
        print(f"  {split} (n={len(idx)}): recall={per_split[split]['recall']:.4f}")

    result = {
        "overall": overall,
        "per_split": per_split,
        "n_bonafide": len(bonafide_scores),
        "n_fraud": len(fraud_scores),
    }
    Path("colab_results.json").write_text(json.dumps(result, indent=2))
    print("\nWrote colab_results.json -- download this and paste its content back.")


if __name__ == "__main__":
    main()
