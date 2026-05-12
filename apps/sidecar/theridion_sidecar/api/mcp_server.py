"""MCP server: expose Theridion capabilities as MCP-compatible tools.

Provides a manifest of available tools with JSON schemas and a real
invoke endpoint that dispatches to the underlying sidecar logic.
"""

from __future__ import annotations

import json
import traceback
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .. import environments, storage
from ..assertions import Assertion, ResponseData, evaluate_all
from ..soap import inspect_wsdl

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class McpTool(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = {}


class McpManifest(BaseModel):
    name: str = "theridion"
    version: str = "0.1.0"
    tools: list[McpTool] = []


class McpInvokeInput(BaseModel):
    tool: str
    arguments: dict[str, Any] = {}


class McpInvokeOutput(BaseModel):
    result: dict[str, Any] = {}
    error: str | None = None


_TOOLS = [
    McpTool(
        name="execute_request",
        description="Execute an HTTP request and return the response",
        input_schema={
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                    "default": "GET",
                },
                "url": {"type": "string", "description": "The request URL"},
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
                "query": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
                "body": {"type": ["string", "null"], "default": None},
                "timeout_seconds": {"type": "number", "default": 30},
                "follow_redirects": {"type": "boolean", "default": True},
                "environment_id": {"type": ["string", "null"], "default": None},
                "collection_id": {"type": ["string", "null"], "default": None},
            },
            "required": ["url"],
        },
    ),
    McpTool(
        name="list_collections",
        description="List all collections with their names and request counts",
        input_schema={"type": "object", "properties": {}},
    ),
    McpTool(
        name="get_collection",
        description="Get a collection by ID including all its requests and folders",
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Collection UUID"},
            },
            "required": ["id"],
        },
    ),
    McpTool(
        name="run_collection",
        description="Run all requests in a collection sequentially and return results",
        input_schema={
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "description": "Collection UUID"},
                "environment_id": {
                    "type": ["string", "null"],
                    "description": "Optional environment UUID for variable substitution",
                    "default": None,
                },
            },
            "required": ["collection_id"],
        },
    ),
    McpTool(
        name="evaluate_assertions",
        description="Evaluate a list of assertions against response data",
        input_schema={
            "type": "object",
            "properties": {
                "assertions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "status", "response_time", "json_path",
                                    "header_exists", "header_equals",
                                    "body_contains", "body_regex",
                                ],
                            },
                            "expected": {"type": "string", "default": ""},
                            "path": {"type": "string", "default": ""},
                            "operator": {"type": "string", "default": "eq"},
                        },
                        "required": ["type"],
                    },
                },
                "response": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "integer"},
                        "headers": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                        "body": {"type": "string"},
                        "elapsed_ms": {"type": "number"},
                    },
                    "required": ["status"],
                },
            },
            "required": ["assertions", "response"],
        },
    ),
    McpTool(
        name="list_environments",
        description="List all environments with variable counts",
        input_schema={"type": "object", "properties": {}},
    ),
    McpTool(
        name="inspect_wsdl",
        description="Inspect a WSDL document and return its services and operations",
        input_schema={
            "type": "object",
            "properties": {
                "wsdl_url": {
                    "type": "string",
                    "description": "URL or file path to the WSDL document",
                },
            },
            "required": ["wsdl_url"],
        },
    ),
    McpTool(
        name="graphql_introspect",
        description="Introspect a GraphQL endpoint and return its schema types",
        input_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "GraphQL endpoint URL",
                },
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
            },
            "required": ["url"],
        },
    ),
]


@router.get("/manifest", response_model=McpManifest)
async def get_manifest() -> McpManifest:
    return McpManifest(tools=_TOOLS)


@router.post("/invoke", response_model=McpInvokeOutput)
async def invoke_tool(body: McpInvokeInput) -> McpInvokeOutput:
    tool_names = {t.name for t in _TOOLS}
    if body.tool not in tool_names:
        return McpInvokeOutput(error=f"Unknown tool: {body.tool}")

    try:
        result = await _dispatch(body.tool, body.arguments)
        return McpInvokeOutput(result=result)
    except Exception as exc:
        return McpInvokeOutput(error=f"{type(exc).__name__}: {exc}")


async def _dispatch(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Route tool invocations to actual sidecar logic."""

    if tool == "execute_request":
        return await _execute_request(args)
    elif tool == "list_collections":
        return _list_collections()
    elif tool == "get_collection":
        return _get_collection(args)
    elif tool == "run_collection":
        return await _run_collection(args)
    elif tool == "evaluate_assertions":
        return _evaluate_assertions(args)
    elif tool == "list_environments":
        return _list_environments()
    elif tool == "inspect_wsdl":
        return _inspect_wsdl(args)
    elif tool == "graphql_introspect":
        return await _graphql_introspect(args)
    else:
        raise ValueError(f"No dispatch handler for tool: {tool}")


async def _execute_request(args: dict[str, Any]) -> dict[str, Any]:
    from .requests import ExecuteRequest, execute

    req = ExecuteRequest(
        method=args.get("method", "GET"),
        url=args["url"],
        headers=args.get("headers", {}),
        query=args.get("query", {}),
        body=args.get("body"),
        timeout_seconds=args.get("timeout_seconds", 30),
        follow_redirects=args.get("follow_redirects", True),
        environment_id=args.get("environment_id"),
        collection_id=args.get("collection_id"),
    )
    resp = await execute(req)
    return resp.model_dump(mode="json")


def _list_collections() -> dict[str, Any]:
    summaries = storage.list_summaries()
    return {"collections": [s.model_dump(mode="json") for s in summaries]}


def _get_collection(args: dict[str, Any]) -> dict[str, Any]:
    coll_id = args["id"]
    coll = storage.get(coll_id)
    if coll is None:
        raise ValueError(f"Collection {coll_id} not found")
    return coll.model_dump(mode="json")


async def _run_collection(args: dict[str, Any]) -> dict[str, Any]:
    from .runner import RunInput, run_collection

    result = await run_collection(
        collection_id=args["collection_id"],
        body=RunInput(environment_id=args.get("environment_id")),
    )
    return result.model_dump(mode="json")


def _evaluate_assertions(args: dict[str, Any]) -> dict[str, Any]:
    assertions = [Assertion(**a) for a in args["assertions"]]
    resp_data = args["response"]
    response = ResponseData(
        status=resp_data["status"],
        headers=resp_data.get("headers", {}),
        body=resp_data.get("body", ""),
        elapsed_ms=resp_data.get("elapsed_ms", 0),
    )
    results = evaluate_all(assertions, response)
    passed = sum(1 for r in results if r.passed)
    return {
        "results": [r.model_dump(mode="json") for r in results],
        "passed": passed,
        "failed": len(results) - passed,
        "total": len(results),
    }


def _list_environments() -> dict[str, Any]:
    summaries = environments.list_summaries()
    return {"environments": [s.model_dump(mode="json") for s in summaries]}


def _inspect_wsdl(args: dict[str, Any]) -> dict[str, Any]:
    summary = inspect_wsdl(args["wsdl_url"])
    return summary.model_dump(mode="json")


async def _graphql_introspect(args: dict[str, Any]) -> dict[str, Any]:
    from .graphql import IntrospectInput, introspect

    result = await introspect(
        IntrospectInput(
            url=args["url"],
            headers=args.get("headers", {}),
        )
    )
    return result.model_dump(mode="json")
