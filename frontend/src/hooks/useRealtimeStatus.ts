import { useEffect, useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  websocketService,
  type RepositoryStatusUpdate,
} from "@/services/websocket";
import { useToast } from "@/components/ui/toast";
import type { Repository, ProcessingStatus } from "@/types/repository";

interface UseRealtimeStatusOptions {
  repositoryId?: number;
  enableNotifications?: boolean;
}

export function useRealtimeStatus({
  repositoryId,
  enableNotifications = true,
}: UseRealtimeStatusOptions = {}) {
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  // Track connection status with real-time updates
  const [connectionStatus, setConnectionStatus] = useState(
    websocketService.getStatus()
  );

  // Subscribe to connection status changes for real-time updates
  useEffect(() => {
    const unsubscribe = websocketService.onConnectionStatusChange((status) => {
      setConnectionStatus(status);
    });

    return unsubscribe;
  }, []);

  // Enable WebSocket when monitoring a repository
  useEffect(() => {
    if (repositoryId) {
      console.log(
        "Enabling WebSocket for repository monitoring:",
        repositoryId
      );
      websocketService.enableForRepository(repositoryId);

      return () => {
        // Don't disable immediately - let other components decide when to disable
      };
    }
  }, [repositoryId]);

  const updateRepositoryData = useCallback(
    (update: RepositoryStatusUpdate) => {
      const { repository_id, status, processed_files, message } = update;

      // Update repository data in cache
      queryClient.setQueryData(
        ["repository", repository_id],
        (oldData: Repository | undefined) => {
          if (!oldData) return oldData;

          return {
            ...oldData,
            status,
            processed_files: processed_files ?? oldData.processed_files,
            updated_at: new Date().toISOString(),
          };
        }
      );

      // Update repository status in cache
      queryClient.setQueryData(
        ["repository-status", repository_id],
        (oldData: ProcessingStatus | undefined) => ({
          repository_id,
          status,
          message,
          processing_progress: update.processing_progress,
          algolia_indexed: update.algolia_indexed ?? oldData?.algolia_indexed,
          mcp_ready: update.mcp_ready ?? oldData?.mcp_ready,
        })
      );

      // Update repositories list in cache
      queryClient.setQueryData(
        ["repositories"],
        (oldData: Repository[] | undefined) => {
          if (!oldData) return oldData;

          return oldData.map((repo) =>
            repo.id === repository_id
              ? {
                  ...repo,
                  status,
                  processed_files: processed_files ?? repo.processed_files,
                  updated_at: new Date().toISOString(),
                }
              : repo
          );
        }
      );
    },
    [queryClient]
  );

  const handleStatusUpdate = useCallback(
    (update: RepositoryStatusUpdate) => {
      updateRepositoryData(update);

      // Show notification for significant status changes
      if (enableNotifications) {
        // Get repository name from cache for better notification text
        // First try repositories list, then individual repository cache
        const repositories = queryClient.getQueryData(["repositories"]) as
          | Repository[]
          | undefined;
        let repository = repositories?.find(
          (repo) => repo.id === update.repository_id
        );

        // If not found in repositories list, try individual repository cache
        if (!repository) {
          repository = queryClient.getQueryData([
            "repository",
            update.repository_id,
          ]) as Repository | undefined;
        }

        const repositoryName =
          repository?.name || `Repository ${update.repository_id}`;

        console.log("🔔 Notification triggered:", {
          repositoryId: update.repository_id,
          repositoryName,
          status: update.status,
          foundInCache: !!repository,
        });

        if (update.status === "completed") {
          addToast({
            type: "success",
            title: "🎉 Repository analysis complete!",
            description: `${repositoryName} is ready for AI-powered search.`,
            duration: 6000,
          });
        } else if (update.status === "failed") {
          addToast({
            type: "error",
            title: "Repository analysis failed",
            description:
              update.message || `Failed to process ${repositoryName}.`,
            duration: 8000,
          });
        }
      }
    },
    [updateRepositoryData, enableNotifications, addToast, queryClient]
  );

  useEffect(() => {
    let unsubscribe: (() => void) | undefined;

    if (repositoryId) {
      // Subscribe to specific repository updates
      unsubscribe = websocketService.onRepositoryUpdate(
        repositoryId,
        handleStatusUpdate
      );
    } else {
      // Subscribe to all repository updates
      unsubscribe = websocketService.onStatusUpdate(handleStatusUpdate);
    }

    return () => {
      unsubscribe?.();
    };
  }, [repositoryId, handleStatusUpdate]);

  // Return connection status and manual controls
  return {
    connectionStatus,
    reconnect: websocketService.reconnect.bind(websocketService),
  };
}
