"""Network probe — async port scanner + HTTP traffic capture (HAR).

Two independent capabilities in one module:

Port scanner
------------
* Async TCP connect probe (non-root, no raw sockets).
* Supports a list of ports and/or common well-known port shorthand ``"common"``.
* Concurrency-limited via asyncio.Semaphore to avoid exhausting file descriptors.
* Service fingerprint: send a tiny banner probe (HTTP GET / SMTP EHLO / etc.)
  and return the first 256 bytes of the greeting.

HAR traffic capture
-------------------
* An in-process httpx hook captures every request/response pair through a
  shared ``httpx.AsyncClient`` and serialises them to the HAR 1.2 format.
* Captured entries can be exported via GET /api/network/har/{session_id} or
  the session can be cleared.
* Useful for recording a multi-step API flow and exporting to .har for
  sharing / importing into other tools.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/network", tags=["network"])

# ---------------------------------------------------------------------------
# Common ports
# ---------------------------------------------------------------------------

_COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 143, 443, 465, 587, 993, 995,
    3000, 3306, 5432, 5900, 6379, 8080, 8443, 8888, 9200, 27017,
]

_SERVICE_HINTS: dict[int, str] = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns",
    80: "http", 110: "pop3", 143: "imap", 443: "https", 465: "smtps",
    587: "submission", 993: "imaps", 995: "pop3s", 3000: "http-alt",
    3306: "mysql", 5432: "postgresql", 5900: "vnc", 6379: "redis",
    8080: "http-proxy", 8443: "https-alt", 9200: "elasticsearch",
    27017: "mongodb",
}

_BANNER_PROBE = b"HEAD / HTTP/1.0\r\nHost: probe\r\n\r\n"

# ---------------------------------------------------------------------------
# HAR session state
# ---------------------------------------------------------------------------

# session_id → list of HAR entry dicts
_har_sessions: dict[str, list[dict[str, Any]]] = {}
_MAX_ENTRIES = 1_000


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PortScanInput(BaseModel):
    host: str = Field(..., min_length=1)
    ports: list[int] | str = "common"
    timeout_ms: int = Field(default=2_000, ge=100, le=30_000)
    concurrency: int = Field(default=100, ge=1, le=500)
    banner_grab: bool = False


class PortResult(BaseModel):
    port: int
    open: bool
    service_hint: str | None = None
    banner: str | None = None
    elapsed_ms: float


class PortScanResult(BaseModel):
    host: str
    scanned: int
    open_count: int
    results: list[PortResult]
    elapsed_ms: float


class HarSessionStartInput(BaseModel):
    label: str = "capture"


class HarSessionOutput(BaseModel):
    session_id: str
    label: str
    entry_count: int


class HarCaptureInput(BaseModel):
    session_id: str
    url: str = Field(..., min_length=1)
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    follow_redirects: bool = True
    timeout_ms: int = Field(default=30_000, ge=100, le=120_000)


class HarCaptureResult(BaseModel):
    session_id: str
    entry_index: int
    status_code: int | None
    elapsed_ms: float
    error: str | None


# ---------------------------------------------------------------------------
# Port scanner
# ---------------------------------------------------------------------------


async def _probe_port(
    host: str,
    port: int,
    timeout_s: float,
    banner_grab: bool,
) -> PortResult:
    t0 = time.perf_counter()
    open_: bool = False
    banner: str | None = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_s,
        )
        open_ = True
        if banner_grab:
            try:
                # Try a small HTTP probe first; works for HTTP, SSH, FTP often
                # returns a banner immediately on connect.
                writer.write(_BANNER_PROBE)
                await asyncio.wait_for(writer.drain(), timeout=1.0)
                raw = await asyncio.wait_for(reader.read(256), timeout=2.0)
                banner = raw.decode("utf-8", errors="replace").strip()[:256]
            except Exception:
                # Best-effort — ignore banner errors
                pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
    except (OSError, asyncio.TimeoutError):
        pass
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return PortResult(
        port=port,
        open=open_,
        service_hint=_SERVICE_HINTS.get(port),
        banner=banner,
        elapsed_ms=round(elapsed_ms, 2),
    )


@router.post("/portscan", response_model=PortScanResult)
async def port_scan(body: PortScanInput) -> PortScanResult:
    """Async TCP port scanner.

    - ``ports="common"`` scans a curated list of ~24 well-known ports.
    - ``ports=[80, 443, 8080]`` scans the specified list.
    """
    if isinstance(body.ports, str) and body.ports == "common":
        ports = _COMMON_PORTS
    elif isinstance(body.ports, list):
        ports = [p for p in body.ports if 1 <= p <= 65535]
    else:
        raise HTTPException(status_code=422, detail="ports must be 'common' or a list of ints")

    if not ports:
        raise HTTPException(status_code=422, detail="no valid ports to scan")

    timeout_s = body.timeout_ms / 1000.0
    sem = asyncio.Semaphore(body.concurrency)
    t0 = time.perf_counter()

    async def _bounded(port: int) -> PortResult:
        async with sem:
            return await _probe_port(body.host, port, timeout_s, body.banner_grab)

    results = await asyncio.gather(*[_bounded(p) for p in ports])
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    open_results = [r for r in results if r.open]

    return PortScanResult(
        host=body.host,
        scanned=len(ports),
        open_count=len(open_results),
        results=list(results),
        elapsed_ms=round(elapsed_ms, 2),
    )


# ---------------------------------------------------------------------------
# HAR capture
# ---------------------------------------------------------------------------

_har_session_labels: dict[str, str] = {}


@router.post("/har/sessions", response_model=HarSessionOutput)
def start_har_session(body: HarSessionStartInput) -> HarSessionOutput:
    """Create a new HAR capture session."""
    sid = str(uuid.uuid4())
    _har_sessions[sid] = []
    _har_session_labels[sid] = body.label
    return HarSessionOutput(session_id=sid, label=body.label, entry_count=0)


@router.get("/har/sessions", response_model=list[HarSessionOutput])
def list_har_sessions() -> list[HarSessionOutput]:
    return [
        HarSessionOutput(
            session_id=sid,
            label=_har_session_labels.get(sid, ""),
            entry_count=len(entries),
        )
        for sid, entries in _har_sessions.items()
    ]


@router.post("/har/capture", response_model=HarCaptureResult)
async def har_capture(body: HarCaptureInput) -> HarCaptureResult:
    """Execute a request and append the entry to the HAR session."""
    if body.session_id not in _har_sessions:
        raise HTTPException(status_code=404, detail="session not found")

    timeout = body.timeout_ms / 1000.0
    content = body.body.encode("utf-8") if body.body else None
    t0 = time.perf_counter()
    status_code: int | None = None
    error: str | None = None
    resp: httpx.Response | None = None

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=body.follow_redirects,
            verify=False,  # noqa: S501
        ) as client:
            resp = await client.request(
                method=body.method,
                url=body.url,
                headers=body.headers,
                content=content,
            )
            status_code = resp.status_code
    except Exception as exc:
        error = str(exc)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Build HAR 1.2 entry
    entry = _build_har_entry(body, resp, elapsed_ms, error)
    entries = _har_sessions[body.session_id]
    entries.append(entry)
    if len(entries) > _MAX_ENTRIES:
        entries.pop(0)
    idx = len(entries) - 1

    return HarCaptureResult(
        session_id=body.session_id,
        entry_index=idx,
        status_code=status_code,
        elapsed_ms=round(elapsed_ms, 2),
        error=error,
    )


@router.get("/har/{session_id}")
def export_har(session_id: str) -> dict:
    """Export session as a HAR 1.2 document (JSON)."""
    if session_id not in _har_sessions:
        raise HTTPException(status_code=404, detail="session not found")
    entries = _har_sessions[session_id]
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "Theridion Net", "version": "1.0"},
            "entries": entries,
        }
    }


@router.delete("/har/{session_id}", response_model=dict)
def clear_har_session(session_id: str) -> dict:
    """Clear all entries in a HAR session."""
    if session_id not in _har_sessions:
        raise HTTPException(status_code=404, detail="session not found")
    count = len(_har_sessions[session_id])
    _har_sessions[session_id].clear()
    return {"cleared": count, "session_id": session_id}


# ---------------------------------------------------------------------------
# HAR helpers
# ---------------------------------------------------------------------------


def _build_har_entry(
    req_input: HarCaptureInput,
    resp: httpx.Response | None,
    elapsed_ms: float,
    error: str | None,
) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    req_headers = [{"name": k, "value": v} for k, v in req_input.headers.items()]
    req_post_data: dict[str, Any] | None = None
    if req_input.body:
        req_post_data = {
            "mimeType": req_input.headers.get("content-type", "text/plain"),
            "text": req_input.body,
        }

    resp_headers: list[dict] = []
    resp_body_text = ""
    resp_body_size = 0
    status = 0
    status_text = ""

    if resp is not None:
        resp_headers = [{"name": k, "value": v} for k, v in resp.headers.items()]
        try:
            resp_body_text = resp.text
        except Exception:
            resp_body_text = base64.b64encode(resp.content).decode("ascii")
        resp_body_size = len(resp.content)
        status = resp.status_code
        status_text = f"HTTP/{resp.http_version} {resp.status_code}"

    entry: dict[str, Any] = {
        "startedDateTime": started,
        "time": round(elapsed_ms, 2),
        "request": {
            "method": req_input.method,
            "url": req_input.url,
            "httpVersion": "HTTP/1.1",
            "headers": req_headers,
            "queryString": [],
            "cookies": [],
            "headersSize": -1,
            "bodySize": len(req_input.body.encode("utf-8")) if req_input.body else -1,
        },
        "response": {
            "status": status,
            "statusText": status_text,
            "httpVersion": "HTTP/1.1",
            "headers": resp_headers,
            "cookies": [],
            "content": {
                "size": resp_body_size,
                "mimeType": (resp.headers.get("content-type", "text/plain") if resp else "text/plain"),
                "text": resp_body_text,
            },
            "redirectURL": "",
            "headersSize": -1,
            "bodySize": resp_body_size,
        },
        "cache": {},
        "timings": {
            "send": 0,
            "wait": round(elapsed_ms, 2),
            "receive": 0,
        },
        "_error": error,
    }

    if req_post_data:
        entry["request"]["postData"] = req_post_data

    return entry
