"""Tests for the fuzzer API — payload positions, attack modes, SSE, flag."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_fuzzer():
    """Reset fuzzer in-process state between tests."""
    import theridion_sidecar.api.fuzzer as _fuzz

    _fuzz._runs.clear()
    _fuzz._results.clear()
    _fuzz._stop_signals.clear()
    _fuzz._subscribers.clear()
    yield
    _fuzz._runs.clear()
    _fuzz._results.clear()
    _fuzz._stop_signals.clear()
    _fuzz._subscribers.clear()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# _build_requests unit tests (pure logic)
# ---------------------------------------------------------------------------


class TestBuildRequests:
    def test_sniper_single_position(self) -> None:
        from theridion_sidecar.api.fuzzer import FuzzerConfig, PayloadPosition, _build_requests

        cfg = FuzzerConfig(
            url="http://example.com/user/§id§",
            method="GET",
            attack_mode="sniper",
            positions=[PayloadPosition(name="id", payloads=["1", "2", "admin"])],
        )
        reqs = _build_requests(cfg)
        assert len(reqs) == 3
        ids = [r["id"] for r in reqs]
        assert ids == ["1", "2", "admin"]

    def test_sniper_multi_marker_same_list(self) -> None:
        """Sniper iterates over each unique marker in the template."""
        from theridion_sidecar.api.fuzzer import FuzzerConfig, PayloadPosition, _build_requests

        cfg = FuzzerConfig(
            url="http://example.com/§a§/§b§",
            method="GET",
            attack_mode="sniper",
            positions=[PayloadPosition(name="x", payloads=["p1", "p2"])],
        )
        reqs = _build_requests(cfg)
        # 2 markers × 2 payloads = 4 requests
        assert len(reqs) == 4

    def test_pitchfork(self) -> None:
        from theridion_sidecar.api.fuzzer import FuzzerConfig, PayloadPosition, _build_requests

        cfg = FuzzerConfig(
            url="http://example.com/§user§/§pass§",
            method="GET",
            attack_mode="pitchfork",
            positions=[
                PayloadPosition(name="user", payloads=["alice", "bob", "carol"]),
                PayloadPosition(name="pass", payloads=["pw1", "pw2"]),
            ],
        )
        reqs = _build_requests(cfg)
        # min(3, 2) = 2 requests
        assert len(reqs) == 2
        assert reqs[0] == {"user": "alice", "pass": "pw1"}
        assert reqs[1] == {"user": "bob", "pass": "pw2"}

    def test_cluster_bomb(self) -> None:
        from theridion_sidecar.api.fuzzer import FuzzerConfig, PayloadPosition, _build_requests

        cfg = FuzzerConfig(
            url="http://example.com/§a§/§b§",
            method="GET",
            attack_mode="cluster_bomb",
            positions=[
                PayloadPosition(name="a", payloads=["x", "y"]),
                PayloadPosition(name="b", payloads=["1", "2", "3"]),
            ],
        )
        reqs = _build_requests(cfg)
        # 2 × 3 = 6 requests
        assert len(reqs) == 6

    def test_sniper_with_no_markers_in_url(self) -> None:
        """If there are no §markers§ in the template, no requests are generated."""
        from theridion_sidecar.api.fuzzer import FuzzerConfig, PayloadPosition, _build_requests

        cfg = FuzzerConfig(
            url="http://example.com/plain",
            method="GET",
            attack_mode="sniper",
            positions=[PayloadPosition(name="x", payloads=["a", "b"])],
        )
        reqs = _build_requests(cfg)
        assert reqs == []


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


class TestFuzzerStart:
    def test_start_returns_run_id(self, client: TestClient) -> None:
        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get(url__startswith="http://fuzz-test.local/").mock(
                return_value=httpx.Response(200, text="ok")
            )
            resp = client.post(
                "/api/fuzzer/start",
                json={
                    "url": "http://fuzz-test.local/user/§id§",
                    "method": "GET",
                    "attack_mode": "sniper",
                    "positions": [{"name": "id", "payloads": ["1", "2"]}],
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["attack_mode"] == "sniper"
        assert data["total_requests"] == 2

    def test_start_invalid_no_positions(self, client: TestClient) -> None:
        resp = client.post(
            "/api/fuzzer/start",
            json={
                "url": "http://example.com/§x§",
                "method": "GET",
                "attack_mode": "sniper",
                "positions": [],
            },
        )
        assert resp.status_code == 422

    def test_start_payload_too_large(self, client: TestClient) -> None:
        """More than 1000 payloads should be rejected."""
        resp = client.post(
            "/api/fuzzer/start",
            json={
                "url": "http://example.com/§x§",
                "method": "GET",
                "attack_mode": "sniper",
                "positions": [{"name": "x", "payloads": [str(i) for i in range(1001)]}],
            },
        )
        assert resp.status_code == 422


class TestFuzzerResults:
    def test_results_accumulate_and_flagging(self, client: TestClient) -> None:
        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get(url__startswith="http://flagtest.local/").mock(
                return_value=httpx.Response(200, text="hello")
            )
            start_resp = client.post(
                "/api/fuzzer/start",
                json={
                    "url": "http://flagtest.local/§val§",
                    "method": "GET",
                    "attack_mode": "sniper",
                    "positions": [{"name": "val", "payloads": ["a", "b", "c"]}],
                    "concurrency": 1,
                },
            )
        assert start_resp.status_code == 200
        run_id = start_resp.json()["run_id"]

        # Wait a brief moment for async tasks
        import time
        time.sleep(0.3)

        results_resp = client.get(f"/api/fuzzer/runs/{run_id}/results")
        assert results_resp.status_code == 200
        results = results_resp.json()
        assert isinstance(results, list)

    def test_get_run_status(self, client: TestClient) -> None:
        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.post(url__startswith="http://runstatus.local/").mock(
                return_value=httpx.Response(500, text="err")
            )
            start_resp = client.post(
                "/api/fuzzer/start",
                json={
                    "url": "http://runstatus.local/§x§",
                    "method": "POST",
                    "attack_mode": "sniper",
                    "positions": [{"name": "x", "payloads": ["foo"]}],
                },
            )
        run_id = start_resp.json()["run_id"]
        status_resp = client.get(f"/api/fuzzer/runs/{run_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert "status" in data
        assert "total_requests" in data

    def test_run_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/fuzzer/runs/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_run(self, client: TestClient) -> None:
        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get(url__startswith="http://del-run.local/").mock(
                return_value=httpx.Response(200, text="ok")
            )
            start_resp = client.post(
                "/api/fuzzer/start",
                json={
                    "url": "http://del-run.local/§v§",
                    "method": "GET",
                    "attack_mode": "sniper",
                    "positions": [{"name": "v", "payloads": ["x"]}],
                },
            )
        run_id = start_resp.json()["run_id"]
        del_resp = client.delete(f"/api/fuzzer/runs/{run_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] == run_id
        # Should be gone now
        get_resp = client.get(f"/api/fuzzer/runs/{run_id}")
        assert get_resp.status_code == 404


class TestFuzzerSSE:
    def test_stream_route_registered(self, client: TestClient) -> None:
        from theridion_sidecar.main import create_app

        app = create_app()
        routes = [r.path for r in app.routes]  # type: ignore[attr-defined]
        assert "/api/fuzzer/stream" in routes


# ---------------------------------------------------------------------------
# Substitution helper tests
# ---------------------------------------------------------------------------


class TestSubstitution:
    def test_substitute_single(self) -> None:
        from theridion_sidecar.api.fuzzer import _substitute

        result = _substitute("hello §name§", {"name": "world"})
        assert result == "hello world"

    def test_substitute_missing_keeps_marker(self) -> None:
        from theridion_sidecar.api.fuzzer import _substitute

        result = _substitute("hello §name§", {})
        assert result == "hello §name§"

    def test_substitute_multiple(self) -> None:
        from theridion_sidecar.api.fuzzer import _substitute

        result = _substitute("§a§-§b§-§a§", {"a": "X", "b": "Y"})
        assert result == "X-Y-X"
