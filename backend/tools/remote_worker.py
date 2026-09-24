"""Run one pipeline step on a separate worker service (worker/worker_api.py)
instead of locally. Called by run_all_generation.py / run_all_evaluations.py
in place of the step's script when the step needs an environment this image
cannot have and its worker URL is configured.

    python tools/remote_worker.py --url $VOICE_WORKER_URL \\
        --script generate/generate_voice_attacks.py \\
        --hydrate voice_bonafide,voice_attacks --push voice_attacks -- --n-per-split 10

Behaves like the local script would: prints the worker's log, exits with
its return code, pulls any bundle the worker pushed (so the new cases are on
THIS machine for the steps that follow), and merges returned metrics.json
entries into this machine's metrics.json.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
METRICS_JSON = BACKEND_DIR / "defend" / "models" / "metrics.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--hydrate", default="")
    ap.add_argument("--push", default="")
    ap.add_argument("--metrics-keys", default="")
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    rest = a.rest[1:] if a.rest[:1] == ["--"] else a.rest
    split = lambda s: [x for x in s.split(",") if x]  # noqa: E731

    base = a.url.rstrip("/")
    headers = {"X-Worker-Token": os.environ.get("WORKER_TOKEN", "")}
    env = {k: os.environ[k] for k in ("FRAUDSHIELD_CAMPAIGN_ID", "VOICE_MAX_SECONDS", "DOC_OCR_BACKEND")
           if k in os.environ}
    body = {"script": a.script, "args": rest, "hydrate": split(a.hydrate), "push": split(a.push),
            "metrics_keys": split(a.metrics_keys), "env": env, "timeout": a.timeout}

    print(f"Dispatching {a.script} to worker {base} ...", flush=True)
    # A sleeping Render worker takes up to a minute to wake; retry the dispatch.
    for attempt in range(8):
        try:
            r = requests.post(f"{base}/jobs", json=body, headers=headers, timeout=90)
            if r.status_code < 500:
                break
        except requests.RequestException as exc:
            r = None
            print(f"  worker not reachable yet ({exc.__class__.__name__}), retrying...", flush=True)
        time.sleep(15)
    if r is None or r.status_code >= 300:
        print(f"WORKER DISPATCH FAILED: {getattr(r, 'status_code', 'no response')} "
              f"{getattr(r, 'text', '')[:300]}", file=sys.stderr)
        return 1
    job_id = r.json()["job_id"]

    seen, failures, deadline = 0, 0, time.time() + a.timeout + 600
    state = {}
    while time.time() < deadline:
        time.sleep(10)
        try:
            state = requests.get(f"{base}/jobs/{job_id}", headers=headers, timeout=60).json()
            failures = 0
        except Exception:
            failures += 1
            if failures > 30:
                print("WORKER UNREACHABLE for 5 minutes", file=sys.stderr)
                return 1
            continue
        log = state.get("log", [])
        for line in log[seen:]:
            print(f"  [worker] {line}", flush=True)
        seen = len(log)
        if state.get("status") in ("completed", "failed", "lost"):
            break
    else:
        print("WORKER JOB TIMED OUT", file=sys.stderr)
        return 1

    if state.get("status") != "completed":
        print(f"WORKER JOB {state.get('status', '?').upper()} (returncode={state.get('returncode')})",
              file=sys.stderr)
        return 1

    if a.push:
        from tools.storage_sync import pull
        print(f"Pulling worker output bundle(s) {a.push} from Storage ...", flush=True)
        if pull(a.push) != 0:
            print("PULL OF WORKER OUTPUT FAILED", file=sys.stderr)
            return 1
    if state.get("metrics"):
        m = json.loads(METRICS_JSON.read_text()) if METRICS_JSON.exists() else {}
        m.update(state["metrics"])
        METRICS_JSON.write_text(json.dumps(m, indent=2))
        print(f"Merged metrics.json entries from worker: {sorted(state['metrics'])}", flush=True)
    rc = state.get("returncode")
    return rc if isinstance(rc, int) else 0


if __name__ == "__main__":
    sys.exit(main())
