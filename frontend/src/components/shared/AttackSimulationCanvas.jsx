import { Link } from "react-router-dom";
import { MaximizeIcon } from "lucide-react";
import { AttackStream, StreamLegend } from "@/components/warroom/AttackStream";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useScoredCases } from "@/hooks/useLiveCases";

// Dashboard-sized view of the same real attack stream the war room shows
// full-bleed (features/warroom/WarRoomPage.jsx).
//
// This component used to read services/api/evaluations.js's
// listEvaluationCases(), which called mockStore.js's getEvaluationCases()
// -- a seeded-random generator that invented the attack name, every model
// signal and the fused risk score for every dot. It now reads real
// evaluation_results rows out of Supabase (services/api/liveCases.js), so
// each dot is a case this system genuinely scored.
export function AttackSimulationCanvas({ run }) {
  const { data: cases, isLoading } = useScoredCases({
    perFamily: 6,
    live: run?.status === "running",
  });

  const counts = { blocked: 0, missed: 0, cleared: 0, false_positive: 0 };
  for (const row of cases ?? []) counts[row.outcome] += 1;

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Live attack simulation</CardTitle>
            <CardDescription>
              Real scored cases from <code className="font-mono text-xs">evaluation_results</code> — green is
              blocked at the Blue Team boundary, red slipped through, amber is a false positive on legitimate
              traffic. Hover any dot for its real evidence.
            </CardDescription>
          </div>
          {run?.id && (
            <Button asChild variant="outline" size="sm">
              <Link to={`/runs/${run.id}/live`}>
                <MaximizeIcon className="size-4" /> War room
              </Link>
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <Skeleton className="h-[300px] w-full rounded-3xl" />
        ) : (
          <AttackStream cases={cases ?? []} live={run?.status === "running"} height={320} />
        )}
        <StreamLegend counts={counts} />
      </CardContent>
    </Card>
  );
}
