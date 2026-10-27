import { websocketService } from "@/services/websocket";

export const POLL_INTERVAL_MS = 3000;
// With the socket live, updates are pushed; polling is only a safety net
export const LIVE_POLL_INTERVAL_MS = 15000;

export function isActiveStatus(status: string | undefined): boolean {
  return status === "pending" || status === "processing";
}

/**
 * What an active run is doing. The backend reports file counts only while it parses, so the
 * counts tell the stages apart: none yet while it downloads, all of them while Algolia indexes.
 */
export function progressStage(repo: {
  status: string;
  processed_files: number;
  total_files: number;
}): string {
  if (repo.status === "pending") return "Queued";
  if (!repo.processed_files) return "Fetching files…";
  if (repo.processed_files < repo.total_files) return "Parsing and storing files…";
  return "Indexing in Algolia…";
}

function interval(): number {
  return websocketService.getStatus() === "connected"
    ? LIVE_POLL_INTERVAL_MS
    : POLL_INTERVAL_MS;
}

/**
 * For TanStack Query's `refetchInterval` option: keep polling while the
 * repository is pending/processing, stop as soon as it is completed/failed.
 */
export function pollWhileActive(
  data: { status: string } | undefined
): number | false {
  return isActiveStatus(data?.status) ? interval() : false;
}

export function pollWhileAnyActive(
  data: { status: string }[] | undefined
): number | false {
  return data?.some((r) => isActiveStatus(r.status)) ? interval() : false;
}
