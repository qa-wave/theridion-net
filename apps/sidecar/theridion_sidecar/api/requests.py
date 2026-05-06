"""HTTP request execution endpoint — REST first, more protocols to follow."""

from __future__ import annotations

import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/requests", tags=["requests"])

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class ExecuteRequest(BaseModel):
    method: HttpMethod = "GET"
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    follow_redirects: bool = True


class ExecuteResponse(BaseModel):
    status: int
    status_text: str
    headers: dict[str, str]
    body: str
    body_size_bytes: int
    elapsed_ms: float
    final_url: str


@router.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest) -> ExecuteResponse:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            http2=True,
            timeout=req.timeout_seconds,
            follow_redirects=req.follow_redirects,
        ) as client:
            response = await client.request(
                method=req.method,
                url=req.url,
                headers=req.headers,
                params=req.query or None,
                content=req.body.encode("utf-8") if req.body is not None else None,
            )
    except httpx.RequestError as exc:
        # Network / DNS / TLS issues — bubble up as 502 with detail. The
        # frontend treats this as a "transport" error distinct from response
        # status codes.
        raise HTTPException(status_code=502, detail=f"transport error: {exc}") from exc

    elapsed_ms = (time.perf_counter() - started) * 1000
    body_text = response.text  # decoded via response.encoding
    return ExecuteResponse(
        status=response.status_code,
        status_text=response.reason_phrase or "",
        headers=dict(response.headers),
        body=body_text,
        body_size_bytes=len(response.content),
        elapsed_ms=round(elapsed_ms, 2),
        final_url=str(response.url),
    )
