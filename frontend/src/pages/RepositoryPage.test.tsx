import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError } from "axios";
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

function httpError(status: number, detail: string) {
  return new AxiosError("fail", "ERR_BAD_RESPONSE", undefined, undefined, {
    status,
    data: { detail },
    statusText: "",
    headers: {},
    config: {} as never,
  });
}

function renderPage(
  repo: Repository,
  client?: QueryClient,
  path = "/repository/1",
  loadError?: Error
) {
  const get = vi.spyOn(api, "getRepository");
  if (loadError) get.mockRejectedValue(loadError);
  else get.mockResolvedValue(repo);
  vi.spyOn(api, "getRepositoryStats").mockReturnValue(new Promise(() => {}));
  client ??= new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/repository/:id" element={<RepositoryPage />} />
            <Route path="/dashboard" element={<div>dashboard page</div>} />
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

  it("labels the source link by host", async () => {
    renderPage(repository);
    expect(await screen.findByRole("link", { name: "View on GitHub →" })).toBeInTheDocument();
  });

  it("shows progress from the repository the WebSocket keeps patched", async () => {
    renderPage({ ...repository, status: "processing", processed_files: 200, total_files: 500 });
    expect(await screen.findByText("200 / 500 files")).toBeInTheDocument();
  });

  it("says View source for a non-GitHub host", async () => {
    renderPage({ ...repository, url: "https://gitlab.com/octo/demo" });
    expect(await screen.findByRole("link", { name: "View source →" })).toBeInTheDocument();
    expect(screen.queryByText("View on GitHub →")).not.toBeInTheDocument();
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

describe("RepositoryPage error states", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows not found for a 404", async () => {
    renderPage(repository, undefined, "/repository/1", httpError(404, "Repository 1 not found"));
    expect(await screen.findByText("Repository not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Dashboard" })).toBeInTheDocument();
  });

  it("stops polling once a processing repository turns 404", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderPage({ ...repository, status: "processing" });
      expect(await screen.findByText("Processing Status")).toBeInTheDocument();
      vi.mocked(api.getRepository).mockRejectedValue(httpError(404, "gone"));
      await vi.advanceTimersByTimeAsync(3100);
      expect(await screen.findByText("Repository not found")).toBeInTheDocument();
      const calls = vi.mocked(api.getRepository).mock.calls.length;
      await vi.advanceTimersByTimeAsync(10000);
      expect(vi.mocked(api.getRepository).mock.calls.length).toEqual(calls);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the message and retries on a server error", async () => {
    renderPage(repository, undefined, "/repository/1", httpError(500, "Boom"));
    const get = vi.mocked(api.getRepository);
    expect(await screen.findByText("Couldn't load this repository")).toBeInTheDocument();
    const calls = get.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(calls));
  });

  it("treats 12abc as not found without a request", async () => {
    renderPage(repository, undefined, "/repository/12abc");
    expect(await screen.findByText("Repository not found")).toBeInTheDocument();
    expect(api.getRepository).not.toHaveBeenCalled();
  });

  it("navigates to the dashboard when delete returns 404", async () => {
    renderPage(repository);
    vi.spyOn(api, "deleteRepository").mockRejectedValue(httpError(404, "Repository 1 not found"));
    await userEvent.click(await screen.findByTitle("Delete repository"));
    await userEvent.click(await screen.findByRole("button", { name: "Delete Repository" }));
    expect(await screen.findByText("dashboard page")).toBeInTheDocument();
  });

  it("shows the progress card for a pending repository", async () => {
    const pending = { ...repository, status: "pending" as const };
    renderPage(pending);
    expect(await screen.findByText("Processing Status")).toBeInTheDocument();
  });
});
