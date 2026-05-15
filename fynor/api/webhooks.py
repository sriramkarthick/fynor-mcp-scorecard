"""
fynor.api.webhooks — HMAC-signed webhook delivery.

Webhook payload is signed with HMAC-SHA256 using the account's webhook secret.
Receivers verify: hmac.compare_digest(computed_sig, header_sig).

Events (certification-loop-contract.md):
  check.completed    — every check run finishes
  cert.issued        — target first achieves CERTIFIED status
  cert.suspended     — CERTIFIED → SUSPENDED transition
  cert.reinstated    — SUSPENDED → CERTIFIED transition
  cert.revoked       — manual revocation

Delivery: async httpx call, 3 retries with exponential backoff (1s, 2s, 4s).
Timeout per attempt: 10 seconds.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any

import httpx

_MAX_RETRIES = 3
_TIMEOUT_S = 10.0
_BACKOFF_BASE = 1.0   # seconds — doubles each retry


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Return 'sha256=<hex>' HMAC-SHA256 signature."""
    digest = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def build_payload(event: str, data: dict[str, Any]) -> dict[str, Any]:
    """Assemble a standard webhook payload dict."""
    return {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }


async def deliver_webhook(
    url: str,
    payload: dict[str, Any],
    secret: str,
) -> bool:
    """
    Deliver a signed webhook payload to the given URL.

    Attempts up to 3 times with exponential backoff. Returns True on success
    (any 2xx response), False if all attempts fail.

    Signature header: ``Fynor-Signature: sha256=<hex>``
    """
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = _sign_payload(payload_bytes, secret)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Fynor-Webhook/1.0",
        "Fynor-Signature": signature,
    }

    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                r = await client.post(url, content=payload_bytes, headers=headers)
            if 200 <= r.status_code < 300:
                return True
            # 4xx: don't retry (misconfigured endpoint — retrying won't help)
            if 400 <= r.status_code < 500:
                return False
            # 5xx: retry
        except (httpx.TimeoutException, httpx.ConnectError):
            pass   # retry

        if attempt < _MAX_RETRIES - 1:
            backoff = _BACKOFF_BASE * (2 ** attempt)
            import asyncio
            await asyncio.sleep(backoff)

    return False


def verify_signature(payload_bytes: bytes, header_sig: str, secret: str) -> bool:
    """
    Verify an inbound webhook signature (for receiver-side validation).

    Use this in the receiving server — not in Fynor itself.
    Comparison is constant-time (hmac.compare_digest).
    """
    expected = _sign_payload(payload_bytes, secret)
    return hmac.compare_digest(expected, header_sig)
