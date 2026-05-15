"""
fynor.api.badges — SVG badge generation for Agent-Ready certificates.

Badges are pre-rendered SVGs stored in S3 and served via CloudFront.
Badge URL: https://badge.fynor.tech/{cert_id}.svg
SLA: < 200ms globally (CloudFront cache TTL: 300s).

Badge states (certification-loop-contract.md):
  CERTIFIED (Grade A): Green  — "Agent-Ready · A"
  CERTIFIED (Grade B): Blue   — "Agent-Ready · B"
  CERTIFIED (Grade C): Yellow — "Agent-Ready · C"
  PENDING:             Grey   — "Pending Certification"
  SUSPENDED:           Red    — "Suspended"
  REVOKED:             Dark   — "Revoked"
  NOT_FOUND:           Grey   — "Not Found" (never 404 — breaks README embeds)

Badge format: Shields.io-compatible flat SVG (128×20px, standard shape).
"""

from __future__ import annotations

from typing import Literal

BadgeState = Literal["CERTIFIED", "PENDING", "SUSPENDED", "REVOKED", "NOT_FOUND"]

_COLORS: dict[str, str] = {
    "green":  "#3fb950",
    "blue":   "#0ea5e9",
    "yellow": "#d29922",
    "red":    "#f85149",
    "dark":   "#444d56",
    "grey":   "#6e7681",
}

_STATE_COLORS: dict[str, str] = {
    "CERTIFIED_A":  _COLORS["green"],
    "CERTIFIED_B":  _COLORS["blue"],
    "CERTIFIED_C":  _COLORS["yellow"],
    "PENDING":      _COLORS["grey"],
    "SUSPENDED":    _COLORS["red"],
    "REVOKED":      _COLORS["dark"],
    "NOT_FOUND":    _COLORS["grey"],
}

_LABEL = "fynor"
_LABEL_WIDTH = 46   # pixels


def _badge_svg(label: str, message: str, color: str) -> str:
    """
    Render a flat Shields.io-style SVG badge.

    Args:
        label:   Left panel text (always "fynor").
        message: Right panel text (e.g. "Agent-Ready · A").
        color:   Right panel background color (hex).
    """
    msg_width = max(len(message) * 7, 60)   # rough char-width estimate
    total_width = _LABEL_WIDTH + msg_width
    msg_x = _LABEL_WIDTH + msg_width // 2

    return f"""\
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{total_width}" height="20" role="img" aria-label="{label}: {message}">
  <title>{label}: {message}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{_LABEL_WIDTH}" height="20" fill="#555"/>
    <rect x="{_LABEL_WIDTH}" width="{msg_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle"
     font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="110">
    <text x="{_LABEL_WIDTH // 2 * 10}" y="150" fill="#010101"
          fill-opacity=".3" transform="scale(.1)" textLength="{(_LABEL_WIDTH - 10) * 10}"
          lengthAdjust="spacing">{label}</text>
    <text x="{_LABEL_WIDTH // 2 * 10}" y="140" transform="scale(.1)"
          textLength="{(_LABEL_WIDTH - 10) * 10}"
          lengthAdjust="spacing">{label}</text>
    <text x="{msg_x * 10}" y="150" fill="#010101"
          fill-opacity=".3" transform="scale(.1)" textLength="{(msg_width - 10) * 10}"
          lengthAdjust="spacing">{message}</text>
    <text x="{msg_x * 10}" y="140" transform="scale(.1)"
          textLength="{(msg_width - 10) * 10}"
          lengthAdjust="spacing">{message}</text>
  </g>
</svg>"""


def generate_badge(status: BadgeState, grade: str | None = None) -> str:
    """
    Generate an SVG badge for the given certification state.

    Args:
        status: Certification status (CERTIFIED, PENDING, SUSPENDED, REVOKED, NOT_FOUND).
        grade:  Grade letter (A, B, C) — only used when status is CERTIFIED.

    Returns:
        SVG string ready to write to S3 / serve over HTTP.
    """
    if status == "CERTIFIED" and grade in ("A", "B", "C"):
        color_key = f"CERTIFIED_{grade}"
        color = _STATE_COLORS.get(color_key, _COLORS["green"])
        message = f"Agent-Ready · {grade}"
    elif status == "PENDING":
        color = _STATE_COLORS["PENDING"]
        message = "Pending"
    elif status == "SUSPENDED":
        color = _STATE_COLORS["SUSPENDED"]
        message = "Suspended"
    elif status == "REVOKED":
        color = _STATE_COLORS["REVOKED"]
        message = "Revoked"
    else:
        # NOT_FOUND or unknown — serve a grey badge, never 404.
        # A 404 breaks GitHub README badge display.
        color = _STATE_COLORS["NOT_FOUND"]
        message = "Not Found"

    return _badge_svg(label=_LABEL, message=message, color=color)


def badge_content_type() -> str:
    """MIME type for SVG responses."""
    return "image/svg+xml; charset=utf-8"


def badge_cache_headers() -> dict[str, str]:
    """Cache headers for CloudFront — 300s TTL per SLA."""
    return {
        "Cache-Control": "public, max-age=300",
        "Content-Type": badge_content_type(),
    }
