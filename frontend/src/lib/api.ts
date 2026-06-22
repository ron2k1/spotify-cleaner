// Typed access to the local FastAPI server. Same-origin in production (the SPA
// is served by uvicorn); proxied through Vite to :8888 in dev. No base URL,
// no auth headers — the OAuth token lives server-side only.

import type {
  ApplyRequest,
  AuthStatus,
  ConfigInfo,
  ErrorEvent,
  GdprUploadResult,
  JobStarted,
  LogEvent,
  PhaseEvent,
  ProfileInfo,
  ProgressEvent,
  ScanRequest,
  ScanResult,
} from "./types";

/** A failed request. `detail` is the server's machine-readable code (e.g.
 *  "not_connected", "spotify_app_not_configured"), never a leaked message. */
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`${status} ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData;
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body && !isForm ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText || `http_${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {
      // Non-JSON error body; keep the status-derived detail.
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  getConfig: () => request<ConfigInfo>("/api/config"),

  getProfiles: () => request<ProfileInfo[]>("/api/profiles"),

  deleteProfile: (profile: string) =>
    request<{ removed: boolean }>(
      `/api/profiles/${encodeURIComponent(profile)}`,
      { method: "DELETE" },
    ),

  getAuthStatus: (profile: string) =>
    request<AuthStatus>(
      `/api/auth/status?profile=${encodeURIComponent(profile)}`,
    ),

  logout: (profile: string) =>
    request<{ removed: boolean }>(
      `/api/auth/logout?profile=${encodeURIComponent(profile)}`,
      { method: "POST" },
    ),

  /** Full-page navigation target — never fetch this, the browser must follow
   *  the 307 to Spotify so the user can approve consent. */
  loginUrl: (profile: string) =>
    `/api/auth/login?profile=${encodeURIComponent(profile)}`,

  uploadGdpr: (files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return request<GdprUploadResult>("/api/gdpr/upload", {
      method: "POST",
      body: fd,
    });
  },

  startScan: (req: ScanRequest) =>
    request<JobStarted>("/api/scan", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  scanResult: (jobId: string) =>
    request<ScanResult>(`/api/scan/${encodeURIComponent(jobId)}/result`),

  /** Full-page download target — the browser fetches and saves the CSV. Not
   *  called through `request`; it's an href the anchor/`window` follows. */
  exportCsvUrl: (jobId: string) =>
    `/api/scan/${encodeURIComponent(jobId)}/export.csv`,

  startApply: (req: ApplyRequest) =>
    request<JobStarted>("/api/apply", {
      method: "POST",
      body: JSON.stringify(req),
    }),
};

export interface JobEventHandlers {
  onPhase?: (d: PhaseEvent) => void;
  onProgress?: (d: ProgressEvent) => void;
  onLog?: (d: LogEvent) => void;
  onDone?: (d: unknown) => void;
  onError?: (d: ErrorEvent) => void;
}

/** Subscribe to a job's SSE stream. Returns a disposer that closes the socket.
 *
 *  The server names every event, so we register per-type listeners (plain
 *  `onmessage` would miss all of them). The browser replays from Last-Event-ID
 *  automatically on reconnect because each event carries an `id`. */
export function streamJob(
  kind: "scan" | "apply",
  jobId: string,
  handlers: JobEventHandlers,
): () => void {
  const es = new EventSource(
    `/api/${kind}/${encodeURIComponent(jobId)}/events`,
  );

  const bind = <T>(fn: ((d: T) => void) | undefined) => (ev: MessageEvent) => {
    if (!fn) return;
    try {
      fn(JSON.parse(ev.data) as T);
    } catch {
      // Ignore a malformed frame rather than tearing down the stream.
    }
  };

  es.addEventListener("phase", bind(handlers.onPhase));
  es.addEventListener("progress", bind(handlers.onProgress));
  es.addEventListener("log", bind(handlers.onLog));

  es.addEventListener("done", (ev) => {
    bind(handlers.onDone)(ev as MessageEvent);
    es.close();
  });

  es.addEventListener("error", (ev) => {
    // A server "error" event carries data; a transport drop does not. Only the
    // former is terminal — let EventSource auto-reconnect on the latter.
    const me = ev as MessageEvent;
    if (me.data) {
      bind(handlers.onError)(me);
      es.close();
    }
  });

  return () => es.close();
}
