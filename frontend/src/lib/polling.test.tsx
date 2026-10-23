import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { POLL_INTERVAL_MS, pollWhileActive, pollWhileAnyActive } from "./polling";
import type { Repository } from "@/types/repository";

describe("polling helpers", () => {
  it("polls for pending/processing only", () => {
    expect(pollWhileActive({ status: "pending" })).toBe(POLL_INTERVAL_MS);
    expect(pollWhileActive({ status: "processing" })).toBe(POLL_INTERVAL_MS);
    expect(pollWhileActive({ status: "completed" })).toBe(false);
    expect(pollWhileActive({ status: "failed" })).toBe(false);
    expect(pollWhileActive(undefined)).toBe(false);
    expect(
      pollWhileAnyActive([{ status: "completed" }, { status: "processing" }])
    ).toBe(POLL_INTERVAL_MS);
    expect(pollWhileAnyActive([{ status: "completed" }])).toBe(false);
  });
});

describe("repository polling", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("stops refetching once the status is completed", async () => {
    const statuses = ["processing", "processing", "completed"] as const;
    let calls = 0;
    const fetchRepo = vi.fn(async () => {
      const status = statuses[Math.min(calls++, statuses.length - 1)];
      return { id: 1, status } as Repository;
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(
      () =>
        useQuery({
          queryKey: ["repository", 1],
          queryFn: fetchRepo,
          refetchInterval: (query) => pollWhileActive(query.state.data),
        }),
      { wrapper }
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetchRepo).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(fetchRepo).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(fetchRepo).toHaveBeenCalledTimes(3);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(result.current.data?.status).toBe("completed");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 5);
    });
    expect(fetchRepo).toHaveBeenCalledTimes(3); // no further polling
  });
});
