"""
One-off diagnostic: reproduces exactly what prepare_conditionals() in
chatterbox/tts_turbo.py checks (librosa.load(path, sr=S3GEN_SR), then
len(wav)/sr > 5.0) against every path fetch_bonafide_clips() actually
returns, so we see precisely which files (if any) still fail Chatterbox's
own check -- rather than trusting a duration measured a different way.
Delete once the real cause is found; not part of the shipped pipeline.

Run from backend/, inside voice_gen_env:
    python diag_bonafide.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluation.librispeech_bonafide import fetch_bonafide_clips

BONAFIDE_DIR = Path(__file__).resolve().parents[1] / "data" / "generated" / "voice_bonafide"

paths = fetch_bonafide_clips(BONAFIDE_DIR, n=40)
print(f"fetch_bonafide_clips returned {len(paths)} paths\n")

import librosa
from chatterbox.models.s3gen import S3GEN_SR

bad = []
for p in paths:
    wav, sr = librosa.load(str(p), sr=S3GEN_SR)
    dur = len(wav) / sr
    ok = dur > 5.0
    if not ok:
        bad.append((p.name, dur))
    print(f"{'OK ' if ok else 'BAD'}  {p.name:35s} {dur:.3f}s")

print(f"\n{len(bad)} of {len(paths)} FAIL Chatterbox's >5.0s check")
for name, dur in bad:
    print(f"  {name}: {dur:.3f}s")
