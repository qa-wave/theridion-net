/**
 * Network probe API client — async port scanner and HAR traffic capture.
 */
import { call } from "./client";

// ---------------------------------------------------------------------------
// Port scan types
// ---------------------------------------------------------------------------

export interface PortScanInput {
  host: string;
  ports: number[] | "common";
  timeout_ms?: number;
  concurrency?: number;
  banner_grab?: boolean;
}

export interface PortResult {
  port: number;
  open: boolean;
  service_hint: string | null;
  banner: string | null;
  elapsed_ms: number;
}

export interface PortScanResult {
  host: string;
  scanned: number;
  open_count: number;
  results: PortResult[];
  elapsed_ms: number;
}

// ---------------------------------------------------------------------------
// HAR capture types
// ---------------------------------------------------------------------------

export interface HarSessionStartInput {
  label?: string;
}

export interface HarSessionOutput {
  session_id: string;
  label: string;
  entry_count: number;
}

export interface HarCaptureInput {
  session_id: string;
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
  follow_redirects?: boolean;
  timeout_ms?: number;
}

export interface HarCaptureResult {
  session_id: string;
  entry_index: number;
  status_code: number | null;
  elapsed_ms: number;
  error: string | null;
}

// HAR 1.2 entry (simplified)
export interface HarEntry {
  startedDateTime: string;
  time: number;
  request: {
    method: string;
    url: string;
    httpVersion: string;
    headers: Array<{ name: string; value: string }>;
    queryString: unknown[];
    cookies: unknown[];
    headersSize: number;
    bodySize: number;
  };
  response: {
    status: number;
    statusText: string;
    httpVersion: string;
    headers: Array<{ name: string; value: string }>;
    cookies: unknown[];
    content: { size: number; mimeType: string; text: string };
    redirectURL: string;
    headersSize: number;
    bodySize: number;
  };
  _error: string | null;
}

export interface HarLog {
  version: string;
  creator: { name: string; version: string };
  entries: HarEntry[];
}

export interface HarExport {
  log: HarLog;
}

// ---------------------------------------------------------------------------
// Methods
// ---------------------------------------------------------------------------

export const networkProbeMethods = {
  /** Async TCP port scan. */
  portScan: (inp: PortScanInput) =>
    call<PortScanResult>("/api/network/portscan", {
      method: "POST",
      body: JSON.stringify(inp),
    }),

  /** Create a new HAR capture session. */
  harStartSession: (label?: string) =>
    call<HarSessionOutput>("/api/network/har/sessions", {
      method: "POST",
      body: JSON.stringify({ label: label ?? "capture" }),
    }),

  /** List all HAR sessions. */
  harListSessions: () =>
    call<HarSessionOutput[]>("/api/network/har/sessions", { method: "GET" }),

  /** Execute a request and record it in the HAR session. */
  harCapture: (inp: HarCaptureInput) =>
    call<HarCaptureResult>("/api/network/har/capture", {
      method: "POST",
      body: JSON.stringify(inp),
    }),

  /** Export a session as HAR 1.2 document. */
  harExport: (sessionId: string) =>
    call<HarExport>(`/api/network/har/${sessionId}`, { method: "GET" }),

  /** Clear all entries in a HAR session. */
  harClearSession: (sessionId: string) =>
    call<{ cleared: number; session_id: string }>(`/api/network/har/${sessionId}`, {
      method: "DELETE",
    }),
};
