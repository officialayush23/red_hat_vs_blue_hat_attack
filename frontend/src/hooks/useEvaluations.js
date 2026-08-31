import { useQuery } from "@tanstack/react-query";
import { getDefenseMetrics, listEvaluationCases, listModelPerformance, listMutationIterations, listWeaknesses } from "@/services/api/evaluations";
export function useEvaluationCases(runId, limit = 12) {
  return useQuery({
    queryKey: ["evaluation-cases", runId, limit],
    queryFn: () => listEvaluationCases(runId, limit)
  });
}
export function useWeaknesses(runId) {
  return useQuery({
    queryKey: ["weaknesses", runId],
    queryFn: () => listWeaknesses(runId)
  });
}
export function useMutationIterations(runId) {
  return useQuery({
    queryKey: ["mutations", runId],
    queryFn: () => listMutationIterations(runId)
  });
}
export function useDefenseMetrics(runId) {
  return useQuery({
    queryKey: ["metrics", runId],
    queryFn: () => getDefenseMetrics(runId)
  });
}
export function useModelPerformance() {
  return useQuery({
    queryKey: ["model-performance"],
    queryFn: listModelPerformance
  });
}
