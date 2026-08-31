import { getEvaluationCases } from "@/data/mockStore";
import { mockDelay } from "@/services/api/client";
import { supabase } from "@/lib/supabaseClient";
import { getRun } from "@/services/api/runs";

// GET /api/evaluations/:runId/cases
//
// Still mock: a real per-case, per-model-signal breakdown (which detector
// scored this exact case, at what confidence) has no computed source yet —
// agent_runner.py's real subprocesses write aggregate metrics.json numbers
// and Supabase's attack_cases/evaluation_results rows, not a joined
// per-case view shaped for this card. Documented gap, not silently faked;
// see AttackSchematic/AttackSimulationCanvas, the only real consumers.
export async function listEvaluationCases(runId, limit = 12) {
  return mockDelay(getEvaluationCases(runId, limit));
}

// GET /api/evaluations/:runId/weaknesses — real weakness cards written by
// agent_runner.py's evaluation-agent stage (RunTracker.update_meta ->
// meta.weaknesses, built by _build_weaknesses() from real metrics.json
// per-family recall). Empty array (not mock data) if the run hasn't
// reached that stage yet.
export async function listWeaknesses(runId) {
  const run = await getRun(runId);
  return run?.weaknesses ?? [];
}

// GET /api/evaluations/:runId/mutations — real iteration history written
// by agent_runner.py (meta.mutationIterations): one real "baseline"
// iteration after the evaluation-agent stage, plus a real round-2 entry
// appended by the mutation-engine stage when severity=adaptive and a real
// adaptive round actually ran and returned parseable before/after recall.
export async function listMutationIterations(runId) {
  const run = await getRun(runId);
  return run?.mutationIterations ?? [];
}

// GET /api/evaluations/:runId/metrics — one real data point per iteration
// in meta.mutationIterations, paired with the run's real precision/recall/
// f1/prAuc/false-positive-rate (agent_runner.py currently only recomputes
// recall/detectionRate per iteration — see update_meta() calls in stage 7 —
// so the other metrics repeat their stage-6 snapshot across iterations
// rather than being fabricated as if they'd been independently re-measured).
export async function getDefenseMetrics(runId) {
  const run = await getRun(runId);
  if (!run) return [];
  const fpRate = run.attacksTested > 0 ? run.falsePositives / run.attacksTested : 0;
  return (run.mutationIterations ?? []).map((it) => ({
    iteration: it.iteration,
    label: it.iteration === 1 ? "Baseline" : `Round ${it.iteration}`,
    detectionRate: it.detectionRate ?? 0,
    precision: run.precision ?? 0,
    recall: run.recall ?? 0,
    f1: run.f1 ?? 0,
    prAuc: run.prAuc ?? 0,
    falsePositiveRate: fpRate,
  }));
}

// GET /api/evaluations/models — real Supabase read against model_registry
// (001_core_schema.sql), synced from backend/defend/models/metrics.json by
// backend/db/sync_model_registry.py. Replaces the old MODEL_PERFORMANCE mock,
// which listed models that don't exist in this system ("Transformer —
// Behavioral", "GraphSAGE — Mule Network") instead of the real ones below.
//
// Curated to the models' real held-out/adversarial numbers where one
// exists (more meaningful than same-distribution validation numbers, and
// matches this page's own "evaluated against the latest adversarial case
// set" copy) — see sync_model_registry.py's MODEL_META for exactly which
// metrics.json key backs each row. gnn's real recall is genuinely poor
// (a known, documented weakness, not a display bug) — shown as-is.
const PRIMARY_MODEL_IDS = [
  { id: "xgboost_adversarial_eval", name: "XGBoost — Transaction" },
  { id: "lightgbm_adversarial_eval", name: "LightGBM — Transaction" },
  { id: "autoencoder_adversarial_eval", name: "Autoencoder — Anomaly" },
  { id: "voice_spoof_detector", name: "Wav2Vec2 — Voice Spoof" },
  { id: "document_consistency_detector", name: "PaddleOCR-VL — Document" },
  { id: "video_kyc_detector", name: "FaceNet — Video KYC" },
  { id: "phishing_classifier_evidence_gate", name: "Phishing Classifier (TF-IDF + LogisticRegression)" },
  { id: "gnn_colab_round5_reported", name: "GraphSAGE — Mule Network (GNN)" },
];

export async function listModelPerformance() {
  const ids = PRIMARY_MODEL_IDS.map(m => m.id);
  const { data, error } = await supabase
    .from("model_registry")
    .select("*")
    .in("id", ids);
  if (error) throw error;

  const byId = Object.fromEntries((data ?? []).map(row => [row.id, row]));
  return PRIMARY_MODEL_IDS
    .filter(({ id }) => byId[id]?.validation_metrics)
    .map(({ id, name }) => {
      const row = byId[id];
      const m = row.validation_metrics ?? {};
      return {
        name,
        modality: row.signal_category ?? "transaction",
        precision: m.precision ?? 0,
        recall: m.recall ?? 0,
        f1: m.f1 ?? 0,
        detectionRate: Math.round((m.recall ?? 0) * 100),
        status: row.status,
        nSamples: m.n_samples,
      };
    });
}
