/**
 * Silk — Frontend testing module sidecar client.
 *
 * Wraps /api/silk/* endpoints.
 */

import { call, getSidecarBaseUrl } from "./client";

// ---- Types ----------------------------------------------------------------

export interface SilkBrowserCheckOutput {
  installed: boolean;
  paths: string[];
}

export interface SilkRunInput {
  spec_path?: string;
  inline_code?: string;
  env_vars?: Record<string, string>;
  timeout_ms?: number;
  workspace_dir?: string;
}

export interface SilkRunOutput {
  run_id: string;
  exit_code: number;
  passed: number;
  failed: number;
  errors: number;
  duration_ms: number;
  trace_path: string | null;
  json_report: Record<string, unknown> | null;
  stderr_tail: string;
}

export interface SilkInstallBrowsersResponse {
  ok: boolean;
  message: string;
  browser_path: string | null;
}

export interface SilkScreenshotDiffInput {
  baseline_path: string;
  current_path: string;
  threshold?: number;
}

export interface SilkScreenshotDiffOutput {
  diff_path: string;
  pixel_diff_count: number;
  total_pixels: number;
  diff_ratio: number;
  passed: boolean;
}

export interface SilkAutoSpecInput {
  request_id: string;
  method: string;
  url: string;
  headers?: Record<string, string>;
  body?: string;
  status_code?: number;
  workspace_dir?: string;
}

export interface SilkAutoSpecOutput {
  spec_path: string;
  spec_code: string;
}

// ---- Methods ----------------------------------------------------------------

export const silkMethods = {
  /** Check whether Playwright Chromium binaries are present locally. */
  silkCheckBrowsers(): Promise<SilkBrowserCheckOutput> {
    return call<SilkBrowserCheckOutput>("/api/silk/browsers/check");
  },

  /** Blocking Chromium install (non-streaming). ~150 MB download. */
  silkInstallBrowsersSync(): Promise<SilkInstallBrowsersResponse> {
    return call<SilkInstallBrowsersResponse>("/api/silk/install-browsers/sync", {
      method: "POST",
    });
  },

  /**
   * Open an SSE stream for Playwright Chromium installation progress.
   *
   * Returns an EventSource you must close when done.
   * Each ``message`` event carries a progress line; look for
   * ``DONE path=`` or ``ERROR `` in ``event.data``.
   *
   * Note: EventSource does not support custom headers — the token is
   * appended as a query param. The sidecar SSE endpoint accepts token
   * via query or header.
   */
  silkInstallBrowsersStream(token: string): Promise<EventSource> {
    return getSidecarBaseUrl().then((base) => {
      const url = `${base}/api/silk/install-browsers?token=${encodeURIComponent(token)}`;
      return new EventSource(url);
    });
  },

  /** Run a Playwright spec file and get a structured report. */
  silkRun(input: SilkRunInput): Promise<SilkRunOutput> {
    return call<SilkRunOutput>("/api/silk/run", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  /**
   * URL to download the trace ZIP for a completed run.
   * Pass to an <a href> or window.open().
   */
  silkTraceUrl(runId: string): Promise<string> {
    return getSidecarBaseUrl().then(
      (base) => `${base}/api/silk/trace/${encodeURIComponent(runId)}`,
    );
  },

  /** Pixel-diff two PNG images. Returns diff PNG path + stats. */
  silkScreenshotDiff(
    input: SilkScreenshotDiffInput,
  ): Promise<SilkScreenshotDiffOutput> {
    return call<SilkScreenshotDiffOutput>("/api/silk/screenshot-diff", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  /**
   * Generate a starter Playwright spec from a failed Strand request.
   * The spec is written to ``<workspace>/.theridion/silk/auto-generated/``.
   */
  silkAutoSpec(input: SilkAutoSpecInput): Promise<SilkAutoSpecOutput> {
    return call<SilkAutoSpecOutput>("/api/silk/auto-spec", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
};
