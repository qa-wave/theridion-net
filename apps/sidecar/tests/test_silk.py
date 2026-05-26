"""Tests for the Silk frontend-testing module (/api/silk/*).

Covers:
  - GET  /api/silk/browsers/check — happy path + missing cache
  - POST /api/silk/run            — spec_path + inline_code + validation errors
  - GET  /api/silk/trace/{id}     — 404 for unknown run, 400 for bad id
  - POST /api/silk/screenshot-diff — pixel diff math with synthetic images
  - POST /api/silk/auto-spec      — generated code structure
  - POST /api/silk/install-browsers/sync — npx absent path

Token auth is handled globally by conftest.py (_pin_sidecar_token + patched
TestClient.__init__), so individual tests do not need HEADERS dicts or env
patches.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """App client with isolated THERIDION_HOME."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# 1. Browser presence check
# ---------------------------------------------------------------------------


def test_check_browsers_no_cache(client: TestClient) -> None:
    """Returns 200 with installed bool when no ms-playwright dirs exist."""
    res = client.get("/api/silk/browsers/check")
    assert res.status_code == 200
    data = res.json()
    assert "installed" in data
    assert isinstance(data["paths"], list)


def test_check_browsers_with_cache(
    client: TestClient, tmp_path: Path
) -> None:
    """Returns installed=True when a chromium-* dir is present."""
    cache_dir = tmp_path / ".cache" / "ms-playwright" / "chromium-123"
    cache_dir.mkdir(parents=True)

    with patch("pathlib.Path.home", return_value=tmp_path):
        res = client.get("/api/silk/browsers/check")

    assert res.status_code == 200
    data = res.json()
    assert data["installed"] is True
    assert len(data["paths"]) >= 1


# ---------------------------------------------------------------------------
# 2. POST /api/silk/run
# ---------------------------------------------------------------------------


def test_run_requires_spec_or_code(client: TestClient) -> None:
    """Returns 400 when neither spec_path nor inline_code is provided."""
    res = client.post("/api/silk/run", json={})
    assert res.status_code == 400
    assert "spec_path" in res.json()["detail"] or "inline_code" in res.json()["detail"]


def test_run_spec_path_not_found(client: TestClient, tmp_path: Path) -> None:
    """Returns 404 when spec_path points to a missing file."""
    res = client.post(
        "/api/silk/run",
        json={"spec_path": str(tmp_path / "missing.spec.ts")},
    )
    assert res.status_code == 404


def test_run_npx_not_found(client: TestClient, tmp_path: Path) -> None:
    """Returns 400 when npx is not on PATH."""
    spec = tmp_path / "sample.spec.ts"
    spec.write_text("test('hi', () => {})", encoding="utf-8")

    with patch("shutil.which", return_value=None):
        res = client.post(
            "/api/silk/run",
            json={"spec_path": str(spec)},
        )

    assert res.status_code == 400
    assert "npx" in res.json()["detail"]


def test_run_inline_code_success(client: TestClient) -> None:
    """Inline code path writes temp file and returns a run result."""
    fake_json_report = {
        "stats": {"expected": 1, "unexpected": 0, "skipped": 0},
        "suites": [],
    }

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(fake_json_report)
    mock_result.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        res = client.post(
            "/api/silk/run",
            json={"inline_code": "import { test } from '@playwright/test';"},
        )

    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    assert data["exit_code"] == 0
    assert data["passed"] == 1
    assert data["failed"] == 0


def test_run_captures_failed_tests(client: TestClient, tmp_path: Path) -> None:
    """failed field reflects unexpected count from Playwright JSON report."""
    fake_report = {
        "stats": {"expected": 0, "unexpected": 2, "skipped": 0},
        "suites": [],
    }

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = json.dumps(fake_report)
    mock_result.stderr = "FAIL my.spec.ts"

    spec = tmp_path / "fail.spec.ts"
    spec.write_text("", encoding="utf-8")

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        res = client.post(
            "/api/silk/run",
            json={"spec_path": str(spec)},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["failed"] == 2
    assert data["exit_code"] == 1


def test_run_timeout_raises_504(client: TestClient, tmp_path: Path) -> None:
    """Returns 504 when the subprocess times out."""
    spec = tmp_path / "slow.spec.ts"
    spec.write_text("", encoding="utf-8")

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired("npx", 1)):
        res = client.post(
            "/api/silk/run",
            json={"spec_path": str(spec), "timeout_ms": 1000},
        )

    assert res.status_code == 504


# ---------------------------------------------------------------------------
# 3. GET /api/silk/trace/{run_id}
# ---------------------------------------------------------------------------


def test_trace_bad_run_id_path_traversal(client: TestClient) -> None:
    """Rejects run IDs that look like path traversal."""
    # The router will URL-encode or 404 depending on routing rules.
    res = client.get("/api/silk/trace/..%2Fetc%2Fpasswd")
    assert res.status_code in (400, 404, 422)


def test_trace_unknown_run(client: TestClient) -> None:
    """Returns 404 for a run ID that was never created."""
    res = client.get("/api/silk/trace/deadbeef00000000")
    assert res.status_code == 404


