import { Link, useParams } from "react-router-dom";
import { CheckCircle2Icon, TriangleAlertIcon, ZapIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { SeverityBadge } from "@/components/shared/badges";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { cn } from "@/lib/utils";
import { useWeaknesses } from "@/hooks/useEvaluations";
import { ATTACK_CATEGORY_LABEL } from "@/types";

// A card is a weakness only when the family actually let an attack
// through. agent_runner.py's _build_weaknesses() now tags each entry
// kind: "weakness" | "clean" for exactly this reason -- this page used to
// render every entry as "Defense weakness detected", so a family with a
// 100% detection rate and a 0% miss rate was headlined as a High-severity
// weakness whose stated reason was "Lowest real recall this run (1.0000)".
// Entries written before that change carry no `kind`, so fall back to the
// only thing that actually decides it: did anything get missed.
function kindOf(w) {
  return w.kind ?? (w.missRate > 0 ? "weakness" : "clean");
}

// Rows written before agent_runner.py's _build_weaknesses() fix carry no
// `kind`, and when they describe a family that missed nothing their stored
// reason text is the known-bad output of the old code ("Lowest real recall
// this run (1.0000)...", recommending an adaptive round against a family
// with a 0% miss rate). Those strings are wrong on their face, so this
// page does not repeat them -- it says plainly that the run predates the
// fix rather than either printing nonsense or silently inventing better
// text and passing it off as the orchestrator's own. Re-running the
// pipeline regenerates them correctly.
function isLegacyCleanRow(w) {
  return w.kind === undefined && w.missRate === 0;
}

function WeaknessCard({ w }) {
  const kind = kindOf(w);
  const isWeakness = kind === "weakness";
  const legacy = isLegacyCleanRow(w);

  return (
    <Card className={cn(isWeakness ? "border-destructive/20" : "border-primary/20")}>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          {isWeakness ? (
            <TriangleAlertIcon className="size-4 shrink-0 text-destructive" />
          ) : (
            <CheckCircle2Icon className="size-4 shrink-0 text-primary" />
          )}
          <CardTitle className="text-base">
            {isWeakness ? "Defense weakness detected" : "No misses this run"} — {w.label}
          </CardTitle>
          {isWeakness ? <SeverityBadge severity={w.severity} /> : null}
        </div>
        <CardDescription>{ATTACK_CATEGORY_LABEL[w.category] ?? w.category}</CardDescription>
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
              <span
                className={cn(
                  "font-medium tabular-nums",
                  w.missRate > 0 ? "text-destructive" : "text-muted-foreground",
                )}
              >
                {w.missRate}%
              </span>
            </div>
            <Progress value={w.missRate} className="[&>div]:bg-destructive" />
          </div>
        </div>

        <div className="space-y-1.5">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {isWeakness ? "Why the defense misses this" : "What this result actually means"}
          </p>
          {legacy ? (
            <p className="text-sm text-muted-foreground">
              This family missed nothing, so there is no gap to explain. The stored explanation for this run
              was written by an earlier version of the orchestrator that labelled a 100% detection rate as a
              weakness; it is suppressed here rather than repeated. Re-run the pipeline to regenerate it.
            </p>
          ) : (
            <ul className="space-y-1 text-sm text-foreground">
              {w.reasons.map((r) => (
                <li key={r} className="flex gap-2">
                  <span className="text-muted-foreground">·</span>
                  {r}
                </li>
              ))}
            </ul>
          )}
        </div>

        {!legacy && (
          <div className="rounded-2xl bg-muted/60 px-4 py-2.5 text-sm text-foreground">
            <span className="font-medium">Recommended: </span>
            {w.recommendedAction}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function WeaknessAnalysisPage() {
  const { runId = "" } = useParams();
  const { data: weaknesses, isLoading } = useWeaknesses(runId);

  const entries = weaknesses ?? [];
  const real = entries.filter((w) => kindOf(w) === "weakness");
  const clean = entries.filter((w) => kindOf(w) !== "weakness");

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Blue Team"
        title="Weakness analysis"
        description={`Where ${runId || "this run"}'s defense actually let attacks through — and, separately, where it missed nothing.`}
        actions={
          <Button asChild>
            <Link to={`/runs/${runId}/mutation`}>
              <ZapIcon className="size-4" />
              Generate Adaptive Attacks
            </Link>
          </Button>
        }
      />

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-44 w-full" />
          <Skeleton className="h-44 w-full" />
        </div>
      ) : entries.length === 0 ? (
        <EmptyState
          icon={<TriangleAlertIcon className="size-10" />}
          title="No weakness data for this run"
          description="The evaluation stage writes these cards from real per-family recall in metrics.json. If the run hasn't reached that stage, or metrics.json has no entry for the scope it ran, there is nothing real to show here yet."
        />
      ) : (
        <div className="space-y-4">
          {real.length === 0 && (
            <Alert>
              <CheckCircle2Icon className="size-4" />
              <AlertTitle>Nothing was missed in this run&apos;s scope</AlertTitle>
              <AlertDescription>
                Every family scored here caught every attack. That is a real result, not a weakness — and it is
                more likely to mean the generated attacks were too easily separated than that the defense is
                flawless. The honest next step is harder attacks, not a defense fix. The system&apos;s genuine
                weak points live in the modalities this run did not score — see Model performance for the
                per-model numbers and their sample sizes.
              </AlertDescription>
            </Alert>
          )}
          {real.map((w) => (
            <WeaknessCard key={w.id} w={w} />
          ))}
          {clean.map((w) => (
            <WeaknessCard key={w.id} w={w} />
          ))}
        </div>
      )}
    </div>
  );
}
