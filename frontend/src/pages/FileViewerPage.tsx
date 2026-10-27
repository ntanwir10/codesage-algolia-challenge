import { useEffect } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { describeError } from "@/lib/errors";
import { fileViewerPath } from "@/lib/utils";

// get_file returns at most 400 lines per call; the viewer shows one such window at a time
const WINDOW = 400;
// Lines shown above a target line, so it isn't the first thing on screen
const CONTEXT = 20;

/** get_file prefixes each line with its right-aligned number and "| " */
function parseLines(content: string) {
  return content.split("\n").flatMap((row) => {
    const match = /^\s*(\d+)\| ?(.*)$/.exec(row);
    return match ? [{ number: Number(match[1]), text: match[2] }] : [];
  });
}

export function FileViewerPage() {
  const { id } = useParams<{ id: string }>();
  const repositoryId = /^\d+$/.test(id ?? "") ? Number(id) : 0;
  const [params, setParams] = useSearchParams();
  const path = params.get("path") ?? "";
  const line = Number(params.get("line")) || 0;
  const end = Math.max(Number(params.get("end")) || line, line);
  const start = Number(params.get("from")) || Math.max(1, line - CONTEXT);

  const file = useQuery({
    queryKey: ["file", repositoryId, path, start],
    queryFn: () => api.getFile(repositoryId, path, start, start + WINDOW - 1),
    enabled: !!repositoryId && !!path,
    retry: false,
  });
  const outline = useQuery({
    queryKey: ["definitions", repositoryId, "file", path],
    queryFn: () => api.listDefinitions(repositoryId, { path_prefix: path, limit: 500 }),
    enabled: !!repositoryId && !!path,
    retry: false,
  });

  // Bring the highlighted lines into view once they are on the page
  useEffect(() => {
    if (line && file.data) {
      document.getElementById(`L${line}`)?.scrollIntoView?.({ block: "center" });
    }
  }, [line, file.data]);

  const back = repositoryId ? `/repository/${repositoryId}` : "/dashboard";
  const lines = file.data ? parseLines(file.data.content) : [];
  const definitions = (outline.data?.definitions ?? []).filter((d) => d.file_path === path);
  const showFrom = (from: number) => {
    const next = new URLSearchParams(params);
    next.set("from", String(Math.max(1, from)));
    setParams(next);
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto space-y-4">
        <Link to={back} className="text-sm text-blue-600 hover:underline">
          ← Back to repository
        </Link>

        <div className="grid gap-4 lg:grid-cols-[1fr_16rem]">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle className="font-mono text-base break-all">{path || "No file selected"}</CardTitle>
              {file.data && (
                <p className="text-sm text-muted-foreground">
                  {file.data.language ?? "text"} · lines {file.data.start_line}–{file.data.end_line} of{" "}
                  {file.data.total_lines}
                </p>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {file.isPending && !!path && <LoadingSpinner text="Loading file..." />}
              {file.error && (
                <p role="alert" className="text-sm text-red-600 break-words">
                  {describeError(file.error).message}
                </p>
              )}
              {file.data && (
                <>
                  {file.data.start_line > 1 && (
                    <Button variant="outline" size="sm" onClick={() => showFrom(file.data.start_line - WINDOW)}>
                      ↑ Previous {WINDOW} lines
                    </Button>
                  )}
                  <pre className="text-xs font-mono overflow-x-auto bg-gray-50 rounded p-2">
                    {lines.map(({ number, text }) => (
                      <div
                        key={number}
                        id={`L${number}`}
                        className={line && number >= line && number <= end ? "bg-yellow-100" : undefined}
                      >
                        <span className="select-none inline-block w-12 pr-3 text-right text-gray-400">
                          {number}
                        </span>
                        {text}
                      </div>
                    ))}
                  </pre>
                  {file.data.end_line < file.data.total_lines && (
                    <Button variant="outline" size="sm" onClick={() => showFrom(file.data.end_line + 1)}>
                      ↓ Next {WINDOW} lines
                    </Button>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          <Card className="h-fit">
            <CardHeader>
              <CardTitle className="text-base">In this file</CardTitle>
            </CardHeader>
            <CardContent>
              {outline.isPending && !!path && <LoadingSpinner size="sm" />}
              {outline.data && definitions.length === 0 && (
                <p className="text-sm text-muted-foreground">No definitions indexed.</p>
              )}
              <ul className="space-y-1 text-sm">
                {definitions.map((d) => (
                  <li key={`${d.entity_type}:${d.entity_name}:${d.line_start}`}>
                    <Link
                      to={fileViewerPath(repositoryId, path, d.line_start, d.line_end)}
                      className="text-blue-600 hover:underline break-all"
                    >
                      {d.entity_name}
                    </Link>{" "}
                    <span className="text-xs text-muted-foreground">
                      {d.entity_type} · {d.line_start}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
