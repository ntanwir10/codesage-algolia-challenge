import type { RepositoryStatus } from "@/types/repository";

export interface RepositoryStatusUpdate {
  repository_id: number;
  status: RepositoryStatus;
  name?: string;
  processed_files?: number;
  total_files?: number;
  timestamp?: string;
  message?: string;
  error?: string;
}

/** Server -> client envelope. */
export type WebSocketMessage =
  | { type: "repository_status"; data: RepositoryStatusUpdate }
  | { type: "connected" | "subscribed" | "unsubscribed"; data?: unknown }
  | { type: "pong" }
  | { type: "error"; data?: { message?: string } };

export type ConnectionStatus = "connecting" | "connected" | "disconnected";
type StatusUpdateCallback = (update: RepositoryStatusUpdate) => void;
type ConnectionStatusCallback = (status: ConnectionStatus) => void;

const WS_CONNECTING = 0;
const WS_OPEN = 1;
const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 30000;
const HEARTBEAT_MS = 25000;
/** Grace period before closing an unused socket (absorbs effect re-runs). */
const IDLE_CLOSE_MS = 1000;

/**
 * Builds the WebSocket URL: VITE_WS_URL / VITE_WEBSOCKET_URL if set, else
 * same-origin `/ws` (ws: or wss: following the page protocol). The API key is
 * appended as `?api_key=`; like the HTTP header, it ships in the bundle.
 */
export function buildWebSocketUrl(): string {
  const explicit =
    import.meta.env.VITE_WS_URL || import.meta.env.VITE_WEBSOCKET_URL;
  let url: string;
  if (explicit) {
    url = explicit;
  } else {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    url = `${scheme}//${window.location.host}/ws`;
  }
  const apiKey = import.meta.env.VITE_CODESAGE_API_KEY;
  if (apiKey) {
    url += `${url.includes("?") ? "&" : "?"}api_key=${encodeURIComponent(apiKey)}`;
  }
  return url;
}

export class WebSocketService {
  private ws: WebSocket | null = null;
  private isConnecting = false;
  private reconnectAttempts = 0;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private idleTimeout: ReturnType<typeof setTimeout> | null = null;
  private repoListeners = new Map<number, Set<StatusUpdateCallback>>();
  private globalListeners = new Set<StatusUpdateCallback>();
  private connectionListeners = new Set<ConnectionStatusCallback>();
  private visibilityHandler = () => {
    if (
      !document.hidden &&
      this.hasSubscribers() &&
      !this.ws &&
      !this.isConnecting
    ) {
      this.reconnectAttempts = 0;
      this.clearReconnect();
      this.connect();
    }
  };

