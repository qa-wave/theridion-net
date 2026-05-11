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


class GrpcReflectRequest(BaseModel):
    host: str = Field(..., min_length=1)


class GrpcService(BaseModel):
    name: str
    methods: list[str] = Field(default_factory=list)


class GrpcReflectResponse(BaseModel):
    services: list[GrpcService]


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
                methods: list[str] = []
                for mr in method_responses:
                    if mr.HasField("file_descriptor_response"):
                        from google.protobuf import descriptor_pb2

                        for fd_bytes in mr.file_descriptor_response.file_descriptor_proto:
                            fd = descriptor_pb2.FileDescriptorProto()
                            fd.ParseFromString(fd_bytes)
                            for service_desc in fd.service:
                                if service_desc.name == svc.name.split(".")[-1]:
                                    methods = [m.name for m in service_desc.method]
                services.append(GrpcService(name=svc.name, methods=methods))
        channel.close()
        return GrpcReflectResponse(services=services)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"gRPC reflection error: {exc}") from exc


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
