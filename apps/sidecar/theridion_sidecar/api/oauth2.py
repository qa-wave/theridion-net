"""OAuth2 authorization_code token exchange endpoint."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])


class OAuth2TokenRequest(BaseModel):
    """Parameters for the OAuth2 authorization_code token exchange."""

    token_url: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: str = ""
    code: str = Field(..., min_length=1)
    redirect_uri: str = ""
    scope: str = ""
    grant_type: str = "authorization_code"


class OAuth2TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None
    raw: dict[str, object] = Field(default_factory=dict)


@router.post("/oauth2/token", response_model=OAuth2TokenResponse)
async def exchange_token(req: OAuth2TokenRequest) -> OAuth2TokenResponse:
    form_data: dict[str, str] = {
        "grant_type": req.grant_type,
        "code": req.code,
        "client_id": req.client_id,
    }
    if req.client_secret:
        form_data["client_secret"] = req.client_secret
    if req.redirect_uri:
        form_data["redirect_uri"] = req.redirect_uri
    if req.scope:
        form_data["scope"] = req.scope

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(req.token_url, data=form_data)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail=f"token endpoint unreachable: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"token endpoint error: {response.text}",
        )

    try:
        body = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"invalid JSON from token endpoint: {exc}"
        ) from exc

    if "access_token" not in body:
        raise HTTPException(
            status_code=502,
            detail=f"no access_token in response: {body}",
        )

    return OAuth2TokenResponse(
        access_token=body["access_token"],
        token_type=body.get("token_type", "Bearer"),
        expires_in=body.get("expires_in"),
        refresh_token=body.get("refresh_token"),
        scope=body.get("scope"),
        raw=body,
    )
