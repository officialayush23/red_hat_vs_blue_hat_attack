import { supabase } from "@/lib/supabaseClient";
import { getRun } from "@/services/api/runs";
import { listScoredCases, OUTCOME_META, outcomeOf } from "@/services/api/liveCases";

// GET /api/evaluations/:runId/cases
//
// Real scored cases from Supabase (services/api/liveCases.js), mapped onto
// the field names the evaluation and schematic views already use.
//
// Was: mockStore.js's getEvaluationCases(), a seeded-random generator that
// invented the attack name, every model signal, whether each signal
// "triggered", and the fused risk score for every case shown.
//
// One field deliberately does NOT survive the move: `triggered`. The old
// mock decided per-signal triggered/not by comparing its own invented score
// to an invented threshold. Real per-detector decision thresholds are not
// carried on evaluation_results rows (only the fused decision is), so there
// is no honest way to say whether an individual model fired. The real score
// is shown instead, and consumers must not render a triggered/below-
// threshold verdict they cannot support.
export async function listEvaluationCases(runId, limit = 12) {
  const rows = await listScoredCases(limit);
  return rows.map((r) => ({
    id: r.id,
    runId,
    caseId: r.caseId,
    attackFamilyId: r.family,
    attackName: r.familyLabel,
    category: r.category,
    modelSignals: r.modelSignals.map((sig) => ({ model: sig.model, score: sig.score })),
    // Consumers render this as a percentage (x * 100); fused_risk_score is
    // persisted 0-100, so it is normalised here rather than at each call site.
    fusedRiskScore: r.riskScore / 100,
    decision: r.decision,
    evidence: r.evidence,
    actualLabel: r.actualLabel,
    detected: r.detected,
    outcome: r.outcome,
    outcomeLabel: OUTCOME_META[r.outcome].label,
    splitPortion: r.splitPortion,
  }));
}

export { outcomeOf };

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
      const nSamples = m.n_samples ?? null;
      return {
        id,
        name,
        modality: row.signal_category ?? "transaction",
        precision: m.precision ?? 0,
        recall: m.recall ?? 0,
        f1: m.f1 ?? 0,
        detectionRate: Math.round((m.recall ?? 0) * 100),
        status: row.status,
        // Evidence strength, carried through so the UI can never show a
        // headline percentage without the sample size behind it. This is
        // the difference between "100% on 1.39M rows" and "100% on 6" --
        // both are real numbers in metrics.json, and only one of them
        // means anything. video_kyc_detector is currently the latter
        // (n_samples=6, three fraud and three bonafide), so any chart or
        // table that renders detectionRate MUST render nSamples with it.
        nSamples,
        nPositive: m.n_positive ?? null,
        falsePositiveRate: m.false_positive_rate ?? null,
        threshold: m.threshold ?? null,
        purpose: row.purpose ?? null,
        dataset: row.dataset ?? null,
        // Bands are deliberately blunt and stated in the UI, not hidden:
        // under 30 evaluated samples a percentage is close to meaningless,
        // under 200 it is indicative at best.
        evidenceStrength:
          nSamples === null ? "unknown" : nSamples < 30 ? "provisional" : nSamples < 200 ? "limited" : "strong",
      };
    });
}
