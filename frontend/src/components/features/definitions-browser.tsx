import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { describeError } from "@/lib/errors";
import { ENTITY_TYPES, fileViewerPath } from "@/lib/utils";
import type { EntityType } from "@/types/mcp";

const LIMIT = 100;
// Tool calls are rate limited (30/minute), so wait for a pause in typing
const DEBOUNCE_MS = 300;

interface DefinitionsBrowserProps {
  repositoryId: number;
  className?: string;
}

/** Every indexed definition, filtered by name and kind, each opening in the file viewer */
export function DefinitionsBrowser({ repositoryId, className }: DefinitionsBrowserProps) {
  const [name, setName] = useState("");
  const [filter, setFilter] = useState("");
  const [entityType, setEntityType] = useState<EntityType | "">("");

  useEffect(() => {
    const timer = setTimeout(() => setFilter(name.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [name]);

  const { data, error, isPending } = useQuery({
    queryKey: ["definitions", repositoryId, filter, entityType],
    queryFn: () =>
      api.listDefinitions(repositoryId, {
        name: filter,
        entity_type: entityType || undefined,
        limit: LIMIT,
      }),
    placeholderData: (previous) => previous, // keep the list while the next filter loads
  });

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span>🧭</span>
          Browse definitions
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Input
            aria-label="Filter definitions by name"
            placeholder="Filter by name..."
            value={name}
            maxLength={200}
            onChange={(e) => setName(e.target.value)}
            className="flex-1 min-w-48"
          />
          <select
            aria-label="Kind of definition"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value as EntityType | "")}
            className="border rounded-md px-2 text-sm bg-background"
          >
            <option value="">All kinds</option>
            {ENTITY_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        {error && (
          <p role="alert" className="text-sm text-red-600">
            {describeError(error).message}
          </p>
        )}
        {isPending && <LoadingSpinner size="sm" />}
        {data && (
          <>
            <p className="text-sm text-muted-foreground" aria-live="polite">
              {data.total > data.definitions.length
                ? `Showing ${data.definitions.length} of ${data.total.toLocaleString()} definitions`
                : `${data.total.toLocaleString()} definitions`}
            </p>
            <ul className="divide-y text-sm">
              {data.definitions.map((d) => (
                <li
                  key={`${d.file_path}:${d.line_start}:${d.entity_type}:${d.entity_name}`}
                  className="py-2 flex flex-wrap items-baseline justify-between gap-x-4"
                >
                  <Link
                    to={fileViewerPath(repositoryId, d.file_path, d.line_start, d.line_end)}
                    className="text-blue-600 hover:underline break-all font-medium"
                  >
                    {d.entity_name}
                  </Link>
                  <span className="text-xs text-muted-foreground break-all">
                    {d.entity_type} · {d.file_path}:{d.line_start}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
