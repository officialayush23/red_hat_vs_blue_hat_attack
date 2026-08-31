import { BrainCircuitIcon, LayoutDashboardIcon, NetworkIcon, RefreshCwIcon, ServerIcon, ShieldCheckIcon, UserIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
const LAYERS = [{
  id: "analyst",
  icon: UserIcon,
  title: "Analyst",
  subtitle: "Fraud & risk team",
  summary: "Defines evaluation objectives and reviews what the loop finds",
  detail: "A human analyst sets the scope and severity for a defense run, reviews discovered weaknesses, and approves recommended mitigations before they reach production models."
}, {
  id: "dashboard",
  icon: LayoutDashboardIcon,
  title: "React Dashboard",
  subtitle: "This application",
  summary: "TypeScript + Tailwind + shadcn/ui, talking to a typed REST client",
  detail: "React 19, TypeScript, Tailwind CSS and shadcn/ui, with TanStack Query for data fetching. Every screen reads from a service layer shaped exactly like the future backend's REST responses, so swapping mocks for live calls needs no UI changes."
}, {
  id: "api",
  icon: ServerIcon,
  title: "FastAPI Gateway",
  subtitle: "Backend API — planned",
  summary: "REST endpoints for runs, attacks, evaluations, agents and reports",
  detail: "A FastAPI service will expose the same endpoints the mock layer already mimics: /runs, /attacks, /evaluations, /agents and /reports. It authenticates the dashboard, orchestrates the agent workflow below, and persists results."
}, {
  id: "redteam",
  icon: BrainCircuitIcon,
  title: "Agentic Red Team",
  subtitle: "Discover → Simulate → Attack",
  summary: "Orchestrator, threat research, attack planning and generation agents",
  detail: "An orchestrator agent coordinates threat-research, attack-planning and attack-generation sub-agents that continuously produce new adversarial variants across transaction, behavioral, graph, voice, text, QR, document and account-takeover categories."
}, {
  id: "blueteam",
  icon: ShieldCheckIcon,
  title: "Blue Team",
  subtitle: "Evaluate → Risk fusion",
  summary: "Per-modality models score each case; fusion produces one decision",
  detail: "Each generated case is scored independently by the transaction, behavioral, graph, text, voice, document and anomaly models. A fusion layer combines those signals into one risk score and a block / review / allow decision, with human-readable evidence."
}, {
  id: "adapt",
  icon: RefreshCwIcon,
  title: "Adaptive Feedback",
  subtitle: "Adapt → back to Red Team",
  summary: "Weaknesses feed the mutation engine, which hardens the defense",
  detail: "Categories with low detection become the seed for the next iteration: the mutation engine varies amount patterns, timing, device relationships and network structure, then the Red Team re-attacks — closing the loop without human intervention."
}];
export function ArchitecturePage() {
  return <div className="space-y-6">
      <PageHeader eyebrow="System" title="Architecture" description="FraudShield is a continuous adversarial loop, not a one-shot detector. Expand a layer for the technical detail underneath it." />

      <Card>
        <CardContent className="space-y-2 py-5">
          <div className="flex flex-wrap items-stretch justify-center gap-2">
            {LAYERS.map((layer, i) => <div key={layer.id} className="flex items-center gap-2">
                <div className="flex w-40 flex-col items-center gap-1.5 rounded-2xl border bg-card px-3 py-3 text-center">
                  <div className="flex size-9 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                    <layer.icon className="size-4.5" />
                  </div>
                  <span className="text-sm font-medium text-foreground">{layer.title}</span>
                  <span className="text-[11px] text-muted-foreground">{layer.subtitle}</span>
                </div>
                {i < LAYERS.length - 1 ? <NetworkIcon className="size-4 shrink-0 rotate-90 text-muted-foreground/40" /> : <RefreshCwIcon className="size-4 shrink-0 text-primary/60" />}
              </div>)}
          </div>
          <p className="pt-1 text-center text-xs text-muted-foreground">
            Adaptive Feedback loops back into the Agentic Red Team — the defense keeps attacking itself.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="py-2">
          <Accordion type="single" collapsible>
            {LAYERS.map(layer => <AccordionItem key={layer.id} value={layer.id}>
                <AccordionTrigger>
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                      <layer.icon className="size-4" />
                    </div>
                    <div className="min-w-0 text-left">
                      <p className="text-foreground">{layer.title}</p>
                      <p className="truncate text-xs font-normal text-muted-foreground">{layer.summary}</p>
                    </div>
                  </div>
                </AccordionTrigger>
                <AccordionContent>
                  <p className="text-muted-foreground">{layer.detail}</p>
                  <Badge variant="outline" className="mt-2 border-border text-muted-foreground">
                    {layer.subtitle}
                  </Badge>
                </AccordionContent>
              </AccordionItem>)}
          </Accordion>
        </CardContent>
      </Card>
    </div>;
}
