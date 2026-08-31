import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { RunsListPage } from "@/features/defense-runs/RunsListPage";
import { CreateRunPage } from "@/features/defense-runs/CreateRunPage";
import { LiveAgentActivityPage } from "@/features/agents/LiveAgentActivityPage";
import { AttackLibraryPage } from "@/features/attacks/AttackLibraryPage";
import { AttackDetailPage } from "@/features/attacks/AttackDetailPage";
import { BlueTeamEvaluationPage } from "@/features/evaluation/BlueTeamEvaluationPage";
import { WeaknessAnalysisPage } from "@/features/weaknesses/WeaknessAnalysisPage";
import { AdaptiveMutationPage } from "@/features/weaknesses/AdaptiveMutationPage";
import { RunResultsPage } from "@/features/results/RunResultsPage";
import { ModelPerformancePage } from "@/features/performance/ModelPerformancePage";
import { ReportPage } from "@/features/reports/ReportPage";
import { ArchitecturePage } from "@/features/architecture/ArchitecturePage";
import { WarRoomPage } from "@/features/warroom/WarRoomPage";
export const router = createBrowserRouter([{
  // The war room is a deliberate full-bleed break-out from AppShell's
  // max-w-6xl content column: it IS the screen you land on the moment a
  // run starts, and a 460px-tall attack stream squeezed into a centred
  // column with a sidebar next to it reads as a widget rather than a
  // console. Its own command bar carries the way back out.
  path: "/runs/:runId/live",
  element: <WarRoomPage />
}, {
  path: "/",
  element: <AppShell />,
  children: [{
    index: true,
    element: <DashboardPage />
  }, {
    path: "runs",
    element: <RunsListPage />
  }, {
    path: "runs/new",
    element: <CreateRunPage />
  }, {
    path: "runs/:runId/activity",
    element: <LiveAgentActivityPage />
  }, {
    path: "runs/:runId/evaluation",
    element: <BlueTeamEvaluationPage />
  }, {
    path: "runs/:runId/weaknesses",
    element: <WeaknessAnalysisPage />
  }, {
    path: "runs/:runId/mutation",
    element: <AdaptiveMutationPage />
  }, {
    path: "runs/:runId/results",
    element: <RunResultsPage />
  }, {
    path: "runs/:runId/report",
    element: <ReportPage />
  }, {
    path: "attacks",
    element: <AttackLibraryPage />
  }, {
    path: "attacks/:attackId",
    element: <AttackDetailPage />
  }, {
    path: "performance",
    element: <ModelPerformancePage />
  }, {
    path: "architecture",
    element: <ArchitecturePage />
  }, {
    path: "*",
    element: <Navigate to="/" replace />
  }]
}]);
