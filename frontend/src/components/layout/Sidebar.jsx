import { ActivityIcon, FileTextIcon, GaugeIcon, LayoutDashboardIcon, ListChecksIcon, Network, PlusCircleIcon, RefreshCwIcon, ShieldAlertIcon, ShieldCheckIcon, TriangleAlertIcon } from "lucide-react";
import { useRuns } from "@/hooks/useRuns";
import { Separator } from "@/components/ui/separator";
import { Sidebar as SidebarPrimitive, SidebarGroup, SidebarMenuButton, useSidebar } from "@/components/ui/sidebar";

export function Sidebar() {
  const { data: runs } = useRuns();
  const { collapsed } = useSidebar();
  const latestId = runs?.[0]?.id ?? "DR-024";

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
          <SidebarMenuButton to={`/runs/${latestId}/activity`} icon={ActivityIcon}>
            Agent Console
          </SidebarMenuButton>
          <SidebarMenuButton to="/attacks" icon={ShieldAlertIcon}>
            Attack Library
          </SidebarMenuButton>
        </SidebarGroup>

        <SidebarGroup title="Blue Team">
          <SidebarMenuButton to={`/runs/${latestId}/evaluation`} icon={ShieldCheckIcon}>
            Evaluation
          </SidebarMenuButton>
          <SidebarMenuButton to={`/runs/${latestId}/weaknesses`} icon={TriangleAlertIcon}>
            Weakness Analysis
          </SidebarMenuButton>
          <SidebarMenuButton to={`/runs/${latestId}/mutation`} icon={RefreshCwIcon}>
            Adaptive Mutation
          </SidebarMenuButton>
        </SidebarGroup>

        <SidebarGroup title="Results">
          <SidebarMenuButton to={`/runs/${latestId}/results`} icon={GaugeIcon}>
            Run Results
          </SidebarMenuButton>
          <SidebarMenuButton to="/performance" icon={GaugeIcon}>
            Model Performance
          </SidebarMenuButton>
          <SidebarMenuButton to={`/runs/${latestId}/report`} icon={FileTextIcon}>
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