  constructor() {
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", this.visibilityHandler);
    }
  }

  private hasSubscribers(): boolean {
    return this.repoListeners.size > 0;
  }

  // --- public API ---------------------------------------------------------

  /** Receive updates for one repository. Subscribes server-side. */
  onRepositoryUpdate(
    repositoryId: number,
    callback: StatusUpdateCallback
  ): () => void {
    let set = this.repoListeners.get(repositoryId);
    const isNewRepo = !set;
    if (!set) {
      set = new Set();
      this.repoListeners.set(repositoryId, set);
    }
    set.add(callback);

    this.clearIdleClose();
    if (isNewRepo) this.send({ type: "subscribe", repository_id: repositoryId });
    this.connect();

    return () => {
      const current = this.repoListeners.get(repositoryId);
      if (!current || !current.delete(callback)) return;
      if (current.size === 0) {
        this.repoListeners.delete(repositoryId);
        this.send({ type: "unsubscribe", repository_id: repositoryId });
        if (!this.hasSubscribers()) this.scheduleIdleClose();
      }
    };
  }

  /**
   * Receive every update delivered on this connection. This does not open the
   * socket or subscribe to anything (the server only sends to subscribers).
   */
  onStatusUpdate(callback: StatusUpdateCallback): () => void {
    this.globalListeners.add(callback);
    return () => {
      this.globalListeners.delete(callback);
    };
  }

  onConnectionStatusChange(callback: ConnectionStatusCallback): () => void {
    this.connectionListeners.add(callback);
    return () => {
      this.connectionListeners.delete(callback);
    };
  }

  getStatus(): ConnectionStatus {
    if (this.ws?.readyState === WS_OPEN) return "connected";
    if (this.isConnecting || this.ws?.readyState === WS_CONNECTING) {
      return "connecting";
    }
    return "disconnected";
  }

  /** Manual reconnect (only meaningful while something is subscribed). */
  reconnect(): void {
    this.reconnectAttempts = 0;
    this.clearReconnect();
    this.teardownSocket(1000, "Manual reconnect");
    if (this.hasSubscribers()) this.connect();
  }

  /** Full shutdown: closes the socket and drops every listener. */
  disconnect(): void {
    this.clearReconnect();
    this.clearIdleClose();
    this.teardownSocket(1000, "Client shutdown");
    this.repoListeners.clear();
    this.globalListeners.clear();
    this.connectionListeners.clear();
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", this.visibilityHandler);
    }
  }

  // --- connection management ---------------------------------------------

  private connect(): void {
    if (this.ws || this.isConnecting || !this.hasSubscribers()) return;

    this.isConnecting = true;
    this.notifyConnection("connecting");

    let socket: WebSocket;
    try {
      socket = new WebSocket(buildWebSocketUrl());
    } catch (error) {
      console.error("Failed to create WebSocket:", error);
      this.isConnecting = false;
      this.notifyConnection("disconnected");
      this.scheduleReconnect();
      return;
    }
    this.ws = socket;

    socket.onopen = () => {
      if (this.ws !== socket) return;
      this.isConnecting = false;
      this.reconnectAttempts = 0;
      this.notifyConnection("connected");
      for (const repositoryId of this.repoListeners.keys()) {
        this.send({ type: "subscribe", repository_id: repositoryId });
      }
      this.startHeartbeat();
    };

    socket.onmessage = (event) => {
      if (this.ws !== socket) return;
      try {
        this.handleMessage(JSON.parse(String(event.data)) as WebSocketMessage);
      } catch (error) {
        console.error("Invalid WebSocket message:", error);
      }
    };

    socket.onerror = () => {
      if (this.ws !== socket) return;
      // A close event normally follows and drives reconnection; reset our
      // bookkeeping now so state never claims a dead socket is live.
      this.isConnecting = false;
      this.stopHeartbeat();
      this.notifyConnection("disconnected");
    };

    socket.onclose = (event) => {
      if (this.ws !== socket) return;
      this.ws = null;
      this.isConnecting = false;
      this.stopHeartbeat();
      this.notifyConnection("disconnected");
      // 1008: the server rejected the API key, so retrying can't succeed
      if (event.code === 1008) {
        console.warn("WebSocket rejected by the server: check VITE_CODESAGE_API_KEY");
        return;
      }
      if (this.hasSubscribers()) this.scheduleReconnect();
    };
  }

  /** Detach and close the current socket without triggering reconnects. */
  private teardownSocket(code: number, reason: string): void {
    this.stopHeartbeat();
    const socket = this.ws;
    this.ws = null;
    this.isConnecting = false;
    if (socket) {
      socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
      try {
        socket.close(code, reason);
      } catch {
        // already closing
      }
      this.notifyConnection("disconnected");
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimeout || !this.hasSubscribers()) return;
    // Exponential backoff capped at 30s, with 50-100% jitter.
    const exp = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** this.reconnectAttempts);
    const delay = Math.round(exp * (0.5 + Math.random() * 0.5));
    this.reconnectAttempts++;
    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect();
    }, delay);
  }

  private clearReconnect(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }

  private scheduleIdleClose(): void {
    this.clearIdleClose();
    this.idleTimeout = setTimeout(() => {
      this.idleTimeout = null;
      if (this.hasSubscribers()) return;
      this.clearReconnect();
      this.teardownSocket(1000, "No subscribers");
    }, IDLE_CLOSE_MS);
  }

  private clearIdleClose(): void {
    if (this.idleTimeout) {
      clearTimeout(this.idleTimeout);
      this.idleTimeout = null;
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatInterval = setInterval(
      () => this.send({ type: "ping" }),
      HEARTBEAT_MS
    );
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private send(payload: Record<string, unknown>): void {
    if (this.ws?.readyState === WS_OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  private handleMessage(message: WebSocketMessage): void {
    switch (message.type) {
      case "repository_status": {
        const update = message.data;
        this.globalListeners.forEach((cb) => cb(update));
        this.repoListeners
          .get(update.repository_id)
          ?.forEach((cb) => cb(update));
        break;
      }
      case "error":
        console.warn("WebSocket server error:", message.data?.message);
        break;
      default:
        // connected / subscribed / unsubscribed / pong need no handling
        break;
    }
  }

  private notifyConnection(status: ConnectionStatus): void {
    this.connectionListeners.forEach((cb) => cb(status));
  }
}

export const websocketService = new WebSocketService();
