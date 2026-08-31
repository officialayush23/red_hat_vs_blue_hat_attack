import { Cell, Pie, PieChart } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
const chartConfig = {
  caught: {
    label: "Caught",
    color: "var(--primary)"
  },
  missed: {
    label: "Missed",
    color: "var(--destructive)"
  }
};
export function CaughtVsMissedChart({
  run
}) {
  const data = [{
    name: "caught",
    label: "Caught",
    value: run.attacksCaught,
    fill: "var(--color-caught)"
  }, {
    name: "missed",
    label: "Missed",
    value: run.attacksMissed,
    fill: "var(--color-missed)"
  }];
  return <Card>
      <CardHeader>
        <CardTitle>Caught vs. missed</CardTitle>
        <CardDescription>
          {run.id} · {run.attacksTested.toLocaleString()} attacks evaluated
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-6">
        <ChartContainer config={chartConfig} className="aspect-square h-40 w-40 shrink-0">
          <PieChart>
            <ChartTooltip content={<ChartTooltipContent hideLabel />} />
            <Pie data={data} dataKey="value" nameKey="label" innerRadius={42} outerRadius={64} strokeWidth={2}>
              {data.map(d => <Cell key={d.name} fill={d.fill} />)}
            </Pie>
          </PieChart>
        </ChartContainer>
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-2">
            <span className="size-2.5 rounded-full bg-primary" />
            <span className="text-muted-foreground">Caught</span>
            <span className="ml-auto font-medium tabular-nums">{run.attacksCaught.toLocaleString()}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="size-2.5 rounded-full bg-destructive" />
            <span className="text-muted-foreground">Missed</span>
            <span className="ml-auto font-medium tabular-nums">{run.attacksMissed.toLocaleString()}</span>
          </div>
        </div>
      </CardContent>
    </Card>;
}
