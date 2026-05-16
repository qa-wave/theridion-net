"""OAuth2 authorization_code token exchange + PKCE + callback server."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = secrets.token_urlsafe(96)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class OAuth2TokenRequest(BaseModel):
    """Parameters for the OAuth2 authorization_code token exchange."""

    token_url: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: str = ""
    code: str = Field(..., min_length=1)
    redirect_uri: str = ""
    scope: str = ""
    grant_type: str = "authorization_code"
    code_verifier: str = ""


class OAuth2TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None
    raw: dict[str, object] = Field(default_factory=dict)


class AuthorizeUrlInput(BaseModel):
    auth_url: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    redirect_uri: str = "http://localhost:9876/oauth2/callback"
    scope: str = ""
    state: str | None = None
    use_pkce: bool = True


class AuthorizeUrlOutput(BaseModel):
    url: str
    state: str
    code_verifier: str | None = None
    code_challenge: str | None = None


class CallbackServerStartInput(BaseModel):
    port: int = 9876
    timeout_seconds: int = 300


class CallbackServerStartOutput(BaseModel):
    port: int
    status: str


class CallbackServerResult(BaseModel):
    status: str  # "waiting", "received", "expired", "not_running"
    code: str | None = None
    state: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# In-process callback server state
# ---------------------------------------------------------------------------


class _CallbackState:
    """Mutable state shared between the HTTP callback handler and the
    FastAPI endpoints. Only one callback server can run at a time."""

    lock = threading.Lock()
    server: HTTPServer | None = None
    thread: threading.Thread | None = None
    code: str | None = None
    state: str | None = None
    error: str | None = None
    received: bool = False


_cb = _CallbackState()


class _CallbackHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler that captures the OAuth2 redirect."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.rstrip("/").endswith("/oauth2/callback"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        qs = parse_qs(parsed.query)
        with _cb.lock:
            _cb.code = qs.get("code", [None])[0]  # type: ignore[assignment]
            _cb.state = qs.get("state", [None])[0]  # type: ignore[assignment]
            _cb.error = qs.get("error", [None])[0]  # type: ignore[assignment]
            _cb.received = True

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = (
            "<!DOCTYPE html><html><body>"
            "<h2>Authorization successful!</h2>"
            "<p>You can close this tab and return to Theridion.</p>"
            "</body></html>"
        )
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr logging."""


def _run_server(port: int, timeout: int) -> None:
    """Run the callback HTTP server in a background thread."""
    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = 1.0  # poll interval for checking the stop flag
    with _cb.lock:
        _cb.server = server
        _cb.code = None
        _cb.state = None
        _cb.error = None
        _cb.received = False

    elapsed = 0.0
    try:
        while elapsed < timeout:
            server.handle_request()
            with _cb.lock:
                if _cb.received:
                    break
            elapsed += 1.0
    finally:
        server.server_close()
        with _cb.lock:
            _cb.server = None
            _cb.thread = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/oauth2/authorize-url", response_model=AuthorizeUrlOutput)
async def build_authorize_url(req: AuthorizeUrlInput) -> AuthorizeUrlOutput:
    """Generate an OAuth2 authorization URL, optionally with PKCE S256."""
    state = req.state or secrets.token_urlsafe(32)
    code_verifier: str | None = None
    code_challenge: str | None = None

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": req.client_id,
        "redirect_uri": req.redirect_uri,
        "state": state,
    }
    if req.scope:
        params["scope"] = req.scope

    if req.use_pkce:
        code_verifier, code_challenge = generate_pkce()
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    # Build URL preserving any existing query params
    parsed = urlparse(req.auth_url)
    existing_qs = parse_qs(parsed.query, keep_blank_values=True)
    for k, v in existing_qs.items():
        if k not in params:
            params[k] = v[0]
    url = parsed._replace(query=urlencode(params)).geturl()

    return AuthorizeUrlOutput(
        url=url,
        state=state,
        code_verifier=code_verifier,
        code_challenge=code_challenge,
    )


@router.post(
    "/oauth2/callback-server/start",
    response_model=CallbackServerStartOutput,
)
async def start_callback_server(
    body: CallbackServerStartInput,
) -> CallbackServerStartOutput:
    """Start a temporary HTTP server that waits for the OAuth2 callback."""
    with _cb.lock:
        if _cb.thread is not None and _cb.thread.is_alive():
            raise HTTPException(
                status_code=409,
                detail="callback server already running",
            )

    thread = threading.Thread(
        target=_run_server,
        args=(body.port, body.timeout_seconds),
        daemon=True,
    )
    with _cb.lock:
        _cb.thread = thread
    thread.start()

    # Give the server a moment to bind
    await asyncio.sleep(0.1)

    return CallbackServerStartOutput(port=body.port, status="listening")


@router.get(
    "/oauth2/callback-server/result",
    response_model=CallbackServerResult,
)
async def get_callback_result() -> CallbackServerResult:
    """Poll for the captured authorization code."""
    with _cb.lock:
        if _cb.received:
            return CallbackServerResult(
                status="received",
                code=_cb.code,
                state=_cb.state,
                error=_cb.error,
            )
        if _cb.thread is not None and _cb.thread.is_alive():
            return CallbackServerResult(status="waiting")
        if _cb.thread is not None:
            # Thread finished without receiving — timeout
            return CallbackServerResult(status="expired")
    return CallbackServerResult(status="not_running")


@router.post("/oauth2/callback-server/stop")
async def stop_callback_server() -> dict[str, str]:
    """Stop the callback server if it's running."""
    with _cb.lock:
        if _cb.server is not None:
            try:
                _cb.server.server_close()
            except Exception:
                pass
            _cb.server = None
        # Mark as not running so the thread exits on next loop iteration
        _cb.received = True
    return {"status": "stopped"}


@router.post("/oauth2/token", response_model=OAuth2TokenResponse)
async def exchange_token(req: OAuth2TokenRequest) -> OAuth2TokenResponse:
    """Exchange an authorization code for tokens, with optional PKCE."""
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
    if req.code_verifier:
        form_data["code_verifier"] = req.code_verifier

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


class OAuth2RefreshRequest(BaseModel):
    """Parameters for the OAuth2 refresh_token grant."""

    token_url: str = Field(..., min_length=1)
    refresh_token: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: str = ""
    scope: str = ""


@router.post("/oauth2/refresh", response_model=OAuth2TokenResponse)
async def refresh_token(req: OAuth2RefreshRequest) -> OAuth2TokenResponse:
    """Use a refresh token to obtain a new access token."""
    form_data: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": req.refresh_token,
        "client_id": req.client_id,
    }
    if req.client_secret:
        form_data["client_secret"] = req.client_secret
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
