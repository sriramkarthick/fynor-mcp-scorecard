"""
tests/test_api_validators.py — Unit tests for fynor.api.validators.

Covers the web-API-specific scope restrictions:
  - validate_interface_type: "cli" must be rejected with a clear error
  - validate_check_options: "auth_token" must be rejected with a clear error
  - validate_interface_type: all valid types must be accepted
  - validate_check_options: legitimate options must still be accepted

Decision references:
  - D1 (plan-eng-review 2026-05-15): CLI removed from web tool
  - D5 (plan-eng-review 2026-05-15): auth_token disabled in web tool
"""

from __future__ import annotations

import pytest

from fynor.api.validators import validate_interface_type, validate_check_options


# ---------------------------------------------------------------------------
# validate_interface_type — T2 (CLI removal)
# ---------------------------------------------------------------------------

class TestValidateInterfaceType:

    def test_cli_rejected_with_actionable_message(self):
        """'cli' must be rejected with a message explaining the RCE risk and the alternative."""
        with pytest.raises(ValueError) as exc_info:
            validate_interface_type("cli")
        msg = str(exc_info.value)
        # Must mention the reason and the alternative
        assert "cli" in msg.lower()
        assert "pip install fynor" in msg or "local" in msg.lower()

    def test_cli_rejected_not_treated_as_unknown(self):
        """'cli' must give a specific error, not the generic 'unknown interface type' message."""
        with pytest.raises(ValueError) as exc_info:
            validate_interface_type("cli")
        # The generic "Supported types:" message should NOT appear — cli gets its own message
        assert "Supported types:" not in str(exc_info.value)

    @pytest.mark.parametrize("valid_type", ["mcp", "rest", "graphql", "grpc", "websocket"])
    def test_valid_types_accepted(self, valid_type: str):
        """All five web-supported types must be accepted without raising."""
        validate_interface_type(valid_type)  # Must not raise

    def test_soap_rejected(self):
        """'soap' must be rejected — no SOAP adapter is implemented."""
        with pytest.raises(ValueError, match="Supported types:"):
            validate_interface_type("soap")

    def test_unknown_type_rejected_with_supported_list(self):
        """Truly unknown types get the generic error listing supported types."""
        with pytest.raises(ValueError, match="Supported types:"):
            validate_interface_type("smtp")

    def test_unknown_type_does_not_list_cli(self):
        """CLI must not appear in the 'Supported types' list for unknown-type errors."""
        with pytest.raises(ValueError) as exc_info:
            validate_interface_type("smtp")
        assert "cli" not in str(exc_info.value).lower()

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError):
            validate_interface_type("")

    def test_case_sensitive(self):
        """Type names are lowercase; 'MCP' is not the same as 'mcp'."""
        with pytest.raises(ValueError):
            validate_interface_type("MCP")


# ---------------------------------------------------------------------------
# validate_check_options — T3 (auth_token disabled)
# ---------------------------------------------------------------------------

class TestValidateCheckOptions:

    def test_auth_token_rejected(self):
        """'auth_token' in options must raise with an actionable message."""
        with pytest.raises(ValueError) as exc_info:
            validate_check_options({"auth_token": "Bearer sk-123"})
        msg = str(exc_info.value)
        assert "auth_token" in msg
        assert "FYNOR_AUTH_TOKEN" in msg or "local" in msg.lower()

    def test_auth_token_rejected_even_if_valid_string(self):
        """Even a well-formed token must be rejected — not a format issue, a policy issue."""
        with pytest.raises(ValueError, match="auth_token"):
            validate_check_options({"auth_token": "x" * 32})

    def test_auth_token_rejected_alongside_other_valid_options(self):
        """auth_token must be rejected even when combined with otherwise valid options."""
        with pytest.raises(ValueError, match="auth_token"):
            validate_check_options({"timeout_ms": 5000, "auth_token": "Bearer token"})

    def test_auth_token_null_still_rejected(self):
        """Presence of the key is enough to trigger the error — value doesn't matter."""
        # The check is `if "auth_token" in options:` — None still triggers it.
        with pytest.raises(ValueError, match="auth_token"):
            validate_check_options({"auth_token": None})

    def test_empty_options_accepted(self):
        """Empty options dict is valid."""
        validate_check_options({})  # Must not raise

    def test_valid_timeout_ms_accepted(self):
        validate_check_options({"timeout_ms": 5000})  # Must not raise

    def test_valid_checks_subset_accepted(self):
        validate_check_options({"checks": ["latency_p95", "error_rate"]})  # Must not raise

    def test_timeout_ms_below_minimum_rejected(self):
        with pytest.raises(ValueError, match="timeout_ms"):
            validate_check_options({"timeout_ms": 500})

    def test_timeout_ms_above_maximum_rejected(self):
        with pytest.raises(ValueError, match="timeout_ms"):
            validate_check_options({"timeout_ms": 999_999})

    def test_unknown_check_name_rejected(self):
        with pytest.raises(ValueError, match="Unknown check names"):
            validate_check_options({"checks": ["latency_p95", "nonexistent_check"]})

    def test_options_must_be_dict(self):
        with pytest.raises(ValueError, match="JSON object"):
            validate_check_options("not a dict")  # type: ignore[arg-type]
