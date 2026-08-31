import { useMemo } from "react";
import { CrosshairIcon, ServerIcon, ShieldIcon } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { FAMILY_LABEL, OUTCOME_META } from "@/services/api/liveCases";

// Every visual property of every dot is derived from the case's real id,
// its real outcome and its real fused risk score. Nothing here is random:
// two renders of the same real case produce the identical dot, which is
// what makes the animation reproducible evidence rather than decoration.
function hashOf(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i += 1) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

const OUTCOME_STYLE = {
  blocked: {
    animation: "stream-blocked",
    dot: "bg-emerald-500 ring-emerald-400/30",
    glow: "0 0 6px 0 rgb(16 185 129 / 0.55)",
    text: "text-emerald-600 dark:text-emerald-400",
  },
  missed: {
    animation: "stream-missed",
    dot: "bg-red-500 ring-red-400/40",
    glow: "0 0 7px 0 rgb(239 68 68 / 0.7)",
    text: "text-red-600 dark:text-red-400",
  },
  false_positive: {
    animation: "stream-false-positive",
    dot: "bg-amber-500 ring-amber-400/30",
    glow: "0 0 6px 0 rgb(245 158 11 / 0.5)",
    text: "text-amber-600 dark:text-amber-400",
  },
  cleared: {
    animation: "stream-cleared",
    dot: "bg-slate-400/70 ring-slate-400/20 dark:bg-slate-500/70",
    glow: "none",
    text: "text-muted-foreground",
  },
};

const LANE_TOP_PAD = 18;
const LANE_BOTTOM_PAD = 12;

function StreamDot({ row, topPct, index, speed }) {
  const style = OUTCOME_STYLE[row.outcome] ?? OUTCOME_STYLE.cleared;
  const h = hashOf(row.id ?? row.caseId ?? String(index));
  // Higher real risk score => faster approach. A 4.2s..9s spread keeps
  // lanes legible without any lane ever going empty.
  const risk = Math.min(100, Math.max(0, row.riskScore)) / 100;
  const duration = (9 - risk * 3.4) / speed;
  const delay = ((h % 1000) / 1000) * duration;
  const size = row.outcome === "cleared" ? "size-2" : "size-2.5";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={`${row.familyLabel} — ${OUTCOME_META[row.outcome].label}`}
          className={cn(
            "attack-dot group absolute z-10 rounded-full ring-2 hover:z-30 hover:ring-4",
            size,
            style.dot,
          )}
          style={{
            top: `${topPct}%`,
            left: `${6 + (index % 7) * 6}%`,
            boxShadow: style.glow,
            animationName: style.animation,
            animationDuration: `${duration.toFixed(2)}s`,
            animationDelay: `-${delay.toFixed(2)}s`,
          }}
        />
      </TooltipTrigger>
      <TooltipContent
        side="top"
        className="block w-72 max-w-72 rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg"
      >
        <p className="mb-0.5 text-xs font-semibold">{row.familyLabel}</p>
        <p className="mb-2 font-mono text-[10px] break-all text-muted-foreground">{row.caseId}</p>
        <dl className="space-y-0.5 text-[11px]">
          <Row label="Ground truth" value={row.actualLabel === "fraud" ? "Fraudulent" : "Legitimate"} />
          <Row label="Decision" value={String(row.decision ?? "—").toUpperCase()} />
          <Row label="Fused risk" value={`${row.riskScore.toFixed(1)} / 100`} />
          {row.splitPortion ? <Row label="Split" value={row.splitPortion} /> : null}
          {row.modelSignals.slice(0, 4).map((s) => (
            <Row
              key={s.model}
              label={s.model}
              value={s.score === null ? "—" : s.score.toFixed(3)}
            />
          ))}
        </dl>
        {row.evidence.length > 0 && (
          <p className="mt-1.5 border-t pt-1.5 font-mono text-[10px] break-words text-muted-foreground">
            {row.evidence.slice(0, 2).join(" · ")}
          </p>
        )}
        <p className={cn("mt-1.5 text-[11px] font-semibold", style.text)}>
          {OUTCOME_META[row.outcome].label} — {OUTCOME_META[row.outcome].blurb}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium tabular-nums">{value}</dd>
    </div>
  );
}

