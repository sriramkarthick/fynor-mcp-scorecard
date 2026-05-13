"""
fynor.adapters.rest — REST API adapter.

Implements BaseAdapter for REST/HTTP JSON APIs.
Ships: v0.2 (Month 9)
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from fynor.adapters.base import BaseAdapter, Response


class RESTAdapter(BaseAdapter):
    """
    Adapter for REST APIs (HTTP + JSON).

    Supports GET and POST probing. The check engine calls call()
    for all 8 checks — the adapter handles the HTTP transport.

    All methods are async (httpx.AsyncClient).
    """

    def __init__(
        self,
        target: str,
        timeout: float = 10.0,
        method: str = "GET",
        auth_token: str | None = None,
        probe_path: str = "/",
    ) -> None:
        """
        Args:
            target:      Base URL of the REST API (e.g. https://api.example.com).
                         Must be pre-validated via validate_target_url().
            timeout:     Per-request timeout in seconds.
            method:      HTTP method to use for probe requests (GET or POST).
            auth_token:  Bearer token for authenticated APIs.
            probe_path:  Path to probe (e.g. /health, /api/v1/ping).
        """
        super().__init__(target, timeout)
        self._method = method.upper()
        self._auth_token = auth_token
        self._probe_path = probe_path.lstrip("/")

    @property
    def _probe_url(self) -> str:
        base = self.target.rstrip("/")
        return f"{base}/{self._probe_path}" if self._probe_path else base

    async def call(self, payload: dict | None = None) -> Response:
        headers = self._build_headers()
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self._method == "POST":
                    r = await client.post(
                        self._probe_url,
                        json=payload or {},
                        headers=headers,
                    )
                else:
                    r = await client.get(self._probe_url, headers=headers)

            latency_ms = (time.monotonic() - t0) * 1000.0
            body: dict | str = _safe_json(r)
            return Response(
                status_code=r.status_code,
                body=body,
                headers=dict(r.headers),
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=0, body=None, latency_ms=latency_ms,
                error=f"timeout after {self.timeout}s: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            return Response(
                status_code=0, body=None,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                error=str(exc),
            )

    async def get_schema(self) -> dict:
        """Attempt to retrieve OpenAPI schema from /openapi.json or /schema."""
        base = self.target.rstrip("/")
        async with httpx.AsyncClient(timeout=5.0) as client:
            for path in ("/openapi.json", "/schema", "/api-docs"):
                try:
                    r = await client.get(f"{base}{path}")
                    if r.status_code == 200:
                        return _safe_json(r) if isinstance(_safe_json(r), dict) else {}
                except Exception:  # noqa: BLE001
                    continue
        return {}

    def get_auth_headers(self) -> dict[str, str]:
        return self._build_headers()

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
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
