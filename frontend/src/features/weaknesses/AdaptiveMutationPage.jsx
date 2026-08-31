import { useParams } from "react-router-dom";
import { ArrowDownIcon, SparklesIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useDefenseMetrics, useMutationIterations } from "@/hooks/useEvaluations";
import { DetectionTrendChart } from "@/features/dashboard/DetectionTrendChart";
export function AdaptiveMutationPage() {
  const {
    runId = ""
  } = useParams();
  const {
    data: iterations,
    isLoading
  } = useMutationIterations(runId);
  const {
    data: metrics
  } = useDefenseMetrics(runId);
  return <div className="space-y-6">
      <PageHeader eyebrow="Blue Team · Adapt" title="Adaptive mutation" description="Each cycle takes the weakness the Blue Team just missed, mutates the attack, and re-tests — DISCOVER → SIMULATE → ATTACK → EVALUATE → ADAPT." />

      {metrics ? <DetectionTrendChart data={metrics} /> : <Skeleton className="h-64 w-full" />}

      {isLoading ? <div className="space-y-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div> : <div className="space-y-3">
          {iterations?.map((it, i) => <div key={it.iteration} className="space-y-3">
              <Card className={i === iterations.length - 1 ? "border-primary/30 bg-primary/5" : undefined}>
                <CardHeader>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <div className="flex size-8 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-sm font-semibold text-primary">
                        {String(it.iteration).padStart(2, "0")}
                      </div>
                      <div>
                        <CardTitle className="text-base">Iteration {it.iteration}</CardTitle>
                        <CardDescription>{it.weakness}</CardDescription>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="cn-font-heading text-2xl font-semibold tabular-nums text-foreground">
                        {it.detectionRate}%
                      </p>
                      <p className="text-xs text-muted-foreground">detection rate</p>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Progress value={it.detectionRate} />
                  <div className="space-y-1.5">
                    <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                      What the mutation engine changed
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {it.changes.map(c => <Badge key={c} variant="outline" className="border-border text-foreground">
                          {c}
                        </Badge>)}
                    </div>
                  </div>
                </CardContent>
              </Card>
              {i < iterations.length - 1 ? <div className="flex justify-center">
                  <ArrowDownIcon className="size-4 text-muted-foreground/60" />
                </div> : null}
            </div>)}
        </div>}

      {iterations && iterations.length > 0 ? <Card className="border-primary/30 bg-primary/5">
          <CardContent className="flex items-center gap-3 py-4">
            <SparklesIcon className="size-5 shrink-0 text-primary" />
            <p className="text-sm text-foreground">
              Detection rose from {iterations[0].detectionRate}% to{" "}
              {iterations[iterations.length - 1].detectionRate}% across {iterations.length} adaptive iterations —
              the defense hardened itself against this weakness without human intervention.
            </p>
          </CardContent>
        </Card> : null}
    </div>;
}
