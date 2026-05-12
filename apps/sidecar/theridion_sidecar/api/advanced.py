"""Advanced API lifecycle endpoints.

This module keeps the heavier "platform" features behind narrow HTTP
contracts: OpenAPI import/export/contract checks, examples, vault,
dependency graphing, flows, snapshots, HAR, TLS inspection, proxy
recording, collection-backed mocks, and git-aware review summaries.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import os
import re
import socket
import ssl
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx
import uvicorn
import yaml
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import APIRouter, HTTPException
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .. import environments, storage
from .. import globals as global_store
from ..assertions import Assertion, AssertionResult, ResponseData, evaluate_all
from ..models import (
    AuthConfig,
    Collection,
    CollectionItem,
    HttpMethod,
    RequestCapture,
    RequestExample,
)
from .requests import _apply_auth

router = APIRouter(prefix="/api/advanced", tags=["advanced"])

HTTP_METHODS: set[str] = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
JSON_MEDIA_TYPES = ("application/json", "application/problem+json", "*/*")
VAR_PATTERN = re.compile(r"\{\{\s*(\$?[A-Za-z_][A-Za-z0-9_-]*)\s*\}\}")


class OpenApiImportInput(BaseModel):
    content: str = Field(..., min_length=1)
    format: Literal["auto", "json", "yaml"] = "auto"
    collection_name: str | None = None
    base_url: str | None = None


class OpenApiImportOutput(BaseModel):
    collection_id: str
    collection_name: str
    request_count: int


class OpenApiExportOutput(BaseModel):
    openapi: dict[str, Any]


class ContractValidateInput(BaseModel):
    openapi_content: str = Field(..., min_length=1)
    method: HttpMethod
    path: str
    status: int = 200
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""


class ContractViolation(BaseModel):
    path: str
    message: str


class ContractValidateOutput(BaseModel):
    passed: bool
    operation_id: str | None = None
    expected_statuses: list[str] = Field(default_factory=list)
    violations: list[ContractViolation] = Field(default_factory=list)


class ObservedResponse(BaseModel):
    method: HttpMethod
    path: str
    status: int
    body: str = ""
    headers: dict[str, str] = Field(default_factory=dict)


class ContractDriftInput(BaseModel):
    openapi_content: str = Field(..., min_length=1)
    collection_id: str | None = None
    observed: list[ObservedResponse] = Field(default_factory=list)


class ContractDriftOutput(BaseModel):
    missing_in_collection: list[str] = Field(default_factory=list)
    undocumented_requests: list[str] = Field(default_factory=list)
    failing_observations: list[ContractValidateOutput] = Field(default_factory=list)
    passed_observations: int = 0


def _parse_structured_content(content: str, fmt: str = "auto") -> dict[str, Any]:
    try:
        if fmt == "json":
            data = json.loads(content)
        elif fmt == "yaml":
            data = yaml.safe_load(content)
        else:
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = yaml.safe_load(content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid structured document: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="document root must be an object")
    return data


def _openapi_base_url(doc: dict[str, Any], override: str | None = None) -> str:
    if override:
        return override.rstrip("/")
    servers = doc.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and isinstance(first.get("url"), str):
            return str(first["url"]).rstrip("/")
    return ""


def _iter_openapi_operations(
    doc: dict[str, Any],
) -> list[tuple[str, str, dict[str, Any]]]:
    paths = doc.get("paths")
    if not isinstance(paths, dict):
        return []
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            upper = str(method).upper()
            if upper in HTTP_METHODS and isinstance(operation, dict):
                operations.append((upper, path, operation))
    return operations


def _operation_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def _resolve_ref(doc: dict[str, Any], node: Any) -> Any:
    if not isinstance(node, dict) or "$ref" not in node:
        return node
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return node
    current: Any = doc
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return node
    return _resolve_ref(doc, current)


def _media_object(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    for media_type in JSON_MEDIA_TYPES:
        media = content.get(media_type)
        if isinstance(media, dict):
            return media
    for media in content.values():
        if isinstance(media, dict):
            return media
    return None


def _schema_for_response(
    doc: dict[str, Any], operation: dict[str, Any], status: int
) -> dict[str, Any] | None:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return None
    response_obj = (
        responses.get(str(status))
        or responses.get(f"{status // 100}XX")
        or responses.get(f"{status // 100}xx")
        or responses.get("default")
    )
    response_obj = _resolve_ref(doc, response_obj)
    if not isinstance(response_obj, dict):
        return None
    media = _media_object(response_obj.get("content"))
    schema = _resolve_ref(doc, media.get("schema")) if media else None
    return schema if isinstance(schema, dict) else None


def _expected_statuses(operation: dict[str, Any]) -> list[str]:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return []
    return sorted(str(k) for k in responses)


def _path_to_regex(openapi_path: str) -> re.Pattern[str]:
    escaped = re.escape(openapi_path)
    pattern = re.sub(r"\\\{[^}/]+\\\}", r"[^/]+", escaped)
    return re.compile(f"^{pattern}$")


def _find_operation(
    doc: dict[str, Any], method: str, path: str
) -> tuple[str, dict[str, Any]] | None:
    for op_method, op_path, operation in _iter_openapi_operations(doc):
        if op_method != method.upper():
            continue
        if op_path == path or _path_to_regex(op_path).match(path):
            return op_path, operation
    return None


def _sample_for_schema(doc: dict[str, Any], schema: Any) -> Any:
    schema = _resolve_ref(doc, schema)
    if not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        props = schema.get("properties")
        if not isinstance(props, dict):
            return {}
        return {str(k): _sample_for_schema(doc, v) for k, v in props.items()}
    if schema_type == "array":
        return [_sample_for_schema(doc, schema.get("items", {}))]
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    return "string"


def _request_body_example(doc: dict[str, Any], operation: dict[str, Any]) -> str | None:
    request_body = _resolve_ref(doc, operation.get("requestBody"))
    if not isinstance(request_body, dict):
        return None
    media = _media_object(request_body.get("content"))
    if not media:
        return None
    if "example" in media:
        return json.dumps(media["example"], indent=2)
    examples = media.get("examples")
    if isinstance(examples, dict) and examples:
        first = next(iter(examples.values()))
        first = _resolve_ref(doc, first)
        if isinstance(first, dict) and "value" in first:
            return json.dumps(first["value"], indent=2)
    schema = media.get("schema")
    sample = _sample_for_schema(doc, schema)
    return json.dumps(sample, indent=2) if sample is not None else None


def _parameters_for_operation(operation: dict[str, Any]) -> list[dict[str, Any]]:
    params = operation.get("parameters")
    return [p for p in params if isinstance(p, dict)] if isinstance(params, list) else []


def _request_url(base_url: str, path: str, operation: dict[str, Any]) -> str:
    url_path = re.sub(r"\{([^}/]+)\}", r"{{\1}}", path)
    query_params: list[tuple[str, str]] = []
    for param in _parameters_for_operation(operation):
        if param.get("in") == "query" and isinstance(param.get("name"), str):
            query_params.append((str(param["name"]), f"{{{{{param['name']}}}}}"))
    query = urlencode(query_params)
    return f"{base_url}{url_path}{'?' + query if query else ''}"


def _operation_to_item(
    doc: dict[str, Any], base_url: str, method: str, path: str, operation: dict[str, Any]
) -> CollectionItem:
    summary = operation.get("summary") or operation.get("operationId")
    name = str(summary or _operation_key(method, path))
    body = _request_body_example(doc, operation)
    headers = {"content-type": "application/json"} if body else {}
    return CollectionItem(
        id=str(uuid.uuid4()),
        name=name,
        method=method,  # type: ignore[arg-type]
        url=_request_url(base_url, path, operation),
        headers=headers,
        body=body,
    )


def _count_requests(items: list[CollectionItem]) -> int:
    total = 0
    for item in items:
        total += _count_requests(item.items) if item.is_folder else 1
    return total


def _flatten_requests(items: list[CollectionItem]) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    for item in items:
        if item.is_folder:
            out.extend(_flatten_requests(item.items))
        else:
            out.append(item)
    return out


def _find_item(items: list[CollectionItem], item_id: str) -> CollectionItem | None:
    for item in items:
        if item.id == item_id:
            return item
        if item.is_folder:
            found = _find_item(item.items, item_id)
            if found is not None:
                return found
    return None


@router.post("/openapi/import", response_model=OpenApiImportOutput)
def import_openapi(body: OpenApiImportInput) -> OpenApiImportOutput:
    doc = _parse_structured_content(body.content, body.format)
    if "openapi" not in doc and "swagger" not in doc:
        raise HTTPException(status_code=400, detail="document is not an OpenAPI/Swagger spec")
    base_url = _openapi_base_url(doc, body.base_url)
    items = [
        _operation_to_item(doc, base_url, method, path, operation)
        for method, path, operation in _iter_openapi_operations(doc)
    ]
    info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
    name = body.collection_name or str(info.get("title") or "OpenAPI import")
    coll = Collection(id=str(uuid.uuid4()), name=name, version=1, items=items)
    storage._atomic_write(coll)
    return OpenApiImportOutput(
        collection_id=coll.id,
        collection_name=coll.name,
        request_count=_count_requests(coll.items),
    )


@router.get("/openapi/export/{collection_id}", response_model=OpenApiExportOutput)
def export_openapi(collection_id: str) -> OpenApiExportOutput:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    paths: dict[str, dict[str, Any]] = {}
    for req in _flatten_requests(coll.items):
        if not req.url or not req.method:
            continue
        parsed = urlsplit(req.url)
        path = parsed.path or "/"
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key and f"{{{{{key}}}}}" in value:
                pass
        path = re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}", r"{\1}", path)
        operation: dict[str, Any] = {
            "summary": req.name,
            "responses": {"200": {"description": "OK"}},
        }
        if req.body:
            operation["requestBody"] = {
                "content": {
                    "application/json": {
                        "example": _json_or_text(req.body),
                    }
                }
            }
        paths.setdefault(path, {})[req.method.lower()] = operation
    return OpenApiExportOutput(
        openapi={
            "openapi": "3.1.0",
            "info": {"title": coll.name, "version": "1.0.0"},
            "paths": paths,
        }
    )


def _json_or_text(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


@router.post("/contracts/validate", response_model=ContractValidateOutput)
def validate_contract(body: ContractValidateInput) -> ContractValidateOutput:
    doc = _parse_structured_content(body.openapi_content)
    found = _find_operation(doc, body.method, body.path)
    if found is None:
        return ContractValidateOutput(
            passed=False,
            violations=[ContractViolation(path="$", message="operation is not documented")],
        )
    openapi_path, operation = found
    expected = _expected_statuses(operation)
    if str(body.status) not in expected and "default" not in expected:
        return ContractValidateOutput(
            passed=False,
            operation_id=operation.get("operationId"),
            expected_statuses=expected,
            violations=[
                ContractViolation(
                    path="$status",
                    message=f"status {body.status} is not one of {', '.join(expected)}",
                )
            ],
        )
    schema = _schema_for_response(doc, operation, body.status)
    if schema is None:
        return ContractValidateOutput(
            passed=True,
            operation_id=operation.get("operationId") or _operation_key(body.method, openapi_path),
            expected_statuses=expected,
        )
    try:
        payload = json.loads(body.body) if body.body else None
    except json.JSONDecodeError as exc:
        return ContractValidateOutput(
            passed=False,
            operation_id=operation.get("operationId"),
            expected_statuses=expected,
            violations=[ContractViolation(path="$body", message=f"invalid JSON: {exc}")],
        )
    try:
        validator = Draft202012Validator(schema)
        violations = [
            ContractViolation(
                path="$" + "".join(f".{p}" for p in error.absolute_path),
                message=error.message,
            )
            for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        ]
    except SchemaError as exc:
        violations = [ContractViolation(path="$schema", message=str(exc))]
    return ContractValidateOutput(
        passed=len(violations) == 0,
        operation_id=operation.get("operationId") or _operation_key(body.method, openapi_path),
        expected_statuses=expected,
        violations=violations,
    )


@router.post("/contracts/drift", response_model=ContractDriftOutput)
def detect_contract_drift(body: ContractDriftInput) -> ContractDriftOutput:
    doc = _parse_structured_content(body.openapi_content)
    documented = {_operation_key(method, path) for method, path, _ in _iter_openapi_operations(doc)}
    collection_keys: set[str] = set()
    if body.collection_id:
        coll = storage.get(body.collection_id)
        if coll is None:
            raise HTTPException(status_code=404, detail="collection not found")
        for req in _flatten_requests(coll.items):
            if req.method and req.url:
                path = re.sub(
                    r"\{\{\s*([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}",
                    r"{\1}",
                    urlsplit(req.url).path or "/",
                )
                collection_keys.add(_operation_key(req.method, path))
    failing: list[ContractValidateOutput] = []
    passed = 0
    for observed in body.observed:
        result = validate_contract(
            ContractValidateInput(
                openapi_content=body.openapi_content,
                method=observed.method,
                path=observed.path,
                status=observed.status,
                headers=observed.headers,
                body=observed.body,
            )
        )
        if result.passed:
            passed += 1
        else:
            failing.append(result)
    return ContractDriftOutput(
        missing_in_collection=sorted(documented - collection_keys) if body.collection_id else [],
        undocumented_requests=sorted(collection_keys - documented) if body.collection_id else [],
        failing_observations=failing,
        passed_observations=passed,
    )


# ---- Request examples -----------------------------------------------------


class RequestExampleInput(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1)
    method: HttpMethod = "GET"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None
    notes: str | None = None


class UpdateExamplesInput(BaseModel):
    examples: list[RequestExampleInput] = Field(default_factory=list)


@router.patch(
    "/collections/{collection_id}/requests/{request_id}/examples",
    response_model=Collection,
)
def update_request_examples(
    collection_id: str, request_id: str, body: UpdateExamplesInput
) -> Collection:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    item = _find_item(coll.items, request_id)
    if item is None or item.is_folder:
        raise HTTPException(status_code=404, detail="request not found")
    item.examples = [
        RequestExample(id=example.id or str(uuid.uuid4()), **example.model_dump(exclude={"id"}))
        for example in body.examples
    ]
    storage._atomic_write(coll)
    return coll


# ---- Secrets vault --------------------------------------------------------


class VaultEntrySummary(BaseModel):
    name: str
    updated_at: str


class VaultListOutput(BaseModel):
    entries: list[VaultEntrySummary]


class VaultWriteInput(BaseModel):
    passphrase: str = Field(..., min_length=8)
    value: str


class VaultRevealInput(BaseModel):
    passphrase: str = Field(..., min_length=8)


class VaultRevealOutput(BaseModel):
    name: str
    value: str


def _vault_path() -> Path:
    path = storage.home_dir() / "vault.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_vault() -> dict[str, Any]:
    path = _vault_path()
    if not path.exists():
        return {"version": 1, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "entries": {}}
    return data if isinstance(data, dict) else {"version": 1, "entries": {}}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{uuid.uuid4()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _vault_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _safe_secret_name(name: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$", name):
        raise HTTPException(status_code=400, detail="invalid secret name")
    return name


@router.get("/secrets", response_model=VaultListOutput)
def list_secrets() -> VaultListOutput:
    vault = _load_vault()
    entries = vault.get("entries") if isinstance(vault.get("entries"), dict) else {}
    return VaultListOutput(
        entries=[
            VaultEntrySummary(name=name, updated_at=str(data.get("updated_at", "")))
            for name, data in sorted(entries.items())
            if isinstance(data, dict)
        ]
    )


@router.put("/secrets/{name}", response_model=VaultEntrySummary)
def write_secret(name: str, body: VaultWriteInput) -> VaultEntrySummary:
    safe_name = _safe_secret_name(name)
    salt = os.urandom(16)
    token = Fernet(_vault_key(body.passphrase, salt)).encrypt(body.value.encode("utf-8"))
    vault = _load_vault()
    entries = vault.setdefault("entries", {})
    if not isinstance(entries, dict):
        entries = {}
        vault["entries"] = entries
    updated_at = datetime.now(tz=UTC).isoformat()
    entries[safe_name] = {
        "salt": base64.b64encode(salt).decode("ascii"),
        "token": token.decode("ascii"),
        "updated_at": updated_at,
    }
    _write_json_atomic(_vault_path(), vault)
    return VaultEntrySummary(name=safe_name, updated_at=updated_at)


@router.post("/secrets/{name}/reveal", response_model=VaultRevealOutput)
def reveal_secret(name: str, body: VaultRevealInput) -> VaultRevealOutput:
    safe_name = _safe_secret_name(name)
    vault = _load_vault()
    entries = vault.get("entries") if isinstance(vault.get("entries"), dict) else {}
    entry = entries.get(safe_name) if isinstance(entries, dict) else None
    if not isinstance(entry, dict):
        raise HTTPException(status_code=404, detail="secret not found")
    try:
        salt = base64.b64decode(str(entry["salt"]))
        token = str(entry["token"]).encode("ascii")
        value = Fernet(_vault_key(body.passphrase, salt)).decrypt(token).decode("utf-8")
    except (KeyError, InvalidToken, ValueError) as exc:
        raise HTTPException(status_code=403, detail="could not decrypt secret") from exc
    return VaultRevealOutput(name=safe_name, value=value)


@router.delete("/secrets/{name}", status_code=204)
def delete_secret(name: str) -> None:
    safe_name = _safe_secret_name(name)
    vault = _load_vault()
    entries = vault.get("entries") if isinstance(vault.get("entries"), dict) else {}
    if not isinstance(entries, dict) or safe_name not in entries:
        raise HTTPException(status_code=404, detail="secret not found")
    del entries[safe_name]
    _write_json_atomic(_vault_path(), vault)


# ---- Variable resolution inspector ---------------------------------------


class VariableInspectInput(BaseModel):
    text: str
    environment_id: str | None = None
    collection_id: str | None = None
    runtime: dict[str, str] = Field(default_factory=dict)


class VariableResolution(BaseModel):
    name: str
    source: Literal["runtime", "environment", "collection", "global", "builtin", "unresolved"]
    value: str | None = None
    resolved: bool


class VariableInspectOutput(BaseModel):
    resolved_text: str
    variables: list[VariableResolution]


def _builtin_preview(name: str) -> str | None:
    if name == "$timestamp":
        return str(int(datetime.now(tz=UTC).timestamp() * 1000))
    if name == "$isoDate":
        return datetime.now(tz=UTC).isoformat()
    if name == "$uuid":
        return str(uuid.uuid4())
    if name == "$randomInt":
        return "0..1000000"
    return None


@router.post("/variables/inspect", response_model=VariableInspectOutput)
def inspect_variables(body: VariableInspectInput) -> VariableInspectOutput:
    env = environments.get(body.environment_id) if body.environment_id else None
    if body.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")
    coll = storage.get(body.collection_id) if body.collection_id else None
    if body.collection_id and coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    globals_lookup = global_store.as_dict()
    collection_lookup = {
        v.name: v.value for v in (coll.variables if coll else []) if v.enabled
    }
    env_lookup = {v.name: v.value for v in (env.variables if env else []) if v.enabled}
    resolutions: list[VariableResolution] = []

    def resolve(name: str) -> str:
        if name in body.runtime:
            value = body.runtime[name]
            resolutions.append(
                VariableResolution(
                    name=name, source="runtime", value=value, resolved=True
                )
            )
            return value
        if name in env_lookup:
            value = env_lookup[name]
            resolutions.append(
                VariableResolution(
                    name=name, source="environment", value=value, resolved=True
                )
            )
            return value
        if name in collection_lookup:
            value = collection_lookup[name]
            resolutions.append(
                VariableResolution(
                    name=name, source="collection", value=value, resolved=True
                )
            )
            return value
        if name in globals_lookup:
            value = globals_lookup[name]
            resolutions.append(
                VariableResolution(
                    name=name, source="global", value=value, resolved=True
                )
            )
            return value
        builtin = _builtin_preview(name)
        if builtin is not None:
            resolutions.append(
                VariableResolution(
                    name=name, source="builtin", value=builtin, resolved=True
                )
            )
            return builtin
        resolutions.append(VariableResolution(name=name, source="unresolved", resolved=False))
        return f"{{{{{name}}}}}"

    resolved_text = VAR_PATTERN.sub(lambda match: resolve(match.group(1)), body.text)
    return VariableInspectOutput(resolved_text=resolved_text, variables=resolutions)


# ---- Dependency graph -----------------------------------------------------


class DependencyNode(BaseModel):
    id: str
    name: str
    produces: list[str] = Field(default_factory=list)
    consumes: list[str] = Field(default_factory=list)


class DependencyEdge(BaseModel):
    from_id: str
    to_id: str
    variable: str


class DependencyGraphOutput(BaseModel):
    nodes: list[DependencyNode]
    edges: list[DependencyEdge]
    unresolved_variables: list[str] = Field(default_factory=list)


def _request_text_fields(req: CollectionItem) -> list[str]:
    parts = [req.url or "", req.body or ""]
    parts.extend(req.headers.values())
    if req.auth:
        parts.extend(
            [
                req.auth.token or "",
                req.auth.username or "",
                req.auth.password or "",
                req.auth.key or "",
                req.auth.value or "",
            ]
        )
    return parts


def _vars_in_request(req: CollectionItem) -> set[str]:
    found: set[str] = set()
    for text in _request_text_fields(req):
        found.update(match.group(1) for match in VAR_PATTERN.finditer(text))
    return found


@router.get("/collections/{collection_id}/dependency-graph", response_model=DependencyGraphOutput)
def dependency_graph(collection_id: str) -> DependencyGraphOutput:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    requests = _flatten_requests(coll.items)
    producers: dict[str, str] = {}
    nodes: list[DependencyNode] = []
    for req in requests:
        produced = [capture.name for capture in req.captures]
        for name in produced:
            producers[name] = req.id
        nodes.append(
            DependencyNode(
                id=req.id,
                name=req.name,
                produces=produced,
                consumes=sorted(_vars_in_request(req)),
            )
        )
    edges: list[DependencyEdge] = []
    unresolved: set[str] = set()
    for node in nodes:
        for var in node.consumes:
            producer_id = producers.get(var)
            if producer_id and producer_id != node.id:
                edges.append(DependencyEdge(from_id=producer_id, to_id=node.id, variable=var))
            elif not var.startswith("$"):
                unresolved.add(var)
    return DependencyGraphOutput(nodes=nodes, edges=edges, unresolved_variables=sorted(unresolved))


# ---- Semantic diff + snapshots -------------------------------------------


class JsonDiffInput(BaseModel):
    left: str
    right: str
    ignore_paths: list[str] = Field(default_factory=list)
    unordered_arrays: bool = True


class JsonDifference(BaseModel):
    path: str
    kind: Literal["added", "removed", "changed"]
    left: Any = None
    right: Any = None


class JsonDiffOutput(BaseModel):
    equal: bool
    differences: list[JsonDifference]


class SnapshotWriteInput(BaseModel):
    value: str
    metadata: dict[str, str] = Field(default_factory=dict)


class SnapshotCompareInput(BaseModel):
    value: str
    ignore_paths: list[str] = Field(default_factory=list)
    unordered_arrays: bool = True


class SnapshotCompareOutput(BaseModel):
    exists: bool
    diff: JsonDiffOutput | None = None


def _parse_json_payload(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc


def _remove_path(data: Any, path: str) -> None:
    if not path:
        return
    parts = path.strip("$.").split(".")
    current = data
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return
    last = parts[-1]
    if isinstance(current, dict):
        current.pop(last, None)
    elif isinstance(current, list) and last.isdigit():
        index = int(last)
        if 0 <= index < len(current):
            current.pop(index)


def _normalize_json(value: Any, ignore_paths: list[str], unordered_arrays: bool) -> Any:
    data = copy.deepcopy(value)
    for path in ignore_paths:
        _remove_path(data, path)

    def normalize(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: normalize(v) for k, v in sorted(node.items())}
        if isinstance(node, list):
            normalized = [normalize(v) for v in node]
            if unordered_arrays:
                return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
            return normalized
        return node

    return normalize(data)


def _diff_values(left: Any, right: Any, path: str = "$") -> list[JsonDifference]:
    if type(left) is not type(right):
        return [JsonDifference(path=path, kind="changed", left=left, right=right)]
    if isinstance(left, dict):
        out: list[JsonDifference] = []
        keys = set(left) | set(right)
        for key in sorted(keys):
            child_path = f"{path}.{key}"
            if key not in left:
                out.append(JsonDifference(path=child_path, kind="added", right=right[key]))
            elif key not in right:
                out.append(JsonDifference(path=child_path, kind="removed", left=left[key]))
            else:
                out.extend(_diff_values(left[key], right[key], child_path))
        return out
    if isinstance(left, list):
        out = []
        for idx in range(max(len(left), len(right))):
            child_path = f"{path}[{idx}]"
            if idx >= len(left):
                out.append(JsonDifference(path=child_path, kind="added", right=right[idx]))
            elif idx >= len(right):
                out.append(JsonDifference(path=child_path, kind="removed", left=left[idx]))
            else:
                out.extend(_diff_values(left[idx], right[idx], child_path))
        return out
    if left != right:
        return [JsonDifference(path=path, kind="changed", left=left, right=right)]
    return []


@router.post("/diff/json", response_model=JsonDiffOutput)
def diff_json(body: JsonDiffInput) -> JsonDiffOutput:
    left = _normalize_json(
        _parse_json_payload(body.left), body.ignore_paths, body.unordered_arrays
    )
    right = _normalize_json(
        _parse_json_payload(body.right), body.ignore_paths, body.unordered_arrays
    )
    differences = _diff_values(left, right)
    return JsonDiffOutput(equal=len(differences) == 0, differences=differences)


def _snapshot_path(name: str) -> Path:
    if not re.match(r"^[A-Za-z0-9_.-]{1,160}$", name):
        raise HTTPException(status_code=400, detail="invalid snapshot name")
    directory = storage.home_dir() / "snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{name}.json"


@router.put("/snapshots/{name}")
def write_snapshot(name: str, body: SnapshotWriteInput) -> dict[str, str]:
    payload = {
        "value": _parse_json_payload(body.value),
        "metadata": body.metadata,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }
    _write_json_atomic(_snapshot_path(name), payload)
    return {"name": name, "status": "saved"}


@router.post("/snapshots/{name}/compare", response_model=SnapshotCompareOutput)
def compare_snapshot(name: str, body: SnapshotCompareInput) -> SnapshotCompareOutput:
    path = _snapshot_path(name)
    if not path.exists():
        return SnapshotCompareOutput(exists=False)
    stored = json.loads(path.read_text(encoding="utf-8"))
    left = json.dumps(stored.get("value"))
    diff = diff_json(
        JsonDiffInput(
            left=left,
            right=body.value,
            ignore_paths=body.ignore_paths,
            unordered_arrays=body.unordered_arrays,
        )
    )
    return SnapshotCompareOutput(exists=True, diff=diff)


# ---- Flow runner, cleanup hooks, data sets, and trace timeline ------------


class FlowStep(BaseModel):
    id: str | None = None
    name: str = "Request"
    method: HttpMethod = "GET"
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None
    assertions: list[Assertion] = Field(default_factory=list)
    captures: list[RequestCapture] = Field(default_factory=list)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)


class FlowRunInput(BaseModel):
    environment_id: str | None = None
    dataset: list[dict[str, str]] = Field(default_factory=lambda: [{}])
    steps: list[FlowStep] = Field(..., min_length=1)
    cleanup_steps: list[FlowStep] = Field(default_factory=list)


class FlowStepResult(BaseModel):
    step_id: str
    name: str
    status: int | None = None
    elapsed_ms: float = 0
    error: str | None = None
    captured_values: dict[str, str] = Field(default_factory=dict)
    assertion_results: list[AssertionResult] = Field(default_factory=list)


class FlowTraceEvent(BaseModel):
    dataset_index: int
    step_id: str
    phase: Literal["request", "assertions", "capture", "cleanup"]
    started_at: str
    ended_at: str
    elapsed_ms: float
    status: int | None = None
    error: str | None = None


class FlowDatasetResult(BaseModel):
    index: int
    runtime: dict[str, str]
    steps: list[FlowStepResult]
    cleanup: list[FlowStepResult]


class FlowRunOutput(BaseModel):
    datasets: list[FlowDatasetResult]
    trace: list[FlowTraceEvent]
    passed_assertions: int
    failed_assertions: int


def _substitute_dict_extra(
    values: dict[str, str], env: environments.Environment | None, runtime: dict[str, str]
) -> dict[str, str]:
    return {key: environments.substitute(value, env, runtime) for key, value in values.items()}


def _auth_with_runtime(
    auth: AuthConfig | None, env: environments.Environment | None, runtime: dict[str, str]
) -> AuthConfig | None:
    if auth is None:
        return None
    data = auth.model_dump()
    for key, value in list(data.items()):
        if isinstance(value, str):
            data[key] = environments.substitute(value, env, runtime)
    return AuthConfig(**data)


def _extract_json_path(data: Any, path: str) -> str | None:
    current = data
    if not path:
        return None
    for part in path.split("."):
        match = re.match(r"^(\w+)\[(\d+)]$", part)
        if match:
            key, index = match.group(1), int(match.group(2))
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
            if not isinstance(current, list) or index >= len(current):
                return None
            current = current[index]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return json.dumps(current) if isinstance(current, (dict, list)) else str(current)


def _capture_values(
    captures: list[RequestCapture], status: int, headers: dict[str, str], body: str
) -> dict[str, str]:
    out: dict[str, str] = {}
    for capture in captures:
        if capture.source == "status":
            out[capture.name] = str(status)
        elif capture.source == "header":
            needle = capture.path.lower()
            out[capture.name] = next((v for k, v in headers.items() if k.lower() == needle), "")
        else:
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                out[capture.name] = ""
            else:
                out[capture.name] = _extract_json_path(payload, capture.path) or ""
    return out


async def _run_flow_step(
    step: FlowStep,
    env: environments.Environment | None,
    runtime: dict[str, str],
    phase: Literal["request", "cleanup"],
) -> tuple[FlowStepResult, FlowTraceEvent]:
    step_id = step.id or str(uuid.uuid4())
    start_dt = datetime.now(tz=UTC)
    started = time.perf_counter()
    result = FlowStepResult(step_id=step_id, name=step.name)
    try:
        resolved_url = environments.substitute(step.url, env, runtime)
        headers = _substitute_dict_extra(step.headers, env, runtime)
        body = environments.substitute(step.body, env, runtime) if step.body is not None else None
        query: dict[str, str] = {}
        auth = _auth_with_runtime(step.auth, env, runtime)
        if auth and auth.type != "none":
            _apply_auth(auth, headers, query, env)
        async with httpx.AsyncClient(http2=True, timeout=step.timeout_seconds) as client:
            response = await client.request(
                method=step.method,
                url=resolved_url,
                headers=headers,
                params=query or None,
                content=body.encode("utf-8") if body is not None else None,
            )
        elapsed = (time.perf_counter() - started) * 1000
        result.status = response.status_code
        result.elapsed_ms = round(elapsed, 2)
        response_headers = dict(response.headers)
        result.captured_values = _capture_values(
            step.captures, response.status_code, response_headers, response.text
        )
        runtime.update(result.captured_values)
        if step.assertions:
            result.assertion_results = evaluate_all(
                step.assertions,
                ResponseData(
                    status=response.status_code,
                    headers=response_headers,
                    body=response.text,
                    elapsed_ms=elapsed,
                ),
            )
    except httpx.RequestError as exc:
        result.error = f"transport error: {exc}"
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    end_dt = datetime.now(tz=UTC)
    event = FlowTraceEvent(
        dataset_index=-1,
        step_id=step_id,
        phase=phase,
        started_at=start_dt.isoformat(),
        ended_at=end_dt.isoformat(),
        elapsed_ms=result.elapsed_ms,
        status=result.status,
        error=result.error,
    )
    return result, event


@router.post("/flows/run", response_model=FlowRunOutput)
async def run_flow(body: FlowRunInput) -> FlowRunOutput:
    env = environments.get(body.environment_id) if body.environment_id else None
    if body.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")
    dataset = body.dataset or [{}]
    datasets: list[FlowDatasetResult] = []
    trace: list[FlowTraceEvent] = []
    passed = 0
    failed = 0
    for index, row in enumerate(dataset):
        runtime = dict(row)
        step_results: list[FlowStepResult] = []
        cleanup_results: list[FlowStepResult] = []
        try:
            for step in body.steps:
                result, event = await _run_flow_step(step, env, runtime, "request")
                event.dataset_index = index
                trace.append(event)
                step_results.append(result)
                passed += sum(1 for assertion in result.assertion_results if assertion.passed)
                failed += sum(1 for assertion in result.assertion_results if not assertion.passed)
        finally:
            for cleanup in body.cleanup_steps:
                result, event = await _run_flow_step(cleanup, env, runtime, "cleanup")
                event.dataset_index = index
                trace.append(event)
                cleanup_results.append(result)
        datasets.append(
            FlowDatasetResult(
                index=index,
                runtime=runtime,
                steps=step_results,
                cleanup=cleanup_results,
            )
        )
    return FlowRunOutput(
        datasets=datasets,
        trace=trace,
        passed_assertions=passed,
        failed_assertions=failed,
    )


# ---- HAR import / export --------------------------------------------------


class HarImportInput(BaseModel):
    content: str = Field(..., min_length=1)
    collection_name: str = "HAR import"


class HarImportOutput(BaseModel):
    collection_id: str
    request_count: int


@router.post("/har/import", response_model=HarImportOutput)
def import_har(body: HarImportInput) -> HarImportOutput:
    har = _parse_json_payload(body.content)
    entries = har.get("log", {}).get("entries", []) if isinstance(har, dict) else []
    if not isinstance(entries, list):
        raise HTTPException(status_code=400, detail="HAR log.entries must be an array")
    items: list[CollectionItem] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("request"), dict):
            continue
        request_data = entry["request"]
        headers = {
            str(h.get("name")): str(h.get("value", ""))
            for h in request_data.get("headers", [])
            if isinstance(h, dict) and h.get("name")
        }
        post_data = request_data.get("postData")
        body_text = post_data.get("text") if isinstance(post_data, dict) else None
        method = str(request_data.get("method", "GET")).upper()
        if method not in HTTP_METHODS:
            method = "GET"
        items.append(
            CollectionItem(
                id=str(uuid.uuid4()),
                name=f"{method} {urlsplit(str(request_data.get('url', ''))).path or '/'}",
                method=method,  # type: ignore[arg-type]
                url=str(request_data.get("url", "")),
                headers=headers,
                body=body_text,
            )
        )
    coll = Collection(id=str(uuid.uuid4()), name=body.collection_name, version=1, items=items)
    storage._atomic_write(coll)
    return HarImportOutput(collection_id=coll.id, request_count=len(items))


@router.get("/har/export/{collection_id}")
def export_har(collection_id: str) -> dict[str, Any]:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    entries = []
    for req in _flatten_requests(coll.items):
        entries.append(
            {
                "startedDateTime": datetime.now(tz=UTC).isoformat(),
                "time": 0,
                "request": {
                    "method": req.method or "GET",
                    "url": req.url or "",
                    "httpVersion": "HTTP/1.1",
                    "headers": [
                        {"name": key, "value": value}
                        for key, value in (req.headers or {}).items()
                    ],
                    "queryString": [
                        {"name": key, "value": value}
                        for key, value in parse_qsl(urlsplit(req.url or "").query)
                    ],
                    "postData": {"mimeType": "text/plain", "text": req.body or ""},
                    "headersSize": -1,
                    "bodySize": len((req.body or "").encode("utf-8")),
                },
                "response": {
                    "status": 0,
                    "statusText": "",
                    "httpVersion": "HTTP/1.1",
                    "headers": [],
                    "content": {"size": 0, "mimeType": "text/plain", "text": ""},
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": 0,
                },
                "cache": {},
                "timings": {"send": 0, "wait": 0, "receive": 0},
            }
        )
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "Theridion", "version": "0.0.1"},
            "entries": entries,
        }
    }


# ---- TLS certificate inspector -------------------------------------------


class TlsInspectInput(BaseModel):
    url: str
    timeout_seconds: float = Field(default=5, gt=0, le=30)


class TlsInspectOutput(BaseModel):
    host: str
    port: int
    subject: dict[str, str]
    issuer: dict[str, str]
    not_before: str | None = None
    not_after: str | None = None
    san: list[str] = Field(default_factory=list)
    tls_version: str | None = None
    cipher: str | None = None


def _cert_name(parts: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(parts, tuple):
        for group in parts:
            if isinstance(group, tuple):
                for key, value in group:
                    out[str(key)] = str(value)
    return out


@router.post("/tls/inspect", response_model=TlsInspectOutput)
def inspect_tls(body: TlsInspectInput) -> TlsInspectOutput:
    parsed = urlsplit(body.url if "://" in body.url else f"https://{body.url}")
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="URL must include a host")
    port = parsed.port or 443
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=body.timeout_seconds) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
                cipher = tls.cipher()
                version = tls.version()
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"TLS connection failed: {exc}") from exc
    san = [
        str(value)
        for key, value in cert.get("subjectAltName", [])
        if str(key).lower() == "dns"
    ]
    return TlsInspectOutput(
        host=host,
        port=port,
        subject=_cert_name(cert.get("subject")),
        issuer=_cert_name(cert.get("issuer")),
        not_before=cert.get("notBefore"),
        not_after=cert.get("notAfter"),
        san=san,
        tls_version=version,
        cipher=cipher[0] if cipher else None,
    )


# ---- Proxy recorder -------------------------------------------------------


class ProxyStartInput(BaseModel):
    target_base_url: str = Field(..., min_length=1)
    port: int | None = None


class ProxyStartOutput(BaseModel):
    session_id: str
    port: int
    target_base_url: str


class ProxyStatusOutput(BaseModel):
    sessions: list[ProxyStartOutput]


class _ProxyHandle:
    def __init__(
        self,
        session_id: str,
        port: int,
        target_base_url: str,
        server: uvicorn.Server,
    ) -> None:
        self.session_id = session_id
        self.port = port
        self.target_base_url = target_base_url.rstrip("/")
        self.server = server
        self.entries: list[dict[str, Any]] = []


_proxy_sessions: dict[str, _ProxyHandle] = {}


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_proxy_app(handle: _ProxyHandle) -> Starlette:
    async def proxy(request: Request) -> Response:
        raw_body = await request.body()
        target = f"{handle.target_base_url}/{request.path_params.get('path', '')}"
        if request.url.query:
            target = f"{target}?{request.url.query}"
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=60) as client:
                response = await client.request(
                    method=request.method,
                    url=target,
                    headers={
                        key: value
                        for key, value in request.headers.items()
                        if key.lower() not in {"host", "content-length"}
                    },
                    content=raw_body,
                )
        except httpx.RequestError as exc:
            return Response(str(exc), status_code=502)
        elapsed = (time.perf_counter() - started) * 1000
        handle.entries.append(
            {
                "startedDateTime": datetime.now(tz=UTC).isoformat(),
                "time": round(elapsed, 2),
                "request": {
                    "method": request.method,
                    "url": target,
                    "headers": [{"name": k, "value": v} for k, v in request.headers.items()],
                    "postData": {"text": raw_body.decode("utf-8", errors="replace")},
                },
                "response": {
                    "status": response.status_code,
                    "statusText": response.reason_phrase,
                    "headers": [{"name": k, "value": v} for k, v in response.headers.items()],
                    "content": {"text": response.text, "size": len(response.content)},
                },
            }
        )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() != "content-encoding"},
        )

    return Starlette(routes=[Route("/{path:path}", proxy, methods=list(HTTP_METHODS))])


@router.post("/proxy/start", response_model=ProxyStartOutput)
async def start_proxy(body: ProxyStartInput) -> ProxyStartOutput:
    port = body.port or _pick_free_port()
    if any(handle.port == port for handle in _proxy_sessions.values()):
        raise HTTPException(status_code=409, detail=f"proxy already running on port {port}")
    session_id = str(uuid.uuid4())
    placeholder = _ProxyHandle(session_id, port, body.target_base_url, server=None)  # type: ignore[arg-type]
    app = _build_proxy_app(placeholder)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    placeholder.server = server
    _proxy_sessions[session_id] = placeholder
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(20):
        if server.started:
            break
        await asyncio.sleep(0.05)
    return ProxyStartOutput(session_id=session_id, port=port, target_base_url=body.target_base_url)


@router.get("/proxy/status", response_model=ProxyStatusOutput)
def proxy_status() -> ProxyStatusOutput:
    return ProxyStatusOutput(
        sessions=[
            ProxyStartOutput(
                session_id=handle.session_id,
                port=handle.port,
                target_base_url=handle.target_base_url,
            )
            for handle in _proxy_sessions.values()
        ]
    )


@router.post("/proxy/{session_id}/stop")
def stop_proxy(session_id: str) -> dict[str, str]:
    handle = _proxy_sessions.pop(session_id, None)
    if handle is None:
        raise HTTPException(status_code=404, detail="proxy session not found")
    handle.server.should_exit = True
    return {"status": "stopped", "session_id": session_id}


@router.get("/proxy/{session_id}/har")
def proxy_har(session_id: str) -> dict[str, Any]:
    handle = _proxy_sessions.get(session_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="proxy session not found")
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "Theridion proxy recorder", "version": "0.0.1"},
            "entries": handle.entries,
        }
    }


# ---- Mock from collection -------------------------------------------------


@router.post("/mock/start-from-collection/{collection_id}")
async def start_mock_from_collection(collection_id: str, port: int | None = None) -> Any:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    from .mock import MockRoute, MockStartRequest, start_mock

    routes: list[MockRoute] = []
    for req in _flatten_requests(coll.items):
        if not req.url:
            continue
        parsed = urlsplit(req.url)
        response_body = (
            req.examples[0].body
            if req.examples and req.examples[0].body is not None
            else req.body or json.dumps({"request": req.name})
        )
        routes.append(
            MockRoute(
                path=parsed.path or "/",
                method=req.method or "GET",
                status=200,
                body=response_body,
                content_type=(
                    "application/json" if _looks_like_json(response_body) else "text/plain"
                ),
            )
        )
    if not routes:
        raise HTTPException(status_code=400, detail="collection has no mockable requests")
    return await start_mock(MockStartRequest(routes=routes, port=port))


def _looks_like_json(value: str) -> bool:
    try:
        json.loads(value)
        return True
    except json.JSONDecodeError:
        return False


# ---- Git-aware review mode ------------------------------------------------


class GitReviewInput(BaseModel):
    repo_path: str = "."


class GitReviewChange(BaseModel):
    file: str
    summary: str
    details: list[str] = Field(default_factory=list)


class GitReviewOutput(BaseModel):
    changes: list[GitReviewChange]


def _git(repo_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_path), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _load_json_maybe(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _requests_by_id(collection: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not collection:
        return out

    def walk(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("is_folder"):
                walk(item.get("items"))
            elif isinstance(item.get("id"), str):
                out[str(item["id"])] = item

    walk(collection.get("items"))
    return out


@router.post("/git/review", response_model=GitReviewOutput)
def git_review(body: GitReviewInput) -> GitReviewOutput:
    repo = Path(body.repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        raise HTTPException(status_code=400, detail="repo_path is not a git repository")
    root_proc = _git(repo, ["rev-parse", "--show-toplevel"])
    if root_proc.returncode != 0:
        raise HTTPException(status_code=400, detail=root_proc.stderr.strip() or "git failed")
    root = Path(root_proc.stdout.strip())
    changed_proc = _git(root, ["diff", "--name-only"])
    if changed_proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=changed_proc.stderr.strip() or "git diff failed",
        )
    changes: list[GitReviewChange] = []
    for rel in [line for line in changed_proc.stdout.splitlines() if line.endswith(".json")]:
        path = root / rel
        if not path.exists():
            changes.append(GitReviewChange(file=rel, summary="Deleted JSON file"))
            continue
        current = _load_json_maybe(path.read_text(encoding="utf-8"))
        if not current or "items" not in current:
            continue
        head_proc = _git(root, ["show", f"HEAD:{rel}"])
        previous = _load_json_maybe(head_proc.stdout) if head_proc.returncode == 0 else None
        old_requests = _requests_by_id(previous)
        new_requests = _requests_by_id(current)
        details: list[str] = []
        for request_id in sorted(new_requests.keys() - old_requests.keys()):
            details.append(f"Added request: {new_requests[request_id].get('name', request_id)}")
        for request_id in sorted(old_requests.keys() - new_requests.keys()):
            details.append(f"Removed request: {old_requests[request_id].get('name', request_id)}")
        for request_id in sorted(new_requests.keys() & old_requests.keys()):
            old = old_requests[request_id]
            new = new_requests[request_id]
            for field in (
                "name",
                "method",
                "url",
                "headers",
                "body",
                "auth",
                "assertions",
                "captures",
            ):
                if old.get(field) != new.get(field):
                    details.append(
                        f"Changed {field} on {new.get('name') or old.get('name') or request_id}"
                    )
        if previous and previous.get("name") != current.get("name"):
            details.insert(
                0,
                f"Renamed collection: {previous.get('name')} -> {current.get('name')}",
            )
        summary = f"{len(details)} collection-level change{'s' if len(details) != 1 else ''}"
        changes.append(GitReviewChange(file=rel, summary=summary, details=details))
    return GitReviewOutput(changes=changes)
