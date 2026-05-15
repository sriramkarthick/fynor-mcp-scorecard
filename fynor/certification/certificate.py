"""
fynor.certification.certificate — Certificate data model.

A Certificate is issued when an interface passes all checks for 30
consecutive days. It is the data backing the Agent-Ready badge.

Field names and badge URL format match certification-loop-contract.md exactly.
Any change here requires a matching change in the contract document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal


CertStatus = Literal["CERTIFIED", "PENDING", "SUSPENDED", "REVOKED"]

# Badge URL pattern — CloudFront distribution, per certification-loop-contract.md.
_BADGE_URL_TEMPLATE = "https://badge.fynor.tech/{cert_id}.svg"
_CERT_URL_TEMPLATE  = "https://fynor.tech/cert/{cert_id}"


@dataclass
class Certificate:
    """
    Agent-Ready Certificate for one interface target.

    Issued after 30 consecutive days of passing all checks (grade A or B).
    Suspended immediately on any failing day.
    Revoked on critical security failures or account closure.

    Field contract (certification-loop-contract.md):
      cert_id        UUID v4 — generated on first issuance, reused on reinstatement
      target_url     URL of the checked interface
      grade          Grade at time of certification (A or B)
      issued_at      When CERTIFIED status was first achieved
      valid_until    issued_at + 365 days
      badge_url      https://badge.fynor.tech/{cert_id}.svg
      cert_status    CERTIFIED | PENDING | SUSPENDED | REVOKED
      reinstated_at  Set when a suspended cert re-achieves CERTIFIED
    """

    cert_id: str                    # UUID v4 — generated on issuance, reused on reinstatement
    target_url: str
    interface_type: str             # mcp | rest | graphql | grpc | websocket
    cert_status: CertStatus
    grade: str                      # A | B — only A and B grades earn certification
    consecutive_passing_days: int
    last_check_date: str            # ISO 8601 date (YYYY-MM-DD)

    issued_at: datetime | None = None       # Set when cert_status → CERTIFIED
    valid_until: datetime | None = None     # issued_at + 365 days
    reinstated_at: datetime | None = None   # Set on SUSPENDED → CERTIFIED transition
    suspended_date: str | None = None       # ISO 8601 date of suspension
    revocation_reason: str | None = None    # Human-readable reason for REVOKED

    badge_url: str = ""             # Populated by _compute_urls() on issuance
    cert_url: str = ""

    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Certification thresholds — locked, do not make configurable.
    REQUIRED_CONSECUTIVE_DAYS: int = 30
    ELIGIBLE_GRADES: frozenset = frozenset({"A", "B"})

    def __post_init__(self) -> None:
        if self.cert_id and not self.badge_url:
            self.badge_url = _BADGE_URL_TEMPLATE.format(cert_id=self.cert_id)
            self.cert_url  = _CERT_URL_TEMPLATE.format(cert_id=self.cert_id)

    def is_eligible(self) -> bool:
        """True when the interface meets the minimum certification requirements."""
        return (
            self.grade in self.ELIGIBLE_GRADES
            and self.consecutive_passing_days >= self.REQUIRED_CONSECUTIVE_DAYS
        )

    def mark_certified(self, at: datetime | None = None) -> None:
        """Transition to CERTIFIED, set issued_at and valid_until."""
        now = at or datetime.now(timezone.utc)
        self.cert_status = "CERTIFIED"
        if self.issued_at is None:
            # First certification — set issued_at
            self.issued_at = now
        else:
            # Re-certification after suspension
            self.reinstated_at = now
        self.valid_until = (self.issued_at or now) + timedelta(days=365)

    def mark_suspended(self, date_str: str) -> None:
        """Transition to SUSPENDED."""
        self.cert_status = "SUSPENDED"
        self.suspended_date = date_str

    def badge_markdown(self) -> str:
        """Return the README badge markdown snippet for embedding."""
        if not self.badge_url:
            return ""
        return f"[![Fynor Agent-Ready]({self.badge_url})]({self.cert_url})"
