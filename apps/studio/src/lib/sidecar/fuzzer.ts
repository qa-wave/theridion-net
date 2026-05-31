/**
 * Fuzzer API client — Sniper / Pitchfork / Cluster-Bomb attack modes.
 */
import { call } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AttackMode = "sniper" | "pitchfork" | "cluster_bomb";

export interface PayloadPosition {
  name: string;
  payloads: string[];
}

export interface FuzzerConfig {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
  attack_mode: AttackMode;
  positions: PayloadPosition[];
  timeout_ms?: number;
  concurrency?: number;
}

export interface FuzzerStartOutput {
  run_id: string;
  total_requests: number;
  attack_mode: AttackMode;
}

export type FuzzerStatus = "running" | "done" | "stopped" | "error";

export interface FuzzerRunStatus {
  run_id: string;
  status: FuzzerStatus;
  total_requests: number;
  completed: number;
  started_at: number;
  finished_at: number | null;
  error: string | null;
}

export interface FuzzResult {
  result_id: string;
  run_id: string;
  seq: number;
  payloads: Record<string, string>;
  url: string;
  method: string;
  request_body: string | null;
  status_code: number | null;
  response_body: string | null;
  response_length: number;
  elapsed_ms: number;
  error: string | null;
  flagged: boolean;
}

export interface FlagInput {
  flagged: boolean;
}

// ---------------------------------------------------------------------------
// Methods
// ---------------------------------------------------------------------------

export const fuzzerMethods = {
  /** Start a fuzzer run. Returns immediately with run_id. */
  fuzzerStart: (cfg: FuzzerConfig) =>
    call<FuzzerStartOutput>("/api/fuzzer/start", {
      method: "POST",
      body: JSON.stringify(cfg),
    }),

  /** Stop a running fuzz run. */
  fuzzerStop: (runId: string) =>
    call<FuzzerRunStatus>(`/api/fuzzer/stop/${runId}`, { method: "POST" }),

  /** Get run status. */
  fuzzerGetRun: (runId: string) =>
    call<FuzzerRunStatus>(`/api/fuzzer/runs/${runId}`, { method: "GET" }),

  /** List results for a run. */
  fuzzerGetResults: (
    runId: string,
    opts?: { limit?: number; offset?: number; flaggedOnly?: boolean; statusCode?: number }
  ) => {
    const params = new URLSearchParams();
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts?.offset !== undefined) params.set("offset", String(opts.offset));
    if (opts?.flaggedOnly) params.set("flagged_only", "true");
    if (opts?.statusCode !== undefined) params.set("status_code", String(opts.statusCode));
    const qs = params.toString();
    return call<FuzzResult[]>(`/api/fuzzer/runs/${runId}/results${qs ? `?${qs}` : ""}`, {
      method: "GET",
    });
  },

  /** Flag/unflag a result as interesting. */
  fuzzerFlagResult: (runId: string, resultId: string, flagged: boolean) =>
    call<FuzzResult>(`/api/fuzzer/runs/${runId}/results/${resultId}/flag`, {
      method: "PATCH",
      body: JSON.stringify({ flagged }),
    }),

  /** Delete a run and all its results. */
  fuzzerDeleteRun: (runId: string) =>
    call<{ deleted: string }>(`/api/fuzzer/runs/${runId}`, { method: "DELETE" }),
};
