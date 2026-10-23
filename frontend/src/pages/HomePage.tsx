import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { GitHubForm, type GitHubFormData } from "@/components/forms/github-form";
import { useToast } from "@/components/ui/toast";
import { api } from "@/services/api";
import { describeError } from "@/lib/errors";
import { isAxiosError } from "axios";
import type { CreateRepositoryRequest } from "@/types/repository";

export function HomePage() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const { addToast } = useToast();

  const handleRepositorySubmit = async (data: GitHubFormData) => {
    setIsSubmitting(true);
    try {
      // The server normalises the URL and derives the name; empty optional
      // fields are omitted (an empty branch means the default branch).
      const createRequest: CreateRepositoryRequest = { url: data.url.trim() };
      const branch = data.branch?.trim();
      if (branch) createRequest.branch = branch;
      const description = data.description?.trim();
      if (description) createRequest.description = description;

      const repository = await api.createRepository(createRequest);
      addToast({
        type: "success",
        title: "Repository added",
        description: "Processing has started. Progress appears on this page.",
      });
      navigate(`/repository/${repository.id}`);
    } catch (error: unknown) {
      const { message, status } = describeError(error);
      // 422 details are shown inline by the form; everything else is toasted.
      const inlineByForm =
        status === 422 &&
        isAxiosError(error) &&
        Array.isArray(error.response?.data?.detail);
      if (!inlineByForm) {
        addToast({
          type: status === 409 ? "warning" : "error",
          title:
            status === 409
              ? "Repository already exists"
              : status === 429
              ? "Slow down"
              : "Failed to add repository",
          description: message,
          duration: 8000,
        });
      }
      // Rethrow so the form keeps the user's input.
      throw error;
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
