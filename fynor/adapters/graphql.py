"""
fynor.adapters.graphql — GraphQL API adapter.

Implements BaseAdapter for GraphQL endpoints. Probes via HTTP POST with
an introspection query or a minimal operation query. Normalises responses
into the standard Response envelope for the check engine.

Note on introspection: most production GraphQL APIs disable introspection
(it exposes the full schema to any caller). When introspection is disabled,
schema-dependent checks return result="na" — disabling introspection is a
security best practice, not a failure. Decision D12 (plan-eng-review 2026-05-15).
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from fynor.adapters.base import BaseAdapter, Response

# Minimal introspection query — just enough to confirm introspection is enabled
# and fetch the top-level type list. Avoids fetching the entire schema (can be
# very large) while still proving introspection is functional.
_INTROSPECTION_QUERY = {
    "query": "{ __schema { types { name } } }",
}

# Minimal probe query — used when introspection is disabled.
# Sends an empty/noop query; any 200-level response confirms the server is alive.
_PROBE_QUERY = {
    "query": "{ __typename }",
}


class GraphQLAdapter(BaseAdapter):
    """
    Adapter for GraphQL APIs (HTTP POST + JSON).

    All methods are async (httpx.AsyncClient). A fresh client is created
    per call to avoid connection-pool state bleeding between checks.

    Args:
        target:      Full URL of the GraphQL endpoint (e.g. https://api.example.com/graphql).
                     Must be pre-validated via validate_target_url().
        timeout:     Per-request timeout in seconds.
        auth_token:  Bearer token for authenticated GraphQL APIs.
    """

    def __init__(
        self,
        target: str,
        timeout: float = 10.0,
        auth_token: str | None = None,
    ) -> None:
        super().__init__(target, timeout)
        self._auth_token = auth_token

    async def call(self, payload: dict | None = None) -> Response:
        """Send one GraphQL POST request to the endpoint."""
        body = payload if payload is not None else _PROBE_QUERY
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

    async def introspect(self) -> Response:
        """
        Send the introspection query to the endpoint.

        Returns the raw Response. The introspection check interprets:
        - 200 + data.__schema present → introspection enabled
        - 200 + errors present and no data → introspection disabled (na)
        - 400 / 403 → introspection disabled (na)
        - error → connectivity failure
        """
        return await self.call(_INTROSPECTION_QUERY)

    async def get_schema(self) -> dict:
        """
        Fetch the GraphQL schema via introspection.

        Returns the introspection result dict, or empty dict when
        introspection is disabled (not a failure — just not available).
        """
        r = await self.introspect()
        if not r.ok or not isinstance(r.body, dict):
            return {}
        data = r.body.get("data") or {}
        return data.get("__schema", {})

    def get_auth_headers(self) -> dict[str, str]:
        return self._build_headers()

    async def call_without_auth(self) -> Response:
        """Make a request with no auth headers (used by auth_token check)."""
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    self.target,
                    json=_PROBE_QUERY,
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
        return _PROBE_QUERY

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
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
