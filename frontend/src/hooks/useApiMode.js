import { useQuery } from "@tanstack/react-query";
import { probeApi, API_BASE, HAS_API_BASE } from "@/services/api/jobs";

// "Can this build actually launch a run right now?"
//
// live   -> a FastAPI backend answered GET /health with {"status":"ok"};
//           the Start button launches a real agent_runner.py process.
// replay -> no reachable backend (the normal state for the deployed site,
//           because agent_runner.py spawns local Python subprocesses over
//           local model + data files). Every page still shows REAL data:
//           it reads completed runs, real scored cases and real model
//           metrics out of Supabase. It just cannot start new work.
//
// Deliberately not cached across reloads and re-probed on an interval, so
// starting uvicorn (or opening a tunnel) mid-demo flips the UI to live
// without a page refresh.
export function useApiMode() {
  const query = useQuery({
    queryKey: ["api-mode", API_BASE],
    queryFn: () => probeApi(),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    staleTime: 0,
    retry: false,
  });
  const live = query.data?.live === true;
  return {
    ...query,
    live,
    mode: live ? "live" : "replay",
    apiBase: API_BASE,
    hasApiBase: HAS_API_BASE,
    reason: query.data?.reason,
  };
}
