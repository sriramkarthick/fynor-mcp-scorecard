"""
fynor.adapters.websocket — WebSocket adapter.

Implements BaseAdapter for WebSocket endpoints using the `websockets` library
(async-native, built on asyncio).

Decision D2 (plan-eng-review 2026-05-15) — keepalive fix:
  The old design checked whether the server sent a ping within 60 seconds.
  This was structurally broken: the total pipeline timeout is 45 seconds,
  so the 60-second check could never pass. The fix:

  1. The adapter sends a PING frame and measures time-to-PONG (active probe).
  2. The keepalive interval defaults to 10 seconds.
  3. The interval is overridable by the server's X-Keepalive-Interval response
     header (negotiated interval). This lets servers advertise their actual
     ping cadence without Fynor imposing an arbitrary fixed value.
  4. The measured PONG latency (not the server's ping arrival) is what's
     compared against the interval — we control the probe timing.

Target format accepted:
  "ws://host/path"    — plaintext WebSocket
  "wss://host/path"   — TLS WebSocket
  "http://host/path"  — converted to ws:// silently
  "https://host/path" — converted to wss:// silently
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import websockets.asyncio.client as ws_client
import websockets.exceptions

from fynor.adapters.base import BaseAdapter, Response

# Default keepalive probe interval (seconds).
# 10s chosen so it fits comfortably within the 45s pipeline timeout.
_DEFAULT_KEEPALIVE_INTERVAL: float = 10.0

# Maximum negotiated interval — must be less than pipeline timeout (45s)
_MAX_KEEPALIVE_INTERVAL: float = 30.0

# Minimum negotiated interval — sub-second keepalives are not realistic
_MIN_KEEPALIVE_INTERVAL: float = 1.0


def _parse_keepalive_interval(headers: dict[str, str]) -> float:
    """
    Read the server's advertised keepalive interval from response headers.

    Looks for: X-Keepalive-Interval (value in seconds, e.g. "10" or "10s").

    Returns:
        Server-negotiated interval clamped to [1.0, 30.0], or the 10s default
        when the header is absent or malformed.
    """
    raw = headers.get("x-keepalive-interval") or headers.get("X-Keepalive-Interval")
    if not raw:
        return _DEFAULT_KEEPALIVE_INTERVAL

    # Strip optional 's' suffix ("25s" → "25")
    raw = raw.strip().rstrip("s").strip()
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_KEEPALIVE_INTERVAL

    return max(_MIN_KEEPALIVE_INTERVAL, min(_MAX_KEEPALIVE_INTERVAL, value))


def _to_ws_uri(target: str) -> str:
    """
    Convert an HTTP(S) URL or bare ws(s) URL to a WebSocket URI.

    ws:// and wss:// are returned unchanged.
    http:// is converted to ws://; https:// to wss://.
    """
    if target.startswith("http://"):
        return "ws://" + target[len("http://"):]
    if target.startswith("https://"):
        return "wss://" + target[len("https://"):]
    return target  # already ws:// or wss://


class WebSocketAdapter(BaseAdapter):
    """
    Adapter for WebSocket endpoints.

    Uses the `websockets` library (async-native). All methods are coroutines.

    Args:
        target:      WebSocket endpoint URL — ws://, wss://, http://, or https://.
                     Must be pre-validated via validate_target_url().
        timeout:     Per-operation timeout in seconds (connect + message round trip).
        auth_token:  Bearer token sent as the Authorization header on upgrade.
        probe_message: Message to send on each call() probe. Defaults to "ping".
    """

    def __init__(
        self,
        target: str,
        timeout: float = 10.0,
        auth_token: str | None = None,
        probe_message: str = "ping",
    ) -> None:
        super().__init__(target, timeout)
        self._auth_token = auth_token
        self._probe_message = probe_message
        self._ws_uri = _to_ws_uri(target)
        # Negotiated keepalive interval — updated when we see the server header
        self.negotiated_keepalive_interval: float = _DEFAULT_KEEPALIVE_INTERVAL

    # ------------------------------------------------------------------
    # BaseAdapter interface
    # ------------------------------------------------------------------

    async def call(self, payload: dict | None = None) -> Response:
        """
        Open a WebSocket connection, send the probe message, receive one reply.

        Args:
            payload: Ignored — WebSocket probes use a fixed text message.

        Returns:
            Normalised Response. status_code 200 on success, 503/504 on failure.
        """
        headers = self._build_extra_headers()
        t0 = time.monotonic()
        try:
            async with ws_client.connect(
                self._ws_uri,
                additional_headers=headers,
                open_timeout=self.timeout,
                ping_interval=None,   # We control pings ourselves in _measure_ping_pong
                close_timeout=3.0,
                user_agent_header="Fynor-Reliability-Checker/1.0",
            ) as ws:
                # Capture server headers for keepalive negotiation
                response_headers = dict(ws.response.headers)
                self.negotiated_keepalive_interval = _parse_keepalive_interval(
                    response_headers
                )

                await ws.send(self._probe_message)
                reply = await asyncio.wait_for(ws.recv(), timeout=self.timeout)

            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=200,
                body=reply if isinstance(reply, str) else reply.decode("utf-8", errors="replace"),
                headers=response_headers,
                latency_ms=latency_ms,
            )

        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=504,
                body=None,
                latency_ms=latency_ms,
                error=f"timeout after {self.timeout}s",
            )
        except websockets.exceptions.WebSocketException as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=503,
                body=None,
                latency_ms=latency_ms,
                error=str(exc),
            )
        except OSError as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=503,
                body=None,
                latency_ms=latency_ms,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=503,
                body=None,
                latency_ms=latency_ms,
                error=str(exc),
            )

    async def get_schema(self) -> dict:
        """
        WebSocket connections do not expose a schema endpoint by default.

        Returns an empty dict — schema information is not applicable for
        most WebSocket APIs. If the server has a capability negotiation
        protocol (e.g. STOMP frames, Socket.IO handshake), a subclass
        should override this method.
        """
        return {}

    def get_auth_headers(self) -> dict[str, str]:
        """Return auth headers as a dict (for interface compatibility)."""
        if self._auth_token:
            return {"Authorization": f"Bearer {self._auth_token}"}
        return {}

    # ------------------------------------------------------------------
    # WebSocket-specific methods used by checks
    # ------------------------------------------------------------------

    async def _measure_ping_pong(self) -> Response:
        """
        Open a connection, send a WebSocket PING control frame, and measure
        time-to-PONG.

        Uses the negotiated keepalive interval as the deadline. If no PONG
        arrives within the deadline, returns a 504 timeout response.

        Returns:
            Response with:
              status_code=200, body={"pong_latency_ms": float}  — PONG received
              status_code=504, error=...                         — timeout
              status_code=503, error=...                         — connection failure
        """
        headers = self._build_extra_headers()
        deadline = self.negotiated_keepalive_interval

        t0 = time.monotonic()
        try:
            async with ws_client.connect(
                self._ws_uri,
                additional_headers=headers,
                open_timeout=self.timeout,
                ping_interval=None,   # Manual ping control
                close_timeout=3.0,
                user_agent_header="Fynor-Reliability-Checker/1.0",
            ) as ws:
                # Update negotiated interval from server headers
                response_headers = dict(ws.response.headers)
                self.negotiated_keepalive_interval = _parse_keepalive_interval(
                    response_headers
                )
                deadline = self.negotiated_keepalive_interval

                # Send a PING frame and await the PONG future
                ping_t0 = time.monotonic()
                pong_waiter = await ws.ping()
                await asyncio.wait_for(pong_waiter, timeout=deadline)
                pong_latency_ms = (time.monotonic() - ping_t0) * 1000.0

            total_latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=200,
                body={"pong_latency_ms": round(pong_latency_ms, 2)},
                latency_ms=total_latency_ms,
            )

        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=504,
                body=None,
                latency_ms=latency_ms,
                error=(
                    f"timeout: no PONG received within "
                    f"{deadline:.1f}s keepalive interval"
                ),
            )
        except websockets.exceptions.WebSocketException as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=503,
                body=None,
                latency_ms=latency_ms,
                error=str(exc),
            )
        except OSError as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Response(
                status_code=503,
                body=None,
                latency_ms=latency_ms,
                error=str(exc),
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

    def _build_extra_headers(self) -> dict[str, str]:
        """Build HTTP upgrade headers (auth token, user-agent)."""
        headers: dict[str, str] = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    def _default_probe_payload(self) -> dict:
        return {}
