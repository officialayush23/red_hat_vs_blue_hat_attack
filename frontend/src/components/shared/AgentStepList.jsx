import { motion } from "framer-motion";
import { CheckCircle2Icon, CircleDashedIcon, LoaderCircleIcon } from "lucide-react";
import { cn } from "@/lib/utils";
const AGENT_LABEL = {
  orchestrator: "Orchestrator Agent",
  "threat-research": "Threat Research Agent",
  "attack-planner": "Attack Planner Agent",
  "attack-generator": "Attack Generator",
  "blue-team": "Blue Team",
  evaluation: "Evaluation Agent",
  "mutation-engine": "Adaptation Agent"
};
function TraceField({ label, value }) {
  if (!value || value === "—") return null;
  return <div className="flex gap-2 text-[11px] leading-relaxed">
      <span className="w-16 shrink-0 font-semibold tracking-wide text-muted-foreground/70 uppercase">{label}</span>
      <span className="min-w-0 flex-1 text-muted-foreground">{value}</span>
    </div>;
}
export function AgentStepList({
  steps,
  compact = false
}) {
  return <ol className="space-y-1">
      {steps.map((step, i) => <motion.li key={step.id} initial={{
      opacity: 0,
      y: 6
    }} animate={{
      opacity: 1,
      y: 0
    }} transition={{
      delay: i * 0.06,
      duration: 0.25
    }} className={cn("flex items-start gap-3 rounded-2xl px-3 py-2.5", step.status === "running" && "bg-primary/5")}>
          <span className="mt-0.5 shrink-0">
            {step.status === "done" && <CheckCircle2Icon className="size-4 text-primary" />}
            {step.status === "running" && <LoaderCircleIcon className="size-4 animate-spin text-primary" />}
            {step.status === "pending" && <CircleDashedIcon className="size-4 text-muted-foreground/50" />}
          </span>
          <span className="min-w-0 flex-1 space-y-1.5">
            <span className="flex items-center gap-2">
              <span className={cn("block text-sm font-medium", step.status === "pending" ? "text-muted-foreground" : "text-foreground")}>
                {AGENT_LABEL[step.agent]}
              </span>
              {step.timestamp && !compact && <span className="font-mono text-[10px] text-muted-foreground/60">
                  {new Date(step.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>}
            </span>
            {!compact && <span className="block text-xs text-muted-foreground">{step.detail}</span>}
            {!compact && step.status !== "pending" && <div className="space-y-1 rounded-xl border border-dashed border-border/70 bg-muted/30 px-2.5 py-2">
                <TraceField label="Observe" value={step.observation} />
                <TraceField label="Decide" value={step.decision} />
                <TraceField label="Tool" value={step.tool} />
                <TraceField label="Act" value={step.action} />
                <TraceField label="Result" value={step.status === "done" ? step.result : undefined} />
                <TraceField label="Next" value={step.status === "done" ? step.next : undefined} />
              </div>}
          </span>
        </motion.li>)}
    </ol>;
}
