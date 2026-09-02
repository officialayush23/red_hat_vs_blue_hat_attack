import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createRun, getRun, listRuns } from "@/services/api/runs";

// "stopped" belongs here: a run the user stopped is over. Leaving it out
// left the war room spinning a live timer next to a "Stopped" badge --
// 171:22 and counting on a run whose process had been dead for hours.
const TERMINAL_STATUSES = new Set(["completed", "completed_with_failures", "failed", "stopped"]);

export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: listRuns,
  });
}

// THE RUN A JUDGE SHOULD BE LOOKING AT.
//
// Not runs[0]. The newest run is frequently one that was stopped or that
// failed before the evaluation stage, and every page keyed to it renders
// empty -- the sidebar's whole Blue Team and Results sections pointed at
// exactly such a run, so "Evaluation", "Weakness Analysis" and "Run
// Results" all opened blank. attacksTested > 0 is required as well as
// hasEvaluation: run_be7536b10d completed with attacksTested 0 and
// detectionRateAfter 100.0, and "100% over nothing" is its own kind of
// misleading.
//
// Returns { run, isStale, hasAny }: isStale says the newest run is NOT
// this one, so a page can say which run it is showing and why.
export function useLatestEvaluatedRun() {
  const { data: runs, isLoading } = useRuns();
  const run = runs?.find((r) => r.hasEvaluation && r.attacksTested > 0);
  return {
    run,
    isLoading,
    hasAny: Boolean(runs?.length),
    isStale: Boolean(run && runs?.[0] && runs[0].id !== run.id),
  };
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
