import { Link } from "react-router-dom";
import { ActivityIcon, AlertTriangleIcon, CrosshairIcon, ShieldCheckIcon, TrendingUpIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { RunStatusBadge } from "@/components/shared/badges";
import { AgentStepList } from "@/components/shared/AgentStepList";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRuns } from "@/hooks/useRuns";
import { useAgentSteps } from "@/hooks/useAgentActivity";
import { useDefenseMetrics } from "@/hooks/useEvaluations";
import { DetectionTrendChart } from "@/features/dashboard/DetectionTrendChart";
import { CategoryBreakdownChart } from "@/features/dashboard/CategoryBreakdownChart";
import { CaughtVsMissedChart } from "@/features/dashboard/CaughtVsMissedChart";
import { AttackSchematic } from "@/components/shared/AttackSchematic";
import { AttackSimulationCanvas } from "@/components/shared/AttackSimulationCanvas";
import { ATTACK_CATEGORY_LABEL } from "@/types";
import { EmptyState } from "@/components/shared/EmptyState";
export function DashboardPage() {
  const {
    data: runs,
    isLoading
  } = useRuns();
  // runs[0] is the most RECENT run, which is not the same thing as the most
  // recent run that produced numbers. A run stopped or failed before the
  // evaluation stage writes no aggregates at all, so every tile on this
  // dashboard fell back to 0 and the headline read "Detection rate 0.0%" --
  // a claim the defense caught nothing, from a run that measured nothing.
  // Show the newest run that actually reached evaluation, and say so.
  // attacksTested > 0 as well as hasEvaluation: run_be7536b10d is a real
  // completed run whose evaluation stage scored nothing (attacksTested 0,
  // detectionRateAfter 100.0), and "100% detection over 0 attacks" is as
  // misleading as a false zero. A headline needs a run with a denominator.
  const latestRun = runs?.find(r => r.hasEvaluation && r.attacksTested > 0) ?? runs?.[0];
  const latestRunIsStale = Boolean(runs?.length) && runs[0]?.id !== latestRun?.id;
  const {
    data: steps
  } = useAgentSteps(latestRun?.id ?? "");
  const {
    data: metrics
  } = useDefenseMetrics(latestRun?.id ?? "");
  const activeRuns = runs?.filter(r => r.status === "running").length ?? 0;
  if (isLoading) {
    return <div className="space-y-6">
        <Skeleton className="h-16 w-full" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({
          length: 8
        }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
      </div>;
  }
  if (!latestRun) {
    return <div className="space-y-6">
        <PageHeader eyebrow="Overview" title="Fraud defense overview" description="What the adversarial feedback loop has found, and whether the defense is actually getting stronger." />
        <EmptyState icon={<ShieldCheckIcon className="size-10" />} title="No defense runs yet" description="Kick off an adversarial evaluation to populate this dashboard with real detection results." action={<Button asChild>
                <Link to="/runs/new">Start Adversarial Evaluation</Link>
              </Button>} />
      </div>;
  }
  return <div className="space-y-6">
      <PageHeader eyebrow="Overview" title="Fraud defense overview" description="What the adversarial feedback loop has found, and whether the defense is actually getting stronger." actions={<Button asChild>
            <Link to="/runs/new">Start Adversarial Evaluation</Link>
          </Button>} />

      {!(latestRun.hasEvaluation && latestRun.attacksTested > 0) && (
        <EmptyState icon={<ShieldCheckIcon className="size-10" />} title="No run has produced measured results yet" description="Every defense run so far ended before the evaluation stage, so there is no detection rate, precision or coverage to display. The tiles below would show zeros that were never measured, so they are withheld." action={<Button asChild>
                <Link to="/runs/new">Start Adversarial Evaluation</Link>
              </Button>} />
      )}

      {latestRun.hasEvaluation && latestRun.attacksTested > 0 && <>
      {latestRunIsStale && (
        <p className="rounded-2xl border border-border bg-muted/50 px-4 py-2 text-sm text-muted-foreground">
          Showing <span className="font-medium text-foreground">{latestRun.id}</span> — the most recent run that
          completed evaluation. Newer runs exist but ended before producing measurable results.
        </p>
      )}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Active defense runs" value={String(activeRuns)} icon={<ActivityIcon className="size-4" />} />
        <StatCard label="Attacks evaluated" value={latestRun.attacksTested.toLocaleString()} icon={<CrosshairIcon className="size-4" />} trendLabel={`${latestRun.id} · latest run`} />
        <StatCard label="Detection rate" value={latestRun.detectionRateAfter.toFixed(1)} suffix="%" tone="positive" trend="up" trendLabel={`+${latestRun.improvementPct.toFixed(1)} pts vs. before mutation`} icon={<ShieldCheckIcon className="size-4" />} />
        <StatCard label="Missed attacks" value={latestRun.attacksMissed.toLocaleString()} tone="negative" trendLabel={`${latestRun.attacksTested > 0 ? (latestRun.attacksMissed / latestRun.attacksTested * 100).toFixed(1) : "0.0"}% miss rate`} icon={<AlertTriangleIcon className="size-4" />} />
        <StatCard label="False positives" value={latestRun.falsePositives.toLocaleString()} trendLabel={`${latestRun.attacksTested > 0 ? (latestRun.falsePositives / latestRun.attacksTested * 100).toFixed(2) : "0.00"}% of volume`} />
        <StatCard label="Attack coverage" value={latestRun.attackCoveragePct.toFixed(0)} suffix="%" trendLabel="of mapped attack taxonomy" />
        <StatCard label="Defense improvement" value={`+${latestRun.improvementPct.toFixed(1)}`} suffix="pts" tone="positive" trend="up" icon={<TrendingUpIcon className="size-4" />} trendLabel="this run" />
        <StatCard label="Weakest category" value={ATTACK_CATEGORY_LABEL[latestRun.weakestCategory]} trendLabel="generate harder variants →" />
      </div>

      <AttackSimulationCanvas run={latestRun} />

      <AttackSchematic run={latestRun} />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">{metrics && <DetectionTrendChart data={metrics} />}</div>
        <CaughtVsMissedChart run={latestRun} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <CategoryBreakdownChart />
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Recent agent activity</CardTitle>
            <CardDescription>{latestRun.id} · Red Team orchestration</CardDescription>
          </CardHeader>
          <CardContent>
            {steps ? <AgentStepList steps={steps} compact /> : <Skeleton className="h-40 w-full" />}
            <Button asChild variant="ghost" size="sm" className="mt-2 w-full justify-center">
              <Link to={`/runs/${latestRun.id}/activity`}>View full activity →</Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      </>}

      <Card>
        <CardHeader>
          <CardTitle>Recent evaluation runs</CardTitle>
          <CardDescription>Every run below can be reopened to inspect its full attack → evaluate → adapt journey</CardDescription>
        </CardHeader>
        <CardContent className="space-y-1">
          {runs?.slice(0, 5).map(run => <Link key={run.id} to={`/runs/${run.id}/results`} className="flex items-center justify-between gap-3 rounded-2xl px-3 py-2.5 text-sm transition-colors hover:bg-muted">
              <span className="font-medium text-foreground">{run.id}</span>
              <span className="hidden flex-1 truncate text-muted-foreground sm:block">{run.objective}</span>
              <span className="tabular-nums text-muted-foreground">
                {run.hasEvaluation ? `${run.detectionRateAfter.toFixed(1)}% detection` : "not evaluated"}
              </span>
              <RunStatusBadge status={run.status} />
            </Link>)}
        </CardContent>
      </Card>
    </div>;
}
