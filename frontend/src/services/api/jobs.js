// Real fetch calls against backend/api/main.py -- the one part of this
// app that genuinely can't be a direct Supabase read, because it
// launches and polls a long-running local Python subprocess (evaluation
// or generation). Not a mock: this module has no mockDelay/mockStore
// dependency, ever -- if the FastAPI backend isn't running, these calls
// fail with a real network error, which is the correct behavior (no
// pretend-success screen).
//
// Requires `uvicorn api.main:app --reload --port 8000` running from
// backend/ -- see backend/api/main.py's module docstring.

// ---- API base resolution ------------------------------------------------
//
// Three distinct situations, which the old one-liner
// (`import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"`)
// collapsed into one and got wrong on a deploy:
//
//  1. Local dev -> http://localhost:8000, the uvicorn the developer is
//     running. Correct, unchanged.
//  2. Deployed WITH a reachable API (a tunnel to a machine that can run
//     the models, or a hosted FastAPI) -> that absolute https origin.
//  3. Deployed WITHOUT one -> there is NO api. Falling back to
//     "http://localhost:8000" here is actively harmful (the browser blocks
//     it as mixed content / loopback), and falling back to a RELATIVE path
//     is worse: the request goes to the static host, vercel.json rewrites
//     `/(.*)` to `/index.html`, and a POST to a static HTML file is
//     answered `405 Method Not Allowed` -- which is exactly the
//     "POST /runs/start failed (405)" seen in production. So case 3
//     resolves to an empty base and every launch call refuses to fire,
//     with the UI switching to replay mode instead.
const RAW_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
const IS_LOCAL =
  typeof window !== "undefined" &&
  /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);

function resolveApiBase() {
  if (!RAW_BASE) return IS_LOCAL ? "http://localhost:8000" : "";
  // A relative base ("", "/", "/api") means same-origin. On a static host
  // that is never a real API -- see case 3 above.
  if (!/^https?:\/\//i.test(RAW_BASE)) return IS_LOCAL ? RAW_BASE.replace(/\/+$/, "") : "";
  // A loopback base on a deployed origin can never be reached by the
  // visitor's browser, whoever set it.
  if (!IS_LOCAL && /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])/i.test(RAW_BASE)) {
    console.warn(
      `[jobs.js] VITE_API_BASE_URL is "${RAW_BASE}" but this build is served from ` +
        `${window.location.hostname}. A visitor's browser cannot reach your loopback address, ` +
        "so the app is running in replay mode. Set VITE_API_BASE_URL to a publicly reachable " +
        "https origin in Vercel's Environment Variables (Production scope) and redeploy -- " +
        "Vite bakes env vars in at BUILD time, so saving the variable alone changes nothing.",
    );
    return "";
  }
  return RAW_BASE.replace(/\/+$/, "");
}

export const API_BASE = resolveApiBase();

// True when there is an address worth calling at all. False means the UI
// must not offer to launch anything -- see useApiHealth().
export const HAS_API_BASE = API_BASE !== "";

function assertApi(path) {
  if (!HAS_API_BASE) {
    throw new Error(
      `No backend configured for this build, so ${path} was not sent. ` +
        "This deploy is read-only (replay mode): it reads real completed runs from Supabase " +
        "but cannot launch new ones. Set VITE_API_BASE_URL to a reachable FastAPI origin and redeploy.",
    );
  }
}

async function apiPost(path, body) {
  assertApi(path);
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`POST ${path} failed (${res.status}): ${detail}`);
  }
  return res.json();
}

async function apiGet(path) {
  assertApi(path);
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`GET ${path} failed (${res.status}): ${detail}`);
  }
  return res.json();
}

// ---- Evaluation jobs --------------------------------------------------

// POST /evaluations/run — kicks off evaluation/run_all_evaluations.py.
// `only`: optional comma-separated step names (voice_spoof,
// document_consistency, video_kyc, phishing_classifier, gnn, fusion,
// behavioral_adjustment, adversarial_tabular).
export async function startEvaluationRun(only) {
  return apiPost("/evaluations/run", only ? { only } : {});
}

// GET /evaluations/status/:runId — poll until status is "completed" or
// "completed_with_failures". `summary` carries per-step results + the
// current scoreboard once finished.
export async function getEvaluationRunStatus(runId) {
  return apiGet(`/evaluations/status/${runId}`);
}

export async function listEvaluationRuns() {
  return apiGet("/evaluations/runs");
}

// GET /evaluations/latest — current on-disk metrics.json scoreboard,
// does not trigger a run. Cheap to poll on page load.
export async function getLatestEvaluationResults() {
  return apiGet("/evaluations/latest");
}

