"""Data-driven collection runner — iterate a collection over CSV/JSON rows.

Each row from the data source is substituted into the collection's requests as
variables (``{{column_name}}``).  Results are surfaced per-iteration and the
overall run summary is returned.

Features:
* CSV (RFC 4180) and JSON array (of objects) data sources.
* Variable scoping: row columns take precedence over environment and collection
  variables.
* Per-request assertion evaluation (honours existing assertions).
* Up to 10 000 rows.
* Optional delay between iterations (think time).
* Fail-fast mode: stop after first failing iteration.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import time
import uuid
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import environments, storage
from ..models import AuthConfig
from ..api._auth import apply_auth
from ..assertions import evaluate_all as _eval_all, ResponseData as _ResponseData

router = APIRouter(prefix="/api/collection-runner", tags=["collection-runner"])

_MAX_ROWS = 10_000
_MAX_RUNS = 50

# run_id → CollectionRunState
_runs: dict[str, "CollectionRunState"] = {}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DataSource(BaseModel):
    type: Literal["csv", "json"] = "json"
    data: str  # CSV text or JSON array text


class CollectionRunInput(BaseModel):
    collection_id: str
    datasource: DataSource
    environment_id: str | None = None
    auth: AuthConfig | None = None
    # ms between iterations (think time)
    delay_ms: int = Field(default=0, ge=0)
    # Stop after first failing iteration
    fail_fast: bool = False
    # Request timeout per request
    timeout_ms: int = Field(default=30_000, ge=100, le=120_000)


class RequestResult(BaseModel):
    item_id: str
    item_name: str
    method: str
    url: str
    status_code: int | None
    elapsed_ms: float
    passed: bool
    assertion_failures: list[str] = Field(default_factory=list)
    error: str | None


class IterationResult(BaseModel):
    iteration: int
    row_data: dict[str, str]
    requests: list[RequestResult]
    passed: bool
    error: str | None


class CollectionRunResult(BaseModel):
    run_id: str
    status: Literal["running", "done", "stopped", "error"]
    collection_id: str
    total_iterations: int
    completed_iterations: int
    passed_iterations: int
    failed_iterations: int
    iterations: list[IterationResult]
    duration_ms: float
    error: str | None


class CollectionRunState:
    def __init__(self, run_id: str, collection_id: str, total: int) -> None:
        self.run_id = run_id
        self.collection_id = collection_id
        self.total_iterations = total
        self.status: Literal["running", "done", "stopped", "error"] = "running"
        self.iterations: list[IterationResult] = []
        self.started_at = time.perf_counter()
        self.finished_at: float | None = None
        self.error: str | None = None
        self.stop_event = asyncio.Event()

    @property
    def completed(self) -> int:
        return len(self.iterations)

    @property
    def passed(self) -> int:
        return sum(1 for it in self.iterations if it.passed)

    @property
    def failed(self) -> int:
        return sum(1 for it in self.iterations if not it.passed)

    def to_result(self) -> CollectionRunResult:
        dur = ((self.finished_at or time.perf_counter()) - self.started_at) * 1000
        return CollectionRunResult(
            run_id=self.run_id,
            status=self.status,
            collection_id=self.collection_id,
            total_iterations=self.total_iterations,
            completed_iterations=self.completed,
            passed_iterations=self.passed,
            failed_iterations=self.failed,
            iterations=self.iterations,
            duration_ms=round(dur, 2),
            error=self.error,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_rows(ds: DataSource) -> list[dict[str, str]]:
    if ds.type == "csv":
        reader = csv.DictReader(io.StringIO(ds.data))
        rows = [{str(k): str(v) for k, v in row.items()} for row in reader]
    else:
        parsed = json.loads(ds.data)
        if not isinstance(parsed, list):
            raise ValueError("JSON data source must be an array of objects")
        rows = [{str(k): str(v) for k, v in (r if isinstance(r, dict) else {}).items()} for r in parsed]
    if len(rows) > _MAX_ROWS:
        raise ValueError(f"data source exceeds max {_MAX_ROWS} rows")
    return rows


def _apply_row_vars(template: str | None, row: dict[str, str]) -> str | None:
    """Substitute {{col}} markers in a string using row data."""
    if template is None:
        return None
    for k, v in row.items():
        template = template.replace(f"{{{{{k}}}}}", v)
    return template


async def _execute_request(
    client: httpx.AsyncClient,
    item: Any,  # CollectionItem
    env: Any,
    coll_vars: dict[str, str] | None,
    row: dict[str, str],
    timeout_s: float,
    run_auth: AuthConfig | None,
) -> RequestResult:
    """Execute a single collection item (request) with row variables."""
    # Resolve URL/headers/body — row takes priority
    url = _apply_row_vars(item.url or "", row) or ""
    url = environments.substitute(url, env, collection_vars=coll_vars)

    headers: dict[str, str] = {}
    for k, v in item.headers.items():
        hk = _apply_row_vars(k, row) or k
        hv = _apply_row_vars(v, row) or v
        headers[hk] = environments.substitute(hv, env, collection_vars=coll_vars)

    body = _apply_row_vars(item.body, row)
    if body:
        body = environments.substitute(body, env, collection_vars=coll_vars)

    query: dict[str, str] = {}
    # Apply item-level auth first, then run-level auth overrides
    item_auth = item.auth or (run_auth if run_auth else None)
    if item_auth and item_auth.type != "none":
        apply_auth(item_auth, headers, query, env, collection_vars=coll_vars)

    method = item.method or "GET"
    content = body.encode("utf-8") if body else None

    t0 = time.perf_counter()
    status_code: int | None = None
    resp_text: str | None = None
    resp_headers: dict[str, str] = {}
    error: str | None = None

    try:
        resp = await client.request(
            method=method,
            url=url,
            headers=headers,
            params=query or None,
            content=content,
            timeout=timeout_s,
        )
        status_code = resp.status_code
        resp_headers = dict(resp.headers)
        try:
            resp_text = resp.text
        except Exception:
            resp_text = resp.content.decode("utf-8", errors="replace")
    except Exception as exc:
        error = str(exc)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Evaluate assertions
    assertion_failures: list[str] = []
    if item.assertions and status_code is not None:
        try:
            resp_data = _ResponseData(
                status=status_code,
                headers=resp_headers,
                body=resp_text or "",
                elapsed_ms=elapsed_ms,
            )
            results = _eval_all(item.assertions, resp_data)
            assertion_failures = [r.message for r in results if not r.passed]
        except Exception as exc:
            assertion_failures = [f"assertion eval error: {exc}"]

    passed = error is None and not assertion_failures

    return RequestResult(
        item_id=item.id,
        item_name=item.name,
        method=method,
        url=url,
        status_code=status_code,
        elapsed_ms=round(elapsed_ms, 2),
        passed=passed,
        assertion_failures=assertion_failures,
        error=error,
    )


def _flatten_items(items: list[Any]) -> list[Any]:
    """Flatten folders recursively to get leaf request items."""
    flat: list[Any] = []
    for item in items:
        if item.is_folder:
            flat.extend(_flatten_items(item.items))
        elif item.kind == "request" and item.url:
            flat.append(item)
    return flat


async def _run_collection(state: CollectionRunState, inp: CollectionRunInput, rows: list[dict[str, str]]) -> None:
    coll = storage.get(inp.collection_id)
    if coll is None:
        state.status = "error"
        state.error = f"collection {inp.collection_id!r} not found"
        state.finished_at = time.perf_counter()
        return

    env = environments.get(inp.environment_id) if inp.environment_id else None
    coll_vars: dict[str, str] = {v.name: v.value for v in coll.variables if v.enabled}
    items = _flatten_items(coll.items)
    timeout_s = inp.timeout_ms / 1000.0

    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True, verify=False) as client:  # noqa: S501
        for i, row in enumerate(rows):
            if state.stop_event.is_set():
                state.status = "stopped"
                break

            req_results: list[RequestResult] = []
            iter_error: str | None = None
            iter_passed = True

            for item in items:
                if state.stop_event.is_set():
                    break
                try:
                    rr = await _execute_request(
                        client, item, env, coll_vars, row, timeout_s, inp.auth
                    )
                    req_results.append(rr)
                    if not rr.passed:
                        iter_passed = False
                except Exception as exc:
                    iter_passed = False
                    iter_error = str(exc)
                    req_results.append(RequestResult(
                        item_id=item.id,
                        item_name=item.name,
                        method=item.method or "GET",
                        url=item.url or "",
                        status_code=None,
                        elapsed_ms=0.0,
                        passed=False,
                        error=str(exc),
                    ))

            state.iterations.append(IterationResult(
                iteration=i,
                row_data=row,
                requests=req_results,
                passed=iter_passed,
                error=iter_error,
            ))

            if not iter_passed and inp.fail_fast:
                state.status = "done"
                break

            if inp.delay_ms > 0:
                await asyncio.sleep(inp.delay_ms / 1000.0)

    if state.status == "running":
        state.status = "done"
    state.finished_at = time.perf_counter()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/run", response_model=CollectionRunResult)
async def run_collection(inp: CollectionRunInput) -> CollectionRunResult:
    """Run a collection synchronously over the data source rows.

    Returns the full result once complete.  For long runs use
    ``/run-async`` + poll ``/runs/{run_id}``.
    """
    # Validate collection exists
    coll = storage.get(inp.collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    # Validate environment
    if inp.environment_id:
        env = environments.get(inp.environment_id)
        if env is None:
            raise HTTPException(status_code=404, detail="environment not found")

    try:
        rows = _parse_rows(inp.datasource)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not rows:
        raise HTTPException(status_code=422, detail="data source contains no rows")

    run_id = str(uuid.uuid4())
    state = CollectionRunState(run_id, inp.collection_id, len(rows))
    _runs[run_id] = state

    # Evict oldest if needed
    if len(_runs) > _MAX_RUNS:
        oldest = next(iter(_runs))
        del _runs[oldest]

    await _run_collection(state, inp, rows)
    return state.to_result()


@router.post("/run-async", response_model=dict)
async def run_collection_async(inp: CollectionRunInput) -> dict[str, str]:
    """Start a collection run asynchronously.  Returns run_id; poll /runs/{run_id}."""
    coll = storage.get(inp.collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    if inp.environment_id:
        env = environments.get(inp.environment_id)
        if env is None:
            raise HTTPException(status_code=404, detail="environment not found")

    try:
        rows = _parse_rows(inp.datasource)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not rows:
        raise HTTPException(status_code=422, detail="data source contains no rows")

    run_id = str(uuid.uuid4())
    state = CollectionRunState(run_id, inp.collection_id, len(rows))
    _runs[run_id] = state

    if len(_runs) > _MAX_RUNS:
        oldest = next(iter(_runs))
        del _runs[oldest]

    asyncio.create_task(_run_collection(state, inp, rows))
    return {"run_id": run_id, "total_iterations": len(rows)}


@router.get("/runs/{run_id}", response_model=CollectionRunResult)
def get_run(run_id: str) -> CollectionRunResult:
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="run not found")
    return state.to_result()


@router.post("/runs/{run_id}/stop", response_model=dict)
def stop_run(run_id: str) -> dict[str, str]:
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="run not found")
    state.stop_event.set()
    state.status = "stopped"
    return {"status": "stopped", "run_id": run_id}


@router.get("/runs", response_model=list[dict])
def list_runs() -> list[dict]:
    return [
        {
            "run_id": s.run_id,
            "collection_id": s.collection_id,
            "status": s.status,
            "total_iterations": s.total_iterations,
            "completed_iterations": s.completed,
        }
        for s in reversed(list(_runs.values()))
    ]
