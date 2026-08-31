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

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Defensive check: a deployed build whose API_BASE still resolves to
// localhost means VITE_API_BASE_URL wasn't baked into THIS build -- Vite
// only reads env vars at build time, so saving the variable in Vercel's
// dashboard does nothing until a fresh build actually runs. Every call
// below then fails with a browser-blocked CORS/loopback error that looks
// identical to a real network outage, so this logs a loud, specific
// explanation instead of leaving that to guesswork.
if (typeof window !== "undefined" && !/^(localhost|127\.0\.0\.1)$/.test(window.location.hostname) && /^https?:\/\/(localhost|127\.0\.0\.1)/.test(API_BASE)) {
  console.error(
    `[jobs.js] API_BASE is "${API_BASE}" on a non-local deploy (${window.location.hostname}). ` +
    "VITE_API_BASE_URL wasn't baked into this build -- set it in Vercel's Environment Variables " +
    "(Production scope) and trigger a fresh deploy, not just a variable save."
  );
}

async function apiPost(path, body) {
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

// GET /runs/:runId/process-status — raw subprocess launch/exit log, a
// fallback for diagnosing a run that never wrote a campaign_runs row at
// all (e.g. missing Supabase credentials on the backend). Real progress
// comes from Supabase directly, not from this.
export async function getRunProcessStatus(runId) {
  return apiGet(`/runs/${runId}/process-status`);
}

// ---- Health -------------------------------------------------------------

export async function checkApiHealth() {
  return apiGet("/health");
}

// ---- Polling helper -------------------------------------------------------

// Polls a status endpoint (getEvaluationRunStatus / getGenerationRunStatus)
// until it reports a terminal status, calling onUpdate after every poll so
// a caller can drive a progress UI. Returns the final state.
const TERMINAL_STATUSES = new Set(["completed", "completed_with_failures", "failed_to_launch"]);

export async function pollRunUntilDone(getStatus, runId, { intervalMs = 2000, onUpdate } = {}) {
  for (;;) {
    const state = await getStatus(runId);
    onUpdate?.(state);
    if (TERMINAL_STATUSES.has(state.status)) return state;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
