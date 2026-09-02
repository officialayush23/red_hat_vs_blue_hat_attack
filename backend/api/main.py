"""
Minimal FastAPI layer -- "run evaluations and generation from the
frontend, async" (2026-08-31, extended 2026-08-31 with /generate/*).
Deliberately narrow scope: this is NOT the full detector-scoring/customer
API surface referenced elsewhere in this codebase's comments (e.g.
document_consistency_detector.py's beneficiary-vs-profile check,
explicitly deferred to "the API layer" -- that endpoint still doesn't
exist). This file does two things: let a frontend trigger
evaluation/run_all_evaluations.py and generate/run_all_generation.py and
poll their progress/result, instead of someone running them by hand on a
terminal every time. Everything else the frontend needs (attack cases,
evaluation_runs/evaluation_results, model_registry, weakness_log) is
read-only and goes straight from the browser to Supabase via the anon key
-- see db/README.md's RLS note (002_rls_policies.sql: public read on
every table, service-role-only write). This API is only for the two
things a browser genuinely cannot do itself: launch and poll a
long-running local Python subprocess.

Async by construction: both POST endpoints launch their master script as
a genuine subprocess via asyncio.create_subprocess_exec (NOT
subprocess.run, which would block FastAPI's entire event loop for however
long PaddleOCR-VL / facenet-pytorch / Chatterbox / the GNN eval take --
could be minutes). Each returns a run_id immediately (202 Accepted); the
frontend polls the matching GET status endpoint for progress and, once
status is "completed"/"completed_with_failures", the response's `summary`
field is exactly the master script's own JSON summary.

Run state lives in two in-memory dicts -- fine for a single-process
dev/demo deployment (same "no infra beyond what's needed to be honest"
posture as the rest of this project). A restart loses in-flight run
history, not any real result -- evaluation results are already durably on
disk in defend/models/metrics.json (and in Supabase, per-case, via
evaluation/supabase_results.py) regardless of whether this process is up;
generation results are already durable as case JSON/parquet on disk and,
after the backfill_attack_cases step, in Supabase's attack_cases table.
GET /evaluations/latest reads metrics.json directly and doesn't touch the
run registry at all.

Run with (from backend/, same venv everything else here runs in):
    pip install fastapi "uvicorn[standard]"
    uvicorn api.main:app --reload --port 8000

Then, e.g.:
    curl -X POST http://localhost:8000/evaluations/run
    curl http://localhost:8000/evaluations/status/<run_id>
    curl http://localhost:8000/evaluations/latest
    curl -X POST http://localhost:8000/generate/run -H "Content-Type: application/json" -d "{\"only\": \"tabular_attacks,backfill_attack_cases\"}"
    curl http://localhost:8000/generate/status/<run_id>
"""

import asyncio
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[1]
EVAL_SCRIPT = BACKEND_DIR / "evaluation" / "run_all_evaluations.py"
GEN_SCRIPT = BACKEND_DIR / "generate" / "run_all_generation.py"
ORCH_SCRIPT = BACKEND_DIR / "orchestration" / "agent_runner.py"
STORAGE_SYNC_SCRIPT = BACKEND_DIR / "tools" / "storage_sync.py"
GENERATED_DIR = BACKEND_DIR.parent / "data" / "generated"
METRICS_JSON = BACKEND_DIR / "defend" / "models" / "metrics.json"
JSON_START, JSON_END = "===JSON_SUMMARY_START===", "===JSON_SUMMARY_END==="

app = FastAPI(title="FraudShield Evaluation & Generation API", version="0.2.0")

# Vite's default dev server port -- always allowed for local dev. The real
# deployed frontend origin(s) (e.g. https://<project>.vercel.app) come from
# CORS_ALLOWED_ORIGINS (comma-separated) so this can be widened per-deploy
# via an env var, without a code change/rebuild every time the frontend URL
# changes (Vercel preview deploys in particular get a new URL each time).
# Vite dev (5173) AND `vite preview` / `npm run preview` (4173) -- the
# preview port was missing before, which is what produced the
# `OPTIONS /runs/start 400 Bad Request` preflight rejections in the local
# uvicorn log (a CORS preflight from a disallowed origin is answered 400,
# not 403, so it reads like a malformed request rather than a CORS block).
_default_origins = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:4173", "http://127.0.0.1:4173",
]
_extra_origins = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
# Vercel mints a brand-new hostname for every preview deploy, so pinning
# exact origins means a broken demo on any redeploy. The regex covers
# *.vercel.app plus any tunnel host used to expose this API during a demo
# (cloudflared/ngrok), and can still be overridden/extended per-deploy via
# CORS_ALLOWED_ORIGINS without a code change.
_ORIGIN_REGEX = os.environ.get(
    "CORS_ALLOWED_ORIGIN_REGEX",
    r"https://([a-z0-9-]+\.)*(vercel\.app|trycloudflare\.com|ngrok-free\.app|ngrok\.io)",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _extra_origins,
    allow_origin_regex=_ORIGIN_REGEX,
    allow_methods=["*"],
    allow_headers=["*"],
)

