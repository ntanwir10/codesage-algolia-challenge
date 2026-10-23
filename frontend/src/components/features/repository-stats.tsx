import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/services/api";
import { pollWhileActive } from "@/lib/polling";
import type { Repository } from "@/types/repository";

interface RepositoryStatsProps {
  repository: Repository;
  className?: string;
}

export function RepositoryStats({
  repository,
  className,
}: RepositoryStatsProps) {
  const { data: stats } = useQuery({
    queryKey: ["repository-stats", repository.id],
    queryFn: () => api.getRepositoryStats(repository.id),
    refetchInterval: (query) => pollWhileActive(query.state.data),
  });

  const entityBreakdown = Object.entries(stats?.entities_by_type ?? {})
    .map(([type, count]) => `${count.toLocaleString()} ${type}`)
    .join(" · ");

  const cards = [
    {
      label: "Files",
      value: `${(stats?.processed_files ?? repository.processed_files).toLocaleString()} / ${(stats?.total_files ?? repository.total_files).toLocaleString()}`,
      icon: "📄",
    },
    {
      label: "Lines of Code",
      value: (stats?.total_lines ?? repository.total_lines).toLocaleString(),
      icon: "🔢",
    },
    {
      label: "Indexed Entities",
      value: (stats?.total_entities ?? 0).toLocaleString(),
      detail: entityBreakdown,
      icon: "🧩",
    },
    {
      label: "Language / Framework",
      value:
        [stats?.language ?? repository.language, stats?.framework ?? repository.framework]
          .filter(Boolean)
          .join(" / ") || "Unknown",
      detail: `Branch: ${repository.branch ?? "default"}`,
      icon: "💻",
    },
  ];

  return (
    <div className={`grid grid-cols-1 md:grid-cols-4 gap-4 ${className || ""}`}>
      {cards.map((card) => (
        <Card key={card.label}>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-lg">{card.icon}</span>
              <div className="text-2xl font-bold">{card.value}</div>
            </div>
            <div className="text-sm text-muted-foreground">{card.label}</div>
            {card.detail && (
              <div className="text-xs text-muted-foreground mt-1">
                {card.detail}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
