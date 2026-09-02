import { useParams, Link } from "react-router-dom";
import { ArrowRightIcon, ClockIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { RunStatusBadge } from "@/components/shared/badges";
import { StatCard } from "@/components/shared/StatCard";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRun } from "@/hooks/useRuns";
import { useDefenseMetrics } from "@/hooks/useEvaluations";
import { DetectionTrendChart } from "@/features/dashboard/DetectionTrendChart";
import { CaughtVsMissedChart } from "@/features/dashboard/CaughtVsMissedChart";
import { ATTACK_CATEGORY_LABEL } from "@/types";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
export function RunResultsPage() {
  const {
    runId = ""
  } = useParams();
  const {
    data: run,
    isLoading
  } = useRun(runId);
  const {
    data: metrics
  } = useDefenseMetrics(runId);
  if (isLoading) {
    return <div className="space-y-6">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>;
  }
  if (!run) {
    return <div className="space-y-6">
        <PageHeader eyebrow="Results" title="Run results" />
        <EmptyState icon={<ClockIcon className="size-10" />} title="This run hasn't reported in yet" description="If you just started it, results usually land here within a few seconds. If it's been longer than that, the run ID may be wrong or the run failed to launch -- check Agent Console for its raw process status." action={<Button asChild variant="outline">
                <Link to="/runs">Back to defense runs</Link>
              </Button>} />
      </div>;
  }
  // A run that was stopped or that failed before the evaluation stage has
  // written NO aggregates. Every field below would fall back to its 0
  // default and this page would report "0.0% detection, PRECISION 0.00,
  // 0% of taxonomy" -- a claim that the defense caught nothing, which is
  // the opposite of "we never measured". Refuse to render numbers that
  // were never computed.
  if (!run.hasEvaluation) {
    return <div className="space-y-6">
        <PageHeader eyebrow="Results" title={`Run results \u2014 ${run.id}`} description={run.objective} actions={<RunStatusBadge status={run.status} />} />
        <EmptyState icon={<ClockIcon className="size-10" />} title="This run has no measured results" description={run.status === "running" ? "The run is still in flight and has not reached the evaluation stage yet. Watch it in the war room \u2014 results appear here once evaluation completes." : "This run ended before the evaluation stage, so no detection rate, precision or coverage was ever computed for it. The numbers are absent, not zero."} action={<Button asChild variant="outline">
                <Link to={run.status === "running" ? `/runs/${run.id}/live` : "/runs"}>
                  {run.status === "running" ? "Open war room" : "Back to defense runs"}
                </Link>
              </Button>} />
      </div>;
  }

  return <div className="space-y-6">
      <PageHeader eyebrow="Results" title={`Run results — ${run.id}`} description={run.objective} actions={<RunStatusBadge status={run.status} />} />

      <Card>
        <CardHeader>
          <CardTitle>Before vs. after the adaptive feedback loop</CardTitle>
          <CardDescription>Detection rate on {run.scope.map(c => ATTACK_CATEGORY_LABEL[c]).join(", ")}</CardDescription>
        </CardHeader>
        {/* When no adaptive round actually ran, "100.0% -> 100.0%, +0.0 pts
            improvement" reads as a broken widget. It isn't -- it is the
            truthful output of a run where nothing was missed, so the
            mutation engine had no weakness to target. Say that instead of
            rendering an empty win. */}
        {run.improvementPct === 0 && run.detectionRateBefore === run.detectionRateAfter ? (
          <CardContent className="space-y-2 py-6 text-center">
            <p className="cn-font-heading text-4xl font-semibold tabular-nums text-foreground">
              {run.detectionRateAfter.toFixed(1)}%
            </p>
            <p className="mx-auto max-w-xl text-sm text-muted-foreground">
              No adaptive round ran for this scope: every family scored caught every attack, so the mutation
              engine had no real weakness to target. There is no before/after to show — an unchanged number
              here is the honest result, not an improvement of zero.
            </p>
          </CardContent>
        ) : (
        <CardContent className="flex flex-col items-center justify-center gap-4 py-6 sm:flex-row sm:gap-8">
          <div className="text-center">
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Before mutation</p>
            <p className="cn-font-heading text-4xl font-semibold tabular-nums text-muted-foreground">
              {run.detectionRateBefore.toFixed(1)}%
            </p>
          </div>
          <ArrowRightIcon className="size-6 shrink-0 rotate-90 text-muted-foreground/50 sm:rotate-0" />
          <div className="text-center">
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">After mutation</p>
            <p className="cn-font-heading text-4xl font-semibold tabular-nums text-primary">
              {run.detectionRateAfter.toFixed(1)}%
            </p>
          </div>
          <div className="rounded-2xl bg-primary/10 px-4 py-2 text-center">
            <p className="cn-font-heading text-xl font-semibold text-primary">+{run.improvementPct.toFixed(1)} pts</p>
            <p className="text-xs text-muted-foreground">improvement</p>
          </div>
        </CardContent>
        )}
      </Card>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Precision" value={run.precision.toFixed(2)} />
        <StatCard label="Recall" value={run.recall.toFixed(2)} />
        <StatCard label="F1 score" value={run.f1.toFixed(2)} />
        <StatCard label="PR-AUC" value={run.prAuc.toFixed(2)} />
        <StatCard label="Attack coverage" value={run.attackCoveragePct.toFixed(0)} suffix="%" />
        <StatCard label="Attacks tested" value={run.attacksTested.toLocaleString()} />
        <StatCard label="Attacks caught" value={run.attacksCaught.toLocaleString()} tone="positive" />
        <StatCard label="False positives" value={run.falsePositives.toLocaleString()} trendLabel={`${run.attacksTested > 0 ? (run.falsePositives / run.attacksTested * 100).toFixed(2) : "0.00"}% of volume`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">{metrics && <DetectionTrendChart data={metrics} />}</div>
        <CaughtVsMissedChart run={run} />
      </div>
    </div>;
}
