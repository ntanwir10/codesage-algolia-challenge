import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { queryClient } from "@/lib/queryClient";
import { Layout } from "@/components/layout/Layout";
import { HomePage } from "@/pages/HomePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { RepositoryPage } from "@/pages/RepositoryPage";
import { ToastProvider } from "@/components/ui/toast";

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <Router>
          <Layout>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/repository/:id" element={<RepositoryPage />} />
            </Routes>
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
