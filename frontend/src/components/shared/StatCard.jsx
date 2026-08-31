import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
export function StatCard({
  label,
  value,
  suffix,
  trend,
  trendLabel,
  icon,
  tone = "default"
}) {
  return <Card>
      <CardContent className="flex items-start justify-between gap-3">
        <div className="space-y-1.5">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
          <p className="cn-font-heading text-2xl font-semibold text-foreground tabular-nums">
            {value}
            {suffix ? <span className="ml-0.5 text-base font-normal text-muted-foreground">{suffix}</span> : null}
          </p>
          {trendLabel ? <p className={cn("text-xs font-medium", tone === "positive" && "text-primary", tone === "negative" && "text-destructive", tone === "default" && "text-muted-foreground")}>
              {trend === "up" ? "↑ " : trend === "down" ? "↓ " : ""}
              {trendLabel}
            </p> : null}
        </div>
        {icon ? <div className="rounded-2xl bg-muted p-2 text-muted-foreground">{icon}</div> : null}
      </CardContent>
    </Card>;
}
