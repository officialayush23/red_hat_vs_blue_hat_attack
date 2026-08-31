import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createRun, getRun, listRuns } from "@/services/api/runs";

const TERMINAL_STATUSES = new Set(["completed", "completed_with_failures", "failed"]);

export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: listRuns,
  });
}

export function useRun(id) {
  return useQuery({
    queryKey: ["runs", id],
    queryFn: () => getRun(id),
    enabled: !!id,
    // Real agent_runner.py run in progress — poll until it reaches a
    // terminal status. Also re-polls a few times right after createRun()
    // even with no data yet, since campaign_runs' first row can land a
    // few hundred ms after POST /runs/start returns.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && TERMINAL_STATUSES.has(status) ? false : 2000;
    },
  });
}

export function useCreateRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: input => createRun(input),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["runs"]
      });
    }
  });
}
