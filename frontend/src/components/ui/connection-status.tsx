import { useEffect, useState } from "react";
import { websocketService } from "@/services/websocket";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function ConnectionStatus() {
  const [status, setStatus] = useState(websocketService.getStatus());
  const [showDetails, setShowDetails] = useState(false);
  const [isDismissed, setIsDismissed] = useState(false);

  useEffect(() => {
    const unsubscribe = websocketService.onConnectionStatusChange(
      (newStatus) => {
        setStatus(newStatus);
        // Reset dismissed state when status changes to show important updates
        if (newStatus === "connecting" || newStatus === "connected") {
          setIsDismissed(false);
        }
      }
    );

    return unsubscribe;
  }, []);

  const getStatusConfig = () => {
    switch (status) {
      case "connected":
        return {
          color: "text-green-600 bg-green-50 border-green-200",
          icon: "🟢",
          text: "Real-time updates active",
          description:
            "WebSocket connection established. You'll receive live updates.",
        };
      case "connecting":
        return {
          color: "text-yellow-600 bg-yellow-50 border-yellow-200",
          icon: "🟡",
          text: "Connecting...",
          description: "Establishing real-time connection...",
        };
      default:
        return {
          color: "text-gray-600 bg-gray-50 border-gray-200",
          icon: "⚪",
          text: "No active processing",
          description:
            "Real-time updates will activate during repository processing.",
        };
    }
  };

  const config = getStatusConfig();

  // Don't show anything when dismissed
  if (isDismissed) {
    return null;
  }

  // Don't show disconnected state unless details are requested or there was an error
  if (status === "disconnected" && !showDetails) {
    return null;
  }

  if (status === "connected" && !showDetails) {
    // Minimal indicator when connected
    return (
      <div
        className="fixed bottom-4 right-4 z-40 cursor-pointer"
        onClick={() => setShowDetails(true)}
      >
        <div
          className={`px-2 py-1 rounded-full text-xs border ${config.color} flex items-center gap-1`}
        >
          <span>{config.icon}</span>
          <span className="hidden sm:inline">Live</span>
        </div>
      </div>
    );
  }

  const handleDismiss = () => {
    setShowDetails(false);
    setIsDismissed(true);
  };

  return (
    <div className="fixed bottom-4 right-4 z-40">
      <Card className={`border ${config.color}`}>
        <CardContent className="p-3">
          <div className="flex items-start gap-2">
            <span className="text-lg">{config.icon}</span>
            <div className="flex-1 min-w-0">
              <h4 className="font-medium text-sm">{config.text}</h4>
              <p className="text-xs mt-1 opacity-90">{config.description}</p>

              <div className="flex items-center gap-2 mt-2">
                {status === "disconnected" && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => websocketService.reconnect()}
                    className="text-xs h-6 px-2"
                  >
                    Reconnect
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleDismiss}
                  className="text-xs h-6 px-2"
                >
                  {status === "connected" ? "Hide" : "Dismiss"}
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
