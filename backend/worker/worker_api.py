"""
Worker service: runs ONE script that needs its own Python environment, on
its own Render service, for the main API (api/main.py) to call over HTTP.

Why this exists (2026-09-24)
----------------------------
Three steps cannot share the main image's Python environment:
  - voice_attacks generation: Chatterbox TTS pins conflict with the main
    torch/transformers stack (requirements-voice-gen.txt).
  - video_kyc (generation + evaluation): facenet-pytorch hard-pins
    torch<2.3, while transformers>=5 in the main image needs torch>=2.5.
Locally these run in separate venvs (voice_gen_env, ...). In production each
gets its own image (Dockerfile.voice, Dockerfile.videokyc) running this
small API, and run_all_generation.py / run_all_evaluations.py call it via
tools/remote_worker.py when the step's WORKER_URL env var is set.

Contract
--------
POST /jobs   {"script": "generate/generate_voice_attacks.py", "args": [...],
              "hydrate": ["voice_bonafide"], "push": ["voice_attacks"],
              "metrics_keys": ["video_kyc_detector"], "env": {...}}
  -> {"job_id": ...}.  The worker: pulls `hydrate` bundles from Supabase
  Storage, runs the script with its own interpreter, and on success pushes
  `push` bundles back to Storage (so the main service can pull the new
  cases), then returns the requested metrics.json entries so the main
  service's scoreboard is updated too. Evaluation scripts persist their
  per-case rows to Supabase themselves, exactly as they do on the main API.
GET /jobs/{id} -> status, returncode, log tail, metrics entries.
GET /health.

Security: every /jobs call must carry X-Worker-Token == $WORKER_TOKEN, and
only scripts listed in $WORKER_SCRIPTS (comma-separated) can be run. A
worker with no WORKER_TOKEN set refuses all jobs.
"""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
METRICS_JSON = BACKEND_DIR / "defend" / "models" / "metrics.json"
JOBS_DIR = Path(os.environ.get("WORKER_JOBS_DIR", "/tmp/fraudshield_worker_jobs"))
ALLOWED = {s.strip() for s in os.environ.get("WORKER_SCRIPTS", "").split(",") if s.strip()}
TOKEN = os.environ.get("WORKER_TOKEN", "")
ENV_ALLOW = {"FRAUDSHIELD_CAMPAIGN_ID", "VOICE_MAX_SECONDS", "DOC_OCR_BACKEND"}

app = FastAPI(title="FraudShield worker")
_jobs: dict = {}
_lock = threading.Lock()   # one job at a time -- these are heavy (TTS, face models)


class JobRequest(BaseModel):
    script: str
    args: list[str] = []
    hydrate: list[str] = []
    push: list[str] = []
    metrics_keys: list[str] = []
    env: dict[str, str] = {}
    timeout: int = 3600


def _save(state: dict) -> None:
    try:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        (JOBS_DIR / f"{state['job_id']}.json").write_text(json.dumps(state, default=str))
    except Exception:
        pass


def _run_job(state: dict, req: JobRequest) -> None:
    def log(msg):
        state["log"].append(msg)
        state["log"] = state["log"][-200:]
        _save(state)

    with _lock:
        state["status"] = "running"
        _save(state)
        try:
            if req.hydrate:
                from tools.storage_sync import ensure_bundles
                log(ensure_bundles(req.hydrate)["summary"])
            env = {**os.environ, **{k: v for k, v in req.env.items() if k in ENV_ALLOW}}
            proc = subprocess.run([sys.executable, str(BACKEND_DIR / req.script), *req.args],
                                  cwd=str(BACKEND_DIR), capture_output=True, text=True,
                                  timeout=req.timeout, env=env)
            for line in ((proc.stdout or "") + (proc.stderr or "")).splitlines()[-60:]:
                state["log"].append(line)
            state["returncode"] = proc.returncode
            if proc.returncode == 0 and req.push:
                from tools.storage_sync import push
                rc = push(",".join(req.push))
                log(f"pushed {req.push} to Storage (rc={rc})")
                if rc != 0:
                    state["returncode"] = rc
            if req.metrics_keys and METRICS_JSON.exists():
                m = json.loads(METRICS_JSON.read_text())
                state["metrics"] = {k: m[k] for k in req.metrics_keys if k in m}
            state["status"] = "completed" if state["returncode"] in (0, 2) else "failed"
        except subprocess.TimeoutExpired:
            state["status"], state["returncode"] = "failed", None
            log(f"TIMED OUT after {req.timeout}s")
        except Exception as exc:
            state["status"] = "failed"
            log(f"worker error: {exc!r}")
        state["finished_at"] = time.time()
        _save(state)


@app.get("/health")
async def health():
    return {"status": "ok", "scripts": sorted(ALLOWED), "busy": _lock.locked()}


@app.post("/jobs", status_code=202)
async def create_job(req: JobRequest, x_worker_token: Optional[str] = Header(default=None)):
    if not TOKEN or x_worker_token != TOKEN:
        raise HTTPException(status_code=401, detail="bad or missing X-Worker-Token")
    if req.script not in ALLOWED:
        raise HTTPException(status_code=403, detail=f"{req.script} is not allowed on this worker ({sorted(ALLOWED)})")
    job_id = uuid.uuid4().hex[:12]
    state = {"job_id": job_id, "script": req.script, "status": "queued", "log": [],
             "returncode": None, "metrics": {}, "started_at": time.time(), "finished_at": None}
    _jobs[job_id] = state
    _save(state)
    threading.Thread(target=_run_job, args=(state, req), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
async def job_status(job_id: str, x_worker_token: Optional[str] = Header(default=None)):
    if not TOKEN or x_worker_token != TOKEN:
        raise HTTPException(status_code=401, detail="bad or missing X-Worker-Token")
    state = _jobs.get(job_id)
    if state is None:
        try:
            state = json.loads((JOBS_DIR / f"{job_id}.json").read_text())
            if state.get("status") in ("queued", "running"):
                state["status"] = "lost"
        except Exception:
            return {"job_id": job_id, "status": "lost", "log": ["worker restarted; job unknown"]}
    return state
