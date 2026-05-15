"""
fynor.adapters.grpc — gRPC service adapter.

Implements BaseAdapter for gRPC endpoints using grpc.aio (async-native).

CRITICAL: this module uses grpc.aio throughout, never the synchronous grpcio API.
Sync gRPC calls block the asyncio event loop — with 8+ checks running concurrently
via asyncio.gather() in FastAPI, one sync gRPC call stalls ALL concurrent checks.
Decision D9 (plan-eng-review 2026-05-15).

Target format accepted:
  "host:port"           — plaintext channel
  "grpc://host:port"    — plaintext channel (scheme stripped)
  "grpcs://host:port"   — TLS channel (scheme stripped)

gRPC reflection (Decision D3 — plan-eng-review 2026-05-15):
  Most production gRPC servers disable the reflection service by default.
  When the server returns StatusCode.UNIMPLEMENTED on the reflection RPC,
  the reflection_enabled check returns result="na" rather than "fail" —
  disabling reflection is a deployment choice, not a bug.

  If the caller provides grpc_method (e.g. "grpc.health.v1.Health/Check"),
  the adapter falls back to probing that specific RPC when reflection is
  unavailable, giving a connectivity signal without requiring reflection.

Reflection protocol:
  The gRPC server reflection service is queried without generated stubs by
  sending a raw protobuf-encoded ServerReflectionRequest. The request asks
  for all service names (field 4 = list_services = ""). The response bytes
  are decoded minimally — we extract service name strings.

  Field 4, wire type 2 (length-delimited), empty string:  b'\"\\x00'
  This is the minimal valid list_services request.
"""

from __future__ import annotations

import asyncio
import re
import struct
import time
from typing import Any

import grpc
import grpc.aio

from fynor.adapters.base import BaseAdapter, Response

# ---------------------------------------------------------------------------
# gRPC status → HTTP status mapping (for normalised Response.status_code)
# ---------------------------------------------------------------------------

_GRPC_TO_HTTP: dict[grpc.StatusCode, int] = {
    grpc.StatusCode.OK:                  200,
    grpc.StatusCode.CANCELLED:           499,
    grpc.StatusCode.UNKNOWN:             500,
    grpc.StatusCode.INVALID_ARGUMENT:    400,
    grpc.StatusCode.DEADLINE_EXCEEDED:   504,
    grpc.StatusCode.NOT_FOUND:           404,
    grpc.StatusCode.ALREADY_EXISTS:      409,
    grpc.StatusCode.PERMISSION_DENIED:   403,
    grpc.StatusCode.RESOURCE_EXHAUSTED:  429,
    grpc.StatusCode.FAILED_PRECONDITION: 412,
    grpc.StatusCode.ABORTED:             409,
    grpc.StatusCode.OUT_OF_RANGE:        400,
    grpc.StatusCode.UNIMPLEMENTED:       501,
    grpc.StatusCode.INTERNAL:            500,
    grpc.StatusCode.UNAVAILABLE:         503,
    grpc.StatusCode.DATA_LOSS:           500,
    grpc.StatusCode.UNAUTHENTICATED:     401,
}

# Raw protobuf: ServerReflectionRequest { list_services: "" }
# field 4 (list_services), wire type 2 (length-delimited), length 0
_REFLECTION_LIST_SERVICES_REQUEST = b"\x22\x00"

# Standard health check method path (gRPC health protocol)
_HEALTH_CHECK_METHOD = "/grpc.health.v1.Health/Check"

# Reflection service method path (v1alpha — most widely deployed)
_REFLECTION_METHOD = (
    "/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo"
)


def _grpc_status_to_http(code: grpc.StatusCode) -> int:
    """Map a gRPC StatusCode to the nearest HTTP status code equivalent."""
    return _GRPC_TO_HTTP.get(code, 500)


