export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type JsonObject = Record<string, any>;

export class RiftApiError extends Error {
  status: number;
  payload: JsonObject | null;

  constructor(message: string, status: number, payload: JsonObject | null = null) {
    super(message);
    this.name = "RiftApiError";
    this.status = status;
    this.payload = payload;
  }
}

const configuredBase = (import.meta.env.VITE_RIFT_API_BASE as string | undefined)?.replace(
  /\/$/,
  "",
);

export const RIFT_API_BASE = configuredBase ?? "";

function apiUrl(path: string) {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${RIFT_API_BASE}${normalized}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      signal: controller.signal,
    });
    const contentType = response.headers.get("content-type") ?? "";
    const payload = contentType.includes("application/json")
      ? ((await response.json()) as JsonObject)
      : ({ text: await response.text() } as JsonObject);
    if (!response.ok) {
      const message = String(
        payload.error ?? payload.reason ?? `RIFT API returned ${response.status}`,
      );
      throw new RiftApiError(message, response.status, payload);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof RiftApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new RiftApiError("RIFT API request timed out", 408);
    }
    throw new RiftApiError(error instanceof Error ? error.message : "RIFT API is unavailable", 0);
  } finally {
    clearTimeout(timeout);
  }
}

export function apiGet<T = JsonObject>(path: string) {
  return request<T>(path);
}

export function apiPost<T = JsonObject>(path: string, body: JsonObject = {}) {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function bytes(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number) || number <= 0) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(number) / Math.log(1024)));
  return `${(number / 1024 ** index).toFixed(index > 2 ? 2 : 1)} ${units[index]}`;
}

export function number(value: unknown, digits = 2) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : "--";
}

export function dateTime(value: unknown) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return "--";
  return new Date(parsed * 1000).toLocaleString();
}

export function statusTone(value: unknown): "ok" | "warn" | "err" | "info" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (["ok", "healthy", "ready", "running", "passed", "fits"].includes(status)) return "ok";
  if (["warn", "warning", "starting", "stale", "backoff", "degraded"].includes(status))
    return "warn";
  if (["error", "failed", "unhealthy", "crashed", "insufficient", "stopped"].includes(status))
    return "err";
  if (["info", "observed", "available"].includes(status)) return "info";
  return "neutral";
}
