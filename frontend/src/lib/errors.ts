import { isAxiosError } from "axios";

/** Thrown when an MCP tool call returns HTTP 200 with `is_error: true`. */
export class MCPToolError extends Error {
  readonly tool: string;

  constructor(tool: string, message: string) {
    super(message);
    this.name = "MCPToolError";
    this.tool = tool;
  }
}

export interface DescribedError {
  message: string;
  status?: number;
  requestId?: string;
  kind: "network" | "tool" | "api" | "general";
}

function detailToString(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d === "string") return d;
        if (d && typeof d === "object" && "msg" in d) {
          const { msg } = d as { msg?: unknown };
          return typeof msg === "string" ? msg : undefined;
        }
        return undefined;
      })
      .filter((s): s is string => !!s);
    return parts.length ? parts.join("; ") : undefined;
  }
  return undefined;
}

/**
 * Turns anything thrown by the API layer into a user-presentable message.
 * Backend error bodies are `{detail: string | [pydantic errors]}`, or
 * `{detail: "Internal server error", request_id}` for a 500.
 */
export function describeError(error: unknown): DescribedError {
  if (error instanceof MCPToolError) {
    return { message: error.message, kind: "tool" };
  }

  if (isAxiosError(error)) {
    const response = error.response;
    if (!response) {
      return {
        message:
          error.code === "ECONNABORTED"
            ? "The server took too long to respond. Try again."
            : "Cannot reach the CodeSage server. Check that the backend is running.",
        kind: "network",
      };
    }
    const status = response.status;
    const data = response.data as
      | { detail?: unknown; request_id?: string }
      | undefined;
    const requestId =
      (response.headers?.["x-request-id"] as string | undefined) ??
      data?.request_id;
    const detail = detailToString(data?.detail);

    let message: string;
    switch (status) {
      case 401:
        message = "The server rejected the API key: this app's key doesn't match the server's.";
        break;
      case 429:
        // The server's own text says how long to wait
        message =
          typeof data?.detail === "string"
            ? data.detail
            : "Too many requests. Please wait a moment and try again.";
        break;
      case 500:
        message = `Server error${requestId ? ` (request ${requestId})` : ""}. Please try again later.`;
        break;
      case 502:
      case 503:
      case 504:
        message =
          typeof data?.detail === "string"
            ? data.detail
            : "The server is temporarily unavailable. Try again shortly.";
        break;
      default:
        message = detail ?? `Request failed (${status}).`;
    }
    return { message, status, requestId, kind: "api" };
  }

  if (error instanceof Error) {
    return { message: error.message, kind: "general" };
  }
  return { message: "Something went wrong. Please try again.", kind: "general" };
}
