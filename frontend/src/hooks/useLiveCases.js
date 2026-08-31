import { useQuery } from "@tanstack/react-query";
import { getCorpusStats, listScoredCases, listScoredCasesByFamily } from "@/services/api/liveCases";

// Real scored cases for the war-room animation. Polls while a run is in
// flight so newly scored cases stream in as the backend writes them.
export function useScoredCases({ perFamily = 8, live = false } = {}) {
  return useQuery({
    queryKey: ["scored-cases", perFamily],
    queryFn: () => listScoredCasesByFamily(perFamily),
    refetchInterval: live ? 5_000 : false,
    staleTime: live ? 0 : 60_000,
  });
}

// Newest-first feed, for the ticker.
export function useRecentScoredCases(limit = 40, live = false) {
  return useQuery({
    queryKey: ["scored-cases-recent", limit],
    queryFn: () => listScoredCases(limit),
    refetchInterval: live ? 5_000 : false,
    staleTime: live ? 0 : 60_000,
  });
}

export function useCorpusStats(live = false) {
  return useQuery({
    queryKey: ["corpus-stats"],
    queryFn: getCorpusStats,
    refetchInterval: live ? 10_000 : false,
    staleTime: live ? 0 : 60_000,
  });
}
