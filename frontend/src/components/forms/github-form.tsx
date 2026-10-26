import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { isAxiosError } from "axios";
import { z } from "zod";
import { describeError } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// Validation schema
const githubUrlSchema = z.object({
  url: z
    .string()
    .trim()
    .min(1, "GitHub URL is required")
    .url("Must be a valid URL")
    .regex(
      /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/,
      "Must be a valid GitHub repository URL (https://github.com/owner/repo)"
    ),
  // Empty means "use the repository's default branch"; never sent when empty.
  branch: z.string().optional(),
  description: z.string().optional(),
});

type GitHubFormData = z.infer<typeof githubUrlSchema>;

export type { GitHubFormData };

interface GitHubFormProps {
  onSubmit: (data: GitHubFormData) => void | Promise<void>;
  isLoading?: boolean;
}

export function GitHubForm({ onSubmit, isLoading = false }: GitHubFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
    reset,
    watch,
    setError,
    clearErrors,
  } = useForm<GitHubFormData>({
    resolver: zodResolver(githubUrlSchema),
    defaultValues: {
      url: "",
      branch: "",
      description: "",
    },
    mode: "onChange",
  });

  // Set when the server says the repo already exists (409), to link to it.
  const [existingId, setExistingId] = useState<number>();

  // Watch URL to extract repository name
  const urlValue = watch("url");
  const repoName = urlValue ? extractRepoName(urlValue) : "";

  const urlField = register("url");
  const serverError = errors.root?.server;
  const errorId = errors.url
    ? "url-error"
    : serverError
    ? "url-server-error"
    : undefined;

  const handleFormSubmit = async (data: GitHubFormData) => {
    try {
      await onSubmit(githubUrlSchema.parse(data));
      reset();
    } catch (error) {
      // Keep the user's input and show the failure under the URL field.
      setExistingId(undefined);
      if (isAxiosError(error) && error.response?.status === 409) {
        const id = error.response.data?.repository_id;
        if (typeof id === "number") setExistingId(id);
      }
      setError("root.server", { message: describeError(error).message });
    }
  };

  return (
    <Card className="w-full max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="text-2xl">🚀</span>
          Add GitHub Repository
        </CardTitle>
        <CardDescription>
          Enter a GitHub repository URL to index and analyze with AI
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
          <div className="space-y-2">
            <label htmlFor="url" className="text-sm font-medium">
              GitHub Repository URL *
            </label>
            <Input
              id="url"
              placeholder="https://github.com/owner/repository"
              {...urlField}
              onChange={(e) => {
                clearErrors("root.server");
                setExistingId(undefined);
                return urlField.onChange(e);
              }}
              aria-invalid={!!(errors.url || serverError)}
              aria-describedby={errorId}
              className={errors.url ? "border-destructive" : ""}
            />
            {errors.url && (
              <p id="url-error" className="text-sm text-destructive">
                {errors.url.message}
              </p>
            )}
            {serverError && (
              <p
                id="url-server-error"
                role="alert"
                className="text-sm text-destructive"
              >
                {serverError.message}
                {existingId !== undefined && (
                  <>
                    {" "}
                    <Link
                      to={`/repository/${existingId}`}
                      className="underline font-medium"
                    >
                      Open it
                    </Link>
                  </>
                )}
              </p>
            )}
            {repoName && !errors.url && (
              <p className="text-sm text-muted-foreground">
                Repository: <strong>{repoName}</strong>
              </p>
            )}
          </div>

          <div className="space-y-2">
            <label htmlFor="branch" className="text-sm font-medium">
              Branch
            </label>
            <Input
              id="branch"
              placeholder="Default branch (leave empty)"
              {...register("branch")}
              className={errors.branch ? "border-destructive" : ""}
            />
            {errors.branch && (
              <p className="text-sm text-destructive">
                {errors.branch.message}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <label htmlFor="description" className="text-sm font-medium">
              Description (optional)
            </label>
            <Input
              id="description"
              placeholder="Brief description of the repository..."
              {...register("description")}
            />
          </div>

          <Button
            type="submit"
            className="w-full"
            disabled={!isValid || isLoading}
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <span className="animate-spin">⏳</span>
                Checking repository…
              </span>
            ) : (
              "Add Repository"
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// Helper function to extract repository name from GitHub URL
function extractRepoName(url: string): string {
  try {
    const match = url.match(/github\.com\/([^/]+)\/([^/]+)/);
    if (match) {
      return `${match[1]}/${match[2].replace(/\.git$/, "")}`;
    }
    return "";
  } catch {
    return "";
  }
}
