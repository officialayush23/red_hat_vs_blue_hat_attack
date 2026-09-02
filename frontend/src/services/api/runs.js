// Real Supabase reads against campaign_runs (001_core_schema.sql) — the
// real per-run record backend/orchestration/agent_runner.py writes to,
// joined against attack_campaigns for the run's name. RLS grants public
// read on both tables (002_rls_policies.sql), so this queries Supabase
// directly with the anon key — no backend round-trip for reads, see
// frontend/src/lib/supabaseClient.js. createRun() is the one write, and
// it goes through the FastAPI backend (services/api/jobs.js) because
// starting a run means launching a real local Python subprocess, which
// only the backend can do.

import { supabase } from "@/lib/supabaseClient";
import { startDefenseRun } from "@/services/api/jobs";

// campaign_runs.stage_results is a jsonb object shaped
// {meta: {...}, steps: [...]} — see agent_runner.py's module docstring.
// This maps that real row onto the same "run" shape the UI already
// expects (frontend/src/data/mockStore.js's buildRun() shape).
function mapCampaignRun(row) {
  const meta = row.stage_results?.meta ?? {};
  return {
    id: row.campaign_id,
    objective: meta.objective ?? "",
    scope: meta.scope ?? [],
    severity: meta.severity ?? "medium",
    scenarioCount: meta.scenarioCount ?? 0,
    // What this run actually attacked. Older runs predate these fields and
    // report undefined rather than a default, because claiming a run drew
    // from held-out combinations when nobody recorded which it drew from
    // would be inventing provenance.
    caseSource: meta.caseSource,
    difficulty: meta.difficulty,
    status: meta.status ?? "queued", // "running" | "completed" | "failed"
    createdAt: meta.createdAt ?? row.created_at,
    completedAt: meta.completedAt,
    currentIteration: meta.currentIteration ?? 1,
    totalIterations: meta.totalIterations ?? 1,
    // meta.weakestCategory is a real scope-category key (FAMILY_TO_CATEGORY
    // in agent_runner.py) that ATTACK_CATEGORY_LABEL[...] can actually look
    // up. row.weakest_stage is a raw family id / weakness_round2_* key —
    // kept only as attacksDetected's sibling below, never used as a label key.
    weakestCategory: meta.weakestCategory,
    attacksDetected: row.overall_detected,
    // Real run-level aggregates written by agent_runner.py's evaluation-agent
    // stage (and refreshed by the mutation-engine stage when severity is
    // "adaptive") — see RunTracker.update_meta() in orchestration/agent_runner.py.
    // Default to 0 / empty rather than undefined so pages that call
    // .toFixed()/.toLocaleString() directly don't crash while a run is still
    // mid-flight (these stages haven't written meta yet) — status distinguishes
    // "still running, no real numbers yet" from "completed with zeros".
    attacksTested: meta.attacksTested ?? 0,
    attacksCaught: meta.attacksCaught ?? 0,
    attacksMissed: meta.attacksMissed ?? 0,
    falsePositives: meta.falsePositives ?? 0,
    precision: meta.precision ?? 0,
    recall: meta.recall ?? 0,
    f1: meta.f1 ?? 0,
    prAuc: meta.prAuc ?? 0,
    // WAS THIS RUN EVER EVALUATED. The `?? 0` defaults below are kept so
    // arithmetic downstream cannot crash on undefined -- but a run stopped at
    // the Blue Team stage never reaches the evaluation stage that writes any
    // of these, so every one of them defaulted to 0 and the UI reported
    // "Detection 0.0%", "PRECISION 0.00", "0% of taxonomy" for runs that had
    // measured NOTHING. Indistinguishable from a defense that caught nothing,
    // which is the opposite claim. Anything rendering these must check this
    // flag first and show "not measured" rather than a number.
    hasEvaluation:
      meta.detectionRateAfter !== undefined && meta.detectionRateAfter !== null,
    detectionRateBefore: meta.detectionRateBefore ?? 0,
    detectionRateAfter: meta.detectionRateAfter ?? 0,
    improvementPct: meta.improvementPct ?? 0,
    attackCoveragePct: meta.attackCoveragePct ?? 0,
    // Sub-steps that actually failed during this run (agent_runner.py's
    // stage_failures). Non-empty means the numbers below may have come from
    // metrics.json entries written by EARLIER runs -- the orchestrator reads
    // the scoreboard, not only this run's output, and cannot tell them apart.
    stageFailures: meta.stageFailures ?? [],
    weaknesses: meta.weaknesses ?? [],
    mutationIterations: meta.mutationIterations ?? [],
  };
}

// GET /api/runs
export async function listRuns() {
  const { data, error } = await supabase
    .from("campaign_runs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(50);
  if (error) throw error;
  return data.map(mapCampaignRun);
}

// GET /api/runs/:id
export async function getRun(id) {
  if (!id) return undefined;
  const { data, error } = await supabase
    .from("campaign_runs")
    .select("*")
    .eq("campaign_id", id)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data ? mapCampaignRun(data) : null;
}

// POST /api/runs — launches the real agent_runner.py orchestrator via
// the FastAPI backend (POST /runs/start). Returns immediately with a
// run_id; campaign_runs won't have a row yet for a few hundred ms until
// agent_runner.py's own first insert lands — callers polling getRun(id)
// right after this should expect one initial "not found" tick.
export async function createRun(input) {
  const { run_id } = await startDefenseRun({
    objective: input.objective,
    scope: input.scope,
    severity: input.severity,
    scenarioCount: input.scenarioCount,
    caseSource: input.caseSource,
    difficulty: input.difficulty,
  });
  return { id: run_id };
}
