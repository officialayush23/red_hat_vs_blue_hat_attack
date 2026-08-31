import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";
import { OnboardingProvider } from "@/lib/onboarding";
import { router } from "@/routes/router";
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false
    }
  }
});
function App() {
  return <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <OnboardingProvider>
            <RouterProvider router={router} />
          </OnboardingProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>;
}
export default App;
