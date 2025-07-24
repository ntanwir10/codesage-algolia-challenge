import { Card, CardContent } from "@/components/ui/card";
import type { Repository } from "@/types/repository";

interface RepositoryStatsProps {
  repository: Repository;
  className?: string;
}

export function RepositoryStats({
  repository,
  className,
}: RepositoryStatsProps) {
  const stats = [
    {
      label: "Total Files",
      value: repository.total_files?.toLocaleString() || "0",
      icon: "📄",
    },
    {
      label: "Lines of Code",
      value: repository.total_lines?.toLocaleString() || "0",
      icon: "🔢",
    },
    {
      label: "Primary Language",
      value: repository.language || "Unknown",
      icon: "💻",
    },
    {
      label: "Branch",
      value: repository.branch || "main",
      icon: "🌿",
    },
  ];

  return (
    <div className={`grid grid-cols-1 md:grid-cols-4 gap-4 ${className || ""}`}>
      {stats.map((stat) => (
        <Card key={stat.label}>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-lg">{stat.icon}</span>
              <div className="text-2xl font-bold">{stat.value}</div>
            </div>
            <div className="text-sm text-muted-foreground">{stat.label}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
