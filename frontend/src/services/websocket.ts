interface RepositoryStatusUpdate {
  repository_id: number;
  status: string;
  message: string;
  processing_progress?: number;
  processed_files?: number;
  total_files?: number;
  algolia_indexed?: boolean;
  mcp_ready?: boolean;
}

interface WebSocketMessage {
  type: "repository_status";
  data: RepositoryStatusUpdate;
}

type StatusUpdateCallback = (update: RepositoryStatusUpdate) => void;
type ConnectionStatusCallback = (
  status: "connecting" | "connected" | "disconnected"
) => void;

class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private listeners: Map<string, StatusUpdateCallback[]> = new Map();
  private connectionListeners: ConnectionStatusCallback[] = [];
  private isConnecting = false;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private isManuallyDisconnected = false;
  private pageVisible = true;
  private serverCheckTimeout: NodeJS.Timeout | null = null;
  private shouldAutoConnect = false; // New: Control automatic connection
  private lastHealthCheck = 0; // New: Throttle health checks

  constructor() {
    this.setupPageVisibilityHandling();
    this.setupBeforeUnloadHandling();
    // Don't auto-connect on construction - wait for explicit request
  }

  // New: Enable WebSocket when user starts repository processing
  enableForRepository(repositoryId?: number): void {
    console.log("WebSocket enabled for repository processing", {
      repositoryId,
    });
    this.shouldAutoConnect = true;
    this.isManuallyDisconnected = false;
    this.connect();
  }

  // New: Disable WebSocket when not needed
  disable(): void {
    console.log("WebSocket disabled - no active repository processing");
    this.shouldAutoConnect = false;
    this.isManuallyDisconnected = true;
    if (this.ws) {
      this.ws.close(1000, "WebSocket disabled");
    }
    this.clearTimeouts();
  }

  private clearTimeouts(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.serverCheckTimeout) {
      clearTimeout(this.serverCheckTimeout);
      this.serverCheckTimeout = null;
    }
  }

  private setupPageVisibilityHandling(): void {
    // Handle page visibility changes to pause/resume connections
    document.addEventListener("visibilitychange", () => {
      this.pageVisible = !document.hidden;

      if (
        this.pageVisible &&
        this.shouldAutoConnect &&
        this.getStatus() === "disconnected" &&
        !this.isManuallyDisconnected
      ) {
        console.log("Page became visible, attempting to reconnect WebSocket");
        this.reconnectAttempts = 0; // Reset attempts when page becomes visible
        this.reconnectDelay = 1000; // Reset delay
        this.connect();
      }
    });
  }

  private setupBeforeUnloadHandling(): void {
    // Clean disconnect on page unload
    window.addEventListener("beforeunload", () => {
      this.isManuallyDisconnected = true;
      if (this.ws) {
        this.ws.close(1000, "Page unload");
      }
    });
  }

  private async checkServerAvailability(): Promise<boolean> {
    try {
      // Throttle health checks to avoid spam
      const now = Date.now();
      if (now - this.lastHealthCheck < 3000) {
        // Don't check more than once every 3 seconds
        return true; // Assume available to avoid spam
      }
      this.lastHealthCheck = now;

      // Extract server base URL (remove /api/v1 suffix if present)
      const apiBaseUrl =
        import.meta.env.VITE_API_BASE_URL || "http://localhost:8001";
      const serverBaseUrl = apiBaseUrl.replace(/\/api\/v1$/, "");

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000); // Reduced timeout

      const response = await fetch(`${serverBaseUrl}/health`, {
        method: "GET",
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      return response.ok;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      if (!errorMessage.includes("AbortError")) {
        // Don't log abort errors
        console.log(
          "Server not available for WebSocket connection:",
          errorMessage
        );
      }
      return false;
    }
  }

  private async connect(): Promise<void> {
    if (this.isConnecting || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    // Don't reconnect if page is hidden, manually disconnected, or auto-connect is disabled
    if (
      !this.pageVisible ||
      this.isManuallyDisconnected ||
      !this.shouldAutoConnect
    ) {
      return;
    }

    // Check if server is available before attempting WebSocket connection
    const serverAvailable = await this.checkServerAvailability();
    if (!serverAvailable) {
      console.log(
        "Server not available, will retry WebSocket connection later"
      );
      this.notifyConnectionListeners("disconnected");
      this.scheduleServerCheck();
      return;
    }

    this.isConnecting = true;
    this.notifyConnectionListeners("connecting");
    const wsUrl =
      import.meta.env.VITE_WEBSOCKET_URL ||
      import.meta.env.VITE_WS_URL ||
      "ws://localhost:8001/ws";

    console.log(
      `Attempting WebSocket connection to ${wsUrl} (attempt ${
        this.reconnectAttempts + 1
      })`
    );

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log("WebSocket connected successfully");
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.isManuallyDisconnected = false;
        this.notifyConnectionListeners("connected");

        // Clear any pending reconnection timeout
        if (this.reconnectTimeout) {
          clearTimeout(this.reconnectTimeout);
          this.reconnectTimeout = null;
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error("Error parsing WebSocket message:", error);
        }
      };

      this.ws.onclose = (event) => {
        console.log(
          `WebSocket disconnected: code=${event.code}, reason=${
            event.reason || "Unknown"
          }`
        );
        this.isConnecting = false;
        this.ws = null;
        this.notifyConnectionListeners("disconnected");

        // Only attempt to reconnect if it wasn't a manual close and page is visible
        if (
          event.code !== 1000 &&
          !this.isManuallyDisconnected &&
          this.pageVisible
        ) {
          console.log(`Connection lost, will attempt to reconnect...`);
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        this.isConnecting = false;
        this.notifyConnectionListeners("disconnected");
      };
    } catch (error) {
      console.error("Failed to create WebSocket connection:", error);
      this.isConnecting = false;
      this.notifyConnectionListeners("disconnected");
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    // Don't schedule reconnect if manually disconnected, page hidden, or auto-connect disabled
    if (
      this.isManuallyDisconnected ||
      !this.pageVisible ||
      !this.shouldAutoConnect
    ) {
      return;
    }

    // Clear any existing timeout
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
    }

    this.reconnectAttempts++;

    // Increase delay with exponential backoff, but cap it
    this.reconnectDelay = Math.min(
      this.reconnectDelay * 1.5,
      this.maxReconnectDelay
    );

    console.log(
      `Scheduling reconnect attempt ${this.reconnectAttempts} in ${this.reconnectDelay}ms`
    );

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect();
    }, this.reconnectDelay);
  }

  private scheduleServerCheck(): void {
    // Don't schedule server check if manually disconnected, page hidden, or auto-connect disabled
    if (
      this.isManuallyDisconnected ||
      !this.pageVisible ||
      !this.shouldAutoConnect
    ) {
      return;
    }

    // Clear any existing timeout
    if (this.serverCheckTimeout) {
      clearTimeout(this.serverCheckTimeout);
    }

    // Check server availability more frequently than reconnection attempts
    const checkDelay = Math.min(5000, this.reconnectDelay);

    console.log(`Scheduling server availability check in ${checkDelay}ms`);

    this.serverCheckTimeout = setTimeout(() => {
      this.serverCheckTimeout = null;
      this.connect();
    }, checkDelay);
  }

  private handleMessage(message: WebSocketMessage): void {
    const { type, data } = message;

    console.log("📨 WebSocket message received:", {
      type,
      repositoryId: data.repository_id,
      status: data.status,
      message: data.message,
      timestamp: new Date().toISOString(),
    });

    // Call global listeners
    const globalListeners = this.listeners.get("*") || [];
    console.log("🌐 Calling global listeners:", globalListeners.length);
    globalListeners.forEach((callback) => callback(data));

    // Call repository-specific listeners
    const repoListeners =
      this.listeners.get(`repository_${data.repository_id}`) || [];
    console.log(
      `📍 Calling repository-${data.repository_id} listeners:`,
      repoListeners.length
    );
    repoListeners.forEach((callback) => callback(data));

    // Call type-specific listeners
    const typeListeners = this.listeners.get(type) || [];
    console.log(`🏷️ Calling ${type} listeners:`, typeListeners.length);
    typeListeners.forEach((callback) => callback(data));
  }

  // Subscribe to all repository status updates
  onStatusUpdate(callback: StatusUpdateCallback): () => void {
    return this.addListener("*", callback);
  }

  // Subscribe to specific repository updates
  onRepositoryUpdate(
    repositoryId: number,
    callback: StatusUpdateCallback
  ): () => void {
    return this.addListener(`repository_${repositoryId}`, callback);
  }

  private addListener(key: string, callback: StatusUpdateCallback): () => void {
    if (!this.listeners.has(key)) {
      this.listeners.set(key, []);
    }

    const listeners = this.listeners.get(key)!;
    listeners.push(callback);

    // Return unsubscribe function
    return () => {
      const index = listeners.indexOf(callback);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    };
  }

  // Notify connection listeners of status changes
  private notifyConnectionListeners(
    status: "connecting" | "connected" | "disconnected"
  ): void {
    this.connectionListeners.forEach((callback) => callback(status));
  }

  // Subscribe to connection status changes
  onConnectionStatusChange(callback: ConnectionStatusCallback): () => void {
    this.connectionListeners.push(callback);

    return () => {
      const index = this.connectionListeners.indexOf(callback);
      if (index > -1) {
        this.connectionListeners.splice(index, 1);
      }
    };
  }

  // Get connection status
  getStatus(): "connecting" | "connected" | "disconnected" {
    if (this.isConnecting) return "connecting";
    if (this.ws?.readyState === WebSocket.OPEN) return "connected";
    return "disconnected";
  }

  // Manual reconnect
  reconnect(): void {
    console.log("Manual reconnect requested");
    this.shouldAutoConnect = true; // Enable auto-connect
    this.isManuallyDisconnected = false;
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;

    this.clearTimeouts();

    if (this.ws) {
      this.ws.close(1000, "Manual reconnect");
    }

    // Small delay to ensure clean disconnect before reconnecting
    setTimeout(() => {
      this.connect();
    }, 100);
  }

  // Cleanup
  disconnect(): void {
    console.log("WebSocket service shutting down");
    this.shouldAutoConnect = false; // Disable auto-connect
    this.isManuallyDisconnected = true;

    this.clearTimeouts();

    if (this.ws) {
      this.ws.close(1000, "Manual disconnect");
      this.ws = null;
    }
    this.listeners.clear();
    this.connectionListeners.length = 0;
  }
}

// Export singleton instance
export const websocketService = new WebSocketService();
export type { RepositoryStatusUpdate, WebSocketMessage };
