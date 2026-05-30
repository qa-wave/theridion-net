"""Tests for load-test variable substitution and auth injection (Bod 2).

Strategy
--------
* The /api/loadtest/run endpoint spawns real httpx workers that hit a real URL.
  We intercept at the network layer using ``respx.mock`` so no external server
  is needed and tests stay fast.
* We use unique hostnames per test to avoid cross-test mock pollution.
* For the 404 / backwards-compat tests we only need the FastAPI layer response.
* ``assert_all_called=False`` + ``assert_all_mocked=False`` on every mock context
  because TestClient runs async in a threadpool and the number of requests fired
  in 0.1s can vary on slow CI machines.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def _make_env(client: TestClient, name: str, variables: list[dict]) -> str:
    """Create environment with variables; return env id."""
    r = client.post("/api/environments", json={"name": name})
    assert r.status_code == 201
    env_id = r.json()["id"]
    client.put(
        f"/api/environments/{env_id}/variables",
        json={"variables": variables},
    )
    return env_id


def _run_loadtest(client: TestClient, payload: dict) -> httpx.Response:
    return client.post("/api/loadtest/run", json=payload)


# ---------------------------------------------------------------------------
# (a) Variable substitution in URL / headers / body / query
# ---------------------------------------------------------------------------


def test_url_substitution(client: TestClient) -> None:
    """{{host}} in URL is expanded to the env value before workers fire."""
    env_id = _make_env(
        client,
        "url-sub",
        [{"name": "host", "value": "urlsub.example.local", "enabled": True}],
    )

    captured_urls: list[str] = []

    def _capture(req: httpx.Request) -> httpx.Response:
        captured_urls.append(str(req.url))
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
        rmock.get(url__regex=r"http://urlsub\.example\.local/.*").mock(
            side_effect=_capture
        )
        resp = _run_loadtest(
            client,
            {
                "url": "http://{{host}}/ping",
                "method": "GET",
                "concurrency": 1,
                "duration_seconds": 0.1,
                "environment_id": env_id,
            },
        )

    assert resp.status_code == 200, resp.text
    assert len(captured_urls) >= 1
    for url in captured_urls:
        assert "urlsub.example.local" in url
        assert "{{host}}" not in url


def test_headers_substitution(client: TestClient) -> None:
    """{{token}} in a custom header is resolved before workers fire."""
    env_id = _make_env(
        client,
        "hdr-sub",
        [{"name": "token", "value": "secret-hdr-abc", "enabled": True}],
    )

    captured: list[httpx.Request] = []

    def _capture(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
        rmock.get(url__startswith="http://hdrsub.api.local/").mock(side_effect=_capture)
        resp = _run_loadtest(
            client,
            {
                "url": "http://hdrsub.api.local/data",
                "method": "GET",
                "headers": {"X-Custom-Token": "{{token}}"},
                "concurrency": 1,
                "duration_seconds": 0.1,
                "environment_id": env_id,
            },
        )

    assert resp.status_code == 200, resp.text
    assert len(captured) >= 1
    assert captured[0].headers.get("x-custom-token") == "secret-hdr-abc"


def test_query_substitution(client: TestClient) -> None:
    """{{api_ver}} in query param dict is resolved before workers fire."""
    env_id = _make_env(
        client,
        "qry-sub",
        [{"name": "api_ver", "value": "v3", "enabled": True}],
    )

    captured: list[httpx.Request] = []

    def _capture(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
        rmock.get(url__startswith="http://qrysub.api.local/").mock(side_effect=_capture)
        resp = _run_loadtest(
            client,
            {
                "url": "http://qrysub.api.local/items",
                "method": "GET",
                "query": {"version": "{{api_ver}}"},
                "concurrency": 1,
                "duration_seconds": 0.1,
                "environment_id": env_id,
            },
        )

    assert resp.status_code == 200, resp.text
    assert len(captured) >= 1
    assert captured[0].url.params.get("version") == "v3"


def test_body_substitution(client: TestClient) -> None:
    """{{user_id}} in request body is resolved before workers fire."""
    env_id = _make_env(
        client,
        "body-sub",
        [{"name": "user_id", "value": "99", "enabled": True}],
    )

    captured: list[httpx.Request] = []

    def _capture(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(201, text="created")

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
        rmock.post("http://bodysub.api.local/users").mock(side_effect=_capture)
        resp = _run_loadtest(
            client,
            {
                "url": "http://bodysub.api.local/users",
                "method": "POST",
                "body": '{"id": "{{user_id}}"}',
                "concurrency": 1,
                "duration_seconds": 0.1,
                "environment_id": env_id,
            },
        )

    assert resp.status_code == 200, resp.text
    assert len(captured) >= 1
    assert b"99" in captured[0].content
    assert b"{{user_id}}" not in captured[0].content


# ---------------------------------------------------------------------------
# (b) Auth injection — bearer, apikey header, apikey query, bearer + env var
# ---------------------------------------------------------------------------


def test_bearer_auth_injected(client: TestClient) -> None:
    """Bearer token is injected as Authorization header for every worker request."""
    captured: list[httpx.Request] = []

    def _capture(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
        rmock.get("http://bearer.secure.local/resource").mock(side_effect=_capture)
        resp = _run_loadtest(
            client,
            {
                "url": "http://bearer.secure.local/resource",
                "method": "GET",
                "concurrency": 1,
                "duration_seconds": 0.1,
                "auth": {"type": "bearer", "token": "my-load-test-token"},
            },
        )

    assert resp.status_code == 200, resp.text
    assert len(captured) >= 1
    assert captured[0].headers.get("authorization") == "Bearer my-load-test-token"


def test_apikey_header_auth_injected(client: TestClient) -> None:
    """API key injected into request header for every worker request."""
    captured: list[httpx.Request] = []

    def _capture(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
        rmock.get("http://apikey-hdr.secure.local/data").mock(side_effect=_capture)
        resp = _run_loadtest(
            client,
            {
                "url": "http://apikey-hdr.secure.local/data",
                "method": "GET",
                "concurrency": 1,
                "duration_seconds": 0.1,
                "auth": {
                    "type": "apikey",
                    "key": "X-API-Key",
                    "value": "supersecret",
                    "add_to": "header",
                },
            },
        )

    assert resp.status_code == 200, resp.text
    assert len(captured) >= 1
    assert captured[0].headers.get("x-api-key") == "supersecret"


def test_apikey_query_auth_injected(client: TestClient) -> None:
    """API key injected as query parameter for every worker request."""
    captured: list[httpx.Request] = []

    def _capture(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
        rmock.get(url__startswith="http://apikey-qry.secure.local/").mock(
            side_effect=_capture
        )
        resp = _run_loadtest(
            client,
            {
                "url": "http://apikey-qry.secure.local/search",
                "method": "GET",
                "concurrency": 1,
                "duration_seconds": 0.1,
                "auth": {
                    "type": "apikey",
                    "key": "api_key",
                    "value": "qwerty123",
                    "add_to": "query",
                },
            },
        )

    assert resp.status_code == 200, resp.text
    assert len(captured) >= 1
    assert captured[0].url.params.get("api_key") == "qwerty123"


def test_bearer_auth_with_env_var(client: TestClient) -> None:
    """Bearer token {{jwt}} sourced from env variable is resolved and injected."""
    env_id = _make_env(
        client,
        "bearer-env",
        [{"name": "jwt", "value": "env-resolved-jwt-xyz", "enabled": True}],
    )

    captured: list[httpx.Request] = []

    def _capture(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
        rmock.get("http://bearer-env.secure.local/jwt-check").mock(side_effect=_capture)
        resp = _run_loadtest(
            client,
            {
                "url": "http://bearer-env.secure.local/jwt-check",
                "method": "GET",
                "concurrency": 1,
                "duration_seconds": 0.1,
                "environment_id": env_id,
                "auth": {"type": "bearer", "token": "{{jwt}}"},
            },
        )

    assert resp.status_code == 200, resp.text
    assert len(captured) >= 1
    assert captured[0].headers.get("authorization") == "Bearer env-resolved-jwt-xyz"


# ---------------------------------------------------------------------------
# (c) 404 on missing environment_id — no workers should fire
# ---------------------------------------------------------------------------


def test_missing_environment_returns_404(client: TestClient) -> None:
    """A non-existent environment_id yields 404 before any worker starts.

    Note: environments.get() validates UUID format, so we use a well-formed
    UUID that simply does not exist in the store.
    """
    nonexistent_uuid = "00000000-0000-0000-0000-000000000000"
    with respx.mock(assert_all_called=False, assert_all_mocked=False):
        resp = _run_loadtest(
            client,
            {
                "url": "http://notused.local/test",
                "method": "GET",
                "concurrency": 1,
                "duration_seconds": 0.1,
                "environment_id": nonexistent_uuid,
            },
        )

    assert resp.status_code == 404
    assert "environment" in resp.json().get("detail", "").lower()


# ---------------------------------------------------------------------------
# (d) Backwards compatibility — plain request without env/auth works as before
# ---------------------------------------------------------------------------


def test_backwards_compat_no_env_no_auth(client: TestClient) -> None:
    """Plain request without env/auth fields returns a valid stats payload."""
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
        rmock.get("http://plain.compat.local/health").mock(
            return_value=httpx.Response(200, text="ok")
        )
        resp = _run_loadtest(
            client,
            {
                "url": "http://plain.compat.local/health",
                "method": "GET",
                "concurrency": 2,
                "duration_seconds": 0.1,
            },
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Result schema must be intact regardless of request count.
    for field in ("total_requests", "avg_latency_ms", "p50_ms", "p95_ms", "p99_ms"):
        assert field in data, f"missing field: {field}"


def test_backwards_compat_auth_none_type(client: TestClient) -> None:
    """auth.type == 'none' is a no-op — Authorization header must NOT appear."""
    captured: list[httpx.Request] = []

    def _capture(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, text="pong")

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
        rmock.get("http://open.compat.local/ping").mock(side_effect=_capture)
        resp = _run_loadtest(
            client,
            {
                "url": "http://open.compat.local/ping",
                "method": "GET",
                "concurrency": 1,
                "duration_seconds": 0.1,
                "auth": {"type": "none"},
            },
        )

    assert resp.status_code == 200, resp.text
    for req in captured:
        header_keys_lower = {k.lower() for k in req.headers}
        assert "authorization" not in header_keys_lower
