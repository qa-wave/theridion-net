/**
 * Load Engine API client — staged load testing with SSE live progress.
 */
import { call } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LoadStage {
  target_vus: number;
  duration_s: number;
  ramp_up_s?: number;
}

export interface LoadEngineConfig {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
  stages: LoadStage[];
  think_time_ms?: number;
  timeout_ms?: number;
}

export interface LoadEngineStartOutput {
  run_id: string;
  total_stages: number;
  total_duration_s: number;
}

export type LoadEngineStatus = "running" | "done" | "stopped" | "error";

export interface LoadEngineTimelinePoint {
  second: number;
  rps: number;
  active_vus: number;
  avg_latency_ms: number;
  p95_ms: number;
  error_rate: number;
}

export interface LoadEngineResult {
  run_id: string;
  status: LoadEngineStatus;
  total_requests: number;
  successful: number;
  failed: number;
  errors: Record<string, number>;
  avg_latency_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  requests_per_second: number;
  duration_s: number;
  timeline: LoadEngineTimelinePoint[];
  error: string | null;
}

export interface LoadEngineRunSummary {
  run_id: string;
  status: LoadEngineStatus;
  total_requests: number;
  started_at: number;
  finished_at: number | null;
}

// ---------------------------------------------------------------------------
// Methods
// ---------------------------------------------------------------------------

export const loadEngineMethods = {
  /** Start a staged load run. Returns immediately; poll getLoadRun or subscribe to SSE. */
  startLoadRun: (cfg: LoadEngineConfig) =>
    call<LoadEngineStartOutput>("/api/load-engine/start", {
      method: "POST",
      body: JSON.stringify(cfg),
    }),

  /** Stop an active load run. */
  stopLoadRun: (runId: string) =>
    call<LoadEngineResult>(`/api/load-engine/stop/${runId}`, { method: "POST" }),

  /** Get full result for a run. */
  getLoadRun: (runId: string) =>
    call<LoadEngineResult>(`/api/load-engine/runs/${runId}`, { method: "GET" }),

  /** List all recent runs (newest first). */
  listLoadRuns: () =>
    call<LoadEngineRunSummary[]>("/api/load-engine/runs", { method: "GET" }),
};
