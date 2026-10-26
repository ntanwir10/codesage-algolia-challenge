import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { websocketService } from "@/services/websocket";
import { ConnectionStatus } from "./connection-status";

describe("ConnectionStatus", () => {
  afterEach(() => vi.restoreAllMocks());

  it("stays steady across retries and keeps a dismissal", () => {
    let emit: (s: "connecting" | "connected" | "disconnected") => void = () => {};
    vi.spyOn(websocketService, "onConnectionStatusChange").mockImplementation(
      (cb) => {
        emit = (s) => {
          vi.spyOn(websocketService, "getStatus").mockReturnValue(s);
          cb(s);
        };
        return () => {};
      }
    );
    vi.spyOn(websocketService, "hasSubscribers").mockReturnValue(true);
    render(<ConnectionStatus />);

    act(() => emit("disconnected"));
    const msg = /Live updates unavailable/;
    expect(screen.getByText(msg)).toBeInTheDocument();
    act(() => emit("connecting"));
    expect(screen.getByText(msg)).toBeInTheDocument();
    act(() => emit("disconnected"));
    expect(screen.getByText(msg)).toBeInTheDocument();

    act(() => screen.getByText("Dismiss").click());
    act(() => emit("connecting"));
    act(() => emit("disconnected"));
    expect(screen.queryByText(msg)).not.toBeInTheDocument();

    act(() => emit("connected"));
    act(() => emit("disconnected"));
    expect(screen.getByText(msg)).toBeInTheDocument();
  });
});
