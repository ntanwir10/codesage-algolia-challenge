import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { GitHubForm } from "@/components/forms/github-form";
import { api } from "@/services/api";
import type { CreateRepositoryRequest } from "@/types/repository";

export function HomePage() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();

  const handleRepositorySubmit = async (data: {
    url: string;
    branch: string;
    description?: string;
  }) => {
    setIsSubmitting(true);
    try {
      // Extract repository name from URL for the API
      const urlParts = data.url.match(/github\.com\/([^/]+)\/([^/]+)/);

      if (!urlParts) {
        throw new Error(
          "Invalid GitHub URL format. Please use: https://github.com/owner/repository"
        );
      }

      const name = `${urlParts[1]}/${urlParts[2].replace(/\.git$/, "")}`;

      const createRequest: CreateRepositoryRequest = {
        name: name.trim(),
        description: data.description?.trim() || `Repository from ${data.url}`,
        url: data.url.trim(),
        branch: (data.branch || "main").trim(),
      };

      console.log("🔍 Form data received:", data);
      console.log("🔍 Parsed URL parts:", urlParts);
      console.log("🚀 Creating repository with request:", createRequest);

      const repository = await api.createRepository(createRequest);
      console.log("✅ Repository created successfully:", repository);

      // Start processing the repository
      const processingStatus = await api.processRepository(repository.id);
      console.log("🔄 Processing started:", processingStatus);

      // Navigate to repository detail page
      navigate(`/repository/${repository.id}`);
    } catch (error: unknown) {
      console.error("❌ Repository creation error:", error);

      let errorMessage = "Failed to create repository. Please try again.";

      // Type guard for axios error
      if (error && typeof error === "object" && "response" in error) {
        const axiosError = error as {
          response?: { status?: number; data?: unknown };
        };
        if (axiosError.response?.status === 400) {
          const errorData = axiosError.response?.data;
          if (typeof errorData === "string") {
            errorMessage = `Validation error: ${errorData}`;
          } else if (
            errorData &&
            typeof errorData === "object" &&
            "detail" in errorData
          ) {
            errorMessage = `Validation error: ${JSON.stringify(
              errorData.detail
            )}`;
          } else if (
            errorData &&
            typeof errorData === "object" &&
            "message" in errorData
          ) {
            const msgData = errorData as { message: string };
            errorMessage = `Error: ${msgData.message}`;
          }
        }
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }

      alert(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Hero Section */}
        <div className="text-center space-y-4">
          <h2 className="text-4xl font-bold tracking-tight">
            Discover Code with AI
          </h2>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Submit a GitHub repository URL and ask natural language questions
            about your code. Powered by Algolia search and MCP server
            integration.
          </p>
        </div>

        {/* GitHub Form */}
        <GitHubForm
          onSubmit={handleRepositorySubmit}
          isLoading={isSubmitting}
        />

        {/* Quick Start Guide */}
        <div className="bg-muted/50 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">How it works:</h3>
          <div className="grid md:grid-cols-3 gap-4">
            <div className="text-center space-y-2">
              <div className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center mx-auto font-bold">
                1
              </div>
              <h4 className="font-medium">Submit Repository</h4>
              <p className="text-sm text-muted-foreground">
                Enter a GitHub URL and we'll clone and analyze your code
              </p>
            </div>
            <div className="text-center space-y-2">
              <div className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center mx-auto font-bold">
                2
              </div>
              <h4 className="font-medium">AI Processing</h4>
              <p className="text-sm text-muted-foreground">
                Our MCP server indexes your code with Algolia for intelligent
                search
              </p>
            </div>
            <div className="text-center space-y-2">
              <div className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center mx-auto font-bold">
                3
              </div>
              <h4 className="font-medium">Ask Questions</h4>
              <p className="text-sm text-muted-foreground">
                Use natural language to explore and understand your codebase
              </p>
            </div>
          </div>
        </div>

        {/* Features Preview */}
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-card border rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-2">🔍 Smart Search</h3>
            <p className="text-muted-foreground">
              Ask questions like "How does authentication work?" or "Find all
              API endpoints" and get contextual answers from your codebase.
            </p>
          </div>
          <div className="bg-card border rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-2">📁 File Explorer</h3>
            <p className="text-muted-foreground">
              Browse your repository structure, view file contents, and
              understand the relationships between different components.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