# run_id -> run state dict, one registry per job type. In-memory by
# design -- see module docstring.
_eval_runs: dict = {}
_gen_runs: dict = {}
_orch_runs: dict = {}
_hydrate_runs: dict = {}


class RunRequest(BaseModel):
    only: Optional[str] = None  # comma-separated step names, same as the CLI's --only flag


class StartAgentRunRequest(BaseModel):
    objective: str
    scope: list[str]
    severity: str = "adaptive"
    scenario_count: int = 200
    seed: int = 42


class HydrateRequest(BaseModel):
    only: Optional[str] = None   # comma-separated bundle names; omit for everything
    force: bool = False          # re-download even when the local sha already matches


class GenerateRunRequest(BaseModel):
    only: Optional[str] = None  # comma-separated step names, e.g. "tabular_attacks,backfill_attack_cases,sync_model_registry"
    n_per_family: Optional[int] = None   # tabular_attacks: cases per family per split (script default: 50)
    n_per_split: Optional[int] = None    # voice/document/phishing_attacks: cases per split (script default: 10)
    n_cases: Optional[int] = None        # adaptive_weakness_round only
    seed: Optional[int] = None


def _spawn(args: list, cwd: str) -> subprocess.Popen:
    """Launch a child process without asyncio's subprocess transport.

    Why not asyncio.create_subprocess_exec: uvicorn on Windows runs the
    SelectorEventLoop, which does NOT implement subprocess support --
    create_subprocess_exec raises a bare NotImplementedError whose str()
    is the empty string. That silently broke every /runs/start,
    /evaluations/run and /generate/run on Windows: the endpoint still
    returned 202 Accepted, the background task caught the exception,
    recorded status="failed_to_launch" with error="", and no process was
    ever created (verified 2026-08-31 against a live uvicorn --reload on
    Windows: POST /runs/start -> failed_to_launch, error ""). Plain
    subprocess.Popen has no such platform gap; the blocking wait on it is
    pushed onto a worker thread with asyncio.to_thread so the event loop
    is never blocked (the whole point of the original async design).
    """
    # Own process GROUP, deliberately. A run spawns a tree -- agent_runner.py
    # -> run_all_generation.py / run_all_evaluations.py -> one eval_*.py per
    # step -- and killing only the parent orphans whatever is actually burning
    # the CPU. A group (Windows) / session (POSIX) gives /runs/{id}/stop
    # something it can terminate as a unit.
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | subprocess.CREATE_NEW_PROCESS_GROUP
        extra = {"creationflags": flags}
    else:
        extra = {"start_new_session": True}
    return subprocess.Popen(
        args, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        **extra,
    )


async def _execute_subprocess_run(registry: dict, run_id: str, script: Path, extra_args: list) -> None:
    """Shared launch/poll body for both /evaluations/run and /generate/run
    -- both master scripts share the exact same contract (argparse CLI,
    --json flag, ===JSON_SUMMARY_START/END=== markers around a JSON blob
    on stdout), so one implementation covers both."""
    state = registry[run_id]
    state["status"] = "running"
    args = [sys.executable, str(script), "--json", *extra_args]
    try:
        proc = await asyncio.to_thread(_spawn, args, str(BACKEND_DIR))
    except Exception as exc:
        state["status"] = "failed_to_launch"
        # repr(), not str(): a bare NotImplementedError stringifies to ""
        # and made this failure mode invisible for an entire session.
        state["error"] = repr(exc)
        state["finished_at"] = time.time()
        return

    state["pid"] = proc.pid
    stdout, stderr = await asyncio.to_thread(proc.communicate)
    state["finished_at"] = time.time()
    state["returncode"] = proc.returncode

    output = stdout.decode(errors="replace")
    summary = None
    if JSON_START in output and JSON_END in output:
        blob = output.split(JSON_START, 1)[1].split(JSON_END, 1)[0].strip()
        try:
            summary = json.loads(blob)
        except json.JSONDecodeError:
            summary = None
    state["summary"] = summary
    state["log_tail"] = "\n".join(output.splitlines()[-40:])
    state["stderr_tail"] = "\n".join(stderr.decode(errors="replace").splitlines()[-40:])
    state["status"] = "completed" if proc.returncode == 0 else "completed_with_failures"


