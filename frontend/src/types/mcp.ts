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
  entity_name: string;
  entity_type: string;
  description: string;
  file_path: string;
  language: string;
  line_start: number;
  line_end: number;
  parameters: string[];
  return_type: string | null;
  content: string;
  relevance_score: number;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  total: number;
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
