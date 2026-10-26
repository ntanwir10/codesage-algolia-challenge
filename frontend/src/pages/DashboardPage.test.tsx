import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AxiosError } from "axios";
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

function renderPage() {
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
  return client;
}

function httpError(status: number, detail: string) {
  return new AxiosError("x", "ERR", undefined, undefined, {
    status,
    data: { detail },
  } as never);
}

describe("DashboardPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows error_message on failed cards", async () => {
    vi.spyOn(api, "getRepositories").mockResolvedValue([
      { ...repository, status: "failed", error_message: "Repository not found" },
    ]);
    renderPage();
    expect(await screen.findByText("Repository not found")).toBeInTheDocument();
  });

  it("uses the described message when the load fails", async () => {
    vi.spyOn(api, "getRepositories").mockRejectedValue(httpError(400, "Backend exploded"));
    renderPage();
    expect(await screen.findByText("Backend exploded")).toBeInTheDocument();
  });

  it("counts pending repos as processing", async () => {
    vi.spyOn(api, "getRepositories").mockResolvedValue([
      { ...repository, status: "pending", processed_files: 0 },
    ]);
    renderPage();
    expect(await screen.findByText(/1 repository processing/)).toBeInTheDocument();
  });

  it("treats a 404 delete as success: refetches, no error toast", async () => {
    const list = vi.spyOn(api, "getRepositories").mockResolvedValue([repository]);
    vi.spyOn(api, "deleteRepository").mockRejectedValue(httpError(404, "gone"));
    renderPage();
    fireEvent.click(await screen.findByLabelText("Delete octo/demo"));
    fireEvent.click(screen.getByText("Delete Repository", { selector: "button" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("Failed to delete repository")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

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
