import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
const SEVERITY_STYLE = {
  low: "bg-muted text-muted-foreground",
  medium: "bg-secondary text-secondary-foreground",
  high: "bg-[color-mix(in_oklch,var(--destructive),white_20%)]/15 text-destructive",
  critical: "bg-destructive/15 text-destructive"
};
export function SeverityBadge({
  severity,
  className
}) {
  return <Badge variant="outline" className={cn("border-transparent capitalize", SEVERITY_STYLE[severity], className)}>
      {severity}
    </Badge>;
}
const STATUS_STYLE = {
  active: {
    label: "Active",
    className: "bg-primary/10 text-primary"
  },
  hardening: {
    label: "Hardening",
    className: "bg-secondary text-secondary-foreground"
  },
  resolved: {
    label: "Resolved",
    className: "bg-muted text-muted-foreground"
  }
};
export function AttackStatusBadge({
  status
}) {
  const s = STATUS_STYLE[status];
  return <Badge variant="outline" className={cn("border-transparent", s.className)}>
      {s.label}
    </Badge>;
}
const RUN_STATUS_STYLE = {
  queued: {
    label: "Queued",
    className: "bg-muted text-muted-foreground"
  },
  running: {
    label: "Running",
    className: "bg-primary/10 text-primary"
  },
  completed: {
    label: "Completed",
    className: "bg-secondary text-secondary-foreground"
  },
  failed: {
    label: "Failed",
    className: "bg-destructive/15 text-destructive"
  }
};
export function RunStatusBadge({
  status
}) {
  const s = RUN_STATUS_STYLE[status];
  return <Badge variant="outline" className={cn("border-transparent", s.className)}>
      {s.label}
    </Badge>;
}
const DECISION_STYLE = {
  block: "bg-destructive/15 text-destructive",
  review: "bg-secondary text-secondary-foreground",
  allow: "bg-muted text-muted-foreground"
};
export function DecisionBadge({
  decision
}) {
  return <Badge variant="outline" className={cn("border-transparent uppercase", DECISION_STYLE[decision])}>
      {decision}
    </Badge>;
}
const DIFFICULTY_LABEL = {
  easy: "Easy",
  moderate: "Moderate",
  hard: "Hard",
  adaptive: "Adaptive"
};
export function DifficultyBadge({
  difficulty
}) {
  return <Badge variant="outline" className="border-border text-foreground">
      {DIFFICULTY_LABEL[difficulty]}
    </Badge>;
}
