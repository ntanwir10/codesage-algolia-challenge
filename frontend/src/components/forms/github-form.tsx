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

// Accepts owner/repo, a GitHub URL, or a repository URL on another git host.
// Returns the https URL to send, or null. Other hosts are only shape-checked: the server parses them.
function parseRepo(input: string): string | null {
  const raw = input
    .trim()
    .replace(/^git@([^:/\s]+):/i, "https://$1/")
    .replace(/^http:\/\//i, "https://")
    .replace(/\/+$/, "");
  const [, host, rest] = raw.match(/^(?:https:\/\/)?([^/\s@]+)\/(.*)$/i) ?? [];
  // A GitHub owner can't contain a dot, so a dotted first segment is a host
  if (host?.includes(".") && !/^(www\.)?github\.com$/i.test(host)) {
    return /^[^/\s]+(\/[^/\s]+)+$/.test(rest) ? `https://${host}/${rest}` : null;
  }
  const path = raw
    .replace(/^(https:\/\/)?(www\.)?(github\.com\/)?/i, "")
    // Only the repository's clone suffix: a branch in /tree/ may itself end in ".git"
    .replace(/^([\w.-]+\/[\w.-]+?)\.git(?=\/tree\/|$)/, "$1");
  // owner/repo, optionally with /tree/<branch>: the server reads the branch from the URL
  return /^[\w.-]+\/[\w.-]+(\/tree\/[^\s]+)?$/.test(path) ? `https://github.com/${path}` : null;
}

// Validation schema: submits the normalised full URL.
const githubUrlSchema = z.object({
  url: z
    .string()
    .refine(
      (v) => parseRepo(v) !== null,
      "Enter owner/repo for GitHub, or a repository's https URL"
    )
    .transform((v) => parseRepo(v) as string),
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

  // Preview the name the server will give it: owner/repo on GitHub, host/path elsewhere
  const urlValue = watch("url");
  const repoName = ((urlValue && parseRepo(urlValue)) || "").replace(/^https:\/\/(github\.com\/)?/, "");

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
      const { message, status } = describeError(error);
      // A missing or invalid branch belongs under the Branch field, not the URL: a 422 on the
      // branch field, or the server's branch messages. Never a 409, whose text names the repository
      const detail = isAxiosError(error) ? error.response?.data?.detail : undefined;
      const branchField =
        Array.isArray(detail) &&
        detail.some((d: { loc?: unknown }) => Array.isArray(d?.loc) && d.loc.includes("branch"));
      const branchError =
        status !== 409 && (branchField || /^Branch '|invalid branch|branch name/i.test(message));
      if (branchError) setError("branch", { type: "server", message });
      else setError("root.server", { message });
    }
  };

  return (
    <Card className="w-full max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="text-2xl">🚀</span>
          Add Repository
        </CardTitle>
        <CardDescription>
          Enter a GitHub repository (owner/repo), or the https URL of a public
          repository on GitLab, Bitbucket or another git host
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
          <div className="space-y-2">
            <label htmlFor="url" className="text-sm font-medium">
              Repository *
            </label>
            <Input
              id="url"
              placeholder="owner/repo or https://gitlab.com/group/project"
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
              aria-invalid={!!errors.branch}
              aria-describedby={errors.branch ? "branch-error" : undefined}
              className={errors.branch ? "border-destructive" : ""}
            />
            {errors.branch && (
              <p id="branch-error" role="alert" className="text-sm text-destructive">
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
