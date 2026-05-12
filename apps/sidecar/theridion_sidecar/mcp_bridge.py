"""MCP stdio bridge for Claude Desktop integration.

Reads JSON-RPC messages from stdin, proxies tool calls to the running
Theridion sidecar via HTTP, and writes JSON-RPC responses to stdout.

Usage::

    theridion-mcp

Or directly::

    python -m theridion_sidecar.mcp_bridge

The bridge expects a running sidecar. It discovers the port from the
sidecar PID file at $THERIDION_HOME/sidecar.pid, or falls back to
the THERIDION_PORT env var, or finally to 8765.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


def _discover_port() -> int:
    """Find the sidecar port from PID file, env var, or default."""
    # 1. Env var override.
    port_env = os.environ.get("THERIDION_PORT")
    if port_env:
        return int(port_env)

    # 2. PID file written by the sidecar.
    home = os.environ.get("THERIDION_HOME")
    home_path = Path(home).expanduser().resolve() if home else Path.home() / ".theridion"
    pid_file = home_path / "sidecar.pid"
    if pid_file.exists():
        try:
            content = pid_file.read_text().strip()
            # Format: "pid:port"
            _, port_str = content.split(":", 1)
            return int(port_str)
        except (ValueError, OSError):
            pass

    # 3. Default dev port.
    return 8765


def _base_url() -> str:
    port = _discover_port()
    return f"http://127.0.0.1:{port}"


def _read_message() -> dict[str, Any] | None:
    """Read a single JSON-RPC message from stdin.

    Supports both bare JSON lines and Content-Length framed messages
    (the MCP spec uses Content-Length framing).
    """
    # Try Content-Length header framing first.
    while True:
        line = sys.stdin.readline()
        if not line:
            return None  # EOF

        line = line.strip()
        if not line:
            continue

        # Content-Length header.
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
            # Skip blank line after header.
            sys.stdin.readline()
            data = sys.stdin.read(length)
            return json.loads(data)

        # Bare JSON line (for simpler transports).
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue


def _write_message(msg: dict[str, Any]) -> None:
    """Write a JSON-RPC message to stdout with Content-Length framing."""
    body = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(body)}\r\n\r\n{body}")
    sys.stdout.flush()


def _jsonrpc_response(id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _jsonrpc_error(id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _handle_initialize(msg: dict[str, Any]) -> dict[str, Any]:
    return _jsonrpc_response(msg.get("id"), {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {
            "name": "theridion",
            "version": "0.1.0",
        },
    })


def _handle_tools_list(msg: dict[str, Any], base_url: str) -> dict[str, Any]:
    try:
        resp = httpx.get(f"{base_url}/api/mcp/manifest", timeout=10)
        resp.raise_for_status()
        manifest = resp.json()
        tools = []
        for t in manifest.get("tools", []):
            tools.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "inputSchema": t.get("input_schema", {}),
            })
        return _jsonrpc_response(msg.get("id"), {"tools": tools})
    except Exception as exc:
        return _jsonrpc_error(msg.get("id"), -32603, f"Failed to fetch manifest: {exc}")


def _handle_tools_call(msg: dict[str, Any], base_url: str) -> dict[str, Any]:
    params = msg.get("params", {})
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    try:
        resp = httpx.post(
            f"{base_url}/api/mcp/invoke",
            json={"tool": tool_name, "arguments": arguments},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            return _jsonrpc_response(msg.get("id"), {
                "content": [{"type": "text", "text": f"Error: {data['error']}"}],
                "isError": True,
            })
        return _jsonrpc_response(msg.get("id"), {
            "content": [{"type": "text", "text": json.dumps(data.get("result", {}), indent=2)}],
        })
    except Exception as exc:
        return _jsonrpc_error(msg.get("id"), -32603, f"Tool call failed: {exc}")


def main() -> None:
    """Entry point for the MCP bridge."""
    base_url = _base_url()

    while True:
        msg = _read_message()
        if msg is None:
            break  # EOF

        method = msg.get("method", "")

        if method == "initialize":
            _write_message(_handle_initialize(msg))
        elif method == "notifications/initialized":
            # Client acknowledgement, no response needed.
            pass
        elif method == "tools/list":
            _write_message(_handle_tools_list(msg, base_url))
        elif method == "tools/call":
            _write_message(_handle_tools_call(msg, base_url))
        elif method == "ping":
            _write_message(_jsonrpc_response(msg.get("id"), {}))
        else:
            if "id" in msg:
                _write_message(_jsonrpc_error(
                    msg.get("id"), -32601, f"Method not found: {method}",
                ))


if __name__ == "__main__":
    main()
