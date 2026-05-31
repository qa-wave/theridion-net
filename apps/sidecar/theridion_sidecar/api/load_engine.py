"""Real load engine — multi-worker asyncio pool with live SSE progress and ramp/stages.

Replaces the naive in-process loop with a proper staged architecture:

* **Stages** — each stage specifies target VUs, duration and ramp-up.  Stages
  are executed in order; VUs are ramped between stages smoothly.
* **Live SSE progress** — per-second progress events with RPS, latency and
  error-rate are broadcast during the run.
* **Proper percentile tracking** — reservoir-sampled latency for p50/p95/p99
  without unbounded memory growth.
* **Graceful stop** — POST /stop/{run_id} sets a stop-signal; workers drain
  within one tick (≤ 1 s).

The engine is a pure asyncio multi-worker pool (no threads, no Locust daemon),
which keeps the deployment model simple (single PyInstaller binary) while being
far more capable than the legacy single-loop approach.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import statistics
import time
import uuid
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/load-engine", tags=["load-engine"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RUNS = 20  # keep last 20 run records
_RESERVOIR_SIZE = 5_000  # reservoir for latency sampling
_MAX_TIMELINE = 3_600  # max timeline points (1 h at 1/s)

# ---------------------------------------------------------------------------
# In-process state
# ---------------------------------------------------------------------------

# run_id → LoadRunState
_runs: dict[str, "LoadRunState"] = {}
# SSE subscribers
_subscribers: list[asyncio.Queue[dict[str, Any] | None]] = []


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LoadStage(BaseModel):
    """A single load stage.

    *target_vus*  — target virtual users at the end of the stage.
    *duration_s*  — how long this stage lasts.
    *ramp_up_s*   — seconds to ramp from current VU count to target_vus.
                    Set to 0 for an instant step.
    """

    target_vus: int = Field(..., ge=1, le=1000)
    duration_s: int = Field(..., ge=1, le=3600)
    ramp_up_s: int = Field(default=0, ge=0)


class LoadEngineConfig(BaseModel):
    url: str = Field(..., min_length=1)
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    stages: list[LoadStage] = Field(..., min_length=1)
    think_time_ms: int = Field(default=0, ge=0)
    timeout_ms: int = Field(default=30_000, ge=100, le=120_000)


class TimelinePoint(BaseModel):
    second: int
    rps: float
    active_vus: int
    avg_latency_ms: float
    p95_ms: float
    error_rate: float  # 0.0 – 1.0


class LoadEngineResult(BaseModel):
    run_id: str
    status: Literal["running", "done", "stopped", "error"]
    total_requests: int
    successful: int
    failed: int
    errors: dict[str, int]
    avg_latency_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    requests_per_second: float
    duration_s: float
    timeline: list[TimelinePoint]
    error: str | None = None


class LoadEngineStartOutput(BaseModel):
    run_id: str
    total_stages: int
    total_duration_s: int


# ---------------------------------------------------------------------------
# Internal run state
# ---------------------------------------------------------------------------


class _Bucket:
    """Per-second aggregation bucket."""

    __slots__ = ("rps", "active_vus", "latencies", "errors")

    def __init__(self) -> None:
        self.rps: int = 0
        self.active_vus: int = 0
        self.latencies: list[float] = []
        self.errors: int = 0


class LoadRunState:
    def __init__(self, run_id: str, cfg: LoadEngineConfig) -> None:
        self.run_id = run_id
        self.cfg = cfg
        self.status: Literal["running", "done", "stopped", "error"] = "running"
        self.total_requests = 0
        self.successful = 0
        self.failed = 0
        self.errors: dict[str, int] = {}
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.error: str | None = None
        # Reservoir for percentile computation
        self._reservoir: list[float] = []
        self._reservoir_count = 0
        # Timeline
        self.timeline: list[_Bucket] = []
        # Control
        self.stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        # Current active VU count (managed by the runner)
        self.active_vus = 0

    def record_sample(self, latency_ms: float, error: str | None, second: int) -> None:
        """Thread-safe (asyncio-safe) sample recording."""
        if error:
            self.failed += 1
            self.errors[error] = self.errors.get(error, 0) + 1
        else:
            self.successful += 1
        self.total_requests += 1

        # Reservoir sampling for latency
        self._reservoir_count += 1
        if len(self._reservoir) < _RESERVOIR_SIZE:
            self._reservoir.append(latency_ms)
        else:
            j = random.randint(0, self._reservoir_count - 1)
            if j < _RESERVOIR_SIZE:
                self._reservoir[j] = latency_ms

        # Timeline bucket
        while len(self.timeline) <= second:
            self.timeline.append(_Bucket())
        b = self.timeline[second]
        b.rps += 1
        b.latencies.append(latency_ms)
        if error:
            b.errors += 1
        b.active_vus = self.active_vus

    def percentile(self, p: float) -> float:
        if not self._reservoir:
            return 0.0
        s = sorted(self._reservoir)
        k = (len(s) - 1) * (p / 100.0)
        f = int(k)
        c = f + 1
        if c >= len(s):
            return s[f]
        return s[f] + (k - f) * (s[c] - s[f])

    def to_result(self) -> LoadEngineResult:
        dur = (self.finished_at or time.time()) - self.started_at
        rps = self.total_requests / dur if dur > 0 else 0.0
        avg = statistics.mean(self._reservoir) if self._reservoir else 0.0

        timeline: list[TimelinePoint] = []
        for i, b in enumerate(self.timeline[:_MAX_TIMELINE]):
            avg_lat = statistics.mean(b.latencies) if b.latencies else 0.0
            p95 = _percentile_sorted(sorted(b.latencies), 95) if b.latencies else 0.0
            err_rate = b.errors / b.rps if b.rps else 0.0
            timeline.append(TimelinePoint(
                second=i,
                rps=b.rps,
                active_vus=b.active_vus,
                avg_latency_ms=round(avg_lat, 2),
                p95_ms=round(p95, 2),
                error_rate=round(err_rate, 4),
            ))

        return LoadEngineResult(
            run_id=self.run_id,
            status=self.status,
            total_requests=self.total_requests,
            successful=self.successful,
            failed=self.failed,
            errors=self.errors,
            avg_latency_ms=round(avg, 2),
            p50_ms=round(self.percentile(50), 2),
            p95_ms=round(self.percentile(95), 2),
            p99_ms=round(self.percentile(99), 2),
            requests_per_second=round(rps, 2),
            duration_s=round(dur, 2),
            timeline=timeline,
            error=self.error,
        )


def _percentile_sorted(s: list[float], p: float) -> float:
    if not s:
        return 0.0
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(s):
        return s[f]
    return s[f] + (k - f) * (s[c] - s[f])


# ---------------------------------------------------------------------------
# Engine loop
# ---------------------------------------------------------------------------


async def _vu_loop(
    vu_id: int,
    state: LoadRunState,
    start_mono: float,
) -> None:
    """Single virtual user — fires requests until stop_event is set."""
    cfg = state.cfg
    content = cfg.body.encode("utf-8") if cfg.body else None
    timeout = cfg.timeout_ms / 1000.0

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        verify=False,  # noqa: S501
    ) as client:
        while not state.stop_event.is_set():
            second = int(time.monotonic() - start_mono)
            t0 = time.perf_counter()
            error: str | None = None
            try:
                await client.request(
                    method=cfg.method,
                    url=cfg.url,
                    headers=cfg.headers,
                    content=content,
                )
            except httpx.RequestError as exc:
                error = type(exc).__name__
            except Exception as exc:
                error = type(exc).__name__
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            state.record_sample(elapsed_ms, error, second)

            if cfg.think_time_ms > 0:
                await asyncio.sleep(cfg.think_time_ms / 1000.0)


async def _broadcast_progress(state: LoadRunState, start_mono: float) -> None:
    """Send progress SSE every second while the run is active."""
    last_total = 0
    while not state.stop_event.is_set():
        await asyncio.sleep(1.0)
        second = int(time.monotonic() - start_mono)
        delta = state.total_requests - last_total
        last_total = state.total_requests
        msg = {
            "run_id": state.run_id,
            "second": second,
            "rps": delta,
            "active_vus": state.active_vus,
            "total_requests": state.total_requests,
            "failed": state.failed,
        }
        _broadcast("load:progress", msg)


async def _run_stages(state: LoadRunState) -> None:
    """Orchestrate stages: ramp VUs, run for duration, then transition."""
    cfg = state.cfg
    start_mono = time.monotonic()
    current_vus = 0
    active_tasks: list[asyncio.Task] = []  # type: ignore[type-arg]

    progress_task = asyncio.create_task(_broadcast_progress(state, start_mono))

    try:
        for stage in cfg.stages:
            if state.stop_event.is_set():
                break

            target = stage.target_vus
            ramp_s = stage.ramp_up_s
            run_s = stage.duration_s

            # --- Ramp phase ---
            if ramp_s > 0 and target != current_vus:
                # We'll add/remove VUs linearly over ramp_s seconds.
                delta = target - current_vus
                ticks = max(1, ramp_s)
                per_tick = delta / ticks
                acc = 0.0
                for tick in range(ticks):
                    if state.stop_event.is_set():
                        break
                    acc += per_tick
                    new_count = round(current_vus + acc)
                    # Add VUs
                    while len(active_tasks) < new_count:
                        t = asyncio.create_task(_vu_loop(len(active_tasks), state, start_mono))
                        active_tasks.append(t)
                    # Remove VUs by cancelling excess
                    while len(active_tasks) > new_count and active_tasks:
                        old = active_tasks.pop()
                        old.cancel()
                    state.active_vus = len(active_tasks)
                    await asyncio.sleep(1.0)
                current_vus = target
            else:
                # Instant step
                while len(active_tasks) < target:
                    t = asyncio.create_task(_vu_loop(len(active_tasks), state, start_mono))
                    active_tasks.append(t)
                while len(active_tasks) > target and active_tasks:
                    old = active_tasks.pop()
                    old.cancel()
                current_vus = target
                state.active_vus = len(active_tasks)

            # --- Run phase ---
            stage_deadline = time.monotonic() + run_s
            while time.monotonic() < stage_deadline:
                if state.stop_event.is_set():
                    break
                await asyncio.sleep(0.5)

        # Stop all VUs
        state.stop_event.set()
        for t in active_tasks:
            t.cancel()
        await asyncio.gather(*active_tasks, return_exceptions=True)

        if state.status == "running":
            state.status = "done"
    except Exception as exc:
        state.status = "error"
        state.error = str(exc)
        state.stop_event.set()
        for t in active_tasks:
            t.cancel()
        await asyncio.gather(*active_tasks, return_exceptions=True)
    finally:
        state.active_vus = 0
        state.finished_at = time.time()
        progress_task.cancel()
        _broadcast("load:done", {
            "run_id": state.run_id,
            "status": state.status,
            "total_requests": state.total_requests,
        })


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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/start", response_model=LoadEngineStartOutput)
async def start_run(cfg: LoadEngineConfig) -> LoadEngineStartOutput:
    """Start a staged load run.  Returns immediately; poll /runs/{run_id} or subscribe to SSE."""
    run_id = str(uuid.uuid4())
    state = LoadRunState(run_id, cfg)
    _runs[run_id] = state

    # Evict oldest if over cap
    if len(_runs) > _MAX_RUNS:
        oldest = next(iter(_runs))
        _runs[oldest].stop_event.set()
        del _runs[oldest]

    asyncio.create_task(_run_stages(state))

    total_dur = sum(s.duration_s + s.ramp_up_s for s in cfg.stages)
    return LoadEngineStartOutput(
        run_id=run_id,
        total_stages=len(cfg.stages),
        total_duration_s=total_dur,
    )


@router.post("/stop/{run_id}", response_model=LoadEngineResult)
def stop_run(run_id: str) -> LoadEngineResult:
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="run not found")
    state.status = "stopped"
    state.stop_event.set()
    return state.to_result()


@router.get("/runs/{run_id}", response_model=LoadEngineResult)
def get_run(run_id: str) -> LoadEngineResult:
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="run not found")
    return state.to_result()


@router.get("/runs", response_model=list[dict])
def list_runs() -> list[dict]:
    return [
        {
            "run_id": s.run_id,
            "status": s.status,
            "total_requests": s.total_requests,
            "started_at": s.started_at,
            "finished_at": s.finished_at,
        }
        for s in reversed(list(_runs.values()))
    ]


@router.get("/stream")
async def stream_events() -> StreamingResponse:
    """SSE stream for live load progress.

    Events: ``load:progress`` (every second), ``load:done``, ``ping``
    """
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=300)
    _subscribers.append(queue)

    async def _gen():
        try:
            # Snapshot of all active runs
            active = [
                {"run_id": s.run_id, "status": s.status, "total_requests": s.total_requests}
                for s in _runs.values()
                if s.status == "running"
            ]
            yield f"event: snapshot\ndata: {json.dumps(active)}\n\n"

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
