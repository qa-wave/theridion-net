/**
 * LoadWorkspacePanel — full-screen Load Testing workspace.
 *
 * Allows running load tests against any saved collection request or a custom URL.
 * Displays live results with timeline chart, percentile metrics and pass/fail status.
 * Emits RunResult v2 to Hub when configured.
 */
import { Activity, BarChart3, ChevronDown, ChevronRight, Loader2, Play, RefreshCw } from "lucide-react";
import { useCallback, useState } from "react";
import { sidecar, type LoadRunResult, type StoredCollection } from "../lib/sidecar";

interface Props {
  collections: StoredCollection[];
  onToast?: (type: "success" | "error" | "info", msg: string) => void;
}

const DURATION_OPTIONS = [10, 30, 60, 120, 300];
const VU_OPTIONS = [1, 5, 10, 25, 50, 100];

interface RunConfig {
  url: string;
  method: string;
  virtualUsers: number;
  durationSeconds: number;
  rampUpSeconds: number;
  thinkTimeMs: number;
}

const DEFAULT_CONFIG: RunConfig = {
  url: "",
  method: "GET",
  virtualUsers: 10,
  durationSeconds: 30,
  rampUpSeconds: 5,
  thinkTimeMs: 0,
};

function MetricCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-neutral-900/40 p-3 flex flex-col gap-1">
      <div className={`text-xl font-bold tabular-nums ${accent ?? "text-neutral-100"}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-widest text-neutral-500">{label}</div>
      {sub && <div className="text-[10px] text-neutral-600">{sub}</div>}
    </div>
  );
}

function Timeline({ result }: { result: LoadRunResult }) {
  if (!result.timeline || result.timeline.length === 0) return null;
  const maxRps = Math.max(...result.timeline.map((t) => t.rps), 1);
  const maxLat = Math.max(...result.timeline.map((t) => t.avg_latency_ms), 1);
  return (
    <div className="rounded-lg border border-white/[0.06] bg-neutral-900/40 p-3">
      <div className="mb-2 text-[10px] uppercase tracking-widest text-neutral-500">Timeline</div>
      <div className="relative h-24 flex items-end gap-px overflow-hidden">
        {result.timeline.map((point, i) => {
          const rpsH = (point.rps / maxRps) * 100;
          const latH = (point.avg_latency_ms / maxLat) * 100;
          const hasError = point.error_count > 0;
          return (
            <div
              key={i}
              className="group relative flex-1 min-w-[2px] flex flex-col-reverse gap-px"
              title={`t=${point.second}s | RPS=${point.rps.toFixed(1)} | lat=${point.avg_latency_ms.toFixed(0)}ms | err=${point.error_count}`}
            >
              {/* RPS bar */}
              <div
                className={`w-full rounded-t-sm ${hasError ? "bg-rose-500/70" : "bg-orange-500/60"}`}
                style={{ height: `${rpsH}%` }}
              />
              {/* Latency overlay */}
              <div
                className="absolute bottom-0 w-full opacity-30 rounded-t-sm bg-sky-400"
                style={{ height: `${latH}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex gap-3 text-[9px] text-neutral-600">
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-orange-500/60" />RPS</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-sky-400/30" />Avg Latency</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-rose-500/70" />Errors</span>
      </div>
    </div>
  );
}

