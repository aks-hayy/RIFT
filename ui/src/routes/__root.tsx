import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";

function NotFoundComponent() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-4">
      <div className="rift-panel px-8 py-10 max-w-md text-center">
        <div className="rift-label mb-2">404 / not-matched</div>
        <h1 className="text-[22px] font-medium text-ink">Route not found</h1>
        <p className="mt-2 text-[13px] text-ink-secondary">
          This URL doesn't correspond to a RIFT resource or view.
        </p>
        <div className="mt-5">
          <Link
            to="/"
            className="inline-flex items-center justify-center h-9 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]"
          >
            Return home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-4">
      <div className="rift-panel px-8 py-10 max-w-md">
        <div className="rift-label mb-2 text-error">error</div>
        <h1 className="text-[18px] font-medium text-ink">This view failed to load</h1>
        <p className="mt-2 text-[13px] text-ink-secondary">
          {error.message || "An unexpected error occurred."}
        </p>
        <div className="mt-5 flex gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="h-9 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]"
          >
            Try again
          </button>
          <a
            href="/"
            className="h-9 px-4 inline-flex items-center rounded-[4px] border border-border text-[13px] font-medium text-ink hover:bg-muted"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "RIFT — LLM control plane" },
      {
        name: "description",
        content:
          "RIFT deploys and operates LLM servers on a single computer or a cluster. Discover hardware, plan deployments, apply, benchmark, and recover.",
      },
      { property: "og:title", content: "RIFT — LLM control plane" },
      {
        property: "og:description",
        content:
          "Control plane for deploying and operating LLM servers on one machine or a cluster.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <Outlet />
    </QueryClientProvider>
  );
}
