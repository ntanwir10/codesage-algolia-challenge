import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { CodeSageAPI, onApiAuthError } from "./api";
import { MCPToolError } from "@/lib/errors";

interface Captured {
  url?: string;
  baseURL?: string;
  method?: string;
  params?: Record<string, unknown>;
  headers: Record<string, unknown>;
  body: unknown;
}

function makeApi(reply: unknown = {}, status = 200) {
  const api = new CodeSageAPI();
  const calls: Captured[] = [];
  api.client.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    calls.push({
      url: config.url,
      baseURL: config.baseURL,
      method: config.method,
      params: config.params,
      headers: config.headers.toJSON() as Record<string, unknown>,
      body: config.data ? JSON.parse(config.data as string) : undefined,
    });
    const response = {
      data: reply,
      status,
      statusText: "",
      headers: {},
      config,
    };
    if (status >= 400) {
      throw new AxiosError("fail", "ERR_BAD_REQUEST", config, null, response);
    }
    return response;
  };
  return { api, calls };
}

afterEach(() => vi.unstubAllEnvs());

describe("CodeSageAPI", () => {
  beforeEach(() => vi.stubEnv("VITE_API_BASE_URL", ""));

  it("defaults to the same-origin /api/v1 base without repeating it in paths", async () => {
    const { api, calls } = makeApi([]);
    await api.getRepositories();
    expect(calls[0].baseURL).toBe("/api/v1");
    expect(calls[0].url).toBe("/repositories/");
    expect(`${calls[0].baseURL}${calls[0].url}`).not.toMatch(/api\/v1.*api\/v1/);
  });

  it("appends /api/v1 when VITE_API_BASE_URL is a bare origin", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8001/");
    const { api, calls } = makeApi([]);
    await api.getRepositories();
    expect(`${calls[0].baseURL}${calls[0].url}`).toBe(
      "http://localhost:8001/api/v1/repositories/"
    );
  });

  it("honours VITE_API_BASE_URL and sends /health at the origin", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.com/api/v1/");
    const { api, calls } = makeApi({ status: "ok" });
    await api.getRepository(3);
    expect(calls[0].baseURL).toBe("https://api.example.com/api/v1");
    await api.healthCheck();
    expect(calls[1].baseURL).toBe("https://api.example.com");
    expect(calls[1].url).toBe("/health");
  });

  it("sends X-API-Key when VITE_CODESAGE_API_KEY is set", async () => {
    vi.stubEnv("VITE_CODESAGE_API_KEY", "secret-key");
    const { api, calls } = makeApi({});
    await api.createRepository({ url: "https://github.com/a/b" });
    expect(calls[0].headers["X-API-Key"]).toBe("secret-key");
  });

  it("omits X-API-Key when no key is configured", async () => {
    vi.stubEnv("VITE_CODESAGE_API_KEY", "");
    const { api, calls } = makeApi({});
    await api.deleteRepository(1);
    expect(calls[0].headers["X-API-Key"]).toBeUndefined();
  });

  it("sends force_reprocess as a query param, not a body", async () => {
    const { api, calls } = makeApi({ message: "ok" });
    await api.reprocessRepository(7);
    expect(calls[0].url).toBe("/repositories/7/process");
    expect(calls[0].params).toEqual({ force_reprocess: true });
    expect(calls[0].body).toBeUndefined();
  });

  it("fetches the real status endpoint", async () => {
    const { api, calls } = makeApi({ repository_id: 7, status: "processing" });
    await api.getRepositoryStatus(7);
    expect(calls[0].url).toBe("/repositories/7/status");
  });

  it("searchCode sends `repository` (never repository_id) and real page/limit", async () => {
    const payload = {
      query: "auth",
      repository: "5",
      total_hits: 25,
      page: 1,
      pages: 3,
      results: [],
    };
    const { api, calls } = makeApi({
      tool: "search_code",
      result: payload,
      is_error: false,
      error: null,
    });
    const result = await api.searchCode({
      query: "auth",
      repository: "5",
      page: 1,
      limit: 10,
    });
    expect(calls[0].url).toBe("/ai/mcp/tools/call");
    expect(calls[0].body).toEqual({
      tool_name: "search_code",
      arguments: { query: "auth", repository: "5", limit: 10, page: 1 },
    });
    const args = (calls[0].body as { arguments: Record<string, unknown> })
      .arguments;
    expect(args).not.toHaveProperty("repository_id");
    expect(args).not.toHaveProperty("per_page");
    expect(result.total_hits).toBe(25);
    expect(result.pages).toBe(3);
  });

  it("maps is_error to a thrown MCPToolError", async () => {
    const { api } = makeApi({
      tool: "search_code",
      result: null,
      is_error: true,
      error: "Algolia is down",
    });
    const attempt = api.searchCode({ query: "x" });
    await expect(attempt).rejects.toBeInstanceOf(MCPToolError);
    await expect(attempt).rejects.toThrow("Algolia is down");
  });

  it("notifies auth listeners on 401", async () => {
    const { api } = makeApi({ detail: "Unauthorized" }, 401);
    const listener = vi.fn();
    const off = onApiAuthError(listener);
    await expect(api.deleteRepository(1)).rejects.toBeInstanceOf(AxiosError);
    expect(listener).toHaveBeenCalledTimes(1);
    off();
  });
});
