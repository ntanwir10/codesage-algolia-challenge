import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { queryClient } from "@/lib/queryClient";
import { GitHubForm } from "@/components/forms/github-form";
import { api } from "@/services/api";
import type { CreateRepositoryRequest } from "@/types/repository";
import { useState } from "react";

function App() {
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleRepositorySubmit = async (data: {
    url: string;
    branch: string;
    description?: string;
  }) => {
    setIsSubmitting(true);
    try {
      // Extract repository name from URL for the API
      const urlParts = data.url.match(/github\.com\/([^/]+)\/([^/]+)/);
      const name = urlParts
        ? `${urlParts[1]}/${urlParts[2].replace(/\.git$/, "")}`
        : "unknown-repo";

      const createRequest: CreateRepositoryRequest = {
        name,
        description: data.description || `Repository from ${data.url}`,
        url: data.url,
        branch: data.branch || "main",
      };

      console.log("Creating repository:", createRequest);

      const repository = await api.createRepository(createRequest);
      console.log("Repository created:", repository);

      // Start processing the repository
      const processingStatus = await api.processRepository(repository.id);
      console.log("Processing started:", processingStatus);

      // TODO: Show success message and redirect to repository status page
      alert(
        `Repository "${repository.name}" created successfully! Processing started.`
      );
    } catch (error) {
      console.error("Error creating repository:", error);
      // TODO: Show error message
      alert("Failed to create repository. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-background">
        {/* Header */}
        <header className="border-b">
          <div className="container mx-auto px-4 py-6">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold text-foreground">CodeSage</h1>
                <p className="text-muted-foreground">
                  AI-Powered Code Discovery Platform
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  Powered by Algolia MCP Server
                </span>
              </div>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="container mx-auto px-4 py-8">
          <div className="max-w-4xl mx-auto space-y-8">
            {/* Hero Section */}
            <div className="text-center space-y-4">
              <h2 className="text-4xl font-bold tracking-tight">
                Discover Code with AI
              </h2>
              <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
                Submit a GitHub repository URL and ask natural language
                questions about your code. Powered by Algolia search and MCP
                server integration.
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
                    Our MCP server indexes your code with Algolia for
                    intelligent search
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
          </div>
        </main>

        {/* Footer */}
        <footer className="border-t mt-16">
          <div className="container mx-auto px-4 py-6 text-center text-muted-foreground">
            <p>
              Built with React, TypeScript, TailwindCSS, and Algolia MCP Server
            </p>
          </div>
        </footer>
      </div>

      {/* React Query Devtools */}
      {import.meta.env.VITE_ENABLE_DEV_TOOLS === "true" && (
        <ReactQueryDevtools initialIsOpen={false} />
      )}
    </QueryClientProvider>
  );
}

export default App;
