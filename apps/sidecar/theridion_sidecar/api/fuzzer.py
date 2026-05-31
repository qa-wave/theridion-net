"""HTTP Fuzzer — payload positions + Sniper / Pitchfork / Cluster-Bomb attack modes.

Attack modes (Burp-Suite naming):
- **Sniper**        — one payload list; iterates it across each marked position in turn
                      (position 1 gets all payloads, then position 2, …).  One slot
                      changes per request, all others keep the original value.
- **Pitchfork**     — N payload lists (one per position); walks them in lock-step.
                      Request count = min(len(list_i)) across all positions.
- **Cluster-Bomb**  — N payload lists; takes the Cartesian product.  Use with care —
                      |P1| × |P2| × … requests will be sent.

Payload positions are marked with ``§placeholder§`` in URL, headers, or body.
Up to 10 positions and 1 000 payloads per list are enforced to prevent misuse.

Results are stored in an in-process registry (capped at 20 000 result rows) and
can be listed, filtered, and flagged as interesting via the REST endpoints.  An SSE
stream broadcasts live progress so the frontend chart updates in real-time.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from itertools import product
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

router = APIRouter(prefix="/api/fuzzer", tags=["fuzzer"])

# ---------------------------------------------------------------------------
# Constants & in-process store
# ---------------------------------------------------------------------------

_MAX_POSITIONS = 10
_MAX_PAYLOADS = 1_000
_MAX_RESULTS = 20_000

AttackMode = Literal["sniper", "pitchfork", "cluster_bomb"]

# run_id → FuzzerRunMeta
_runs: dict[str, "FuzzerRunMeta"] = {}
# run_id → list[FuzzResult]
_results: dict[str, list["FuzzResult"]] = {}
# run_id → asyncio.Event  (set when the run should stop)
_stop_signals: dict[str, asyncio.Event] = {}
# SSE subscribers: list of asyncio.Queue
_subscribers: list[asyncio.Queue[dict[str, Any] | None]] = []


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PayloadPosition(BaseModel):
    """A named ``§marker§`` position and the payloads to insert there."""

    name: str
    payloads: list[str] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _clamp(self) -> "PayloadPosition":
        if len(self.payloads) > _MAX_PAYLOADS:
            raise ValueError(f"max {_MAX_PAYLOADS} payloads per position")
        return self


class FuzzerConfig(BaseModel):
    url: str = Field(..., min_length=1)
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    attack_mode: AttackMode = "sniper"
    positions: list[PayloadPosition] = Field(..., min_length=1)
    timeout_ms: int = Field(default=10_000, ge=100, le=60_000)
    concurrency: int = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def _validate(self) -> "FuzzerConfig":
        if len(self.positions) > _MAX_POSITIONS:
            raise ValueError(f"max {_MAX_POSITIONS} payload positions")
        if self.attack_mode == "sniper" and len(self.positions) != 1:
            # Sniper uses a single payload list; markers can be multiple.
            pass  # allowed — single list, multiple marker occurrences
        if self.attack_mode in ("pitchfork", "cluster_bomb") and len(self.positions) < 1:
            raise ValueError("pitchfork/cluster_bomb need at least one position")
        return self


class FuzzerRunMeta(BaseModel):
    run_id: str
    config: FuzzerConfig
    status: Literal["running", "done", "stopped", "error"] = "running"
    total_requests: int = 0
    completed: int = 0
    started_at: float = Field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None


class FuzzResult(BaseModel):
    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    seq: int
    # The values that were inserted at each position
    payloads: dict[str, str]
    # Rendered request (after substitution)
    url: str
    method: str
    request_body: str | None
    # Response
    status_code: int | None
    response_body: str | None
    response_length: int
    elapsed_ms: float
    error: str | None
    # User flag
    flagged: bool = False


class FuzzerStartOutput(BaseModel):
    run_id: str
    total_requests: int
    attack_mode: AttackMode


class FuzzerRunStatus(BaseModel):
    run_id: str
    status: str
    total_requests: int
    completed: int
    started_at: float
    finished_at: float | None
    error: str | None


class FlagInput(BaseModel):
    flagged: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MARKER_RE = re.compile(r"§([^§]+)§")


def _substitute(template: str, values: dict[str, str]) -> str:
    """Replace ``§name§`` markers with values from *values* dict."""
    def _repl(m: re.Match) -> str:  # type: ignore[type-arg]
        return values.get(m.group(1), m.group(0))
    return _MARKER_RE.sub(_repl, template)


def _build_requests(cfg: FuzzerConfig) -> list[dict[str, str]]:
    """Return a list of dicts mapping position-name → payload for each request."""
    if cfg.attack_mode == "sniper":
        # Single payload list; find ALL marker names in the template.
        markers = _MARKER_RE.findall(cfg.url or "")
        if cfg.body:
            markers += _MARKER_RE.findall(cfg.body)
        for v in cfg.headers.values():
            markers += _MARKER_RE.findall(v)
        # De-duplicate while preserving order
        seen: set[str] = set()
        ordered_markers: list[str] = []
        for m in markers:
            if m not in seen:
                seen.add(m)
                ordered_markers.append(m)
        payloads = cfg.positions[0].payloads
        requests: list[dict[str, str]] = []
        for marker in ordered_markers:
            for payload in payloads:
                # All other markers keep their literal §marker§ string
                row = {m: f"§{m}§" for m in ordered_markers}
                row[marker] = payload
                requests.append(row)
        return requests

    if cfg.attack_mode == "pitchfork":
        n = min(len(p.payloads) for p in cfg.positions)
        requests = []
        for i in range(n):
            row = {p.name: p.payloads[i] for p in cfg.positions}
            requests.append(row)
        return requests

    # cluster_bomb — Cartesian product
    names = [p.name for p in cfg.positions]
    lists = [p.payloads for p in cfg.positions]
    requests = []
    for combo in product(*lists):
        row = dict(zip(names, combo))
        requests.append(row)
    return requests


async def _execute_one(
    client: httpx.AsyncClient,
    cfg: FuzzerConfig,
    seq: int,
    run_id: str,
    payload_map: dict[str, str],
) -> FuzzResult:
    url = _substitute(cfg.url, payload_map)
    body = _substitute(cfg.body, payload_map) if cfg.body else None
    headers = {k: _substitute(v, payload_map) for k, v in cfg.headers.items()}
    content = body.encode("utf-8") if body else None
    t0 = time.perf_counter()
    status_code: int | None = None
    resp_body: str | None = None
    error: str | None = None
    try:
        resp = await client.request(
            method=cfg.method,
            url=url,
            headers=headers,
            content=content,
            timeout=cfg.timeout_ms / 1000.0,
        )
        status_code = resp.status_code
        try:
            resp_body = resp.text
        except Exception:
            resp_body = resp.content.decode("utf-8", errors="replace")
    except Exception as exc:
        error = str(exc)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    resp_len = len(resp_body.encode("utf-8")) if resp_body else 0
    return FuzzResult(
        run_id=run_id,
        seq=seq,
        payloads=payload_map,
        url=url,
        method=cfg.method,
        request_body=body,
        status_code=status_code,
        response_body=resp_body,
        response_length=resp_len,
        elapsed_ms=round(elapsed_ms, 2),
        error=error,
    )


def _broadcast(event_type: str, data: Any) -> None:
    dead: list[asyncio.Queue[dict[str, Any] | None]] = []
    for q in _subscribers:
        try:
            q.put_nowait({"event": event_type, "data": data})
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


async def _run_fuzzer(run_id: str, cfg: FuzzerConfig, request_maps: list[dict[str, str]]) -> None:
    meta = _runs[run_id]
    result_list = _results[run_id]
    stop_evt = _stop_signals[run_id]

    sem = asyncio.Semaphore(cfg.concurrency)
    seq_counter = 0

    async def _bounded(pm: dict[str, str], seq: int) -> None:
        async with sem:
            if stop_evt.is_set():
                return
            async with httpx.AsyncClient(
                timeout=cfg.timeout_ms / 1000.0,
                follow_redirects=True,
                verify=False,  # noqa: S501
            ) as client:
                result = await _execute_one(client, cfg, seq, run_id, pm)
            result_list.append(result)
            # Cap results
            if len(result_list) > _MAX_RESULTS:
                result_list.pop(0)
            meta.completed += 1
            _broadcast("fuzz:result", {
                "run_id": run_id,
                "seq": seq,
                "status_code": result.status_code,
                "response_length": result.response_length,
                "elapsed_ms": result.elapsed_ms,
                "error": result.error,
                "payloads": result.payloads,
            })
            _broadcast("fuzz:progress", {
                "run_id": run_id,
                "completed": meta.completed,
                "total": meta.total_requests,
            })

    tasks = []
    for pm in request_maps:
        tasks.append(asyncio.create_task(_bounded(pm, seq_counter)))
        seq_counter += 1

    try:
        await asyncio.gather(*tasks)
        if stop_evt.is_set():
            meta.status = "stopped"
        else:
            meta.status = "done"
    except Exception as exc:
        meta.status = "error"
        meta.error = str(exc)
    finally:
        meta.finished_at = time.time()
        _broadcast("fuzz:done", {"run_id": run_id, "status": meta.status})
        _stop_signals.pop(run_id, None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/start", response_model=FuzzerStartOutput)
async def start_fuzz(cfg: FuzzerConfig) -> FuzzerStartOutput:
    """Start a fuzzer run.  Returns run_id immediately; results stream via SSE."""
    request_maps = _build_requests(cfg)
    if not request_maps:
        raise HTTPException(status_code=400, detail="no requests generated for the given config")

    run_id = str(uuid.uuid4())
    meta = FuzzerRunMeta(run_id=run_id, config=cfg, total_requests=len(request_maps))
    _runs[run_id] = meta
    _results[run_id] = []
    _stop_signals[run_id] = asyncio.Event()

    asyncio.create_task(_run_fuzzer(run_id, cfg, request_maps))

    return FuzzerStartOutput(
        run_id=run_id,
        total_requests=len(request_maps),
        attack_mode=cfg.attack_mode,
    )


@router.post("/stop/{run_id}", response_model=FuzzerRunStatus)
def stop_fuzz(run_id: str) -> FuzzerRunStatus:
    """Request a running fuzz to stop."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="run not found")
    evt = _stop_signals.get(run_id)
    if evt:
        evt.set()
    meta = _runs[run_id]
    return FuzzerRunStatus(
        run_id=run_id,
        status=meta.status,
        total_requests=meta.total_requests,
        completed=meta.completed,
        started_at=meta.started_at,
        finished_at=meta.finished_at,
        error=meta.error,
    )