def _parse_target(target: str) -> tuple[str, bool]:
    """
    Parse a Fynor gRPC target string into (channel_target, use_tls).

    Accepts:
      "host:port"          → ("host:port", False)
      "grpc://host:port"   → ("host:port", False)
      "grpcs://host:port"  → ("host:port", True)
    """
    if target.startswith("grpcs://"):
        return target[len("grpcs://"):], True
    if target.startswith("grpc://"):
        return target[len("grpc://"):], False
    return target, False


def _extract_service_names(response_bytes: bytes) -> list[str]:
    """
    Minimally parse a ServerReflectionResponse to extract service names.

    The reflection response contains a list_services_response (field 4)
    which contains repeated ServiceResponse (field 1) each with name (field 1).

    We use a simple regex over the raw bytes to extract ASCII service names
    without needing the full proto definitions. This is intentionally simple —
    we only need the service names for display, not for invoking them.
    """
    # Service names are valid gRPC service paths: Package.ServiceName
    # Extract all ASCII strings that look like service identifiers
    names = re.findall(rb"[\x20-\x7e]{5,}", response_bytes)
    result: list[str] = []
    for raw in names:
        candidate = raw.decode("ascii", errors="replace")
        # Service names contain dots and are at least 3 chars
        if "." in candidate and len(candidate) >= 3:
            # Filter out obvious non-service strings (paths, headers, etc.)
            if not candidate.startswith("/") and " " not in candidate:
                result.append(candidate)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for name in result:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


