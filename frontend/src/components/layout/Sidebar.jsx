import { ActivityIcon, FileTextIcon, FlaskConicalIcon, GaugeIcon, LayoutDashboardIcon, ListChecksIcon, Network, PlusCircleIcon, RefreshCwIcon, ShieldAlertIcon, ShieldCheckIcon, TriangleAlertIcon, UsersIcon } from "lucide-react";
import { useLatestEvaluatedRun } from "@/hooks/useRuns";
import { Separator } from "@/components/ui/separator";
import { Sidebar as SidebarPrimitive, SidebarGroup, SidebarMenuButton, useSidebar } from "@/components/ui/sidebar";

export function Sidebar() {
  const { collapsed } = useSidebar();
  // Every Blue Team / Results link below is keyed to a run id. It used to
  // be runs[0] -- the NEWEST run -- which is routinely one that was
  // stopped before the evaluation stage, so "Evaluation", "Weakness
  // Analysis", "Adaptive Mutation", "Run Results" and "Reports" all
  // opened empty for a first-time visitor. Point them at the newest run
  // that actually produced results instead.
  //
  // The old fallback was the literal string "DR-024" -- a leftover mock id
  // that resolves to no row, so with an empty database every one of these
  // links led to a not-found page. When there is genuinely no evaluated
  // run, send people to the runs list, which can explain itself.
  const { run: latestRun } = useLatestEvaluatedRun();
  const latestId = latestRun?.id;
  const runLink = (suffix) => (latestId ? `/runs/${latestId}/${suffix}` : "/runs");

  return (
    <SidebarPrimitive
      header={
        <>
          <div className="flex items-center gap-2.5 px-3 py-5">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
              <ShieldCheckIcon className="size-4" />
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <p className="cn-font-heading truncate text-sm font-semibold text-foreground">FraudShield</p>
                <p className="truncate text-[11px] text-muted-foreground">Agentic AI · Fraud Defense</p>
              </div>
            )}
          </div>
          <Separator />
        </>
      }
      footer={
        <>
          <Separator />
          <div className="px-3 py-3">
            {!collapsed && <p className="text-[11px] text-muted-foreground">Real evaluation data — read from Supabase</p>}
          </div>
        </>
      }
    >
      <nav>
        <SidebarGroup title="Overview">
          <SidebarMenuButton to="/" icon={LayoutDashboardIcon}>
            Dashboard
          </SidebarMenuButton>
          <SidebarMenuButton to="/runs" icon={ListChecksIcon} end>
            Defense Runs
          </SidebarMenuButton>
          <SidebarMenuButton to="/runs/new" icon={PlusCircleIcon}>
            Create Run
          </SidebarMenuButton>
        </SidebarGroup>

        <SidebarGroup title="Red Team">
          <SidebarMenuButton to={runLink("activity")} icon={ActivityIcon}>
            Agent Console
          </SidebarMenuButton>
          <SidebarMenuButton to="/attacks" icon={ShieldAlertIcon}>
            Attack Library
          </SidebarMenuButton>
          <SidebarMenuButton to="/customers" icon={UsersIcon}>
            Customer Universe
          </SidebarMenuButton>
        </SidebarGroup>

        <SidebarGroup title="Blue Team">
          <SidebarMenuButton to={runLink("evaluation")} icon={ShieldCheckIcon}>
            Evaluation
          </SidebarMenuButton>
          <SidebarMenuButton to={runLink("weaknesses")} icon={TriangleAlertIcon}>
            Weakness Analysis
          </SidebarMenuButton>
          <SidebarMenuButton to={runLink("mutation")} icon={RefreshCwIcon}>
            Adaptive Mutation
          </SidebarMenuButton>
        </SidebarGroup>

        <SidebarGroup title="Results">
          <SidebarMenuButton to={runLink("results")} icon={GaugeIcon}>
            Run Results
          </SidebarMenuButton>
          <SidebarMenuButton to="/simulate" icon={FlaskConicalIcon}>
            Simulate Your Data
          </SidebarMenuButton>
          <SidebarMenuButton to="/performance" icon={GaugeIcon}>
            Model Performance
          </SidebarMenuButton>
          <SidebarMenuButton to={runLink("report")} icon={FileTextIcon}>
            Reports / Export
          </SidebarMenuButton>
          <SidebarMenuButton to="/architecture" icon={Network}>
            Architecture
          </SidebarMenuButton>
        </SidebarGroup>
      </nav>
    </SidebarPrimitive>
  );
}
