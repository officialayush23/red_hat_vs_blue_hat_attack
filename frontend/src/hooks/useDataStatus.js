import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getDataStatus, getHydrateStatus, startHydrate } from "@/services/api/jobs";

// Whether the backend instance this build talks to can actually run the
// pipeline over real cases. `enabled` should be the api-live flag: with no
// reachable backend there is nothing to ask.
export function useDataStatus(enabled = true) {
  return useQuery({
    queryKey: ["data-status"],
    queryFn: getDataStatus,
    enabled,
    retry: false,
    staleTime: 30_000,
  });
}

export function useHydrate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (opts) => {
      const { run_id } = await startHydrate(opts);
      // Poll to completion -- pulling ~236 MB takes minutes, and a caller
      // that returns as soon as the job is queued would let the UI claim
      // success while the container is still empty.
      //
      // A restarting backend (Render: out of memory, redeploy) answers 502s
      // for a while and then has no record of the job. Tolerate a run of
      // failed polls, and treat "lost" as terminal instead of looping on it.
      let failures = 0;
      for (;;) {
        await new Promise((r) => setTimeout(r, 3000));
        let state;
        try {
          state = await getHydrateStatus(run_id);
          failures = 0;
        } catch (err) {
          if (++failures >= 20) throw err; // ~1 minute of an unreachable backend
          continue;
        }
        if (state.status === "lost") {
          throw new Error(state.error || "The backend restarted and lost this job -- check data status and retry.");
        }
        if (["completed", "completed_with_failures", "failed_to_launch"].includes(state.status)) {
          return state;
        }
      }
    },
    // Re-read what is actually on disk either way -- a lost job may still
    // have finished some bundles before the restart.
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["data-status"] }),
  });
}
