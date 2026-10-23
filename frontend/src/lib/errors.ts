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
          "Cannot reach the CodeSage server. Check that the backend is running.",
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
        message =
          "Invalid or missing API key. Set VITE_CODESAGE_API_KEY to the key the server expects.";
        break;
      case 429:
        message = "Too many requests. Please wait a moment and try again.";
        break;
      case 500:
        message = `Server error${requestId ? ` (request ${requestId})` : ""}. Please try again later.`;
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
