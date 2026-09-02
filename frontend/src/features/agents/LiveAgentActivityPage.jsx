import { useParams, Link } from "react-router-dom";
import { ZapIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { AgentStepList } from "@/components/shared/AgentStepList";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRun } from "@/hooks/useRuns";
import { useAgentSteps } from "@/hooks/useAgentActivity";

// agent_runner.py reports 8 steps: the 7 planned stages plus the
// data-loader step that hydrates this instance before generation. Used
// only to render progress against a known total, never to fabricate a
// stage's content.
const TOTAL_STAGES = 8;
// "stopped" belongs here: a run the user stopped is over. Leaving it out
// left the war room spinning a live timer next to a "Stopped" badge --
// 171:22 and counting on a run whose process had been dead for hours.
const TERMINAL_STATUSES = new Set(["completed", "completed_with_failures", "failed", "stopped"]);

export function LiveAgentActivityPage() {
  const { runId = "" } = useParams();
  const { data: run } = useRun(runId);
  const { data: steps } = useAgentSteps(runId);

  const stepCount = steps?.length ?? 0;
  const isComplete = run ? TERMINAL_STATUSES.has(run.status) : false;
  const progressPct = Math.min(100, Math.round((stepCount / TOTAL_STAGES) * 100));
  const isRunning = steps?.some(s => s.status === "running") ?? false;

  return <div className="space-y-6">
      <PageHeader eyebrow="Agent Console · Live" title="Agent activity & decision trace" description="Real steps from backend/orchestration/agent_runner.py — each stage calls this project's actual generate_*.py / eval_*.py scripts and reports what they really did." actions={run ? <Button asChild variant="outline">
              <Link to={`/runs/${run.id}/results`}>View results</Link>
            </Button> : null} />

      {!run || !steps ? <Skeleton className="h-96 w-full" /> : <div className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Orchestrator agent</CardTitle>
                  <CardDescription>Goal: "{run.objective}"</CardDescription>
                </div>
                <Badge variant="outline" className="border-transparent bg-primary/10 text-primary">
                  {run.id}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {steps.length === 0 ? <p className="text-sm text-muted-foreground">Waiting for the first real stage to report in…</p> : <AgentStepList steps={steps} />}
              {isRunning && <div className="flex items-center gap-2 rounded-2xl bg-muted/60 px-3 py-2.5 text-sm text-muted-foreground">
                  <ZapIcon className="size-4 animate-pulse text-primary" />
                  A real backend subprocess is running for this stage — this can take from seconds to several minutes.
                </div>}
              {run.status === "failed" && <div className="rounded-2xl bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
                  This run failed before completing. Check the backend terminal / API logs for the traceback.
                </div>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Progress</CardTitle>
              <CardDescription>{isComplete ? "Run complete" : "Real adversarial loop running"}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{stepCount} of {TOTAL_STAGES} stages</span>
                  <span className="tabular-nums">{progressPct}%</span>
                </div>
                <Progress value={progressPct} />
              </div>
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Scope</dt>
                  <dd className="font-medium">{run.scope.length} categories</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Scenarios</dt>
                  <dd className="font-medium tabular-nums">{run.scenarioCount.toLocaleString()}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Severity</dt>
                  <dd className="font-medium capitalize">{run.severity}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Iteration</dt>
                  <dd className="font-medium tabular-nums">
                    {run.currentIteration} / {run.totalIterations}
                  </dd>
                </div>
              </dl>
              {isComplete && <Button asChild className="w-full">
                  <Link to={`/runs/${run.id}/weaknesses`}>Review weaknesses found →</Link>
                </Button>}
            </CardContent>
          </Card>
        </div>}
    </div>;
}
