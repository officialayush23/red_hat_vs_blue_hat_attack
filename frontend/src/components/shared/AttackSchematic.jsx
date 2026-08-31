import { ArrowRightIcon, CompassIcon, RefreshCwIcon, SearchIcon, ShieldIcon } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DecisionBadge } from "@/components/shared/badges";
import { cn } from "@/lib/utils";
import { useEvaluationCases, useMutationIterations, useWeaknesses } from "@/hooks/useEvaluations";
import { ATTACK_CATEGORY_LABEL } from "@/types";

const TONE = {
  red: {
    ring: "border-destructive/30 bg-destructive/10 text-destructive",
    dot: "bg-destructive",
  },
  blue: {
    ring: "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400",
    dot: "bg-blue-500",
  },
  amber: {
    ring: "border-[color-mix(in_oklch,var(--secondary-foreground),white_10%)]/30 bg-secondary text-secondary-foreground",
    dot: "bg-secondary-foreground/70",
  },
};

function SchematicNode({ icon: Icon, tone, kicker, title, detail, tooltip }) {
  const t = TONE[tone];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            "group flex w-full flex-col items-start gap-1 rounded-2xl border px-4 py-3 text-left transition-transform hover:-translate-y-0.5 hover:shadow-sm",
            t.ring,
          )}
        >
          <span className="flex items-center gap-1.5 text-[10px] font-semibold tracking-wide uppercase opacity-80">
            <span className={cn("size-1.5 shrink-0 rounded-full", t.dot)} />
            {kicker}
          </span>
          <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            <Icon className="size-3.5 shrink-0" />
            {title}
          </span>
          <span className="line-clamp-2 text-xs text-muted-foreground">{detail}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="block w-72 max-w-72 rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg">
        <div className="flex w-full flex-col gap-0.5">{tooltip}</div>
      </TooltipContent>
    </Tooltip>
  );
}

function TooltipRow({ label, value }) {
  return (
    <div className="flex w-full items-start justify-between gap-3 py-0.5 text-xs">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-foreground">{value}</span>
    </div>
  );
}

