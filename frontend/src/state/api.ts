// Minimal typed fetch helper for the FastAPI backend.
// No endpoints are wired up yet; views will import `api` once the backend is live.

/** Base URL of the FastAPI backend. */
export const API_BASE_URL = "http://localhost:8000";

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
  /** Query-string parameters appended to the URL. */
  params?: Record<string, string | number | boolean | undefined>;
  /** JSON-serializable request body (POST/PUT only). */
  body?: unknown;
  /** Abort signal for cancellable requests. */
  signal?: AbortSignal;
}

/** Core request function: builds the URL, sends JSON, parses JSON. */
async function request<T>(
  method: "GET" | "POST" | "PUT" | "DELETE",
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }

  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });

  if (!response.ok) {
    throw new ApiError(response.status, response.statusText, await response.text());
  }
  return (await response.json()) as T;
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
