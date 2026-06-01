"""Full load testing with virtual users, ramp-up, think time, and per-second timeline.

Uses pure asyncio + httpx (no extra dependencies like locust).  Returns
structured results with percentile breakdowns and a per-second timeline
suitable for charting on the frontend.

Results are persisted to ``$THERIDION_HOME/load_results.jsonl`` (newest first,
capped at 100 entries) so the LoadWorkspacePanel can show historical runs on
first load without requiring a live test.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from theridion_sidecar.storage import home_dir

router = APIRouter(prefix="/api/loadtest", tags=["loadtest"])

_MAX_SAVED_RESULTS = 100


# ----- Persistence ----------------------------------------------------------


def _load_results_path() -> Path:
    d = home_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "load_results.jsonl"


def _read_saved_results() -> list[dict[str, Any]]:
    p = _load_results_path()
    if not p.exists():
        return []
    results: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return results


def _write_saved_results(results: list[dict[str, Any]]) -> None:
    p = _load_results_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="load_results.", suffix=".tmp", dir=str(p.parent))
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, p)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _persist_result(result_dict: dict[str, Any]) -> None:
    """Prepend *result_dict* to the saved results file (newest first, capped)."""
    results = _read_saved_results()
    results.insert(0, result_dict)
    if len(results) > _MAX_SAVED_RESULTS:
        results = results[:_MAX_SAVED_RESULTS]
    _write_saved_results(results)


# ----- Models ---------------------------------------------------------------


class LoadRunConfig(BaseModel):
    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    virtual_users: int = Field(default=10, ge=1, le=500)
    duration_seconds: int = Field(default=30, ge=1, le=600)
    ramp_up_seconds: int = Field(default=5, ge=0)
    think_time_ms: int = Field(default=0, ge=0)
    environment_id: str | None = None


class TimelinePoint(BaseModel):
    second: int
    rps: float
    avg_latency_ms: float
    error_count: int
    active_users: int


class LoadRunResult(BaseModel):
    total_requests: int
    successful: int
    failed: int
    errors: dict[str, int]
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    p50_ms: float
    p75_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    requests_per_second: float
    duration_seconds: float
    timeline: list[TimelinePoint]


# ----- Internals ------------------------------------------------------------


def _percentile(sorted_data: list[float], p: float) -> float:
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    d = k - f
    return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])


class _Sample:
    __slots__ = ("second", "latency_ms", "error")

    def __init__(self, second: int, latency_ms: float, error: str | None) -> None:
        self.second = second
        self.latency_ms = latency_ms
        self.error = error


async def _virtual_user(
    user_id: int,
    client: httpx.AsyncClient,
    cfg: LoadRunConfig,
    start_mono: float,
    samples: list[_Sample],
    active_counts: dict[int, int],
) -> None:
    """One virtual user loop — fires requests until duration expires."""
    # Ramp-up: stagger the start of each user
    if cfg.ramp_up_seconds > 0 and cfg.virtual_users > 1:
        delay = cfg.ramp_up_seconds * (user_id / (cfg.virtual_users - 1))
        await asyncio.sleep(delay)

    deadline = start_mono + cfg.duration_seconds
    content = cfg.body.encode("utf-8") if cfg.body else None

    while time.monotonic() < deadline:
        second = int(time.monotonic() - start_mono)
        active_counts[second] = active_counts.get(second, 0) + 1

        req_start = time.perf_counter()
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
        latency = (time.perf_counter() - req_start) * 1000.0
        samples.append(_Sample(second=second, latency_ms=latency, error=error))

        if cfg.think_time_ms > 0:
            await asyncio.sleep(cfg.think_time_ms / 1000.0)


def _build_timeline(
    samples: list[_Sample],
    active_counts: dict[int, int],
    duration: int,
) -> list[TimelinePoint]:
    """Aggregate samples into per-second buckets."""
    buckets: dict[int, list[_Sample]] = {}
    for s in samples:
        buckets.setdefault(s.second, []).append(s)

    points: list[TimelinePoint] = []
    for sec in range(duration):
        bucket = buckets.get(sec, [])
        lats = [s.latency_ms for s in bucket]
        errors = sum(1 for s in bucket if s.error)
        points.append(
            TimelinePoint(
                second=sec,
                rps=len(bucket),
                avg_latency_ms=round(statistics.mean(lats), 2) if lats else 0.0,
                error_count=errors,
                active_users=active_counts.get(sec, 0),
            )
        )
    return points


# ----- Route ----------------------------------------------------------------


@router.post("/run-full", response_model=LoadRunResult)
async def run_full_loadtest(cfg: LoadRunConfig) -> LoadRunResult:
    """Execute a full load test with virtual users, ramp-up, and timeline."""
    samples: list[_Sample] = []
    active_counts: dict[int, int] = {}

    start_mono = time.monotonic()
    started = time.perf_counter()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        tasks = [
            asyncio.create_task(
                _virtual_user(i, client, cfg, start_mono, samples, active_counts)
            )
            for i in range(cfg.virtual_users)
        ]
        await asyncio.gather(*tasks)

    actual_duration = time.perf_counter() - started
    total = len(samples)

    if total == 0:
        return LoadRunResult(
            total_requests=0,
            successful=0,
            failed=0,
            errors={},
            avg_latency_ms=0.0,
            min_latency_ms=0.0,
            max_latency_ms=0.0,
            p50_ms=0.0,
            p75_ms=0.0,
            p90_ms=0.0,
            p95_ms=0.0,
            p99_ms=0.0,
            requests_per_second=0.0,
            duration_seconds=round(actual_duration, 2),
            timeline=[],
        )

    sorted_lat = sorted(s.latency_ms for s in samples)
    error_summary: dict[str, int] = {}
    failed = 0
    for s in samples:
        if s.error:
            failed += 1
            error_summary[s.error] = error_summary.get(s.error, 0) + 1

    timeline = _build_timeline(
        samples, active_counts, math.ceil(actual_duration)
    )

    return LoadRunResult(
        total_requests=total,
        successful=total - failed,
        failed=failed,
        errors=error_summary,
        avg_latency_ms=round(statistics.mean(sorted_lat), 2),
        min_latency_ms=round(sorted_lat[0], 2),
        max_latency_ms=round(sorted_lat[-1], 2),
        p50_ms=round(_percentile(sorted_lat, 50), 2),
        p75_ms=round(_percentile(sorted_lat, 75), 2),
        p90_ms=round(_percentile(sorted_lat, 90), 2),
        p95_ms=round(_percentile(sorted_lat, 95), 2),
        p99_ms=round(_percentile(sorted_lat, 99), 2),
        requests_per_second=round(total / actual_duration, 2) if actual_duration > 0 else 0.0,
        duration_seconds=round(actual_duration, 2),
        timeline=timeline,
    )

    # Persist result so the frontend can show it on next launch.
    saved_dict = result.model_dump(mode="json")
    saved_dict["id"] = str(uuid.uuid4())
    saved_dict["url"] = cfg.url
    saved_dict["method"] = cfg.method
    saved_dict["virtual_users"] = cfg.virtual_users
    saved_dict["ramp_up_seconds"] = cfg.ramp_up_seconds
    saved_dict["started_at"] = time.time() - actual_duration
    _persist_result(saved_dict)

    return result


# ----- Saved results endpoint -----------------------------------------------


class SavedLoadResult(BaseModel):
    """Summary view of a persisted load test result."""

    id: str
    url: str
    method: str
    virtual_users: int
    duration_seconds: float
    started_at: float
    total_requests: int
    successful: int
    failed: int
    avg_latency_ms: float
    p95_ms: float
    p99_ms: float
    requests_per_second: float
    errors: dict[str, int] = Field(default_factory=dict)


@router.get("/saved", response_model=list[SavedLoadResult])
def list_saved_results() -> list[SavedLoadResult]:
    """Return all persisted load test results (newest first)."""
    raw = _read_saved_results()
    out: list[SavedLoadResult] = []
    for r in raw:
        try:
            out.append(SavedLoadResult(
                id=r.get("id", str(uuid.uuid4())),
                url=r.get("url", ""),
                method=r.get("method", "GET"),
                virtual_users=r.get("virtual_users", 0),
                duration_seconds=float(r.get("duration_seconds", 0)),
                started_at=float(r.get("started_at", 0)),
                total_requests=int(r.get("total_requests", 0)),
                successful=int(r.get("successful", 0)),
                failed=int(r.get("failed", 0)),
                avg_latency_ms=float(r.get("avg_latency_ms", 0)),
                p95_ms=float(r.get("p95_ms", 0)),
                p99_ms=float(r.get("p99_ms", 0)),
                requests_per_second=float(r.get("requests_per_second", 0)),
                errors=r.get("errors", {}),
            ))
        except Exception:
            continue
    return out
