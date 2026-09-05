import { createFileRoute, Link, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/deployments")({
  head: () => ({
    meta: [
      { title: "Deployments — RIFT" },
      { name: "description", content: "Model services running across the fleet." },
      { property: "og:title", content: "Deployments — RIFT" },
      { property: "og:description", content: "Model services running across the fleet." },
    ],
  }),
  component: () => <Outlet />,
});

export { Link };
