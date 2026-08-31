import { useMemo } from "react";
import { CrosshairIcon, ServerIcon, ShieldIcon, SkullIcon } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useEvaluationCases } from "@/hooks/useEvaluations";
import { getAttackById } from "@/data/attackCatalog";
import { ATTACK_CATEGORY_LABEL } from "@/types";

const MAX_LANES = 6;
const MAX_PER_LANE = 3;
const LANE_TOP_PAD = 12;
const LANE_BOTTOM_PAD = 10;

function buildLanes(cases) {
  const byCategory = new Map();
  for (const c of cases) {
    const attack = getAttackById(c.attackFamilyId);
    const category = attack?.category ?? "transaction";
    if (!byCategory.has(category)) byCategory.set(category, []);
    const bucket = byCategory.get(category);
    if (bucket.length < MAX_PER_LANE) bucket.push({ ...c, category, severity: attack?.severity });
  }
  return [...byCategory.entries()].slice(0, MAX_LANES).map(([category, items]) => ({ category, items }));
}

function TooltipRow({ label, value }) {
  return (
    <div className="flex w-full items-start justify-between gap-3 py-0.5 text-xs">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-foreground">{value}</span>
    </div>
  );
}

function AttackDot({ c, laneTopPct, index }) {
  const detected = c.detected;
  const duration = 5.5 + (index % 4) * 0.9;
  const delay = (index * 1.7) % duration;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={c.attackName}
          className={cn(
            "group absolute z-10 size-3.5 rounded-full ring-2 hover:z-20 hover:ring-4 hover:brightness-125 hover:[animation-play-state:paused]",
            detected ? "ring-destructive/40 bg-destructive" : "ring-amber-500/40 bg-amber-500",
          )}
          style={{
            top: `${laneTopPct}%`,
            left: "6%",
            animationName: detected ? "attack-travel-block" : "attack-travel-pass",
            animationDuration: `${duration}s`,
            animationDelay: `${delay}s`,
            animationIterationCount: "infinite",
            animationTimingFunction: "linear",
          }}
        />
      </TooltipTrigger>
      <TooltipContent side="top" className="block w-64 max-w-64 rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg">
        <p className="mb-1.5 text-xs font-semibold text-foreground">{c.attackName}</p>
        <div className="flex w-full flex-col gap-0.5">
          <TooltipRow label="Category" value={ATTACK_CATEGORY_LABEL[c.category] ?? c.category} />
          <TooltipRow label="Severity" value={c.severity ?? "—"} />
          <TooltipRow label="Signals" value={`${c.modelSignals.filter((s) => s.triggered).length}/${c.modelSignals.length} triggered`} />
          <TooltipRow label="Risk score" value={`${(c.fusedRiskScore * 100).toFixed(0)}%`} />
        </div>
        <p className={cn("mt-1.5 text-[11px] font-semibold", detected ? "text-destructive" : "text-amber-600 dark:text-amber-400")}>
          {detected ? "✕ Blocked at the Blue Team boundary" : "⚠ Slipped past defenses — reached the system"}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}

export function AttackSimulationCanvas({ run }) {
  const { data: cases } = useEvaluationCases(run.id, 30);
  const lanes = useMemo(() => (cases ? buildLanes(cases) : []), [cases]);

  const laneCount = lanes.length || 1;
  const laneStep = (100 - LANE_TOP_PAD - LANE_BOTTOM_PAD) / Math.max(laneCount - 1, 1);

  let dotIndex = 0;

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle>Live attack simulation</CardTitle>
        <CardDescription>
          {run.id} · every dot is a real attack case — red is blocked at the Blue Team boundary, amber slips through. Hover any dot.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="relative h-[300px] w-full overflow-hidden rounded-2xl border bg-gradient-to-r from-destructive/5 via-transparent to-primary/5">
          {/* Column labels */}
          <div className="absolute top-2 left-3 flex items-center gap-1.5 text-[10px] font-semibold tracking-wide text-destructive uppercase">
            <CrosshairIcon className="size-3" /> Red Team
          </div>
          <div className="absolute top-2 left-1/2 flex -translate-x-1/2 items-center gap-1.5 text-[10px] font-semibold tracking-wide text-blue-600 uppercase dark:text-blue-400">
            <ShieldIcon className="size-3" /> Blue Team Defense
          </div>
          <div className="absolute top-2 right-3 flex items-center gap-1.5 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
            <ServerIcon className="size-3" /> System
          </div>

          {/* Boundary line */}
          <div className="absolute top-8 bottom-3 left-1/2 w-px -translate-x-1/2 border-l border-dashed border-blue-500/40" />

          {/* Lanes */}
          {lanes.map((lane, li) => {
            const topPct = LANE_TOP_PAD + li * laneStep + 6;
            return (
              <div key={lane.category} className="absolute inset-x-0" style={{ top: `${topPct}%` }}>
                <div className="absolute inset-x-[6%] h-px bg-border/50" />
                <span className="absolute left-[6%] -translate-y-[calc(100%+4px)] truncate text-[9px] font-medium text-muted-foreground/70 uppercase">
                  {ATTACK_CATEGORY_LABEL[lane.category] ?? lane.category}
                </span>
              </div>
            );
          })}

          {/* Attacker + system icons per lane */}
          {lanes.map((lane, li) => {
            const topPct = LANE_TOP_PAD + li * laneStep + 6;
            return (
              <div key={`icons-${lane.category}`}>
                <SkullIcon
                  className="absolute size-3.5 -translate-x-1/2 -translate-y-1/2 text-destructive/70"
                  style={{ top: `${topPct}%`, left: "3%" }}
                />
                <ServerIcon
                  className="absolute size-3.5 -translate-x-1/2 -translate-y-1/2 text-muted-foreground/70"
                  style={{ top: `${topPct}%`, left: "97%" }}
                />
              </div>
            );
          })}

          {/* Dots */}
          {lanes.map((lane, li) => {
            const topPct = LANE_TOP_PAD + li * laneStep + 6;
            return lane.items.map((c) => {
              const el = <AttackDot key={c.id} c={c} laneTopPct={topPct} index={dotIndex} />;
              dotIndex += 1;
              return el;
            });
          })}

          {!cases && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
              Loading simulation…
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
