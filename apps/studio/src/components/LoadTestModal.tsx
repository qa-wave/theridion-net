import { useEffect, useState } from "react";
import { Activity, ChevronDown, ChevronRight, Loader2, Play, X } from "lucide-react";
import { sidecar, type LoadTestResult } from "../lib/sidecar";
import type { AuthConfig, EnvironmentSummary } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string | null;
  /** Pre-selected environment ID from the main panel (can be overridden inside modal). */
  environmentId?: string | null;
  /** Collection ID of the active request (passed through to backend for variable substitution). */
  collectionId?: string | null;
  /** Auth config from the active request tab (used as default; user can override). */
  auth?: AuthConfig;
}

const NONE_AUTH: AuthConfig = { type: "none" };

const AUTH_TYPES = [
  { value: "none", label: "No Auth" },
  { value: "bearer", label: "Bearer Token" },
  { value: "basic", label: "Basic Auth" },
  { value: "apikey", label: "API Key" },
] as const;

export function LoadTestModal({
  open,
  onClose,
  method,
  url,
  headers,
  body,
  environmentId,
  collectionId,
  auth: authProp,
}: Props) {
  const [concurrency, setConcurrency] = useState(10);
  const [duration, setDuration] = useState(5);
  const [rpsLimit, setRpsLimit] = useState<number | null>(null);
  const [result, setResult] = useState<LoadTestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Environment
  const [environments, setEnvironments] = useState<EnvironmentSummary[]>([]);
  const [selectedEnvId, setSelectedEnvId] = useState<string | null>(environmentId ?? null);

  // Auth
  const [auth, setAuth] = useState<AuthConfig>(authProp ?? NONE_AUTH);
  const [authExpanded, setAuthExpanded] = useState(false);

  // Sync when parent props change (e.g. user opens modal after switching env)
  useEffect(() => {
    if (open) {
      setSelectedEnvId(environmentId ?? null);
      setAuth(authProp ?? NONE_AUTH);
      setResult(null);
      setError(null);
    }
  }, [open, environmentId, authProp]);

  useEffect(() => {
    if (!open) return;
    sidecar.listEnvironments().then(setEnvironments).catch(() => {/* non-fatal */});
  }, [open]);

  if (!open) return null;

  async function run() {
    if (!url) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const res = await sidecar.loadTest({
        url,
        method: method as "GET",
        headers,
        body,
        concurrency,
        duration_seconds: duration,
        rps_limit: rpsLimit,
        environment_id: selectedEnvId,
        collection_id: collectionId ?? null,
        auth: auth.type !== "none" ? auth : null,
        query: {},
      });
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none";
  const selectClass =
    "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none";
  const labelClass = "mb-1 block text-[10px] uppercase tracking-widest text-neutral-500";

  const authBadge = auth.type !== "none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[640px] w-[700px] max-h-[92vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Activity className="h-4 w-4 text-cobweb-400" /> Load Test
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
            aria-label="Close load test modal"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Request summary */}
        <div className="border-b border-glass px-4 py-2 text-xs">
          <span className="font-mono text-neutral-400">{method} {url}</span>
        </div>

        {error && (
          <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">
            {error}
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-4">
          {!result ? (
            <div className="space-y-5">
              {/* Perf params row */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className={labelClass}>Concurrency</label>
                  <input
                    type="number"
                    value={concurrency}
                    onChange={(e) => setConcurrency(Number(e.target.value))}
                    min={1}
                    max={500}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className={labelClass}>Duration (s)</label>
                  <input
                    type="number"
                    value={duration}
                    onChange={(e) => setDuration(Number(e.target.value))}
                    min={1}
                    max={300}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className={labelClass}>RPS limit</label>
                  <input
                    type="number"
                    value={rpsLimit ?? ""}
                    onChange={(e) => setRpsLimit(e.target.value ? Number(e.target.value) : null)}
                    placeholder="unlimited"
                    className={inputClass}
                  />
                </div>
              </div>

              {/* Environment selector */}
              <div>
                <label className={labelClass}>Environment</label>
                <select
                  value={selectedEnvId ?? ""}
                  onChange={(e) => setSelectedEnvId(e.target.value || null)}
                  className={selectClass}
                  aria-label="Select environment"
                >
                  <option value="">— none —</option>
                  {environments.map((env) => (
                    <option key={env.id} value={env.id}>
                      {env.name}
                    </option>
                  ))}
                </select>
                {environments.length === 0 && (
                  <p className="mt-1 text-[10px] text-neutral-600">No environments defined.</p>
                )}
              </div>

              {/* Auth section — collapsible */}
              <div className="rounded-md border border-glass">
                <button
                  type="button"
                  onClick={() => setAuthExpanded((v) => !v)}
                  className="flex w-full items-center justify-between px-3 py-2 text-xs text-neutral-400 hover:text-neutral-200 transition"
                  aria-expanded={authExpanded}
                >
                  <span className="flex items-center gap-1.5">
                    {authExpanded ? (
                      <ChevronDown className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5" />
                    )}
                    <span className="text-[10px] uppercase tracking-widest text-neutral-500">
                      Auth
                    </span>
                    {authBadge && (
                      <span className="rounded bg-cobweb-500/20 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-cobweb-400">
                        {auth.type}
                      </span>
                    )}
                  </span>
                </button>

                {authExpanded && (
                  <div className="border-t border-glass px-3 pb-3 pt-2 space-y-3">
                    {/* Type selector */}
                    <div>
                      <label className={labelClass}>Type</label>
                      <select
                        value={auth.type}
                        onChange={(e) =>
                          setAuth({ type: e.target.value as AuthConfig["type"] })
                        }
                        className={selectClass}
                        data-testid="load-test-auth-type"
                      >
                        {AUTH_TYPES.map((a) => (
                          <option key={a.value} value={a.value}>
                            {a.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Bearer */}
                    {auth.type === "bearer" && (
                      <div>
                        <label className={labelClass}>Token</label>
                        <input
                          type="text"
                          value={auth.token ?? ""}
                          onChange={(e) => setAuth({ ...auth, token: e.target.value })}
                          placeholder="{{token}}"
                          className={inputClass}
                          spellCheck={false}
                        />
                      </div>
                    )}

                    {/* Basic */}
                    {auth.type === "basic" && (
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className={labelClass}>Username</label>
                          <input
                            type="text"
                            value={auth.username ?? ""}
                            onChange={(e) => setAuth({ ...auth, username: e.target.value })}
                            placeholder="{{username}}"
                            className={inputClass}
                            spellCheck={false}
                          />
                        </div>
                        <div>
                          <label className={labelClass}>Password</label>
                          <input
                            type="password"
                            value={auth.password ?? ""}
                            onChange={(e) => setAuth({ ...auth, password: e.target.value })}
                            placeholder="{{password}}"
                            className={inputClass}
                            spellCheck={false}
                          />
                        </div>
                      </div>
                    )}

                    {/* API Key */}
                    {auth.type === "apikey" && (
                      <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className={labelClass}>Key</label>
                            <input
                              type="text"
                              value={auth.key ?? ""}
                              onChange={(e) => setAuth({ ...auth, key: e.target.value })}
                              placeholder="X-API-Key"
                              className={inputClass}
                              spellCheck={false}
                            />
                          </div>
                          <div>
                            <label className={labelClass}>Value</label>
                            <input
                              type="text"
                              value={auth.value ?? ""}
                              onChange={(e) => setAuth({ ...auth, value: e.target.value })}
                              placeholder="{{api_key}}"
                              className={inputClass}
                              spellCheck={false}
                            />
                          </div>
                        </div>
                        <div>
                          <label className={labelClass}>Add to</label>
                          <select
                            value={auth.add_to ?? "header"}
                            onChange={(e) =>
                              setAuth({ ...auth, add_to: e.target.value as "header" | "query" })
                            }
                            className={selectClass}
                          >
                            <option value="header">Header</option>
                            <option value="query">Query Parameter</option>
                          </select>
                        </div>
                      </div>
                    )}

                    {auth.type === "none" && (
                      <p className="text-[10px] leading-relaxed text-neutral-600">
                        No authentication. Select a type above to configure credentials.
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* Run button */}
              <button
                type="button"
                onClick={run}
                disabled={busy || !url}
                className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-5 py-2 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {busy ? "Running..." : "Start Load Test"}
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3">
                <StatCard label="Total Requests" value={String(result.total_requests)} />
                <StatCard label="Successful" value={String(result.successful)} color="text-emerald-400" />
                <StatCard label="Failed" value={String(result.failed)} color={result.failed > 0 ? "text-rose-400" : "text-neutral-400"} />
                <StatCard label="RPS" value={result.actual_rps.toFixed(1)} />
              </div>
              <div className="grid grid-cols-4 gap-3">
                <StatCard label="Avg Latency" value={`${result.avg_latency_ms.toFixed(0)}ms`} />
                <StatCard label="p50" value={`${result.p50_ms.toFixed(0)}ms`} />
                <StatCard label="p95" value={`${result.p95_ms.toFixed(0)}ms`} />
                <StatCard label="p99" value={`${result.p99_ms.toFixed(0)}ms`} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <StatCard label="Min Latency" value={`${result.min_latency_ms.toFixed(0)}ms`} />
                <StatCard label="Max Latency" value={`${result.max_latency_ms.toFixed(0)}ms`} />
              </div>
              {Object.keys(result.errors).length > 0 && (
                <div>
                  <p className="mb-1 text-[10px] uppercase tracking-widest text-neutral-500">Errors</p>
                  {Object.entries(result.errors).map(([err, count]) => (
                    <div key={err} className="flex justify-between text-xs">
                      <span className="text-rose-400">{err}</span>
                      <span className="text-neutral-500">{count}x</span>
                    </div>
                  ))}
                </div>
              )}
              <button
                type="button"
                onClick={() => setResult(null)}
                className="text-xs text-cobweb-400 hover:text-cobweb-300"
              >
                Run again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-lg border border-glass bg-neutral-900/30 p-3">
      <div className={`text-lg font-bold ${color ?? "text-neutral-100"}`}>{value}</div>
      <div className="mt-0.5 text-[10px] uppercase tracking-widest text-neutral-500">{label}</div>
    </div>
  );
}
