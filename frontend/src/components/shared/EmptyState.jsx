import { Card, CardContent } from "@/components/ui/card";

// Generic "the query settled and there is genuinely no data" state --
// distinct from a loading skeleton. Any page whose data hook can finish
// loading with nothing (empty array / null / no row found) must render
// this instead of falling through to the loading skeleton, or the UI
// looks permanently stuck with no error and no explanation.
export function EmptyState({ icon, title, description, action }) {
  return <Card>
      <CardContent className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
        {icon && <div className="text-muted-foreground/40">{icon}</div>}
        <div className="space-y-1">
          <p className="text-base font-medium text-foreground">{title}</p>
          {description && <p className="mx-auto max-w-sm text-sm text-muted-foreground">{description}</p>}
        </div>
        {action}
      </CardContent>
    </Card>;
}
