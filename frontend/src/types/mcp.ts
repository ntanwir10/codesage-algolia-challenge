export interface MCPToolCallRequest {
  tool_name: string;
  arguments: Record<string, any>;
}

export interface MCPToolCallResponse {
  tool: string;
  result: Record<string, any>;
  success: boolean;
  execution_time_ms?: number;
}

export interface MCPErrorResponse {
  error: string;
  tool?: string;
  details?: Record<string, any>;
}

export interface MCPTool {
  name: string;
  description: string;
  parameters: Record<string, any>;
}

export interface MCPToolsResponse {
  tools: MCPTool[];
  count: number;
  status: string;
}

export interface SearchQuery {
  query: string;
  repository_id?: number;
  language?: string;
  entity_type?: string;
  filters?: string;
  page?: number;
  per_page?: number;
}

export interface SearchHit {
  id: string;
  title: string;
  content: string;
  summary?: string;
  entity_type: string;
  file_path: string;
  line_number?: number;
  language?: string;
  repository_id: number;
  repository_name?: string;
  score: number;
  highlighted: Record<string, string[]>;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  total_hits: number;
  processing_time: number;
  page: number;
  per_page: number;
  has_more: boolean;
  facets: Record<string, any>;
  suggestions: string[];
}

export interface MCPCapabilities {
  implementation: {
    name: string;
    version: string;
  };
  capabilities: {
    tools: boolean;
    resources: boolean;
    prompts: boolean;
  };
}
