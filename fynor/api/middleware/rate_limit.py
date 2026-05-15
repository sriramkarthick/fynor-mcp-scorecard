"""
fynor.api.middleware.rate_limit — Tier-based rate limiting via DynamoDB.

This is the APPLICATION-LEVEL rate limiter (runs inside FastAPI).
It works in tandem with the CLOUDFLARE primary rate limiter (D4):
  - Cloudflare: 100 req/30s per IP — blocks floods before they reach Railway
  - This middleware: per-account hourly quota based on subscription tier

Tier limits (api-implementation-contract.md):
  free:       0 runs/hr  (CLI only — no hosted API access)
  pro:       12 runs/hr
  team:      60 runs/hr
  enterprise: unlimited

DynamoDB key: ``ratelimit:{api_key_hash}:{current_hour_iso}``
TTL: end of the current clock hour (auto-expired by DynamoDB TTL).

On limit exceeded: returns HTTP 429 with Retry-After header set to
seconds remaining in the current hour.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import boto3
from fastapi import HTTPException, Request

_TABLE_RATELIMIT = os.environ.get("DYNAMODB_TABLE_RATELIMIT", "fynor-ratelimit-prod")

RATE_LIMITS: dict[str, int] = {
    "free":       0,    # CLI only — no hosted API access
    "pro":        12,   # runs per hour
    "team":       60,   # runs per hour
    "enterprise": -1,   # unlimited (-1 = no limit)
}


def _current_hour_iso() -> str:
    """Return ISO 8601 string truncated to the current UTC hour."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:00:00Z")


def _seconds_until_next_hour() -> int:
    """Seconds remaining in the current UTC clock hour."""
    now = datetime.now(timezone.utc)
    return (60 - now.minute) * 60 - now.second


def _hour_end_unix() -> int:
    """Unix timestamp at the end of the current UTC clock hour (TTL for DynamoDB)."""
    now = datetime.now(timezone.utc)
    seconds_left = _seconds_until_next_hour()
    return int(now.timestamp()) + seconds_left


async def check_rate_limit(account: dict, db=None) -> None:
    """
    Enforce tier-based hourly rate limits.

    Args:
        account: Account dict with 'tier' and 'key_hash' fields.
        db:      boto3 DynamoDB client. If None, one is created from env.

    Raises:
        HTTPException(429) when the account has exceeded its hourly quota.
        HTTPException(403) when the tier is 'free' (no hosted API access).
    """
    tier = account.get("tier", "pro")
    limit = RATE_LIMITS.get(tier, 12)

    if limit == 0:
        raise HTTPException(
            status_code=403,
            detail=(
                "Free tier accounts cannot use the hosted API. "
                "Install the CLI: pip install fynor"
            ),
        )

    if limit == -1:
        return   # enterprise — unlimited

    if db is None:
        db = boto3.client("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    key_hash = account["key_hash"]
    hour_key = f"ratelimit:{key_hash}:{_current_hour_iso()}"

    try:
        # Atomic increment — returns the new count after increment.
        response = db.update_item(
            TableName=_TABLE_RATELIMIT,
            Key={"rate_key": {"S": hour_key}},
            UpdateExpression="ADD run_count :one SET #ttl = if_not_exists(#ttl, :ttl_val)",
            ExpressionAttributeNames={"#ttl": "TTL"},
            ExpressionAttributeValues={
                ":one": {"N": "1"},
                ":ttl_val": {"N": str(_hour_end_unix())},
            },
            ReturnValues="ALL_NEW",
        )
        count = int(
            response.get("Attributes", {}).get("run_count", {}).get("N", "1")
        )
    except Exception:
        # DynamoDB unavailable — fail open (Cloudflare primary still protects)
        return

    if count > limit:
        retry_after = _seconds_until_next_hour()
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded for {tier!r} tier "
                f"({limit} runs/hour). "
                f"Quota resets in {retry_after // 60} minutes."
            ),
            headers={"Retry-After": str(retry_after)},
        )
