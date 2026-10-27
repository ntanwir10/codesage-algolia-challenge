export interface MCPToolCallRequest {
  tool_name: string;
  arguments: Record<string, unknown>;
}

/**
 * Envelope returned by POST /ai/mcp/tools/call (HTTP 200 even when the tool
 * itself failed: then `is_error` is true, `result` is null and `error` is set).
 */
export interface MCPToolCallResponse<T = unknown> {
  tool: string;
  result: T | null;
  is_error: boolean;
  error: string | null;
}

export type EntityType = "function" | "class" | "import" | "doc_section" | "terraform_block";

/** The `result` payload of get_file: at most 400 lines per call. */
export interface FileContent {
  repository: string;
  path: string;
  language: string | null;
  total_lines: number;
  start_line: number;
  end_line: number;
  truncated: boolean;
  /** One line per row, each prefixed with its right-aligned number and "| ". */
  content: string;
}

export interface Definition {
  entity_type: string;
  entity_name: string;
  file_path: string;
  line_start: number | null;
  line_end: number | null;
  signature: string | null;
  description: string | null;
}

/** The `result` payload of list_definitions. */
export interface DefinitionsResponse {
  repository: string;
  total: number;
  definitions: Definition[];
}

/** Arguments accepted by the search_code tool (unknown keys are rejected: 422). */
export interface SearchQuery {
  query: string;
  /** Repository ID (as a string) or "owner/name". */
  repository?: string;
  language?: string;
  entity_type?: EntityType;
  /** 1-50 */
  limit?: number;
  /** Zero-based page index. */
  page?: number;
}

export interface SearchHit {
  entity_name: string;
  entity_type: string;
  file_path: string;
  line_start: number;
  line_end: number;
  language: string | null;
  signature: string | null;
  snippet: string | null;
  description: string | null;
  /** GitHub permalink to the entity. */
  url: string | null;
}

/** The `result` payload of a successful search_code call. */
export interface SearchResponse {
  query: string;
  repository: string | null;
  total_hits: number;
  page: number;
  pages: number;
  results: SearchHit[];
}

export interface SearchSuggestionsResponse {
  suggestions: string[];
}
