"""gRPC reflection + unary invocation endpoints.

Uses grpcio and grpc_reflection to list services and call unary methods.
Requires grpcio and grpcio-reflection in dependencies.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/grpc", tags=["grpc"])


# ---- Models ----------------------------------------------------------------

class GrpcReflectRequest(BaseModel):
    host: str = Field(..., min_length=1)


class GrpcMethodInfo(BaseModel):
    name: str
    input_type: str = ""
    output_type: str = ""
    is_streaming: bool = False


class GrpcService(BaseModel):
    name: str
    methods: list[GrpcMethodInfo] = Field(default_factory=list)


class GrpcReflectResponse(BaseModel):
    services: list[GrpcService]


class GrpcDescribeRequest(BaseModel):
    host: str = Field(..., min_length=1)
    service: str = Field(..., min_length=1)
    method: str = Field(..., min_length=1)


class GrpcFieldDescriptor(BaseModel):
    name: str
    type: str
    label: str = "optional"
    type_name: str | None = None
    fields: list[GrpcFieldDescriptor] | None = None


class GrpcDescribeResponse(BaseModel):
    input_type: str
    output_type: str
    input_fields: list[GrpcFieldDescriptor]
    template: dict[str, Any]


GrpcFieldDescriptor.model_rebuild()


class GrpcInvokeRequest(BaseModel):
    host: str = Field(..., min_length=1)
    service: str = Field(..., min_length=1)
    method: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)


class GrpcInvokeResponse(BaseModel):
    ok: bool
    result: Any = None
    error: str | None = None
    elapsed_ms: float = 0


# ---- Helpers ---------------------------------------------------------------

# Protobuf field type number to human-readable name mapping
_PROTO_TYPE_MAP: dict[int, str] = {
    1: "double",
    2: "float",
    3: "int64",
    4: "uint64",
    5: "int32",
    6: "fixed64",
    7: "fixed32",
    8: "bool",
    9: "string",
    10: "group",
    11: "message",
    12: "bytes",
    13: "uint32",
    14: "enum",
    15: "sfixed32",
    16: "sfixed64",
    17: "sint32",
    18: "sint64",
}

_PROTO_LABEL_MAP: dict[int, str] = {
    1: "optional",
    2: "required",
    3: "repeated",
}

# Default values per proto type for template generation
_PROTO_DEFAULTS: dict[str, Any] = {
    "string": "",
    "bool": False,
    "int32": 0,
    "int64": 0,
    "uint32": 0,
    "uint64": 0,
    "sint32": 0,
    "sint64": 0,
    "fixed32": 0,
    "fixed64": 0,
    "sfixed32": 0,
    "sfixed64": 0,
    "float": 0.0,
    "double": 0.0,
    "bytes": "",
    "enum": 0,
}


def _parse_field_descriptors(
    fd_proto: Any,
    msg_type_name: str,
    visited: set[str] | None = None,
) -> list[GrpcFieldDescriptor]:
    """Walk a FileDescriptorProto to extract fields for a given message type.

    Handles nested messages up to a reasonable depth to avoid cycles.
    """
    if visited is None:
        visited = set()
    # Prevent infinite recursion on self-referencing messages
    if msg_type_name in visited:
        return []
    visited = visited | {msg_type_name}

    # Strip leading dot for matching
    bare = msg_type_name.lstrip(".")
    # Look through all message types in the file descriptor
    target = None
    for mt in fd_proto.message_type:
        full = f"{fd_proto.package}.{mt.name}" if fd_proto.package else mt.name
        if full == bare or mt.name == bare:
            target = mt
            break
        # Check nested types
        found = _find_nested(mt, bare, fd_proto.package)
        if found is not None:
            target = found
            break

    if target is None:
        return []

    result: list[GrpcFieldDescriptor] = []
    for f in target.field:
        type_str = _PROTO_TYPE_MAP.get(f.type, f"unknown({f.type})")
        label_str = _PROTO_LABEL_MAP.get(f.label, "optional")
        nested: list[GrpcFieldDescriptor] | None = None
        type_name: str | None = f.type_name.lstrip(".") if f.type_name else None
        if f.type == 11 and f.type_name:  # message type
            nested = _parse_field_descriptors(fd_proto, f.type_name, visited)
        result.append(GrpcFieldDescriptor(
            name=f.name,
            type=type_str,
            label=label_str,
            type_name=type_name,
            fields=nested if nested else None,
        ))
    return result


def _find_nested(msg: Any, target_name: str, package: str) -> Any:
    """Recursively search nested message types."""
    for nested in msg.nested_type:
        full = f"{package}.{msg.name}.{nested.name}" if package else f"{msg.name}.{nested.name}"
        if full == target_name or nested.name == target_name:
            return nested
        found = _find_nested(nested, target_name, package)
        if found is not None:
            return found
    return None


def _build_template(fields: list[GrpcFieldDescriptor]) -> dict[str, Any]:
    """Generate a template JSON object from field descriptors."""
    template: dict[str, Any] = {}
    for f in fields:
        if f.type == "message" and f.fields:
            val = _build_template(f.fields)
            template[f.name] = [val] if f.label == "repeated" else val
        else:
            default = _PROTO_DEFAULTS.get(f.type, "")
            template[f.name] = [default] if f.label == "repeated" else default
    return template


# ---- Endpoints -------------------------------------------------------------

@router.post("/reflect", response_model=GrpcReflectResponse)
async def reflect(req: GrpcReflectRequest) -> GrpcReflectResponse:
    try:
        import grpc
        from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="grpcio / grpcio-reflection not installed",
        ) from exc

    try:
        channel = grpc.insecure_channel(req.host)
        stub = reflection_pb2_grpc.ServerReflectionStub(channel)

        # List services
        request = reflection_pb2.ServerReflectionRequest(
            list_services=""
        )
        responses = stub.ServerReflectionInfo(iter([request]))
        services: list[GrpcService] = []
        for resp in responses:
            for svc in resp.list_services_response.service:
                if svc.name.startswith("grpc.reflection"):
                    continue
                # Get methods for each service
                method_req = reflection_pb2.ServerReflectionRequest(
                    file_containing_symbol=svc.name
                )
                method_responses = stub.ServerReflectionInfo(iter([method_req]))
                methods: list[GrpcMethodInfo] = []
                for mr in method_responses:
                    if mr.HasField("file_descriptor_response"):
                        from google.protobuf import descriptor_pb2

                        for fd_bytes in mr.file_descriptor_response.file_descriptor_proto:
                            fd = descriptor_pb2.FileDescriptorProto()
                            fd.ParseFromString(fd_bytes)
                            for service_desc in fd.service:
                                if service_desc.name == svc.name.split(".")[-1]:
                                    methods = [
                                        GrpcMethodInfo(
                                            name=m.name,
                                            input_type=m.input_type.lstrip("."),
                                            output_type=m.output_type.lstrip("."),
                                            is_streaming=m.client_streaming or m.server_streaming,
                                        )
                                        for m in service_desc.method
                                    ]
                services.append(GrpcService(name=svc.name, methods=methods))
        channel.close()
        return GrpcReflectResponse(services=services)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"gRPC reflection error: {exc}") from exc


@router.post("/describe", response_model=GrpcDescribeResponse)
async def describe(req: GrpcDescribeRequest) -> GrpcDescribeResponse:
    """Describe a gRPC method's input/output message types.

    Returns field descriptors and a template JSON object suitable for
    populating the request payload editor.
    """
    try:
        import grpc
        from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="grpcio / grpcio-reflection not installed",
        ) from exc

    try:
        channel = grpc.insecure_channel(req.host)
        stub = reflection_pb2_grpc.ServerReflectionStub(channel)

        # Resolve the file descriptor for the service
        file_req = reflection_pb2.ServerReflectionRequest(
            file_containing_symbol=req.service
        )
        responses = stub.ServerReflectionInfo(iter([file_req]))

        input_type = ""
        output_type = ""
        fd_proto = None

        for resp in responses:
            if resp.HasField("file_descriptor_response"):
                from google.protobuf import descriptor_pb2

                for fd_bytes in resp.file_descriptor_response.file_descriptor_proto:
                    fd = descriptor_pb2.FileDescriptorProto()
                    fd.ParseFromString(fd_bytes)
                    for service_desc in fd.service:
                        short_name = req.service.split(".")[-1]
                        if service_desc.name == short_name:
                            for m in service_desc.method:
                                if m.name == req.method:
                                    input_type = m.input_type.lstrip(".")
                                    output_type = m.output_type.lstrip(".")
                                    fd_proto = fd
                                    break

        channel.close()

        if fd_proto is None or not input_type:
            raise HTTPException(
                status_code=404,
                detail=f"Method {req.service}/{req.method} not found via reflection",
            )

        input_fields = _parse_field_descriptors(fd_proto, input_type)
        template = _build_template(input_fields)

        return GrpcDescribeResponse(
            input_type=input_type,
            output_type=output_type,
            input_fields=input_fields,
            template=template,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"gRPC describe error: {exc}",
        ) from exc


@router.post("/invoke", response_model=GrpcInvokeResponse)
async def invoke(req: GrpcInvokeRequest) -> GrpcInvokeResponse:
    try:
        import grpc
        from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message_factory
        from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="grpcio / grpcio-reflection not installed",
        ) from exc

    import time

    started = time.perf_counter()
    try:
        channel = grpc.insecure_channel(req.host)
        stub = reflection_pb2_grpc.ServerReflectionStub(channel)

        # Resolve the file descriptor for the service
        symbol = f"{req.service}.{req.method}" if "." not in req.method else req.method
        file_req = reflection_pb2.ServerReflectionRequest(
            file_containing_symbol=req.service
        )
        responses = stub.ServerReflectionInfo(iter([file_req]))

        pool = descriptor_pool.DescriptorPool()
        for resp in responses:
            if resp.HasField("file_descriptor_response"):
                for fd_bytes in resp.file_descriptor_response.file_descriptor_proto:
                    fd_proto = descriptor_pb2.FileDescriptorProto()
                    fd_proto.ParseFromString(fd_bytes)
                    try:
                        pool.Add(fd_proto)
                    except Exception:
                        pass

        # Find the method descriptor
        svc_desc = pool.FindServiceByName(req.service)
        method_desc = svc_desc.FindMethodByName(req.method)

        # Build request message
        factory = message_factory.MessageFactory(pool)
        request_class = factory.GetPrototype(method_desc.input_type)
        request_msg = request_class()
        if req.payload:
            json_format.ParseDict(req.payload, request_msg)

        # Build metadata
        metadata = list(req.metadata.items()) if req.metadata else None

        # Make the call
        full_method = f"/{req.service}/{req.method}"
        response_bytes = channel.unary_unary(
            full_method,
            request_serializer=lambda x: x.SerializeToString(),
            response_deserializer=factory.GetPrototype(method_desc.output_type).FromString,
        )(request_msg, timeout=req.timeout_seconds, metadata=metadata)

        elapsed = (time.perf_counter() - started) * 1000
        result = json_format.MessageToDict(response_bytes)
        channel.close()

        return GrpcInvokeResponse(ok=True, result=result, elapsed_ms=round(elapsed, 2))
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return GrpcInvokeResponse(
            ok=False,
            error=str(exc),
            elapsed_ms=round(elapsed, 2),
        )
