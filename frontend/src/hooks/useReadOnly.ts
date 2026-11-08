import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";

/** Whether this server is read-only (a public demo). False until it answers, so a normal
 * server's controls never wait on it */
export function useReadOnly(): boolean {
  const { data } = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api.getCapabilities(),
    staleTime: Infinity,
    retry: false,
  });
  return data?.read_only === true;
}
