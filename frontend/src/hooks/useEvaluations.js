import { useQuery } from "@tanstack/react-query";
import { getDefenseMetrics, listEvaluationCases, listModelPerformance, listMutationIterations, listWeaknesses } from "@/services/api/evaluations";

// These pages used to fetch once and then sit on a 30s-stale cache with no
// polling, so a run finishing (or a Blue Team eval landing) never showed up
// until a manual reload. Poll while the tab is visible; react-query pauses
// intervals for background tabs by default.
const LIVE = { refetchInterval: 10_000, staleTime: 5_000 };
export function useEvaluationCases(runId, limit = 12) {
  return useQuery({
    queryKey: ["evaluation-cases", runId, limit],
    queryFn: () => listEvaluationCases(runId, limit),
    ...LIVE
  });
}
export function useWeaknesses(runId) {
  return useQuery({
    queryKey: ["weaknesses", runId],
    queryFn: () => listWeaknesses(runId),
    enabled: !!runId,
    ...LIVE
  });
}
export function useMutationIterations(runId) {
  return useQuery({
    queryKey: ["mutations", runId],
    queryFn: () => listMutationIterations(runId),
    enabled: !!runId,
    ...LIVE
  });
}
export function useDefenseMetrics(runId) {
  return useQuery({
    queryKey: ["metrics", runId],
    queryFn: () => getDefenseMetrics(runId),
    enabled: !!runId,
    ...LIVE
  });
}
export function useModelPerformance() {
  return useQuery({
    queryKey: ["model-performance"],
    queryFn: listModelPerformance,
    refetchInterval: 30_000
  });
}
