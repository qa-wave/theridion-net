"""OWASP security scanner: SQL injection, XSS, auth bypass, rate limit tests.

Scan results are persisted to ``$THERIDION_HOME/security_scans.jsonl`` (newest
first, capped at 50 entries) so the SecurityWorkspacePanel can display past
scans on first load without re-running anything.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from theridion_sidecar.storage import home_dir

router = APIRouter(prefix="/api/security", tags=["owasp-scanner"])

_MAX_SAVED_SCANS = 50


# ----- Persistence ----------------------------------------------------------


def _security_scans_path() -> Path:
    d = home_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "security_scans.jsonl"


def _read_saved_scans() -> list[dict[str, Any]]:
    p = _security_scans_path()
    if not p.exists():
        return []
    scans: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            scans.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return scans


def _write_saved_scans(scans: list[dict[str, Any]]) -> None:
    p = _security_scans_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="security_scans.", suffix=".tmp", dir=str(p.parent))
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for s in scans:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, p)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _persist_scan(scan_dict: dict[str, Any]) -> None:
    scans = _read_saved_scans()
    scans.insert(0, scan_dict)
    if len(scans) > _MAX_SAVED_SCANS:
        scans = scans[:_MAX_SAVED_SCANS]
    _write_saved_scans(scans)

SeverityLevel = Literal["critical", "high", "medium", "low", "info"]
ScanType = Literal["sql_injection", "xss", "auth_bypass", "rate_limit"]


class OWASPScanInput(BaseModel):
    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    scan_types: list[ScanType] = Field(
        default_factory=lambda: ["sql_injection", "xss", "auth_bypass", "rate_limit"],
    )


class Finding(BaseModel):
    scan_type: ScanType
    severity: SeverityLevel
    title: str
    evidence: str
    description: str


class OWASPScanOutput(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    score: int = 100  # 0-100, higher is safer
    scan_types_run: list[ScanType] = Field(default_factory=list)
    elapsed_ms: float = 0


# --- Payloads ---

SQL_PAYLOADS = [
    "' OR '1'='1",
    "1; DROP TABLE users--",
    "' UNION SELECT NULL,NULL--",
    "1' AND '1'='1",
    "admin'--",
]

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    '"><img src=x onerror=alert(1)>',
    "javascript:alert(document.cookie)",
]

RATE_LIMIT_COUNT = 20


async def _send(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
    body: str | None = None,
) -> httpx.Response | None:
    try:
        return await client.request(
            method,
            url,
            headers=headers,
            params=params,
            content=body,
            timeout=10,
        )
    except Exception:
        return None


async def _scan_sql_injection(
    client: httpx.AsyncClient,
    inp: OWASPScanInput,
) -> list[Finding]:
    findings: list[Finding] = []
    for payload in SQL_PAYLOADS:
        # Inject into each param
        for key in inp.params:
            injected = {**inp.params, key: payload}
            resp = await _send(client, inp.method, inp.url, inp.headers, injected, inp.body)
            if resp is None:
                continue
            body_lower = resp.text.lower()
            # Look for SQL error indicators in response
            sql_errors = [
                "sql syntax", "mysql", "sqlite", "postgresql", "ora-",
                "syntax error", "unclosed quotation", "unterminated",
                "you have an error in your sql",
            ]
            for err in sql_errors:
                if err in body_lower:
                    findings.append(Finding(
                        scan_type="sql_injection",
                        severity="critical",
                        title=f"SQL error leaked via param '{key}'",
                        evidence=f"Payload: {payload} | Param: {key} | Matched: '{err}'",
                        description="The server returned a database error message when given a SQL injection payload, suggesting the input is not properly sanitized.",
                    ))
                    break
            # Check if injected payload is reflected without sanitisation
            if payload in resp.text and resp.status_code == 200:
                findings.append(Finding(
                    scan_type="sql_injection",
                    severity="high",
                    title=f"SQL payload reflected in response via '{key}'",
                    evidence=f"Payload: {payload} | Status: {resp.status_code}",
                    description="The SQL injection payload was reflected in the response body, indicating potential lack of input sanitization.",
                ))
    return findings


async def _scan_xss(
    client: httpx.AsyncClient,
    inp: OWASPScanInput,
) -> list[Finding]:
    findings: list[Finding] = []
    for payload in XSS_PAYLOADS:
        for key in inp.params:
            injected = {**inp.params, key: payload}
            resp = await _send(client, inp.method, inp.url, inp.headers, injected, inp.body)
            if resp is None:
                continue
            if payload in resp.text:
                findings.append(Finding(
                    scan_type="xss",
                    severity="high",
                    title=f"XSS payload reflected via param '{key}'",
                    evidence=f"Payload: {payload} | Status: {resp.status_code}",
                    description="The XSS payload was returned unescaped in the response, which could allow cross-site scripting attacks.",
                ))
            # Check for missing security headers
            csp = resp.headers.get("content-security-policy", "")
            x_xss = resp.headers.get("x-xss-protection", "")
            if not csp and not x_xss:
                findings.append(Finding(
                    scan_type="xss",
                    severity="medium",
                    title="Missing XSS protection headers",
                    evidence=f"No Content-Security-Policy or X-XSS-Protection header found",
                    description="The response lacks CSP and X-XSS-Protection headers, reducing defense against XSS.",
                ))
                break  # Only report once
        else:
            continue
        break
    return findings


async def _scan_auth_bypass(
    client: httpx.AsyncClient,
    inp: OWASPScanInput,
) -> list[Finding]:
    findings: list[Finding] = []
    # First, get baseline with auth
    baseline = await _send(client, inp.method, inp.url, inp.headers, inp.params, inp.body)
    if baseline is None:
        return findings

    # Remove authorization headers
    stripped = {
        k: v for k, v in inp.headers.items()
        if k.lower() not in ("authorization", "x-api-key", "cookie", "x-auth-token")
    }
    no_auth = await _send(client, inp.method, inp.url, stripped, inp.params, inp.body)
    if no_auth is None:
        return findings

    if no_auth.status_code == baseline.status_code and baseline.status_code < 400:
        findings.append(Finding(
            scan_type="auth_bypass",
            severity="critical",
            title="Endpoint accessible without authentication",
            evidence=f"With auth: {baseline.status_code} | Without auth: {no_auth.status_code}",
            description="Removing authentication headers did not change the response status, suggesting the endpoint may not enforce auth.",
        ))
    elif no_auth.status_code < 400:
        findings.append(Finding(
            scan_type="auth_bypass",
            severity="high",
            title="Endpoint returns success without auth headers",
            evidence=f"Without auth status: {no_auth.status_code}",
            description="The endpoint returned a success status code even without authentication credentials.",
        ))

    return findings


async def _scan_rate_limit(
    client: httpx.AsyncClient,
    inp: OWASPScanInput,
) -> list[Finding]:
    findings: list[Finding] = []
    statuses: list[int] = []
    tasks = []
    for _ in range(RATE_LIMIT_COUNT):
        tasks.append(_send(client, inp.method, inp.url, inp.headers, inp.params, inp.body))

    responses = await asyncio.gather(*tasks)
    for resp in responses:
        if resp is not None:
            statuses.append(resp.status_code)

    rate_limited = sum(1 for s in statuses if s == 429)
    if rate_limited == 0 and len(statuses) >= RATE_LIMIT_COUNT:
        findings.append(Finding(
            scan_type="rate_limit",
            severity="medium",
            title="No rate limiting detected",
            evidence=f"Sent {RATE_LIMIT_COUNT} rapid requests, 0 received 429 status",
            description="The endpoint did not return any 429 (Too Many Requests) responses during rapid-fire testing.",
        ))
    elif rate_limited > 0:
        findings.append(Finding(
            scan_type="rate_limit",
            severity="info",
            title="Rate limiting is active",
            evidence=f"Sent {RATE_LIMIT_COUNT} requests, {rate_limited} received 429",
            description="The endpoint enforces rate limiting.",
        ))

    return findings


def _compute_score(findings: list[Finding]) -> int:
    """Compute a security score from 0-100 based on findings."""
    score = 100
    for f in findings:
        if f.severity == "critical":
            score -= 25
        elif f.severity == "high":
            score -= 15
        elif f.severity == "medium":
            score -= 10
        elif f.severity == "low":
            score -= 5
        # info doesn't deduct
    return max(0, score)


@router.post("/owasp-scan", response_model=OWASPScanOutput)
async def owasp_scan(body: OWASPScanInput) -> OWASPScanOutput:
    t0 = time.monotonic()
    findings: list[Finding] = []
    scan_types_run: list[ScanType] = []

    async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
        if "sql_injection" in body.scan_types:
            scan_types_run.append("sql_injection")
            findings.extend(await _scan_sql_injection(client, body))

        if "xss" in body.scan_types:
            scan_types_run.append("xss")
            findings.extend(await _scan_xss(client, body))

        if "auth_bypass" in body.scan_types:
            scan_types_run.append("auth_bypass")
            findings.extend(await _scan_auth_bypass(client, body))

        if "rate_limit" in body.scan_types:
            scan_types_run.append("rate_limit")
            findings.extend(await _scan_rate_limit(client, body))

    elapsed = (time.monotonic() - t0) * 1000
    score = _compute_score(findings)

    result = OWASPScanOutput(
        findings=findings,
        score=score,
        scan_types_run=scan_types_run,
        elapsed_ms=round(elapsed, 1),
    )

    # Persist so the panel can show historical scans on next launch.
    saved_dict = result.model_dump(mode="json")
    saved_dict["id"] = str(uuid.uuid4())
    saved_dict["url"] = body.url
    saved_dict["method"] = body.method
    saved_dict["started_at"] = time.time() - elapsed / 1000
    _persist_scan(saved_dict)

    return result


# ----- Saved scans endpoint -------------------------------------------------


class SavedSecurityScan(BaseModel):
    """Summary of a persisted security scan result."""

    id: str
    url: str
    method: str
    scan_types_run: list[str]
    score: int
    elapsed_ms: float
    started_at: float
    findings: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/saved", response_model=list[SavedSecurityScan])
def list_saved_scans() -> list[SavedSecurityScan]:
    """Return all persisted security scan results (newest first)."""
    raw = _read_saved_scans()
    out: list[SavedSecurityScan] = []
    for s in raw:
        try:
            out.append(SavedSecurityScan(
                id=s.get("id", str(uuid.uuid4())),
                url=s.get("url", ""),
                method=s.get("method", "GET"),
                scan_types_run=s.get("scan_types_run", []),
                score=int(s.get("score", 100)),
                elapsed_ms=float(s.get("elapsed_ms", 0)),
                started_at=float(s.get("started_at", 0)),
                findings=s.get("findings", []),
            ))
        except Exception:
            continue
    return out
