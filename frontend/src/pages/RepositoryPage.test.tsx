import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/ui/toast";
import { api } from "@/services/api";
import type { Repository } from "@/types/repository";
import { RepositoryPage } from "./RepositoryPage";

vi.mock("@/hooks/useRealtimeStatus", () => ({
  useRealtimeStatus: () => ({ connectionStatus: "disconnected" }),
}));

const repository: Repository = {
  id: 1,
  name: "octo/demo",
  url: "https://github.com/octo/demo",
  branch: null,
  status: "completed",
  error_message: null,
  total_files: 3,
  processed_files: 3,
  total_lines: 30,
  created_at: "2026-10-25T00:00:00Z",
};

function renderPage(repo: Repository, client?: QueryClient) {
  vi.spyOn(api, "getRepository").mockResolvedValue(repo);
  vi.spyOn(api, "getRepositoryStatus").mockResolvedValue({
    repository_id: repo.id,
    status: repo.status,
    processed_files: repo.processed_files,
    total_files: repo.total_files,
    progress: 100,
  });
  vi.spyOn(api, "getRepositoryStats").mockReturnValue(new Promise(() => {}));
  client ??= new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/repository/1"]}>
          <Routes>
            <Route path="/repository/:id" element={<RepositoryPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("RepositoryPage completion card", () => {
  afterEach(() => vi.restoreAllMocks());

  it("says complete when nothing was left out", async () => {
    renderPage(repository);
    expect(await screen.findByText("Repository analysis complete!")).toBeInTheDocument();
  });

  it("says partially indexed, and what was skipped, when the run left files out", async () => {
    const message = "Partially indexed: 5 files over the 1000-file limit were skipped";
    renderPage({ ...repository, error_message: message });
    expect(await screen.findByText("Repository partially indexed")).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.queryByText("Repository analysis complete!")).not.toBeInTheDocument();
  });
});

describe("RepositoryPage failures", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the failure reason on the failed card", async () => {
    renderPage({ ...repository, status: "failed", error_message: "Clone failed: auth required" });
    expect(await screen.findByText("Processing failed")).toBeInTheDocument();
    expect(screen.getByText("Clone failed: auth required")).toBeInTheDocument();
  });

  it("keeps showing the repository when a background refetch fails", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderPage(repository, client);
    expect(await screen.findByText("Repository analysis complete!")).toBeInTheDocument();
    vi.spyOn(api, "getRepository").mockRejectedValue(new Error("network"));
    await client.refetchQueries({ queryKey: ["repository", 1] });
    await waitFor(() => expect(client.getQueryState(["repository", 1])?.error).toBeTruthy());
    expect(screen.getByText("Repository analysis complete!")).toBeInTheDocument();
    expect(screen.queryByText("Repository not found")).not.toBeInTheDocument();
  });
});
