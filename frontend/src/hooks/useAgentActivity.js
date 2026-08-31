import { useQuery } from "@tanstack/react-query";
import { listAgentSteps } from "@/services/api/agents";

export function useAgentSteps(runId) {
  return useQuery({
    queryKey: ["agent-steps", runId],
    queryFn: () => listAgentSteps(runId),
    enabled: !!runId,
    // Real steps arrive one at a time as agent_runner.py's stages run
    // (each can take from milliseconds to minutes) — poll while the page
    // is open rather than a one-shot fetch. Cheap: one small jsonb read.
    refetchInterval: 2000,
  });
}
