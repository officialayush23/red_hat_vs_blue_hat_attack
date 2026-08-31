"use client";

import * as React from "react";
import { NavLink } from "react-router-dom";
import { PanelLeftIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const SIDEBAR_STORAGE_KEY = "fraudshield-sidebar-collapsed";
const SIDEBAR_WIDTH = "16rem";
const SIDEBAR_WIDTH_ICON = "3.5rem";

const SidebarContext = React.createContext(null);

export function useSidebar() {
  const ctx = React.useContext(SidebarContext);
  if (!ctx) throw new Error("useSidebar must be used within a SidebarProvider");
  return ctx;
}

export function SidebarProvider({ defaultCollapsed = false, children }) {
  const [collapsed, setCollapsed] = React.useState(() => {
    try {
      const stored = localStorage.getItem(SIDEBAR_STORAGE_KEY);
      return stored ? stored === "1" : defaultCollapsed;
    } catch {
      return defaultCollapsed;
    }
  });

  const toggleSidebar = React.useCallback(() => {
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, next ? "1" : "0");
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const value = React.useMemo(() => ({ collapsed, toggleSidebar }), [collapsed, toggleSidebar]);

  return (
    <SidebarContext.Provider value={value}>
      <div
        style={{
          "--sidebar-width": SIDEBAR_WIDTH,
          "--sidebar-width-icon": SIDEBAR_WIDTH_ICON,
        }}
        className="flex h-dvh w-full overflow-hidden bg-background text-foreground"
      >
        {children}
      </div>
    </SidebarContext.Provider>
  );
}

export function SidebarTrigger({ className, ...props }) {
  const { toggleSidebar, collapsed } = useSidebar();
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={toggleSidebar}
      aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      className={cn("hidden md:inline-flex", className)}
      {...props}
    >
      <PanelLeftIcon className="size-4" />
    </Button>
  );
}

export function Sidebar({ header, footer, className, children }) {
  const { collapsed } = useSidebar();
  return (
    <aside
      data-collapsed={collapsed}
      className={cn(
        "hidden shrink-0 flex-col border-r bg-card transition-[width] duration-200 ease-linear md:flex",
        className,
      )}
      style={{ width: collapsed ? "var(--sidebar-width-icon)" : "var(--sidebar-width)" }}
    >
      {header}
      <div className="flex-1 overflow-x-hidden overflow-y-auto px-2 py-4">{children}</div>
      {footer}
    </aside>
  );
}

export function SidebarGroup({ title, children }) {
  const { collapsed } = useSidebar();
  return (
    <div className="space-y-1 pb-5">
      {!collapsed && (
        <p className="truncate px-3 text-[11px] font-semibold tracking-wide text-muted-foreground/70 uppercase">
          {title}
        </p>
      )}
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

export function SidebarMenuButton({ to, icon: Icon, children, end }) {
  const { collapsed } = useSidebar();

  const link = (
    <NavLink
      to={to}
      end={end ?? to === "/"}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2.5 rounded-2xl px-3 py-2 text-sm font-medium transition-colors",
          collapsed && "justify-center px-0",
          isActive ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground",
        )
      }
    >
      <Icon className="size-4 shrink-0" />
      {!collapsed && <span className="truncate">{children}</span>}
    </NavLink>
  );

  if (!collapsed) return link;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{children}</TooltipContent>
    </Tooltip>
  );
}
