// Minimal typed fetch helper for the FastAPI backend.
// No endpoints are wired up yet; views will import `api` once the backend is live.

/**
 * Base URL of the FastAPI backend.
 *
 * Dev (Vite on :5173) talks cross-origin to the dev backend on :8000 with CORS.
 * Production builds are served by FastAPI itself from the same origin (the
 * single-origin desktop `.exe`), so we target `window.location.origin` — the
 * page's own host:port — which makes the bundle portable to any port the
 * desktop launcher happens to bind (it falls back off :8000 if taken).
 */
export const API_BASE_URL = import.meta.env.DEV
  ? "http://localhost:8000"
  : window.location.origin;

/** Error thrown when the backend responds with a non-2xx status. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly statusText: string,
    public readonly body: string,
  ) {
    super(`API ${status} ${statusText}: ${body}`);
    this.name = "ApiError";
  }
}

/** Options accepted by the request helper. */
interface RequestOptions {
  /** Query-string parameters appended to the URL. Objects are serialized as
   *  JSON strings (the backend parses them back — U2 policy overrides). */
  params?: Record<string, unknown>;
  /** JSON-serializable request body (POST/PUT only). */
  body?: unknown;
  /** Abort signal for cancellable requests. */
  signal?: AbortSignal;
  /** Milliseconds before the request aborts with a timeout error. Defaults to
   *  60s; pass a larger value for known-long jobs, or 0 to disable. */
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 60_000;

/** Core request function: builds the URL, sends JSON, parses JSON.
 *
 *  Every request carries a timeout: a stalled request must surface as a
 *  visible error, never an eternal spinner — each stuck fetch also pins one
 *  of the browser's ~6 connections per host until every later call to the
 *  backend queues behind it. */
async function request<T>(
  method: "GET" | "POST" | "PUT" | "DELETE",
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value === undefined) continue;
    url.searchParams.set(
      key,
      typeof value === "object" && value !== null ? JSON.stringify(value) : String(value),
    );
  }

  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  let timedOut = false;
  const timer =
    timeoutMs > 0
      ? setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs)
      : undefined;
  const onCallerAbort = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  else options.signal?.addEventListener("abort", onCallerAbort, { once: true });

  try {
    // The abort covers the body read too — a connection can stall mid-stream.
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new ApiError(response.status, response.statusText, await response.text());
    }
    return (await response.json()) as T;
  } catch (err: unknown) {
    if (timedOut)
      throw new Error(`${method} ${path} timed out after ${Math.round(timeoutMs / 1000)}s`);
    throw err;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    options.signal?.removeEventListener("abort", onCallerAbort);
  }
}

/** Typed convenience wrappers, e.g. `api.get<Smile[]>("/smiles")`. */
export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>("GET", path, options),
  post: <T>(path: string, options?: RequestOptions) =>
    request<T>("POST", path, options),
  put: <T>(path: string, options?: RequestOptions) =>
    request<T>("PUT", path, options),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>("DELETE", path, options),
};
