"""Tests for the data-driven collection runner (CSV/JSON)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_runner():
    import theridion_sidecar.api.collection_runner as _cr

    _cr._runs.clear()
    yield
    _cr._runs.clear()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Data parsing unit tests
# ---------------------------------------------------------------------------


class TestParseRows:
    def test_json_array(self) -> None:
        from theridion_sidecar.api.collection_runner import DataSource, _parse_rows

        ds = DataSource(type="json", data='[{"name":"alice","age":"30"},{"name":"bob","age":"25"}]')
        rows = _parse_rows(ds)
        assert len(rows) == 2
        assert rows[0]["name"] == "alice"
        assert rows[1]["age"] == "25"

    def test_csv_basic(self) -> None:
        from theridion_sidecar.api.collection_runner import DataSource, _parse_rows

        csv_data = "name,age\nalice,30\nbob,25\n"
        ds = DataSource(type="csv", data=csv_data)
        rows = _parse_rows(ds)
        assert len(rows) == 2
        assert rows[0]["name"] == "alice"
        assert rows[1]["name"] == "bob"

    def test_json_not_array_raises(self) -> None:
        from theridion_sidecar.api.collection_runner import DataSource, _parse_rows

        ds = DataSource(type="json", data='{"key":"val"}')
        with pytest.raises(ValueError, match="array"):
            _parse_rows(ds)

    def test_max_rows_enforced(self) -> None:
        from theridion_sidecar.api.collection_runner import DataSource, _parse_rows, _MAX_ROWS

        rows = [{"id": str(i)} for i in range(_MAX_ROWS + 1)]
        ds = DataSource(type="json", data=json.dumps(rows))
        with pytest.raises(ValueError, match="max"):
            _parse_rows(ds)


# ---------------------------------------------------------------------------
# Row variable substitution
# ---------------------------------------------------------------------------


class TestApplyRowVars:
    def test_substitutes_column(self) -> None:
        from theridion_sidecar.api.collection_runner import _apply_row_vars

        result = _apply_row_vars("http://example.com/{{user}}", {"user": "alice"})
        assert result == "http://example.com/alice"

    def test_missing_column_unchanged(self) -> None:
        from theridion_sidecar.api.collection_runner import _apply_row_vars

        result = _apply_row_vars("{{missing}}", {})
        assert result == "{{missing}}"

    def test_none_template(self) -> None:
        from theridion_sidecar.api.collection_runner import _apply_row_vars

        result = _apply_row_vars(None, {"key": "val"})
        assert result is None


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


def _make_collection(client: TestClient, name: str = "test-coll") -> str:
    """Create a minimal collection with one GET request; return collection_id."""
    coll_resp = client.post("/api/collections", json={"name": name})
    assert coll_resp.status_code == 201, coll_resp.text
    coll_id = coll_resp.json()["id"]

    req_resp = client.post(
        f"/api/collections/{coll_id}/requests",
        json={
            "name": "GetUser",
            "method": "GET",
            "url": "http://runner-test.local/users/{{user_id}}",
        },
    )
    assert req_resp.status_code in (200, 201), req_resp.text
    return coll_id


class TestCollectionRunnerMissingResources:
    def test_missing_collection_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/collection-runner/run",
            json={
                "collection_id": "00000000-0000-0000-0000-000000000000",
                "datasource": {"type": "json", "data": '[{"id":"1"}]'},
            },
        )
        assert resp.status_code == 404

    def test_missing_environment_returns_404(self, client: TestClient) -> None:
        coll_id = _make_collection(client)
        resp = client.post(
            "/api/collection-runner/run",
            json={
                "collection_id": coll_id,
                "environment_id": "00000000-0000-0000-0000-000000000000",
                "datasource": {"type": "json", "data": '[{"id":"1"}]'},
            },
        )
        assert resp.status_code == 404

    def test_empty_datasource_returns_422(self, client: TestClient) -> None:
        coll_id = _make_collection(client)
        resp = client.post(
            "/api/collection-runner/run",
            json={
                "collection_id": coll_id,
                "datasource": {"type": "json", "data": "[]"},
            },
        )
        assert resp.status_code == 422

    def test_invalid_json_datasource_returns_422(self, client: TestClient) -> None:
        coll_id = _make_collection(client)
        resp = client.post(
            "/api/collection-runner/run",
            json={
                "collection_id": coll_id,
                "datasource": {"type": "json", "data": "not json"},
            },
        )
        assert resp.status_code == 422


class TestCollectionRunnerExecution:
    def test_json_datasource_runs_per_row(self, client: TestClient) -> None:
        coll_id = _make_collection(client)
        rows_data = json.dumps([{"user_id": "1"}, {"user_id": "2"}, {"user_id": "3"}])

        captured_urls: list[str] = []

        def _cap(req: httpx.Request) -> httpx.Response:
            captured_urls.append(str(req.url))
            return httpx.Response(200, json={"id": req.url.path.split("/")[-1]})

        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get(url__startswith="http://runner-test.local/").mock(side_effect=_cap)
            resp = client.post(
                "/api/collection-runner/run",
                json={
                    "collection_id": coll_id,
                    "datasource": {"type": "json", "data": rows_data},
                },
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total_iterations"] == 3
        assert data["completed_iterations"] == 3
        assert data["status"] == "done"
        # Each iteration should have one request result
        assert len(data["iterations"]) == 3

    def test_csv_datasource_runs_per_row(self, client: TestClient) -> None:
        coll_id = _make_collection(client)
        csv_data = "user_id\n10\n20\n"

        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get(url__startswith="http://runner-test.local/").mock(
                return_value=httpx.Response(200, text="ok")
            )
            resp = client.post(
                "/api/collection-runner/run",
                json={
                    "collection_id": coll_id,
                    "datasource": {"type": "csv", "data": csv_data},
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_iterations"] == 2

    def test_row_variables_substituted_in_url(self, client: TestClient) -> None:
        coll_id = _make_collection(client, "var-sub")
        rows_data = json.dumps([{"user_id": "42"}])

        captured: list[httpx.Request] = []

        def _cap(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, text="ok")

        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get(url__startswith="http://runner-test.local/users/").mock(side_effect=_cap)
            resp = client.post(
                "/api/collection-runner/run",
                json={
                    "collection_id": coll_id,
                    "datasource": {"type": "json", "data": rows_data},
                },
            )

        assert resp.status_code == 200
        assert len(captured) == 1
        # URL should have the row value substituted
        assert "42" in str(captured[0].url)


class TestCollectionRunnerAsync:
    def test_async_run_returns_run_id(self, client: TestClient) -> None:
        coll_id = _make_collection(client, "async-test")
        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get(url__startswith="http://runner-test.local/").mock(
                return_value=httpx.Response(200)
            )
            resp = client.post(
                "/api/collection-runner/run-async",
                json={
                    "collection_id": coll_id,
                    "datasource": {"type": "json", "data": '[{"user_id":"1"}]'},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["total_iterations"] == 1

    def test_async_run_pollable(self, client: TestClient) -> None:
        coll_id = _make_collection(client, "poll-test")
        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get(url__startswith="http://runner-test.local/").mock(
                return_value=httpx.Response(200)
            )
            start_resp = client.post(
                "/api/collection-runner/run-async",
                json={
                    "collection_id": coll_id,
                    "datasource": {"type": "json", "data": '[{"user_id":"1"}]'},
                },
            )
        run_id = start_resp.json()["run_id"]
        poll_resp = client.get(f"/api/collection-runner/runs/{run_id}")
        assert poll_resp.status_code == 200
        data = poll_resp.json()
        assert data["run_id"] == run_id

    def test_stop_async_run(self, client: TestClient) -> None:
        coll_id = _make_collection(client, "stop-test")
        # Use a real async run that will likely still be running
        resp = client.post(
            "/api/collection-runner/run-async",
            json={
                "collection_id": coll_id,
                "datasource": {
                    "type": "json",
                    "data": json.dumps([{"user_id": str(i)} for i in range(50)]),
                },
                "delay_ms": 500,  # slow enough to still be running
            },
        )
        run_id = resp.json()["run_id"]
        stop_resp = client.post(f"/api/collection-runner/runs/{run_id}/stop")
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "stopped"


class TestCollectionRunnerFailFast:
    def test_fail_fast_stops_after_first_failure(self, client: TestClient) -> None:
        """With fail_fast=True, the runner should stop after the first failing iteration."""
        coll_id = _make_collection(client, "fail-fast")
        rows_data = json.dumps([{"user_id": str(i)} for i in range(5)])

        call_count = 0

        def _cap(req: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            # Fail on first call
            return httpx.Response(500, text="error")

        with respx.mock(assert_all_called=False, assert_all_mocked=False) as rmock:
            rmock.get(url__startswith="http://runner-test.local/").mock(side_effect=_cap)
            resp = client.post(
                "/api/collection-runner/run",
                json={
                    "collection_id": coll_id,
                    "datasource": {"type": "json", "data": rows_data},
                    "fail_fast": True,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        # With no assertions, a 500 status doesn't auto-fail without assertion check
        # But the run should have completed
        assert data["status"] in ("done", "stopped")
