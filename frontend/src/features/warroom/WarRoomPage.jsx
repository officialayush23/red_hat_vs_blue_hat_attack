import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ActivityIcon,
  ArrowLeftIcon,
  GaugeIcon,
  LoaderCircleIcon,
  RadioIcon,
  ZapIcon,
} from "lucide-react";
import { AttackStream, StreamLegend } from "@/components/warroom/AttackStream";
import { ResizeHandle } from "@/components/shared/ResizablePanel";
import { useResizablePanel } from "@/hooks/useResizablePanel";
import { AgentStepList } from "@/components/shared/AgentStepList";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useRun } from "@/hooks/useRuns";
import { useAgentSteps } from "@/hooks/useAgentActivity";
import { useApiMode } from "@/hooks/useApiMode";
import { useCorpusStats, useRecentScoredCases, useScoredCases } from "@/hooks/useLiveCases";
import { OUTCOME_META } from "@/services/api/liveCases";

// agent_runner.py reports 8 steps: the 7 planned stages plus the
// data-loader step that pulls this instance's missing dataset bundles
// from Supabase Storage before generation. Used only to render progress
// against a known total, never to fabricate a stage's content.
const TOTAL_STAGES = 8;
const TERMINAL_STATUSES = new Set(["completed", "completed_with_failures", "failed"]);

