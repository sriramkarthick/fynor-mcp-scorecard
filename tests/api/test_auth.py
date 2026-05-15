"""
tests/api/test_auth.py — Tests for fynor.api.auth

Covers key generation, hashing, verification, and the new_key_record helper.
All tests set the required FYNOR_HMAC_SECRET environment variable to a
32-byte test secret so _get_hmac_secret() never raises.
"""

from __future__ import annotations

import os
import uuid

import pytest

# Patch the secret before importing auth so _get_hmac_secret() succeeds.
_TEST_SECRET = "A" * 32   # 32-byte string — meets minimum length requirement
os.environ.setdefault("FYNOR_HMAC_SECRET", _TEST_SECRET)

from fynor.api.auth import (
    generate_api_key,
    hash_api_key,
    new_key_record,
    verify_api_key,
)


# ---------------------------------------------------------------------------
# generate_api_key
# ---------------------------------------------------------------------------

class TestGenerateApiKey:

    def test_returns_three_tuple(self):
        result = generate_api_key()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_raw_key_prefix(self):
        raw_key, _, _ = generate_api_key()
        assert raw_key.startswith("fynor_live_")

    def test_raw_key_minimum_length(self):
        """fynor_live_ + 32 bytes b64 ≈ 11 + 43 chars."""
        raw_key, _, _ = generate_api_key()
        assert len(raw_key) >= 40

    def test_key_hash_is_hex_string(self):
        _, key_hash, _ = generate_api_key()
        assert isinstance(key_hash, str)
        int(key_hash, 16)   # should not raise

    def test_key_hash_is_sha256_length(self):
        """SHA-256 hex digest is 64 characters."""
        _, key_hash, _ = generate_api_key()
        assert len(key_hash) == 64

    def test_key_prefix_is_12_chars(self):
        _, _, prefix = generate_api_key()
        assert len(prefix) == 12

    def test_key_prefix_matches_raw_key_start(self):
        raw_key, _, prefix = generate_api_key()
        assert raw_key.startswith(prefix)

    def test_two_keys_are_unique(self):
        raw1, hash1, _ = generate_api_key()
        raw2, hash2, _ = generate_api_key()
        assert raw1 != raw2
        assert hash1 != hash2

    def test_hash_of_raw_key_matches_returned_hash(self):
        """hash_api_key(raw) must equal the key_hash returned from generate."""
        raw_key, key_hash, _ = generate_api_key()
        assert hash_api_key(raw_key) == key_hash


# ---------------------------------------------------------------------------
# hash_api_key
# ---------------------------------------------------------------------------

class TestHashApiKey:

    def test_returns_string(self):
        result = hash_api_key("fynor_live_test_key_12345678901234")
        assert isinstance(result, str)

    def test_deterministic(self):
        key = "fynor_live_deterministic_test_key"
        assert hash_api_key(key) == hash_api_key(key)

    def test_different_keys_different_hashes(self):
        h1 = hash_api_key("fynor_live_aaaaaaaaaaaaaaaaaaaaaaaa")
        h2 = hash_api_key("fynor_live_bbbbbbbbbbbbbbbbbbbbbbbb")
        assert h1 != h2

    def test_hex_output(self):
        h = hash_api_key("fynor_live_hextest1234567890123456")
        int(h, 16)   # should not raise — must be pure hex

    def test_sha256_hex_length(self):
        h = hash_api_key("fynor_live_length_test_1234567890")
        assert len(h) == 64


# ---------------------------------------------------------------------------
# verify_api_key
# ---------------------------------------------------------------------------

class TestVerifyApiKey:

    def test_correct_key_verifies_true(self):
        raw_key, key_hash, _ = generate_api_key()
        assert verify_api_key(raw_key, key_hash) is True

    def test_wrong_key_verifies_false(self):
        _, key_hash, _ = generate_api_key()
        assert verify_api_key("fynor_live_wrong_key_aaaaaaaaaaaa", key_hash) is False

    def test_empty_key_verifies_false(self):
        _, key_hash, _ = generate_api_key()
        assert verify_api_key("", key_hash) is False

    def test_correct_key_wrong_hash_false(self):
        raw_key, _, _ = generate_api_key()
        _, other_hash, _ = generate_api_key()
        assert verify_api_key(raw_key, other_hash) is False

    def test_returns_bool(self):
        raw_key, key_hash, _ = generate_api_key()
        result = verify_api_key(raw_key, key_hash)
        assert isinstance(result, bool)

    def test_constant_time_comparison(self):
        """verify_api_key must use compare_digest — we check the output, not internals."""
        raw_key, key_hash, _ = generate_api_key()
        # Tampered hash: flip one character
        tampered = key_hash[:-1] + ("a" if key_hash[-1] != "a" else "b")
        assert verify_api_key(raw_key, tampered) is False


# ---------------------------------------------------------------------------
# new_key_record
# ---------------------------------------------------------------------------

class TestNewKeyRecord:

    @pytest.fixture
    def sample_record(self) -> dict:
        raw_key, key_hash, key_prefix = generate_api_key()
        account_id = str(uuid.uuid4())
        return new_key_record(raw_key, key_hash, key_prefix, account_id, "pro")

    def test_returns_dict(self, sample_record: dict):
        assert isinstance(sample_record, dict)

    def test_has_key_hash(self, sample_record: dict):
        assert "key_hash" in sample_record
        assert len(sample_record["key_hash"]) == 64

    def test_has_key_prefix(self, sample_record: dict):
        assert "key_prefix" in sample_record
        assert len(sample_record["key_prefix"]) == 12

    def test_has_account_id(self, sample_record: dict):
        assert "account_id" in sample_record

    def test_tier_stored(self, sample_record: dict):
        assert sample_record["tier"] == "pro"

    def test_created_at_iso(self, sample_record: dict):
        from datetime import datetime
        assert "created_at" in sample_record
        # Must parse without error
        datetime.fromisoformat(sample_record["created_at"])

    def test_last_used_at_none(self, sample_record: dict):
        assert sample_record["last_used_at"] is None

    def test_revoked_false(self, sample_record: dict):
        assert sample_record["revoked"] is False

    def test_raw_key_not_stored(self):
        """The full raw key must NOT appear in the stored record.
        The key_prefix (first 12 chars) IS stored by design for UI display.
        """
        raw_key, key_hash, key_prefix = generate_api_key()
        record = new_key_record(raw_key, key_hash, key_prefix, str(uuid.uuid4()), "pro")
        for v in record.values():
            if isinstance(v, str):
                assert v != raw_key, (
                    f"Full raw key found in record value: {v!r}"
                )

    @pytest.mark.parametrize("tier", ["free", "pro", "team", "enterprise"])
    def test_all_tiers_accepted(self, tier: str):
        raw_key, key_hash, key_prefix = generate_api_key()
        record = new_key_record(raw_key, key_hash, key_prefix, str(uuid.uuid4()), tier)
        assert record["tier"] == tier


# ---------------------------------------------------------------------------
# Missing secret guard
# ---------------------------------------------------------------------------

class TestMissingHmacSecret:

    def test_raises_when_secret_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FYNOR_HMAC_SECRET", raising=False)
        with pytest.raises(RuntimeError, match="FYNOR_HMAC_SECRET"):
            generate_api_key()

    def test_raises_when_secret_too_short(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FYNOR_HMAC_SECRET", "tooshort")
        with pytest.raises(RuntimeError, match="32 bytes"):
            generate_api_key()
