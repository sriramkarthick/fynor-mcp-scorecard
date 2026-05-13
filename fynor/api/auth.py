"""
fynor.api.auth — API key generation, storage, and validation.

API keys are stored as HMAC-SHA256 digests, not bcrypt hashes.

WHY NOT BCRYPT:
  bcrypt is designed for passwords — it is intentionally slow (200-500ms per
  verification at cost factor 12). API key validation happens on every HTTP
  request. At 500ms per check, a service handling 100 req/s would spend 50
  seconds/second just on key validation — impossible.

WHY HMAC-SHA256:
  Security properties for API keys differ from passwords:
  - API keys are long (32+ random bytes), not human-memorable. There is no
    dictionary attack surface.
  - The security guarantee comes from the key length, not the hash speed.
  - HMAC with a server-side secret: even if the DB is leaked, the hash is
    useless without the HMAC secret (unlike bcrypt where the hash alone
    enables offline cracking of short passwords).
  - Verification is O(1) microseconds vs O(1) milliseconds for bcrypt.

KEY FORMAT:
  fynor_live_<32-byte-urlsafe-base64>

STORAGE:
  {
    "key_hash":  HMAC-SHA256(raw_key, SERVER_HMAC_SECRET) — hex string
    "key_prefix": first 12 chars of raw_key (for identification in dashboard)
    "account_id": owner account UUID
    "tier":      free | pro | team | enterprise
    "created_at": ISO-8601 UTC
    "last_used_at": ISO-8601 UTC or null
    "revoked":   bool
  }

The raw key is shown to the user ONCE at creation and then discarded.
Fynor never stores the raw key.

ENVIRONMENT:
  FYNOR_HMAC_SECRET — 256-bit (32-byte) random secret, base64-encoded.
  Must be set in all environments. Rotate with a key-version migration plan.
  Generate with: python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from base64 import urlsafe_b64encode
from datetime import datetime, timezone

_KEY_PREFIX_LEN = 12
_KEY_BYTES = 32  # 256 bits of entropy


def _get_hmac_secret() -> bytes:
    """
    Load the HMAC secret from the environment.

    Raises:
        RuntimeError: If FYNOR_HMAC_SECRET is not set or is too short.
    """
    raw = os.environ.get("FYNOR_HMAC_SECRET", "")
    if not raw:
        raise RuntimeError(
            "FYNOR_HMAC_SECRET environment variable is not set. "
            "Generate one with: "
            "python -c \"import secrets, base64; "
            "print(base64.b64encode(secrets.token_bytes(32)).decode())\""
        )
    secret = raw.encode("utf-8")
    if len(secret) < 32:
        raise RuntimeError(
            "FYNOR_HMAC_SECRET must be at least 32 bytes (256 bits). "
            "Current value is too short."
        )
    return secret


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        Tuple of (raw_key, key_hash, key_prefix):
          raw_key    — Show to the user ONCE, then discard. Never store this.
          key_hash   — HMAC-SHA256 digest to store in the database.
          key_prefix — First 12 chars of the raw key, stored for UI display.

    Example:
        raw_key, key_hash, prefix = generate_api_key()
        # Send raw_key to the user (once, over TLS).
        # Store key_hash + prefix + account_id in DynamoDB.
        # Discard raw_key from memory after returning it.
    """
    token_bytes = secrets.token_bytes(_KEY_BYTES)
    token_b64 = urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")
    raw_key = f"fynor_live_{token_b64}"

    key_hash = _hmac_digest(raw_key)
    key_prefix = raw_key[:_KEY_PREFIX_LEN]

    return raw_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    """
    Compute the HMAC-SHA256 hash of a raw API key.

    Used during validation: hash the submitted key and compare to the stored hash.
    The comparison is always done with hmac.compare_digest (constant-time) to
    prevent timing attacks.

    Args:
        raw_key: The raw API key submitted by the client.

    Returns:
        Hex-encoded HMAC-SHA256 digest.
    """
    return _hmac_digest(raw_key)


def verify_api_key(submitted_key: str, stored_hash: str) -> bool:
    """
    Verify a submitted API key against a stored hash.

    Comparison is constant-time to prevent timing attacks. Even a timing
    difference of nanoseconds can leak information about the stored hash.

    Args:
        submitted_key: The raw key submitted in the X-Fynor-Key header.
        stored_hash:   The HMAC-SHA256 hash stored in DynamoDB.

    Returns:
        True if the key is valid.
    """
    submitted_hash = _hmac_digest(submitted_key)
    return hmac.compare_digest(submitted_hash, stored_hash)


def _hmac_digest(raw_key: str) -> str:
    """Compute HMAC-SHA256(raw_key, FYNOR_HMAC_SECRET). Returns hex string."""
    secret = _get_hmac_secret()
    return hmac.new(secret, raw_key.encode("utf-8"), hashlib.sha256).hexdigest()


def new_key_record(
    raw_key: str,
    key_hash: str,
    key_prefix: str,
    account_id: str,
    tier: str,
) -> dict:
    """
    Build a DynamoDB record for a new API key.

    Args:
        raw_key:    The raw key (used only to derive key_hash here, then discarded).
        key_hash:   Pre-computed HMAC-SHA256 hash.
        key_prefix: First 12 chars of raw_key for UI display.
        account_id: UUID of the owning account.
        tier:       One of: free | pro | team | enterprise.

    Returns:
        Dict ready for DynamoDB put_item.
    """
    return {
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "account_id": account_id,
        "tier": tier,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_used_at": None,
        "revoked": False,
    }
