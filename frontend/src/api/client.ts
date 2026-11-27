export type Readiness = {
  status: "ok" | "unavailable";
  checks: Record<string, "ok" | "fail">;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly fields: Record<string, string[]> = {},
    readonly requestId: string | null = null,
  ) {
    super(message);
  }
}

let csrfToken: string | null = null;

async function getCsrf(force = false): Promise<string> {
  if (csrfToken && !force) return csrfToken;
  const res = await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
  csrfToken = ((await res.json()) as { csrfToken: string }).csrfToken;
  return csrfToken;
}

type Body = Record<string, unknown> | undefined;

async function send(method: string, path: string, body: Body, retried = false): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRFToken"] = await getCsrf();
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 403 && method !== "GET" && !retried) {
    const text = await res.clone().text();
    if (text.includes("CSRF")) {
      await getCsrf(true);
      return send(method, path, body, true);
    }
  }
  return res;
}

/** When the server last answered a request. The server's idle clock restarts on every request. */
export let lastApiAt = Date.now();

export async function api<T>(method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: Body): Promise<T> {
  let res: Response;
  try {
    res = await send(method, path, body);
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection.", 0, "network");
  }
  lastApiAt = Date.now();
  if (res.status === 204) return undefined as T;
  const requestId = res.headers.get("X-Request-ID");
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (res.ok) return data as T;
  const err = (data as { error?: { message?: string; code?: string; fields?: Record<string, string[]> } } | null)?.error;
  if (res.status === 401) window.dispatchEvent(new Event("rs:unauthenticated"));
  throw new ApiError(err?.message ?? `Request failed (${res.status}).`, res.status, err?.code ?? "error", err?.fields, requestId);
}

/** /health/ready answers 503 with a useful body, so it bypasses the normal error path. */
export async function fetchReadiness(signal?: AbortSignal): Promise<Readiness> {
  const res = await fetch("/api/v1/health/ready", { signal, headers: { Accept: "application/json" } });
  if (res.ok || res.status === 503) return (await res.json()) as Readiness;
  throw new ApiError("Unexpected response.", res.status, "error", {}, res.headers.get("X-Request-ID"));
}

/** Multipart upload with progress. fetch cannot report upload progress, so this uses XHR. */
export async function upload<T>(method: "POST", path: string, file: File, onProgress?: (fraction: number) => void, fields: Record<string, string> = {}, fieldName = "file"): Promise<T> {
  const token = await getCsrf();
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, `/api/v1${path}`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("X-CSRFToken", token);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new ApiError("Cannot reach the server. Check your connection.", 0, "network"));
    xhr.onload = () => {
      const requestId = xhr.getResponseHeader("X-Request-ID");
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON body, e.g. a proxy error page */
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data as T);
      if (xhr.status === 401) window.dispatchEvent(new Event("rs:unauthenticated"));
      const err = (data as { error?: { message?: string; code?: string; fields?: Record<string, string[]> } } | null)?.error;
      const fallback = xhr.status === 413 ? "The file is too large (25 MB maximum)." : `Upload failed (${xhr.status}).`;
      const reason = err?.fields?.[fieldName]?.[0] ?? err?.message ?? fallback;
      reject(new ApiError(reason, xhr.status, err?.code ?? "error", err?.fields, requestId));
    };
    const form = new FormData();
    for (const [k, v] of Object.entries(fields)) form.append(k, v);
    form.append(fieldName, file);
    xhr.send(form);
  });
}

/** Download a file the API builds on request (CSV or PDF). Refusals come back as the server's message instead of a broken download. */
export async function downloadFile(path: string, fallbackName = "download.csv"): Promise<void> {
  const res = await fetch(`/api/v1${path}`, { credentials: "same-origin" }); // no Accept header: the API negotiates JSON only, so "text/csv" would be a 406
  if (!res.ok) {
    if (res.status === 401) window.dispatchEvent(new Event("rs:unauthenticated"));
    const body = (await res.json().catch(() => null)) as { error?: { message?: string; code?: string } } | null;
    throw new ApiError(body?.error?.message ?? `Download failed (${res.status}).`, res.status, body?.error?.code ?? "error", {}, res.headers.get("X-Request-ID"));
  }
  const blob = await res.blob();
  const name = /filename="?([^";]+)"?/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** Like downloadFile, for a file the server builds from a POSTed form (the backup). */
export async function downloadPost(path: string, body: Record<string, unknown>, fallbackName: string): Promise<void> {
  const res = await send("POST", path, body);
  if (!res.ok) {
    if (res.status === 401) window.dispatchEvent(new Event("rs:unauthenticated"));
    const data = (await res.json().catch(() => null)) as { error?: { message?: string; code?: string; fields?: Record<string, string[]> } } | null;
    throw new ApiError(data?.error?.message ?? `Request failed (${res.status}).`, res.status, data?.error?.code ?? "error", data?.error?.fields, res.headers.get("X-Request-ID"));
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = /filename="?([^";]+)"?/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  a.click();
  URL.revokeObjectURL(url);
}
