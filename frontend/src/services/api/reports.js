import { getRun } from "@/services/api/runs";
import { listModelPerformance, getDefenseMetrics } from "@/services/api/evaluations";

// GET /api/reports/:runId — assembled from the same real sources every
// other page now reads (campaign_runs.stage_results.meta via getRun(),
// model_registry via listModelPerformance()), not frontend/src/data/
// mockStore.js's getReport(). Two fields have no dedicated real source and
// are honestly derived rather than fabricated from scratch:
//   - topMissedScenarios: no script computes a per-scenario (as opposed to
//     per-family) miss rate yet, so this reuses the real per-family
//     weaknesses, sorted by real missRate -- same real numbers as the
//     Weaknesses table below, just re-sliced for this card.
//   - recommendedMitigations: the real recommendedAction each weakness
//     card already carries (_build_weaknesses() in agent_runner.py),
//     de-duplicated -- not a separate generated list.
export async function fetchReport(runId) {
  const [run, modelEvidence, iterationImprovement] = await Promise.all([
    getRun(runId),
    listModelPerformance(),
    getDefenseMetrics(runId),
  ]);
  if (!run) return null;

  const weaknesses = run.weaknesses ?? [];
  const topMissedScenarios = [...weaknesses]
    .sort((a, b) => (b.missRate ?? 0) - (a.missRate ?? 0))
    .slice(0, 5)
    .map((w) => ({ name: w.label, category: w.category, missRate: w.missRate }));
  const recommendedMitigations = [...new Set(weaknesses.map((w) => w.recommendedAction).filter(Boolean))];

  return {
    runId: run.id,
    generatedAt: run.completedAt ?? new Date().toISOString(),
    objective: run.objective,
    // Carried through from runs.js. A run that never reached the evaluation
    // stage has no performance numbers at all; the zeros below are fallbacks
    // to keep .toFixed() safe, NOT measurements. The page must not print
    // them as results -- see ReportPage.jsx.
    hasEvaluation: run.hasEvaluation,
    runStatus: run.status,
    attackCoveragePct: run.attackCoveragePct ?? 0,
    dataSource: run.status === "completed" ? "Live — completed run" : `Live — run ${run.status}`,
    performance: {
      detectionRateBefore: run.detectionRateBefore ?? 0,
      detectionRateAfter: run.detectionRateAfter ?? 0,
      precision: run.precision ?? 0,
      recall: run.recall ?? 0,
      f1: run.f1 ?? 0,
      prAuc: run.prAuc ?? 0,
      falsePositiveRate: run.attacksTested > 0 ? (run.falsePositives / run.attacksTested) * 100 : 0,
    },
    iterationImprovement,
    weaknesses,
    topMissedScenarios,
    modelEvidence,
    recommendedMitigations,
  };
}

// GET /api/reports/:runId/export?format=json|csv
export function exportReport(report, format) {
  if (format === "json") {
    return new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json"
    });
  }
  const rows = [["Metric", "Value"], ["Run ID", report.runId], ["Generated At", report.generatedAt], ["Objective", report.objective], ["Attack Coverage %", String(report.attackCoveragePct)], ["Detection Before %", String(report.performance.detectionRateBefore)], ["Detection After %", String(report.performance.detectionRateAfter)], ["Precision", String(report.performance.precision)], ["Recall", String(report.performance.recall)], ["F1", String(report.performance.f1)], ["PR-AUC", String(report.performance.prAuc)], ["False Positive Rate %", String(report.performance.falsePositiveRate)]];
  const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
  return new Blob([csv], {
    type: "text/csv"
  });
}
