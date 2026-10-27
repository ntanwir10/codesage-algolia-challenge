import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  useLocation,
} from "react-router-dom";
import { queryClient } from "@/lib/queryClient";
import { Layout } from "@/components/layout/Layout";
import { HomePage } from "@/pages/HomePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { RepositoryPage } from "@/pages/RepositoryPage";
import { FileViewerPage } from "@/pages/FileViewerPage";
import { ToastProvider } from "@/components/ui/toast";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { EmptyState } from "@/components/ui/empty-state";

// Keyed by path so a crash on one page clears when the user navigates away.
export function AppRoutes() {
  const { pathname } = useLocation();
  return (
    <ErrorBoundary key={pathname}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/repository/:id" element={<RepositoryPage />} />
        <Route path="/repository/:id/file" element={<FileViewerPage />} />
        <Route
          path="*"
          element={
            <EmptyState
              icon="🔍"
              title="Page not found"
              description="The page you're looking for doesn't exist."
              action={{ label: "Go home", href: "/" }}
              className="container mx-auto px-4"
            />
          }
        />
      </Routes>
    </ErrorBoundary>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <Router>
          <Layout>
            <AppRoutes />
          </Layout>
        </Router>
      </ToastProvider>

      {/* React Query Devtools */}
      {import.meta.env.VITE_ENABLE_DEV_TOOLS === "true" && (
        <ReactQueryDevtools initialIsOpen={false} />
      )}
    </QueryClientProvider>
  );
}

export default App;
