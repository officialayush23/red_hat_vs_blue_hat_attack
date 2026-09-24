"""
Thin wrapper around a pretrained voice-spoof/deepfake detector -- Section 5's
"Voice spoof/deepfake detector... No -- pretrained inference" row, Principle 6
("using an existing one honestly is not a lesser claim").

Model choice and why (research spike, 2026-08-30): the SOTA paper-reproduction
candidate (XLS-R-SLS-Deepfake-Detection, ACM MM 2024) needs fairseq plus a
separate ~1.2GB XLS-R-300M self-supervised checkpoint and custom model.py --
real integration risk this close to the deadline for a ~1-2 EER-point
improvement we can't bank on holding on our own data anyway. Went instead
with `garystafford/wav2vec2-deepfake-voice-detector` (Apache 2.0): same
XLS-R-300M backbone lineage, loads via plain `transformers`
(AutoModelForAudioClassification + AutoFeatureExtractor, no custom code,
no fairseq), and its OWN training data is specifically real speech vs. six
TTS platforms (ElevenLabs, Amazon Polly, Hume AI, etc.) -- a good match for
our own TTS-generated attack audio. Its self-reported 97.9% accuracy /
0.998 ROC-AUC is exactly the kind of headline number Principle 11 says not
to trust blindly -- evaluation/eval_voice_spoof.py runs it against OUR OWN
generated set and records the real number, whatever it turns out to be.

NOT executable in the cloud sandbox this was authored in (no working
torch/transformers install there, same limitation noted in
train_autoencoder.py) -- written carefully against the model card's
documented API, but genuinely unverified until run on real hardware. Flag
any import/shape errors back immediately, don't assume this is bug-free.
"""

from pathlib import Path

import os

import numpy as np

# The spoof model is selectable, same pattern as the document detector's OCR
# backend. Swapping it changes the detector, so eval_voice_spoof.py records
# the model id in the metrics key -- a challenger can never overwrite the
# incumbent's numbers, and both can be measured on the identical 166 cases.
#
# Incumbent (unchanged default): garystafford/wav2vec2-deepfake-voice-detector,
# Apache 2.0, recall 0.8171 / precision 0.8701 / FPR 12.5% on n=166.
#
# Challengers worth measuring against it (all Hugging Face, all loadable
# through the same AutoModelForAudioClassification path):
#   mo-thecreator/Deepfake-audio-detection
#   Hemgg/Deepfake-audio-detection
# AASIST-family models (e.g. lab260/AASIST3) are the stronger published
# architecture for ASVspoof-style anti-spoofing, but they are NOT
# AutoModelForAudioClassification-compatible -- they need their own loader,
# so they are a separate piece of work rather than a VOICE_MODEL_ID swap.
DEFAULT_MODEL_ID = "garystafford/wav2vec2-deepfake-voice-detector"
MODEL_ID = os.environ.get("VOICE_MODEL_ID", "").strip() or DEFAULT_MODEL_ID
SAMPLE_RATE = 16_000


class VoiceSpoofDetector:
    """Lazy-loads the model on first use (not at import time) so importing
    this module doesn't require torch/transformers to be installed unless
    the detector is actually used."""

    def __init__(self, device: str | None = None):
        import torch  # local import -- see module docstring

        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model = None
        self._feature_extractor = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        self._feature_extractor = AutoFeatureExtractor.from_pretrained(MODEL_ID)
        self._model = AutoModelForAudioClassification.from_pretrained(MODEL_ID).to(self.device)
        self._model.eval()

        # Sanity-check the label mapping rather than assuming index 1 = "fake" --
        # the model card doesn't pin this down explicitly, and getting it
        # backwards would silently invert every score.
        id2label = {int(k): v for k, v in self._model.config.id2label.items()}
        spoof_idx = [i for i, lbl in id2label.items() if "fake" in lbl.lower() or "spoof" in lbl.lower()]
        if len(spoof_idx) != 1:
            raise RuntimeError(
                f"Could not unambiguously identify the 'spoof/fake' class from id2label={id2label}. "
                f"Fix _spoof_class_index below to hardcode the right index once you've inspected this."
            )
        self._spoof_class_index = spoof_idx[0]

    def score(self, audio_path: str | Path) -> float:
        """Returns P(spoof) in [0, 1] for one audio file. Loads at 16kHz mono
        (the model's expected input rate) regardless of the source file's
        native rate/channels."""
        import librosa

        self._ensure_loaded()
        max_s = os.environ.get("VOICE_MAX_SECONDS", "").strip()
        audio, _ = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True,
                                duration=float(max_s) if max_s else None)
        inputs = self._feature_extractor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with self._torch.no_grad():
            logits = self._model(**inputs).logits
            probs = self._torch.nn.functional.softmax(logits, dim=-1)
        return float(probs[0, self._spoof_class_index].cpu().item())

    def score_batch(self, audio_paths: list) -> np.ndarray:
        """Sequential scoring with an on-disk score cache.

        2026-09-24: the voice_spoof step sat "scoring..." for many minutes
        on Render every run -- ~170 clips of up to ~30s each through
        wav2vec2 on a shared CPU, re-scored from scratch each time although
        neither the clips nor the model had changed. Scores are now cached
        per (model id, file path, size, mtime, max-seconds), so a clip is
        only ever scored once per container; a regenerated clip changes
        size/mtime and is re-scored. The numbers are identical to a cold
        run -- this skips repeated work, it does not approximate it.

        VOICE_MAX_SECONDS (unset = whole clip, the recorded behavior) caps
        how much of each clip is scored, for CPU-only hosts that need a
        faster first run; metrics.json should be read with that in mind."""
        import json
        import os

        try:
            self._torch.set_num_threads(max(1, os.cpu_count() or 1))
        except Exception:
            pass
        cache_path = Path(__file__).resolve().parents[3] / "data" / ".eval_cache" / "voice_scores.json"
        try:
            cache = json.loads(cache_path.read_text())
        except Exception:
            cache = {}
        max_s = os.environ.get("VOICE_MAX_SECONDS", "").strip()
        out, hits = [], 0
        for i, p in enumerate(audio_paths):
            p = Path(p)
            try:
                st = p.stat()
                key = f"{MODEL_ID}|{p.as_posix()}|{st.st_size}|{int(st.st_mtime)}|{max_s}"
            except OSError:
                key = None
            if key and key in cache:
                out.append(cache[key])
                hits += 1
                continue
            v = self.score(p)
            out.append(v)
            if key:
                cache[key] = v
            if (i + 1) % 20 == 0:
                print(f"  voice_spoof: scored {i + 1}/{len(audio_paths)} ({hits} from cache)", flush=True)
                self._save_cache(cache_path, cache)
        self._save_cache(cache_path, cache)
        if hits:
            print(f"  voice_spoof: {hits}/{len(audio_paths)} clip scores reused from cache", flush=True)
        return np.array(out, dtype="float64")

    @staticmethod
    def _save_cache(path: Path, cache: dict) -> None:
        import json
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cache))
        except Exception:
            pass
