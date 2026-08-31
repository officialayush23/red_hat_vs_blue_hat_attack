import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { ATTACK_CATALOG } from "@/data/attackCatalog";
import { ATTACK_CATEGORY_LABEL } from "@/types";
const chartConfig = {
  variants: {
    label: "Attack variants",
    color: "var(--primary)"
  }
};
export function CategoryBreakdownChart() {
  const byCategory = Object.entries(ATTACK_CATEGORY_LABEL).map(([key, label]) => ({
    category: label,
    variants: ATTACK_CATALOG.filter(a => a.category === key).reduce((s, a) => s + a.variants, 0)
  }));
  return <Card>
      <CardHeader>
        <CardTitle>Attacks by category</CardTitle>
        <CardDescription>Generated adversarial variants across the attack taxonomy</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="aspect-auto h-56 w-full">
          <BarChart data={byCategory} layout="vertical" margin={{
          left: 0,
          right: 16,
          top: 4,
          bottom: 4
        }}>
            <CartesianGrid horizontal={false} />
            <XAxis type="number" tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="category" tickLine={false} axisLine={false} width={130} tick={{
            fontSize: 11
          }} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="variants" fill="var(--color-variants)" radius={[0, 6, 6, 0]} />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>;
}
