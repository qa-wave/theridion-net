"""RunResult v2 — emit load/security results in the canonical cross-product contract.

Schema: /theridion-weave/docs/contracts/run-result-v2.schema.json
  schema_version: 2
  product: "net"
  suite_type: "load" | "security"
  requests: list of per-step summaries
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/run-result", tags=["run-result-v2"])


# ---------------------------------------------------------------------------
# RunResult v2 wire contract (subset needed for Net)
# ---------------------------------------------------------------------------

SuiteType = Literal["load", "security", "integration"]
RequestStatus = Literal["pass", "fail", "skip", "blocked"]


class RunResultRequest(BaseModel):
    """Single request/step entry inside RunResult v2 ``requests`` array."""
    request_id: str | None = None
    name: str
    method: str | None = None
    url: str | None = None
    status_code: int | None = None
    status: RequestStatus
    duration_ms: float | None = None
    test_key: str | None = None
    evidence: str | None = None
    error: str | None = None


class RunResultMeta(BaseModel):
    git_sha: str | None = None
    report_url: str | None = None
    weave_case_key: str | None = None
    triggered_by: str | None = None


class RunResultV2(BaseModel):
    """Canonical RunResult v2 — matches run-result-v2.schema.json exactly."""
    schema_version: Literal[2] = 2
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    product: Literal["net"] = "net"
    suite_type: SuiteType
    collection_id: str | None = None
    collection_name: str | None = None
    environment: str | None = None
    branch: str | None = None
    started_at: str
    finished_at: str | None = None
    duration_ms: float | None = None
    total: int | None = None
    passed: int | None = None
    failed: int | None = None
    flaky: int | None = None
    requests: list[RunResultRequest]
    meta: RunResultMeta | None = None


# ---------------------------------------------------------------------------
# Load test → RunResult v2
# ---------------------------------------------------------------------------


class LoadRunResultV2Input(BaseModel):
    """Wrap a load test result for RunResult v2 publication."""
    # Load run result fields (mirrors load_runner.LoadRunResult)
    total_requests: int
    successful: int
    failed: int
    errors: dict[str, int] = Field(default_factory=dict)
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
    # Metadata
    collection_id: str | None = None
    collection_name: str | None = None
    environment: str | None = None
    url: str | None = None
    method: str | None = None
    started_at: str | None = None
    # Hub publish
    hub_url: str | None = None
    hub_token: str | None = None


class LoadRunResultV2Output(BaseModel):
    run_result: RunResultV2
    published: bool
    publish_error: str | None = None


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _load_to_run_result(inp: LoadRunResultV2Input, started_at: str) -> RunResultV2:
    """Convert a LoadRunResult to RunResultV2 format."""
    finished_at = _now_iso()
    duration_ms = inp.duration_seconds * 1000.0

    # Represent the load test as a single synthetic request summary.
    # The "pass" criterion: error rate < 5%.
    error_rate = (inp.failed / inp.total_requests) if inp.total_requests > 0 else 0.0
    status: RequestStatus = "pass" if error_rate < 0.05 else "fail"

    evidence_parts = [
        f"RPS={inp.requests_per_second:.1f}",
        f"avg={inp.avg_latency_ms:.0f}ms",
        f"p95={inp.p95_ms:.0f}ms",
        f"p99={inp.p99_ms:.0f}ms",
    ]
    if inp.errors:
        evidence_parts.append(f"errors={inp.errors}")

    requests = [
        RunResultRequest(
            name=f"Load Test — {inp.method or 'GET'} {inp.url or '(unknown)'}",
            method=inp.method,
            url=inp.url,
            status=status,
            duration_ms=duration_ms,
            evidence=" | ".join(evidence_parts),
            error=None if error_rate < 0.05 else f"error_rate={error_rate:.1%}",
        )
    ]

    return RunResultV2(
        product="net",
        suite_type="load",
        collection_id=inp.collection_id,
        collection_name=inp.collection_name,
        environment=inp.environment,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        total=1,
        passed=1 if status == "pass" else 0,
        failed=1 if status == "fail" else 0,
        requests=requests,
        meta=RunResultMeta(triggered_by="net:load"),
    )


# ---------------------------------------------------------------------------
# Security scan → RunResult v2
# ---------------------------------------------------------------------------


class SecurityRunResultV2Input(BaseModel):
    """Wrap an OWASP scan result for RunResult v2 publication."""
    url: str
    findings: list[dict] = Field(default_factory=list)  # OWASPFinding-compatible
    score: int = 100
    scan_types_run: list[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0
    collection_id: str | None = None
    collection_name: str | None = None
    environment: str | None = None
    started_at: str | None = None
    hub_url: str | None = None
    hub_token: str | None = None


class SecurityRunResultV2Output(BaseModel):
    run_result: RunResultV2
    published: bool
    publish_error: str | None = None


def _security_to_run_result(inp: SecurityRunResultV2Input, started_at: str) -> RunResultV2:
    """Convert an OWASP scan to RunResultV2 format."""
    finished_at = _now_iso()
    duration_ms = inp.elapsed_ms

    # Each unique finding type becomes a request entry.
    requests: list[RunResultRequest] = []

    if not inp.findings:
        requests.append(RunResultRequest(
            name=f"Security Scan — {inp.url}",
            url=inp.url,
            status="pass",
            duration_ms=duration_ms,
            evidence=f"score={inp.score}/100, no findings",
        ))
    else:
        for finding in inp.findings:
            severity = finding.get("severity", "info")
            status: RequestStatus = "pass" if severity == "info" else "fail"
            requests.append(RunResultRequest(
                name=finding.get("title", "Finding"),
                url=inp.url,
                status=status,
                duration_ms=None,
                evidence=finding.get("evidence"),
                error=finding.get("description") if status == "fail" else None,
            ))

    passed = sum(1 for r in requests if r.status == "pass")
    failed = len(requests) - passed

    return RunResultV2(
        product="net",
        suite_type="security",
        collection_id=inp.collection_id,
        collection_name=inp.collection_name,
        environment=inp.environment,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        total=len(requests),
        passed=passed,
        failed=failed,
        requests=requests,
        meta=RunResultMeta(triggered_by="net:security"),
    )


# ---------------------------------------------------------------------------
# Hub publish helper
# ---------------------------------------------------------------------------


async def _publish_to_hub(
    run_result: RunResultV2,
    hub_url: str,
    hub_token: str,
) -> tuple[bool, str | None]:
    """POST the RunResult v2 payload to Hub /api/runs/ingest."""
    ingest_url = f"{hub_url.rstrip('/')}/api/runs/ingest"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                ingest_url,
                json=run_result.model_dump(mode="json"),
                headers={
                    "Authorization": f"Bearer {hub_token}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": run_result.run_id,
                },
            )
            if resp.status_code in (200, 201):
                return True, None
            return False, f"Hub returned {resp.status_code}: {resp.text[:200]}"
    except httpx.RequestError as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/load", response_model=LoadRunResultV2Output)
async def wrap_load_result(inp: LoadRunResultV2Input) -> LoadRunResultV2Output:
    """Convert a LoadRunResult to RunResult v2 and optionally publish to Hub."""
    started_at = inp.started_at or _now_iso()
    run_result = _load_to_run_result(inp, started_at)

    published = False
    publish_error: str | None = None
    if inp.hub_url and inp.hub_token:
        published, publish_error = await _publish_to_hub(run_result, inp.hub_url, inp.hub_token)

    return LoadRunResultV2Output(
        run_result=run_result,
        published=published,
        publish_error=publish_error,
    )


@router.post("/security", response_model=SecurityRunResultV2Output)
async def wrap_security_result(inp: SecurityRunResultV2Input) -> SecurityRunResultV2Output:
    """Convert a SecurityScanOutput to RunResult v2 and optionally publish to Hub."""
    started_at = inp.started_at or _now_iso()
    run_result = _security_to_run_result(inp, started_at)

    published = False
    publish_error: str | None = None
    if inp.hub_url and inp.hub_token:
        published, publish_error = await _publish_to_hub(run_result, inp.hub_url, inp.hub_token)

    return SecurityRunResultV2Output(
        run_result=run_result,
        published=published,
        publish_error=publish_error,
    )