# ---------------------------------------------------------------------------
# Evaluation endpoints
# ---------------------------------------------------------------------------

@app.post("/evaluations/run", status_code=202)
async def start_eval_run(req: RunRequest = RunRequest()):
    """Kicks off a full (or --only-scoped) evaluation refresh in the
    background and returns immediately. Poll /evaluations/status/{run_id}
    for progress -- this endpoint itself never blocks on the run."""
    run_id = uuid.uuid4().hex[:12]
    _eval_runs[run_id] = {
        "run_id": run_id, "job": "evaluation", "status": "queued", "started_at": time.time(),
        "finished_at": None, "only": req.only, "summary": None,
    }
    extra_args = ["--only", req.only] if req.only else []
    asyncio.create_task(_execute_subprocess_run(_eval_runs, run_id, EVAL_SCRIPT, extra_args))
    return {"run_id": run_id, "status": "queued"}


@app.get("/evaluations/status/{run_id}")
async def get_eval_status(run_id: str):
    state = _eval_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No evaluation run with id {run_id}")
    return state


@app.get("/evaluations/runs")
async def list_eval_runs():
    """Every evaluation run this API process has seen, most recent
    first -- lost on restart (see module docstring), which is fine: it's
    a progress log for the currently-open dashboard session, not a
    durable record."""
    return sorted(_eval_runs.values(), key=lambda r: r["started_at"], reverse=True)


@app.get("/evaluations/latest")
async def latest_results():
    """Current on-disk scoreboard -- reads metrics.json directly, does NOT
    trigger a run. What a dashboard should poll on load / on an interval
    for 'what do we know right now', separate from 'kick off a fresh
    evaluation' (POST /evaluations/run)."""
    if not METRICS_JSON.exists():
        return {}
    return json.loads(METRICS_JSON.read_text())


# ---------------------------------------------------------------------------
# Generation ("ingest attacks") endpoints
# ---------------------------------------------------------------------------

@app.post("/generate/run", status_code=202)
async def start_generate_run(req: GenerateRunRequest = GenerateRunRequest()):
    """Kicks off a full (or --only-scoped) attack-generation/ingestion
    refresh in the background: synthetic customers, the four tabular
    families, voice/document/phishing media families, video-KYC (whatever
    identities are on disk), then backfill_attack_cases + sync_model_registry
    so Supabase reflects the new data. Poll /generate/status/{run_id} for
    progress -- this endpoint itself never blocks on the run.

    Defaults are intentionally small (n_per_family=50, n_per_split=10) for
    a fast frontend-triggered refresh; pass explicit values for a full
    dataset build, or run generate/run_all_generation.py directly."""
    run_id = uuid.uuid4().hex[:12]
    _gen_runs[run_id] = {
        "run_id": run_id, "job": "generation", "status": "queued", "started_at": time.time(),
        "finished_at": None, "only": req.only, "summary": None,
    }
    extra_args = []
    if req.only:
        extra_args += ["--only", req.only]
    if req.n_per_family is not None:
        extra_args += ["--n-per-family", str(req.n_per_family)]
    if req.n_per_split is not None:
        extra_args += ["--n-per-split", str(req.n_per_split)]
    if req.n_cases is not None:
        extra_args += ["--n-cases", str(req.n_cases)]
    if req.seed is not None:
        extra_args += ["--seed", str(req.seed)]
    asyncio.create_task(_execute_subprocess_run(_gen_runs, run_id, GEN_SCRIPT, extra_args))
    return {"run_id": run_id, "status": "queued"}


@app.get("/generate/status/{run_id}")
async def get_generate_status(run_id: str):
    state = _gen_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No generation run with id {run_id}")
    return state


