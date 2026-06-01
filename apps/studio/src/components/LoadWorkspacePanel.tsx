/**
 * LoadWorkspacePanel — full-screen Load Testing workspace.
 *
 * Allows running load tests against any saved collection request or a custom URL.
 * Displays live results with timeline chart, percentile metrics and pass/fail status.
 * Emits RunResult v2 to Hub when configured.
 */
import { Activity, BarChart3, ChevronDown, ChevronRight, Clock, Loader2, Play, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { sidecar, type LoadRunResult, type SavedLoadResult, type StoredCollection } from "../lib/sidecar";
import { useT } from "../lib/i18n/context";

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
  const t = useT();
  if (!result.timeline || result.timeline.length === 0) return null;
  const maxRps = Math.max(...result.timeline.map((pt) => pt.rps), 1);
  const maxLat = Math.max(...result.timeline.map((pt) => pt.avg_latency_ms), 1);
  return (
    <div className="rounded-lg border border-white/[0.06] bg-neutral-900/40 p-3">
      <div className="mb-2 text-[10px] uppercase tracking-widest text-neutral-500">{t("load.timeline")}</div>
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
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-orange-500/60" />{t("load.timeline.rps")}</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-sky-400/30" />{t("load.timeline.avgLatency")}</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-rose-500/70" />{t("load.timeline.errors")}</span>
      </div>
    </div>
  );
}

