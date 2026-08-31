import { Link, useParams } from "react-router-dom";
import { TriangleAlertIcon, ZapIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { SeverityBadge } from "@/components/shared/badges";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useWeaknesses } from "@/hooks/useEvaluations";
import { ATTACK_CATEGORY_LABEL } from "@/types";
export function WeaknessAnalysisPage() {
  const {
    runId = ""
  } = useParams();
  const {
    data: weaknesses,
    isLoading
  } = useWeaknesses(runId);
  return <div className="space-y-6">
      <PageHeader eyebrow="Blue Team" title="Weakness analysis" description={`Attack categories where ${runId || "this run"}'s defense showed the weakest detection, and the reasoning behind each gap.`} actions={<Button asChild>
            <Link to={`/runs/${runId}/mutation`}>
              <ZapIcon className="size-4" />
              Generate Adaptive Attacks
            </Link>
          </Button>} />

      {isLoading ? <div className="space-y-4">
          <Skeleton className="h-44 w-full" />
          <Skeleton className="h-44 w-full" />
        </div> : <div className="space-y-4">
          {weaknesses?.map(w => <Card key={w.id} className="border-destructive/20">
              <CardHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <TriangleAlertIcon className="size-4 shrink-0 text-destructive" />
                  <CardTitle className="text-base">Defense weakness detected — {w.label}</CardTitle>
                  <SeverityBadge severity={w.severity} />
                </div>
                <CardDescription>{ATTACK_CATEGORY_LABEL[w.category]}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>Detection rate</span>
                      <span className="font-medium text-foreground tabular-nums">{w.detectionRate}%</span>
                    </div>
                    <Progress value={w.detectionRate} />
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>Miss rate</span>
                      <span className="font-medium text-destructive tabular-nums">{w.missRate}%</span>
                    </div>
                    <Progress value={w.missRate} className="[&>div]:bg-destructive" />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Why the defense misses this
                  </p>
                  <ul className="space-y-1 text-sm text-foreground">
                    {w.reasons.map(r => <li key={r} className="flex gap-2">
                        <span className="text-muted-foreground">·</span>
                        {r}
                      </li>)}
                  </ul>
                </div>

                <div className="rounded-2xl bg-muted/60 px-4 py-2.5 text-sm text-foreground">
                  <span className="font-medium">Recommended: </span>
                  {w.recommendedAction}
                </div>
              </CardContent>
            </Card>)}
        </div>}
    </div>;
}
