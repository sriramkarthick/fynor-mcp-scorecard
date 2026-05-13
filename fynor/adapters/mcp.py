"""
fynor.adapters.mcp — MCP server adapter.

Implements BaseAdapter for Model Context Protocol servers.
MCP uses JSON-RPC 2.0 over HTTP POST. Every request is a JSON-RPC call;
every response must conform to the MCP envelope schema.

Reference: https://spec.modelcontextprotocol.io
Ships: v0.1 (Month 6)
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from fynor.adapters.base import BaseAdapter, Response


class MCPAdapter(BaseAdapter):
    """
    Adapter for MCP (Model Context Protocol) servers.

    Sends JSON-RPC 2.0 requests and normalises the MCP envelope
    into a standard Response for the check engine.

    All methods are async (httpx.AsyncClient). A fresh client is created
    per call to avoid connection-pool state bleeding between checks.
    For burst() calls the parent class reuses this method sequentially,
    which is correct — each request is independent.
    """

    # Minimal JSON-RPC 2.0 probe — lists available tools
    _PROBE_PAYLOAD: dict = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }

    def __init__(
        self,
        target: str,
        timeout: float = 10.0,
        auth_token: str | None = None,
    ) -> None:
        """
        Args:
            target:     Full URL of the MCP server (e.g. http://localhost:8000/mcp).
                        Must be pre-validated via validate_target_url().
            timeout:    Per-request timeout in seconds.
            auth_token: Bearer token for authenticated MCP servers.
        """
        super().__init__(target, timeout)
        self._auth_token = auth_token

    async def call(self, payload: dict | None = None) -> Response:
        """Send one JSON-RPC 2.0 request to the MCP server."""
        body = payload if payload is not None else self._PROBE_PAYLOAD
        headers = self._build_headers()

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(self.target, json=body, headers=headers)
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=r.status_code,
                body=_safe_json(r),
                headers=dict(r.headers),
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=0,
                body=None,
                latency_ms=latency_ms,
                error=f"timeout after {self.timeout}s: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            return Response(
                status_code=0,
                body=None,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                error=str(exc),
            )

    async def get_schema(self) -> dict:
        """
        Retrieve the MCP server's tool schema via tools/list.

        Returns the full JSON-RPC result body, or empty dict on failure.
        """
        r = await self.call(self._PROBE_PAYLOAD)
        if not r.ok or not isinstance(r.body, dict):
            return {}
        return r.body.get("result", {})

    def get_auth_headers(self) -> dict[str, str]:
        """Return current auth headers (Bearer token if configured)."""
        return self._build_headers()

    async def call_without_auth(self) -> Response:
        """
        Make a request with no auth headers.

        Used by the auth_token check to verify the server correctly
        rejects unauthenticated requests with 401.
        """
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    self.target,
                    json=self._PROBE_PAYLOAD,
                    headers={"Content-Type": "application/json"},
                )
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=r.status_code,
                body=_safe_json(r),
                headers=dict(r.headers),
                latency_ms=latency_ms,
            )
        except Exception as exc:  # noqa: BLE001
            return Response(
                status_code=0,
                body=None,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                error=str(exc),
            )

    def _default_probe_payload(self) -> dict:
        return self._PROBE_PAYLOAD

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "Fynor-Reliability-Checker/1.0",
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers


def _safe_json(response: Any) -> dict | str:
    """Return parsed JSON or raw text. Never raises."""
    try:
        return response.json()
    except Exception:  # noqa: BLE001
        return response.text