export function AttackStream({ cases = [], live = false, speed = 1, height = 420 }) {
  const lanes = useMemo(() => {
    const byFamily = new Map();
    for (const row of cases) {
      if (!byFamily.has(row.family)) byFamily.set(row.family, []);
      byFamily.get(row.family).push(row);
    }
    return [...byFamily.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([family, items]) => ({ family, items: items.slice(0, 9) }));
  }, [cases]);

  const laneCount = Math.max(lanes.length, 1);
  const laneStep = (100 - LANE_TOP_PAD - LANE_BOTTOM_PAD) / Math.max(laneCount - 1, 1);

  return (
    <div
      className="relative w-full overflow-hidden rounded-3xl border bg-card"
      style={{ height }}
    >
      <div className="absolute inset-0 bg-gradient-to-r from-red-500/5 via-transparent to-blue-500/5" />

      {/* Column headers -- a 3-column grid, not three absolutely-positioned
          labels: at narrow widths absolute centring made "Blue Team Defense"
          overlap "Payment System". The long words drop below 640px. */}
      <div className="absolute inset-x-3 top-3 grid grid-cols-3 items-center text-[10px] font-semibold tracking-[0.14em] uppercase">
        <span className="flex items-center gap-1.5 text-red-600 dark:text-red-400">
          <CrosshairIcon className="size-3.5 shrink-0" />
          <span className="truncate">Red<span className="hidden sm:inline"> Team</span></span>
        </span>
        <span className="flex items-center justify-center gap-1.5 text-blue-600 dark:text-blue-400">
          <ShieldIcon className="size-3.5 shrink-0" />
          <span className="truncate">Blue Team<span className="hidden sm:inline"> Defense</span></span>
        </span>
        <span className="flex items-center justify-end gap-1.5 text-muted-foreground">
          <ServerIcon className="size-3.5 shrink-0" />
          <span className="truncate"><span className="hidden sm:inline">Payment </span>System</span>
        </span>
      </div>

      {/* Defense boundary */}
      <div
        className={cn(
          "absolute top-10 bottom-4 left-1/2 w-px -translate-x-1/2 bg-gradient-to-b from-transparent via-blue-500/70 to-transparent",
          live && "shield-line",
        )}
      />
      {live && (
        <div className="pointer-events-none absolute top-10 bottom-4 left-1/2 w-16 -translate-x-1/2 overflow-hidden">
          <div className="shield-sweep h-1/3 w-full bg-gradient-to-b from-transparent via-blue-400/25 to-transparent" />
        </div>
      )}

      {/* Lanes */}
      {lanes.map((lane, li) => {
        const topPct = LANE_TOP_PAD + li * laneStep;
        return (
          <div key={lane.family}>
            <div
              className="absolute inset-x-[5%] h-px bg-border/60"
              style={{ top: `${topPct}%` }}
            />
            <span
              className="absolute left-[5%] rounded bg-card/85 px-1 py-px text-[9px] font-medium tracking-wide text-muted-foreground uppercase backdrop-blur-[1px]"
              style={{ top: `calc(${topPct}% - 17px)` }}
            >
              {FAMILY_LABEL[lane.family] ?? lane.family}
              <span className="ml-1.5 tabular-nums opacity-60">{lane.items.length}</span>
            </span>
          </div>
        );
      })}

      {/* Dots */}
      {lanes.map((lane, li) => {
        const topPct = LANE_TOP_PAD + li * laneStep;
        return lane.items.map((row, i) => (
          <StreamDot
            key={row.id}
            row={row}
            topPct={topPct}
            index={li * 13 + i}
            speed={speed}
          />
        ));
      })}

      {lanes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center px-8 text-center text-sm text-muted-foreground">
          No scored cases in Supabase yet — run the evaluation harness
          (<code className="font-mono text-xs">python evaluation/run_all_evaluations.py</code>)
          to populate <code className="font-mono text-xs">evaluation_results</code>.
        </div>
      )}
    </div>
  );
}

export function StreamLegend({ counts }) {
  const order = ["blocked", "missed", "false_positive", "cleared"];
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
      {order.map((key) => (
        <span key={key} className="flex items-center gap-1.5">
          <span
            className={cn("size-2.5 rounded-full ring-2", OUTCOME_STYLE[key].dot)}
            style={{ boxShadow: OUTCOME_STYLE[key].glow }}
          />
          <span className="text-muted-foreground">{OUTCOME_META[key].label}</span>
          {counts?.[key] !== undefined && (
            <span className="font-semibold tabular-nums">{counts[key].toLocaleString()}</span>
          )}
        </span>
      ))}
    </div>
  );
}
