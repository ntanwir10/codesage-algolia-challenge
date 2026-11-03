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

function makeApi(reply: unknown = {}, status = 200, headers: Record<string, string> = {}) {
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
      headers,
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

  it("sends mode only for a semantic search or suggestion, and reads capabilities", async () => {
    const empty = { query: "q", repository: null, total_hits: 0, page: 0, pages: 0, results: [] };
    const { api, calls } = makeApi({ tool: "search_code", result: empty, is_error: false, error: null });
    await api.searchCode({ query: "q", mode: "semantic" });
    await api.searchCode({ query: "q", mode: "keyword" });
    const argsOf = (i: number) => (calls[i].body as { arguments: Record<string, unknown> }).arguments;
    expect(argsOf(0).mode).toBe("semantic");
    expect(argsOf(1)).not.toHaveProperty("mode");

    await api.getSearchSuggestions("qq", { mode: "semantic" });
    await api.getSearchSuggestions("qq");
    expect(calls[2].params).toMatchObject({ query: "qq", mode: "semantic" });
    expect(calls[3].params?.mode).toBeUndefined();

    const caps = makeApi({ semantic_search: true });
    expect(await caps.api.getCapabilities()).toEqual({ semantic_search: true });
    expect(caps.calls[0].url).toBe("/ai/mcp/capabilities");
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

  it("leaves a refused proxy login to the browser, without the key notice", async () => {
    const listener = vi.fn();
    const off = onApiAuthError(listener);
    await makeApi({}, 200).api.getRepositories(); // reset any earlier streak
    const login = makeApi("<html>401</html>", 401, { "www-authenticate": 'Basic realm="CodeSage"' }).api;
    await expect(login.getRepositories()).rejects.toBeInstanceOf(AxiosError);
    expect(listener).not.toHaveBeenCalled();
    off();
  });

  it("notifies once per 401 streak and again after a success", async () => {
    const listener = vi.fn();
    const off = onApiAuthError(listener);
    const ok = makeApi({}, 200).api;
    const bad = makeApi({ detail: "Unauthorized" }, 401).api;
    await ok.getRepositories(); // reset any earlier streak
    await expect(bad.getRepositories()).rejects.toBeInstanceOf(AxiosError);
    await expect(bad.getRepositories()).rejects.toBeInstanceOf(AxiosError);
    expect(listener).toHaveBeenCalledTimes(1);
    await ok.getRepositories();
    await expect(bad.getRepositories()).rejects.toBeInstanceOf(AxiosError);
    expect(listener).toHaveBeenCalledTimes(2);
    off();
  });
});
