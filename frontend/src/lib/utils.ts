import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

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
