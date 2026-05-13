"""
fynor.certification.certificate — Certificate data model.

A Certificate is issued when an interface passes all checks for
30 consecutive days. It is the data backing the Agent-Ready badge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CertificationStatus(str, Enum):
    PENDING     = "pending"     # Not enough passing days yet
    CERTIFIED   = "certified"   # 30+ consecutive passing days
    SUSPENDED   = "suspended"   # Check failed — cert paused
    REVOKED     = "revoked"     # Manual revocation (security issue)
    EXPIRED     = "expired"     # Not rechecked within 90 days


@dataclass
class Certificate:
    """
    Agent-Ready Certificate for one interface target.

    Issued after 30 consecutive days of passing all checks.
    Suspended immediately on any check failure.
    Revoked on critical security failures.
    """

    target: str
    interface_type: str             # mcp | rest | graphql | grpc | websocket | soap | cli
    status: CertificationStatus
    grade: str                      # A | B — only A and B grades earn certification
    consecutive_passing_days: int
    last_check_date: str
    issued_date: str | None = None  # Set when status becomes CERTIFIED
    suspended_date: str | None = None
    revocation_reason: str | None = None
    certificate_id: str = ""        # Set on issuance: target_id hash
    badge_url: str = ""             # https://fynor.tech/badge/{certificate_id}
    cert_url: str = ""              # https://fynor.tech/cert/{certificate_id}
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Certification thresholds
    REQUIRED_CONSECUTIVE_DAYS: int = 30
    MINIMUM_GRADE: frozenset = frozenset({"A", "B"})

    def is_eligible(self) -> bool:
        """True when the interface meets the minimum certification requirements."""
        return (
            self.grade in self.MINIMUM_GRADE
            and self.consecutive_passing_days >= self.REQUIRED_CONSECUTIVE_DAYS
        )

    def badge_markdown(self) -> str:
        """Return the README badge markdown snippet."""
        if not self.badge_url:
            return ""
        return (
            f"[![Fynor Agent-Ready]({self.badge_url})]({self.cert_url})"
        )
