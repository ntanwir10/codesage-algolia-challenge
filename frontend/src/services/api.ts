import axios, { type AxiosInstance } from "axios";
import type {
  Repository,
  CreateRepositoryRequest,
  ProcessingStatus,
  RepositoryUpdate,
} from "@/types/repository";
import type {
  MCPToolCallRequest,
  MCPToolCallResponse,
  MCPToolsResponse,
  SearchQuery,
  SearchResponse,
  MCPCapabilities,
} from "@/types/mcp";

class CodeSageAPI {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
      timeout: 30000,
      headers: {
        "Content-Type": "application/json",
      },
    });

    // Request interceptor for logging
    this.client.interceptors.request.use(
      (config) => {
        console.log(
          `Making ${config.method?.toUpperCase()} request to ${config.url}`
        );
        return config;
      },
      (error) => {
        console.error("Request error:", error);
        return Promise.reject(error);
      }
    );

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        console.error("API Error:", error.response?.data || error.message);
        return Promise.reject(error);
      }
    );
  }

  // Repository Management
  async createRepository(data: CreateRepositoryRequest): Promise<Repository> {
    const response = await this.client.post("/api/v1/repositories/", data);
    return response.data;
  }

  async getRepositories(params?: {
    skip?: number;
    limit?: number;
    language?: string;
    status?: string;
    mcp_ready?: boolean;
  }): Promise<Repository[]> {
    const response = await this.client.get("/api/v1/repositories/", { params });
    return response.data;
  }

  async getRepository(id: number): Promise<Repository> {
    const response = await this.client.get(`/api/v1/repositories/${id}`);
    return response.data;
  }

  async updateRepository(
    id: number,
    data: RepositoryUpdate
  ): Promise<Repository> {
    const response = await this.client.put(`/api/v1/repositories/${id}`, data);
    return response.data;
  }

  async deleteRepository(id: number): Promise<void> {
    await this.client.delete(`/api/v1/repositories/${id}`);
  }

  async processRepository(
    id: number,
    forceReprocess = false
  ): Promise<ProcessingStatus> {
    const response = await this.client.post(
      `/api/v1/repositories/${id}/process`,
      {
        force_reprocess: forceReprocess,
      }
    );
    return response.data;
  }

  async getRepositoryStatus(id: number): Promise<ProcessingStatus> {
    const response = await this.client.get(`/api/v1/repositories/${id}/status`);
    return response.data;
  }

  // MCP Integration
  async getMCPCapabilities(): Promise<MCPCapabilities> {
    const response = await this.client.get("/api/v1/ai/mcp/capabilities");
    return response.data;
  }

  async getMCPTools(): Promise<MCPToolsResponse> {
    const response = await this.client.get("/api/v1/ai/mcp/tools");
    return response.data;
  }

  async callMCPTool(
    toolName: string,
    args: Record<string, any>
  ): Promise<MCPToolCallResponse> {
    const request: MCPToolCallRequest = {
      tool_name: toolName,
      arguments: args,
    };
    const response = await this.client.post(
      "/api/v1/ai/mcp/tools/call",
      request
    );
    return response.data;
  }

  // Search functionality
  async searchCode(query: SearchQuery): Promise<SearchResponse> {
    const response = await this.client.post("/api/v1/search/", query);
    return response.data;
  }

  async getSearchSuggestions(query: string): Promise<string[]> {
    const response = await this.client.get("/api/v1/search/suggestions", {
      params: { query, limit: 10 },
    });
    return response.data.suggestions || [];
  }

  // Health checks
  async healthCheck(): Promise<{ status: string }> {
    const response = await this.client.get("/health");
    return response.data;
  }

  async getMCPServerInfo(): Promise<any> {
    const response = await this.client.get("/mcp");
    return response.data;
  }
}

// Export singleton instance
export const api = new CodeSageAPI();
export default api;
