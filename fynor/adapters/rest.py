"""
fynor.adapters.rest — REST API adapter.

Implements BaseAdapter for REST/HTTP JSON APIs.
Ships: v0.2 (Month 9)
"""

from __future__ import annotations

import time

import httpx

from fynor.adapters.base import BaseAdapter, Response


class RESTAdapter(BaseAdapter):
    """
    Adapter for REST APIs (HTTP + JSON).

    Supports GET and POST probing. The check engine calls call()
    for all 8 checks — the adapter handles the HTTP transport.
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
            timeout:     Request timeout in seconds.
            method:      HTTP method to use for probe requests (GET or POST).
            auth_token:  Bearer token for authenticated APIs.
            probe_path:  Path to probe (e.g. /health, /api/v1/ping).
        """
        super().__init__(target, timeout)
        self._method = method.upper()
        self._auth_token = auth_token
        self._probe_path = probe_path.lstrip("/")
        self._client = httpx.Client(timeout=timeout)

    @property
    def _probe_url(self) -> str:
        base = self.target.rstrip("/")
        return f"{base}/{self._probe_path}" if self._probe_path else base

    def call(self, payload: dict | None = None) -> Response:
        headers = self._build_headers()
        t0 = time.monotonic()
        try:
            if self._method == "POST":
                r = self._client.post(self._probe_url, json=payload or {}, headers=headers)
            else:
                r = self._client.get(self._probe_url, headers=headers)

            latency_ms = (time.monotonic() - t0) * 1000.0
            body: dict | str
            try:
                body = r.json()
            except Exception:  # noqa: BLE001
                body = r.text

            return Response(
                status_code=r.status_code,
                body=body,
                headers=dict(r.headers),
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(status_code=0, body=None, latency_ms=latency_ms,
                            error=f"timeout after {self.timeout}s: {exc}")
        except Exception as exc:  # noqa: BLE001
            return Response(status_code=0, body=None,
                            latency_ms=(time.monotonic() - t0) * 1000.0, error=str(exc))

    def get_schema(self) -> dict:
        """Attempt to retrieve OpenAPI schema from /openapi.json or /schema."""
        base = self.target.rstrip("/")
        for path in ("/openapi.json", "/schema", "/api-docs"):
            try:
                r = self._client.get(f"{base}{path}", timeout=5.0)
                if r.status_code == 200:
                    return r.json()
            except Exception:  # noqa: BLE001
                continue
        return {}

    def get_auth_headers(self) -> dict[str, str]:
        return self._build_headers()

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    def __del__(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass
