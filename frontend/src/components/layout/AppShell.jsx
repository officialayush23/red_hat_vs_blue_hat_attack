import { Outlet } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { OnboardingDialog } from "@/components/shared/OnboardingDialog";
import { SidebarProvider } from "@/components/ui/sidebar";
export function AppShell() {
  return <SidebarProvider>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-6xl space-y-6 px-4 py-6 md:px-8 md:py-8">
            <Outlet />
          </div>
        </main>
      </div>
      <OnboardingDialog />
    </SidebarProvider>;
}