@app.get("/generate/runs")
async def list_generate_runs():
    """Every generation run this API process has seen, most recent
    first -- same lost-on-restart, dashboard-session-only posture as
    /evaluations/runs."""
    return sorted(_gen_runs.values(), key=lambda r: r["started_at"], reverse=True)


# ---------------------------------------------------------------------------
# Agent-run ("Create defense run" / live agent activity) endpoints
# ---------------------------------------------------------------------------
#
# Unlike /evaluations/* and /generate/*, this endpoint's job is ONLY to
# launch orchestration/agent_runner.py -- it does not track step-by-step
# progress itself. agent_runner.py persists real live progress directly
# into Supabase's campaign_runs.stage_results after every stage (see its
# own module docstring), so the frontend polls that table directly via
# the anon key (RLS: public read) instead of polling this API. This
# endpoint's own registry is just a process-launch log / crash log for
# cases where the subprocess dies before writing anything to Supabase.

@app.post("/runs/start", status_code=202)
async def start_agent_run(req: StartAgentRunRequest):
    """Launches orchestration/agent_runner.py in the background and
    returns its run_id immediately. Poll progress via Supabase directly:
        select * from campaign_runs where campaign_id = '<run_id>'
    (or GET /runs/{run_id}/process-status here for a raw log tail if the
    process appears to have died before writing anything)."""
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    args = [
        "--objective", req.objective, "--scope", ",".join(req.scope),
        "--severity", req.severity, "--scenario-count", str(req.scenario_count),
        "--seed", str(req.seed), "--run-id", run_id,
    ]
    _orch_runs[run_id] = {"run_id": run_id, "status": "launched", "started_at": time.time()}

    async def _launch():
        try:
            proc = await asyncio.to_thread(
                _spawn, [sys.executable, str(ORCH_SCRIPT), *args], str(BACKEND_DIR)
            )
        except Exception as exc:
            _orch_runs[run_id]["status"] = "failed_to_launch"
            _orch_runs[run_id]["error"] = repr(exc)
            _orch_runs[run_id]["finished_at"] = time.time()
            return
        _orch_runs[run_id]["pid"] = proc.pid
        _orch_runs[run_id]["status"] = "running"
        stdout, stderr = await asyncio.to_thread(proc.communicate)
        _orch_runs[run_id]["status"] = "process_exited"
        _orch_runs[run_id]["returncode"] = proc.returncode
        _orch_runs[run_id]["finished_at"] = time.time()
        _orch_runs[run_id]["log_tail"] = "\n".join(stdout.decode(errors="replace").splitlines()[-40:])
        _orch_runs[run_id]["stderr_tail"] = "\n".join(stderr.decode(errors="replace").splitlines()[-40:])

    asyncio.create_task(_launch())
    return {"run_id": run_id, "status": "launched"}


def _kill_tree(pid: int) -> str:
    """Kill a process and everything it spawned. Returns what was done.

    Windows has no process-group signal that reaches grandchildren reliably
    from Python, so taskkill /T /F is used there -- it is the only thing that
    actually walks the tree. POSIX gets a SIGTERM to the session, then SIGKILL
    if it is still alive after a grace period."""
    if os.name == "nt":
        proc = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, text=True,
        )
        return f"taskkill rc={proc.returncode} {proc.stdout.strip() or proc.stderr.strip()}"
    import signal
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        return "already gone"
    time.sleep(3)
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
        return "SIGTERM then SIGKILL"
    except ProcessLookupError:
        return "SIGTERM"