// Wall-clock duration of the run. While it is in flight this ticks against
// now; once it finishes it is frozen at the real completedAt - createdAt
// the orchestrator recorded (a finished run showing an ever-growing timer
// is just wrong).
function useElapsed(startedAt, finishedAt, running) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running || finishedAt) return undefined;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running, finishedAt]);
  if (!startedAt) return null;
  const end = finishedAt ? new Date(finishedAt).getTime() : now;
  const secs = Math.max(0, Math.floor((end - new Date(startedAt).getTime()) / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function Counter({ label, value, tone, sub }) {
  return (
    <div className="rounded-2xl border bg-card px-3 py-2.5">
      <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">{label}</p>
      <p className={cn("cn-font-heading text-xl font-semibold tabular-nums", tone)}>{value}</p>
      {sub ? <p className="text-[10px] text-muted-foreground">{sub}</p> : null}
    </div>
  );
}

export function WarRoomPage() {
  const { runId = "" } = useParams();
  const { data: run } = useRun(runId);
  const { data: steps } = useAgentSteps(runId);
  const api = useApiMode();

  const status = run?.status;
  const isRunning = Boolean(run) && !TERMINAL_STATUSES.has(status);
  const runningOrWaiting = !run || isRunning;

  const { data: cases } = useScoredCases({ perFamily: 8, live: runningOrWaiting });
  const { data: recent } = useRecentScoredCases(24, runningOrWaiting);
  const { data: stats } = useCorpusStats(runningOrWaiting);

  const stepCount = steps?.length ?? 0;
  const progressPct = Math.min(100, Math.round((stepCount / TOTAL_STAGES) * 100));
  const currentStep = steps?.find((s) => s.status === "running") ?? steps?.[stepCount - 1];
  const elapsed = useElapsed(run?.createdAt, run?.completedAt, isRunning);

  // 380px was the old hard-coded rail. Kept as the default so nobody's layout
  // changes until they drag it; the bounds stop the stream or the rail being
  // dragged down to a useless sliver.
  const {
    containerRef: railRef,
    containerStyle: railStyle,
    handleProps: railHandleProps,
  } = useResizablePanel({
    storageKey: "fraudshield.warroom.railWidth",
    cssVar: "--warroom-rail",
    defaultWidth: 380,
    minWidth: 300,
    // 640 was too narrow for the widest thing the rail actually has to show:
    // Threat Research's RESULT line enumerates every family's train/held-out
    // combinations and their dimension lists, and it ran off the right edge
    // with the handle already at its maximum. A cap you cannot drag past is
    // not a resizable panel.
    maxWidth: 900,
    side: "right",
  });

  const laneCounts = useMemo(() => {
    const c = { blocked: 0, missed: 0, cleared: 0, false_positive: 0 };
    for (const row of cases ?? []) c[row.outcome] += 1;
    return c;
  }, [cases]);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* ---- Command bar ---- */}
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b px-4 py-3 md:px-6">
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link to="/runs">
            <ArrowLeftIcon className="size-4" /> Runs
          </Link>
        </Button>
        <Separator orientation="vertical" className="hidden h-6 md:block" />
        <div className="min-w-0 flex-1 basis-48">
          <p className="truncate text-[10px] font-semibold tracking-[0.14em] text-muted-foreground uppercase">
            Adversarial war room
          </p>
          <p className="truncate text-sm font-medium">
            {run?.objective || "Waiting for the orchestrator to register this run…"}
          </p>
        </div>

        <Badge
          variant="outline"
          className={cn(
            "gap-1.5 border-transparent",
            api.live ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-muted text-muted-foreground",
          )}
        >
          <RadioIcon className={cn("size-3.5", api.live && "animate-pulse")} />
          {api.live ? "Backend live" : "Replay mode"}
        </Badge>

        {run ? (
          <Badge
            variant="outline"
            className={cn(
              "gap-1.5 border-transparent capitalize",
              status === "completed" && "bg-primary/10 text-primary",
              status === "failed" && "bg-destructive/10 text-destructive",
              isRunning && "bg-amber-500/10 text-amber-600 dark:text-amber-400",
            )}
          >
            {isRunning ? <LoaderCircleIcon className="size-3.5 animate-spin" /> : <ActivityIcon className="size-3.5" />}
            {status}
            {elapsed ? <span className="font-mono tabular-nums">· {elapsed}</span> : null}
          </Badge>
        ) : null}

        <span className="hidden font-mono text-[11px] text-muted-foreground lg:inline">{runId}</span>
      </header>

      {/* ---- Main grid ----
           The agent rail used to be a hard 380px. On a 1280px laptop that left
           the attack stream barely wider than the rail; on an ultrawide it was
           a ribbon against acres of empty chart. The width is a real preference
           now, driven by a CSS custom property so dragging it does not
           re-render the stream on every pointermove. Below xl the layout stacks
           and the variable is simply unused. */}
      <div
        ref={railRef}
        style={railStyle}
        className="grid flex-1 gap-4 p-4 md:p-6 xl:grid-cols-[minmax(0,1fr)_auto_var(--warroom-rail)] xl:gap-0 xl:gap-y-4"
      >
        <div className="flex min-w-0 flex-col gap-4 xl:pr-4">
          <AttackStream cases={cases ?? []} live={runningOrWaiting} height={460} />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <StreamLegend counts={laneCounts} />
            {/* The legend counts the dots ON THIS CANVAS -- a recent sample,
                not the corpus. The counters below are exact counts over every
                row. Saying so stops the two being read as the same number. */}
            <p className="text-[11px] text-muted-foreground">
              Every dot is a real row from Supabase&apos;s <code className="font-mono">evaluation_results</code> —
              real fused risk score, real decision, real ground truth. Hover any dot for its evidence.
              The legend counts this sample; the totals below cover the whole corpus.
            </p>
          </div>

          {/* Corpus-wide real counters */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {/* "Detected", not "blocked". `detected` is correctness at each
                detector's own calibrated threshold; `decision` is the 0-100
                band fusion.py assigns. They diverge -- thousands of fraud rows
                are detected=true with decision='approve' -- so the block rate
                is stated separately rather than the detection rate being shown
                under the word "blocked". */}
            <Counter
              label="Attacks detected"
              value={(stats?.fraudDetected ?? 0).toLocaleString()}
              tone="text-emerald-600 dark:text-emerald-400"
              sub={
                stats
                  ? `${stats.detectionPct.toFixed(1)}% of scored fraud results — ` +
                    `${stats.fraudBlockedOutright.toLocaleString()} blocked outright (${stats.blockedPct.toFixed(1)}%)`
                  : undefined
              }
            />
            <Counter
              label="Attacks missed"
              value={(stats?.fraudMissed ?? 0).toLocaleString()}
              tone="text-red-600 dark:text-red-400"
              sub="reached the system"
            />
            <Counter
              label="False positives"
              value={(stats?.falsePositives ?? 0).toLocaleString()}
              tone="text-amber-600 dark:text-amber-400"
              sub={stats ? `${stats.falsePositivePct.toFixed(1)}% of scored legitimate samples` : undefined}
            />
            {/* "Scored results", not "cases": evaluation_results holds one
                row per (case, evaluation run), so a case scored by three
                evidence-gate runs is three rows. Labelling a row count as a
                case count would inflate the corpus by ~2x. The distinct
                case count is the sub-line, from attack_cases. */}
            <Counter
              label="Scored results"
              value={(stats?.scoredCases ?? 0).toLocaleString()}
              tone="text-foreground"
              sub={stats ? `over ${stats.attackCases.toLocaleString()} generated attack cases` : undefined}
            />
          </div>

          {/* Live ticker of the most recently scored real cases */}
          <div className="rounded-2xl border">
            <div className="flex items-center gap-2 border-b px-3 py-2">
              <GaugeIcon className="size-3.5 text-muted-foreground" />
              <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                Most recently scored cases
              </p>
            </div>
            <ScrollArea className="h-44">
              <ul className="divide-y">
                {(recent ?? []).map((row) => (
                  <li key={row.id} className="flex items-center gap-3 px-3 py-1.5 text-xs">
                    <span className="hidden w-40 shrink-0 truncate font-mono text-[10px] text-muted-foreground lg:inline">
                      {row.caseId}
                    </span>
                    <span className="min-w-0 flex-1 truncate">{row.familyLabel}</span>
                    <span className="w-14 shrink-0 text-right font-medium tabular-nums">
                      {row.riskScore === null ? "—" : row.riskScore.toFixed(1)}
                    </span>
                    <span className="hidden w-20 shrink-0 text-right text-muted-foreground uppercase sm:inline">
                      {row.decision}
                    </span>
                    <span
                      className={cn(
                        "w-24 shrink-0 text-right font-medium",
                        row.outcome === "blocked" && "text-emerald-600 dark:text-emerald-400",
                        row.outcome === "missed" && "text-red-600 dark:text-red-400",
                        row.outcome === "false_positive" && "text-amber-600 dark:text-amber-400",
                        row.outcome === "cleared" && "text-muted-foreground",
                      )}
                    >
                      {OUTCOME_META[row.outcome].label}
                    </span>
                  </li>
                ))}
                {!recent?.length && (
                  <li className="px-3 py-6 text-center text-xs text-muted-foreground">
                    No scored cases yet.
                  </li>
                )}
              </ul>
            </ScrollArea>
          </div>
        </div>

        <ResizeHandle {...railHandleProps} label="Resize the agent rail" />

        {/* ---- Agent rail ---- */}
        <aside className="flex min-w-0 flex-col gap-4 xl:pl-4">
          <div className="rounded-2xl border p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                Orchestrator progress
              </p>
              <span className="text-xs tabular-nums text-muted-foreground">
                {stepCount} / {TOTAL_STAGES}
              </span>
            </div>
            <Progress value={progressPct} />
            {currentStep ? (
              <p className="mt-3 flex items-start gap-2 text-xs text-muted-foreground">
                <ZapIcon className={cn("mt-0.5 size-3.5 shrink-0 text-primary", isRunning && "animate-pulse")} />
                <span className="min-w-0">{currentStep.detail}</span>
              </p>
            ) : (
              <p className="mt-3 text-xs text-muted-foreground">
                Waiting for the first real stage to report in…
              </p>
            )}
          </div>

          <div className="flex min-h-0 flex-1 flex-col rounded-2xl border">
            <div className="border-b px-3 py-2">
              <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                Agent decision trace
              </p>
            </div>
            <ScrollArea className="h-[420px] px-1 py-2 xl:h-auto xl:min-h-[320px] xl:flex-1">
              {steps?.length ? (
                <AgentStepList steps={steps} />
              ) : (
                <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                  agent_runner.py writes each stage into Supabase as it starts and completes.
                </p>
              )}
            </ScrollArea>
          </div>

          {run && TERMINAL_STATUSES.has(status) && (
            <div className="grid gap-2">
              <Button asChild className="w-full">
                <Link to={`/runs/${run.id}/weaknesses`}>Review weaknesses found →</Link>
              </Button>
              <Button asChild variant="outline" className="w-full">
                <Link to={`/runs/${run.id}/results`}>Full results</Link>
              </Button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
