"""
tests/certification/test_badge.py — Tests for SVG badge generation.

Covers all states from certification-loop-contract.md:
  CERTIFIED (A/B/C), PENDING, SUSPENDED, REVOKED, NOT_FOUND
and the cache/content-type helpers.
"""

from __future__ import annotations

import pytest

from fynor.api.badges import (
    BadgeState,
    badge_cache_headers,
    badge_content_type,
    generate_badge,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_svg(text: str) -> bool:
    """Quick check that output looks like an SVG document."""
    return text.strip().startswith("<svg") and "</svg>" in text


# ---------------------------------------------------------------------------
# generate_badge — output format
# ---------------------------------------------------------------------------

class TestGenerateBadgeFormat:

    def test_returns_string(self):
        result = generate_badge("CERTIFIED", grade="A")
        assert isinstance(result, str)

    def test_output_is_svg(self):
        assert _is_svg(generate_badge("CERTIFIED", grade="A"))

    def test_svg_has_title_element(self):
        svg = generate_badge("CERTIFIED", grade="A")
        assert "<title>" in svg and "</title>" in svg

    def test_svg_has_aria_label(self):
        svg = generate_badge("PENDING")
        assert 'aria-label=' in svg

    def test_svg_has_width_and_height(self):
        svg = generate_badge("SUSPENDED")
        assert 'width=' in svg and 'height="20"' in svg


# ---------------------------------------------------------------------------
# CERTIFIED — grade variants
# ---------------------------------------------------------------------------

class TestCertifiedBadges:

    @pytest.mark.parametrize("grade,color_fragment", [
        ("A", "#3fb950"),   # green
        ("B", "#0ea5e9"),   # blue
        ("C", "#d29922"),   # yellow
    ])
    def test_certified_grade_colors(self, grade: str, color_fragment: str):
        svg = generate_badge("CERTIFIED", grade=grade)
        assert color_fragment in svg

    @pytest.mark.parametrize("grade", ["A", "B", "C"])
    def test_certified_message_contains_grade(self, grade: str):
        svg = generate_badge("CERTIFIED", grade=grade)
        assert grade in svg

    @pytest.mark.parametrize("grade", ["A", "B", "C"])
    def test_certified_message_agent_ready(self, grade: str):
        svg = generate_badge("CERTIFIED", grade=grade)
        assert "Agent-Ready" in svg

    def test_certified_no_grade_falls_back_to_not_found(self):
        """CERTIFIED without a valid grade → NOT_FOUND (grey) fallback."""
        svg = generate_badge("CERTIFIED", grade=None)
        assert "#6e7681" in svg   # grey
        assert "Not Found" in svg

    def test_certified_invalid_grade_falls_back(self):
        """Grade 'D' is not valid → fallback to NOT_FOUND."""
        svg = generate_badge("CERTIFIED", grade="D")  # type: ignore[arg-type]
        assert "Not Found" in svg


# ---------------------------------------------------------------------------
# Non-certified states
# ---------------------------------------------------------------------------

class TestOtherStates:

    def test_pending_grey(self):
        svg = generate_badge("PENDING")
        assert "#6e7681" in svg

    def test_pending_message(self):
        svg = generate_badge("PENDING")
        assert "Pending" in svg

    def test_suspended_red(self):
        svg = generate_badge("SUSPENDED")
        assert "#f85149" in svg

    def test_suspended_message(self):
        svg = generate_badge("SUSPENDED")
        assert "Suspended" in svg

    def test_revoked_dark(self):
        svg = generate_badge("REVOKED")
        assert "#444d56" in svg

    def test_revoked_message(self):
        svg = generate_badge("REVOKED")
        assert "Revoked" in svg

    def test_not_found_grey(self):
        svg = generate_badge("NOT_FOUND")
        assert "#6e7681" in svg

    def test_not_found_message(self):
        svg = generate_badge("NOT_FOUND")
        assert "Not Found" in svg

    def test_not_found_is_svg_not_404(self):
        """Critical: NOT_FOUND must still return a valid SVG, never an error."""
        svg = generate_badge("NOT_FOUND")
        assert _is_svg(svg)


# ---------------------------------------------------------------------------
# Label
# ---------------------------------------------------------------------------

class TestBadgeLabel:

    @pytest.mark.parametrize("status,grade", [
        ("CERTIFIED", "A"),
        ("PENDING", None),
        ("SUSPENDED", None),
        ("REVOKED", None),
        ("NOT_FOUND", None),
    ])
    def test_label_always_fynor(self, status: BadgeState, grade: str | None):
        svg = generate_badge(status, grade=grade)
        assert "fynor" in svg


# ---------------------------------------------------------------------------
# badge_content_type
# ---------------------------------------------------------------------------

class TestBadgeContentType:

    def test_returns_svg_mime(self):
        ct = badge_content_type()
        assert "image/svg+xml" in ct

    def test_includes_charset(self):
        ct = badge_content_type()
        assert "utf-8" in ct.lower()


# ---------------------------------------------------------------------------
# badge_cache_headers
# ---------------------------------------------------------------------------

class TestBadgeCacheHeaders:

    def test_returns_dict(self):
        headers = badge_cache_headers()
        assert isinstance(headers, dict)

    def test_cache_control_public(self):
        headers = badge_cache_headers()
        assert "Cache-Control" in headers
        assert "public" in headers["Cache-Control"]

    def test_cache_control_max_age_300(self):
        headers = badge_cache_headers()
        assert "max-age=300" in headers["Cache-Control"]

    def test_content_type_in_headers(self):
        headers = badge_cache_headers()
        assert "Content-Type" in headers
        assert "image/svg+xml" in headers["Content-Type"]