@router.get("/runs/{run_id}", response_model=FuzzerRunStatus)
def get_run(run_id: str) -> FuzzerRunStatus:
    meta = _runs.get(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="run not found")
    return FuzzerRunStatus(
        run_id=run_id,
        status=meta.status,
        total_requests=meta.total_requests,
        completed=meta.completed,
        started_at=meta.started_at,
        finished_at=meta.finished_at,
        error=meta.error,
    )


@router.get("/runs/{run_id}/results", response_model=list[FuzzResult])
def get_results(
    run_id: str,
    limit: int = 200,
    offset: int = 0,
    flagged_only: bool = False,
    status_code: int | None = None,
) -> list[FuzzResult]:
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="run not found")
    results = _results[run_id]
    if flagged_only:
        results = [r for r in results if r.flagged]
    if status_code is not None:
        results = [r for r in results if r.status_code == status_code]
    return results[offset: offset + limit]


@router.patch("/runs/{run_id}/results/{result_id}/flag", response_model=FuzzResult)
def flag_result(run_id: str, result_id: str, body: FlagInput) -> FuzzResult:
    """Toggle the 'flagged' state of a result (mark as interesting)."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="run not found")
    for r in _results[run_id]:
        if r.result_id == result_id:
            r.flagged = body.flagged
            return r
    raise HTTPException(status_code=404, detail="result not found")


@router.delete("/runs/{run_id}", response_model=dict)
def delete_run(run_id: str) -> dict:
    """Delete run metadata and all results."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="run not found")
    # Stop first
    evt = _stop_signals.pop(run_id, None)
    if evt:
        evt.set()
    del _runs[run_id]
    _results.pop(run_id, None)
    return {"deleted": run_id}


@router.get("/stream")
async def stream_events() -> StreamingResponse:
    """SSE stream for live fuzz progress.

    Events: ``fuzz:result``, ``fuzz:progress``, ``fuzz:done``, ``ping``
    """
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=500)
    _subscribers.append(queue)

    async def _gen():
        try:
            # Send active runs snapshot on connect
            snapshot = [
                {
                    "run_id": m.run_id,
                    "status": m.status,
                    "completed": m.completed,
                    "total": m.total_requests,
                }
                for m in _runs.values()
                if m.status == "running"
            ]
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

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
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _ping_loop(queue: asyncio.Queue[dict[str, Any] | None]) -> None:
    while True:
        await asyncio.sleep(15)
        try:
            queue.put_nowait({"event": "ping", "data": {}})
        except asyncio.QueueFull:
            pass
