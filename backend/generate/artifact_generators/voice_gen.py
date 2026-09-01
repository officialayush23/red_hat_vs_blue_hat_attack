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

    @staticmethod
    def _as_float32(value):
        """Cast a waveform (or a list of them) to float32, leaving anything
        else untouched. numpy arrays and torch tensors both, because the two
        call sites below take different types."""
        import numpy as np
        import torch

        if isinstance(value, (list, tuple)):
            return type(value)(VoiceGenerator._as_float32(v) for v in value)
        if isinstance(value, np.ndarray):
            return value.astype(np.float32, copy=False)
        if torch.is_tensor(value) and value.dtype != torch.float32:
            return value.to(torch.float32)
        return value

    def _patch_reference_audio_dtype(self) -> None:
        """Force float32 into the two consumers of the REFERENCE waveform.

        2026-09-01, on a Colab T4: generation died with

            ValueError: input must have the type torch.float32, got type torch.float64

        raised by an LSTM inside Chatterbox's voice encoder, after the model
        and PerthNet had both loaded -- so never an install or a CUDA problem.

        The cause is one dtype, not two bugs. Chatterbox's own
        prepare_conditionals() loads the reference clip with librosa.load(),
        which returns float64 by default, and librosa.resample() preserves
        that. The float64 waveform then reaches two places, and each inherits
        it (verified against the installed source in
        backend/voice_gen_env/Lib/site-packages/chatterbox/):

          - VoiceEncoder.embeds_from_wavs() -> melspectrogram() builds a
            float64 mel -> embeds_from_mels() -> inference() -> self.lstm,
            whose weights are float32. torch refuses the mix. That is the
            traceback above.
          - S3Tokenizer.forward() -> _prepare_audio() produces a float64
            tensor -> log_mel_spectrogram(). Same class of failure; it is the
            one that surfaced first, and patching only it just moved the error
            downstream to the voice encoder.

        Casting each failing tensor as it appears is whack-a-mole against a
        single upstream cause, so this casts at the two boundaries the
        waveform crosses. The alternative -- reimplementing
        prepare_conditionals() with .astype("float32") in it -- would pin this
        file to one Chatterbox version's internals; these two are stable
        public methods.

        Distinct from _patch_watermarker_dtype below: that one is on the way
        OUT (generated waveform -> perth) and only appears on CPU. This one is
        on the way IN (reference clip -> conditioning) and appears on both
        devices."""
        ve = getattr(self._model, "ve", None)
        if ve is not None and not getattr(ve, "_fraudshield_f32_ref_patch", False):
            inner_embeds = ve.embeds_from_wavs

            def embeds_from_wavs(wavs, *args, **kwargs):
                return inner_embeds(VoiceGenerator._as_float32(wavs), *args, **kwargs)

            ve.embeds_from_wavs = embeds_from_wavs
            ve._fraudshield_f32_ref_patch = True

        s3gen = getattr(self._model, "s3gen", None)
        tokenizer = getattr(s3gen, "tokenizer", None) if s3gen is not None else None
        if tokenizer is not None and not getattr(tokenizer, "_fraudshield_f32_ref_patch", False):
            inner_forward = tokenizer.forward

            def forward(wavs, *args, **kwargs):
                return inner_forward(VoiceGenerator._as_float32(wavs), *args, **kwargs)

            tokenizer.forward = forward
            tokenizer._fraudshield_f32_ref_patch = True

    def _patch_watermarker_dtype(self) -> None:
        """Force float32 into Chatterbox's Perth watermarker.

        2026-09-01, on a CPU runtime: generation died with

            VOICE GENERATION FAILED: expected scalar type Double but found Float

        after the model and PerthNet had both loaded successfully, so it was
        never an install problem. Chatterbox hands the generated waveform to
        resemble-perth for provenance watermarking, and perth does
        torch.from_numpy(wav) without asserting a dtype. numpy float64 in
        produces a Double tensor, PerthNet's convolutions are Float, and torch
        refuses the mix. On CUDA the array happens to arrive as float32 and the
        bug never surfaces, which is why this only appeared once the run moved
        to CPU.

        The fix is a cast at the boundary, NOT disabling the watermarker.
        Stripping the AI-provenance mark off synthetic speech is not something
        to do for convenience -- and there is a second reason to keep it: if
        every attack clip carried a watermark and every bonafide clip did not,
        the spoof detector could learn 'has watermark' instead of 'is
        synthetic', and its recall would be measuring the wrong thing entirely.
        Keeping the watermarker on both paths keeps that confound out.

        *args/**kwargs deliberately: perth's signature differs across versions
        and this wrapper must not care."""
        import numpy as np

        wm = getattr(self._model, "watermarker", None)
        if wm is None or getattr(wm, "_fraudshield_f32_patch", False):
            return
        inner = wm.apply_watermark

        def apply_watermark(wav, *args, **kwargs):
            return inner(np.asarray(wav, dtype=np.float32), *args, **kwargs)

        wm.apply_watermark = apply_watermark
        wm._fraudshield_f32_patch = True

    def synthesize(self, text: str, speaker_wav_path: str | Path, out_path: str | Path) -> Path:
        """Clones the voice in speaker_wav_path reading `text`, writes a
        .wav to out_path. Used for BOTH generation modes above -- the only
        difference is which reference clip the caller passes in."""
        import torch
        import torchaudio as ta

        self._ensure_loaded()
        self._patch_reference_audio_dtype()
        self._patch_watermarker_dtype()
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wav = self._model.generate(text, audio_prompt_path=str(speaker_wav_path))

        # Same dtype discipline on the way out: torchaudio.save writes whatever
        # it is handed, and a float64 tensor here would produce a .wav that the
        # spoof detector's loader reads differently from every other clip in
        # the corpus -- a silent, per-file inconsistency in the evaluation set.
        if torch.is_tensor(wav) and wav.dtype != torch.float32:
            wav = wav.to(torch.float32)
        ta.save(str(out_path), wav, self._model.sr)
        return out_path
