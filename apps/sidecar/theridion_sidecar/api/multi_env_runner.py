"""Multi-environment runner — run collection against multiple envs."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from theridion_sidecar import storage
from theridion_sidecar import environments

router = APIRouter(prefix="/api/test", tags=["test"])


class MultiEnvRequest(BaseModel):
    collection_id: str = Field(..., min_length=1)
    environment_ids: list[str] = Field(..., min_length=1)


class EnvRunResult(BaseModel):
    env_name: str
    env_id: str
    passed: int
    failed: int
    errors: int
    elapsed_ms: float


class RequestStatusRow(BaseModel):
    request_name: str
    statuses: dict[str, int]


class MultiEnvResult(BaseModel):
    results: list[EnvRunResult]
    comparison: list[RequestStatusRow]


def _flatten_requests(items: list[dict]) -> list[dict]:
    """Recursively flatten collection items into a list of requests."""
    result: list[dict] = []
    for item in items:
        if item.get("is_folder"):
            result.extend(_flatten_requests(item.get("items", [])))
        else:
            result.append(item)
    return result


async def _run_env(
    collection: dict, env_id: str, env_name: str,
) -> tuple[EnvRunResult, dict[str, int]]:
    """Run all requests in collection against one environment."""
    requests = _flatten_requests(collection.get("items", []))
    passed = 0
    failed = 0
    errors = 0
    statuses: dict[str, int] = {}
    start = time.perf_counter()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for req_item in requests:
            url = req_item.get("url", "")
            method = req_item.get("method", "GET")
            headers = req_item.get("headers", {})
            body = req_item.get("body")
            name = req_item.get("name", url)

            # Substitute variables
            try:
                env_obj = environments.get(env_id)
                if env_obj:
                    url = environments.substitute(url, env_obj)
                    headers = environments.substitute_dict(headers, env_obj)
                    if body:
                        body = environments.substitute(body, env_obj)
            except Exception:
                pass

            try:
                resp = await client.request(
                    method=method, url=url, headers=headers,
                    content=body.encode() if body else None,
                )
                statuses[name] = resp.status_code
                if resp.status_code < 400:
                    passed += 1
                else:
                    failed += 1
            except Exception:
                errors += 1
                statuses[name] = 0

    elapsed = (time.perf_counter() - start) * 1000
    return (
        EnvRunResult(
            env_name=env_name, env_id=env_id,
            passed=passed, failed=failed, errors=errors,
            elapsed_ms=round(elapsed, 2),
        ),
        statuses,
    )


@router.post("/multi-env", response_model=MultiEnvResult)
async def multi_env_runner(req: MultiEnvRequest) -> MultiEnvResult:
    # Load collection
    col_path = storage.collections_dir() / f"{req.collection_id}.json"
    if not col_path.exists():
        raise HTTPException(status_code=404, detail="Collection not found")

    collection = json.loads(col_path.read_text(encoding="utf-8"))

    # Load env names
    env_names: dict[str, str] = {}
    for eid in req.environment_ids:
        env_obj = environments.get(eid)
        env_names[eid] = env_obj.name if env_obj else eid

    # Run in parallel
    tasks = [
        _run_env(collection, eid, env_names[eid])
        for eid in req.environment_ids
    ]
    raw_results = await asyncio.gather(*tasks)

    results: list[EnvRunResult] = []
    all_statuses: dict[str, dict[str, int]] = {}
    for env_result, statuses in raw_results:
        results.append(env_result)
        all_statuses[env_result.env_id] = statuses

    # Build comparison
    all_request_names: list[str] = []
    for _, statuses in raw_results:
        for name in statuses:
            if name not in all_request_names:
                all_request_names.append(name)

    comparison: list[RequestStatusRow] = []
    for name in all_request_names:
        row_statuses = {
            eid: all_statuses.get(eid, {}).get(name, 0)
            for eid in req.environment_ids
        }
        comparison.append(RequestStatusRow(
            request_name=name, statuses=row_statuses,
        ))

    return MultiEnvResult(results=results, comparison=comparison)
