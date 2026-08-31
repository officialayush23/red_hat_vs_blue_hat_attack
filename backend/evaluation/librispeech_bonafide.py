"""
Small set of real, freely-licensed human speech clips -- used two ways:

1. As reference clips for "plain" (non-impersonation) voice_scam generation
   (voice_gen.py) -- a real voice Chatterbox clones from, distinct from any
   synthetic customer's own registered voice.
2. As the bonafide (real, not-spoofed) class for eval_voice_spoof.py's
   detector evaluation -- we have no real recorded human speech of our own
   anywhere in this project (correctly -- we don't record real people), so
   this is the one place a small external, permissively-licensed real-speech
   sample is the right call, the same way PaySim/IEEE-CIS are real external
   data for the transaction models.

Source: `hf-internal-testing/librispeech_asr_dummy` on Hugging Face -- a
small (~9MB) slice of LibriSpeech dev-clean, public domain (LibriSpeech
itself is built from public-domain LibriVox audiobook recordings), used
widely in HF's own model tutorials for exactly this kind of lightweight
real-speech sample. This is intentionally small -- tens of clips, a handful
of speakers -- so the resulting evaluation has real but LIMITED statistical
power; that caveat is written into eval_voice_spoof.py's recorded results
rather than hidden.

NOT executable in the cloud sandbox this was authored in (no `datasets`/
`soundfile`/network path verified there). Written against the standard,
well-documented `datasets.load_dataset` API.

Usage:
    from evaluation.librispeech_bonafide import fetch_bonafide_clips
    paths = fetch_bonafide_clips(out_dir="data/generated/voice_bonafide", n=40)
"""

import sys
from pathlib import Path

# Chatterbox hard-rejects any reference/prompt clip shorter than 5 seconds
# ("Audio prompt must be longer than 5 seconds!", raised deep inside its S3
# tokenizer). Measured against the actual downloaded clips: 19 of the first
# 40 rows of this dataset are under 5s (it's a "dummy" slice, not curated
# for length), so filtering is required, not optional. 6.0s keeps a buffer
# above Chatterbox's exact cutoff rather than sitting right on it.
MIN_DURATION_SEC = 6.0


def _duration_sec(path: Path) -> float:
    import soundfile as sf
    info = sf.info(str(path))
    return info.frames / float(info.samplerate)


def fetch_bonafide_clips(out_dir: str | Path, n: int = 40) -> list:
    """Downloads (via the `datasets` library, cached after first run) up to
    `n` real speech clips at least MIN_DURATION_SEC long and writes each as
    a .wav under out_dir. Returns the list of written paths. Idempotent --
    reuses valid clips already on disk instead of re-downloading.

    Decodes audio manually via soundfile from the raw bytes (Audio(decode=False))
    rather than relying on `datasets`' built-in auto-decode -- recent `datasets`
    releases (4.0+) moved that path to require `torchcodec` as a hard dependency,
    and torchcodec ships prebuilt wheels matched tightly to specific torch
    versions, which is exactly the kind of extra version-pinning risk this
    project is trying to avoid (see requirements.txt's TTS/pandas note). This
    sidesteps it entirely using a library we already depend on.

    Scans the FULL dataset split (not just the first n rows) and keeps only
    clips >= MIN_DURATION_SEC -- short clips are common early in this
    dataset's ordering, so capping the scan at n rows (the original
    approach) under-fills the bank. If the dataset genuinely doesn't have n
    qualifying clips, returns however many it found rather than raising --
    callers sample with replacement (random.choice), so a smaller-than-n
    bank still works, just with less variety; a warning is printed either
    way so this isn't silently short."""
    import io

    import soundfile as sf
    from datasets import Audio, load_dataset

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(out_dir.glob("librispeech_bonafide_*.wav"))
    valid_existing = [p for p in existing if _duration_sec(p) >= MIN_DURATION_SEC]
    if len(valid_existing) >= n:
        return valid_existing[:n]

    ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation")
    ds = ds.cast_column("audio", Audio(decode=False))  # raw bytes/path, no torchcodec needed

    paths = list(valid_existing)
    next_idx = len(existing)  # never overwrite/reuse indices already on disk (incl. too-short ones)
    for sample in ds:
        if len(paths) >= n:
            break
        raw = sample["audio"]
        if raw.get("bytes"):
            array, samplerate = sf.read(io.BytesIO(raw["bytes"]))
        elif raw.get("path"):
            array, samplerate = sf.read(raw["path"])
        else:
            continue
        duration = len(array) / float(samplerate)
        if duration < MIN_DURATION_SEC:
            continue
        out_path = out_dir / f"librispeech_bonafide_{next_idx:03d}.wav"
        next_idx += 1
        sf.write(str(out_path), array, samplerate)
        paths.append(out_path)

    if not paths:
        raise RuntimeError(
            "hf-internal-testing/librispeech_asr_dummy returned no samples >= "
            f"{MIN_DURATION_SEC}s -- check network access / dataset availability "
            "before continuing."
        )
    if len(paths) < n:
        print(
            f"WARNING: only {len(paths)} bonafide clips >= {MIN_DURATION_SEC}s available "
            f"in hf-internal-testing/librispeech_asr_dummy (asked for {n}) -- "
            "voice_scam generation will resample with replacement instead of failing.",
            file=sys.stderr,
        )
    return paths
