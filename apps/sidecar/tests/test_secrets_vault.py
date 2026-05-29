"""Tests for the secrets vault and {{secret:NAME}} substitution.

Covers:
- vault store / resolve (hit)
- vault resolve miss (returns None, token left in place)
- substitute() resolves {{secret:NAME}} from vault
- substitute() leaves {{secret:NAME}} in place when secret is missing
- plaintext env JSON never contains the resolved secret value
- existing {{var}} substitution unaffected (backward compat)
- vault API endpoints: list / store / delete / exists
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def vault_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point THERIDION_HOME + vault passphrase to tmp_path for isolation."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    monkeypatch.setenv("THERIDION_VAULT_PASSPHRASE", "test-passphrase-abc123")
    # Force module re-import so storage paths pick up the new env vars.
    import importlib
    import theridion_sidecar.secrets_vault as sv
    import theridion_sidecar.storage as st
    importlib.reload(st)
    importlib.reload(sv)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    monkeypatch.setenv("THERIDION_VAULT_PASSPHRASE", "test-passphrase-abc123")
    from theridion_sidecar.main import create_app
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Unit tests: secrets_vault module
# ---------------------------------------------------------------------------


def test_vault_store_and_resolve(vault_env: None) -> None:
    from theridion_sidecar import secrets_vault as sv

    sv.store("MY_TOKEN", "super-secret-value")
    result = sv.resolve("MY_TOKEN")
    assert result == "super-secret-value"


def test_vault_resolve_missing_returns_none(vault_env: None) -> None:
    from theridion_sidecar import secrets_vault as sv

    result = sv.resolve("DOES_NOT_EXIST")
    assert result is None


def test_vault_enc_file_is_not_plaintext(vault_env: None, tmp_path: Path) -> None:
    """The .enc file must not contain the plaintext secret."""
    from theridion_sidecar import secrets_vault as sv

    sv.store("API_KEY", "top-secret-12345")
    enc_path = tmp_path / "secrets" / "API_KEY.enc"
    assert enc_path.exists()
    raw = enc_path.read_bytes()
    assert b"top-secret-12345" not in raw


def test_vault_delete(vault_env: None) -> None:
    from theridion_sidecar import secrets_vault as sv

    sv.store("TEMP_KEY", "value")
    assert sv.resolve("TEMP_KEY") == "value"
    deleted = sv.delete("TEMP_KEY")
    assert deleted is True
    assert sv.resolve("TEMP_KEY") is None


def test_vault_list_names(vault_env: None) -> None:
    from theridion_sidecar import secrets_vault as sv

    sv.store("TOKEN_A", "a")
    sv.store("TOKEN_B", "b")
    names = sv.list_names()
    assert "TOKEN_A" in names
    assert "TOKEN_B" in names


def test_vault_invalid_name_raises(vault_env: None) -> None:
    from theridion_sidecar import secrets_vault as sv

    with pytest.raises(ValueError):
        sv.store("../../etc/passwd", "evil")


# ---------------------------------------------------------------------------
# Unit tests: substitute() with {{secret:NAME}}
# ---------------------------------------------------------------------------


def test_substitute_resolves_secret_hit(vault_env: None) -> None:
    from theridion_sidecar import secrets_vault as sv
    from theridion_sidecar.environments import substitute

    sv.store("BEARER_TOKEN", "abc-xyz-999")
    result = substitute("Bearer {{secret:BEARER_TOKEN}}", env=None)
    assert result == "Bearer abc-xyz-999"


def test_substitute_leaves_secret_token_on_miss(vault_env: None) -> None:
    from theridion_sidecar.environments import substitute

    # Secret is NOT stored — token must stay in place
    result = substitute("Bearer {{secret:MISSING_TOKEN}}", env=None)
    assert result == "Bearer {{secret:MISSING_TOKEN}}"


def test_substitute_secret_does_not_leak_to_env_lookup(
    vault_env: None,
    tmp_path: Path,
) -> None:
    """Resolving {{secret:NAME}} must NOT place the value into the plain env
    lookup dict (i.e. the env JSON file on disk remains clean)."""
    import json
    from theridion_sidecar import secrets_vault as sv
    from theridion_sidecar.environments import (
        Environment,
        EnvVariable,
        substitute,
        _atomic_write,
    )

    sv.store("DB_PASS", "hunter2")

    env = Environment(
        id="11111111-1111-1111-1111-111111111111",
        name="Test",
        variables=[EnvVariable(name="host", value="db.example.com")],
    )
    _atomic_write(env)

    # Perform substitution
    result = substitute("{{host}}:{{secret:DB_PASS}}", env=env)
    assert result == "db.example.com:hunter2"

    # Read back the env JSON and assert the plaintext secret is NOT there
    env_file = tmp_path / "environments" / "11111111-1111-1111-1111-111111111111.json"
    raw = json.loads(env_file.read_text())
    env_text = json.dumps(raw)
    assert "hunter2" not in env_text


def test_substitute_plain_var_still_works_after_change(vault_env: None) -> None:
    """Backward compat: existing {{var}} resolution must be unaffected."""
    from theridion_sidecar.environments import Environment, EnvVariable, substitute

    env = Environment(
        id="22222222-2222-2222-2222-222222222222",
        name="T",
        variables=[EnvVariable(name="baseUrl", value="https://api.example.com")],
    )
    result = substitute("{{baseUrl}}/v1/health", env=env)
    assert result == "https://api.example.com/v1/health"


def test_substitute_secret_and_plain_var_combined(vault_env: None) -> None:
    from theridion_sidecar import secrets_vault as sv
    from theridion_sidecar.environments import Environment, EnvVariable, substitute

    sv.store("AUTH_TOKEN", "tok-secret")
    env = Environment(
        id="33333333-3333-3333-3333-333333333333",
        name="T",
        variables=[EnvVariable(name="base", value="https://api.io")],
    )
    result = substitute("{{base}}/data?token={{secret:AUTH_TOKEN}}", env=env)
    assert result == "https://api.io/data?token=tok-secret"


# ---------------------------------------------------------------------------
# Integration tests: vault API endpoints
# ---------------------------------------------------------------------------


def test_api_store_and_list(client: TestClient) -> None:
    res = client.post("/api/vault/secrets", json={"name": "MY_KEY", "value": "s3cr3t"})
    assert res.status_code == 201
    assert res.json()["name"] == "MY_KEY"
    # Value must NOT be in the response
    assert "s3cr3t" not in res.text

    listed = client.get("/api/vault/secrets").json()
    assert "MY_KEY" in listed["names"]


def test_api_store_does_not_return_value(client: TestClient) -> None:
    res = client.post("/api/vault/secrets", json={"name": "SECRET_X", "value": "plaintext"})
    assert res.status_code == 201
    assert "plaintext" not in res.text


def test_api_exists(client: TestClient) -> None:
    client.post("/api/vault/secrets", json={"name": "EXISTS_KEY", "value": "val"})
    res = client.get("/api/vault/secrets/EXISTS_KEY/exists")
    assert res.status_code == 200
    assert res.json()["exists"] is True

    res2 = client.get("/api/vault/secrets/NO_SUCH_KEY/exists")
    assert res2.json()["exists"] is False


def test_api_delete(client: TestClient) -> None:
    client.post("/api/vault/secrets", json={"name": "TO_DELETE", "value": "x"})
    res = client.delete("/api/vault/secrets/TO_DELETE")
    assert res.status_code == 204

    res2 = client.delete("/api/vault/secrets/TO_DELETE")
    assert res2.status_code == 404


def test_api_execute_resolves_secret_in_bearer(client: TestClient) -> None:
    """Integration: /api/requests/execute resolves {{secret:NAME}} in auth."""
    from typing import Any
    from unittest.mock import patch

    # Store the secret via the vault API
    client.post("/api/vault/secrets", json={"name": "EXEC_TOKEN", "value": "real-token-abc"})

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.reason_phrase = "OK"
            self.headers: dict[str, str] = {"content-type": "text/plain"}
            self.text = ""
            self.content = b""
            self.url = "https://example.com"
            self.cookies: dict[str, str] = {}

    class _FakeRequest:
        def __init__(self, **kwargs: Any) -> None:
            self._kwargs = kwargs
            self.extensions: dict[str, Any] = {}

    class _FakeClient:
        last_headers: dict[str, str] = {}

        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *_a: Any) -> None:
            return None

        def build_request(self, **kwargs: Any) -> _FakeRequest:
            _FakeClient.last_headers = kwargs.get("headers", {})
            return _FakeRequest(**kwargs)

        async def send(self, request: _FakeRequest, **_kw: Any) -> _FakeResponse:
            return _FakeResponse()

    with patch("theridion_sidecar.api.requests.httpx.AsyncClient", _FakeClient):
        res = client.post(
            "/api/requests/execute",
            json={
                "method": "GET",
                "url": "https://example.com",
                "headers": {"Authorization": "Bearer {{secret:EXEC_TOKEN}}"},
            },
        )

    assert res.status_code == 200
    # The resolved Authorization header must contain the real token
    assert _FakeClient.last_headers.get("Authorization") == "Bearer real-token-abc"
