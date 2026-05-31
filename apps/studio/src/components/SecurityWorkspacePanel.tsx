/**
 * SecurityWorkspacePanel — full-screen Security workspace.
 *
 * Combines OWASP active scanner, passive interceptor findings, and inline
 * send-to-request for individual findings. Emits RunResult v2 to Hub.
 */
import {
  AlertTriangle,
  CheckCircle,
  Info,
  Loader2,
  Play,
  RefreshCw,
  Shield,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { useCallback, useState } from "react";
import { sidecar, type OWASPFinding, type OWASPScanInput, type OWASPScanOutput, type StoredCollection } from "../lib/sidecar";
import { InterceptModal } from "./InterceptModal";

interface Props {
  collections: StoredCollection[];
  onToast?: (type: "success" | "error" | "info", msg: string) => void;
  onSendToRequest?: (method: string, url: string, headers: Record<string, string>, body: string | null) => void;
}

type OWASPScanType = "sql_injection" | "xss" | "auth_bypass" | "rate_limit";
type SeverityLevel = "critical" | "high" | "medium" | "low" | "info";

const SEVERITY_ORDER: Record<SeverityLevel, number> = {
  critical: 0, high: 1, medium: 2, low: 3, info: 4,
};

function severityColor(s: SeverityLevel) {
  switch (s) {
    case "critical": return "text-rose-400";
    case "high": return "text-orange-400";
    case "medium": return "text-amber-400";
    case "low": return "text-sky-400";
    case "info": return "text-neutral-400";
  }
}

function SeverityBadge({ severity }: { severity: SeverityLevel }) {
  const colors: Record<SeverityLevel, string> = {
    critical: "bg-rose-500/20 text-rose-400 border-rose-500/30",
    high: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    medium: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    low: "bg-sky-500/20 text-sky-400 border-sky-500/30",
    info: "bg-neutral-700/40 text-neutral-400 border-neutral-700",
  };
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${colors[severity]}`}>
      {severity}
    </span>
  );
}

function ScoreRing({ score }: { score: number }) {
  const color = score >= 80 ? "text-emerald-400" : score >= 50 ? "text-amber-400" : "text-rose-400";
  return (
    <div className="flex flex-col items-center gap-1">
      <div className={`text-4xl font-bold tabular-nums ${color}`}>{score}</div>
      <div className="text-[10px] uppercase tracking-widest text-neutral-500">Security Score</div>
    </div>
  );
}

export function SecurityWorkspacePanel({ collections, onToast, onSendToRequest }: Props) {
  const [url, setUrl] = useState("");
  const [params, setParams] = useState("");
  const [scanTypes, setScanTypes] = useState<OWASPScanType[]>(["sql_injection", "xss", "auth_bypass", "rate_limit"]);
  const [result, setResult] = useState<OWASPScanOutput | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interceptOpen, setInterceptOpen] = useState(false);
  const [selectedCollection, setSelectedCollection] = useState<string>("");

  const allRequests = collections.flatMap((c) =>
    c.items.filter((it) => !it.is_folder).map((it) => ({
      collectionName: c.name, id: it.id, name: it.name,
      method: it.method ?? "GET", url: it.url ?? "",
    }))
  );

  const handleCollectionSelect = useCallback((reqId: string) => {
    setSelectedCollection(reqId);
    const req = allRequests.find((r) => r.id === reqId);
    if (req) setUrl(req.url);
  }, [allRequests]);

  function toggleScanType(t: OWASPScanType) {
    setScanTypes((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]
    );
  }

  async function run() {
    if (!url) return;
    setBusy(true);
    setError(null);
    setResult(null);
    const parsedParams: Record<string, string> = {};
    if (params.trim()) {
      try {
        const sp = new URLSearchParams(params.trim());
        sp.forEach((v, k) => { parsedParams[k] = v; });
      } catch {
        // ignore parse errors — user might type key=value pairs
      }
    }
    try {
      const inp: OWASPScanInput = {
        url,
        method: "GET",
        headers: {},
        params: parsedParams,
        body: null,
        scan_types: scanTypes,
      };
      const res = await sidecar.owaspScan(inp);
      setResult(res);
      const critHigh = res.findings.filter((f) => f.severity === "critical" || f.severity === "high").length;
      if (critHigh > 0) {
        onToast?.("error", `Security scan: ${critHigh} critical/high finding${critHigh !== 1 ? "s" : ""}`);
      } else {
        onToast?.("success", `Security scan complete — score ${res.score}/100`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      onToast?.("error", `Scan failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  const inputCls = "w-full rounded-md border border-white/[0.06] bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-red-500/40 focus:outline-none";
  const labelCls = "mb-1 block text-[10px] uppercase tracking-widest text-neutral-500";

  const SCAN_TYPE_LABELS: Record<OWASPScanType, string> = {
    sql_injection: "SQL Injection",
    xss: "XSS",
    auth_bypass: "Auth Bypass",
    rate_limit: "Rate Limiting",
  };

  const sortedFindings = result?.findings
    ? [...result.findings].sort((a, b) => SEVERITY_ORDER[a.severity as SeverityLevel] - SEVERITY_ORDER[b.severity as SeverityLevel])
    : [];

  return (
    <div className="flex h-full overflow-hidden bg-neutral-950">
      {/* Left: Config */}
      <div className="flex w-80 shrink-0 flex-col overflow-y-auto border-r border-white/[0.06] bg-neutral-925/90 p-4 gap-4">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-red-500" />
          <span className="text-sm font-semibold text-neutral-100">Security Scan</span>
        </div>

        <div>
          <label className={labelCls}>Target URL</label>
          <input
            type="url"
            className={inputCls}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://api.example.com/endpoint"
            spellCheck={false}
          />
        </div>

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

        <div>
          <label className={labelCls}>Query params (key=value&amp;...)</label>
          <input
            type="text"
            className={inputCls}
            value={params}
            onChange={(e) => setParams(e.target.value)}
            placeholder="id=1&name=test"
            spellCheck={false}
          />
          <p className="mt-1 text-[10px] text-neutral-600">
            Params to inject payloads into
          </p>
        </div>

        <div>
          <label className={labelCls}>Scan types</label>
          <div className="space-y-1.5">
            {(Object.keys(SCAN_TYPE_LABELS) as OWASPScanType[]).map((t) => (
              <label key={t} className="flex items-center gap-2 cursor-pointer text-xs text-neutral-300">
                <input
                  type="checkbox"
                  checked={scanTypes.includes(t)}
                  onChange={() => toggleScanType(t)}
                  className="rounded border-neutral-600 accent-red-500"
                />
                {SCAN_TYPE_LABELS[t]}
              </label>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={run}
          disabled={busy || !url || scanTypes.length === 0}
          className="flex items-center justify-center gap-2 rounded-lg bg-red-700 px-4 py-2 text-xs font-semibold text-white transition hover:bg-red-600 disabled:opacity-40"
        >
          {busy ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> Scanning…</>
          ) : (
            <><ShieldAlert className="h-4 w-4" /> Run Scan</>
          )}
        </button>

        {result && !busy && (
          <button
            type="button"
            onClick={() => { setResult(null); setError(null); }}
            className="flex items-center justify-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-300 transition"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Reset
          </button>
        )}

        {/* Interceptor toggle */}
        <div className="mt-auto border-t border-white/[0.06] pt-4">
          <button
            type="button"
            onClick={() => setInterceptOpen(true)}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/[0.08] bg-neutral-900/50 px-3 py-2 text-xs text-neutral-400 transition hover:bg-neutral-800/50 hover:text-neutral-200"
          >
            <Shield className="h-3.5 w-3.5" />
            Open Interceptor
          </button>
          <p className="mt-1 text-center text-[10px] text-neutral-600">
            Capture &amp; inspect live traffic
          </p>
        </div>
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
              <Loader2 className="mx-auto h-8 w-8 animate-spin text-red-500 mb-3" />
              <p className="text-sm">Running security scan…</p>
            </div>
          </div>
        )}

        {!result && !busy && !error && (
          <div className="flex h-full items-center justify-center text-neutral-500">
            <div className="text-center">
              <Shield className="mx-auto h-12 w-12 text-neutral-700 mb-4" />
              <p className="text-sm font-medium text-neutral-400">No results yet</p>
              <p className="text-xs mt-1">Configure a target URL and run a scan</p>
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-4">
            {/* Score + summary */}
            <div className="flex items-start gap-4 rounded-lg border border-white/[0.06] bg-neutral-900/40 p-4">
              <ScoreRing score={result.score} />
              <div className="flex-1 space-y-1">
                <div className="text-sm font-medium text-neutral-200">
                  {result.findings.length === 0
                    ? "No findings — target looks clean"
                    : `${result.findings.length} finding${result.findings.length !== 1 ? "s" : ""} detected`}
                </div>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {result.scan_types_run.map((t) => (
                    <span key={t} className="rounded border border-white/[0.06] bg-neutral-800/50 px-1.5 py-0.5 text-[10px] text-neutral-400">
                      {t.replace("_", " ")}
                    </span>
                  ))}
                </div>
                <div className="text-[10px] text-neutral-600 mt-1">
                  Elapsed: {result.elapsed_ms.toFixed(0)}ms
                </div>
              </div>
            </div>

            {/* Findings list */}
            {sortedFindings.length > 0 && (
              <div className="space-y-2">
                {sortedFindings.map((f, i) => (
                  <FindingCard
                    key={i}
                    finding={f as OWASPFinding}
                    onSendToRequest={
                      onSendToRequest
                        ? () => onSendToRequest("GET", url, {}, null)
                        : undefined
                    }
                  />
                ))}
              </div>
            )}

            {result.findings.length === 0 && (
              <div className="flex items-center gap-2 rounded-lg border border-emerald-800/30 bg-emerald-950/10 px-4 py-3 text-sm text-emerald-400">
                <CheckCircle className="h-4 w-4 shrink-0" />
                No vulnerabilities detected for selected scan types
              </div>
            )}
          </div>
        )}
      </div>

      {/* Interceptor modal */}
      <InterceptModal
        open={interceptOpen}
        onClose={() => setInterceptOpen(false)}
        onSendToRequest={onSendToRequest}
      />
    </div>
  );
}

function FindingCard({
  finding,
  onSendToRequest,
}: {
  finding: OWASPFinding;
  onSendToRequest?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-lg border border-white/[0.06] bg-neutral-900/40 overflow-hidden">
      <button
        type="button"
        className="flex w-full items-start gap-3 p-3 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <SeverityIcon severity={finding.severity as SeverityLevel} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-neutral-100 truncate">{finding.title}</span>
            <SeverityBadge severity={finding.severity as SeverityLevel} />
          </div>
          <div className="mt-0.5 text-[10px] text-neutral-500 truncate">{finding.evidence}</div>
        </div>
      </button>
      {expanded && (
        <div className="border-t border-white/[0.06] px-3 pb-3 pt-2 space-y-2">
          <p className="text-xs text-neutral-400 leading-relaxed">{finding.description}</p>
          <div className="rounded bg-neutral-800/50 px-2 py-1.5 font-mono text-[10px] text-neutral-500 break-all">
            {finding.evidence}
          </div>
          {onSendToRequest && (
            <button
              type="button"
              onClick={onSendToRequest}
              className="flex items-center gap-1.5 text-[10px] text-cobweb-400 hover:text-cobweb-300 transition"
            >
              <Play className="h-3 w-3" /> Send to Request panel
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function SeverityIcon({ severity }: { severity: SeverityLevel }) {
  switch (severity) {
    case "critical":
    case "high":
      return <XCircle className={`h-4 w-4 shrink-0 mt-0.5 ${severityColor(severity)}`} />;
    case "medium":
      return <AlertTriangle className={`h-4 w-4 shrink-0 mt-0.5 ${severityColor(severity)}`} />;
    default:
      return <Info className={`h-4 w-4 shrink-0 mt-0.5 ${severityColor(severity)}`} />;
  }
}
