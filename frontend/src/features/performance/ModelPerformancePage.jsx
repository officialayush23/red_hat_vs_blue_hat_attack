import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/shared/PageHeader";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useModelPerformance } from "@/hooks/useEvaluations";
import { MODALITY_LABEL } from "@/types";
const chartConfig = {
  detectionRate: {
    label: "Detection rate",
    color: "var(--primary)"
  }
};
export function ModelPerformancePage() {
  const {
    data: models,
    isLoading
  } = useModelPerformance();
  return <div className="space-y-6">
      <PageHeader eyebrow="Results" title="Model / defense performance" description="How each detection model in the Blue Team's ensemble performs in isolation — precision, recall, F1, and detection rate." />

      {isLoading || !models ? <Skeleton className="h-72 w-full" /> : <>
          <Card>
            <CardHeader>
              <CardTitle>Detection rate by model</CardTitle>
              <CardDescription>Share of adversarial cases each model correctly flags on its own</CardDescription>
            </CardHeader>
            <CardContent>
              <ChartContainer config={chartConfig} className="aspect-auto h-64 w-full">
                <BarChart data={models} layout="vertical" margin={{
              left: 0,
              right: 24,
              top: 4,
              bottom: 4
            }}>
                  <CartesianGrid horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tickLine={false} axisLine={false} tickFormatter={v => `${v}%`} />
                  <YAxis type="category" dataKey="name" tickLine={false} axisLine={false} width={190} tick={{
                fontSize: 11
              }} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="detectionRate" fill="var(--color-detectionRate)" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ChartContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Per-model metrics</CardTitle>
              <CardDescription>Evaluated against the latest adversarial case set, all modalities</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Model</TableHead>
                    <TableHead>Modality</TableHead>
                    <TableHead className="text-right">Precision</TableHead>
                    <TableHead className="text-right">Recall</TableHead>
                    <TableHead className="text-right">F1</TableHead>
                    <TableHead className="text-right">Detection rate</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {models.map(m => <TableRow key={m.name}>
                      <TableCell className="font-medium">{m.name}</TableCell>
                      <TableCell className="text-muted-foreground">{MODALITY_LABEL[m.modality]}</TableCell>
                      <TableCell className="text-right tabular-nums">{m.precision.toFixed(2)}</TableCell>
                      <TableCell className="text-right tabular-nums">{m.recall.toFixed(2)}</TableCell>
                      <TableCell className="text-right tabular-nums">{m.f1.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-medium tabular-nums text-primary">
                        {m.detectionRate}%
                      </TableCell>
                    </TableRow>)}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>}
    </div>;
}