// ---- Generation ("ingest attacks") jobs -------------------------------

// POST /generate/run — kicks off generate/run_all_generation.py.
// opts: { only, n_per_family, n_per_split, n_cases, seed } — all optional,
// see backend/api/main.py's GenerateRunRequest for exact semantics.
export async function startGenerationRun(opts) {
  return apiPost("/generate/run", opts ?? {});
}

export async function getGenerationRunStatus(runId) {
  return apiGet(`/generate/status/${runId}`);
}

export async function listGenerationRuns() {
  return apiGet("/generate/runs");
}

// ---- Agent runs ("Create defense run") ---------------------------------

// POST /runs/start — launches backend/orchestration/agent_runner.py, a
// REAL 7-stage agent pipeline (orchestrator → threat-research →
// attack-planner → attack-generator → blue-team → evaluation →
// mutation-engine) that calls the project's real generate_*.py/eval_*.py
// scripts and reports exactly what they did — no simulated narration.
// Progress is NOT polled here: agent_runner.py writes live progress
// directly into Supabase's campaign_runs table (see services/api/runs.js
// and services/api/agents.js), which the frontend reads directly via the
// anon key. This call only launches the process and returns its run_id.
export async function startDefenseRun({ objective, scope, severity, scenarioCount, seed }) {
  return apiPost("/runs/start", {
    objective,
    scope,
    severity,
    scenario_count: scenarioCount,
    seed,
  });
}

// POST /runs/:runId/stop — kill the run's whole process tree AND mark
// campaign_runs.status = 'stopped' so the UI stops showing it as live.
// Before this existed there was no way to end a run at all: one that had
// wandered into a step that could not succeed held the war room at
// "Running" until a 30-minute per-step timeout expired.
export async function stopDefenseRun(runId) {
  return apiPost(`/runs/${runId}/stop`, {});
}

// GET /runs/:runId/process-status — raw subprocess launch/exit log, a
// fallback for diagnosing a run that never wrote a campaign_runs row at
// all (e.g. missing Supabase credentials on the backend). Real progress
// comes from Supabase directly, not from this.
export async function getRunProcessStatus(runId) {
  return apiGet(`/runs/${runId}/process-status`);
}

// ---- Dataset hydration ---------------------------------------------------

// GET /data/status -- what generated data the backend instance we're
// talking to actually has on disk. This matters because the Railway image
// is built from the repo, and data/generated/ is gitignored: a run
// launched against a container that has never been hydrated completes in
// seconds and reports attacksTested: 0. Reading this lets the UI say so
// BEFORE someone clicks Start, instead of after.
export async function getDataStatus() {
  return apiGet("/data/status");
}

// POST /data/hydrate -- pull the dataset bundles from Supabase Storage
// into that instance (backend/tools/storage_sync.py). Hundreds of MB, so
// it returns a run_id to poll rather than blocking.
export async function startHydrate(opts) {
  return apiPost("/data/hydrate", opts ?? {});
}

export async function getHydrateStatus(runId) {
  return apiGet(`/data/hydrate/status/${runId}`);
}

// ---- Health -------------------------------------------------------------

export async function checkApiHealth() {
  return apiGet("/health");
}

// Boolean "is there a live backend behind this build right now" probe.
// Never throws: an unreachable/absent API is a normal, expected state
// (the deployed site runs in replay mode), not an error to surface.
export async function probeApi(timeoutMs = 4000) {
  if (!HAS_API_BASE) return { live: false, reason: "no-api-base", base: API_BASE };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: controller.signal });
    if (!res.ok) return { live: false, reason: `http-${res.status}`, base: API_BASE };
    const body = await res.json().catch(() => ({}));
    return { live: body?.status === "ok", reason: body?.status ?? "unknown", base: API_BASE };
  } catch (err) {
    return { live: false, reason: err?.name === "AbortError" ? "timeout" : "unreachable", base: API_BASE };
  } finally {
    clearTimeout(timer);
  }
}

// ---- Polling helper -------------------------------------------------------

// Polls a status endpoint (getEvaluationRunStatus / getGenerationRunStatus)
// until it reports a terminal status, calling onUpdate after every poll so
// a caller can drive a progress UI. Returns the final state.
const TERMINAL_STATUSES = new Set(["completed", "completed_with_failures", "failed_to_launch", "stopped"]);

export async function pollRunUntilDone(getStatus, runId, { intervalMs = 2000, onUpdate } = {}) {
  for (;;) {
    const state = await getStatus(runId);
    onUpdate?.(state);
    if (TERMINAL_STATUSES.has(state.status)) return state;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