@app.post("/runs/{run_id}/stop")
async def stop_agent_run(run_id: str):
    """Stop a running defense run and say so in Supabase.

    Until 2026-09-02 there was no way to stop a run at all -- a war-room run
    that had wandered into a step which could not succeed simply held the UI
    at "Running" until its per-step timeout expired, and the only recourse was
    killing uvicorn. There is no honest demo story in that.

    Two halves, and the second matters as much as the first: kill the process
    tree, THEN mark campaign_runs so the frontend (which reads that table
    directly, not this API) stops showing the run as live. A killed process
    that leaves a row saying "running" forever is the ghost-run failure mode
    again, in a different table."""
    state = _orch_runs.get(run_id)
    killed = "no local process on record"
    if state and state.get("pid") and state.get("status") == "running":
        killed = await asyncio.to_thread(_kill_tree, state["pid"])
        state["status"] = "stopped"
        state["finished_at"] = time.time()

    # campaign_runs has NO status COLUMN. The run's status lives inside the
    # stage_results jsonb, at meta.status -- that is what agent_runner.py's
    # RunTracker.update_meta() writes and what the frontend's
    # mapCampaignRun() reads (row.stage_results?.meta?.status). The first
    # version of this endpoint updated a "status" column, which does not
    # exist, so every stop reported FAILED and no run was ever marked.
    #
    # Read-modify-write rather than a jsonb path update, because supabase-py
    # has no deep-merge: fetching the row and putting back a patched object is
    # the honest way to change one key without dropping the other nine.
    marked = None
    try:
        from db.supabase_client import get_service_client
        client = await asyncio.to_thread(get_service_client)

        def _mark():
            row = (client.table("campaign_runs")
                   .select("stage_results")
                   .eq("campaign_id", run_id)
                   .maybe_single().execute()).data
            if row is None:
                return "no campaign_runs row for this id"
            stage = row.get("stage_results") or {}
            meta = dict(stage.get("meta") or {})
            was = meta.get("status")
            meta["status"] = "stopped"
            meta["stoppedAt"] = datetime.now(timezone.utc).isoformat()
            stage = {**stage, "meta": meta}
            (client.table("campaign_runs")
             .update({"stage_results": stage})
             .eq("campaign_id", run_id).execute())
            return f"stage_results.meta.status: {was} -> stopped"

        marked = await asyncio.to_thread(_mark)
    except Exception as exc:
        # Report it. A stop that half-worked must not look like a clean stop.
        marked = f"FAILED to mark campaign_runs: {type(exc).__name__}: {exc}"

    return {"run_id": run_id, "process": killed, "supabase": marked}


@app.get("/runs/{run_id}/process-status")
async def get_run_process_status(run_id: str):
    """Raw subprocess launch/exit log -- a fallback for diagnosing a run
    that never wrote a campaign_runs row at all (e.g. Supabase creds
    missing). For real step-by-step progress, query campaign_runs
    directly (see start_agent_run's docstring)."""
    state = _orch_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No agent run with id {run_id}")
    return state


@app.get("/version")
async def version():
    """What commit is ACTUALLY running here.

    2026-09-02: the Railway deployment sat 11 commits behind for hours while
    the frontend called an endpoint that only existed in the newer code, and
    the only way to guess what was live was reading a truncated commit title
    off a dashboard card. Worse, Railway's "Redeploy" re-runs THAT
    deployment's commit rather than the branch head, so a fresh timestamp is
    not evidence of fresh code -- which is exactly how the stale build was
    mistaken for a new one.

    Railway injects RAILWAY_GIT_COMMIT_SHA at runtime, so this needs no build
    step. `git rev-parse` is the fallback for a local uvicorn. Compare the sha
    against `git log -1` and the question is answered in one request, with no
    dashboard involved.

    `stop_endpoint` is here deliberately: it is the specific route whose
    absence produced a 404 that looked like a bug in the frontend."""
    sha = (os.environ.get("RAILWAY_GIT_COMMIT_SHA")
           or os.environ.get("SOURCE_COMMIT")
           or os.environ.get("GIT_COMMIT"))
    origin = "env"
    if not sha:
        origin = "git"
        try:
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(BACKEND_DIR),
                                 capture_output=True, text=True, timeout=5).stdout.strip() or None
        except Exception:
            sha = None
    routes = {getattr(r, "path", "") for r in app.routes}
    return {
        "commit": sha,
        "commit_source": origin if sha else "unavailable",
        "branch": os.environ.get("RAILWAY_GIT_BRANCH"),
        "deployed_at": os.environ.get("RAILWAY_DEPLOYMENT_ID"),
        "stop_endpoint": "/runs/{run_id}/stop" in routes,
        "route_count": len(routes),
    }


@app.get("/")
async def root():
    """Service index.

    FastAPI defines no route for "/", so opening the deployment's bare URL
    returned {"detail":"Not Found"} -- which reads as a dead service even
    though /health was answering fine the whole time. Anyone checking
    whether the backend is up types the bare hostname first, so this route
    exists to answer that question directly and list what is actually
    available here."""
    return {
        "service": app.title,
        "version": app.version,
        "status": "ok",
        "docs": "/docs",
        "endpoints": {
            "health": "GET /health",
            "version": "GET /version",
            "latest_metrics": "GET /evaluations/latest",
            "start_evaluation": "POST /evaluations/run",
            "evaluation_status": "GET /evaluations/status/{run_id}",
            "start_generation": "POST /generate/run",
            "generation_status": "GET /generate/status/{run_id}",
            "start_agent_run": "POST /runs/start",
            "agent_run_process_status": "GET /runs/{run_id}/process-status",
            "data_status": "GET /data/status",
            "hydrate_data": "POST /data/hydrate",
        },
        "note": (
            "Reads (attack cases, evaluation results, model registry, campaign runs) do not go "
            "through this API -- the frontend queries Supabase directly with the anon key under "
            "public-read RLS. This API exists for the things a browser cannot do: launching and "
            "polling long-running Python subprocesses."
        ),
    }


