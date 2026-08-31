import { useQuery } from "@tanstack/react-query";
import { fetchReport } from "@/services/api/reports";
export function useReport(runId) {
  return useQuery({
    queryKey: ["report", runId],
    queryFn: () => fetchReport(runId)
  });
}
