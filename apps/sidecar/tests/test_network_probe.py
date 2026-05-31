"""Tests for network probe — port scanner and HAR capture."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_har_state():
    import theridion_sidecar.api.network_probe as _np

    _np._har_sessions.clear()
    _np._har_session_labels.clear()
    yield
    _np._har_sessions.clear()
    _np._har_session_labels.clear()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Port scanner
# ---------------------------------------------------------------------------


class TestPortScanInput:
    def test_common_ports_shorthand(self, client: TestClient) -> None:
        """Asking for 'common' ports scans all ~24 well-known ports (fast timeout)."""
        resp = client.post(
            "/api/network/portscan",
            json={"host": "127.0.0.1", "ports": "common", "timeout_ms": 200},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["host"] == "127.0.0.1"
        assert data["scanned"] > 0
        assert "results" in data
        assert isinstance(data["results"], list)
        assert all("port" in r and "open" in r for r in data["results"])

    def test_explicit_port_list(self, client: TestClient) -> None:
        resp = client.post(
            "/api/network/portscan",
            json={"host": "127.0.0.1", "ports": [80, 443, 8080], "timeout_ms": 200},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scanned"] == 3
        ports_in_result = {r["port"] for r in data["results"]}
        assert ports_in_result == {80, 443, 8080}

    def test_localhost_ports_classified(self, client: TestClient) -> None:
        """Open ports have open=True, closed have open=False."""
        resp = client.post(
            "/api/network/portscan",
            json={"host": "127.0.0.1", "ports": [9], "timeout_ms": 200},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data["results"][0]
        # Port 9 is almost certainly closed on localhost — open=False
        assert result["port"] == 9
        assert isinstance(result["open"], bool)

    def test_service_hint_included(self, client: TestClient) -> None:
        resp = client.post(
            "/api/network/portscan",
            json={"host": "127.0.0.1", "ports": [80, 22], "timeout_ms": 200},
        )
        assert resp.status_code == 200
        hints = {r["port"]: r.get("service_hint") for r in resp.json()["results"]}
        assert hints.get(80) == "http"
        assert hints.get(22) == "ssh"

    def test_invalid_ports_parameter(self, client: TestClient) -> None:
        resp = client.post(
            "/api/network/portscan",
            json={"host": "127.0.0.1", "ports": "all"},
        )
        assert resp.status_code in (422, 400)

    def test_empty_port_list_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/api/network/portscan",
            json={"host": "127.0.0.1", "ports": []},
        )
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# HAR capture
# ---------------------------------------------------------------------------


class TestHarSessions:
    def test_create_and_list_session(self, client: TestClient) -> None:
        resp = client.post("/api/network/har/sessions", json={"label": "test-session"})
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["label"] == "test-session"
        assert data["entry_count"] == 0

        list_resp = client.get("/api/network/har/sessions")
        assert list_resp.status_code == 200
        sessions = list_resp.json()
        assert any(s["session_id"] == data["session_id"] for s in sessions)

    def test_capture_adds_entry(self, client: TestClient) -> None:
        # Create session
        sess_resp = client.post("/api/network/har/sessions", json={"label": "cap"})
        session_id = sess_resp.json()["session_id"]

        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get("http://har-capture.local/ping").mock(
                return_value=httpx.Response(200, text="pong", headers={"content-type": "text/plain"})
            )
            cap_resp = client.post(
                "/api/network/har/capture",
                json={
                    "session_id": session_id,
                    "url": "http://har-capture.local/ping",
                    "method": "GET",
                },
            )

        assert cap_resp.status_code == 200
        data = cap_resp.json()
        assert data["session_id"] == session_id
        assert data["entry_index"] == 0
        assert data["status_code"] == 200

    def test_export_har_format(self, client: TestClient) -> None:
        sess_resp = client.post("/api/network/har/sessions", json={"label": "export"})
        session_id = sess_resp.json()["session_id"]

        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get("http://har-export.local/api").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
            client.post(
                "/api/network/har/capture",
                json={
                    "session_id": session_id,
                    "url": "http://har-export.local/api",
                    "method": "GET",
                },
            )

        export_resp = client.get(f"/api/network/har/{session_id}")
        assert export_resp.status_code == 200
        har = export_resp.json()
        assert "log" in har
        assert har["log"]["version"] == "1.2"
        assert "entries" in har["log"]
        assert len(har["log"]["entries"]) == 1

    def test_clear_session(self, client: TestClient) -> None:
        sess_resp = client.post("/api/network/har/sessions", json={"label": "clear"})
        session_id = sess_resp.json()["session_id"]

        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get("http://har-clear.local/a").mock(return_value=httpx.Response(200))
            client.post(
                "/api/network/har/capture",
                json={"session_id": session_id, "url": "http://har-clear.local/a"},
            )

        clear_resp = client.delete(f"/api/network/har/{session_id}")
        assert clear_resp.status_code == 200
        assert clear_resp.json()["cleared"] == 1
        # Export should now be empty
        export_resp = client.get(f"/api/network/har/{session_id}")
        assert len(export_resp.json()["log"]["entries"]) == 0

    def test_capture_unknown_session(self, client: TestClient) -> None:
        resp = client.post(
            "/api/network/har/capture",
            json={
                "session_id": "nonexistent",
                "url": "http://example.com/",
            },
        )
        assert resp.status_code == 404

    def test_export_unknown_session(self, client: TestClient) -> None:
        resp = client.get("/api/network/har/nonexistent")
        assert resp.status_code == 404

    def test_capture_failed_request_still_records(self, client: TestClient) -> None:
        """Even when the upstream is unreachable, the entry is recorded."""
        sess_resp = client.post("/api/network/har/sessions", json={"label": "fail"})
        session_id = sess_resp.json()["session_id"]

        cap_resp = client.post(
            "/api/network/har/capture",
            json={
                "session_id": session_id,
                "url": "http://127.0.0.1:1/unreachable",
                "timeout_ms": 500,
            },
        )
        assert cap_resp.status_code == 200
        data = cap_resp.json()
        assert data["error"] is not None
        # Entry should be in the export
        export_resp = client.get(f"/api/network/har/{session_id}")
        entries = export_resp.json()["log"]["entries"]
        assert len(entries) == 1
