import { useState } from "react";
import { useParams } from "react-router-dom";
import { ActivityIcon, ArrowDownIcon, CreditCardIcon, FileTextIcon, MessageSquareIcon, MicIcon, ShareIcon, SparklesIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { DecisionBadge } from "@/components/shared/badges";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useEvaluationCases } from "@/hooks/useEvaluations";
import { MODALITY_LABEL } from "@/types";
const MODALITY_ICON = {
  transaction: CreditCardIcon,
  behavioral: ActivityIcon,
  graph: ShareIcon,
  voice: MicIcon,
  text: MessageSquareIcon,
  anomaly: SparklesIcon,
  document: FileTextIcon
};
export function BlueTeamEvaluationPage() {
  const {
    runId = ""
  } = useParams();
  const {
    data: cases,
    isLoading
  } = useEvaluationCases(runId, 10);
  const [selectedId, setSelectedId] = useState(null);
  const selected = cases?.find(c => c.id === selectedId) ?? cases?.[0];
  return <div className="space-y-6">
      <PageHeader eyebrow="Blue Team" title="Evaluation pipeline" description={`How the defense scores and decides on each adversarial case in ${runId || "this run"} — from the raw case through per-model signals to a fused risk decision.`} />

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <Card className="lg:sticky lg:top-4 lg:self-start">
          <CardHeader>
            <CardTitle className="text-sm">Evaluated cases</CardTitle>
            <CardDescription>Select a case to inspect its decision</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? <div className="space-y-2 p-4">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div> : <ScrollArea className="h-[560px]">
                <div className="space-y-1 p-3">
                  {cases?.map(c => <button key={c.id} onClick={() => setSelectedId(c.id)} className={cn("flex w-full flex-col gap-1 rounded-2xl border px-3 py-2.5 text-left transition-colors", (selected?.id ?? cases[0]?.id) === c.id ? "border-primary/40 bg-primary/5" : "border-transparent hover:bg-muted")}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium text-foreground">{c.attackName}</span>
                        <DecisionBadge decision={c.decision} />
                      </div>
                      <span className="text-xs text-muted-foreground tabular-nums">
                        Fused risk {(c.fusedRiskScore * 100).toFixed(0)}%
                      </span>
                    </button>)}
                </div>
              </ScrollArea>}
          </CardContent>
        </Card>

        <div className="space-y-3">
          {!selected ? <Skeleton className="h-96 w-full" /> : <EvaluationPipeline evalCase={selected} />}
        </div>
      </div>
    </div>;
}
function EvaluationPipeline({
  evalCase
}) {
  return <div className="space-y-3">
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Input case</p>
            <p className="cn-font-heading text-base font-semibold text-foreground">{evalCase.attackName}</p>
            <p className="text-xs text-muted-foreground">{evalCase.id}</p>
          </div>
          <Badge variant="outline" className="border-border text-muted-foreground capitalize">
            Ground truth: {evalCase.actualLabel}
          </Badge>
        </CardContent>
      </Card>

      <PipelineArrow label="Per-modality model signals" />

      <div className="grid gap-3 sm:grid-cols-2">
        {/* No Triggered / Below-threshold badge here any more. The old mock
            invented both the score and the threshold it was compared
            against; real evaluation_results rows carry each detector's raw
            score but not its per-model decision threshold (only the fused
            decision is persisted), so there is no honest way to state
            whether an individual model fired. The real score is shown on
            its own. */}
        {evalCase.modelSignals.map(s => {
        const Icon = MODALITY_ICON[evalCase.category] ?? MODALITY_ICON.transaction;
        return <Card key={s.model}>
              <CardContent className="space-y-2 py-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="flex size-7 shrink-0 items-center justify-center rounded-xl bg-muted">
                      {Icon ? <Icon className="size-3.5 text-muted-foreground" /> : null}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">{s.model}</p>
                      <p className="text-[11px] text-muted-foreground">{MODALITY_LABEL[evalCase.category] ?? evalCase.attackName}</p>
                    </div>
                  </div>
                  <span className="shrink-0 font-medium tabular-nums text-foreground">
                    {s.score === null || s.score === undefined ? "—" : s.score.toFixed(3)}
                  </span>
                </div>
                <Progress value={s.score === null || s.score === undefined ? 0 : Math.min(100, s.score * 100)} />
              </CardContent>
            </Card>;
      })}
      </div>

      <PipelineArrow label="Risk fusion" />

      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="flex flex-col items-center gap-3 py-6 text-center sm:flex-row sm:justify-between sm:text-left">
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Final risk score</p>
            <p className="cn-font-heading text-4xl font-semibold tabular-nums text-foreground">
              {(evalCase.fusedRiskScore * 100).toFixed(0)}%
            </p>
            <p className="text-xs text-muted-foreground">
              Weighted fusion across {evalCase.modelSignals.length} modality signals
            </p>
          </div>
          <div className="flex flex-col items-center gap-2 sm:items-end">
            <DecisionBadge decision={evalCase.decision} />
            <p className="text-xs text-muted-foreground">
              {evalCase.outcomeLabel ?? (evalCase.detected ? "Scored correctly" : "Scored incorrectly")}
              {evalCase.actualLabel ? ` — ground truth: ${evalCase.actualLabel}` : ""}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Why this decision</CardTitle>
          <CardDescription>Human-readable evidence behind the fused score</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1.5 text-sm text-foreground">
            {evalCase.evidence.map(e => <li key={e} className="flex gap-2">
                <span className="text-muted-foreground">·</span>
                {e}
              </li>)}
          </ul>
        </CardContent>
      </Card>
    </div>;
}
function PipelineArrow({
  label
}) {
  return <div className="flex items-center gap-3 px-1">
      <div className="h-px flex-1 bg-border" />
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <ArrowDownIcon className="size-3.5" />
        {label}
      </div>
      <div className="h-px flex-1 bg-border" />
    </div>;
}
