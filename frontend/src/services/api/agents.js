// Real Supabase read against campaign_runs.stage_results.steps — the
// live agent-step trace backend/orchestration/agent_runner.py writes
// after every stage starts and completes (see its module docstring for
// the exact shape, which mirrors AgentStepList.jsx field-for-field).
// Replaces the old getAgentSteps() mock, which fabricated all 7 steps'
// text with Math.random() and no real backend behind any of it.

import { supabase } from "@/lib/supabaseClient";

// GET /api/agents/:runId/steps
export async function listAgentSteps(runId) {
  if (!runId) return [];
  const { data, error } = await supabase
    .from("campaign_runs")
    .select("stage_results")
    .eq("campaign_id", runId)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data?.stage_results?.steps ?? [];
}
