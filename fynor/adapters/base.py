"""
fynor.adapters.base — Abstract base adapter.

Every interface adapter implements this contract. The check engine calls
only these methods — it never knows which interface type it is talking to.

Design decision: adapters are synchronous by default (uses httpx in sync mode).
Async support will be added in v0.3 when WebSocket requires it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Response:
    """Normalised response from any interface adapter."""

    status_code: int                    # HTTP status or exit code equivalent
    body: dict | str | bytes | None     # Parsed JSON dict, raw string, or bytes
    headers: dict[str, str] = field(default_factory=dict)
    latency_ms: float = 0.0             # Round-trip time in milliseconds
    error: str | None = None            # Set when the call itself failed (timeout, conn refused)

    @property
    def ok(self) -> bool:
        """True when the call succeeded at the transport layer (2xx or equivalent)."""
        return self.error is None and 200 <= self.status_code < 300


class BaseAdapter(ABC):
    """
    Abstract interface adapter.

    Subclass this for each interface type (MCP, REST, GraphQL, …).
    The check engine calls these methods only — it never touches the
    underlying transport directly.
    """

    def __init__(self, target: str, timeout: float = 10.0) -> None:
        """
        Args:
            target:  URL or process identifier of the interface endpoint.
            timeout: Request timeout in seconds.
        """
        self.target = target
        self.timeout = timeout

    @abstractmethod
    def call(self, payload: dict) -> Response:
        """
        Make a single request to the target.

        Args:
            payload: Request body or parameters, adapter-specific format.

        Returns:
            Normalised Response object. Never raises — errors go into Response.error.
        """
        ...

    @abstractmethod
    def get_schema(self) -> dict:
        """
        Retrieve the interface schema declaration.

        For MCP: the JSON Schema from the MCP spec.
        For REST: OpenAPI / JSON Schema from /schema or equivalent.
        For GraphQL: introspection result.
        For gRPC: proto descriptor.
        For CLI: --help output parsed into a dict.

        Returns:
            Schema as a dict. Empty dict if not available.
        """
        ...

    @abstractmethod
    def get_auth_headers(self) -> dict[str, str]:
        """
        Return current auth headers for one request.

        Used by auth_token check to verify correct credential handling.
        Returns empty dict for unauthenticated endpoints.
        """
        ...

    def burst(self, n: int, rps: float, payload: dict | None = None) -> list[Response]:
        """
        Send N requests at a target rate.

        Used by latency_p95, error_rate, and rate_limit checks.

        Args:
            n:       Number of requests to send.
            rps:     Target requests per second. Actual rate is best-effort.
            payload: Request payload. Uses default probe payload if None.

        Returns:
            List of Response objects in send order.
        """
        import time

        payload = payload or self._default_probe_payload()
        results: list[Response] = []
        interval = 1.0 / rps if rps > 0 else 0.0

        for _ in range(n):
            t0 = time.monotonic()
            results.append(self.call(payload))
            elapsed = time.monotonic() - t0
            sleep = interval - elapsed
            if sleep > 0:
                time.sleep(sleep)

        return results

    def _default_probe_payload(self) -> dict:
        """
        Minimal valid payload for the interface type.
        Subclasses should override to return a real probe payload.
        """
        return {}
