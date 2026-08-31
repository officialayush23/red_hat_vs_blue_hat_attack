import { useParams, Link } from "react-router-dom";
import { FileJsonIcon, FileSpreadsheetIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { SeverityBadge } from "@/components/shared/badges";
import { StatCard } from "@/components/shared/StatCard";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useReport } from "@/hooks/useReports";
import { exportReport } from "@/services/api/reports";
import { DetectionTrendChart } from "@/features/dashboard/DetectionTrendChart";
import { ATTACK_CATEGORY_LABEL, MODALITY_LABEL } from "@/types";
import { EmptyState } from "@/components/shared/EmptyState";
function downloadReport(report, format) {
  const blob = exportReport(report, format);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${report.runId}-defense-report.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
export function ReportPage() {
  const {
    runId = ""
  } = useParams();
  const {
    data: report,
    isLoading
  } = useReport(runId);
  if (isLoading) {
    return <div className="space-y-6">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>;
  }
  if (!report) {
    return <div className="space-y-6">
        <PageHeader eyebrow="Reports" title="Defense report" />
        <EmptyState icon={<FileJsonIcon className="size-10" />} title="No report for this run" description="This run doesn't have results to report on yet -- it may still be in progress, or the run ID no longer exists." action={<Button asChild variant="outline">
                <Link to="/runs">Back to defense runs</Link>
              </Button>} />
      </div>;
  }
  return <div className="space-y-6">
      <PageHeader eyebrow="Reports" title={`Defense report — ${report.runId}`} description={report.objective} actions={<div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => downloadReport(report, "csv")}>
              <FileSpreadsheetIcon className="size-4" />
              Export CSV
            </Button>
            <Button onClick={() => downloadReport(report, "json")}>
              <FileJsonIcon className="size-4" />
              Export Report (JSON)
            </Button>
          </div>} />

      <Card>
        <CardContent className="grid gap-4 py-4 text-sm sm:grid-cols-4">
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Defense run ID</p>
            <p className="font-medium text-foreground">{report.runId}</p>
          </div>
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Generated</p>
            <p className="font-medium text-foreground">{new Date(report.generatedAt).toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Attack coverage</p>
            <p className="font-medium text-foreground">{report.attackCoveragePct.toFixed(0)}% of taxonomy</p>
          </div>
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Data</p>
            <p className="font-medium text-foreground">{report.dataSource}</p>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Detection before" value={report.performance.detectionRateBefore.toFixed(1)} suffix="%" />
        <StatCard label="Detection after" value={report.performance.detectionRateAfter.toFixed(1)} suffix="%" tone="positive" />
        <StatCard label="Precision" value={report.performance.precision.toFixed(2)} />
        <StatCard label="Recall" value={report.performance.recall.toFixed(2)} />
        <StatCard label="F1 score" value={report.performance.f1.toFixed(2)} />
        <StatCard label="PR-AUC" value={report.performance.prAuc.toFixed(2)} />
        <StatCard label="False positive rate" value={report.performance.falsePositiveRate.toFixed(2)} suffix="%" />
      </div>

      <DetectionTrendChart data={report.iterationImprovement} />

      <Card>
        <CardHeader>
          <CardTitle>Weaknesses found</CardTitle>
          <CardDescription>Attack categories the Blue Team detected weakest in this run</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Category</TableHead>
                <TableHead>Weakness</TableHead>
                <TableHead className="text-right">Detection</TableHead>
                <TableHead className="text-right">Miss rate</TableHead>
                <TableHead>Severity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.weaknesses.map(w => <TableRow key={w.id}>
                  <TableCell className="text-muted-foreground">{ATTACK_CATEGORY_LABEL[w.category]}</TableCell>
                  <TableCell className="font-medium">{w.label}</TableCell>
                  <TableCell className="text-right tabular-nums">{w.detectionRate}%</TableCell>
                  <TableCell className="text-right tabular-nums text-destructive">{w.missRate}%</TableCell>
                  <TableCell>
                    <SeverityBadge severity={w.severity} />
                  </TableCell>
                </TableRow>)}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Top missed scenarios</CardTitle>
            <CardDescription>Highest-miss-rate attack scenarios this run</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {report.topMissedScenarios.map(s => <div key={s.name} className="flex items-center justify-between gap-3 rounded-2xl bg-muted/60 px-3 py-2 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium text-foreground">{s.name}</p>
                  <p className="text-xs text-muted-foreground">{ATTACK_CATEGORY_LABEL[s.category]}</p>
                </div>
                <span className="shrink-0 font-medium tabular-nums text-destructive">{s.missRate}%</span>
              </div>)}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Model evidence</CardTitle>
            <CardDescription>Per-model detection rate feeding the fused risk score</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {report.modelEvidence.map(m => <div key={m.name} className="flex items-center justify-between gap-3 text-sm">
                <div className="min-w-0">
                  <p className="truncate text-foreground">{m.name}</p>
                  <p className="text-xs text-muted-foreground">{MODALITY_LABEL[m.modality]}</p>
                </div>
                <span className="shrink-0 font-medium tabular-nums text-foreground">{m.detectionRate}%</span>
              </div>)}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recommended mitigations</CardTitle>
          <CardDescription>Suggested next steps to harden the defense further</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1.5 text-sm text-foreground">
            {report.recommendedMitigations.map(m => <li key={m} className="flex gap-2">
                <span className="text-muted-foreground">·</span>
                {m}
              </li>)}
          </ul>
        </CardContent>
      </Card>
    </div>;
}
