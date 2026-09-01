import { useQuery } from "@tanstack/react-query";
import { getAttack, getAttackCases, getGeneratedCombinations, getRepresentativeCase, listAttacks, listScenarios } from "@/services/api/attacks";
export function useAttacks() {
  return useQuery({
    queryKey: ["attacks"],
    queryFn: listAttacks
  });
}
export function useAttack(id) {
  return useQuery({
    queryKey: ["attacks", id],
    queryFn: () => getAttack(id),
    enabled: !!id
  });
}
export function useAttackCases(runId, limit = 6) {
  return useQuery({
    queryKey: ["attack-cases", runId, limit],
    queryFn: () => getAttackCases(runId, limit)
  });
}
export function useRepresentativeCase(attackId) {
  return useQuery({
    queryKey: ["representative-case", attackId],
    queryFn: () => getRepresentativeCase(attackId),
    enabled: !!attackId
  });
}
export function useGeneratedCombinations(family) {
  return useQuery({
    queryKey: ["generated-combinations", family],
    queryFn: () => getGeneratedCombinations(family),
    enabled: !!family
  });
}
export function useScenarios() {
  return useQuery({
    queryKey: ["attack-scenarios"],
    queryFn: listScenarios,
    staleTime: 60_000
  });
}
