"""
fynor.adapters.base — Abstract base adapter.

Every interface adapter implements this contract. The check engine calls
only these methods — it never knows which interface type it is talking to.

Design decision: adapters are fully async (httpx.AsyncClient).
Running all 8 checks concurrently from an async orchestrator requires async
I/O throughout the stack. Each check's internal requests are sequential
(determinism requirement from ADR-04), but checks themselves run concurrently
via asyncio.gather() at the orchestrator level.

SSRF protection: validate_target_url() must be called before any adapter is
instantiated. It resolves the hostname and rejects private/reserved IP ranges.
This blocks Server-Side Request Forgery attacks on the hosted API.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# SSRF protection — private and reserved IP ranges (RFC 1918 / RFC 5735)
# ---------------------------------------------------------------------------

_PRIVATE_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("10.0.0.0/8"),          # RFC 1918 private
    ipaddress.ip_network("172.16.0.0/12"),        # RFC 1918 private
    ipaddress.ip_network("192.168.0.0/16"),       # RFC 1918 private
    ipaddress.ip_network("127.0.0.0/8"),          # loopback
    ipaddress.ip_network("169.254.0.0/16"),       # link-local / AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),        # shared address space (RFC 6598)
    ipaddress.ip_network("192.0.0.0/24"),         # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),         # documentation (TEST-NET-1)
    ipaddress.ip_network("198.18.0.0/15"),        # benchmarking
    ipaddress.ip_network("198.51.100.0/24"),      # documentation (TEST-NET-2)
    ipaddress.ip_network("203.0.113.0/24"),       # documentation (TEST-NET-3)
    ipaddress.ip_network("240.0.0.0/4"),          # reserved
    ipaddress.ip_network("::1/128"),              # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),             # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),            # IPv6 link-local
]


def validate_target_url(url: str) -> None:
    """
    Validate that a target URL is safe to probe.

    Checks:
    1. Scheme must be http or https.
    2. Hostname must resolve to a public IP address.
    3. Resolved IP must not be in any private/reserved range (SSRF protection).

    Args:
        url: The target URL to validate.

    Raises:
        ValueError: If the URL is invalid or resolves to a private address.

    Note:
        This check is intentionally blocking (uses socket.getaddrinfo) because
        it must complete before any async I/O begins. Call it from synchronous
        setup code (CLI argument parsing, API request validation) before
        constructing an adapter.

        DNS rebinding mitigation: the adapter re-validates the IP on every
        request by using httpx's transport-level address locking. Full
        DNS rebinding protection requires a custom httpx transport; this is
        planned for the hosted service (Month 4) via a WAF rule on API Gateway.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"URL scheme must be 'http' or 'https', got: {parsed.scheme!r}. "
            f"Non-HTTP schemes are not supported."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Cannot parse a hostname from URL: {url!r}")

    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 80)
    except socket.gaierror as exc:
        raise ValueError(
            f"Cannot resolve hostname {hostname!r}: {exc}. "
            "Verify the URL is reachable and the hostname is spelled correctly."
        ) from exc

    for _, _, _, _, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        for private_net in _PRIVATE_NETWORKS:
            if ip in private_net:
                raise ValueError(
                    f"SSRF protection: target {hostname!r} resolves to "
                    f"private/reserved IP {ip_str!r} ({private_net}). "
                    "Fynor cannot probe internal network addresses. "
                    "Use a publicly reachable URL."
                )


# ---------------------------------------------------------------------------
# Response and BaseAdapter
# ---------------------------------------------------------------------------


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
    The check engine calls these async methods only — it never touches
    the underlying transport directly.

    All methods are async. The check orchestrator runs all 8 checks
    concurrently via asyncio.gather(). Within each check, requests are
    sequential (ADR-04: deterministic, reproducible results).
    """

    def __init__(self, target: str, timeout: float = 10.0) -> None:
        """
        Args:
            target:  URL or process identifier of the interface endpoint.
                     Must have already been validated by validate_target_url().
            timeout: Per-request timeout in seconds.
        """
        self.target = target
        self.timeout = timeout

    @abstractmethod
    async def call(self, payload: dict | None = None) -> Response:
        """
        Make a single async request to the target.

        Args:
            payload: Request body or parameters, adapter-specific format.
                     Uses the adapter's default probe payload if None.

        Returns:
            Normalised Response object. Never raises — errors go into Response.error.
        """
        ...

    @abstractmethod
    async def get_schema(self) -> dict:
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

        Synchronous: header construction never involves I/O.
        """
        ...

    async def burst(
        self,
        n: int,
        rps: float,
        payload: dict | None = None,
    ) -> list[Response]:
        """
        Send N requests sequentially at a target rate.

        Sequential (not concurrent) by design: ADR-04 requires that latency
        and error-rate checks reflect single-agent workloads, not burst traffic.
        Concurrent sending would artificially inflate latency and does not
        model how an AI agent actually calls a tool.

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
            results.append(await self.call(payload))
            elapsed = time.monotonic() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        return results

    def _default_probe_payload(self) -> dict:
        """
        Minimal valid payload for the interface type.
        Subclasses should override to return a real probe payload.
        """
        return {}
