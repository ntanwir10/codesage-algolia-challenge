import { useEffect, useRef } from "react";
import { useToast } from "@/components/ui/toast";
import { onApiAuthError } from "@/services/api";
import { websocketService } from "@/services/websocket";

/**
 * One app-wide listener: completion/failure toasts for any subscribed
 * repository, plus a clear toast when the API rejects the API key (401).
 */
export function useGlobalToasts(): void {
  const { addToast } = useToast();
  const lastStatus = useRef(new Map<number, string>());

  useEffect(
    () =>
      websocketService.onStatusUpdate((update) => {
        const previous = lastStatus.current.get(update.repository_id);
        lastStatus.current.set(update.repository_id, update.status);
        if (previous === update.status) return; // de-duplicate repeats
        const name = update.name || `Repository ${update.repository_id}`;
        // The backend sends error_message as the message of a run that left files out
        if (update.status === "completed" && update.message?.startsWith("Partially indexed")) {
          addToast({
            type: "warning",
            title: "Repository partially indexed",
            description: `${name}: ${update.message}`,
            duration: 8000,
          });
        } else if (update.status === "completed") {
          addToast({
            type: "success",
            title: "Repository analysis complete",
            description: `${name} is ready for search.`,
            duration: 6000,
          });
        } else if (update.status === "failed") {
          addToast({
            type: "error",
            title: "Repository analysis failed",
            description: update.error || update.message || `Failed to process ${name}.`,
            duration: 8000,
          });
        }
      }),
    [addToast]
  );

  useEffect(
    () =>
      onApiAuthError(() =>
        addToast({
          type: "error",
          title: "API key rejected",
          description:
            "The server rejected this app's API key. Locally, VITE_CODESAGE_API_KEY in frontend/.env must match CODESAGE_API_KEY in backend/.env (restart Vite after changing it); behind the production proxy, check the key nginx adds.",
          duration: 10000,
        })
      ),
    [addToast]
  );
}
