import { CircleHelpIcon, MenuIcon, MoonIcon, ShieldCheckIcon, SunIcon } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Sidebar } from "@/components/layout/Sidebar";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useTheme } from "@/lib/theme";
import { useOnboarding } from "@/lib/onboarding";

export function Topbar() {
  const { theme, toggleTheme } = useTheme();
  const { open: openOnboarding } = useOnboarding();
  return <header className="flex h-14 shrink-0 items-center justify-between border-b bg-card px-4 md:px-6">
      <div className="flex items-center gap-3">
        <SidebarTrigger />
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon-sm" className="md:hidden">
              <MenuIcon />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-64 p-0">
            <SheetHeader className="sr-only">
              <SheetTitle>Navigation</SheetTitle>
            </SheetHeader>
            <Sidebar />
          </SheetContent>
        </Sheet>
        <div className="flex items-center gap-2 md:hidden">
          <ShieldCheckIcon className="size-4 text-primary" />
          <span className="cn-font-heading text-sm font-semibold">FraudShield</span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="hidden border-border text-xs text-muted-foreground sm:inline-flex">
          Prototype · Demo Data
        </Badge>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={openOnboarding}
          aria-label="What is FraudShield?"
          title="What is FraudShield?"
        >
          <CircleHelpIcon className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? <SunIcon className="size-4" /> : <MoonIcon className="size-4" />}
        </Button>
        <div className="flex size-8 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground">
          FA
        </div>
      </div>
    </header>;
}
