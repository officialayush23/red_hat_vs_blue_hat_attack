# FraudShield backend -- FastAPI layer (api/main.py) for Railway.
#
# Scope of this image, deliberately: xgboost/lightgbm/autoencoder eval, GNN
# eval (torch_geometric), phishing classifier, voice-spoof DETECTION
# (transformers/wav2vec2), fusion, behavioral adjustment -- everything that
# runs in the main "red" venv locally EXCEPT video-KYC. Three families are
# out of this first deploy, each for a real, verified reason rather than
# being silently dropped:
#   - document_consistency: needs the separate paddleocr_env venv locally
#     (paddlepaddle's pinned deps conflict with this venv's -- see
#     run_all_evaluations.py's VENV_OVERRIDES comment).
#   - voice_scam GENERATION (not detection): needs the separate
#     voice_gen_env venv locally (Chatterbox's pins conflict with this
#     venv's torch -- see run_all_generation.py's VENV_OVERRIDES comment).
#   - video_kyc: facenet-pytorch (its MTCNN/InceptionResnetV1 face
#     matcher) hard-pins torch<2.3, but transformers>=5 (needed for the
#     voice-spoof wav2vec2 detector already in THIS image) requires
#     torch>=2.5 -- confirmed by actually installing both together and
#     watching pip downgrade torch to 2.2.2, which then makes transformers
#     report "PyTorch was not found" (verified in a throwaway venv before
#     writing this Dockerfile, not assumed). These two can't share one
#     Python environment; video-KYC needs its own, like the two above.
#
# run_all_evaluations.py / run_all_generation.py already handle a missing
# venv gracefully (VENV_OVERRIDES falls back to sys.executable with a
# printed warning, then that ONE step fails with a clear "No module named"
# instead of crashing the batch) -- so all three will honestly report
# themselves unavailable here rather than silently pretending to work.
# Giving each its own isolated venv in this image (matching the local
# paddleocr_env/voice_gen_env pattern, plus a new video_kyc_env) is real
# follow-up work, not a blocker for going live.
FROM python:3.11-slim

WORKDIR /app

# libsndfile1: soundfile (voice-spoof audio I/O). ffmpeg: librosa decoding
# non-WAV audio.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# torch (CPU build -- see docs/TRAINING_SETUP.md; the repo's own GPU install
# instructions don't apply on a CPU-only Railway container) + torch_geometric
# (pure Python per eval_gnn.py's own docstring, no CUDA compilation needed).
# Deliberately NOT facenet-pytorch/opencv here -- see the video-KYC note
# above; installing torch alone (no facenet-pytorch pulling it down to
# <2.3) lets pip resolve the latest torch, which is what transformers needs.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir torch_geometric

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
