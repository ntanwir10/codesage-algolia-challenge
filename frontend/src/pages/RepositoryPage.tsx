import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
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

export function RepositoryPage() {
  const { id } = useParams<{ id: string }>();
  const repositoryId = parseInt(id || "0");
  const navigate = useNavigate();

  const [deleteDialog, setDeleteDialog] = useState<{
    isOpen: boolean;
    isDeleting: boolean;
  }>({
    isOpen: false,
    isDeleting: false,
  });

  const {
    data: repository,
    isLoading: isRepoLoading,
    error: repoError,
  } = useQuery({
    queryKey: ["repository", repositoryId],
    queryFn: () => api.getRepository(repositoryId),
    enabled: !!repositoryId,
  });

  const { data: status } = useQuery({
    queryKey: ["repository-status", repositoryId],
    queryFn: () => api.getRepositoryStatus(repositoryId),
    enabled: !!repositoryId,
    refetchInterval: repository?.status === "processing" ? 5000 : false, // Poll every 5 seconds when processing
  });

  // Enable real-time updates for this specific repository
  const { connectionStatus } = useRealtimeStatus({
    repositoryId,
    enableNotifications: false, // Notifications handled globally
  });

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
      await api.deleteRepository(repository.id);

      console.log("✅ Repository deleted successfully");

      // Navigate back to dashboard
      navigate("/dashboard");
    } catch (error) {
      console.error("❌ Failed to delete repository:", error);
      setDeleteDialog((prev) => ({ ...prev, isDeleting: false }));

      // Show error message (you could replace this with a toast notification)
      alert("Failed to delete repository. Please try again.");
    }
  };

  const handleDeleteCancel = () => {
    setDeleteDialog({
      isOpen: false,
      isDeleting: false,
    });
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

  if (repoError || !repository) {
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

  const canSearch = repository.status === "completed" && status?.mcp_ready;

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link
            to="/dashboard"
            className="hover:text-foreground transition-colors"
          >
            Dashboard
          </Link>
          <span>/</span>
          <span className="text-foreground font-medium">{repository.name}</span>
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
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-blue-100 rounded-lg">
              <span className="text-3xl">📂</span>
            </div>
            <div>
              <h1 className="text-3xl font-bold">{repository.name}</h1>
              {repository.description && (
                <p className="text-muted-foreground mt-1 text-lg">
                  {repository.description}
                </p>
              )}
              <div className="flex items-center gap-4 mt-3">
                {repository.url && (
                  <a
                    href={repository.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:underline font-medium"
                  >
                    View on GitHub →
                  </a>
                )}
                <span className="text-sm text-muted-foreground">
                  Created {new Date(repository.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
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
        {status && repository.status === "processing" && (
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
                <p className="text-sm text-muted-foreground">
                  {status.message}
                </p>

                {repository.processed_files > 0 ? (
                  <div>
                    <AnimatedProgress
                      value={
                        (repository.processed_files / repository.total_files) *
                        100
                      }
                      showLabel={true}
                      animated={true}
                      color="blue"
                      size="lg"
                    />
                    <div className="flex items-center justify-between text-sm mt-2">
                      <span className="text-muted-foreground">
                        {repository.processed_files} / {repository.total_files}{" "}
                        files
                      </span>
                      <span className="text-xs text-blue-600">
                        ETA: ~
                        {Math.ceil(
                          (repository.total_files -
                            repository.processed_files) /
                            10
                        )}{" "}
                        min
                      </span>
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
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <span
                      className={
                        status.algolia_indexed
                          ? "text-green-600"
                          : "text-gray-400"
                      }
                    >
                      {status.algolia_indexed ? "✅" : "⏳"}
                    </span>
                    <span>Algolia Search Index</span>
                    {status.algolia_indexed &&
                      connectionStatus === "connected" && (
                        <span className="text-xs text-green-600">Live</span>
                      )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={
                        status.mcp_ready ? "text-green-600" : "text-gray-400"
                      }
                    >
                      {status.mcp_ready ? "✅" : "⏳"}
                    </span>
                    <span>MCP AI Integration</span>
                    {status.mcp_ready && connectionStatus === "connected" && (
                      <span className="text-xs text-green-600">Live</span>
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Completion Status */}
        {repository.status === "completed" && (
          <Card className="border-green-200 bg-green-50/50">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <span className="text-2xl">🎉</span>
                <div>
                  <p className="font-medium text-green-700">
                    Repository analysis complete!
                  </p>
                  <p className="text-sm text-green-600">
                    Your repository is ready for AI-powered search and
                    exploration.
                    {connectionStatus === "connected" && (
                      <span className="ml-1">Real-time updates enabled.</span>
                    )}
                  </p>
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
                    {status?.message ||
                      "There was an error processing this repository."}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* AI Search Interface */}
        <SearchInterface repositoryId={repositoryId} canSearch={!!canSearch} />

        {/* Quick Actions */}
        <div className="flex flex-wrap gap-4">
          <Link to="/dashboard">
            <Button variant="outline" className="gap-2">
              ← Back to Dashboard
            </Button>
          </Link>
          {repository.url && (
            <a href={repository.url} target="_blank" rel="noopener noreferrer">
              <Button variant="outline" className="gap-2">
                <span>🔗</span>
                View on GitHub
              </Button>
            </a>
          )}
          {canSearch && (
            <Button variant="outline" className="gap-2">
              <span>📁</span>
              Browse Files
            </Button>
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
