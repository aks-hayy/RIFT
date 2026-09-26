import type { Service } from "./types";

export function assignedServices(services: Service[], nodeId: string | null): Service[] {
  if (!nodeId) return [];
  return services.filter((service) =>
    service.assignments.some((assignment) => assignment.nodeId === nodeId),
  );
}
