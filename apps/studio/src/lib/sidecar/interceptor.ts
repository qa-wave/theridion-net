/**
 * Interceptor API client — intercepting proxy control and RunResult v2 publishing.
 */
import { call } from "./client";

// ---------------------------------------------------------------------------
// Interceptor types
// ---------------------------------------------------------------------------

export interface ScanFlag {
  type: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  location: string;
  detail: string;
}

export interface CapturedFlow {
  flow_id: string;
  timestamp: number;
  method: string;
  url: string;
  request_headers: Record<string, string>;
  request_body: string | null;
  status_code: number | null;
  response_headers: Record<string, string>;
  response_body: string | null;
  elapsed_ms: number | null;
  state: "pending" | "paused" | "forwarded" | "error";
  flags: ScanFlag[];
  error: string | null;
}

export interface InterceptConfig {
  enabled: boolean;
  break_on_all: boolean;
  passive_scan: boolean;
}

export interface InterceptStatus {
  enabled: boolean;
  break_on_all: boolean;
  passive_scan: boolean;
  flow_count: number;
  paused_count: number;
}

export interface ForwardRequest {
  method: string;
  url: string;
  headers?: Record<string, string>;
  body?: string | null;
}

export interface ForwardResult {
  flow_id: string;
  status_code: number;
  response_headers: Record<string, string>;
  response_body: string;
  elapsed_ms: number;
  flags: ScanFlag[];
}

export interface FlowListOutput {
  flows: CapturedFlow[];
  total: number;
}

export interface EditForwardInput {
  flow_id: string;
  method?: string;
  url?: string;
  headers?: Record<string, string>;
  body?: string | null;
}

export interface SendToRequestOutput {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string | null;
}

// ---------------------------------------------------------------------------
// Publish config types
// ---------------------------------------------------------------------------

/** Payload for PUT /api/run-result/config */
export interface PublishConfig {
  weave_url: string;
  weave_token: string;
  hub_url: string;
  hub_token: string;
  enabled: boolean;
}

/** Response from GET/PUT /api/run-result/config — tokens masked */
export interface PublishConfigMasked {
  weave_url: string;
  weave_token_set: boolean;
  hub_url: string;
  hub_token_set: boolean;
  enabled: boolean;
}

// ---------------------------------------------------------------------------
// RunResult v2 types
// ---------------------------------------------------------------------------

export type RunResultSuiteType = "load" | "security" | "integration";
export type RunResultRequestStatus = "pass" | "fail" | "skip" | "blocked";

export interface RunResultRequest {
  request_id?: string;
  name: string;
  method?: string;
  url?: string;
  status_code?: number;
  status: RunResultRequestStatus;
  duration_ms?: number;
  test_key?: string;
  evidence?: string;
  error?: string;
}

export interface RunResultV2 {
  schema_version: 2;
  run_id: string;
  product: "net";
  suite_type: RunResultSuiteType;
  collection_id?: string;
  collection_name?: string;
  environment?: string;
  branch?: string;
  started_at: string;
  finished_at?: string;
  duration_ms?: number;
  total?: number;
  passed?: number;
  failed?: number;
  requests: RunResultRequest[];
}

export interface LoadRunResultV2Input {
  total_requests: number;
  successful: number;
  failed: number;
  errors: Record<string, number>;
  avg_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
  p50_ms: number;
  p75_ms: number;
  p90_ms: number;
  p95_ms: number;
  p99_ms: number;
  requests_per_second: number;
  duration_seconds: number;
  collection_id?: string;
  collection_name?: string;
  environment?: string;
  url?: string;
  method?: string;
  started_at?: string;
  hub_url?: string;
  hub_token?: string;
}

export interface LoadRunResultV2Output {
  run_result: RunResultV2;
  published: boolean;
  publish_error: string | null;
}

export interface SecurityRunResultV2Input {
  url: string;
  findings: Array<{
    scan_type: string;
    severity: string;
    title: string;
    evidence: string;
    description: string;
  }>;
  score: number;
  scan_types_run: string[];
  elapsed_ms: number;
  collection_id?: string;
  collection_name?: string;
  environment?: string;
  started_at?: string;
  hub_url?: string;
  hub_token?: string;
}

export interface SecurityRunResultV2Output {
  run_result: RunResultV2;
  published: boolean;
  publish_error: string | null;
}

// ---------------------------------------------------------------------------
// Methods
// ---------------------------------------------------------------------------

export const interceptorMethods = {
  /** Get current interceptor status. */
  interceptorStatus: () =>
    call<InterceptStatus>("/api/interceptor/status", { method: "GET" }),

  /** Configure the interceptor (enable, break-on-all, passive scan). */
  interceptorConfigure: (cfg: InterceptConfig) =>
    call<InterceptStatus>("/api/interceptor/config", {
      method: "POST",
      body: JSON.stringify(cfg),
    }),

  /** Capture and forward a request through the interceptor. */
  interceptorForward: (req: ForwardRequest) =>
    call<ForwardResult>("/api/interceptor/forward", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  /** Release a paused breakpoint, optionally with edits. */
  interceptorRelease: (flowId: string, edit?: EditForwardInput) =>
    call<{ status: string; flow_id: string }>(`/api/interceptor/release/${flowId}`, {
      method: "POST",
      body: edit ? JSON.stringify(edit) : undefined,
    }),

  /** List captured flows. */
  interceptorListFlows: (limit = 100, offset = 0) =>
    call<FlowListOutput>(`/api/interceptor/flows?limit=${limit}&offset=${offset}`, { method: "GET" }),

  /** Get a single flow by ID. */
  interceptorGetFlow: (flowId: string) =>
    call<CapturedFlow>(`/api/interceptor/flows/${flowId}`, { method: "GET" }),

  /** Clear all captured flows. */
  interceptorClearFlows: () =>
    call<{ cleared: number }>("/api/interceptor/flows", { method: "DELETE" }),

  /** Get the request from a flow to open in the request panel. */
  interceptorSendToRequest: (flowId: string) =>
    call<SendToRequestOutput>(`/api/interceptor/flows/${flowId}/send-to-request`, { method: "GET" }),

  /** Wrap a load test result as RunResult v2 and optionally publish to Hub. */
  wrapLoadResult: (inp: LoadRunResultV2Input) =>
    call<LoadRunResultV2Output>("/api/run-result/load", {
      method: "POST",
      body: JSON.stringify(inp),
    }),

  /** Wrap a security scan result as RunResult v2 and optionally publish to Hub. */
  wrapSecurityResult: (inp: SecurityRunResultV2Input) =>
    call<SecurityRunResultV2Output>("/api/run-result/security", {
      method: "POST",
      body: JSON.stringify(inp),
    }),

  /** Get the current publish config (tokens masked). */
  getPublishConfig: () =>
    call<PublishConfigMasked>("/api/run-result/config", { method: "GET" }),

  /** Save publish config. Pass the full config including tokens. */
  putPublishConfig: (cfg: PublishConfig) =>
    call<PublishConfigMasked>("/api/run-result/config", {
      method: "PUT",
      body: JSON.stringify(cfg),
    }),
};
