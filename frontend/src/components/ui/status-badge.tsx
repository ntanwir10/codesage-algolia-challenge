import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: "pending" | "processing" | "completed" | "failed";
  showIcon?: boolean;
  className?: string;
}

export function StatusBadge({
  status,
  showIcon = true,
  className,
}: StatusBadgeProps) {
  const getStatusConfig = (status: string) => {
    switch (status) {
      case "completed":
        return {
          color: "text-green-700 bg-green-50 border-green-200",
          icon: "✅",
          label: "Completed",
        };
      case "processing":
        return {
          color: "text-blue-700 bg-blue-50 border-blue-200",
          icon: "⏳",
          label: "Processing",
        };
      case "failed":
        return {
          color: "text-red-700 bg-red-50 border-red-200",
          icon: "❌",
          label: "Failed",
        };
      default:
        return {
          color: "text-gray-700 bg-gray-50 border-gray-200",
          icon: "⏸️",
          label: "Pending",
        };
    }
  };

  const config = getStatusConfig(status);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium border",
        config.color,
        className
      )}
    >
      {showIcon && <span>{config.icon}</span>}
      {config.label}
    </span>
  );
}
