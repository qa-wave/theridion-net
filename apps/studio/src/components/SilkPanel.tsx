/**
 * SilkPanel — Frontend testing module (Playwright runner panel).
 *
 * Layout:
 *   Left sidebar  — list of test runs (id, pass/fail badge, duration)
 *   Center        — selected run: JSON report summary + stderr tail
 *   Right column  — assertion/step timeline extracted from report
 *
 * The panel also handles the "Install browser support" flow with a progress
 * log, gating the run button on browser presence.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Download,
  MonitorPlay,
  Play,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { sidecar } from "../lib/sidecar";
import type { SilkRunOutput } from "../lib/sidecar/silk";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RunEntry {
  run: SilkRunOutput;
  specLabel: string;
  startedAt: number; // Date.now()
  traceUrl?: string; // resolved after run, if trace exists
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function StatusBadge({
  passed,
  failed,
  exitCode,
}: {
  passed: number;
  failed: number;
  exitCode: number;
}) {
  if (exitCode === 0 && failed === 0) {
    return (
      <span className="flex items-center gap-1 text-emerald-400 text-xs font-medium">
        <CheckCircle2 size={12} />
        {passed} passed
      </span>
    );
  }
  if (failed > 0) {
    return (
      <span className="flex items-center gap-1 text-red-400 text-xs font-medium">
        <XCircle size={12} />
        {failed} failed
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-neutral-400 text-xs font-medium">
      <AlertCircle size={12} />
      exit {exitCode}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Install dialog
// ---------------------------------------------------------------------------

interface InstallDialogProps {
  onDone: () => void;
  onCancel: () => void;
}

function InstallDialog({ onDone, onCancel }: InstallDialogProps) {
  const [log, setLog] = useState<string[]>(["Starting download (~150 MB)…"]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    sidecar
      .silkInstallBrowsersSync()
      .then((res) => {
        if (cancelled) return;
        if (res.ok) {
          setLog((prev) => [
            ...prev,
            `Done. Browser path: ${res.browser_path ?? "unknown"}`,
          ]);
          setDone(true);
          setTimeout(onDone, 1200);
        } else {
          setError(res.message);
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      });

    return () => {
      cancelled = true;
    };
  }, [onDone]);

  // Auto-scroll log.
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [log]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-[520px] rounded-lg border border-neutral-800 bg-neutral-925 shadow-2xl p-5 flex flex-col gap-4">
        <div className="flex items-center gap-2 text-neutral-100">
          <Download size={18} className="text-emerald-400" />
          <h2 className="font-semibold text-sm">Install Playwright Chromium</h2>
        </div>

        <div
          ref={logRef}
          className="h-48 overflow-y-auto rounded bg-neutral-950 p-3 font-mono text-xs text-neutral-400 select-text"
        >
          {log.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
          {error && (
            <div className="text-red-400 mt-1">Error: {error}</div>
          )}
          {done && (
            <div className="text-emerald-400 mt-1">Chromium ready.</div>
          )}
        </div>

        <p className="text-xs text-neutral-500">
          Playwright Chromium will be installed to{" "}
          <code className="text-neutral-400">~/.cache/ms-playwright/</code>
          &nbsp;and is ~150 MB. This is a one-time operation.
        </p>

        <div className="flex justify-end gap-2">
          {!done && !error && (
            <button
              onClick={onCancel}
              className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition-colors"
            >
              Cancel
            </button>
          )}
          {(done || error) && (
            <button
              onClick={onCancel}
              className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition-colors"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Run form
// ---------------------------------------------------------------------------

interface RunFormProps {
  onRun: (specPath: string, workspaceDir: string) => void;
  running: boolean;
}

function RunForm({ onRun, running }: RunFormProps) {
  const [specPath, setSpecPath] = useState("");
  const [workspaceDir, setWorkspaceDir] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (specPath.trim()) {
      onRun(specPath.trim(), workspaceDir.trim());
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-900 p-4"
    >
      <h3 className="text-xs font-semibold text-neutral-300 uppercase tracking-wider">
        Run spec
      </h3>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-neutral-500">Spec file path</label>
        <input
          value={specPath}
          onChange={(e) => setSpecPath(e.target.value)}
          placeholder="/path/to/my.spec.ts"
          className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-600 transition-colors"
          spellCheck={false}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-neutral-500">
          Workspace dir (optional — must contain package.json with{" "}
          <code>@playwright/test</code>)
        </label>
        <input
          value={workspaceDir}
          onChange={(e) => setWorkspaceDir(e.target.value)}
          placeholder="/path/to/project"
          className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-600 transition-colors"
          spellCheck={false}
        />
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={running || !specPath.trim()}
          className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
        >
          {running ? (
            <RefreshCw size={12} className="animate-spin" />
          ) : (
            <Play size={12} />
          )}
          {running ? "Running…" : "Run"}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Step timeline
// ---------------------------------------------------------------------------

interface TimelineProps {
  report: Record<string, unknown> | null;
}

interface PlaywrightSuite {
  title: string;
  specs?: PlaywrightSpec[];
  suites?: PlaywrightSuite[];
}

interface PlaywrightSpec {
  title: string;
  ok: boolean;
  tests?: Array<{
    status: string;
    results?: Array<{ duration: number; error?: { message: string } }>;
  }>;
}

function flattenSpecs(suite: PlaywrightSuite): PlaywrightSpec[] {
  const out: PlaywrightSpec[] = [];
  (suite.specs ?? []).forEach((s) => out.push(s));
  (suite.suites ?? []).forEach((s) => out.push(...flattenSpecs(s)));
  return out;
}

function StepTimeline({ report }: TimelineProps) {
  if (!report) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-neutral-600">
        No report data
      </div>
    );
  }

  const suites = (report.suites as PlaywrightSuite[] | undefined) ?? [];
  const allSpecs = suites.flatMap(flattenSpecs);

  if (allSpecs.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-neutral-600">
        No test steps found
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1 overflow-y-auto p-2">
      {allSpecs.map((spec, i) => {
        const result = spec.tests?.[0]?.results?.[0];
        const duration = result?.duration ?? 0;
        const errorMsg = result?.error?.message;

        return (
          <div
            key={i}
            className={`flex items-start gap-2 rounded p-2 text-xs ${
              spec.ok
                ? "bg-emerald-950/40 border border-emerald-900/40"
                : "bg-red-950/40 border border-red-900/40"
            }`}
          >
            {spec.ok ? (
              <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-400" />
            ) : (
              <XCircle size={12} className="mt-0.5 shrink-0 text-red-400" />
            )}
            <div className="flex-1 min-w-0">
              <div className="text-neutral-200 font-medium truncate">{spec.title}</div>
              {errorMsg && (
                <div className="mt-0.5 text-red-400 text-[10px] line-clamp-3 font-mono">
                  {errorMsg}
                </div>
              )}
            </div>
            <div className="shrink-0 flex items-center gap-1 text-neutral-500">
              <Clock size={10} />
              {duration}ms
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

interface SilkPanelProps {
  onToast?: (type: "success" | "error" | "info", message: string) => void;
}

export function SilkPanel({ onToast }: SilkPanelProps) {
  const [browsersInstalled, setBrowsersInstalled] = useState<boolean | null>(null);
  const [showInstallDialog, setShowInstallDialog] = useState(false);
  const [runs, setRuns] = useState<RunEntry[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [checkingBrowsers, setCheckingBrowsers] = useState(false);

  // Check browser presence on mount.
  const checkBrowsers = useCallback(async () => {
    setCheckingBrowsers(true);
    try {
      const res = await sidecar.silkCheckBrowsers();
      setBrowsersInstalled(res.installed);
    } catch {
      setBrowsersInstalled(false);
    } finally {
      setCheckingBrowsers(false);
    }
  }, []);

  useEffect(() => {
    void checkBrowsers();
  }, [checkBrowsers]);

  const handleInstallDone = useCallback(() => {
    setShowInstallDialog(false);
    void checkBrowsers();
    onToast?.("success", "Playwright Chromium installed.");
  }, [checkBrowsers, onToast]);

  const handleRun = useCallback(
    async (specPath: string, workspaceDir: string) => {
      if (!browsersInstalled) {
        setShowInstallDialog(true);
        return;
      }
      setRunning(true);
      try {
        const result = await sidecar.silkRun({
          spec_path: specPath,
          workspace_dir: workspaceDir || undefined,
        });
        const traceUrl = result.trace_path
          ? await sidecar.silkTraceUrl(result.run_id)
          : undefined;
        const entry: RunEntry = {
          run: result,
          specLabel: specPath.split("/").pop() ?? specPath,
          startedAt: Date.now(),
          traceUrl,
        };
        setRuns((prev) => [entry, ...prev]);
        setSelectedIdx(0);
        if (result.failed > 0 || result.exit_code !== 0) {
          onToast?.("error", `Silk: ${result.failed} failed`);
        } else {
          onToast?.("success", `Silk: ${result.passed} passed`);
        }
      } catch (e: unknown) {
        onToast?.("error", `Silk run error: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setRunning(false);
      }
    },
    [browsersInstalled, onToast],
  );

  const selectedEntry = selectedIdx !== null ? runs[selectedIdx] : null;

  return (
    <>
      {showInstallDialog && (
        <InstallDialog
          onDone={handleInstallDone}
          onCancel={() => setShowInstallDialog(false)}
        />
      )}

      <div className="flex h-full bg-neutral-950 text-neutral-200">
        {/* Left sidebar — run list */}
        <div className="flex w-56 shrink-0 flex-col border-r border-neutral-800 bg-neutral-925">
          <div className="flex items-center justify-between border-b border-neutral-800 px-3 py-2">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-neutral-300">
              <MonitorPlay size={13} className="text-emerald-500" />
              Silk runs
            </span>
            <button
              onClick={() => void checkBrowsers()}
              disabled={checkingBrowsers}
              title="Refresh browser check"
              className="text-neutral-500 hover:text-neutral-300 transition-colors"
            >
              <RefreshCw size={12} className={checkingBrowsers ? "animate-spin" : ""} />
            </button>
          </div>

          {/* Browser status banner */}
          {browsersInstalled === false && (
            <div className="m-2 rounded border border-amber-800/50 bg-amber-950/40 p-2 text-[10px] text-amber-400">
              <div className="font-semibold mb-1">Browser support needed</div>
              <button
                onClick={() => setShowInstallDialog(true)}
                className="flex items-center gap-1 text-amber-300 hover:text-amber-200 underline underline-offset-2"
              >
                <Download size={10} />
                Install Chromium (~150 MB)
              </button>
            </div>
          )}

          {/* Run entries */}
          <div className="flex-1 overflow-y-auto py-1">
            {runs.length === 0 && (
              <div className="px-3 py-6 text-center text-xs text-neutral-600">
                No runs yet
              </div>
            )}
            {runs.map((entry, i) => (
              <button
                key={entry.run.run_id}
                onClick={() => setSelectedIdx(i)}
                className={`w-full text-left px-3 py-2 flex flex-col gap-0.5 transition-colors ${
                  selectedIdx === i
                    ? "bg-neutral-800 border-l-2 border-emerald-500"
                    : "hover:bg-neutral-900 border-l-2 border-transparent"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="truncate text-xs text-neutral-200 max-w-[130px]">
                    {entry.specLabel}
                  </span>
                  <ChevronRight size={10} className="text-neutral-600 shrink-0" />
                </div>
                <StatusBadge
                  passed={entry.run.passed}
                  failed={entry.run.failed}
                  exitCode={entry.run.exit_code}
                />
                <span className="text-[10px] text-neutral-600">
                  {entry.run.duration_ms}ms
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Center — form + run detail */}
        <div className="flex flex-1 min-w-0 flex-col gap-4 overflow-y-auto p-4">
          <RunForm onRun={handleRun} running={running} />

          {selectedEntry && (
            <div className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-900 p-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold text-neutral-300 uppercase tracking-wider">
                  Run {selectedEntry.run.run_id.slice(0, 8)}
                </h3>
                {selectedEntry.traceUrl && (
                  <a
                    href={selectedEntry.traceUrl}
                    download={`trace-${selectedEntry.run.run_id}.zip`}
                    className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                  >
                    <Download size={12} />
                    Download trace
                  </a>
                )}
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-4 gap-2">
                {[
                  { label: "Passed", value: selectedEntry.run.passed, color: "text-emerald-400" },
                  { label: "Failed", value: selectedEntry.run.failed, color: "text-red-400" },
                  { label: "Errors", value: selectedEntry.run.errors, color: "text-amber-400" },
                  { label: "Duration", value: `${selectedEntry.run.duration_ms}ms`, color: "text-neutral-300" },
                ].map(({ label, value, color }) => (
                  <div
                    key={label}
                    className="rounded bg-neutral-950 p-2 flex flex-col items-center"
                  >
                    <span className={`text-base font-bold ${color}`}>{value}</span>
                    <span className="text-[10px] text-neutral-500">{label}</span>
                  </div>
                ))}
              </div>

              {/* Stderr tail */}
              {selectedEntry.run.stderr_tail && (
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] uppercase text-neutral-500 tracking-wider">
                    stderr (last 20 lines)
                  </span>
                  <pre className="max-h-36 overflow-y-auto rounded bg-neutral-950 p-2 text-[10px] text-neutral-400 font-mono whitespace-pre-wrap">
                    {selectedEntry.run.stderr_tail}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right — step timeline */}
        <div className="flex w-64 shrink-0 flex-col border-l border-neutral-800">
          <div className="border-b border-neutral-800 px-3 py-2">
            <span className="text-xs font-semibold text-neutral-400 uppercase tracking-wider">
              Assertion timeline
            </span>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">
            <StepTimeline report={selectedEntry?.run.json_report ?? null} />
          </div>
        </div>
      </div>
    </>
  );
}