export function LoadWorkspacePanel({ collections, onToast }: Props) {
  const [cfg, setCfg] = useState<RunConfig>(DEFAULT_CONFIG);
  const [result, setResult] = useState<LoadRunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [selectedCollection, setSelectedCollection] = useState<string>("");

  // Flatten collection requests for the URL picker
  const allRequests = collections.flatMap((c) =>
    c.items
      .filter((it) => !it.is_folder)
      .map((it) => ({ collectionName: c.name, id: it.id, name: it.name, method: it.method ?? "GET", url: it.url ?? "" }))
  );

  const handleCollectionSelect = useCallback((reqId: string) => {
    setSelectedCollection(reqId);
    const req = allRequests.find((r) => r.id === reqId);
    if (req) {
      setCfg((prev) => ({ ...prev, url: req.url, method: req.method }));
    }
  }, [allRequests]);

  async function run() {
    if (!cfg.url) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await sidecar.loadTestFull({
        url: cfg.url,
        method: cfg.method,
        headers: {},
        body: null,
        virtual_users: cfg.virtualUsers,
        duration_seconds: cfg.durationSeconds,
        ramp_up_seconds: cfg.rampUpSeconds,
        think_time_ms: cfg.thinkTimeMs,
      });
      setResult(res);
      onToast?.("success", `Load test complete — ${res.total_requests} requests, ${res.requests_per_second.toFixed(1)} RPS`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      onToast?.("error", `Load test failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  const inputCls = "w-full rounded-md border border-white/[0.06] bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-orange-500/40 focus:outline-none";
  const labelCls = "mb-1 block text-[10px] uppercase tracking-widest text-neutral-500";

  return (
    <div className="flex h-full overflow-hidden bg-neutral-950">
      {/* Left: Config pane */}
      <div className="flex w-80 shrink-0 flex-col overflow-y-auto border-r border-white/[0.06] bg-neutral-925/90 p-4 gap-4">
        {/* Header */}
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-orange-500" />
          <span className="text-sm font-semibold text-neutral-100">Load Test</span>
        </div>

        {/* URL */}
        <div>
          <label className={labelCls}>Target URL</label>
          <input
            type="url"
            className={inputCls}
            value={cfg.url}
            onChange={(e) => setCfg((p) => ({ ...p, url: e.target.value }))}
            placeholder="https://api.example.com/endpoint"
            spellCheck={false}
          />
        </div>

        {/* Pick from collection */}
        {allRequests.length > 0 && (
          <div>
            <label className={labelCls}>Or use saved request</label>
            <select
              className={inputCls}
              value={selectedCollection}
              onChange={(e) => handleCollectionSelect(e.target.value)}
            >
              <option value="">— pick a request —</option>
              {allRequests.map((r) => (
                <option key={r.id} value={r.id}>
                  [{r.method}] {r.collectionName} / {r.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* VU + Duration */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>Virtual users</label>
            <select
              className={inputCls}
              value={cfg.virtualUsers}
              onChange={(e) => setCfg((p) => ({ ...p, virtualUsers: Number(e.target.value) }))}
            >
              {VU_OPTIONS.map((v) => (
                <option key={v} value={v}>{v} VU</option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls}>Duration</label>
            <select
              className={inputCls}
              value={cfg.durationSeconds}
              onChange={(e) => setCfg((p) => ({ ...p, durationSeconds: Number(e.target.value) }))}
            >
              {DURATION_OPTIONS.map((d) => (
                <option key={d} value={d}>{d}s</option>
              ))}
            </select>
          </div>
        </div>

        {/* Advanced */}
        <div className="rounded-md border border-white/[0.06]">
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="flex w-full items-center justify-between px-3 py-2 text-xs text-neutral-400 hover:text-neutral-200 transition"
          >
            <span className="flex items-center gap-1.5">
              {showAdvanced ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              <span className="text-[10px] uppercase tracking-widest text-neutral-500">Advanced</span>
            </span>
          </button>
          {showAdvanced && (
            <div className="border-t border-white/[0.06] px-3 pb-3 pt-2 space-y-3">
              <div>
                <label className={labelCls}>Ramp-up (s)</label>
                <input
                  type="number"
                  min={0}
                  max={60}
                  className={inputCls}
                  value={cfg.rampUpSeconds}
                  onChange={(e) => setCfg((p) => ({ ...p, rampUpSeconds: Number(e.target.value) }))}
                />
              </div>
              <div>
                <label className={labelCls}>Think time (ms)</label>
                <input
                  type="number"
                  min={0}
                  max={5000}
                  className={inputCls}
                  value={cfg.thinkTimeMs}
                  onChange={(e) => setCfg((p) => ({ ...p, thinkTimeMs: Number(e.target.value) }))}
                />
              </div>
            </div>
          )}
        </div>

        {/* Run button */}
        <button
          type="button"
          onClick={run}
          disabled={busy || !cfg.url}
          className="flex items-center justify-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-orange-500 disabled:opacity-40"
        >
          {busy ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> Running…</>
          ) : (
            <><Play className="h-4 w-4" /> Start Load Test</>
          )}
        </button>

        {/* Reset */}
        {result && !busy && (
          <button
            type="button"
            onClick={() => { setResult(null); setError(null); }}
            className="flex items-center justify-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-300 transition"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Reset
          </button>
        )}
      </div>

      {/* Right: Results */}
      <div className="flex-1 overflow-y-auto p-6">
        {error && (
          <div className="mb-4 rounded-lg border border-rose-800/40 bg-rose-950/20 px-4 py-3 text-sm text-rose-400">
            {error}
          </div>
        )}

        {busy && !result && (
          <div className="flex h-full items-center justify-center text-neutral-500">
            <div className="text-center">
              <Loader2 className="mx-auto h-8 w-8 animate-spin text-orange-500 mb-3" />
              <p className="text-sm">Running load test…</p>
              <p className="text-xs mt-1 text-neutral-600">
                {cfg.virtualUsers} VUs × {cfg.durationSeconds}s
              </p>
            </div>
          </div>
        )}

        {!result && !busy && !error && (
          <div className="flex h-full items-center justify-center text-neutral-500">
            <div className="text-center">
              <BarChart3 className="mx-auto h-12 w-12 text-neutral-700 mb-4" />
              <p className="text-sm font-medium text-neutral-400">No results yet</p>
              <p className="text-xs mt-1">Configure a target URL and start a test</p>
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-4">
            {/* Summary grid */}
            <div className="grid grid-cols-4 gap-3">
              <MetricCard label="Total Requests" value={result.total_requests.toLocaleString()} />
              <MetricCard label="RPS" value={result.requests_per_second.toFixed(1)} accent="text-orange-400" />
              <MetricCard label="Successful" value={result.successful.toLocaleString()} accent="text-emerald-400" />
              <MetricCard
                label="Failed"
                value={result.failed.toLocaleString()}
                accent={result.failed > 0 ? "text-rose-400" : "text-neutral-400"}
              />
            </div>
            <div className="grid grid-cols-4 gap-3">
              <MetricCard label="Avg Latency" value={`${result.avg_latency_ms.toFixed(0)}ms`} />
              <MetricCard label="p50" value={`${result.p50_ms.toFixed(0)}ms`} />
              <MetricCard label="p95" value={`${result.p95_ms.toFixed(0)}ms`} accent={result.p95_ms > 1000 ? "text-amber-400" : undefined} />
              <MetricCard label="p99" value={`${result.p99_ms.toFixed(0)}ms`} accent={result.p99_ms > 2000 ? "text-rose-400" : undefined} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <MetricCard label="Min" value={`${result.min_latency_ms.toFixed(0)}ms`} />
              <MetricCard label="Max" value={`${result.max_latency_ms.toFixed(0)}ms`} />
              <MetricCard label="Duration" value={`${result.duration_seconds.toFixed(1)}s`} />
            </div>

            {/* Timeline */}
            <Timeline result={result} />

            {/* Errors */}
            {Object.keys(result.errors).length > 0 && (
              <div className="rounded-lg border border-rose-800/30 bg-rose-950/10 p-3">
                <div className="mb-2 text-[10px] uppercase tracking-widest text-rose-500">Errors</div>
                {Object.entries(result.errors).map(([err, count]) => (
                  <div key={err} className="flex justify-between text-xs py-0.5">
                    <span className="text-rose-400">{err}</span>
                    <span className="text-neutral-500">{count}×</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
