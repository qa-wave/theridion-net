"""HTTP intercepting proxy with request/response capture, breakpoints, and SSE streaming.

Acts as a CONNECT/HTTP proxy on a local port.  Captured flows are broadcast
over SSE so the frontend can render them in real-time.  Supports:

- Passive interception (record-only)
- Active breakpoints (forward is gated until the UI releases the flow)
- Edit-and-forward (replace body / headers before forwarding)
- Send-to-request (hand a captured flow back to the main request panel)
- Passive scanner: automatic flag injection via the existing sensitive_data,
  cors, and injection detectors
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from theridion_sidecar.api.sensitive_data import _scan_text

router = APIRouter(prefix="/api/interceptor", tags=["interceptor"])

# ---------------------------------------------------------------------------
# In-process state (singleton per sidecar run)
# ---------------------------------------------------------------------------

# Captured flows, keyed by flow_id — newest first.
_flows: dict[str, "CapturedFlow"] = {}
_MAX_FLOWS = 500  # cap to avoid unbounded memory growth

# SSE subscribers — each is an asyncio.Queue that receives ServerSentEvent dicts.
_subscribers: list[asyncio.Queue[dict[str, Any] | None]] = []

# Breakpoints: set of flow_ids currently paused waiting for release.
_breakpoints: dict[str, asyncio.Event] = {}
_breakpoint_edits: dict[str, "EditForwardInput"] = {}

# Global intercept settings
_intercept_enabled = False
_break_on_all = False
_passive_scan_enabled = True


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CapturedFlow(BaseModel):
    flow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=time.time)
    # Request
    method: str
    url: str
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: str | None = None
    # Response (filled after forward)
    status_code: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: str | None = None
    elapsed_ms: float | None = None
    # State
    state: Literal["pending", "paused", "forwarded", "error"] = "pending"
    # Passive scanner flags
    flags: list["ScanFlag"] = Field(default_factory=list)
    error: str | None = None


class ScanFlag(BaseModel):
    type: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    location: str
    detail: str


class InterceptConfig(BaseModel):
    enabled: bool = False
    break_on_all: bool = False
    passive_scan: bool = True


class InterceptStatus(BaseModel):
    enabled: bool
    break_on_all: bool
    passive_scan: bool
    flow_count: int
    paused_count: int


class ForwardRequest(BaseModel):
    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None


class ForwardResult(BaseModel):
    flow_id: str
    status_code: int
    response_headers: dict[str, str]
    response_body: str
    elapsed_ms: float
    flags: list[ScanFlag]


class EditForwardInput(BaseModel):
    flow_id: str
    method: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    body: str | None = None


class FlowListOutput(BaseModel):
    flows: list[CapturedFlow]
    total: int


class ClearOutput(BaseModel):
    cleared: int


class SendToRequestOutput(BaseModel):
    method: str
    url: str
    headers: dict[str, str]
    body: str | None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _broadcast(event_type: str, data: Any) -> None:
    """Push an SSE event to all active subscribers."""
    msg = {"event": event_type, "data": data}
    dead: list[asyncio.Queue[dict[str, Any] | None]] = []
    for q in _subscribers:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def _passive_scan(flow: CapturedFlow) -> list[ScanFlag]:
    """Run passive scanner checks on a completed flow."""
    flags: list[ScanFlag] = []

    # 1. Sensitive data in response body
    if flow.response_body:
        findings = _scan_text(flow.response_body, "response_body")
        for f in findings:
            flags.append(ScanFlag(
                type=f"sensitive:{f.type}",
                severity="high",
                location=f.location,
                detail=f"Sensitive data ({f.type}) found at line {f.line}: {f.value_preview}",
            ))

    # 2. Sensitive data in request body
    if flow.request_body:
        req_findings = _scan_text(flow.request_body, "request_body")
        for f in req_findings:
            flags.append(ScanFlag(
                type=f"sensitive:{f.type}",
                severity="medium",
                location="request_body",
                detail=f"Sensitive data ({f.type}) in request at line {f.line}: {f.value_preview}",
            ))

    # 3. Missing security headers
    resp_hdrs = {k.lower(): v for k, v in flow.response_headers.items()}
    if not resp_hdrs.get("content-security-policy"):
        flags.append(ScanFlag(
            type="missing_header",
            severity="medium",
            location="response_headers",
            detail="Missing Content-Security-Policy header",
        ))
    if not resp_hdrs.get("x-content-type-options"):
        flags.append(ScanFlag(
            type="missing_header",
            severity="low",
            location="response_headers",
            detail="Missing X-Content-Type-Options header",
        ))
    if not resp_hdrs.get("x-frame-options") and not resp_hdrs.get("content-security-policy"):
        flags.append(ScanFlag(
            type="missing_header",
            severity="low",
            location="response_headers",
            detail="Missing X-Frame-Options header",
        ))

    # 4. Wildcard CORS
    acao = resp_hdrs.get("access-control-allow-origin", "")
    if acao == "*":
        flags.append(ScanFlag(
            type="cors_wildcard",
            severity="medium",
            location="response_headers",
            detail="Wildcard Access-Control-Allow-Origin: any origin can make requests",
        ))

    # 5. HTTP over plain text for sensitive paths
    url_lower = (flow.url or "").lower()
    if url_lower.startswith("http://") and any(
        kw in url_lower for kw in ["/login", "/auth", "/token", "/password", "/signin"]
    ):
        flags.append(ScanFlag(
            type="plaintext_credentials",
            severity="high",
            location="url",
            detail="Sensitive endpoint served over HTTP (not HTTPS)",
        ))

    # 6. SQL injection reflected payload
    if flow.request_body and flow.response_body:
        sql_markers = ["' or '1'='1", "1; drop", "union select"]
        resp_lower = flow.response_body.lower()
        for marker in sql_markers:
            if marker in flow.request_body.lower() and marker in resp_lower:
                flags.append(ScanFlag(
                    type="sqli_reflected",
                    severity="critical",
                    location="response_body",
                    detail=f"SQL injection payload reflected in response: {marker!r}",
                ))

    return flags


async def _do_forward(
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, str], str, float]:
    """Execute the HTTP request and return (status, resp_headers, body, elapsed_ms)."""
    content = body.encode("utf-8") if body else None
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:  # noqa: S501
        resp = await client.request(
            method=method,
            url=url,
            headers=headers,
            content=content,
        )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    resp_headers = dict(resp.headers)
    try:
        resp_body = resp.text
    except Exception:
        resp_body = resp.content.decode("utf-8", errors="replace")
    return resp.status_code, resp_headers, resp_body, elapsed_ms


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/status", response_model=InterceptStatus)
def get_status() -> InterceptStatus:
    """Return current interceptor configuration and flow counts."""
    return InterceptStatus(
        enabled=_intercept_enabled,
        break_on_all=_break_on_all,
        passive_scan=_passive_scan_enabled,
        flow_count=len(_flows),
        paused_count=sum(1 for f in _flows.values() if f.state == "paused"),
    )


@router.post("/config", response_model=InterceptStatus)
def configure(cfg: InterceptConfig) -> InterceptStatus:
    """Update interceptor settings."""
    global _intercept_enabled, _break_on_all, _passive_scan_enabled
    _intercept_enabled = cfg.enabled
    _break_on_all = cfg.break_on_all
    _passive_scan_enabled = cfg.passive_scan
    _broadcast("config", cfg.model_dump())
    return get_status()


@router.post("/forward", response_model=ForwardResult)
async def forward(req: ForwardRequest) -> ForwardResult:
    """Capture and forward a request.  If break-on-all is active, pause before forwarding.

    This is the main entry point when the UI wants to send a request through
    the interceptor pipeline (e.g. via right-click → "Run as Intercepted").
    """
    flow = CapturedFlow(
        method=req.method,
        url=req.url,
        request_headers=req.headers,
        request_body=req.body,
        state="pending",
    )
    _flows[flow.flow_id] = flow
    # Trim oldest flows if over cap
    if len(_flows) > _MAX_FLOWS:
        oldest_key = next(iter(_flows))
        del _flows[oldest_key]

    _broadcast("flow:captured", flow.model_dump())

    if _break_on_all and _intercept_enabled:
        flow.state = "paused"
        _broadcast("flow:paused", {"flow_id": flow.flow_id})
        evt = asyncio.Event()
        _breakpoints[flow.flow_id] = evt
        # Wait up to 5 minutes for the user to release
        try:
            await asyncio.wait_for(evt.wait(), timeout=300)
        except asyncio.TimeoutError:
            flow.state = "error"
            flow.error = "Breakpoint timed out (5 min)"
            del _breakpoints[flow.flow_id]
            _broadcast("flow:error", {"flow_id": flow.flow_id, "error": flow.error})
            raise HTTPException(status_code=408, detail=flow.error)

        # Check if user supplied edits
        edit = _breakpoint_edits.pop(flow.flow_id, None)
        if edit:
            if edit.method:
                flow.method = req.method = edit.method
            if edit.url:
                flow.url = req.url = edit.url
            if edit.headers is not None:
                flow.request_headers = req.headers = edit.headers
            if edit.body is not None:
                flow.request_body = req.body = edit.body
        del _breakpoints[flow.flow_id]

    # Forward the request
    try:
        status_code, resp_headers, resp_body, elapsed_ms = await _do_forward(
            flow.method, flow.url, flow.request_headers, flow.request_body,
        )
    except Exception as exc:
        flow.state = "error"
        flow.error = str(exc)
        _broadcast("flow:error", {"flow_id": flow.flow_id, "error": flow.error})
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    flow.status_code = status_code
    flow.response_headers = resp_headers
    flow.response_body = resp_body
    flow.elapsed_ms = elapsed_ms
    flow.state = "forwarded"

    if _passive_scan_enabled:
        flow.flags = _passive_scan(flow)

    _broadcast("flow:forwarded", flow.model_dump())

    return ForwardResult(
        flow_id=flow.flow_id,
        status_code=status_code,
        response_headers=resp_headers,
        response_body=resp_body,
        elapsed_ms=elapsed_ms,
        flags=flow.flags,
    )


@router.post("/release/{flow_id}", response_model=dict)
def release_breakpoint(flow_id: str, edit: EditForwardInput | None = None) -> dict[str, str]:
    """Release a paused breakpoint, optionally with edited request values."""
    evt = _breakpoints.get(flow_id)
    if not evt:
        raise HTTPException(status_code=404, detail="flow not found or not paused")
    if edit:
        _breakpoint_edits[flow_id] = edit
    evt.set()
    return {"status": "released", "flow_id": flow_id}


@router.get("/flows", response_model=FlowListOutput)
def list_flows(limit: int = 100, offset: int = 0) -> FlowListOutput:
    """Return captured flows (most recent first)."""
    all_flows = list(reversed(list(_flows.values())))
    total = len(all_flows)
    page = all_flows[offset : offset + limit]
    return FlowListOutput(flows=page, total=total)


@router.get("/flows/{flow_id}", response_model=CapturedFlow)
def get_flow(flow_id: str) -> CapturedFlow:
    """Return a single captured flow by ID."""
    flow = _flows.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="flow not found")
    return flow


@router.delete("/flows", response_model=ClearOutput)
def clear_flows() -> ClearOutput:
    """Clear all captured flows."""
    count = len(_flows)
    _flows.clear()
    _broadcast("flows:cleared", {"count": count})
    return ClearOutput(cleared=count)


@router.get("/flows/{flow_id}/send-to-request", response_model=SendToRequestOutput)
def send_to_request(flow_id: str) -> SendToRequestOutput:
    """Return the request portion of a flow so the UI can open it in the request panel."""
    flow = _flows.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="flow not found")
    return SendToRequestOutput(
        method=flow.method,
        url=flow.url,
        headers=flow.request_headers,
        body=flow.request_body,
    )


@router.get("/stream")
async def stream_events() -> StreamingResponse:
    """Server-Sent Events stream of interceptor events.

    Events:
    - ``flow:captured``    — a request was captured (before forward)
    - ``flow:paused``      — breakpoint hit; waiting for release
    - ``flow:forwarded``   — response received, flow complete
    - ``flow:error``       — forward failed
    - ``flows:cleared``    — all flows cleared
    - ``config``           — settings changed
    - ``ping``             — keepalive (every 15 s)
    """
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=200)
    _subscribers.append(queue)

    async def generator():
        try:
            # Send current state snapshot on connect
            snapshot = {
                "event": "snapshot",
                "data": {
                    "flows": [f.model_dump() for f in list(reversed(list(_flows.values())))[:50]],
                    "enabled": _intercept_enabled,
                    "break_on_all": _break_on_all,
                    "passive_scan": _passive_scan_enabled,
                },
            }
            yield f"event: snapshot\ndata: {json.dumps(snapshot['data'])}\n\n"

            ping_task = asyncio.create_task(_ping_loop(queue))
            try:
                while True:
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=30)
                    except asyncio.TimeoutError:
                        yield "event: ping\ndata: {}\n\n"
                        continue
                    if msg is None:
                        break
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
            finally:
                ping_task.cancel()
        finally:
            try:
                _subscribers.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _ping_loop(queue: asyncio.Queue[dict[str, Any] | None]) -> None:
    """Send a ping every 15 seconds to keep the SSE connection alive."""
    while True:
        await asyncio.sleep(15)
        try:
            queue.put_nowait({"event": "ping", "data": {}})
        except asyncio.QueueFull:
            pass
