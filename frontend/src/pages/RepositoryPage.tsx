import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { RepositoryStats } from "@/components/features/repository-stats";
import { SearchInterface } from "@/components/features/search-interface";
import { AnimatedProgress } from "@/components/ui/animated-progress";
import { DeleteConfirmationDialog } from "@/components/ui/delete-confirmation-dialog";
import { useRealtimeStatus } from "@/hooks/useRealtimeStatus";
import { useToast } from "@/components/ui/toast";
import { describeError } from "@/lib/errors";
import { isActiveStatus, pollWhileActive } from "@/lib/polling";
import { isHttpUrl, sourceLabel } from "@/lib/utils";

// Stop polling once the repository is gone: react-query keeps the last good data
// (still "processing") after a 404, which would otherwise keep the interval alive.
const pollUnlessGone = (query: {
  state: { data: { status: string } | undefined; error: unknown };
}) =>
  query.state.error && describeError(query.state.error).status === 404
    ? false
    : pollWhileActive(query.state.data);

export function RepositoryPage() {
  const { id } = useParams<{ id: string }>();
  // Strict: parseInt would load repo 12 for "12abc". 0 means invalid.
  const repositoryId = /^\d+$/.test(id ?? "") ? Number(id) : 0;
  const navigate = useNavigate();

  const [deleteDialog, setDeleteDialog] = useState<{
    isOpen: boolean;
    isDeleting: boolean;
  }>({
    isOpen: false,
    isDeleting: false,
  });

  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const [isReprocessing, setIsReprocessing] = useState(false);

  // Poll every ~3s while pending/processing; stops once completed/failed.
  const {
    data: repository,
    isLoading: isRepoLoading,
    error: repoError,
    refetch,
  } = useQuery({
    queryKey: ["repository", repositoryId],
    queryFn: () => api.getRepository(repositoryId),
    enabled: !!repositoryId,
    refetchInterval: pollUnlessGone,
  });

  // Live updates: subscribe while the repository is being processed.
  const repositoryIds = useMemo(
    () => (repositoryId ? [repositoryId] : []),
    [repositoryId]
  );
  const { connectionStatus } = useRealtimeStatus({ repositoryIds });

  const handleDeleteClick = () => {
    setDeleteDialog({
      isOpen: true,
      isDeleting: false,
    });
  };

  const handleDeleteConfirm = async () => {
    if (!repository) return;

    setDeleteDialog((prev) => ({ ...prev, isDeleting: true }));

    try {
      try {
        await api.deleteRepository(repository.id);
      } catch (error) {
        // Already gone (e.g. deleted in another tab): same outcome as success.
        if (describeError(error).status !== 404) throw error;
      }

      addToast({ type: "success", title: "Repository deleted" });
      // Don't remove this page's queries: its observers would refetch the deleted repository
      // (404s) before navigating unmounts them. Once unmounted they're inactive and expire.
      navigate("/dashboard");
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
    } catch (error) {
      const { message, status: httpStatus } = describeError(error);
      setDeleteDialog({ isOpen: false, isDeleting: false });
      if (httpStatus === 401) return; // the global auth toast covers it
      addToast({
        type: "error",
        title:
          httpStatus === 409
            ? "Cannot delete while processing"
            : httpStatus === 502
            ? "Delete failed; nothing was deleted"
            : "Failed to delete repository",
        description: message,
        duration: 8000,
      });
    }
  };

  const handleDeleteCancel = () => {
    setDeleteDialog({
      isOpen: false,
      isDeleting: false,
    });
  };

  const handleReprocess = async () => {
    if (!repository) return;
    setIsReprocessing(true);
    try {
      await api.reprocessRepository(repository.id);
      addToast({
        type: "success",
        title: "Reprocessing started",
        description: "The repository will be re-analyzed and re-indexed.",
      });
      queryClient.invalidateQueries({ queryKey: ["repository", repositoryId] });
      queryClient.invalidateQueries({ queryKey: ["repository-stats", repositoryId] });
    } catch (error) {
      const { message, status: httpStatus } = describeError(error);
      if (httpStatus === 401) return; // the global auth toast covers it
      addToast({
        type: httpStatus === 409 ? "warning" : "error",
        title:
          httpStatus === 409
            ? "Reprocessing not started"
            : "Failed to start reprocessing",
        description: message,
        duration: 8000,
      });
    } finally {
      setIsReprocessing(false);
    }
  };

  if (isRepoLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <LoadingSpinner
            size="lg"
            text="Loading repository details..."
            className="py-16"
          />
        </div>
      </div>
    );
  }

  // A 404 beats stale cached data (deleted in another tab); other background
  // poll failures keep the old data and only show an error when there is none.
  const described = repoError ? describeError(repoError) : null;
  if (!repositoryId || described?.status === 404 || (!repository && !described)) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <EmptyState
            icon="❌"
            title="Repository not found"
            description="The repository you're looking for doesn't exist or you don't have access to it."
            action={{
              label: "Back to Dashboard",
              href: "/dashboard",
            }}
          />
        </div>
      </div>
    );
  }

  if (!repository) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <EmptyState
            icon="⚠️"
            title="Couldn't load this repository"
            description={described?.message ?? ""}
            action={{ label: "Try again", onClick: () => refetch() }}
          />
        </div>
      </div>
    );
  }

  const canSearch = repository.status === "completed";

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Breadcrumb */}
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <Link
            to="/dashboard"
            className="hover:text-foreground transition-colors"
          >
            Dashboard
          </Link>
          <span>/</span>
          <span className="text-foreground font-medium break-all">{repository.name}</span>
          {connectionStatus === "connected" && (
            <>
              <span>/</span>
              <span className="text-green-600 flex items-center gap-1">
                🔄 Live updates
              </span>
            </>
          )}
        </div>

        {/* Repository Header */}
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex items-start gap-4 min-w-0">
            <div className="p-3 bg-blue-100 rounded-lg">
              <span className="text-3xl">📂</span>
            </div>
            <div className="min-w-0">
              <h1 className="text-3xl font-bold break-words">{repository.name}</h1>
              {repository.description && (
                <p className="text-muted-foreground mt-1 text-lg">
                  {repository.description}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3">
                {isHttpUrl(repository.url) && (
                  <a
                    href={repository.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:underline font-medium break-all"
                  >
                    {sourceLabel(repository.url)} →
                  </a>
                )}
                <span className="text-sm text-muted-foreground">
                  Created {new Date(repository.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={repository.status} />
            <Button
              variant="outline"
              size="sm"
              onClick={handleDeleteClick}
              className="text-red-600 hover:text-red-700 hover:bg-red-50"
              title="Delete repository"
            >
              <span className="mr-1">🗑️</span>
              Delete
            </Button>
          </div>
        </div>

        {/* Repository Stats */}
        <RepositoryStats repository={repository} />

        {/* Processing Status */}
        {isActiveStatus(repository.status) && (
          <Card className="border-blue-200 bg-blue-50/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <span className="animate-spin">⏳</span>
                Processing Status
                {connectionStatus === "connected" && (
                  <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                    Live Updates
                  </span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {(() => {
                  // The WebSocket patches these into the cached repository as batches land
                  const processed = repository.processed_files;
                  const total = repository.total_files;
                  return total > 0 && processed > 0 ? (
                    <div>
                      <AnimatedProgress
                        value={(processed / total) * 100}
                        showLabel={true}
                        animated={true}
                        color="blue"
                        size="lg"
                      />
                      <div className="text-sm mt-2 text-muted-foreground">
                        {processed} / {total} files
                      </div>
                    </div>
                  ) : (
                    <AnimatedProgress
                      value={0}
                      indeterminate={true}
                      animated={true}
                      color="blue"
                      size="lg"
                    />
                  );
                })()}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Completion Status: amber when the run left files out (error_message says which) */}
        {repository.status === "completed" && (
          <Card
            className={
              repository.error_message
                ? "border-amber-200 bg-amber-50/50"
                : "border-green-200 bg-green-50/50"
            }
          >
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <span className="text-2xl">
                  {repository.error_message ? "⚠️" : "🎉"}
                </span>
                <div>
                  <p
                    className={
                      repository.error_message
                        ? "font-medium text-amber-700"
                        : "font-medium text-green-700"
                    }
                  >
                    {repository.error_message
                      ? "Repository partially indexed"
                      : "Repository analysis complete!"}
                  </p>
                  {repository.error_message ? (
                    <p className="mt-1 text-sm text-muted-foreground">
                      {repository.error_message}
                    </p>
                  ) : (
                    <p className="text-sm text-green-600">
                      Your repository is ready for AI-powered search and
                      exploration.
                      {connectionStatus === "connected" && (
                        <span className="ml-1">Real-time updates enabled.</span>
                      )}
                    </p>
                  )}
                  <Button
                    variant="outline"
                    className="mt-2"
                    onClick={handleReprocess}
                    disabled={isReprocessing}
                  >
                    {isReprocessing ? "Reprocessing..." : "Reprocess"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Error Status */}
        {repository.status === "failed" && (
          <Card className="border-red-200 bg-red-50/50">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <span className="text-2xl">❌</span>
                <div>
                  <p className="font-medium text-red-700">Processing failed</p>
                  <p className="text-sm text-red-600">
                    There was an error processing this repository. You can try
                    reprocessing it.
                  </p>
                  {repository.error_message && (
                    <p className="mt-1 text-sm text-red-700">
                      {repository.error_message}
                    </p>
                  )}
                  <Button
                    variant="outline"
                    className="mt-2"
                    onClick={handleReprocess}
                    disabled={isReprocessing}
                  >
                    {isReprocessing ? "Reprocessing..." : "Reprocess"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* AI Search Interface */}
        {/* Keyed so results and in-flight searches never carry over to another repository */}
        <SearchInterface
          key={repositoryId}
          repositoryId={repositoryId}
          canSearch={!!canSearch}
          status={repository.status}
        />

        {/* Quick Actions */}
        <div className="flex flex-wrap gap-4">
          <Link to="/dashboard">
            <Button variant="outline" className="gap-2">
              ← Back to Dashboard
            </Button>
          </Link>
          {isHttpUrl(repository.url) && (
            <a href={repository.url} target="_blank" rel="noopener noreferrer">
              <Button variant="outline" className="gap-2">
                <span>🔗</span>
                {sourceLabel(repository.url)}
              </Button>
            </a>
          )}
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        isDeleting={deleteDialog.isDeleting}
        title="Delete Repository"
        description={
          repository
            ? `Are you sure you want to delete "${repository.name}"? This action cannot be undone and will remove all associated data including search indexes and files.`
            : ""
        }
        confirmText="Delete Repository"
        variant="danger"
      />
    </div>
  );
}
