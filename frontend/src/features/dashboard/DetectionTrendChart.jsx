import { Line, LineChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
const chartConfig = {
  detectionRate: {
    label: "Detection rate",
    color: "var(--primary)"
  }
};
export function DetectionTrendChart({
  data
}) {
  // Real per-family detection rates can genuinely fall well under 80%
  // (a weak family isn't a display bug) -- a hardcoded [80, 100] domain
  // would silently clip those runs off the top of the chart. Floor the
  // domain a bit below the lowest real point instead, capped at 0.
  const rates = (data ?? []).map(d => d.detectionRate).filter(v => typeof v === "number");
  const lo = rates.length ? Math.max(0, Math.floor(Math.min(...rates) / 10) * 10 - 10) : 0;
  return <Card>
      <CardHeader>
        <CardTitle>Detection performance over iterations</CardTitle>
        <CardDescription>Latest defense run — before mutation vs. after each adaptive iteration</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="aspect-auto h-56 w-full">
          <LineChart data={data} margin={{
          left: 4,
          right: 12,
          top: 8,
          bottom: 0
        }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={8} />
            <YAxis domain={[lo, 100]} tickLine={false} axisLine={false} tickMargin={8} tickFormatter={v => `${v}%`} width={38} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Line type="monotone" dataKey="detectionRate" stroke="var(--color-detectionRate)" strokeWidth={2} dot={{
            r: 3
          }} />
          </LineChart>
        </ChartContainer>
      </CardContent>
    </Card>;
}