export function LoadWorkspacePanel({ collections, onToast }: Props) {
  const t = useT();
  const [cfg, setCfg] = useState<RunConfig>(DEFAULT_CONFIG);
  const [result, setResult] = useState<LoadRunResult | null>(null);
  const [savedResults, setSavedResults] = useState<SavedLoadResult[]>([]);
  const [selectedSaved, setSelectedSaved] = useState<SavedLoadResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [selectedCollection, setSelectedCollection] = useState<string>("");

  // Load saved results on mount so the panel is populated immediately.
  useEffect(() => {
    sidecar.listSavedLoadResults().then((results) => {
      setSavedResults(results);
      if (results.length > 0 && !result) {
        setSelectedSaved(results[0]);
      }
    }).catch(() => { /* sidecar not ready yet */ });
  }, []);

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
      setSelectedSaved(null);
      // Refresh saved results list so the history sidebar updates.
      sidecar.listSavedLoadResults().then(setSavedResults).catch(() => {});
      onToast?.("success", t("load.toast.complete", { requests: res.total_requests, rps: res.requests_per_second.toFixed(1) }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      onToast?.("error", t("load.toast.failed", { msg }));
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
          <span className="text-sm font-semibold text-neutral-100">{t("load.header")}</span>
        </div>

        {/* URL */}
        <div>
          <label className={labelCls}>{t("load.targetUrl")}</label>
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
            <label className={labelCls}>{t("load.savedRequest")}</label>
            <select
              className={inputCls}
              value={selectedCollection}
              onChange={(e) => handleCollectionSelect(e.target.value)}
            >
              <option value="">{t("load.savedRequest.placeholder")}</option>
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
            <label className={labelCls}>{t("load.virtualUsers")}</label>
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
            <label className={labelCls}>{t("load.duration")}</label>
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
              <span className="text-[10px] uppercase tracking-widest text-neutral-500">{t("load.advanced")}</span>
            </span>
          </button>
          {showAdvanced && (
            <div className="border-t border-white/[0.06] px-3 pb-3 pt-2 space-y-3">
              <div>
                <label className={labelCls}>{t("load.rampUp")}</label>
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
                <label className={labelCls}>{t("load.thinkTime")}</label>
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
            <><Loader2 className="h-4 w-4 animate-spin" /> {t("load.running")}</>
          ) : (
            <><Play className="h-4 w-4" /> {t("load.start")}</>
          )}
        </button>

        {/* Reset */}
        {result && !busy && (
          <button
            type="button"
            onClick={() => { setResult(null); setError(null); }}
            className="flex items-center justify-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-300 transition"
          >
            <RefreshCw className="h-3.5 w-3.5" /> {t("load.reset")}
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
              <p className="text-sm">{t("load.running")}</p>
              <p className="text-xs mt-1 text-neutral-600">
                {cfg.virtualUsers} VUs × {cfg.durationSeconds}s
              </p>
            </div>
          </div>
        )}

        {!result && !busy && !error && !selectedSaved && savedResults.length === 0 && (
          <div className="flex h-full items-center justify-center text-neutral-500">
            <div className="text-center">
              <BarChart3 className="mx-auto h-12 w-12 text-neutral-700 mb-4" />
              <p className="text-sm font-medium text-neutral-400">{t("load.empty.title")}</p>
              <p className="text-xs mt-1">{t("load.empty.description")}</p>
            </div>
          </div>
        )}

        {/* Saved results history sidebar */}
        {savedResults.length > 0 && !result && !busy && (
          <div className="mb-4">
            <div className="mb-2 flex items-center gap-1.5">
              <Clock className="h-3 w-3 text-neutral-500" />
              <span className="text-[10px] uppercase tracking-widest text-neutral-500">{t("load.recentRuns")}</span>
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {savedResults.slice(0, 8).map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => setSelectedSaved(r)}
                  className={`shrink-0 rounded-lg border px-3 py-2 text-left transition ${
                    selectedSaved?.id === r.id
                      ? "border-orange-500/40 bg-orange-950/20"
                      : "border-white/[0.06] bg-neutral-900/40 hover:border-white/[0.12]"
                  }`}
                >
                  <div className="text-[10px] font-mono text-neutral-400 truncate max-w-[180px]">{r.method} {r.url.replace(/^https?:\/\/[^/]+/, "")}</div>
                  <div className="mt-0.5 text-xs font-bold text-orange-400">{r.requests_per_second.toFixed(1)} RPS</div>
                  <div className="text-[10px] text-neutral-600">{r.total_requests.toLocaleString()} req · {r.virtual_users} VU</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Selected saved result summary */}
        {!result && !busy && selectedSaved && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-xs text-neutral-500">
              <Clock className="h-3.5 w-3.5" />
              <span>{t("load.savedRun")} · {new Date(selectedSaved.started_at * 1000).toLocaleString()}</span>
              <span className="ml-auto font-mono text-neutral-600 truncate max-w-xs">{selectedSaved.method} {selectedSaved.url}</span>
            </div>
            <div className="grid grid-cols-4 gap-3">
              <MetricCard label={t("load.metric.totalRequests")} value={selectedSaved.total_requests.toLocaleString()} />
              <MetricCard label={t("load.metric.rps")} value={selectedSaved.requests_per_second.toFixed(1)} accent="text-orange-400" />
              <MetricCard label={t("load.metric.successful")} value={selectedSaved.successful.toLocaleString()} accent="text-emerald-400" />
              <MetricCard label={t("load.metric.failed")} value={selectedSaved.failed.toLocaleString()} accent={selectedSaved.failed > 0 ? "text-rose-400" : "text-neutral-400"} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <MetricCard label={t("load.metric.avgLatency")} value={`${selectedSaved.avg_latency_ms.toFixed(0)}ms`} />
              <MetricCard label={t("load.metric.p95")} value={`${selectedSaved.p95_ms.toFixed(0)}ms`} accent={selectedSaved.p95_ms > 1000 ? "text-amber-400" : undefined} />
              <MetricCard label={t("load.metric.p99")} value={`${selectedSaved.p99_ms.toFixed(0)}ms`} accent={selectedSaved.p99_ms > 2000 ? "text-rose-400" : undefined} />
            </div>
            {Object.keys(selectedSaved.errors).length > 0 && (
              <div className="rounded-lg border border-rose-800/30 bg-rose-950/10 p-3">
                <div className="mb-2 text-[10px] uppercase tracking-widest text-rose-500">{t("load.errors")}</div>
                {Object.entries(selectedSaved.errors).map(([err, count]) => (
                  <div key={err} className="flex justify-between text-xs py-0.5">
                    <span className="text-rose-400">{err}</span>
                    <span className="text-neutral-500">{count}×</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {result && (
          <div className="space-y-4">
            {/* Summary grid */}
            <div className="grid grid-cols-4 gap-3">
              <MetricCard label={t("load.metric.totalRequests")} value={result.total_requests.toLocaleString()} />
              <MetricCard label={t("load.metric.rps")} value={result.requests_per_second.toFixed(1)} accent="text-orange-400" />
              <MetricCard label={t("load.metric.successful")} value={result.successful.toLocaleString()} accent="text-emerald-400" />
              <MetricCard
                label={t("load.metric.failed")}
                value={result.failed.toLocaleString()}
                accent={result.failed > 0 ? "text-rose-400" : "text-neutral-400"}
              />
            </div>
            <div className="grid grid-cols-4 gap-3">
              <MetricCard label={t("load.metric.avgLatency")} value={`${result.avg_latency_ms.toFixed(0)}ms`} />
              <MetricCard label={t("load.metric.p50")} value={`${result.p50_ms.toFixed(0)}ms`} />
              <MetricCard label={t("load.metric.p95")} value={`${result.p95_ms.toFixed(0)}ms`} accent={result.p95_ms > 1000 ? "text-amber-400" : undefined} />
              <MetricCard label={t("load.metric.p99")} value={`${result.p99_ms.toFixed(0)}ms`} accent={result.p99_ms > 2000 ? "text-rose-400" : undefined} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <MetricCard label={t("load.metric.min")} value={`${result.min_latency_ms.toFixed(0)}ms`} />
              <MetricCard label={t("load.metric.max")} value={`${result.max_latency_ms.toFixed(0)}ms`} />
              <MetricCard label={t("load.metric.duration")} value={`${result.duration_seconds.toFixed(1)}s`} />
            </div>

            {/* Timeline */}
            <Timeline result={result} />

            {/* Errors */}
            {Object.keys(result.errors).length > 0 && (
              <div className="rounded-lg border border-rose-800/30 bg-rose-950/10 p-3">
                <div className="mb-2 text-[10px] uppercase tracking-widest text-rose-500">{t("load.errors")}</div>
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
