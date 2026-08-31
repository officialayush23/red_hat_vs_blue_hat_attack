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
                    <TableCell className="font-medium">
                      <Link to={`/runs/${run.id}/results`} className="hover:underline">
                        {run.id}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-64 truncate text-muted-foreground">{run.objective}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {run.scope.slice(0, 2).map(c => ATTACK_CATEGORY_LABEL[c]).join(", ")}
                      {run.scope.length > 2 ? ` +${run.scope.length - 2}` : ""}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{run.scenarioCount.toLocaleString()}</TableCell>
                    <TableCell className="text-right tabular-nums">{run.detectionRateAfter.toFixed(1)}%</TableCell>
                    <TableCell className="text-right tabular-nums text-primary">
                      +{run.improvementPct.toFixed(1)}
                    </TableCell>
                    <TableCell>
                      <RunStatusBadge status={run.status} />
                    </TableCell>
                  </TableRow>)}
              </TableBody>
            </Table>}
        </CardContent>
      </Card>
    </div>;
}
