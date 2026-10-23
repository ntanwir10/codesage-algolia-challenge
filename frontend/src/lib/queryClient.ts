import { QueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";

export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  // Don't retry on 4xx errors (client errors)
  if (isAxiosError(error)) {
    const status = error.response?.status;
    if (status !== undefined && status >= 400 && status < 500) {
      return false;
    }
  }
  // Retry up to 3 times for other errors (5xx, network)
  return failureCount < 3;
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Time in milliseconds to cache data
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 10 * 60 * 1000, // 10 minutes (formerly cacheTime)
      retry: shouldRetryQuery,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});
