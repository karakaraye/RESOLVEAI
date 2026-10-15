export type ApiErrorKind =
  | "not-configured"
  | "unreachable"
  | "unauthorized"
  | "forbidden"
  | "not-found"
  | "conflict"
  | "validation"
  | "server";

export class ApiError extends Error {
  constructor(public kind: ApiErrorKind, message: string, public status?: number) {
    super(message);
  }
}

export const API_BASE_URL = (process.env.NEXT_PUBLIC_RESOLVEIQ_API_URL?.replace(/\/$/, "")) || (process.env.NEXT_PUBLIC_BIIRS_API_URL?.replace(/\/$/, "")) || "/api/v1";

const statusKinds: Record<number, ApiErrorKind> = { 400: "validation", 401: "unauthorized", 403: "forbidden", 404: "not-found", 409: "conflict", 422: "validation" };

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[2]) : null;
}

type Options = { method?: "GET" | "POST" | "PUT"; body?: unknown; idempotencyKey?: string; signal?: AbortSignal };

export async function apiFetch<T>(path: string, { method = "GET", body, idempotencyKey, signal }: Options = {}): Promise<T> {
  if (!API_BASE_URL) throw new ApiError("not-configured", "The RESOLVEIQ service address is not configured.");
  const csrfToken = method !== "GET" ? getCsrfToken() : null;
  let response: Response;
  try {
    response = await fetch(API_BASE_URL + path, {
      method,
      signal,
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
        // Required by the API on every state-changing request; cross-site forms cannot send it.
        ...(method === "GET" ? {} : { "X-BIIRS-Request": "1" }),
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError("unreachable", "The RESOLVEIQ service could not be reached.");
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { message?: string; detail?: string } | null;
    throw new ApiError(statusKinds[response.status] ?? "server", detail?.message ?? detail?.detail ?? `Request failed (${response.status}).`, response.status);
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export const signInUrl = () => {
  const returnTo = typeof window !== "undefined" ? window.location.pathname + window.location.search : "/";
  return `${API_BASE_URL}/session/sign-in?returnTo=${encodeURIComponent(returnTo)}`;
};

export function query(params: Record<string, string | number | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  const text = search.toString();
  return text ? `?${text}` : "";
}
