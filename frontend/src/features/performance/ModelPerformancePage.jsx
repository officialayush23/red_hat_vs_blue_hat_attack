import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts";
import { TriangleAlertIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useModelPerformance } from "@/hooks/useEvaluations";
import { MODALITY_LABEL } from "@/types";

const chartConfig = {
  detectionRate: { label: "Detection rate", color: "var(--primary)" },
};

// A detection rate is meaningless without the number of samples behind it.
// video_kyc_detector's real metrics.json entry is precision/recall/f1 = 1.0
// on n_samples = 6 (three fraud, three bonafide) -- rendering that as a
// full-width 100% bar next to LightGBM's 100% on 1,392,882 rows invites
// exactly one question from a reviewer, and there is no good answer to it.
// So every surface on this page carries n, and anything under 30 samples is
// labelled provisional in place rather than in a footnote.
const STRENGTH = {
  provisional: {
    label: "Provisional",
    className: "bg-destructive/10 text-destructive",
    explain: "Fewer than 30 evaluated samples — this percentage is not yet meaningful evidence.",
  },
  limited: {
    label: "Limited",
    className: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
    explain: "Fewer than 200 evaluated samples — indicative, not conclusive.",
  },
  strong: {
    label: "Evidence-gated",
    className: "bg-primary/10 text-primary",
    explain: "200+ evaluated samples.",
  },
  unknown: {
    label: "Sample size unknown",
    className: "bg-muted text-muted-foreground",
    explain: "This entry has no n_samples recorded in metrics.json.",
  },
};

function StrengthBadge({ strength }) {
  const meta = STRENGTH[strength] ?? STRENGTH.unknown;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className={cn("border-transparent", meta.className)}>
          {meta.label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{meta.explain}</TooltipContent>
    </Tooltip>
  );
}

function fmtN(n) {
  return n === null || n === undefined ? "—" : n.toLocaleString();
}

export function ModelPerformancePage() {
  const { data: models, isLoading } = useModelPerformance();

  const weak = (models ?? []).filter((m) => m.evidenceStrength === "provisional");
  const poor = (models ?? []).filter((m) => m.recall < 0.5);
  const highFpr = (models ?? []).filter((m) => (m.falsePositiveRate ?? 0) >= 0.1);

  const chartData = (models ?? []).map((m) => ({
    ...m,
    // Axis label carries n so the bar can never be read without it.
    name: `${m.name}  (n=${fmtN(m.nSamples)})`,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Results"
        title="Model / defense performance"
        description="Every number here is read from backend/defend/models/metrics.json via the model_registry table — each one written by a real evaluation script. Sample sizes are shown alongside, because they differ by five orders of magnitude across these models."
      />

      {isLoading || !models ? (
        <Skeleton className="h-72 w-full" />
      ) : (
        <>
          {(weak.length > 0 || poor.length > 0 || highFpr.length > 0) && (
            <Alert>
              <TriangleAlertIcon className="size-4" />
              <AlertTitle>Read these numbers with their limits</AlertTitle>
              <AlertDescription>
                <ul className="mt-1 list-disc space-y-1 pl-4">
                  {weak.map((m) => (
                    <li key={m.id}>
                      <strong>{m.name}</strong> scores {(m.recall * 100).toFixed(0)}% on{" "}
                      <strong>n={fmtN(m.nSamples)}</strong>
                      {m.nPositive ? ` (${m.nPositive} fraud)` : ""} — far too few samples to claim a
                      detection rate. Treat it as a wiring check, not a result.
                    </li>
                  ))}
                  {poor.map((m) => (
                    <li key={`poor-${m.id}`}>
                      <strong>{m.name}</strong> has a real recall of {(m.recall * 100).toFixed(1)}% on
                      n={fmtN(m.nSamples)} — a known, documented limitation, shown as measured rather
                      than hidden.
                    </li>
                  ))}
                  {highFpr.map((m) => (
                    <li key={`fpr-${m.id}`}>
                      <strong>{m.name}</strong> has a{" "}
                      {((m.falsePositiveRate ?? 0) * 100).toFixed(1)}% false-positive rate on legitimate
                      samples — real customer friction, not a rounding error.
                    </li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Detection rate by model</CardTitle>
              <CardDescription>
                Share of evaluated fraud cases each model correctly flags on its own. The sample size is
                printed on every axis label — these range from 6 samples to 1.39 million, and the bars are
                not comparable without it.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ChartContainer config={chartConfig} className="aspect-auto h-72 w-full">
                <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 48, top: 4, bottom: 4 }}>
                  <CartesianGrid horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                  <YAxis type="category" dataKey="name" tickLine={false} axisLine={false} width={260} tick={{ fontSize: 10 }} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="detectionRate" fill="var(--color-detectionRate)" radius={[0, 6, 6, 0]}>
                    <LabelList dataKey="detectionRate" position="right" formatter={(v) => `${v}%`} className="fill-foreground text-[10px]" />
                  </Bar>
                </BarChart>
              </ChartContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Per-model metrics</CardTitle>
              <CardDescription>
                Held-out / adversarial numbers where one exists, otherwise the model&apos;s own evidence-gate
                entry. Hover a model name for what it is and what it was scored against.
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Model</TableHead>
                    <TableHead>Modality</TableHead>
                    <TableHead className="text-right">Samples</TableHead>
                    <TableHead className="text-right">Precision</TableHead>
                    <TableHead className="text-right">Recall</TableHead>
                    <TableHead className="text-right">F1</TableHead>
                    <TableHead className="text-right">False-positive rate</TableHead>
                    <TableHead>Evidence</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {models.map((m) => (
                    <TableRow key={m.id} className={cn(m.evidenceStrength === "provisional" && "bg-destructive/5")}>
                      <TableCell className="font-medium">
                        {m.purpose ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="cursor-help underline decoration-dotted underline-offset-4">
                                {m.name}
                              </span>
                            </TooltipTrigger>
                            <TooltipContent className="block max-w-80 text-xs">
                              <p className="mb-1">{m.purpose}</p>
                              {m.dataset && <p className="text-muted-foreground">Scored against: {m.dataset}</p>}
                              {m.threshold !== null && (
                                <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                                  decision threshold {m.threshold.toFixed(4)}
                                </p>
                              )}
                            </TooltipContent>
                          </Tooltip>
                        ) : (
                          m.name
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground">{MODALITY_LABEL[m.modality] ?? m.modality}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmtN(m.nSamples)}
                        {m.nPositive ? (
                          <span className="block text-[10px] text-muted-foreground">{fmtN(m.nPositive)} fraud</span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{m.precision.toFixed(3)}</TableCell>
                      <TableCell className="text-right tabular-nums">{m.recall.toFixed(3)}</TableCell>
                      <TableCell className="text-right tabular-nums">{m.f1.toFixed(3)}</TableCell>
                      <TableCell
                        className={cn(
                          "text-right tabular-nums",
                          (m.falsePositiveRate ?? 0) >= 0.1 && "font-medium text-amber-600 dark:text-amber-400",
                        )}
                      >
                        {m.falsePositiveRate === null ? "—" : `${(m.falsePositiveRate * 100).toFixed(2)}%`}
                      </TableCell>
                      <TableCell>
                        <StrengthBadge strength={m.evidenceStrength} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
