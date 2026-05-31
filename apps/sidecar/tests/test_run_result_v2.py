"""Tests for the RunResult v2 wrapper endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


class TestRunResultV2LoadConversion:
    def test_load_result_produces_valid_schema(self, client: TestClient) -> None:
        """A successful load run should produce schema_version=2 product=net."""
        resp = client.post(
            "/api/run-result/load",
            json={
                "total_requests": 1000,
                "successful": 990,
                "failed": 10,
                "errors": {"ConnectTimeout": 10},
                "avg_latency_ms": 120.5,
                "min_latency_ms": 10.0,
                "max_latency_ms": 800.0,
                "p50_ms": 100.0,
                "p75_ms": 150.0,
                "p90_ms": 200.0,
                "p95_ms": 300.0,
                "p99_ms": 500.0,
                "requests_per_second": 33.3,
                "duration_seconds": 30.0,
                "url": "https://api.example.com/health",
                "method": "GET",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        rr = data["run_result"]
        assert rr["schema_version"] == 2
        assert rr["product"] == "net"
        assert rr["suite_type"] == "load"
        assert rr["total"] == 1
        assert isinstance(rr["requests"], list)
        assert len(rr["requests"]) == 1
        assert "started_at" in rr
        assert "finished_at" in rr

    def test_load_result_pass_status_low_error_rate(self, client: TestClient) -> None:
        """Error rate < 5% → status=pass."""
        resp = client.post(
            "/api/run-result/load",
            json={
                "total_requests": 100,
                "successful": 97,
                "failed": 3,
                "errors": {},
                "avg_latency_ms": 100.0,
                "min_latency_ms": 10.0,
                "max_latency_ms": 500.0,
                "p50_ms": 90.0,
                "p75_ms": 120.0,
                "p90_ms": 180.0,
                "p95_ms": 250.0,
                "p99_ms": 400.0,
                "requests_per_second": 10.0,
                "duration_seconds": 10.0,
            },
        )
        assert resp.status_code == 200
        rr = resp.json()["run_result"]
        assert rr["requests"][0]["status"] == "pass"
        assert rr["passed"] == 1
        assert rr["failed"] == 0

    def test_load_result_fail_status_high_error_rate(self, client: TestClient) -> None:
        """Error rate >= 5% → status=fail."""
        resp = client.post(
            "/api/run-result/load",
            json={
                "total_requests": 100,
                "successful": 80,
                "failed": 20,
                "errors": {"ConnectionError": 20},
                "avg_latency_ms": 500.0,
                "min_latency_ms": 100.0,
                "max_latency_ms": 2000.0,
                "p50_ms": 400.0,
                "p75_ms": 700.0,
                "p90_ms": 900.0,
                "p95_ms": 1200.0,
                "p99_ms": 1800.0,
                "requests_per_second": 5.0,
                "duration_seconds": 20.0,
            },
        )
        assert resp.status_code == 200
        rr = resp.json()["run_result"]
        assert rr["requests"][0]["status"] == "fail"
        assert rr["failed"] == 1

    def test_load_result_no_hub_no_publish(self, client: TestClient) -> None:
        """Without hub_url/hub_token, published=False and no error."""
        resp = client.post(
            "/api/run-result/load",
            json={
                "total_requests": 50,
                "successful": 50,
                "failed": 0,
                "errors": {},
                "avg_latency_ms": 80.0,
                "min_latency_ms": 5.0,
                "max_latency_ms": 300.0,
                "p50_ms": 70.0,
                "p75_ms": 90.0,
                "p90_ms": 110.0,
                "p95_ms": 150.0,
                "p99_ms": 200.0,
                "requests_per_second": 25.0,
                "duration_seconds": 2.0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["published"] is False
        assert data["publish_error"] is None

    def test_load_result_run_id_is_uuid(self, client: TestClient) -> None:
        """run_id should be a valid UUID string."""
        import uuid

        resp = client.post(
            "/api/run-result/load",
            json={
                "total_requests": 10,
                "successful": 10,
                "failed": 0,
                "errors": {},
                "avg_latency_ms": 50.0,
                "min_latency_ms": 10.0,
                "max_latency_ms": 200.0,
                "p50_ms": 45.0,
                "p75_ms": 60.0,
                "p90_ms": 80.0,
                "p95_ms": 100.0,
                "p99_ms": 150.0,
                "requests_per_second": 5.0,
                "duration_seconds": 2.0,
            },
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_result"]["run_id"]
        # Should parse as UUID without raising
        uuid.UUID(run_id)


class TestRunResultV2SecurityConversion:
    def test_security_result_no_findings_pass(self, client: TestClient) -> None:
        """No findings → score=100, status=pass."""
        resp = client.post(
            "/api/run-result/security",
            json={
                "url": "https://api.example.com/login",
                "findings": [],
                "score": 100,
                "scan_types_run": ["sql_injection", "xss"],
                "elapsed_ms": 1500.0,
            },
        )
        assert resp.status_code == 200
        rr = resp.json()["run_result"]
        assert rr["schema_version"] == 2
        assert rr["product"] == "net"
        assert rr["suite_type"] == "security"
        assert rr["requests"][0]["status"] == "pass"

    def test_security_result_critical_finding_fail(self, client: TestClient) -> None:
        """Critical finding → status=fail for that request entry."""
        resp = client.post(
            "/api/run-result/security",
            json={
                "url": "https://api.example.com/search",
                "findings": [
                    {
                        "scan_type": "sql_injection",
                        "severity": "critical",
                        "title": "SQL error leaked",
                        "evidence": "payload: ' OR '1'='1",
                        "description": "SQL injection vulnerable endpoint",
                    }
                ],
                "score": 75,
                "scan_types_run": ["sql_injection"],
                "elapsed_ms": 800.0,
            },
        )
        assert resp.status_code == 200
        rr = resp.json()["run_result"]
        assert rr["failed"] == 1
        assert rr["requests"][0]["status"] == "fail"

    def test_security_result_info_finding_pass(self, client: TestClient) -> None:
        """Info-only finding → status=pass (not a vulnerability)."""
        resp = client.post(
            "/api/run-result/security",
            json={
                "url": "https://api.example.com/health",
                "findings": [
                    {
                        "scan_type": "rate_limit",
                        "severity": "info",
                        "title": "Rate limiting active",
                        "evidence": "429 returned on request 5",
                        "description": "Rate limiting is configured",
                    }
                ],
                "score": 95,
                "scan_types_run": ["rate_limit"],
                "elapsed_ms": 300.0,
            },
        )
        assert resp.status_code == 200
        rr = resp.json()["run_result"]
        assert rr["requests"][0]["status"] == "pass"

    def test_security_result_multiple_findings_counts(self, client: TestClient) -> None:
        """Multiple findings produce correct total/passed/failed counts."""
        resp = client.post(
            "/api/run-result/security",
            json={
                "url": "https://api.example.com/api",
                "findings": [
                    {
                        "scan_type": "xss",
                        "severity": "high",
                        "title": "XSS reflected",
                        "evidence": "<script>",
                        "description": "XSS",
                    },
                    {
                        "scan_type": "rate_limit",
                        "severity": "info",
                        "title": "Rate limiting active",
                        "evidence": "429 response",
                        "description": "OK",
                    },
                ],
                "score": 60,
                "scan_types_run": ["xss", "rate_limit"],
                "elapsed_ms": 1200.0,
            },
        )
        assert resp.status_code == 200
        rr = resp.json()["run_result"]
        assert rr["total"] == 2
        assert rr["failed"] == 1
        assert rr["passed"] == 1

    def test_security_result_no_hub_no_publish(self, client: TestClient) -> None:
        resp = client.post(
            "/api/run-result/security",
            json={
                "url": "https://api.example.com/test",
                "findings": [],
                "score": 100,
                "scan_types_run": [],
                "elapsed_ms": 100.0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["published"] is False
        assert data["publish_error"] is None


class TestRunResultV2HubPublish:
    def test_publish_fails_gracefully_on_bad_hub(self, client: TestClient) -> None:
        """Publishing to a non-existent hub returns published=False with error."""
        resp = client.post(
            "/api/run-result/load",
            json={
                "total_requests": 10,
                "successful": 10,
                "failed": 0,
                "errors": {},
                "avg_latency_ms": 50.0,
                "min_latency_ms": 5.0,
                "max_latency_ms": 200.0,
                "p50_ms": 45.0,
                "p75_ms": 60.0,
                "p90_ms": 80.0,
                "p95_ms": 100.0,
                "p99_ms": 150.0,
                "requests_per_second": 5.0,
                "duration_seconds": 2.0,
                "hub_url": "http://127.0.0.1:19999",
                "hub_token": "test-token",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Hub is not running — should fail gracefully
        assert data["published"] is False
        assert data["publish_error"] is not None
