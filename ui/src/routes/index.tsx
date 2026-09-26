import { createFileRoute, redirect } from "@tanstack/react-router";
import { DEFAULT_ROUTE } from "@/lib/rift/navigation";

export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: DEFAULT_ROUTE });
  },
  component: () => null,
});
