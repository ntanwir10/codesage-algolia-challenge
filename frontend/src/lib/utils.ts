import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import type { EntityType } from "@/types/mcp"

/** The kinds of definition search and the definitions browser can filter on */
export const ENTITY_TYPES: { value: EntityType; label: string }[] = [
  { value: "function", label: "Functions" },
  { value: "class", label: "Classes and types" },
  { value: "doc_section", label: "Doc sections" },
  { value: "terraform_block", label: "Terraform blocks" },
  { value: "import", label: "Imports" },
]

/** The file viewer's URL for a file, optionally highlighting lines `line`..`end` */
export function fileViewerPath(repositoryId: number, path: string, line?: number | null, end?: number | null) {
  const params = new URLSearchParams({ path })
  if (line) params.set("line", String(line))
  if (line && end && end > line) params.set("end", String(end))
  return `/repository/${repositoryId}/file?${params}`
}

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** True only for absolute http(s) URLs; guards against `javascript:` hrefs. */
export function isHttpUrl(value: string | null | undefined): value is string {
  return !!value && /^https?:\/\//i.test(value);
}

/** "View on GitHub" only for github.com; other hosts get a neutral label. */
export function sourceLabel(url: string) {
  try {
    return new URL(url).hostname === "github.com" ? "View on GitHub" : "View source";
  } catch {
    return "View source";
  }
}
