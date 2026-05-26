"""Silk — Frontend testing module (Playwright runner integration).

Provides four endpoints:
  POST /api/silk/install-browsers  — download Playwright Chromium (SSE stream)
  POST /api/silk/run               — execute a .spec.ts file via npx playwright
  GET  /api/silk/trace/{id}        — stream back a trace ZIP
  POST /api/silk/screenshot-diff   — pixel-diff two PNG images

All paths require X-Theridion-Token (enforced by main.py middleware).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .. import storage

router = APIRouter(prefix="/api/silk", tags=["silk"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SILK_DIR_NAME = "silk"


def _silk_dir() -> Path:
    """~/.theridion/silk/ — stores run artefacts and screenshots."""
    d = storage.home_dir() / _SILK_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_dir(run_id: str) -> Path:
    d = _silk_dir() / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _node_bin(name: str) -> str | None:
    """Return the absolute path of a node binary if resolvable."""
    return shutil.which(name)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class InstallBrowsersResponse(BaseModel):
    ok: bool
    message: str
    browser_path: str | None = None


class SilkRunInput(BaseModel):
    spec_path: str | None = Field(
        None,
        description="Absolute or workspace-relative path to a .spec.ts file.",
    )
    inline_code: str | None = Field(
        None,
        description="TypeScript spec source; written to a temp file when spec_path is absent.",
    )
    env_vars: dict[str, str] = Field(
        default_factory=dict,
        description="Extra environment variables injected into the subprocess.",
    )
    timeout_ms: int = Field(
        60_000,
        ge=1_000,
        le=600_000,
        description="Wall-clock timeout for the entire Playwright run (ms).",
    )
    workspace_dir: str | None = Field(
        None,
        description="Working directory for the npx call (must contain package.json with @playwright/test).",
    )


class SilkRunOutput(BaseModel):
    run_id: str
    exit_code: int
    passed: int
    failed: int
    errors: int
    duration_ms: int
    trace_path: str | None = None
    json_report: dict | None = None
    stderr_tail: str = ""


class ScreenshotDiffInput(BaseModel):
    baseline_path: str = Field(..., description="Absolute path to the baseline PNG.")
    current_path: str = Field(..., description="Absolute path to the current PNG.")
    threshold: float = Field(
        0.1,
        ge=0.0,
        le=1.0,
        description="Pixel-diff threshold as a fraction of total pixels (0–1).",
    )


class ScreenshotDiffOutput(BaseModel):
    diff_path: str
    pixel_diff_count: int
    total_pixels: int
    diff_ratio: float
    passed: bool


# ---------------------------------------------------------------------------
# 1. Install browsers (SSE stream)
# ---------------------------------------------------------------------------


@router.post("/install-browsers")
async def install_browsers() -> StreamingResponse:
    """Stream Playwright Chromium download progress via SSE.

    Each SSE event is ``data: <line>\\n\\n``.  The final event is
    ``data: DONE path=<path>\\n\\n`` on success or
    ``data: ERROR <message>\\n\\n`` on failure.
    """

    async def _stream() -> AsyncGenerator[str, None]:
        npx = _node_bin("npx")
        if not npx:
            yield "data: ERROR npx not found — install Node.js 18+\n\n"
            return

        yield "data: Starting Playwright Chromium install…\n\n"

        proc = await asyncio.create_subprocess_exec(
            npx,
            "playwright",
            "install",
            "chromium",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ},
        )

        assert proc.stdout is not None
        browser_path: str | None = None

        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if not line:
                continue
            yield f"data: {line}\n\n"
            # Playwright prints something like:
            # Chromium 123.0.6312.86 (playwright build 1097) downloaded to /path
            if "downloaded to" in line.lower() or "chromium" in line.lower():
                parts = line.split("downloaded to", 1)
                if len(parts) == 2:
                    browser_path = parts[1].strip()

        await proc.wait()

        if proc.returncode == 0:
            if not browser_path:
                # Try to detect the cache dir ourselves.
                cache_candidates = [
                    Path.home() / ".cache" / "ms-playwright",
                    Path.home() / "Library" / "Caches" / "ms-playwright",
                    Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")) if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else None,
                ]
                for c in cache_candidates:
                    if c and c.exists():
                        browser_path = str(c)
                        break
            yield f"data: DONE path={browser_path or 'unknown'}\n\n"
        else:
            yield f"data: ERROR exit code {proc.returncode}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Sync fallback for simple polling (not SSE).
@router.post("/install-browsers/sync", response_model=InstallBrowsersResponse)
def install_browsers_sync() -> InstallBrowsersResponse:
    """Blocking install — for clients that cannot handle SSE."""
    npx = _node_bin("npx")
    if not npx:
        raise HTTPException(400, detail="npx not found — install Node.js 18+")

    result = subprocess.run(
        [npx, "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ},
    )

    browser_path: str | None = None
    for line in result.stdout.splitlines():
        if "downloaded to" in line.lower():
            parts = line.split("downloaded to", 1)
            if len(parts) == 2:
                browser_path = parts[1].strip()
                break

    if result.returncode == 0:
        return InstallBrowsersResponse(
            ok=True,
            message="Chromium installed successfully",
            browser_path=browser_path,
        )

    raise HTTPException(
        500,
        detail=f"playwright install failed (exit {result.returncode}): {result.stderr[:500]}",
    )


# ---------------------------------------------------------------------------
# 2. Run a spec
# ---------------------------------------------------------------------------


@router.post("/run", response_model=SilkRunOutput)
def run_spec(body: SilkRunInput) -> SilkRunOutput:
    """Execute a Playwright .spec.ts via *npx playwright test*.

    Either ``spec_path`` (path to an existing file) or ``inline_code``
    (TypeScript source that will be written to a temp file) must be provided.

    Returns structured JSON from ``--reporter=json`` plus a path to the trace
    ZIP if Playwright produced one.
    """
    npx = _node_bin("npx")
    if not npx:
        raise HTTPException(400, detail="npx not found — install Node.js 18+")

    run_id = uuid.uuid4().hex
    run_d = _run_dir(run_id)
    tmp_file: Path | None = None

    try:
        # Resolve spec path.
        if body.spec_path:
            spec = Path(body.spec_path)
            if not spec.is_absolute() and body.workspace_dir:
                spec = Path(body.workspace_dir) / spec
            if not spec.exists():
                raise HTTPException(
                    404, detail=f"spec file not found: {spec}"
                )
            spec_path_str = str(spec)
        elif body.inline_code:
            tmp_file = run_d / "inline.spec.ts"
            tmp_file.write_text(body.inline_code, encoding="utf-8")
            spec_path_str = str(tmp_file)
        else:
            raise HTTPException(
                400, detail="provide either spec_path or inline_code"
            )

        json_report_path = run_d / "report.json"
        trace_dir = run_d / "traces"
        trace_dir.mkdir(exist_ok=True)

        env = {**os.environ, **body.env_vars}
        # Tell Playwright where to put traces.
        env["PLAYWRIGHT_TRACE_DEST"] = str(trace_dir)

        cmd = [
            npx,
            "playwright",
            "test",
            spec_path_str,
            "--reporter=json",
            f"--output={run_d / 'results'}",
        ]

        cwd = body.workspace_dir or str(run_d)

        start_ns = _monotonic_ns()
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=body.timeout_ms / 1000,
            env=env,
            cwd=cwd,
        )
        duration_ms = (_monotonic_ns() - start_ns) // 1_000_000

        # Parse the JSON written to stdout (Playwright json reporter outputs
        # to stdout; our custom path approach writes via env).
        json_report: dict | None = None
        passed = 0
        failed = 0
        errors = 0

        raw_out = proc.stdout.strip()
        if raw_out:
            # Playwright json reporter writes to stdout.
            # Strip any non-JSON preamble (e.g. deprecation warnings).
            json_start = raw_out.find("{")
            if json_start != -1:
                try:
                    json_report = json.loads(raw_out[json_start:])
                    stats = json_report.get("stats", {})
                    passed = stats.get("expected", 0)
                    failed = stats.get("unexpected", 0)
                    errors = stats.get("skipped", 0)
                except json.JSONDecodeError:
                    pass

        # Also save to disk for later retrieval.
        if json_report:
            json_report_path.write_text(json.dumps(json_report), encoding="utf-8")

        # Look for trace ZIP(s) produced by Playwright.
        trace_zips = list(trace_dir.rglob("*.zip"))
        trace_path: str | None = None
        if trace_zips:
            # Use the first (most likely there's only one per spec).
            trace_path = str(trace_zips[0])

        stderr_tail = "\n".join(proc.stderr.splitlines()[-20:]) if proc.stderr else ""

        return SilkRunOutput(
            run_id=run_id,
            exit_code=proc.returncode,
            passed=passed,
            failed=failed,
            errors=errors,
            duration_ms=duration_ms,
            trace_path=trace_path,
            json_report=json_report,
            stderr_tail=stderr_tail,
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(
            504,
            detail=f"spec run timed out after {body.timeout_ms} ms",
        )
    finally:
        if tmp_file and tmp_file.exists():
            # Keep inline spec for debugging; it lives in run_d which is
            # cleaned by the user or a future GC job.
            pass


def _monotonic_ns() -> int:
    import time
    return time.monotonic_ns()


# ---------------------------------------------------------------------------
# 3. Trace download
# ---------------------------------------------------------------------------


@router.get("/trace/{run_id}")
def get_trace(run_id: str) -> FileResponse:
    """Return the Playwright trace ZIP for a previous run.

    The trace can be opened with ``npx playwright show-trace <file>``.
    """
    # Basic path-traversal guard.
    if ".." in run_id or "/" in run_id or "\\" in run_id:
        raise HTTPException(400, detail="invalid run_id")

    run_d = _silk_dir() / "runs" / run_id
    if not run_d.exists():
        raise HTTPException(404, detail=f"run {run_id!r} not found")

    trace_zips = list(run_d.rglob("*.zip"))
    if not trace_zips:
        raise HTTPException(404, detail=f"no trace found for run {run_id!r}")

    zip_path = trace_zips[0]
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"trace-{run_id}.zip",
    )


# ---------------------------------------------------------------------------
# 4. Screenshot diff
# ---------------------------------------------------------------------------


@router.post("/screenshot-diff", response_model=ScreenshotDiffOutput)
def screenshot_diff(body: ScreenshotDiffInput) -> ScreenshotDiffOutput:
    """Compute a pixel diff between two PNG images using Pillow ImageChops.

    Returns the diff ratio, pixel count, a path to the diff PNG, and whether
    the diff is below *threshold*.
    """
    baseline_p = Path(body.baseline_path)
    current_p = Path(body.current_path)

    # Check existence before importing Pillow so 404 fires regardless.
    for p in (baseline_p, current_p):
        if not p.exists():
            raise HTTPException(404, detail=f"image not found: {p}")

    try:
        from PIL import Image, ImageChops, ImageFilter
    except ImportError:
        raise HTTPException(
            500,
            detail="Pillow is not installed — run: uv add pillow",
        )

    try:
        baseline_img = Image.open(baseline_p).convert("RGB")
        current_img = Image.open(current_p).convert("RGB")
    except Exception as exc:
        raise HTTPException(400, detail=f"could not open image: {exc}") from exc

    # Resize current to match baseline if dimensions differ.
    if baseline_img.size != current_img.size:
        current_img = current_img.resize(baseline_img.size, Image.LANCZOS)

    diff_img = ImageChops.difference(baseline_img, current_img)

    # Threshold the diff for pixel counting.
    diff_arr = diff_img.convert("L")
    # Any pixel with luminance > 10 counts as different.
    threshold_val = 10
    thresholded = diff_arr.point(lambda x: 255 if x > threshold_val else 0)

    pixel_diff_count = sum(1 for px in thresholded.getdata() if px > 0)
    total_pixels = baseline_img.width * baseline_img.height
    diff_ratio = pixel_diff_count / total_pixels if total_pixels > 0 else 0.0

    # Highlight diffs in red on a grey background.
    enhanced = diff_img.filter(ImageFilter.SHARPEN)
    diff_out_path = _silk_dir() / "diffs" / f"{uuid.uuid4().hex}.png"
    diff_out_path.parent.mkdir(parents=True, exist_ok=True)
    enhanced.save(str(diff_out_path))

    return ScreenshotDiffOutput(
        diff_path=str(diff_out_path),
        pixel_diff_count=pixel_diff_count,
        total_pixels=total_pixels,
        diff_ratio=round(diff_ratio, 6),
        passed=diff_ratio <= body.threshold,
    )


# ---------------------------------------------------------------------------
# 5. Browser presence check (lightweight)
# ---------------------------------------------------------------------------


class BrowserCheckOutput(BaseModel):
    installed: bool
    paths: list[str]


@router.get("/browsers/check", response_model=BrowserCheckOutput)
def check_browsers() -> BrowserCheckOutput:
    """Check if Playwright Chromium binaries are present in the local cache."""
    candidates = [
        Path.home() / ".cache" / "ms-playwright",
        Path.home() / "Library" / "Caches" / "ms-playwright",
    ]
    custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if custom:
        candidates.append(Path(custom))

    found: list[str] = []
    for c in candidates:
        if c.exists():
            # Check there's at least one chromium-* sub-dir.
            chromium_dirs = list(c.glob("chromium-*"))
            if chromium_dirs:
                found.extend(str(d) for d in chromium_dirs)

    return BrowserCheckOutput(installed=bool(found), paths=found)


# ---------------------------------------------------------------------------
# 6. Generate a starter spec from a Strand (collection request) failure
# ---------------------------------------------------------------------------


class AutoSpecInput(BaseModel):
    request_id: str = Field(..., description="ID of the failed Strand request.")
    method: str = Field("GET")
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    status_code: int | None = None
    workspace_dir: str | None = None


class AutoSpecOutput(BaseModel):
    spec_path: str
    spec_code: str


@router.post("/auto-spec", response_model=AutoSpecOutput)
def auto_spec(body: AutoSpecInput) -> AutoSpecOutput:
    """Generate a minimal Playwright spec that reproduces a failed Strand request.

    The generated file is written to:
      ``<workspace>/.theridion/silk/auto-generated/<request_id>.spec.ts``
    """
    headers_ts = "\n".join(
        f"      '{k}': '{v}'," for k, v in body.headers.items()
    )
    body_ts = ""
    if body.body:
        # Escape backticks to avoid breaking the template literal.
        escaped = body.body.replace("`", "\\`")
        body_ts = f"    body: `{escaped}`,"

    status_assert = ""
    if body.status_code:
        status_assert = (
            f"\n  expect(response.status()).toBe({body.status_code});"
        )

    spec_code = f"""\
import {{ test, expect }} from '@playwright/test';

// Auto-generated from Strand request {body.request_id!r}
// Reproduce the failed request and verify the response.

test('reproduce {body.request_id}', async ({{ request }}) => {{
  const response = await request.{body.method.lower()}('{body.url}', {{
    headers: {{
{headers_ts}
    }},
{body_ts}
  }});
{status_assert}
  // TODO: add your assertions here
  expect(response.ok()).toBeTruthy();
}});
"""

    if body.workspace_dir:
        out_dir = Path(body.workspace_dir) / ".theridion" / "silk" / "auto-generated"
    else:
        out_dir = _silk_dir() / "auto-generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    spec_path = out_dir / f"{body.request_id}.spec.ts"
    spec_path.write_text(spec_code, encoding="utf-8")

    return AutoSpecOutput(spec_path=str(spec_path), spec_code=spec_code)
