import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { isAxiosError } from "axios";
import { z } from "zod";
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
    .min(1, "GitHub URL is required")
    .url("Must be a valid URL")
    .regex(
      /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/,
      "Must be a valid GitHub repository URL (https://github.com/owner/repo)"
    ),
  branch: z.string().min(1, "Branch is required"),
  description: z.string().optional(),
});

type GitHubFormData = z.infer<typeof githubUrlSchema>;

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
  } = useForm<GitHubFormData>({
    resolver: zodResolver(githubUrlSchema),
    defaultValues: {
      url: "",
      branch: "main",
      description: "",
    },
    mode: "onChange",
  });

  // Watch URL to extract repository name
  const urlValue = watch("url");
  const repoName = urlValue ? extractRepoName(urlValue) : "";

  const handleFormSubmit = async (data: GitHubFormData) => {
    try {
      await onSubmit(githubUrlSchema.parse(data));
      reset();
    } catch (error) {
      // Keep the user's input; surface server-side validation messages
      const detail = isAxiosError(error)
        ? error.response?.data?.detail
        : undefined;
      if (isAxiosError(error) && error.response?.status === 422 && Array.isArray(detail)) {
        const messages = detail
          .map((d: { msg?: string }) => d?.msg)
          .filter(Boolean)
          .join("; ");
        setError("root.server", { message: messages || "Validation failed" });
      } else {
        console.error("Submit error:", error);
      }
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
              {...register("url")}
              className={errors.url ? "border-destructive" : ""}
            />
            {errors.url && (
              <p className="text-sm text-destructive">{errors.url.message}</p>
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
              placeholder="main"
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

          {errors.root?.server && (
            <p role="alert" className="text-sm text-destructive">
              {errors.root.server.message}
            </p>
          )}

          <Button
            type="submit"
            className="w-full"
            disabled={!isValid || isLoading}
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <span className="animate-spin">⏳</span>
                Processing...
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
