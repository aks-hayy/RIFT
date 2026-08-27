import { queryOptions, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { rift, RiftUnavailable } from "./client";
import type {
  RiftNode,
  Service,
  FleetHealth,
  Incident,
  Plan,
  DeploymentRevision,
  DeploymentRecord,
  Benchmark,
  ModelRecommendation,
  UseCase,
  ModelArtifact,
  MeshNode,
  MeshSighting,
  MeshTopology,
  OperationRecord,
  SettingsSnapshot,
  EvaluationRun,
} from "./types";

export const keys = {
  health: ["rift", "health"] as const,
  nodes: ["rift", "nodes"] as const,
  node: (id: string) => ["rift", "node", id] as const,
  meshSightings: ["rift", "mesh", "sightings"] as const,
  meshNodes: ["rift", "mesh", "nodes"] as const,
  meshTopology: ["rift", "mesh", "topology"] as const,
  services: ["rift", "services"] as const,
  deploymentRecords: ["rift", "deployment-records"] as const,
  service: (id: string) => ["rift", "service", id] as const,
  revisions: (id: string) => ["rift", "revisions", id] as const,
  benchmarks: (id: string) => ["rift", "benchmarks", id] as const,
  incidents: ["rift", "incidents"] as const,
  timeline: ["rift", "timeline"] as const,
  logs: (service = "chat") => ["rift", "logs", service] as const,
  backends: ["rift", "backends"] as const,
  reports: ["rift", "reports"] as const,
  latestPlan: ["rift", "latest-plan"] as const,
  plan: (id: string) => ["rift", "plan", id] as const,
  settings: ["rift", "settings"] as const,
  evaluations: (id: string) => ["rift", "evaluations", id] as const,
  operations: ["rift", "operations"] as const,
};

/** Wrap a Query hook so callers can render `unavailable` states cleanly. */
export interface RiftQueryResult<T> {
  data: T | undefined;
  isLoading: boolean;
  unavailable: RiftUnavailable | null;
  error: Error | null;
  refetch: () => void;
}

function shape<T>(q: UseQueryResult<T, Error>): RiftQueryResult<T> {
  const err = q.error;
  return {
    data: q.data,
    isLoading: q.isPending,
    unavailable: err instanceof RiftUnavailable ? err : null,
    error: err instanceof RiftUnavailable ? null : ((err as Error | null) ?? null),
    refetch: () => void q.refetch(),
  };
}

export const healthOptions = queryOptions<FleetHealth>({
  queryKey: keys.health,
  queryFn: ({ signal }) => rift.health(signal),
  staleTime: 5_000,
  refetchInterval: 15_000,
  retry: false,
});

export const nodesOptions = queryOptions<RiftNode[]>({
  queryKey: keys.nodes,
  queryFn: ({ signal }) => rift.listNodes(signal),
  staleTime: 5_000,
  refetchInterval: 15_000,
  retry: false,
});

export const servicesOptions = queryOptions<Service[]>({
  queryKey: keys.services,
  queryFn: ({ signal }) => rift.listServices(signal),
  staleTime: 5_000,
  refetchInterval: 20_000,
  retry: false,
});

export const incidentsOptions = queryOptions<Incident[]>({
  queryKey: keys.incidents,
  queryFn: ({ signal }) => rift.listIncidents(signal),
  staleTime: 5_000,
  refetchInterval: 15_000,
  retry: false,
});

export function useHealth() {
  return shape(useQuery(healthOptions));
}
export function useNodes() {
  return shape(useQuery(nodesOptions));
}
export function useMeshSightings() {
  return shape(
    useQuery<MeshSighting[]>({
      queryKey: keys.meshSightings,
      queryFn: ({ signal }) => rift.listMeshSightings(signal),
      staleTime: 2_000,
      refetchInterval: 10_000,
      retry: false,
    }),
  );
}
export function useMeshNodes() {
  return shape(
    useQuery<MeshNode[]>({
      queryKey: keys.meshNodes,
      queryFn: ({ signal }) => rift.listMeshNodes(signal),
      staleTime: 3_000,
      refetchInterval: 10_000,
      retry: false,
    }),
  );
}
export function useMeshTopology() {
  return shape(
    useQuery<MeshTopology>({
      queryKey: keys.meshTopology,
      queryFn: ({ signal }) => rift.getMeshTopology(signal),
      staleTime: 5_000,
      refetchInterval: 15_000,
      retry: false,
    }),
  );
}
export function useServices() {
  return shape(useQuery(servicesOptions));
}

export function useDeploymentRecords() {
  return shape(
    useQuery<DeploymentRecord[]>({
      queryKey: keys.deploymentRecords,
      queryFn: ({ signal }) => rift.listDeploymentRecords(signal),
      staleTime: 2_000,
      refetchInterval: 5_000,
      retry: false,
    }),
  );
}
export function useIncidents() {
  return shape(useQuery(incidentsOptions));
}

export function useTimeline() {
  return shape(
    useQuery({
      queryKey: keys.timeline,
      queryFn: ({ signal }) => rift.timeline(signal),
      staleTime: 5_000,
      refetchInterval: 15_000,
      retry: false,
    }),
  );
}

export function useLogs(service = "chat") {
  return shape(
    useQuery({
      queryKey: keys.logs(service),
      queryFn: ({ signal }) => rift.logs(signal, service),
      staleTime: 3_000,
      refetchInterval: 10_000,
      retry: false,
    }),
  );
}

export function useBackends() {
  return shape(
    useQuery({
      queryKey: keys.backends,
      queryFn: ({ signal }) => rift.backends(signal),
      staleTime: 15_000,
      refetchInterval: 30_000,
      retry: false,
    }),
  );
}

export function useSettings() {
  return shape(
    useQuery<SettingsSnapshot>({
      queryKey: keys.settings,
      queryFn: ({ signal }) => rift.settings(signal),
      staleTime: 10_000,
      refetchInterval: 30_000,
      retry: false,
    }),
  );
}

export function useReports() {
  return shape(
    useQuery({
      queryKey: keys.reports,
      queryFn: ({ signal }) => rift.reports(signal),
      staleTime: 5_000,
      refetchInterval: 5_000,
      retry: false,
    }),
  );
}

export function useLatestPlan() {
  return shape(
    useQuery({
      queryKey: keys.latestPlan,
      queryFn: ({ signal }) => rift.currentPlan(signal),
      staleTime: 15_000,
      retry: false,
    }),
  );
}

export function useNode(id: string | undefined) {
  return shape(
    useQuery({
      queryKey: id ? keys.node(id) : ["rift", "node", "none"],
      queryFn: ({ signal }) => rift.getNode(id!, signal),
      enabled: !!id,
      retry: false,
    }),
  );
}

export function useService(id: string | undefined) {
  return shape(
    useQuery({
      queryKey: id ? keys.service(id) : ["rift", "service", "none"],
      queryFn: ({ signal }) => rift.getService(id!, signal),
      enabled: !!id,
      retry: false,
    }),
  );
}

export function useRevisions(serviceId: string | undefined) {
  return shape(
    useQuery({
      queryKey: serviceId ? keys.revisions(serviceId) : ["rift", "revisions", "none"],
      queryFn: ({ signal }) => rift.listRevisions(serviceId!, signal),
      enabled: !!serviceId,
      retry: false,
    }),
  );
}

export function useBenchmarks(serviceId: string | undefined) {
  return shape(
    useQuery({
      queryKey: serviceId ? keys.benchmarks(serviceId) : ["rift", "benchmarks", "none"],
      queryFn: ({ signal }) => rift.listBenchmarks(serviceId!, signal),
      enabled: !!serviceId,
      retry: false,
    }),
  );
}

export function useEvaluations(serviceId: string | undefined) {
  return shape(
    useQuery<EvaluationRun[]>({
      queryKey: serviceId ? keys.evaluations(serviceId) : ["rift", "evaluations", "none"],
      queryFn: () => rift.listEvaluations(serviceId),
      enabled: !!serviceId,
      staleTime: 5_000,
      refetchInterval: 15_000,
      retry: false,
    }),
  );
}

export function useOperations() {
  return shape(
    useQuery<OperationRecord[]>({
      queryKey: keys.operations,
      queryFn: ({ signal }) => rift.listOperations(signal),
      staleTime: 500,
      refetchInterval: 1_000,
      retry: false,
    }),
  );
}

export type RecommendInput = {
  useCase: UseCase;
  source: ModelArtifact["source"];
  localPath?: string;
  endpointUrl?: string;
  modelRef?: string;
};

export function recommendationKey(input: RecommendInput) {
  return ["rift", "recommend", input] as const;
}

export function useRecommendations(input: RecommendInput | null) {
  return shape(
    useQuery<ModelRecommendation[]>({
      queryKey: input ? recommendationKey(input) : ["rift", "recommend", "none"],
      queryFn: () => rift.recommend(input!),
      enabled: !!input,
      retry: false,
      staleTime: 60_000,
    }),
  );
}

export function usePlan(id: string | null) {
  return shape(
    useQuery<Plan>({
      queryKey: id ? keys.plan(id) : ["rift", "plan", "none"],
      queryFn: ({ signal }) => rift.getPlan(id!, signal),
      enabled: !!id,
      retry: false,
    }),
  );
}

export type { RiftUnavailable };
export type Revisions = DeploymentRevision[];
export type BenchList = Benchmark[];
