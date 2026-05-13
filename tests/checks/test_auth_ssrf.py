"""
tests/checks/test_auth_ssrf.py — Unit tests for SSRF URL validation.

These tests do NOT make real DNS calls. Private IP validation is tested
via the ipaddress module directly. DNS-resolution tests use mock.patch.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from fynor.adapters.base import validate_target_url


# ---------------------------------------------------------------------------
# Scheme validation (no DNS calls needed)
# ---------------------------------------------------------------------------

def test_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="scheme must be 'http' or 'https'"):
        validate_target_url("ftp://example.com/resource")


def test_rejects_file_scheme():
    with pytest.raises(ValueError, match="scheme must be 'http' or 'https'"):
        validate_target_url("file:///etc/passwd")


def test_rejects_javascript_scheme():
    with pytest.raises(ValueError, match="scheme must be 'http' or 'https'"):
        validate_target_url("javascript:alert(1)")


def test_rejects_no_hostname():
    with pytest.raises(ValueError, match="Cannot parse a hostname"):
        validate_target_url("https://")


# ---------------------------------------------------------------------------
# Private IP rejection (mocked DNS)
# ---------------------------------------------------------------------------

def _mock_getaddrinfo(ip: str):
    """Return getaddrinfo mock that resolves to the given IP."""
    return [(None, None, None, None, (ip, 80))]


def test_rejects_localhost_127():
    with patch("socket.getaddrinfo", return_value=_mock_getaddrinfo("127.0.0.1")):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_target_url("http://localhost/mcp")


def test_rejects_rfc1918_10_range():
    with patch("socket.getaddrinfo", return_value=_mock_getaddrinfo("10.0.1.5")):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_target_url("http://internal-service.local/mcp")


def test_rejects_rfc1918_172_range():
    with patch("socket.getaddrinfo", return_value=_mock_getaddrinfo("172.20.0.1")):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_target_url("http://vpc.internal/mcp")


def test_rejects_rfc1918_192_168_range():
    with patch("socket.getaddrinfo", return_value=_mock_getaddrinfo("192.168.1.1")):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_target_url("http://router.local/mcp")


def test_rejects_aws_metadata_service():
    """169.254.169.254 is the AWS instance metadata endpoint — must be blocked."""
    with patch("socket.getaddrinfo", return_value=_mock_getaddrinfo("169.254.169.254")):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_target_url("http://some-hostname.example.com/latest/meta-data/")


def test_rejects_ipv6_loopback():
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("::1", 80, 0, 0))]):
        with pytest.raises(ValueError, match="private/reserved IP"):
            validate_target_url("http://[::1]/mcp")


def test_rejects_unresolvable_hostname():
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name not found")):
        with pytest.raises(ValueError, match="Cannot resolve hostname"):
            validate_target_url("http://this-does-not-exist.fynor-test.invalid/mcp")


# ---------------------------------------------------------------------------
# Valid public URLs (mocked DNS to avoid network in CI)
# ---------------------------------------------------------------------------

def test_accepts_public_ip():
    """Public IP (8.8.8.8) should be accepted."""
    with patch("socket.getaddrinfo", return_value=_mock_getaddrinfo("8.8.8.8")):
        validate_target_url("https://api.example.com/mcp")  # should not raise


def test_accepts_https():
    with patch("socket.getaddrinfo", return_value=_mock_getaddrinfo("93.184.216.34")):
        validate_target_url("https://example.com/mcp")  # should not raise
