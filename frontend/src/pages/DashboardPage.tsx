import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";
import { api } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { AnimatedProgress } from "@/components/ui/animated-progress";
import { DeleteConfirmationDialog } from "@/components/ui/delete-confirmation-dialog";
import type { Repository } from "@/types/repository";

export function DashboardPage() {
  const [deleteDialog, setDeleteDialog] = useState<{
    isOpen: boolean;
    repository: Repository | null;
    isDeleting: boolean;
  }>({
    isOpen: false,
    repository: null,
    isDeleting: false,
  });

  const {
    data: repositories = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["repositories"],
    queryFn: () => api.getRepositories(),
  });

  // Enable real-time updates for all repositories
  // Note: Notifications are handled globally in Layout.tsx

  const handleDeleteClick = (repository: Repository) => {
    setDeleteDialog({
      isOpen: true,
      repository,
      isDeleting: false,
    });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteDialog.repository) return;

    setDeleteDialog((prev) => ({ ...prev, isDeleting: true }));

    try {
      await api.deleteRepository(deleteDialog.repository.id);

      // Close dialog and refresh repository list
      setDeleteDialog({
        isOpen: false,
        repository: null,
        isDeleting: false,
      });

      // Refresh the repository list
      refetch();

      console.log("✅ Repository deleted successfully");
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
      repository: null,
      isDeleting: false,
    });
  };

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <LoadingSpinner
            size="lg"
            text="Loading your repositories..."
            className="py-16"
          />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <EmptyState
            icon="❌"
            title="Failed to load repositories"
            description="There was an error loading your repositories. Please try again."
            action={{
              label: "Try Again",
              onClick: () => refetch(),
            }}
          />
        </div>
      </div>
    );
  }

  const stats = {
    total: repositories.length,
    completed: repositories.filter((r) => r.status === "completed").length,
    processing: repositories.filter((r) => r.status === "processing").length,
    failed: repositories.filter((r) => r.status === "failed").length,
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold">Repository Dashboard</h1>
            <p className="text-muted-foreground">
              Manage and explore your code repositories with real-time updates
            </p>
          </div>
          <Link to="/">
            <Button className="gap-2">
              <span>+</span>
              Add Repository
            </Button>
          </Link>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <span className="text-2xl">📊</span>
                </div>
                <div>
                  <div className="text-2xl font-bold">{stats.total}</div>
                  <div className="text-sm text-muted-foreground">
                    Total Repositories
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 rounded-lg">
                  <span className="text-2xl">✅</span>
                </div>
                <div>
                  <div className="text-2xl font-bold text-green-600">
                    {stats.completed}
                  </div>
                  <div className="text-sm text-muted-foreground">Completed</div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <span className="text-2xl">⏳</span>
                </div>
                <div>
                  <div className="text-2xl font-bold text-blue-600">
                    {stats.processing}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Processing
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-red-100 rounded-lg">
                  <span className="text-2xl">❌</span>
                </div>
                <div>
                  <div className="text-2xl font-bold text-red-600">
                    {stats.failed}
                  </div>
                  <div className="text-sm text-muted-foreground">Failed</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Repository List */}
        {repositories.length === 0 ? (
          <Card>
            <CardContent>
              <EmptyState
                icon="📁"
                title="No repositories yet"
                description="Get started by adding your first GitHub repository to analyze with AI-powered search"
                action={{
                  label: "Add Your First Repository",
                  href: "/",
                }}
              />
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold">Your Repositories</h2>
              {stats.processing > 0 && (
                <div className="text-sm text-muted-foreground">
                  🔄 {stats.processing} repositories processing
                </div>
              )}
            </div>

            {repositories.map((repo) => (
              <Card
                key={repo.id}
                className="hover:shadow-lg transition-all duration-200"
              >
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-gray-100 rounded-lg">
                        <span className="text-2xl">📂</span>
                      </div>
                      <div>
                        <CardTitle className="text-lg">{repo.name}</CardTitle>
                        {repo.description && (
                          <p className="text-sm text-muted-foreground mt-1">
                            {repo.description}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <StatusBadge status={repo.status} />
                      <div className="flex items-center gap-2">
                        <Link to={`/repository/${repo.id}`}>
                          <Button variant="outline" size="sm">
                            View Details
                          </Button>
                        </Link>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDeleteClick(repo)}
                          className="text-red-600 hover:text-red-700 hover:bg-red-50"
                          title="Delete repository"
                        >
                          <span className="text-sm">🗑️</span>
                        </Button>
                      </div>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500">📄</span>
                      <span>
                        <strong>{repo.total_files}</strong> files
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500">🔢</span>
                      <span>
                        <strong>{repo.total_lines.toLocaleString()}</strong>{" "}
                        lines
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500">💻</span>
                      <span>
                        <strong>{repo.language || "Unknown"}</strong>
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500">🌿</span>
                      <span>
                        <strong>{repo.branch}</strong>
                      </span>
                    </div>
                  </div>

                  {/* Enhanced Processing Progress */}
                  {repo.status === "processing" && repo.processed_files > 0 && (
                    <div className="mt-4">
                      <AnimatedProgress
                        value={(repo.processed_files / repo.total_files) * 100}
                        showLabel={true}
                        animated={true}
                        color="blue"
                        size="md"
                      />
                      <div className="flex items-center justify-between text-xs text-muted-foreground mt-1">
                        <span>
                          {repo.processed_files} / {repo.total_files} files
                          processed
                        </span>
                        <span className="animate-pulse">🔄 Live updates</span>
                      </div>
                    </div>
                  )}

                  {/* Indeterminate progress for starting repositories */}
                  {repo.status === "processing" &&
                    repo.processed_files === 0 && (
                      <div className="mt-4">
                        <AnimatedProgress
                          value={0}
                          indeterminate={true}
                          animated={true}
                          color="blue"
                          size="md"
                        />
                      </div>
                    )}

                  {/* Repository URL */}
                  {repo.url && (
                    <div className="mt-3 pt-3 border-t">
                      <a
                        href={repo.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-blue-600 hover:underline"
                      >
                        View on GitHub →
                      </a>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        isDeleting={deleteDialog.isDeleting}
        title="Delete Repository"
        description={
          deleteDialog.repository
            ? `Are you sure you want to delete "${deleteDialog.repository.name}"? This action cannot be undone and will remove all associated data including search indexes.`
            : ""
        }
        confirmText="Delete Repository"
        variant="danger"
      />
    </div>
  );
}
