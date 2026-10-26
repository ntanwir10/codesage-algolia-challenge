import axios, { type AxiosInstance } from "axios";
import { MCPToolError } from "@/lib/errors";
import type {
  Repository,
  CreateRepositoryRequest,
  RepositoryUpdate,
  ProcessingStatus,
  RepositoryStatsData,
  ReprocessResponse,
} from "@/types/repository";
import type {
  MCPToolCallRequest,
  MCPToolCallResponse,
  MCPToolsResponse,
  SearchQuery,
  SearchResponse,
  SearchSuggestionsResponse,
} from "@/types/mcp";

/**
 * All request paths below are relative to the base URL, which defaults to the
 * same-origin `/api/v1` (nginx in Docker, the Vite proxy in dev) and can be
 * overridden with VITE_API_BASE_URL. Paths must NOT repeat `/api/v1`.
 */
const DEFAULT_BASE_URL = "/api/v1";

type AuthErrorListener = () => void;
const authErrorListeners = new Set<AuthErrorListener>();

/** Register a callback invoked (throttled) whenever the server answers 401. */
export function onApiAuthError(listener: AuthErrorListener): () => void {
  authErrorListeners.add(listener);
  return () => {
    authErrorListeners.delete(listener);
  };
}

// Fire once, then stay quiet until a request succeeds again (polling keeps 401ing).
let authErrorNotified = false;
/** Also called by the WebSocket service when /ws closes with 1008. */
export function notifyAuthError(): void {
  if (authErrorNotified) return;
  authErrorNotified = true;
  authErrorListeners.forEach((listener) => listener());
}

/** A request (or the WebSocket handshake) got through, so the next 401 is news again. */
export function clearAuthNotice(): void {
  authErrorNotified = false;
}

function resolveBaseURL(): string {
  const base = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(
    /\/+$/,
    ""
  );
  // Also accept a bare backend origin (e.g. http://localhost:8001), the older convention
  return base.endsWith("/api/v1") ? base : `${base}/api/v1`;
}

/** Origin hosting /health: the API base's origin, or "" for same-origin. */
function resolveOrigin(baseURL: string): string {
  try {
    return new URL(baseURL).origin;
  } catch {
    return "";
  }
}

export class CodeSageAPI {
  readonly client: AxiosInstance;
  private readonly origin: string;

  constructor() {
    const baseURL = resolveBaseURL();
    this.origin = resolveOrigin(baseURL);
    this.client = axios.create({
      baseURL,
      timeout: 30000,
      headers: { "Content-Type": "application/json" },
    });

    // NOTE: VITE_* variables are inlined into the JavaScript bundle at build
    // time, so this key ships to every browser that loads the app. That is
    // acceptable only for this local, single-user setup; it is not a secret.
    const apiKey = import.meta.env.VITE_CODESAGE_API_KEY;
    this.client.interceptors.request.use((config) => {
      if (apiKey) config.headers.set("X-API-Key", apiKey);
      return config;
    });

    this.client.interceptors.response.use(
      (response) => {
        clearAuthNotice();
        return response;
      },
      (error: unknown) => {
        if (axios.isAxiosError(error) && error.response?.status === 401) {
          notifyAuthError();
        }
        return Promise.reject(error);
      }
    );
  }

  // Repository management
  async createRepository(data: CreateRepositoryRequest): Promise<Repository> {
    const response = await this.client.post<Repository>("/repositories/", data);
    return response.data;
  }

  async getRepositories(params?: {
    skip?: number;
    limit?: number;
    language?: string;
    status?: string;
  }): Promise<Repository[]> {
    const response = await this.client.get<Repository[]>("/repositories/", {
      params,
    });
    return response.data;
  }

  async getRepository(id: number): Promise<Repository> {
    const response = await this.client.get<Repository>(`/repositories/${id}`);
    return response.data;
  }

  async updateRepository(
    id: number,
    data: RepositoryUpdate
  ): Promise<Repository> {
    const response = await this.client.put<Repository>(
      `/repositories/${id}`,
      data
    );
    return response.data;
  }

  async deleteRepository(id: number): Promise<void> {
    await this.client.delete(`/repositories/${id}`);
  }

  /** force_reprocess is a query parameter, not a request body. */
  async reprocessRepository(id: number): Promise<ReprocessResponse> {
    const response = await this.client.post<ReprocessResponse>(
      `/repositories/${id}/process`,
      undefined,
      { params: { force_reprocess: true } }
    );
    return response.data;
  }

  async getRepositoryStatus(id: number): Promise<ProcessingStatus> {
    const response = await this.client.get<ProcessingStatus>(
      `/repositories/${id}/status`
    );
    return response.data;
  }

  async getRepositoryStats(id: number): Promise<RepositoryStatsData> {
    const response = await this.client.get<RepositoryStatsData>(
      `/repositories/${id}/stats`
    );
    return response.data;
  }

  // MCP over HTTP
  async getMCPTools(): Promise<MCPToolsResponse> {
    const response = await this.client.get<MCPToolsResponse>("/ai/mcp/tools");
    return response.data;
  }

  /** Returns the raw envelope; check `is_error` or use callTool(). */
  async callMCPTool<T = unknown>(
    toolName: string,
    args: Record<string, unknown>
  ): Promise<MCPToolCallResponse<T>> {
    const request: MCPToolCallRequest = {
      tool_name: toolName,
      arguments: args,
    };
    const response = await this.client.post<MCPToolCallResponse<T>>(
      "/ai/mcp/tools/call",
      request
    );
    return response.data;
  }

  /** Calls a tool and throws MCPToolError when the tool reports is_error. */
  async callTool<T>(toolName: string, args: Record<string, unknown>): Promise<T> {
    const response = await this.callMCPTool<T>(toolName, args);
    if (response.is_error || response.result === null) {
      throw new MCPToolError(
        toolName,
        response.error || `Tool "${toolName}" failed`
      );
    }
    return response.result;
  }

  // Search
  async searchCode(query: SearchQuery): Promise<SearchResponse> {
    // Only send arguments the server knows; it rejects unknown keys with 422.
    const args: Record<string, unknown> = {
      query: query.query,
      limit: query.limit ?? 10,
      page: query.page ?? 0,
    };
    if (query.repository) args.repository = query.repository;
    if (query.language) args.language = query.language;
    if (query.entity_type) args.entity_type = query.entity_type;
    return this.callTool<SearchResponse>("search_code", args);
  }

  async getSearchSuggestions(
    query: string,
    options: { repositoryId?: number; limit?: number; signal?: AbortSignal } = {}
  ): Promise<string[]> {
    const response = await this.client.get<SearchSuggestionsResponse>(
      "/ai/search/suggestions",
      {
        params: {
          query,
          limit: options.limit ?? 5,
          repository_id: options.repositoryId,
        },
        signal: options.signal,
      }
    );
    return response.data.suggestions || [];
  }

  // Health check lives at the origin root, not under the API base.
  async healthCheck(): Promise<{ status: string }> {
    const response = await this.client.get<{ status: string }>("/health", {
      baseURL: this.origin,
    });
    return response.data;
  }
}

export const api = new CodeSageAPI();