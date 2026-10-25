import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/ui/toast";
import { api } from "@/services/api";
import type { Repository } from "@/types/repository";
import { DashboardPage } from "./DashboardPage";

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

describe("DashboardPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the list when a background refetch fails", async () => {
    vi.spyOn(api, "getRepositories").mockResolvedValue([repository]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter>
            <DashboardPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>
    );
    expect(await screen.findByText("octo/demo")).toBeInTheDocument();
    vi.spyOn(api, "getRepositories").mockRejectedValue(new Error("network"));
    await client.refetchQueries({ queryKey: ["repositories"] });
    await waitFor(() => expect(client.getQueryState(["repositories"])?.error).toBeTruthy());
    expect(screen.getByText("octo/demo")).toBeInTheDocument();
    expect(screen.queryByText("Failed to load repositories")).not.toBeInTheDocument();
  });
});
