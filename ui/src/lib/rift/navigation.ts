export type PrimaryNavigationItem = {
  label: string;
  to:
    | "/overview"
    | "/deployments"
    | "/nodes"
    | "/models"
    | "/groups"
    | "/operations"
    | "/tuning"
    | "/settings";
};

export type NavigationLink = { label: string; to: "/workloads" | "/setup" | "/models/catalog" };

export const DEFAULT_ROUTE = "/workloads" as const;

export const NAVIGATION = {
  primary: [
    { label: "Overview", to: "/overview" },
    { label: "Services", to: "/deployments" },
    { label: "Nodes", to: "/nodes" },
    { label: "Models", to: "/models" },
    { label: "Groups", to: "/groups" },
    { label: "Operations", to: "/operations" },
    { label: "Tuning", to: "/tuning" },
    { label: "Settings", to: "/settings" },
  ] satisfies PrimaryNavigationItem[],
  deployment: [
    { label: "Workload Deploy", to: "/workloads" },
    { label: "Best Fit Setup", to: "/setup" },
  ] satisfies NavigationLink[],
  modelsCatalog: { label: "Catalog", to: "/models/catalog" } satisfies NavigationLink,
};
