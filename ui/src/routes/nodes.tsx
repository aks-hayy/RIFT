import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/nodes")({
  head: () => ({
    meta: [
      { title: "Nodes — RIFT" },
      { name: "description", content: "Hardware and agent status for every enrolled node." },
      { property: "og:title", content: "Nodes — RIFT" },
      { property: "og:description", content: "Hardware and agent status for every enrolled node." },
    ],
  }),
  component: () => <Outlet />,
});
