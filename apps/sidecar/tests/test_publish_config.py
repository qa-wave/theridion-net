"""Tests for publish config persistence + dual publish via config (mocked network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_LOAD_PAYLOAD: dict[str, Any] = {
    "total_requests": 100,
    "successful": 98,
    "failed": 2,
    "errors": {},
    "avg_latency_ms": 80.0,
    "min_latency_ms": 5.0,
    "max_latency_ms": 400.0,
    "p50_ms": 70.0,
    "p75_ms": 90.0,
    "p90_ms": 110.0,
    "p95_ms": 150.0,
    "p99_ms": 200.0,
    "requests_per_second": 10.0,
    "duration_seconds": 10.0,
}

_SECURITY_PAYLOAD: dict[str, Any] = {
    "url": "https://api.example.com/",
    "findings": [],
    "score": 100,
    "scan_types_run": [],
    "elapsed_ms": 100.0,
}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    # Clear any cached config module state between tests.
    import importlib
    import sys

    for mod_name in list(sys.modules.keys()):
        if "publish_config" in mod_name or "run_result_v2" in mod_name:
            del sys.modules[mod_name]

    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Config persistence tests
# ---------------------------------------------------------------------------


class TestPublishConfigEndpoints:
    def test_get_returns_defaults_when_no_config(self, client: TestClient) -> None:
        """GET /api/run-result/config returns defaults (empty strings, enabled=True)."""
        resp = client.get("/api/run-result/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["weave_url"] == ""
        assert data["weave_token_set"] is False
        assert data["hub_url"] == ""
        assert data["hub_token_set"] is False
        assert data["enabled"] is True

    def test_put_persists_config(self, client: TestClient, tmp_path: Path) -> None:
        """PUT saves config; subsequent GET reflects the change (tokens as booleans)."""
        resp = client.put(
            "/api/run-result/config",
            json={
                "weave_url": "https://weave.example.com",
                "weave_token": "weave-secret",
                "hub_url": "https://hub.example.com",
                "hub_token": "hub-secret",
                "enabled": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["weave_url"] == "https://weave.example.com"
        assert data["weave_token_set"] is True
        assert data["hub_url"] == "https://hub.example.com"
        assert data["hub_token_set"] is True

    def test_put_persists_to_disk(self, client: TestClient, tmp_path: Path) -> None:
        """PUT actually writes publish_config.json to the home dir."""
        client.put(
            "/api/run-result/config",
            json={
                "weave_url": "https://weave.local",
                "weave_token": "tok-weave",
                "hub_url": "",
                "hub_token": "",
                "enabled": True,
            },
        )
        config_file = tmp_path / "publish_config.json"
        assert config_file.exists(), "publish_config.json was not created"
        disk = json.loads(config_file.read_text())
        assert disk["weave_url"] == "https://weave.local"
        assert disk["weave_token"] == "tok-weave"

    def test_put_clears_token_with_empty_string(self, client: TestClient, tmp_path: Path) -> None:
        """PUT with empty token string clears the token."""
        # Set a token first
        client.put(
            "/api/run-result/config",
            json={"weave_url": "https://w.example.com", "weave_token": "tok", "hub_url": "", "hub_token": "", "enabled": True},
        )
        # Clear it
        resp = client.put(
            "/api/run-result/config",
            json={"weave_url": "https://w.example.com", "weave_token": "", "hub_url": "", "hub_token": "", "enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["weave_token_set"] is False

    def test_get_token_not_leaked_in_response(self, client: TestClient) -> None:
        """Token value must NOT appear in GET response body."""
        client.put(
            "/api/run-result/config",
            json={"weave_url": "https://w.example.com", "weave_token": "super-secret-xyz", "hub_url": "", "hub_token": "", "enabled": True},
        )
        resp = client.get("/api/run-result/config")
        body = resp.text
        assert "super-secret-xyz" not in body

    def test_disabled_config_returns_correct_flag(self, client: TestClient) -> None:
        """PUT with enabled=False is persisted correctly."""
        resp = client.put(
            "/api/run-result/config",
            json={"weave_url": "", "weave_token": "", "hub_url": "", "hub_token": "", "enabled": False},
        )
        assert resp.json()["enabled"] is False


# ---------------------------------------------------------------------------
# Dual publish — mocked network
# ---------------------------------------------------------------------------


class TestDualPublishViaConfig:
    def _put_config(
        self,
        client: TestClient,
        weave_url: str = "",
        weave_token: str = "",
        hub_url: str = "",
        hub_token: str = "",
        enabled: bool = True,
    ) -> None:
        r = client.put(
            "/api/run-result/config",
            json={
                "weave_url": weave_url,
                "weave_token": weave_token,
                "hub_url": hub_url,
                "hub_token": hub_token,
                "enabled": enabled,
            },
        )
        assert r.status_code == 200

    @respx.mock
    def test_publishes_to_weave_from_config(self, client: TestClient) -> None:
        """When weave_url+weave_token are set in config, load result is POSTed to Weave."""
        weave_ingest = respx.post("https://weave.local/api/runs/ingest").mock(
            return_value=Response(201, json={"ok": True})
        )
        self._put_config(client, weave_url="https://weave.local", weave_token="w-tok")

        resp = client.post("/api/run-result/load", json=_LOAD_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["published"] is True
        assert data["publish_error"] is None
        assert weave_ingest.called

    @respx.mock
    def test_publishes_to_hub_from_config(self, client: TestClient) -> None:
        """When hub_url+hub_token are set in config, load result is POSTed to Hub."""
        hub_ingest = respx.post("https://hub.local/api/ingest").mock(
            return_value=Response(200, json={"ok": True})
        )
        self._put_config(client, hub_url="https://hub.local", hub_token="h-tok")

        resp = client.post("/api/run-result/load", json=_LOAD_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["published"] is True
        assert hub_ingest.called

    @respx.mock
    def test_publishes_to_both_targets(self, client: TestClient) -> None:
        """When both Weave and Hub are configured, both receive the payload."""
        weave_ingest = respx.post("https://weave.test/api/runs/ingest").mock(
            return_value=Response(201)
        )
        hub_ingest = respx.post("https://hub.test/api/ingest").mock(
            return_value=Response(200)
        )
        self._put_config(
            client,
            weave_url="https://weave.test",
            weave_token="wt",
            hub_url="https://hub.test",
            hub_token="ht",
        )

        resp = client.post("/api/run-result/load", json=_LOAD_PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["published"] is True
        assert weave_ingest.called
        assert hub_ingest.called

    @respx.mock
    def test_weave_failure_does_not_block_hub(self, client: TestClient) -> None:
        """If Weave fails, Hub still receives the payload (best-effort)."""
        respx.post("https://weave.fail/api/runs/ingest").mock(
            return_value=Response(500, text="server error")
        )
        hub_ingest = respx.post("https://hub.ok/api/ingest").mock(
            return_value=Response(200)
        )
        self._put_config(
            client,
            weave_url="https://weave.fail",
            weave_token="wt",
            hub_url="https://hub.ok",
            hub_token="ht",
        )

        resp = client.post("/api/run-result/load", json=_LOAD_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        # Hub succeeded → published=True even though Weave failed
        assert data["published"] is True
        assert hub_ingest.called

    @respx.mock
    def test_hub_failure_captured_in_error(self, client: TestClient) -> None:
        """Hub 500 → published=False, error captured."""
        respx.post("https://hub.fail/api/ingest").mock(
            return_value=Response(503, text="unavailable")
        )
        self._put_config(client, hub_url="https://hub.fail", hub_token="ht")

        resp = client.post("/api/run-result/load", json=_LOAD_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["published"] is False
        assert data["publish_error"] is not None

    @respx.mock
    def test_disabled_config_skips_all_publish(self, client: TestClient) -> None:
        """When enabled=False, no network calls are made."""
        weave_mock = respx.post("https://weave.skip/api/runs/ingest").mock(
            return_value=Response(200)
        )
        hub_mock = respx.post("https://hub.skip/api/ingest").mock(
            return_value=Response(200)
        )
        self._put_config(
            client,
            weave_url="https://weave.skip",
            weave_token="wt",
            hub_url="https://hub.skip",
            hub_token="ht",
            enabled=False,
        )

        resp = client.post("/api/run-result/load", json=_LOAD_PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["published"] is False
        assert not weave_mock.called
        assert not hub_mock.called

    @respx.mock
    def test_per_call_hub_overrides_config(self, client: TestClient) -> None:
        """hub_url/hub_token on the call body take precedence over config."""
        # Config has a different hub URL
        self._put_config(client, hub_url="https://config-hub.test", hub_token="cfg-tok")

        override_mock = respx.post("https://override-hub.test/api/ingest").mock(
            return_value=Response(200)
        )

        resp = client.post(
            "/api/run-result/load",
            json={**_LOAD_PAYLOAD, "hub_url": "https://override-hub.test", "hub_token": "override-tok"},
        )
        assert resp.status_code == 200
        assert override_mock.called

    @respx.mock
    def test_idempotency_key_is_run_id(self, client: TestClient) -> None:
        """Requests to Weave/Hub carry Idempotency-Key equal to run_id."""
        weave_ingest = respx.post("https://weave.idem/api/runs/ingest").mock(
            return_value=Response(201)
        )
        self._put_config(client, weave_url="https://weave.idem", weave_token="wt")

        resp = client.post("/api/run-result/load", json=_LOAD_PAYLOAD)
        assert resp.status_code == 200
        run_id = resp.json()["run_result"]["run_id"]

        # Inspect the captured request
        assert weave_ingest.calls.last is not None
        sent_key = weave_ingest.calls.last.request.headers.get("idempotency-key")
        assert sent_key == run_id

    @respx.mock
    def test_security_result_published_via_config(self, client: TestClient) -> None:
        """Security scan results also go through the config-based dual publish."""
        weave_ingest = respx.post("https://weave.sec/api/runs/ingest").mock(
            return_value=Response(201)
        )
        self._put_config(client, weave_url="https://weave.sec", weave_token="wt")

        resp = client.post("/api/run-result/security", json=_SECURITY_PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["published"] is True
        assert weave_ingest.called

    @respx.mock
    def test_no_targets_configured_no_publish(self, client: TestClient) -> None:
        """Empty config (default state) → published=False, no error."""
        resp = client.post("/api/run-result/load", json=_LOAD_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["published"] is False
        assert data["publish_error"] is None
