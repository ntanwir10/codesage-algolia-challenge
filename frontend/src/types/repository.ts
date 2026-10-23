export type RepositoryStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed";

export interface Repository {
  id: number;
  name: string;
  description?: string | null;
  url?: string | null;
  /** null means the repository's default branch. */
  branch: string | null;
  language?: string | null;
  framework?: string | null;
  status: RepositoryStatus;
  total_files: number;
  processed_files: number;
  total_lines: number;
  security_score?: number | null;
  vulnerability_count: number;
  created_at: string;
  updated_at?: string | null;
  processed_at?: string | null;
}

export interface CreateRepositoryRequest {
  name?: string;
  url: string;
  branch?: string;
  description?: string;
  language?: string;
}

/** `status` and `url` are no longer accepted by the server. */
export interface RepositoryUpdate {
  name?: string;
  description?: string;
  branch?: string;
  language?: string;
  framework?: string;
}

export interface ProcessingStatus {
  repository_id: number;
  status: RepositoryStatus;
  processed_files: number;
  total_files: number;
  progress: number;
}

export interface RepositoryStatsData {
  repository_id: number;
  status: RepositoryStatus;
  total_files: number;
  processed_files: number;
  total_lines: number;
  total_entities: number;
  entities_by_type: Record<string, number>;
  files_by_language: Record<string, number>;
  language?: string | null;
  framework?: string | null;
}

export interface ReprocessResponse {
  message?: string;
  [key: string]: unknown;
}
