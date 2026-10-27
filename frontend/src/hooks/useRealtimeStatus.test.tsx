import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/ui/toast";
import {
  websocketService,
  type ConnectionStatus,
  type RepositoryStatusUpdate,
} from "@/services/websocket";
import type { Repository } from "@/types/repository";
import { useRealtimeStatus } from "./useRealtimeStatus";
import { useGlobalToasts } from "./useStatusToasts";

const repo: Repository = {
  id: 1,
  name: "octo/demo",
  url: "https://github.com/octo/demo",
  branch: null,
  status: "processing",
  error_message: null,
  total_files: 500,
  processed_files: 0,
  total_lines: 0,
  created_at: "2026-10-25T00:00:00Z",
};

/** Capture the socket callbacks the hooks register, so a test can fire them */
function fakeSocket() {
  const socket: {
    status: (status: ConnectionStatus) => void;
    update: (update: RepositoryStatusUpdate) => void;
  } = { status: () => {}, update: () => {} };
  vi.spyOn(websocketService, "getStatus").mockReturnValue("disconnected");
  vi.spyOn(websocketService, "onConnectionStatusChange").mockImplementation((cb) => {
    socket.status = cb;
    return () => {};
  });
  vi.spyOn(websocketService, "onRepositoryUpdate").mockImplementation((_id, cb) => {
    socket.update = cb;
    return () => {};
  });
  vi.spyOn(websocketService, "onStatusUpdate").mockImplementation((cb) => {
    socket.update = cb;
    return () => {};
  });
  return socket;
}

function renderRealtime(client: QueryClient) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  renderHook(() => useRealtimeStatus({ repositoryIds: [repo.id] }), { wrapper });
}

describe("useRealtimeStatus", () => {
  afterEach(() => vi.restoreAllMocks());

  it("patches a list-only cache on a progress tick without refetching it", () => {
    const socket = fakeSocket();
    const client = new QueryClient();
    client.setQueryData(["repositories"], [repo]);
    const invalidate = vi.spyOn(client, "invalidateQueries");
    renderRealtime(client);

    act(() =>
      socket.update({ repository_id: 1, status: "processing", processed_files: 200, total_files: 500 })
    );

    expect(client.getQueryData<Repository[]>(["repositories"])?.[0].processed_files).toBe(200);
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("refetches failed queries when the socket comes back, once", () => {
    const socket = fakeSocket();
    const client = new QueryClient();
    const refetch = vi.spyOn(client, "refetchQueries").mockResolvedValue();
    renderRealtime(client);

    act(() => socket.status("connected"));
    act(() => socket.status("connected"));

    expect(refetch).toHaveBeenCalledTimes(1);
    const { predicate } = refetch.mock.calls[0][0] as {
      predicate: (q: { state: { status: string } }) => boolean;
    };
    expect(predicate({ state: { status: "error" } })).toBe(true);
    expect(predicate({ state: { status: "success" } })).toBe(false);
  });
});

describe("useGlobalToasts", () => {
  afterEach(() => vi.restoreAllMocks());

  function Toasts() {
    useGlobalToasts();
    return null;
  }

  it("warns instead of celebrating when a run left files out", async () => {
    const socket = fakeSocket();
    render(
      <ToastProvider>
        <Toasts />
      </ToastProvider>
    );

    act(() =>
      socket.update({
        repository_id: 1,
        status: "completed",
        name: "octo/demo",
        message: "Partially indexed: 5 files could not be parsed",
      })
    );

    expect(await screen.findByText("Repository partially indexed")).toBeInTheDocument();
    expect(screen.queryByText("Repository analysis complete")).not.toBeInTheDocument();
  });
});
