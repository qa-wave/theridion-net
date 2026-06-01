/**
 * Browser-demo fallback data — bundled synthetic results shown when the app
 * runs in a plain browser (no Tauri shell / sidecar).
 *
 * None of this is ever used inside the real Tauri desktop app; real sidecar
 * data always wins.  The data exists purely for marketing screenshots.
 */

import type { LoadRunResult, OWASPFinding, OWASPScanOutput, ExecuteResponse } from "./sidecar";

// ---------------------------------------------------------------------------
// Load-test demo result
// ---------------------------------------------------------------------------

function buildTimeline(): LoadRunResult["timeline"] {
  // 30 seconds; ramp 0-10 s, sustain 10-25 s, drain 25-30 s
  return Array.from({ length: 30 }, (_, i) => {
    const rampFactor = i < 10 ? i / 10 : i < 25 ? 1 : (30 - i) / 5;
    const baseRps = 142 * rampFactor;
    const jitter = Math.sin(i * 0.7) * 8 + Math.sin(i * 1.3) * 4;
    const rps = Math.max(0, baseRps + jitter);

    // Latency slightly rises under load
    const baseLat = 38 + rampFactor * 24;
    const latJitter = Math.cos(i * 0.5) * 6 + Math.cos(i * 1.1) * 3;
    const avg_latency_ms = Math.max(12, baseLat + latJitter);

    return {
      second: i + 1,
      rps,
      avg_latency_ms,
      error_count: i === 18 ? 3 : i === 19 ? 1 : 0,  // brief error spike
      active_users: Math.round(50 * rampFactor),
    };
  });
}

export const DEMO_LOAD_RESULT: LoadRunResult = {
  total_requests: 4_238,
  successful: 4_231,
  failed: 7,
  errors: { "connect timeout": 5, "read timeout": 2 },
  avg_latency_ms: 62.4,
  min_latency_ms: 11.2,
  max_latency_ms: 984.5,
  p50_ms: 54.1,
  p75_ms: 78.3,
  p90_ms: 98.7,
  p95_ms: 134.2,
  p99_ms: 312.8,
  requests_per_second: 141.3,
  duration_seconds: 30.0,
  timeline: buildTimeline(),
};

// ---------------------------------------------------------------------------
// Security scan demo result
// ---------------------------------------------------------------------------

const DEMO_FINDINGS: OWASPFinding[] = [
  {
    title: "SQL Injection (Reflected)",
    severity: "critical",
    scan_type: "sql_injection",
    evidence: "GET /api/users?id=1' OR '1'='1 → 500 Internal Server Error (stack trace exposed)",
    description:
      "The endpoint echoes un-sanitised SQL syntax back in the error body. An attacker can enumerate and extract database rows by injecting Boolean-based or time-based payloads.",
  },
  {
    title: "Missing Content-Security-Policy Header",
    severity: "high",
    scan_type: "xss",
    evidence: "Response headers contain no Content-Security-Policy directive",
    description:
      "Without a CSP, browsers permit inline scripts and arbitrary external origins, greatly increasing the impact of any XSS vulnerability. Add a strict CSP that restricts script sources.",
  },
  {
    title: "Wildcard CORS Origin Allowed",
    severity: "medium",
    scan_type: "auth_bypass",
    evidence: "Access-Control-Allow-Origin: *  with Access-Control-Allow-Credentials: true",
    description:
      "Returning a wildcard CORS origin alongside credentials is disallowed by the spec, but the observed combination allows cross-origin reads when combined with certain cookie policies. Restrict the allowed origin to specific domains.",
  },
  {
    title: "Sensitive Credentials in Response Body",
    severity: "high",
    scan_type: "sql_injection",
    evidence: '{"api_key": "sk-live-xxxxxxxxxxxxxxxx", "password_hash": "$2b$12$..."}',
    description:
      "The API leaks internal credentials in a JSON response. Even hashed passwords can be cracked offline. Remove all credential fields from API responses immediately.",
  },
  {
    title: "X-Frame-Options Header Missing",
    severity: "medium",
    scan_type: "xss",
    evidence: "No X-Frame-Options or frame-ancestors CSP directive found",
    description:
      "Without X-Frame-Options the page can be embedded in an attacker-controlled iframe, enabling clickjacking attacks that trick users into performing unintended actions.",
  },
  {
    title: "Rate Limiting Not Enforced on Login",
    severity: "low",
    scan_type: "rate_limit",
    evidence: "50 consecutive POST /auth/login requests succeeded with no 429 response",
    description:
      "The authentication endpoint does not enforce rate limiting, allowing brute-force and credential-stuffing attacks. Implement adaptive rate limiting with exponential back-off.",
  },
  {
    title: "Server Version Disclosure",
    severity: "low",
    scan_type: "xss",
    evidence: "Server: nginx/1.24.0  X-Powered-By: Express 4.18.2",
    description:
      "Response headers reveal exact software versions, allowing attackers to target known CVEs. Remove or obscure Server and X-Powered-By headers.",
  },
];

export const DEMO_SECURITY_RESULT: OWASPScanOutput = {
  findings: DEMO_FINDINGS,
  score: 34,
  elapsed_ms: 2847.3,
  scan_types_run: ["sql_injection", "xss", "auth_bypass", "rate_limit"],
};

// ---------------------------------------------------------------------------
// Integration response demo
// ---------------------------------------------------------------------------

export const DEMO_RESPONSE_BODY = JSON.stringify(
  {
    id: "usr_01hx7k2mn3pq4rs",
    name: "Alice Wonderland",
    email: "alice@example.com",
    role: "admin",
    plan: "pro",
    created_at: "2024-11-15T08:30:00Z",
    last_login: "2026-05-30T14:22:11Z",
    api_quota: { used: 8_412, limit: 50_000, reset_at: "2026-06-01T00:00:00Z" },
    features: ["custom_environments", "team_sync", "hub_export", "ai_assist"],
    metadata: {
      onboarding_completed: true,
      referral_source: "organic",
      timezone: "Europe/Prague",
    },
  },
  null,
  2,
);

export const DEMO_RESPONSE: ExecuteResponse = {
  status: 200,
  status_text: "OK",
  headers: {
    "content-type": "application/json; charset=utf-8",
    "x-request-id": "req_01hx7k3mn9pq4rs",
    "x-ratelimit-limit": "1000",
    "x-ratelimit-remaining": "987",
    "x-ratelimit-reset": "1748736000",
    "cache-control": "no-store",
    "content-security-policy": "default-src 'self'",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "vary": "Accept-Encoding",
    "cf-ray": "8abc1234def-FRA",
    "cf-cache-status": "DYNAMIC",
    "server": "cloudflare",
  },
  body: DEMO_RESPONSE_BODY,
  body_size_bytes: new TextEncoder().encode(DEMO_RESPONSE_BODY).length,
  elapsed_ms: 47,
  final_url: "https://api.example.com/v1/me",
  resolved_url: "https://api.example.com/v1/me",
  timing: {
    dns_ms: 1.2,
    connect_ms: 4.8,
    tls_ms: 12.1,
    server_processing_ms: 24.6,
    transfer_ms: 4.3,
    total_ms: 47.0,
  },
  cookies: {},
};
