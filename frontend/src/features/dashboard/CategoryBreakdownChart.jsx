import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import { getCategoryBreakdown } from "@/services/api/attacks";
import { ATTACK_CATEGORY_LABEL } from "@/types";

// Real generated-case counts per attack category, from Supabase's
// attack_cases table via services/api/attacks.js.
//
// Was: ATTACK_CATALOG.filter(...).reduce((s, a) => s + a.variants, 0) --
// summing a hand-written `variants` field off 12 invented attacks, over a
// category list that included "QR / Quishing", which no real family maps
// to. Every bar on this chart was a made-up number.
const chartConfig = {
  generatedCases: { label: "Generated cases", color: "var(--primary)" },
};

export function CategoryBreakdownChart() {
  const { data, isLoading } = useQuery({
    queryKey: ["category-breakdown"],
    queryFn: getCategoryBreakdown,
  });

  const rows = (data ?? [])
    .map((c) => ({ ...c, category: ATTACK_CATEGORY_LABEL[c.category] ?? c.category }))
    .sort((a, b) => b.generatedCases - a.generatedCases);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Attacks by category</CardTitle>
        <CardDescription>
          Real generated cases in <code className="font-mono text-xs">attack_cases</code>, grouped by the scope
          category each attack family maps to
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-56 w-full" />
        ) : (
          <ChartContainer config={chartConfig} className="aspect-auto h-56 w-full">
            <BarChart data={rows} layout="vertical" margin={{ left: 0, right: 40, top: 4, bottom: 4 }}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="category" tickLine={false} axisLine={false} width={130} tick={{ fontSize: 11 }} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="generatedCases" fill="var(--color-generatedCases)" radius={[0, 6, 6, 0]}>
                <LabelList
                  dataKey="generatedCases"
                  position="right"
                  formatter={(v) => v.toLocaleString()}
                  className="fill-foreground text-[10px]"
                />
              </Bar>
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
