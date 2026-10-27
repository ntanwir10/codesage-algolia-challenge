import { websocketService } from "@/services/websocket";

export const POLL_INTERVAL_MS = 3000;
// With the socket live, updates are pushed; polling is only a safety net
export const LIVE_POLL_INTERVAL_MS = 15000;

export function isActiveStatus(status: string | undefined): boolean {
  return status === "pending" || status === "processing";
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
