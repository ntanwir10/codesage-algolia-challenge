export const POLL_INTERVAL_MS = 3000;

export function isActiveStatus(status: string | undefined): boolean {
  return status === "pending" || status === "processing";
}

/**
 * For TanStack Query's `refetchInterval` option: keep polling while the
 * repository is pending/processing, stop as soon as it is completed/failed.
 */
export function pollWhileActive(
  data: { status: string } | undefined
): number | false {
  return isActiveStatus(data?.status) ? POLL_INTERVAL_MS : false;
}

export function pollWhileAnyActive(
  data: { status: string }[] | undefined
): number | false {
  return data?.some((r) => isActiveStatus(r.status)) ? POLL_INTERVAL_MS : false;
}
