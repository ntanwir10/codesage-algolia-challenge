import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { onApiAuthError } from "@/services/api";
import {
  WebSocketService,
  buildWebSocketProtocols,
  buildWebSocketUrl,
} from "./websocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  closed: { code?: number } | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;

  url: string;
  protocols?: string[];
  constructor(url: string, protocols?: string[]) {
    this.url = url;
    this.protocols = protocols;
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close(code?: number) {
    this.closed = { code };
    this.readyState = 3;
  }
  // test helpers
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  receive(msg: unknown) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  drop(code = 1006) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

const last = () => FakeWebSocket.instances[FakeWebSocket.instances.length - 1];

describe("WebSocketService", () => {
  let service: WebSocketService;

  beforeEach(() => {
    vi.useFakeTimers();
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubEnv("VITE_WS_URL", "");
    vi.stubEnv("VITE_WEBSOCKET_URL", "");
    vi.stubEnv("VITE_CODESAGE_API_KEY", "");
    service = new WebSocketService();
  });

  afterEach(() => {
    service.disconnect();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("does not open a socket until a repository is subscribed", () => {
    service.onStatusUpdate(() => {});
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("sends subscribe for every subscribed repo on open", () => {
    service.onRepositoryUpdate(1, () => {});
    service.onRepositoryUpdate(2, () => {});
    const ws = last();
    expect(ws.sent).toEqual([]); // not open yet
    ws.open();
    expect(ws.sent).toEqual([
      { type: "subscribe", repository_id: 1 },
      { type: "subscribe", repository_id: 2 },
    ]);
  });

  it("sends subscribe when a new listener is added to an open socket", () => {
    service.onRepositoryUpdate(1, () => {});
    last().open();
    service.onRepositoryUpdate(9, () => {});
    expect(last().sent.at(-1)).toEqual({ type: "subscribe", repository_id: 9 });
  });

  it("delivers repository_status envelopes to repo and global listeners only", () => {
    const repo1 = vi.fn();
    const repo2 = vi.fn();
    const global = vi.fn();
    service.onRepositoryUpdate(1, repo1);
    service.onRepositoryUpdate(2, repo2);
    service.onStatusUpdate(global);
    last().open();
    const data = { repository_id: 1, status: "processing", processed_files: 3 };
    last().receive({ type: "connected", data: {} });
    last().receive({ type: "subscribed", data: { repository_id: 1 } });
    last().receive({ type: "repository_status", data });
    expect(repo1).toHaveBeenCalledWith(data);
    expect(global).toHaveBeenCalledWith(data);
    expect(repo2).not.toHaveBeenCalled();
    expect(repo1).toHaveBeenCalledTimes(1);
  });

  it("sends unsubscribe when the last listener goes and closes when idle", () => {
    const off1 = service.onRepositoryUpdate(1, () => {});
    const off2 = service.onRepositoryUpdate(1, () => {});
    last().open();
    off1();
    expect(last().sent.some((m) => m.type === "unsubscribe")).toBe(false);
    off2();
    expect(last().sent.at(-1)).toEqual({
      type: "unsubscribe",
      repository_id: 1,
    });
    const ws = last();
    expect(ws.closed).toBeNull();
    vi.advanceTimersByTime(1500);
    expect(ws.closed).toEqual({ code: 1000 });
  });

  it("sends a heartbeat ping every 25s", () => {
    service.onRepositoryUpdate(1, () => {});
    last().open();
    vi.advanceTimersByTime(25000);
    expect(last().sent.at(-1)).toEqual({ type: "ping" });
  });

  it("reconnects when a ping gets no reply (half-open connection)", () => {
    service.onRepositoryUpdate(1, () => {});
    const first = last();
    first.open();
    vi.advanceTimersByTime(25000); // ping
    first.receive({ type: "pong" });
    vi.advanceTimersByTime(25000); // answered: ping again, no reconnect
    expect(first.closed).toBeNull();

    const statuses: string[] = [];
    service.onConnectionStatusChange((status) => statuses.push(status));
    vi.advanceTimersByTime(25000); // unanswered
    expect(first.closed).toEqual({ code: 4000 });
    expect(statuses).toEqual(["disconnected"]); // reported once, not twice
    vi.advanceTimersByTime(1000);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("reconnects with capped backoff and resubscribes", () => {
    service.onRepositoryUpdate(4, () => {});
    last().open();
    last().drop();
    expect(FakeWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1000); // first retry <= 1s
    expect(FakeWebSocket.instances).toHaveLength(2);
    last().open();
    expect(last().sent).toContainEqual({ type: "subscribe", repository_id: 4 });
  });

  it("stops reconnecting when the server rejects the API key", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    service.onRepositoryUpdate(4, () => {});
    last().open();
    last().drop(1008);
    vi.advanceTimersByTime(60000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("raises the auth-error notice when the server rejects the API key", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.advanceTimersByTime(10000); // clear the 5s notice throttle left by earlier tests
    const onAuthError = vi.fn();
    const off = onApiAuthError(onAuthError);
    service.onRepositoryUpdate(4, () => {});
    last().open();
    last().drop(1008);
    expect(onAuthError).toHaveBeenCalledTimes(1);
    off();
  });

  it("builds a wss: URL on https pages, never with the key in it", () => {
    vi.stubEnv("VITE_CODESAGE_API_KEY", "k e y");
    vi.stubGlobal("location", {
      protocol: "https:",
      host: "codesage.example.com",
    });
    expect(buildWebSocketUrl()).toBe("wss://codesage.example.com/ws");
    vi.stubGlobal("location", { protocol: "http:", host: "localhost:5173" });
    expect(buildWebSocketUrl()).toBe("ws://localhost:5173/ws");
  });

  it("prefers VITE_WS_URL when set", () => {
    vi.stubEnv("VITE_WS_URL", "wss://ws.example.com/ws");
    expect(buildWebSocketUrl()).toBe("wss://ws.example.com/ws");
  });

  it("sends the key hex-encoded in a subprotocol", () => {
    expect(buildWebSocketProtocols()).toEqual(["codesage"]);
    vi.stubEnv("VITE_CODESAGE_API_KEY", "k e");
    expect(buildWebSocketProtocols()).toEqual(["codesage", "codesage.key.6b2065"]);
    service.onRepositoryUpdate(1, () => {});
    expect(last().protocols).toEqual(["codesage", "codesage.key.6b2065"]);
  });
});