class GRPCAdapter(BaseAdapter):
    """
    Adapter for gRPC services.

    Uses grpc.aio throughout — never the synchronous grpcio API.
    Decision D9 (plan-eng-review 2026-05-15).

    Args:
        target:      gRPC endpoint — "host:port", "grpc://host:port", or
                     "grpcs://host:port". Must be pre-validated for SSRF.
        timeout:     Per-call deadline in seconds.
        auth_token:  Bearer token (sent as "authorization" metadata).
        grpc_method: Optional RPC method to probe when reflection is disabled.
                     Format: "package.ServiceName/MethodName" or
                     "/package.ServiceName/MethodName".
                     Example: "grpc.health.v1.Health/Check"
    """

    def __init__(
        self,
        target: str,
        timeout: float = 10.0,
        auth_token: str | None = None,
        grpc_method: str | None = None,
    ) -> None:
        super().__init__(target, timeout)
        self._auth_token = auth_token
        self.grpc_method = grpc_method  # exposed for checks to read
        self._channel_target, self._use_tls = _parse_target(target)

    # ------------------------------------------------------------------
    # BaseAdapter interface
    # ------------------------------------------------------------------

    async def call(self, payload: dict | None = None) -> Response:
        """
        Make one gRPC unary call to the configured grpc_method (or the
        health check endpoint as default).

        Args:
            payload: Ignored for gRPC — calls are made with empty bytes.
                     Kept for interface compatibility.

        Returns:
            Normalised Response. status_code follows the gRPC→HTTP mapping.
        """
        method = self._normalise_method(
            self.grpc_method or _HEALTH_CHECK_METHOD
        )
        return await self._unary_call(method, request_bytes=b"")

    async def get_schema(self) -> dict:
        """
        Fetch the service list via gRPC reflection.

        Returns:
            Dict with key "services" → list of service name strings.
            Returns {} when reflection is disabled (not a failure).
        """
        r = await self._call_reflection_service()
        if r.status_code != 200 or not isinstance(r.body, dict):
            return {}
        return r.body

    def get_auth_headers(self) -> dict[str, str]:
        """Return auth metadata as a dict (for interface compatibility)."""
        if self._auth_token:
            return {"authorization": f"Bearer {self._auth_token}"}
        return {}

    # ------------------------------------------------------------------
    # gRPC-specific methods used by checks
    # ------------------------------------------------------------------

    async def _call_reflection_service(self) -> Response:
        """
        Attempt to list all services via the gRPC reflection protocol.

        Returns:
            Response with:
              status_code=200, body={"services": [...]}  — reflection available
              status_code=501, error="StatusCode.UNIMPLEMENTED"  — disabled
              status_code=503/504, error=...              — connectivity failure
        """
        channel_kwargs: dict[str, Any] = {
            "options": [
                ("grpc.max_receive_message_length", 4 * 1024 * 1024),  # 4 MB
            ]
        }

        t0 = time.monotonic()
        try:
            if self._use_tls:
                credentials = grpc.ssl_channel_credentials()
                channel = grpc.aio.secure_channel(
                    self._channel_target, credentials, **channel_kwargs
                )
            else:
                channel = grpc.aio.insecure_channel(
                    self._channel_target, **channel_kwargs
                )

            async with channel:
                stub = channel.stream_stream(
                    _REFLECTION_METHOD,
                    request_serializer=lambda b: b,
                    response_deserializer=lambda b: b,
                )
                # Send a single list_services request then close the send side
                call = stub(
                    iter([_REFLECTION_LIST_SERVICES_REQUEST]),
                    timeout=self.timeout,
                    metadata=self._build_metadata(),
                )
                # Collect all response chunks (usually just one)
                raw_chunks: list[bytes] = []
                async for chunk in call:
                    if isinstance(chunk, bytes):
                        raw_chunks.append(chunk)
                    if len(raw_chunks) >= 4:  # guard — don't buffer forever
                        break

            latency_ms = (time.monotonic() - t0) * 1000.0
            raw = b"".join(raw_chunks)
            services = _extract_service_names(raw)
            return Response(
                status_code=200,
                body={"services": services},
                latency_ms=latency_ms,
            )

        except grpc.aio.AioRpcError as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            code = exc.code()
            http_code = _grpc_status_to_http(code)
            return Response(
                status_code=http_code,
                body=None,
                latency_ms=latency_ms,
                error=f"{code}: {exc.details()}",
            )
        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=504,
                body=None,
                latency_ms=latency_ms,
                error=f"timeout after {self.timeout}s",
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=503,
                body=None,
                latency_ms=latency_ms,
                error=str(exc),
            )

    async def _unary_call(
        self,
        method: str,
        request_bytes: bytes = b"",
    ) -> Response:
        """
        Make one unary gRPC call with raw bytes, without generated stubs.

        Args:
            method:        Fully-qualified method path, e.g.
                           "/grpc.health.v1.Health/Check"
            request_bytes: Serialised protobuf request (empty = default probe).

        Returns:
            Normalised Response.
        """
        t0 = time.monotonic()
        try:
            if self._use_tls:
                credentials = grpc.ssl_channel_credentials()
                channel = grpc.aio.secure_channel(self._channel_target, credentials)
            else:
                channel = grpc.aio.insecure_channel(self._channel_target)

            async with channel:
                stub = channel.unary_unary(
                    method,
                    request_serializer=lambda b: b,
                    response_deserializer=lambda b: b,
                )
                response_bytes: bytes = await stub(
                    request_bytes,
                    timeout=self.timeout,
                    metadata=self._build_metadata(),
                )

            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=200,
                body=response_bytes,
                latency_ms=latency_ms,
            )

        except grpc.aio.AioRpcError as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            code = exc.code()
            http_code = _grpc_status_to_http(code)
            return Response(
                status_code=http_code,
                body=None,
                latency_ms=latency_ms,
                error=f"{code}: {exc.details()}",
            )
        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=504,
                body=None,
                latency_ms=latency_ms,
                error=f"timeout after {self.timeout}s",
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=503,
                body=None,
                latency_ms=latency_ms,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_metadata(self) -> list[tuple[str, str]]:
        """Build gRPC call metadata (auth token, user-agent)."""
        metadata: list[tuple[str, str]] = [
            ("user-agent", "fynor-reliability-checker/1.0"),
        ]
        if self._auth_token:
            metadata.append(("authorization", f"Bearer {self._auth_token}"))
        return metadata

    @staticmethod
    def _normalise_method(method: str) -> str:
        """Ensure method path starts with '/'."""
        return method if method.startswith("/") else f"/{method}"

    def _default_probe_payload(self) -> dict:
        return {}
