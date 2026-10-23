import { useEffect, useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  websocketService,
  type ConnectionStatus,
  type RepositoryStatusUpdate,
} from "@/services/websocket";
import type { Repository } from "@/types/repository";

interface UseRealtimeStatusOptions {
  /** Repositories to subscribe to. The socket only opens while non-empty. */
  repositoryIds?: number[];
}

/**
 * Subscribes to live status for the given repositories, mirrors updates into
 * the TanStack Query cache and invalidates the affected queries. Completion
 * and failure toasts live in Layout (one global listener), not here.
 */
export function useRealtimeStatus({
  repositoryIds = [],
}: UseRealtimeStatusOptions = {}): { connectionStatus: ConnectionStatus } {
  const queryClient = useQueryClient();
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(
    () => websocketService.getStatus()
  );

  useEffect(
    () =>
      websocketService.onConnectionStatusChange(setConnectionStatus),
    []
  );

  const handleUpdate = useCallback(
    (update: RepositoryStatusUpdate) => {
      const { repository_id: id, status } = update;
      const patch = (repo: Repository): Repository => ({
        ...repo,
        status,
        processed_files: update.processed_files ?? repo.processed_files,
        total_files: update.total_files ?? repo.total_files,
      });

      const previous = queryClient.getQueryData<Repository>(["repository", id]);
      queryClient.setQueryData<Repository | undefined>(
        ["repository", id],
        (old) => (old ? patch(old) : old)
      );
      queryClient.setQueryData<Repository[] | undefined>(
        ["repositories"],
        (old) => old?.map((repo) => (repo.id === id ? patch(repo) : repo))
      );

      // Progress ticks are patched in place; a status change (or a terminal
      // state, which brings final totals) refetches the authoritative data.
      const changed = !previous || previous.status !== status;
      if (changed || status === "completed" || status === "failed") {
        queryClient.invalidateQueries({ queryKey: ["repository", id] });
        queryClient.invalidateQueries({ queryKey: ["repository-status", id] });
        queryClient.invalidateQueries({ queryKey: ["repository-stats", id] });
        queryClient.invalidateQueries({ queryKey: ["repositories"] });
      }
    },
    [queryClient]
  );

  // Stable primitive key so a new array identity doesn't re-run the effect.
  const idsKey = useMemo(
    () => [...new Set(repositoryIds)].sort((a, b) => a - b).join(","),
    [repositoryIds]
  );

  useEffect(() => {
    const ids = idsKey ? idsKey.split(",").map(Number) : [];
    const unsubscribers = ids.map((id) =>
      websocketService.onRepositoryUpdate(id, handleUpdate)
    );
    return () => unsubscribers.forEach((unsubscribe) => unsubscribe());
  }, [idsKey, handleUpdate]);

  return { connectionStatus };
}
