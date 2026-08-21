type RuntimeErrorContext = Record<string, unknown>;

export function reportRuntimeError(error: unknown, context: RuntimeErrorContext = {}) {
  if (typeof console === "undefined") return;

  const message =
    error instanceof Response
      ? `Response ${error.status}${error.url ? ` at ${error.url}` : ""}`
      : error instanceof Error
        ? error.message
        : String(error);

  console.error("[RIFT] runtime error", {
    message,
    stack: error instanceof Error ? error.stack : undefined,
    route: typeof window === "undefined" ? undefined : window.location.pathname,
    ...context,
  });
}