# ---------------------------------------------------------------------------
# Dataset hydration
# ---------------------------------------------------------------------------
#
# data/generated/ is gitignored (236 MB, regenerable), so an image built
# from this repo ships without it. A run launched against such a container
# completes in seconds and honestly reports "Generation had failures" /
# "attacksTested: 0" -- structurally correct and completely empty
# (confirmed against the live Railway deployment on 2026-08-31).
#
# These two endpoints make that state visible and fixable from outside:
# GET /data/status says what this particular instance actually has on
# disk, and POST /data/hydrate pulls the bundles from Supabase Storage
# (backend/tools/storage_sync.py). The frontend reads the first one so it
# can refuse to offer a Start button that would produce an empty run,
# instead of letting someone click it and find out afterwards.

@app.get("/data/status")
async def data_status():
    """What generated data does THIS instance have? Cheap, no network --
    a directory scan, so it can be polled on page load."""
    bundles = {}
    if GENERATED_DIR.exists():
        for entry in sorted(GENERATED_DIR.iterdir()):
            if not entry.is_dir():
                continue
            files = [p for p in entry.rglob("*") if p.is_file() and p.name != ".storage_bundle.json"]
            marker = entry / ".storage_bundle.json"
            bundles[entry.name] = {
                "files": len(files),
                "bytes": sum(p.stat().st_size for p in files),
                "hydratedFromStorage": marker.exists(),
            }
    total_files = sum(b["files"] for b in bundles.values())
    return {
        "generatedDir": str(GENERATED_DIR),
        "exists": GENERATED_DIR.exists(),
        "bundles": bundles,
        "totalFiles": total_files,
        # The honest headline the UI keys off: can this instance run the
        # generation/evaluation pipeline over real cases at all?
        "canRunPipeline": total_files > 0,
    }


@app.post("/data/hydrate", status_code=202)
async def hydrate_data(req: HydrateRequest = HydrateRequest()):
    """Pull dataset bundles from Supabase Storage into data/generated/ on
    this instance. Long-running (hundreds of MB), so it launches in the
    background and returns a run_id to poll, same contract as the other
    job endpoints here."""
    run_id = uuid.uuid4().hex[:12]
    _hydrate_runs[run_id] = {
        "run_id": run_id, "job": "hydrate", "status": "queued", "started_at": time.time(),
        "finished_at": None, "only": req.only, "summary": None,
    }
    extra_args = ["pull"]
    if req.only:
        extra_args += ["--only", req.only]
    if req.force:
        extra_args.append("--force")

    async def _run():
        state = _hydrate_runs[run_id]
        state["status"] = "running"
        try:
            proc = await asyncio.to_thread(
                _spawn, [sys.executable, str(STORAGE_SYNC_SCRIPT), *extra_args], str(BACKEND_DIR)
            )
        except Exception as exc:
            state["status"] = "failed_to_launch"
            state["error"] = repr(exc)
            state["finished_at"] = time.time()
            return
        state["pid"] = proc.pid
        stdout, stderr = await asyncio.to_thread(proc.communicate)
        state["finished_at"] = time.time()
        state["returncode"] = proc.returncode
        state["log_tail"] = "\n".join(stdout.decode(errors="replace").splitlines()[-40:])
        state["stderr_tail"] = "\n".join(stderr.decode(errors="replace").splitlines()[-40:])
        state["status"] = "completed" if proc.returncode == 0 else "completed_with_failures"

    asyncio.create_task(_run())
    return {"run_id": run_id, "status": "queued"}


@app.get("/data/hydrate/status/{run_id}")
async def hydrate_status(run_id: str):
    state = _hydrate_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No hydrate run with id {run_id}")
    return state


@app.get("/health")
async def health():
    return {"status": "ok"}