function CaseChip({ c }) {
  const triggered = c.modelSignals.filter((s) => s.triggered).length;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex flex-col items-start gap-1 rounded-xl border px-3 py-2 text-left text-xs transition-colors hover:bg-muted",
            c.detected ? "border-border" : "border-destructive/40 bg-destructive/5",
          )}
        >
          <span className="flex w-full items-center justify-between gap-2">
            <span className="truncate font-medium text-foreground">{c.attackName}</span>
            <DecisionBadge decision={c.decision} />
          </span>
          <span className="text-muted-foreground">
            {triggered}/{c.modelSignals.length} signals · risk {(c.fusedRiskScore * 100).toFixed(0)}%
          </span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="block w-64 max-w-64 rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg">
        <p className="mb-1.5 text-xs font-semibold text-foreground">{c.attackName}</p>
        <div className="space-y-1 border-b pb-1.5">
          {c.modelSignals.map((s) => (
            <div key={s.model} className="flex items-center justify-between gap-3 text-[11px]">
              <span className={cn("truncate", s.triggered ? "text-foreground" : "text-muted-foreground")}>{s.model}</span>
              <span className={cn("tabular-nums", s.triggered ? "font-medium text-destructive" : "text-muted-foreground")}>
                {s.score.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-1.5 text-[11px] text-muted-foreground">{c.evidence[c.evidence.length - 1]}</p>
        <p className={cn("mt-1 text-[11px] font-semibold", c.detected ? "text-primary" : "text-destructive")}>
          {c.detected ? "Caught by the Blue Team" : "Missed — fed back into adaptation"}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}

export function AttackSchematic({ run }) {
  const { data: cases } = useEvaluationCases(run.id, 6);
  const { data: weaknesses } = useWeaknesses(run.id);
  const { data: mutations } = useMutationIterations(run.id);

  const sample = cases?.[0];
  const weakest = weaknesses?.[0];
  const nextIteration = mutations?.[mutations.length - 1];
  const missed = cases?.filter((c) => !c.detected) ?? [];

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle>Live attack ↔ defense schematic</CardTitle>
        <CardDescription>{run.id} · hover any stage to see what actually happened</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-stretch gap-2 lg:flex-row lg:items-center">
          <div className="lg:flex-1">
            <SchematicNode
              icon={CompassIcon}
              tone="red"
              kicker="Red Team"
              title="Attack Generation"
              detail={sample ? sample.attackName : "Generating adversarial scenarios…"}
              tooltip={
                <>
                  <p className="mb-1.5 text-xs font-semibold text-foreground">Goal: {run.objective}</p>
                  <TooltipRow label="Scope" value={run.scope.map((c) => ATTACK_CATEGORY_LABEL[c]).join(", ")} />
                  <TooltipRow label="Scenarios this run" value={run.scenarioCount.toLocaleString()} />
                  <TooltipRow label="Technique" value="CTGAN · TimeGAN · mutation" />
                  {sample && <TooltipRow label="Sample scenario" value={sample.attackName} />}
                </>
              }
            />
          </div>
          <ArrowRightIcon className="mx-auto size-4 shrink-0 rotate-90 text-muted-foreground/40 lg:rotate-0" />
          <div className="lg:flex-1">
            <SchematicNode
              icon={ShieldIcon}
              tone="blue"
              kicker="Blue Team"
              title="Multimodal Detection"
              detail={`${run.attacksCaught.toLocaleString()} caught · ${run.attacksMissed.toLocaleString()} missed`}
              tooltip={
                <>
                  <p className="mb-1.5 text-xs font-semibold text-foreground">Per-modality specialist models</p>
                  {sample?.modelSignals.map((s) => (
                    <TooltipRow key={s.model} label={s.model} value={s.triggered ? `▲ ${s.score.toFixed(2)}` : "—"} />
                  ))}
                  <TooltipRow label="Fused decision" value={sample?.decision.toUpperCase() ?? "—"} />
                </>
              }
            />
          </div>
          <ArrowRightIcon className="mx-auto size-4 shrink-0 rotate-90 text-muted-foreground/40 lg:rotate-0" />
          <div className="lg:flex-1">
            <SchematicNode
              icon={SearchIcon}
              tone="amber"
              kicker="Evaluation Agent"
              title="Weakness Found"
              detail={weakest ? weakest.label : "Scoring detection coverage…"}
              tooltip={
                <>
                  <p className="mb-1.5 text-xs font-semibold text-foreground">
                    {weakest ? weakest.label : "Evaluating"} — {weakest?.missRate ?? 0}% miss rate
                  </p>
                  {weakest?.reasons.map((r) => (
                    <p key={r} className="py-0.5 text-[11px] text-muted-foreground">
                      • {r}
                    </p>
                  ))}
                </>
              }
            />
          </div>
          <ArrowRightIcon className="mx-auto size-4 shrink-0 rotate-90 text-muted-foreground/40 lg:rotate-0" />
          <div className="lg:flex-1">
            <SchematicNode
              icon={RefreshCwIcon}
              tone="amber"
              kicker="Adaptation Agent"
              title="Next Strategy"
              detail={nextIteration ? nextIteration.changes[0] : "Selecting harder variant…"}
              tooltip={
                <>
                  <p className="mb-1.5 text-xs font-semibold text-foreground">Harder follow-up scenario</p>
                  {nextIteration?.changes.map((c) => (
                    <p key={c} className="py-0.5 text-[11px] text-muted-foreground">
                      • {c}
                    </p>
                  ))}
                  <p className="mt-1.5 text-[11px] font-semibold text-primary">↺ Sent back to Attack Generation</p>
                </>
              }
            />
          </div>
        </div>

        <p className="mt-2 text-center text-[11px] text-muted-foreground lg:text-right">
          ↺ every missed attack loops back into Attack Generation, harder than before
        </p>

        {cases && (
          <div className="mt-5 border-t pt-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-semibold text-foreground">This run's attack cases — hover for evidence</p>
              {missed.length > 0 && (
                <span className="text-[11px] text-destructive">{missed.length} missed, feeding the next iteration</span>
              )}
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {cases.map((c) => (
                <CaseChip key={c.id} c={c} />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
