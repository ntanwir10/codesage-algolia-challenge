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
          color: "text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-950/40 border-green-200 dark:border-green-800",
          icon: "✅",
          label: "Completed",
        };
      case "processing":
        return {
          color: "text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800",
          icon: "⏳",
          label: "Processing",
        };
      case "failed":
        return {
          color: "text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-800",
          icon: "❌",
          label: "Failed",
        };
      default:
        return {
          color: "text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700",
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
