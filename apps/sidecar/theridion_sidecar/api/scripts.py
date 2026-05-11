"""Pre-request script execution — run user JS in a sandboxed subprocess.

The script receives a `pm` object with environment variables and can
set/modify them. Communication is via stdin/stdout JSON.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/scripts", tags=["scripts"])


class ScriptInput(BaseModel):
    script: str = Field(..., min_length=1)
    variables: dict[str, str] = Field(default_factory=dict)
    request: dict[str, Any] = Field(default_factory=dict)


class ScriptOutput(BaseModel):
    success: bool
    variables: dict[str, str] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
    duration_ms: float = 0


WRAPPER_TEMPLATE = """
const input = JSON.parse(process.argv[1]);
const pm = {
  variables: new Map(Object.entries(input.variables || {})),
  request: input.request || {},
  logs: [],
  environment: {
    get: (key) => pm.variables.get(key) || '',
    set: (key, val) => pm.variables.set(key, String(val)),
    has: (key) => pm.variables.has(key),
  },
};
const console_log = console.log;
console.log = (...args) => pm.logs.push(args.map(String).join(' '));
try {
  %SCRIPT%
  const vars = {};
  pm.variables.forEach((v, k) => { vars[k] = v; });
  console_log(JSON.stringify({ success: true, variables: vars, logs: pm.logs }));
} catch (e) {
  console_log(JSON.stringify({ success: false, error: e.message, logs: pm.logs, variables: {} }));
}
"""


@router.post("/execute", response_model=ScriptOutput)
async def execute_script(body: ScriptInput) -> ScriptOutput:
    import time

    # Build the wrapper with user script embedded.
    wrapper = WRAPPER_TEMPLATE.replace("%SCRIPT%", body.script)

    input_data = json.dumps({
        "variables": body.variables,
        "request": body.request,
    })

    started = time.perf_counter()
    try:
        result = subprocess.run(
            ["node", "-e", wrapper, input_data],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=501,
            detail="Node.js not found — pre-request scripts require Node.js installed",
        )
    except subprocess.TimeoutExpired:
        return ScriptOutput(
            success=False,
            error="Script timed out (5s limit)",
            duration_ms=5000,
        )

    elapsed = (time.perf_counter() - started) * 1000

    if result.returncode != 0:
        return ScriptOutput(
            success=False,
            error=result.stderr.strip() or "Script failed",
            duration_ms=round(elapsed, 2),
        )

    try:
        output = json.loads(result.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return ScriptOutput(
            success=False,
            error=f"Invalid script output: {result.stdout[:200]}",
            duration_ms=round(elapsed, 2),
        )

    return ScriptOutput(
        success=output.get("success", False),
        variables=output.get("variables", {}),
        logs=output.get("logs", []),
        error=output.get("error"),
        duration_ms=round(elapsed, 2),
    )
