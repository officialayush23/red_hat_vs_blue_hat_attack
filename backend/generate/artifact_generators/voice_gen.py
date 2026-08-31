"""
Audio generation for the voice_scam family (Section 4a) via Chatterbox
(Resemble AI, MIT license, resemble-ai/chatterbox) -- does few-shot voice
cloning from a short reference clip, same as the XTTS-v2 approach this
replaced.

WHY CHATTERBOX INSTEAD OF XTTS-V2/coqui-tts: XTTS-v2 was the original
choice (see docs/TECHNICAL_SPEC.md's history) but hit an unresolved native
segmentation fault loading its checkpoint on this project's exact
environment (torch 2.13.0+cu130 on Windows) -- ruled out numba JIT via
NUMBA_DISABLE_JIT=1 (still crashed), never got a traceback to work from (a
segfault bypasses Python's exception handling entirely). Chatterbox's real
advantage here isn't quality, it's that its own pinned dependencies
(torch==2.6.0, torchaudio==2.6.0) predate torchaudio's torchcodec/FFmpeg
requirement (introduced at torchaudio 2.9), so it sidesteps that entire
dependency chain rather than fighting it.

WHY A SEPARATE VENV: Chatterbox pins torch==2.6.0 exactly, which would
conflict with the CUDA-specific torch==2.13.0+cu130 the rest of this
project (autoencoder, XGBoost/LightGBM, planned GNN) already depends on
and has verified working. Rather than risk that working setup, voice
generation runs in its own throwaway venv (backend/requirements-voice-gen.txt)
on CPU -- this is a one-time batch of 80 short clips, not a served path,
so CPU inference time is a non-issue. eval_voice_spoof.py (detection) does
NOT need this venv -- it only scores already-generated .wav files via
transformers/librosa, both already in the main venv.

Two generation modes, chosen by the caller via which reference clip is
passed in (mirrors the original XTTS-based design):
- plain: reference clip drawn from the LibriSpeech bonafide bank
  (evaluation/librispeech_bonafide.py) -- generic synthetic voice, no
  claimed identity.
- cloned_customer: clone a specific synthetic customer's registered
  reference voice (Section 4b-i, synthetic_customers.voice_ref) -- the
  actual "voice impersonation" attack. (Not yet wired to real Vault rows --
  see the TODO in generate_voice_attacks.py, unchanged by this swap.)

NOT executable in the cloud sandbox this was authored in -- depends on
chatterbox-tts/torch, not installable there. The API below matches
Chatterbox's documented README example directly.

Usage (only after `pip install chatterbox-tts` in the voice-gen venv):
    from generate.artifact_generators.voice_gen import VoiceGenerator
    gen = VoiceGenerator()
    gen.synthesize(text="...", speaker_wav_path="ref.wav", out_path="case_0001.wav")
"""

from pathlib import Path


class VoiceGenerator:
    """Lazy-loads Chatterbox Turbo on first use -- importing this module
    doesn't require chatterbox-tts/torch to be installed unless generation
    actually happens. Same public interface as the XTTS-based version it
    replaced (synthesize(text, speaker_wav_path, out_path)), so callers
    (generate_voice_attacks.py) needed zero changes."""

    def __init__(self, device: str | None = None):
        self._device = device
        self._model = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import torch
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model = ChatterboxTurboTTS.from_pretrained(device=device)

    def synthesize(self, text: str, speaker_wav_path: str | Path, out_path: str | Path) -> Path:
        """Clones the voice in speaker_wav_path reading `text`, writes a
        .wav to out_path. Used for BOTH generation modes above -- the only
        difference is which reference clip the caller passes in."""
        import torchaudio as ta

        self._ensure_loaded()
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wav = self._model.generate(text, audio_prompt_path=str(speaker_wav_path))
        ta.save(str(out_path), wav, self._model.sr)
        return out_path
