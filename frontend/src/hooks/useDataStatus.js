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
      for (;;) {
        await new Promise((r) => setTimeout(r, 3000));
        const state = await getHydrateStatus(run_id);
        if (["completed", "completed_with_failures", "failed_to_launch"].includes(state.status)) {
          return state;
        }
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["data-status"] }),
  });
}
