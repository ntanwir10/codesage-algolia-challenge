export interface Repository {
  id: number;
  name: string;
  description?: string;
  url?: string;
  branch: string;
  language?: string;
  framework?: string;
  status: "pending" | "processing" | "completed" | "failed";
  total_files: number;
  processed_files: number;
  total_lines: number;
  security_score?: number;
  vulnerability_count: number;
  created_at: string;
  updated_at?: string;
  processed_at?: string;
}

export interface CreateRepositoryRequest {
  name: string;
  description?: string;
  url: string;
  branch?: string;
  language?: string;
}

export interface RepositoryUpdate {
  name?: string;
  description?: string;
  url?: string;
  branch?: string;
  language?: string;
  framework?: string;
  status?: string;
}

export interface ProcessingStatus {
  repository_id: number;
  status: string;
  message: string;
  processing_progress?: number;
  algolia_indexed?: boolean;
  mcp_ready?: boolean;
}
