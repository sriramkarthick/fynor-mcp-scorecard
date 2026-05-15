"""
infrastructure/lambdas/cert_evaluator.py — EventBridge daily certification cron.

Triggered: cron(0 2 * * ? *)  — 02:00 UTC every day.
Target:    This Lambda function.

For every registered target in ``fynor-certifications``:
  1. Query last 30–60 days from ``fynor-daily-results``
  2. Run evaluate_certification_window()
  3. Update ``fynor-certifications`` table
  4. Fire cert.issued / cert.suspended / cert.reinstated webhooks on status change

Contract: docs/tasks/certification-loop-contract.md
SLA:      docs/sla.md — FYNOR_INFRA_ERROR clause implemented via DayRecord.fynor_infra_err
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import boto3

from fynor.certification.certificate import Certificate
from fynor.certification.evaluator import DayRecord, evaluate_certification_window

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_TABLE_DAILY   = os.environ.get("DYNAMODB_TABLE_DAILY",   "fynor-daily-results-prod")
_TABLE_CERTS   = os.environ.get("DYNAMODB_TABLE_CERTS",   "fynor-certifications-prod")
_TABLE_KEYS    = os.environ.get("DYNAMODB_TABLE_KEYS",    "fynor-api-keys-prod")
_WEBHOOK_QUEUE = os.environ.get("SQS_WEBHOOK_QUEUE_URL",  "")   # SQS queue for webhook delivery

_LOOKBACK_DAYS = 60   # query window — evaluator trims to 30 qualifying days


def handler(event: dict, context: Any) -> dict:
    """
    EventBridge cron handler.

    Evaluates all registered targets and updates their certification status.
    Conservative on failure: if the Lambda raises, EventBridge retries twice.
    No cert status changes happen when the cron fails — prevents spurious suspensions.
    """
    db = boto3.client("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    today = datetime.now(timezone.utc).date()

    targets_evaluated = 0
    targets_changed = 0
    errors = []

    # Scan all certification records (at Phase A scale this is fine;
    # Phase B will use paginated query on a GSI if > 1000 targets).
    try:
        certs_response = db.scan(TableName=_TABLE_CERTS)
        cert_items = certs_response.get("Items", [])
    except Exception as exc:
        logger.error("Failed to scan certifications table: %s", exc)
        raise   # let EventBridge retry

    for cert_item in cert_items:
        target_hash = _s(cert_item, "target_hash")
        target_url  = _s(cert_item, "target_url")
        if not target_hash or not target_url:
            continue

        try:
            changed = _evaluate_target(db, today, cert_item, target_hash, target_url)
            targets_evaluated += 1
            if changed:
                targets_changed += 1
        except Exception as exc:
            logger.error("Error evaluating target %s: %s", target_url, exc)
            errors.append({"target": target_url, "error": str(exc)})

    logger.info(
        "Cert evaluation complete: %d targets, %d status changes, %d errors",
        targets_evaluated, targets_changed, len(errors),
    )

    return {
        "targets_evaluated": targets_evaluated,
        "targets_changed": targets_changed,
        "errors": errors,
        "date": today.isoformat(),
    }


def _evaluate_target(
    db: Any,
    today: date,
    cert_item: dict,
    target_hash: str,
    target_url: str,
) -> bool:
    """
    Evaluate one target and update its certification record.

    Returns True if the cert_status changed.
    """
    # Query daily results for the last LOOKBACK_DAYS days
    since_date = (today - timedelta(days=_LOOKBACK_DAYS)).isoformat()

    query_resp = db.query(
        TableName=_TABLE_DAILY,
        KeyConditionExpression="target_hash = :th AND #d >= :since",
        ExpressionAttributeNames={"#d": "date"},
        ExpressionAttributeValues={
            ":th":    {"S": target_hash},
            ":since": {"S": since_date},
        },
    )

    records = [_item_to_day_record(item) for item in query_resp.get("Items", [])]
    verdict, qualifying_days = evaluate_certification_window(records, today)

    previous_status = _s(cert_item, "cert_status") or "PENDING"

    if verdict == previous_status:
        # No change — update last_evaluated_at only
        db.update_item(
            TableName=_TABLE_CERTS,
            Key={"target_hash": {"S": target_hash}, "sort_key": {"S": "CERT"}},
            UpdateExpression="SET last_evaluated_at = :t",
            ExpressionAttributeValues={":t": {"S": today.isoformat()}},
        )
        return False

    # Status changed — persist and fire webhook
    cert_id = _s(cert_item, "cert_id") or str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    update_expr_parts = [
        "cert_status = :status",
        "last_evaluated_at = :t",
        "qualifying_days = :qd",
        "cert_id = :cid",
    ]
    attr_values: dict = {
        ":status": {"S": verdict},
        ":t":      {"S": today.isoformat()},
        ":qd":     {"N": str(qualifying_days)},
        ":cid":    {"S": cert_id},
    }

    if verdict == "CERTIFIED" and previous_status != "CERTIFIED":
        if not _s(cert_item, "issued_at"):
            update_expr_parts.append("issued_at = :issued")
            attr_values[":issued"] = {"S": now_iso}
        else:
            update_expr_parts.append("reinstated_at = :reinstated")
            attr_values[":reinstated"] = {"S": now_iso}

    if verdict == "SUSPENDED":
        update_expr_parts.append("suspended_date = :sd")
        attr_values[":sd"] = {"S": today.isoformat()}

    db.update_item(
        TableName=_TABLE_CERTS,
        Key={"target_hash": {"S": target_hash}, "sort_key": {"S": "CERT"}},
        UpdateExpression="SET " + ", ".join(update_expr_parts),
        ExpressionAttributeValues=attr_values,
    )

    # Enqueue webhook via SQS (async delivery — does not block the cron)
    if _WEBHOOK_QUEUE:
        _enqueue_webhook(verdict, previous_status, cert_id, target_url, today)

    logger.info(
        "Target %s: %s → %s (%d qualifying days)",
        target_url, previous_status, verdict, qualifying_days,
    )
    return True


def _item_to_day_record(item: dict) -> DayRecord:
    """Convert a DynamoDB Item dict to a DayRecord."""
    date_str = _s(item, "date") or "1970-01-01"
    return DayRecord(
        date=date.fromisoformat(date_str),
        passed=item.get("passed", {}).get("BOOL", False),
        fynor_infra_err=item.get("fynor_infra_err", {}).get("BOOL", False),
        runs_count=int(item.get("runs_count", {}).get("N", "0")),
    )


def _enqueue_webhook(
    verdict: str,
    previous_status: str,
    cert_id: str,
    target_url: str,
    today: date,
) -> None:
    """Push a webhook event to SQS for async delivery."""
    event_map = {
        "CERTIFIED": "cert.issued" if previous_status == "PENDING" else "cert.reinstated",
        "SUSPENDED": "cert.suspended",
        "REVOKED":   "cert.revoked",
    }
    event_name = event_map.get(verdict, "cert.status_changed")

    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    payload = {
        "event": event_name,
        "cert_id": cert_id,
        "target_url": target_url,
        "previous_status": previous_status,
        "new_status": verdict,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        sqs.send_message(
            QueueUrl=_WEBHOOK_QUEUE,
            MessageBody=json.dumps(payload),
        )
    except Exception as exc:
        logger.warning("Failed to enqueue webhook for %s: %s", target_url, exc)


def _s(item: dict, key: str) -> str | None:
    """Extract a DynamoDB String attribute value, or None."""
    v = item.get(key)
    if v and "S" in v:
        return v["S"]
    return None