def test_trace_returns_zip(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Returns 200 + application/zip when a trace ZIP exists."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))

    from theridion_sidecar.api.silk import _run_dir

    run_id = "abc123"
    run_d = _run_dir(run_id)
    trace_dir = run_d / "traces"
    trace_dir.mkdir(parents=True)
    zip_file = trace_dir / "trace.zip"
    zip_file.write_bytes(b"PK")

    res = client.get(f"/api/silk/trace/{run_id}")
    assert res.status_code == 200
    assert "zip" in res.headers["content-type"]


# ---------------------------------------------------------------------------
# 4. POST /api/silk/screenshot-diff
# ---------------------------------------------------------------------------


def test_screenshot_diff_missing_file(client: TestClient) -> None:
    """Returns 404 when a path does not exist."""
    res = client.post(
        "/api/silk/screenshot-diff",
        json={
            "baseline_path": "/nonexistent/baseline.png",
            "current_path": "/nonexistent/current.png",
        },
    )
    assert res.status_code == 404


def test_screenshot_diff_identical_images(
    client: TestClient, tmp_path: Path
) -> None:
    """Identical images produce diff_ratio=0 and passed=True."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    img = Image.new("RGB", (100, 100), color=(128, 0, 0))
    baseline = tmp_path / "baseline.png"
    current = tmp_path / "current.png"
    img.save(str(baseline))
    img.save(str(current))

    res = client.post(
        "/api/silk/screenshot-diff",
        json={
            "baseline_path": str(baseline),
            "current_path": str(current),
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["pixel_diff_count"] == 0
    assert data["diff_ratio"] == 0.0
    assert data["passed"] is True


def test_screenshot_diff_different_images(
    client: TestClient, tmp_path: Path
) -> None:
    """Completely different images produce diff_ratio > 0."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    red = Image.new("RGB", (50, 50), color=(255, 0, 0))
    blue = Image.new("RGB", (50, 50), color=(0, 0, 255))
    baseline = tmp_path / "baseline.png"
    current = tmp_path / "current.png"
    red.save(str(baseline))
    blue.save(str(current))

    res = client.post(
        "/api/silk/screenshot-diff",
        json={"baseline_path": str(baseline), "current_path": str(current)},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["pixel_diff_count"] > 0
    assert data["diff_ratio"] > 0
    assert "diff_path" in data
    assert data["total_pixels"] == 50 * 50


def test_screenshot_diff_threshold_fail(
    client: TestClient, tmp_path: Path
) -> None:
    """passed=False when diff exceeds threshold."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    red = Image.new("RGB", (50, 50), color=(255, 0, 0))
    blue = Image.new("RGB", (50, 50), color=(0, 0, 255))
    baseline = tmp_path / "b.png"
    current = tmp_path / "c.png"
    red.save(str(baseline))
    blue.save(str(current))

    res = client.post(
        "/api/silk/screenshot-diff",
        json={
            "baseline_path": str(baseline),
            "current_path": str(current),
            "threshold": 0.0,
        },
    )

    assert res.status_code == 200
    assert res.json()["passed"] is False


# ---------------------------------------------------------------------------
# 5. POST /api/silk/auto-spec
# ---------------------------------------------------------------------------


def test_auto_spec_generates_file(client: TestClient, tmp_path: Path) -> None:
    """Generated spec contains the request ID and URL."""
    res = client.post(
        "/api/silk/auto-spec",
        json={
            "request_id": "req-001",
            "method": "POST",
            "url": "https://api.example.com/users",
            "headers": {"Content-Type": "application/json"},
            "body": '{"name": "Alice"}',
            "status_code": 201,
            "workspace_dir": str(tmp_path),
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert "spec_path" in data
    assert "spec_code" in data
    assert "req-001" in data["spec_code"]
    assert "https://api.example.com/users" in data["spec_code"]
    assert "201" in data["spec_code"]
    assert Path(data["spec_path"]).exists()


def test_auto_spec_no_workspace_uses_silk_dir(client: TestClient) -> None:
    """When workspace_dir is absent the spec goes into the silk home dir."""
    res = client.post(
        "/api/silk/auto-spec",
        json={
            "request_id": "req-002",
            "method": "GET",
            "url": "https://example.com/health",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert Path(data["spec_path"]).exists()
    assert "request.get(" in data["spec_code"]
    assert "toBeTruthy" in data["spec_code"]


# ---------------------------------------------------------------------------
# 6. POST /api/silk/install-browsers/sync
# ---------------------------------------------------------------------------


def test_install_browsers_sync_no_npx(client: TestClient) -> None:
    """Returns 400 when npx is absent."""
    with patch("shutil.which", return_value=None):
        res = client.post("/api/silk/install-browsers/sync")

    assert res.status_code == 400
    assert "npx" in res.json()["detail"]


def test_install_browsers_sync_failure(client: TestClient) -> None:
    """Returns 500 when playwright install exits non-zero."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "fatal error"

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        res = client.post("/api/silk/install-browsers/sync")

    assert res.status_code == 500


def test_install_browsers_sync_success(client: TestClient) -> None:
    """Returns ok=True when playwright install exits 0."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Chromium 123 downloaded to /home/user/.cache/ms-playwright/chromium-123"
    mock_result.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        res = client.post("/api/silk/install-browsers/sync")

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "chromium" in (data["browser_path"] or "").lower()
