/**
 * Collection Runner API client — data-driven runner over CSV/JSON rows.
 */
import { call } from "./client";
import type { AuthConfig } from "./types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type DataSourceType = "csv" | "json";

export interface DataSource {
  type: DataSourceType;
  /** CSV text or JSON array string. */
  data: string;
}

export interface CollectionRunInput {
  collection_id: string;
  datasource: DataSource;
  environment_id?: string;
  auth?: AuthConfig;
  /** Delay between iterations in ms. */
  delay_ms?: number;
  /** Stop after first failing iteration. */
  fail_fast?: boolean;
  timeout_ms?: number;
}

export interface CollectionRequestResult {
  item_id: string;
  item_name: string;
  method: string;
  url: string;
  status_code: number | null;
  elapsed_ms: number;
  passed: boolean;
  assertion_failures: string[];
  error: string | null;
}

export interface IterationResult {
  iteration: number;
  row_data: Record<string, string>;
  requests: CollectionRequestResult[];
  passed: boolean;
  error: string | null;
}

export type CollectionRunStatus = "running" | "done" | "stopped" | "error";

export interface CollectionRunResult {
  run_id: string;
  status: CollectionRunStatus;
  collection_id: string;
  total_iterations: number;
  completed_iterations: number;
  passed_iterations: number;
  failed_iterations: number;
  iterations: IterationResult[];
  duration_ms: number;
  error: string | null;
}

export interface CollectionRunSummary {
  run_id: string;
  collection_id: string;
  status: CollectionRunStatus;
  total_iterations: number;
  completed_iterations: number;
}

// ---------------------------------------------------------------------------
// Methods
// ---------------------------------------------------------------------------

export const collectionRunnerMethods = {
  /**
   * Run collection synchronously (blocks until all rows complete).
   * For long runs prefer runCollectionAsync.
   */
  runCollection: (inp: CollectionRunInput) =>
    call<CollectionRunResult>("/api/collection-runner/run", {
      method: "POST",
      body: JSON.stringify(inp),
    }),

  /** Start an async collection run; returns run_id. Poll getCollectionRun. */
  runCollectionAsync: (inp: CollectionRunInput) =>
    call<{ run_id: string; total_iterations: number }>("/api/collection-runner/run-async", {
      method: "POST",
      body: JSON.stringify(inp),
    }),

  /** Poll an async collection run result. */
  getCollectionRun: (runId: string) =>
    call<CollectionRunResult>(`/api/collection-runner/runs/${runId}`, { method: "GET" }),

  /** Stop an async collection run. */
  stopCollectionRun: (runId: string) =>
    call<{ status: string; run_id: string }>(`/api/collection-runner/runs/${runId}/stop`, {
      method: "POST",
    }),

  /** List recent collection runs. */
  listCollectionRuns: () =>
    call<CollectionRunSummary[]>("/api/collection-runner/runs", { method: "GET" }),
};
