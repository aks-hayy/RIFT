import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost, type JsonObject } from "@/lib/rift-api";

export const riftKeys = {
  all: ["rift"] as const,
  status: ["rift", "status"] as const,
  hardware: ["rift", "hardware"] as const,
  state: ["rift", "state"] as const,
  services: ["rift", "services"] as const,
  backends: ["rift", "backends"] as const,
  plan: ["rift", "plan"] as const,
  discovery: ["rift", "discovery"] as const,
  reports: ["rift", "reports"] as const,
  incidents: ["rift", "incidents"] as const,
  gateway: ["rift", "gateway"] as const,
  observability: ["rift", "observability"] as const,
  cluster: ["rift", "cluster"] as const,
};

export function useRiftQuery<T = JsonObject>(
  key: readonly unknown[],
  path: string,
  options: { refetchInterval?: number; enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: key,
    queryFn: () => apiGet<T>(path),
    retry: 1,
    staleTime: 2_000,
    refetchInterval: options.refetchInterval,
    enabled: options.enabled,
  });
}

export function useRiftMutation<T = JsonObject>(
  path: string,
  invalidates: readonly (readonly unknown[])[] = [riftKeys.all],
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: JsonObject = {}) => apiPost<T>(path, payload),
    onSuccess: async () => {
      await Promise.all(invalidates.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
    },
  });
}

export function useRiftHealth() {
  return useRiftQuery<JsonObject>(riftKeys.status, "/api/rift/status", {
    refetchInterval: 5_000,
  });
}
