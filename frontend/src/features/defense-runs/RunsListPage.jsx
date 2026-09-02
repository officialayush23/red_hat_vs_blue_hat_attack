import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { RunStatusBadge } from "@/components/shared/badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRuns } from "@/hooks/useRuns";
import { ATTACK_CATEGORY_LABEL } from "@/types";
export function RunsListPage() {
  const {
    data: runs,
    isLoading
  } = useRuns();
  const [statusFilter, setStatusFilter] = useState("all");
  const filtered = runs?.filter(r => statusFilter === "all" || r.status === statusFilter);
  return <div className="space-y-6">
      <PageHeader eyebrow="Red Team · Blue Team" title="Defense runs" description="Every adversarial evaluation the Red Team has run against the fraud defense, and how the defense responded." actions={<Button asChild>
            <Link to="/runs/new">Start Adversarial Evaluation</Link>
          </Button>} />

      <div className="flex items-center gap-3">
        <Select value={statusFilter} onValueChange={v => setStatusFilter(v)}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="queued">Queued</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent>
          {isLoading ? <Skeleton className="h-64 w-full" /> : <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Run</TableHead>
                  <TableHead>Objective</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead className="text-right">Scenarios</TableHead>
                  <TableHead className="text-right">Detection</TableHead>
                  <TableHead className="text-right">Improvement</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered?.map(run => <TableRow key={run.id} className="cursor-pointer">
                    {/* A RUNNING run must land in the war room, not on a
                        results page that can only show zeros because the run
                        has not written its aggregates yet. Until 2026-09-02
                        every row went to /results, so /runs/:id/live -- the
                        one screen built to watch a live run -- was reachable
                        only by typing the URL. */}
                    <TableCell className="font-medium">
                      <Link
                        to={run.status === "running" ? `/runs/${run.id}/live` : `/runs/${run.id}/results`}
                        className="hover:underline"
                      >
                        {run.id}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-64 truncate text-muted-foreground">{run.objective}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {run.scope.slice(0, 2).map(c => ATTACK_CATEGORY_LABEL[c]).join(", ")}
                      {run.scope.length > 2 ? ` +${run.scope.length - 2}` : ""}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{run.scenarioCount.toLocaleString()}</TableCell>
                    {/* A run that never reached the evaluation stage (stopped
                        or failed mid-flight) has no detection number at all.
                        Rendering the 0 default here claimed the defense caught
                        nothing, which is the opposite of "not measured". */}
                    <TableCell className="text-right tabular-nums">
                      {run.hasEvaluation ? `${run.detectionRateAfter.toFixed(1)}%` : <span className="text-muted-foreground" title="This run never reached the evaluation stage">--</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-primary">
                      {run.hasEvaluation ? `+${run.improvementPct.toFixed(1)}` : <span className="text-muted-foreground">--</span>}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <RunStatusBadge status={run.status} />
                        {run.status === "running" && (
                          <Button asChild size="sm" variant="outline" className="h-6 px-2 text-[11px]">
                            <Link to={`/runs/${run.id}/live`}>Watch live</Link>
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>)}
              </TableBody>
            </Table>}
        </CardContent>
      </Card>
    </div>;
}
