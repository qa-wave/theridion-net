/**
 * InterceptModal — real-time intercepting proxy UI.
 *
 * Connects to the sidecar /api/interceptor/stream SSE endpoint and displays
 * captured flows with passive scanner flags.  Supports:
 *
 * - Enable/disable interception
 * - Break-on-all mode (pause each flow for review/edit before forwarding)
 * - Edit-and-forward: modify request before it continues
 * - Send-to-request: open captured request in the main panel
 * - Clear flows
 */
import {
  AlertTriangle,
  CheckCircle,
  Circle,
  Edit3,
  Play,
  Send,
  Shield,
  Terminal,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { getSidecarBaseUrl } from "../lib/sidecar";
import { useT } from "../lib/i18n/context";

// ---------------------------------------------------------------------------
// Types (mirrors sidecar interceptor.py)
// ---------------------------------------------------------------------------

interface ScanFlag {
  type: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  location: string;
  detail: string;
}

interface CapturedFlow {
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

interface InterceptConfig {
  enabled: boolean;
  break_on_all: boolean;
  passive_scan: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function flagSeverityColor(s: ScanFlag["severity"]) {
  switch (s) {
    case "critical": return "text-rose-400";
    case "high": return "text-orange-400";
    case "medium": return "text-amber-400";
    case "low": return "text-sky-400";
    default: return "text-neutral-400";
  }
}

function stateIcon(state: CapturedFlow["state"]) {
  switch (state) {
    case "paused": return <Circle className="h-3.5 w-3.5 text-amber-400 animate-pulse" />;
    case "forwarded": return <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />;
    case "error": return <XCircle className="h-3.5 w-3.5 text-rose-400" />;
    default: return <Circle className="h-3.5 w-3.5 text-neutral-500" />;
  }
}

function methodColor(method: string) {
  const m = method.toUpperCase();
  switch (m) {
    case "GET": return "text-sky-400";
    case "POST": return "text-emerald-400";
    case "PUT": return "text-amber-400";
    case "PATCH": return "text-violet-400";
    case "DELETE": return "text-rose-400";
    default: return "text-neutral-400";
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  open: boolean;
  onClose: () => void;
  onSendToRequest?: (method: string, url: string, headers: Record<string, string>, body: string | null) => void;
}

export function InterceptModal({ open, onClose, onSendToRequest }: Props) {
  const [flows, setFlows] = useState<CapturedFlow[]>([]);
  const [config, setConfig] = useState<InterceptConfig>({ enabled: false, break_on_all: false, passive_scan: true });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editMethod, setEditMethod] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [editBody, setEditBody] = useState("");
  const [connected, setConnected] = useState(false);
  // Reserved for future native EventSource: const eventSourceRef = useRef<EventSource | null>(null);

  // Connect to SSE stream
  useEffect(() => {
    if (!open) return;

    const baseUrl = getSidecarBaseUrl();
    const storedToken = localStorage.getItem("theridion.sidecar-token") || "";
    const url = `${baseUrl}/api/interceptor/stream`;

    // EventSource doesn't support custom headers; use fetch + ReadableStream instead
    let cancelled = false;
    const controller = new AbortController();

    async function connect() {
      try {
        const resp = await fetch(url, {
          signal: controller.signal,
          headers: {
            Accept: "text/event-stream",
            "X-Theridion-Token": storedToken,
          },
        });
        if (!resp.body) return;
        setConnected(true);
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          let eventName = "message";
          let dataParts: string[] = [];

          for (const line of lines) {
            if (line.startsWith("event:")) {
              eventName = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              dataParts.push(line.slice(5).trim());
            } else if (line === "") {
              // Dispatch event
              if (dataParts.length > 0) {
                try {
                  const payload = JSON.parse(dataParts.join("\n"));
                  handleSseEvent(eventName, payload);
                } catch { /* ignore parse errors */ }
              }
              eventName = "message";
              dataParts = [];
            }
          }
        }
      } catch (e) {
        if (!cancelled) {
          setConnected(false);
        }
      }
    }

    void connect();
    return () => {
      cancelled = true;
      setConnected(false);
      controller.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function handleSseEvent(event: string, data: unknown) {
    if (event === "snapshot") {
      const snap = data as { flows: CapturedFlow[]; enabled: boolean; break_on_all: boolean; passive_scan: boolean };
      setFlows(snap.flows ?? []);
      setConfig({ enabled: snap.enabled, break_on_all: snap.break_on_all, passive_scan: snap.passive_scan });
    } else if (event === "flow:captured" || event === "flow:forwarded") {
      const flow = data as CapturedFlow;
      setFlows((prev) => {
        const idx = prev.findIndex((f) => f.flow_id === flow.flow_id);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = flow;
          return next;
        }
        return [flow, ...prev].slice(0, 500);
      });
    } else if (event === "flow:paused") {
      const { flow_id } = data as { flow_id: string };
      setFlows((prev) => prev.map((f) => f.flow_id === flow_id ? { ...f, state: "paused" } : f));
    } else if (event === "flow:error") {
      const { flow_id, error } = data as { flow_id: string; error: string };
      setFlows((prev) => prev.map((f) => f.flow_id === flow_id ? { ...f, state: "error", error } : f));
    } else if (event === "flows:cleared") {
      setFlows([]);
    } else if (event === "config") {
      setConfig(data as InterceptConfig);
    }
  }

  async function updateConfig(patch: Partial<InterceptConfig>) {
    const next = { ...config, ...patch };
    setConfig(next);
    try {
      const base = getSidecarBaseUrl();
      const t = localStorage.getItem("theridion.sidecar-token") || "";
      await fetch(`${base}/api/interceptor/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Theridion-Token": t },
        body: JSON.stringify(next),
      });
    } catch { /* non-critical */ }
  }

  async function releaseBreakpoint(flowId: string, edit?: { method: string; url: string; body: string }) {
    try {
      const base = getSidecarBaseUrl();
      const t = localStorage.getItem("theridion.sidecar-token") || "";
      const body = edit
        ? JSON.stringify({ flow_id: flowId, method: edit.method, url: edit.url, body: edit.body || null })
        : null;
      await fetch(`${base}/api/interceptor/release/${flowId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Theridion-Token": t },
        body,
      });
    } catch { /* non-critical */ }
  }

  async function clearFlows() {
    try {
      const base = getSidecarBaseUrl();
      const t = localStorage.getItem("theridion.sidecar-token") || "";
      await fetch(`${base}/api/interceptor/flows`, {
        method: "DELETE",
        headers: { "X-Theridion-Token": t },
      });
      setFlows([]);
    } catch { /* non-critical */ }
  }

  const selectedFlow = flows.find((f) => f.flow_id === selectedId) ?? null;

  function startEdit(flow: CapturedFlow) {
    setEditMethod(flow.method);
    setEditUrl(flow.url);
    setEditBody(flow.request_body ?? "");
    setEditMode(true);
  }

  async function sendEdit(flow: CapturedFlow) {
    await releaseBreakpoint(flow.flow_id, { method: editMethod, url: editUrl, body: editBody });
    setEditMode(false);
  }

  const t = useT();

  if (!open) return null;

  const inputCls = "w-full rounded border border-white/[0.06] bg-neutral-900/50 px-2 py-1 text-xs text-neutral-100 focus:border-red-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[80vh] w-[90vw] max-w-6xl flex-col overflow-hidden rounded-xl border border-white/[0.08] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
          <div className="flex items-center gap-3">
            <Shield className="h-4 w-4 text-red-500" />
            <span className="text-sm font-semibold text-neutral-100">{t("intercept.title")}</span>
            <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-500" : "bg-neutral-600"}`} title={connected ? t("intercept.connected") : t("intercept.disconnected")} />
            <span className="text-[10px] text-neutral-500">{t("intercept.flows", { n: flows.length })}</span>
          </div>
          <div className="flex items-center gap-3">
            {/* Enable toggle */}
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-neutral-400">
              <span>{t("intercept.toggle.intercept")}</span>
              <button
                type="button"
                role="switch"
                aria-checked={config.enabled}
                onClick={() => updateConfig({ enabled: !config.enabled })}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${config.enabled ? "bg-red-600" : "bg-neutral-700"}`}
              >
                <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${config.enabled ? "translate-x-[18px]" : "translate-x-[2px]"}`} />
              </button>
            </label>
            {/* Break-on-all */}
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-neutral-400">
              <span>{t("intercept.toggle.breakAll")}</span>
              <button
                type="button"
                role="switch"
                aria-checked={config.break_on_all}
                onClick={() => updateConfig({ break_on_all: !config.break_on_all })}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${config.break_on_all ? "bg-amber-600" : "bg-neutral-700"}`}
              >
                <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${config.break_on_all ? "translate-x-[18px]" : "translate-x-[2px]"}`} />
              </button>
            </label>
            {/* Passive scan */}
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-neutral-400">
              <span>{t("intercept.toggle.autoScan")}</span>
              <button
                type="button"
                role="switch"
                aria-checked={config.passive_scan}
                onClick={() => updateConfig({ passive_scan: !config.passive_scan })}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${config.passive_scan ? "bg-sky-600" : "bg-neutral-700"}`}
              >
                <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${config.passive_scan ? "translate-x-[18px]" : "translate-x-[2px]"}`} />
              </button>
            </label>
            <button
              type="button"
              onClick={clearFlows}
              className="flex items-center gap-1 rounded px-2 py-1 text-[10px] text-neutral-500 hover:bg-neutral-800 hover:text-neutral-300 transition"
            >
              <Trash2 className="h-3 w-3" /> {t("intercept.clear")}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1 text-neutral-500 hover:bg-white/[0.05] hover:text-neutral-200"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex flex-1 min-h-0">
          {/* Flow list */}
          <div className="flex w-72 shrink-0 flex-col overflow-hidden border-r border-white/[0.06]">
            <div className="flex-1 overflow-y-auto">
              {flows.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-neutral-600 p-4 text-center">
                  <Terminal className="h-8 w-8 mb-2" />
                  <p className="text-xs">{t("intercept.empty.title")}</p>
                  {!config.enabled && (
                    <p className="text-[10px] mt-1">{t("intercept.empty.hint")}</p>
                  )}
                </div>
              )}
              {flows.map((flow) => (
                <button
                  key={flow.flow_id}
                  type="button"
                  onClick={() => { setSelectedId(flow.flow_id); setEditMode(false); }}
                  className={`flex w-full items-start gap-2 px-3 py-2 text-left text-xs transition-colors border-b border-white/[0.03] ${
                    selectedId === flow.flow_id
                      ? "bg-white/[0.06]"
                      : "hover:bg-white/[0.03]"
                  }`}
                >
                  {stateIcon(flow.state)}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className={`font-mono font-bold ${methodColor(flow.method)}`}>{flow.method}</span>
                      <span className="truncate text-neutral-300">{new URL(flow.url.startsWith("http") ? flow.url : `http://${flow.url}`).pathname}</span>
                    </div>
                    <div className="text-[10px] text-neutral-600 truncate">{flow.url}</div>
                    {flow.flags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {flow.flags.slice(0, 2).map((f, i) => (
                          <span key={i} className={`text-[9px] ${flagSeverityColor(f.severity)}`}>
                            ● {f.type.replace("_", " ")}
                          </span>
                        ))}
                        {flow.flags.length > 2 && (
                          <span className="text-[9px] text-neutral-600">+{flow.flags.length - 2} more</span>
                        )}
                      </div>
                    )}
                  </div>
                  {flow.status_code && (
                    <span className={`ml-auto font-mono text-[10px] ${flow.status_code < 300 ? "text-emerald-400" : flow.status_code < 400 ? "text-sky-400" : flow.status_code < 500 ? "text-amber-400" : "text-rose-400"}`}>
                      {flow.status_code}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Detail pane */}
          <div className="flex flex-1 min-w-0 flex-col overflow-hidden">
            {!selectedFlow ? (
              <div className="flex h-full items-center justify-center text-neutral-600">
                <p className="text-xs">{t("intercept.selectFlow")}</p>
              </div>
            ) : (
              <div className="flex flex-1 min-h-0 flex-col overflow-y-auto p-4 space-y-4">
                {/* Actions */}
                <div className="flex items-center gap-2 flex-wrap">
                  {selectedFlow.state === "paused" && !editMode && (
                    <>
                      <button
                        type="button"
                        onClick={() => releaseBreakpoint(selectedFlow.flow_id)}
                        className="flex items-center gap-1.5 rounded bg-emerald-800/40 px-3 py-1.5 text-xs text-emerald-300 hover:bg-emerald-800/60 transition"
                      >
                        <Play className="h-3.5 w-3.5" /> {t("intercept.forward")}
                      </button>
                      <button
                        type="button"
                        onClick={() => startEdit(selectedFlow)}
                        className="flex items-center gap-1.5 rounded bg-amber-800/40 px-3 py-1.5 text-xs text-amber-300 hover:bg-amber-800/60 transition"
                      >
                        <Edit3 className="h-3.5 w-3.5" /> {t("intercept.editForward")}
                      </button>
                    </>
                  )}
                  {selectedFlow.state === "paused" && editMode && (
                    <>
                      <button
                        type="button"
                        onClick={() => sendEdit(selectedFlow)}
                        className="flex items-center gap-1.5 rounded bg-emerald-800/40 px-3 py-1.5 text-xs text-emerald-300 hover:bg-emerald-800/60 transition"
                      >
                        <Send className="h-3.5 w-3.5" /> {t("intercept.sendEdited")}
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditMode(false)}
                        className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs text-neutral-400 hover:text-neutral-200 transition"
                      >
                        <X className="h-3.5 w-3.5" /> {t("intercept.cancel")}
                      </button>
                    </>
                  )}
                  {onSendToRequest && (
                    <button
                      type="button"
                      onClick={() => {
                        onSendToRequest(
                          selectedFlow.method,
                          selectedFlow.url,
                          selectedFlow.request_headers,
                          selectedFlow.request_body,
                        );
                        onClose();
                      }}
                      className="flex items-center gap-1.5 rounded bg-neutral-800/60 px-3 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700/60 transition"
                    >
                      <Terminal className="h-3.5 w-3.5" /> {t("intercept.sendToRequest")}
                    </button>
                  )}
                </div>

                {/* Edit form */}
                {editMode && (
                  <div className="space-y-2 rounded-lg border border-amber-800/30 bg-amber-950/10 p-3">
                    <p className="text-[10px] uppercase tracking-widest text-amber-500">{t("intercept.edit.label")}</p>
                    <div className="grid grid-cols-3 gap-2">
                      <input className={inputCls} value={editMethod} onChange={(e) => setEditMethod(e.target.value)} placeholder={t("intercept.edit.method")} />
                      <input className={`${inputCls} col-span-2`} value={editUrl} onChange={(e) => setEditUrl(e.target.value)} placeholder={t("intercept.edit.url")} />
                    </div>
                    <textarea
                      className={`${inputCls} font-mono h-24 resize-none`}
                      value={editBody}
                      onChange={(e) => setEditBody(e.target.value)}
                      placeholder={t("intercept.edit.body")}
                    />
                  </div>
                )}

                {/* Flags */}
                {selectedFlow.flags.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[10px] uppercase tracking-widest text-neutral-500">{t("intercept.flags")}</p>
                    {selectedFlow.flags.map((flag, i) => (
                      <div key={i} className="flex items-start gap-2 rounded border border-white/[0.05] bg-neutral-900/30 px-2 py-1.5">
                        <AlertTriangle className={`h-3.5 w-3.5 shrink-0 mt-0.5 ${flagSeverityColor(flag.severity)}`} />
                        <div>
                          <div className={`text-xs font-medium ${flagSeverityColor(flag.severity)}`}>{flag.type.replace(/_/g, " ")}</div>
                          <div className="text-[10px] text-neutral-400">{flag.detail}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Request */}
                <Section title={t("intercept.section.request")}>
                  <div className="font-mono text-xs">
                    <span className={`font-bold ${methodColor(selectedFlow.method)}`}>{selectedFlow.method}</span>
                    {" "}
                    <span className="text-neutral-300 break-all">{selectedFlow.url}</span>
                  </div>
                  <HeaderTable headers={selectedFlow.request_headers} />
                  {selectedFlow.request_body && (
                    <pre className="mt-2 rounded bg-neutral-900/60 px-2 py-2 font-mono text-[10px] text-neutral-400 overflow-auto max-h-40">
                      {selectedFlow.request_body.slice(0, 2000)}
                    </pre>
                  )}
                </Section>

                {/* Response */}
                {selectedFlow.state === "forwarded" && (
                  <Section title={t("intercept.section.response")}>
                    <div className="flex items-center gap-2 text-xs">
                      <span className={`font-mono font-bold ${
                        (selectedFlow.status_code ?? 0) < 300 ? "text-emerald-400"
                        : (selectedFlow.status_code ?? 0) < 400 ? "text-sky-400"
                        : (selectedFlow.status_code ?? 0) < 500 ? "text-amber-400"
                        : "text-rose-400"
                      }`}>{selectedFlow.status_code}</span>
                      {selectedFlow.elapsed_ms != null && (
                        <span className="text-neutral-500">{selectedFlow.elapsed_ms.toFixed(0)}ms</span>
                      )}
                    </div>
                    <HeaderTable headers={selectedFlow.response_headers} />
                    {selectedFlow.response_body && (
                      <pre className="mt-2 rounded bg-neutral-900/60 px-2 py-2 font-mono text-[10px] text-neutral-400 overflow-auto max-h-48">
                        {selectedFlow.response_body.slice(0, 3000)}
                      </pre>
                    )}
                  </Section>
                )}

                {selectedFlow.state === "error" && (
                  <div className="rounded border border-rose-800/30 bg-rose-950/10 px-3 py-2 text-xs text-rose-400">
                    {selectedFlow.error}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <p className="text-[10px] uppercase tracking-widest text-neutral-500">{title}</p>
      <div className="rounded-lg border border-white/[0.05] bg-neutral-900/30 p-3 space-y-1">
        {children}
      </div>
    </div>
  );
}

function HeaderTable({ headers }: { headers: Record<string, string> }) {
  const entries = Object.entries(headers);
  if (entries.length === 0) return null;
  return (
    <div className="mt-1 space-y-0.5 max-h-28 overflow-y-auto">
      {entries.map(([k, v]) => (
        <div key={k} className="flex gap-2 text-[10px]">
          <span className="text-neutral-500 shrink-0 w-32 truncate">{k}</span>
          <span className="text-neutral-400 truncate">{v}</span>
        </div>
      ))}
    </div>
  );
}
