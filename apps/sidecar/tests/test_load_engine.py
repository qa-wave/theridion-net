"""Tests for the staged load engine.

Strategy:
- Unit-test internal logic (percentile, _percentile_sorted, LoadRunState) directly.
- Test the start endpoint model/validation at the HTTP layer.
- For runs that would run for real duration, cancel them immediately.
- The SSE stream route registration is verified without connecting.

We avoid waiting for stage durations to complete by immediately stopping runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_engine():
    import theridion_sidecar.api.load_engine as _eng

    _eng._runs.clear()
    _eng._subscribers.clear()
    yield
    for state in list(_eng._runs.values()):
        try:
            state.stop_event.set()
        except Exception:
            pass
    _eng._runs.clear()
    _eng._subscribers.clear()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Unit tests for internal logic (no network, no async)
# ---------------------------------------------------------------------------


class TestPercentileSorted:
    def test_empty(self) -> None:
        from theridion_sidecar.api.load_engine import _percentile_sorted

        assert _percentile_sorted([], 95) == 0.0

    def test_single_value(self) -> None:
        from theridion_sidecar.api.load_engine import _percentile_sorted

        assert _percentile_sorted([42.0], 95) == 42.0

    def test_p50_is_median(self) -> None:
        from theridion_sidecar.api.load_engine import _percentile_sorted

        data = sorted([10.0, 20.0, 30.0, 40.0, 50.0])
        assert _percentile_sorted(data, 50) == 30.0

    def test_p100_is_max(self) -> None:
        from theridion_sidecar.api.load_engine import _percentile_sorted

        data = sorted([1.0, 5.0, 10.0])
        assert _percentile_sorted(data, 100) == 10.0


class TestLoadRunState:
    def test_record_sample_increments_counters(self) -> None:
        from theridion_sidecar.api.load_engine import LoadEngineConfig, LoadRunState, LoadStage

        cfg = LoadEngineConfig(
            url="http://example.com/",
            stages=[LoadStage(target_vus=1, duration_s=1)],
        )
        state = LoadRunState("run-1", cfg)
        state.record_sample(50.0, None, second=0)
        state.record_sample(100.0, "ConnectError", second=0)

        assert state.total_requests == 2
        assert state.successful == 1
        assert state.failed == 1
        assert "ConnectError" in state.errors

    def test_percentile_computation(self) -> None:
        from theridion_sidecar.api.load_engine import LoadEngineConfig, LoadRunState, LoadStage

        cfg = LoadEngineConfig(
            url="http://example.com/",
            stages=[LoadStage(target_vus=1, duration_s=1)],
        )
        state = LoadRunState("run-2", cfg)
        for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
            state.record_sample(v, None, second=0)

        p50 = state.percentile(50)
        assert 20 <= p50 <= 40  # should be around 30

    def test_to_result_schema(self) -> None:
        from theridion_sidecar.api.load_engine import LoadEngineConfig, LoadRunState, LoadStage

        cfg = LoadEngineConfig(
            url="http://example.com/",
            stages=[LoadStage(target_vus=1, duration_s=1)],
        )
        state = LoadRunState("run-3", cfg)
        state.record_sample(100.0, None, second=0)
        state.status = "done"
        import time
        state.finished_at = time.time()
        result = state.to_result()

        assert result.run_id == "run-3"
        assert result.total_requests == 1
        assert result.successful == 1
        assert isinstance(result.timeline, list)
        assert result.p95_ms >= 0

    def test_timeline_buckets(self) -> None:
        from theridion_sidecar.api.load_engine import LoadEngineConfig, LoadRunState, LoadStage

        cfg = LoadEngineConfig(
            url="http://example.com/",
            stages=[LoadStage(target_vus=1, duration_s=5)],
        )
        state = LoadRunState("run-4", cfg)
        # Record samples at different seconds
        for sec in range(5):
            for _ in range(10):
                state.record_sample(float(sec * 10 + 5), None, second=sec)
        state.status = "done"
        import time
        state.finished_at = time.time()
        result = state.to_result()

        assert len(result.timeline) == 5
        assert all(pt.rps == 10 for pt in result.timeline)


# ---------------------------------------------------------------------------
# HTTP API validation tests (start + stop immediately)
# ---------------------------------------------------------------------------


class TestLoadEngineAPI:
    def test_start_returns_run_id(self, client: TestClient) -> None:
        resp = client.post(
            "/api/load-engine/start",
            json={
                "url": "http://127.0.0.1:1/noop",
                "stages": [{"target_vus": 1, "duration_s": 1, "ramp_up_s": 0}],
                "timeout_ms": 100,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        run_id = data["run_id"]
        # Immediately stop to not block teardown
        client.post(f"/api/load-engine/stop/{run_id}")
        assert data["total_stages"] == 1
        assert data["total_duration_s"] == 1

    def test_start_multi_stage_counts(self, client: TestClient) -> None:
        resp = client.post(
            "/api/load-engine/start",
            json={
                "url": "http://127.0.0.1:1/noop",
                "stages": [
                    {"target_vus": 2, "duration_s": 1, "ramp_up_s": 0},
                    {"target_vus": 5, "duration_s": 1, "ramp_up_s": 0},
                ],
                "timeout_ms": 100,
            },
        )
        run_id = resp.json()["run_id"]
        client.post(f"/api/load-engine/stop/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["total_stages"] == 2

    def test_start_invalid_no_stages(self, client: TestClient) -> None:
        resp = client.post(
            "/api/load-engine/start",
            json={"url": "http://example.com/", "stages": []},
        )
        assert resp.status_code == 422

    def test_start_stage_vu_over_limit(self, client: TestClient) -> None:
        resp = client.post(
            "/api/load-engine/start",
            json={
                "url": "http://example.com/",
                "stages": [{"target_vus": 1001, "duration_s": 1}],
            },
        )
        assert resp.status_code == 422

    def test_stop_run(self, client: TestClient) -> None:
        resp = client.post(
            "/api/load-engine/start",
            json={
                "url": "http://127.0.0.1:1/noop",
                "stages": [{"target_vus": 1, "duration_s": 1, "ramp_up_s": 0}],
                "timeout_ms": 100,
            },
        )
        run_id = resp.json()["run_id"]
        stop_resp = client.post(f"/api/load-engine/stop/{run_id}")
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] in ("stopped", "done", "running", "error")

    def test_get_run_result_schema(self, client: TestClient) -> None:
        resp = client.post(
            "/api/load-engine/start",
            json={
                "url": "http://127.0.0.1:1/noop",
                "stages": [{"target_vus": 1, "duration_s": 1, "ramp_up_s": 0}],
                "timeout_ms": 100,
            },
        )
        run_id = resp.json()["run_id"]
        client.post(f"/api/load-engine/stop/{run_id}")

        result_resp = client.get(f"/api/load-engine/runs/{run_id}")
        assert result_resp.status_code == 200
        data = result_resp.json()
        assert data["run_id"] == run_id
        assert "status" in data
        assert "total_requests" in data
        assert "p95_ms" in data
        assert "p50_ms" in data
        assert "p99_ms" in data
        assert isinstance(data["timeline"], list)

    def test_get_nonexistent_run(self, client: TestClient) -> None:
        resp = client.get("/api/load-engine/runs/nonexistent")
        assert resp.status_code == 404

    def test_stop_nonexistent_run(self, client: TestClient) -> None:
        resp = client.post("/api/load-engine/stop/nonexistent")
        assert resp.status_code == 404

    def test_list_runs(self, client: TestClient) -> None:
        run_ids: list[str] = []
        for _ in range(2):
            r = client.post(
                "/api/load-engine/start",
                json={
                    "url": "http://127.0.0.1:1/noop",
                    "stages": [{"target_vus": 1, "duration_s": 1}],
                    "timeout_ms": 100,
                },
            )
            run_ids.append(r.json()["run_id"])
        # Stop them all
        for rid in run_ids:
            client.post(f"/api/load-engine/stop/{rid}")
        resp = client.get("/api/load-engine/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) >= 2
        assert all("run_id" in r for r in runs)


class TestLoadEngineSSE:
    def test_stream_route_registered(self) -> None:
        from theridion_sidecar.main import create_app

        app = create_app()
        routes = [r.path for r in app.routes]  # type: ignore[attr-defined]
        assert "/api/load-engine/stream" in routes
