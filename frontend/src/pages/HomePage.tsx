import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { GitHubForm, type GitHubFormData } from "@/components/forms/github-form";
import { useToast } from "@/components/ui/toast";
import { api } from "@/services/api";
import type { CreateRepositoryRequest } from "@/types/repository";

export function HomePage() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const { addToast } = useToast();
  const queryClient = useQueryClient();

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
      // staleTime is 5 min, so without this the dashboard would miss the new repo.
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
      addToast({
        type: "success",
        title: "Repository added",
        description: "Processing has started. Progress appears on this page.",
      });
      navigate(`/repository/${repository.id}`);
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
            Add a GitHub repository, search its code here, and let Claude
            answer questions about it through MCP. Powered by Algolia search.
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
                Enter owner/repo and we'll fetch and parse its code
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
              <h4 className="font-medium">Search and Ask Claude</h4>
              <p className="text-sm text-muted-foreground">
                Search definitions here, or ask Claude about the code
              </p>
            </div>
          </div>
        </div>

        {/* Features Preview */}
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-card border rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-2">🔍 Smart Search</h3>
            <p className="text-muted-foreground">
              Search names like "authMiddleware" or "createStore", including
              part of a camelCase name. Ask Claude "How does authentication
              work?" and it searches the index for you.
            </p>
          </div>
          <div className="bg-card border rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-2">🤖 Claude Desktop</h3>
            <p className="text-muted-foreground">
              Connect Claude Desktop over MCP to search code, read files, list
              definitions and find patterns in your indexed repositories.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
