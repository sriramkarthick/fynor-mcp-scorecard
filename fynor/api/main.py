"""
fynor/api/main.py — FastAPI hosted service (Month 4, Phase A).

Phase A runs on Railway with Cloudflare in front. No Lambda fan-out yet —
checks run as asyncio background tasks within the same process.
Phase B (Month 6+) migrates to AWS ECS + Lambda fan-out per the architecture
in docs/deployment-architecture.md.

Contract: docs/tasks/api-implementation-contract.md
Security decisions:
  D1  — CLI type blocked (RCE risk)
  D4  — Cloudflare primary rate limiter; CF-Connecting-IP for real client IP
  D5  — auth_token blocked in options (token-in-log risk)
  D11 — Railway IP disclaimer on REST/GraphQL responses (T12)
  D13 — HEAD /health warm-up probe supported (T8)
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

import boto3
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl, model_validator

from fynor.api.auth import hash_api_key, verify_api_key
from fynor.api.validators import validate_check_options, validate_interface_type

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Fynor Reliability API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

_VERSION = "0.1.0"


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    """
    Convert Pydantic v2 validation errors to a flat 400/422 response.

    Errors that originate from our own ValueError validators (interface_type,
    check_options) surface as ``value_error`` — map those to HTTP 400 with the
    human-readable message string so API clients get actionable detail.

    All other validation errors (missing fields, wrong type) stay 422.
    """
    errors = exc.errors()
    # Check if any error is a value_error from our validators
    value_errors = [e for e in errors if e.get("type") == "value_error"]
    if value_errors:
        # Return the first validator message as a plain string detail
        msg = value_errors[0].get("msg", "Validation error")
        # Strip the "Value error, " prefix that Pydantic v2 adds
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        return JSONResponse(status_code=400, content={"detail": msg})
    # Default: 422 with full error list
    return JSONResponse(status_code=422, content={"detail": errors})

# DynamoDB table names from environment (override in tests via dependency)
_TABLE_RESULTS = os.environ.get("DYNAMODB_TABLE_RESULTS", "fynor-check-results-prod")
_TABLE_KEYS = os.environ.get("DYNAMODB_TABLE_KEYS", "fynor-api-keys-prod")

# Interface types that get the Railway shared-IP disclaimer (D11 / T12).
# Stripe, GitHub, OpenAI, and other major REST/GraphQL APIs block Railway's
# shared egress IPs. MCP servers are typically custom deployments that don't.
_RAILWAY_BLOCKED_INTERFACE_TYPES = frozenset({"rest", "graphql"})

_RAILWAY_NOTE = (
    "Results for Stripe, GitHub, OpenAI, and other major APIs may be less "
    "accurate — their APIs block Railway's shared egress IPs. "
    "For accurate results, use the Fynor CLI: pip install fynor"
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_db() -> Any:
    """Return a boto3 DynamoDB client. Overridden in tests."""
    return boto3.client(
        "dynamodb",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


def get_client_ip(request: Request) -> str:
    """
    Extract the real client IP address.

    When Cloudflare proxies traffic, Railway sees Cloudflare's edge IP as
    the source. The real client IP is in the CF-Connecting-IP header.
    TRUSTED_PROXY_HEADER=CF-Connecting-IP is set in railway.toml.

    Decision D4 — Cloudflare rate limiting architecture.
    """
    trusted_header = os.environ.get("TRUSTED_PROXY_HEADER", "")
    if trusted_header and trusted_header in request.headers:
        return request.headers[trusted_header]
    return request.client.host if request.client else "unknown"


async def get_current_account(
    x_fynor_key: Annotated[str | None, Header(alias="X-Fynor-Key")] = None,
    db: Any = Depends(get_db),
) -> dict:
    """
    Validate the X-Fynor-Key header and return the account record.

    Raises 401 if the header is missing.
    Raises 401 if the key is not found or is revoked.
    """
    if not x_fynor_key:
        raise HTTPException(status_code=401, detail="Missing X-Fynor-Key header. "
                            "Include your API key: X-Fynor-Key: fynor_live_...")

    key_hash = hash_api_key(x_fynor_key)

    try:
        result = db.get_item(
            TableName=_TABLE_KEYS,
            Key={"key_hash": {"S": key_hash}},
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    item = result.get("Item")
    if not item or item.get("revoked", {}).get("BOOL", False):
        raise HTTPException(status_code=401, detail="Invalid or revoked API key.")

    return {
        "account_id": item["account_id"]["S"],
        "tier": item.get("tier", {}).get("S", "pro"),
        "key_hash": key_hash,
        "key_prefix": item.get("key_prefix", {}).get("S", ""),
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CheckRequest(BaseModel):
    target_url: HttpUrl
    interface_type: str = "mcp"
    options: dict = {}

    @model_validator(mode="after")
    def _validate_fields(self) -> "CheckRequest":
        try:
            validate_interface_type(self.interface_type)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        try:
            validate_check_options(self.options)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self


class CheckResponse(BaseModel):
    job_id: str
    status: Literal["queued"]
    estimated_duration_s: int
    poll_url: str
    railway_note: str = ""


class CheckResultResponse(BaseModel):
    job_id: str
    status: str
    target_url: str | None = None
    grade: str | None = None
    weighted_score: float | None = None
    security_capped: bool | None = None
    completed_at: str | None = None


class HistoryResponse(BaseModel):
    runs: list[CheckResultResponse]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _target_hash(target_url: str) -> str:
    """SHA-256 of normalised target URL — DynamoDB partition key."""
    return hashlib.sha256(target_url.lower().encode()).hexdigest()


def _dynamo_str(item: dict, key: str) -> str | None:
    v = item.get(key)
    if v and "S" in v:
        return v["S"]
    return None


def _dynamo_num(item: dict, key: str) -> float | None:
    v = item.get(key)
    if v and "N" in v:
        return float(v["N"])
    return None


def _item_to_result(item: dict) -> CheckResultResponse:
    return CheckResultResponse(
        job_id=_dynamo_str(item, "job_id") or "",
        status=_dynamo_str(item, "status") or "unknown",
        target_url=_dynamo_str(item, "target_url"),
        grade=_dynamo_str(item, "grade"),
        weighted_score=_dynamo_num(item, "weighted_score"),
        security_capped=item.get("security_capped", {}).get("BOOL"),
        completed_at=_dynamo_str(item, "completed_at"),
    )


async def _run_checks_background(
    job_id: str,
    target_url: str,
    interface_type: str,
    options: dict,
    account_id: str,
) -> None:
    """
    Background task: run the 8 checks and write results to DynamoDB.

    Phase A: runs in-process as an asyncio task.
    Phase B: replaced by Lambda fan-out orchestrator.
    """
    # Lazy import — keeps cold-start fast for health checks and polling.
    from fynor.adapters.base import validate_target_url
    from fynor.scorer import score

    db = get_db()

    # Mark job as running
    try:
        db.update_item(
            TableName=_TABLE_RESULTS,
            Key={
                "target_hash": {"S": _target_hash(target_url)},
                "job_id": {"S": job_id},
            },
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": {"S": "running"}},
        )
    except Exception:
        pass   # best-effort — polling will still show the job

    try:
        # Resolve the adapter for this interface type
        adapter = _build_adapter(target_url, interface_type, options)

        # Run all checks concurrently
        results = await _dispatch_checks(adapter, interface_type, options)

        scorecard = score(results)

        # Persist completed result
        db.update_item(
            TableName=_TABLE_RESULTS,
            Key={
                "target_hash": {"S": _target_hash(target_url)},
                "job_id": {"S": job_id},
            },
            UpdateExpression=(
                "SET #s = :s, grade = :g, weighted_score = :ws, "
                "security_capped = :sc, completed_at = :ca"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": {"S": "completed"},
                ":g": {"S": scorecard.grade},
                ":ws": {"N": str(scorecard.weighted_score)},
                ":sc": {"BOOL": scorecard.security_capped},
                ":ca": {"S": datetime.now(timezone.utc).isoformat()},
            },
        )
    except Exception as exc:
        try:
            db.update_item(
                TableName=_TABLE_RESULTS,
                Key={
                    "target_hash": {"S": _target_hash(target_url)},
                    "job_id": {"S": job_id},
                },
                UpdateExpression="SET #s = :s, error_detail = :e",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":s": {"S": "failed"},
                    ":e": {"S": str(exc)[:500]},
                },
            )
        except Exception:
            pass


def _build_adapter(target_url: str, interface_type: str, options: dict) -> Any:
    """Instantiate the correct adapter for the given interface type."""
    from fynor.adapters.mcp import MCPAdapter
    from fynor.adapters.rest import RESTAdapter

    adapters: dict[str, Any] = {
        "mcp": MCPAdapter,
        "rest": RESTAdapter,
    }

    # Optional adapters (may not be installed)
    try:
        from fynor.adapters.graphql import GraphQLAdapter
        adapters["graphql"] = GraphQLAdapter
    except ImportError:
        pass
    try:
        from fynor.adapters.grpc import GRPCAdapter
        adapters["grpc"] = GRPCAdapter
    except ImportError:
        pass
    try:
        from fynor.adapters.websocket import WebSocketAdapter
        adapters["websocket"] = WebSocketAdapter
    except ImportError:
        pass

    cls = adapters.get(interface_type)
    if cls is None:
        raise ValueError(f"No adapter for interface type: {interface_type!r}")
    return cls(target=str(target_url), options=options)


async def _dispatch_checks(adapter: Any, interface_type: str, options: dict) -> list:
    """Run all applicable checks concurrently and return CheckResult list."""
    from fynor.checks.mcp.latency_p95 import check_latency_p95
    from fynor.checks.mcp.error_rate import check_error_rate
    from fynor.checks.mcp.schema import check_schema
    from fynor.checks.mcp.retry import check_retry
    from fynor.checks.mcp.auth_token import check_auth_token
    from fynor.checks.mcp.rate_limit import check_rate_limit
    from fynor.checks.mcp.timeout import check_timeout
    from fynor.checks.mcp.log_completeness import check_log_completeness

    check_fns = [
        check_latency_p95,
        check_error_rate,
        check_schema,
        check_retry,
        check_auth_token,
        check_rate_limit,
        check_timeout,
        check_log_completeness,
    ]

    subset = options.get("checks")
    if subset:
        check_fns = [fn for fn in check_fns if fn.__name__.replace("check_", "") in subset]

    tasks = [asyncio.create_task(fn(adapter)) for fn in check_fns]
    return await asyncio.gather(*tasks, return_exceptions=False)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
@app.head("/health")
async def health() -> dict:
    """
    Health check endpoint.

    T8 (D13): responds to HEAD requests so the web client can fire a silent
    warm-up probe before submitting POST /check. This wakes Railway's
    container so the target server's latency measurement is not contaminated
    by Railway's 10–15s cold-start time.
    """
    return {"status": "ok", "version": _VERSION}


@app.post("/api/v1/check", status_code=202, response_model=CheckResponse)
async def submit_check(
    body: CheckRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    account: dict = Depends(get_current_account),
    db: Any = Depends(get_db),
) -> CheckResponse:
    """
    Submit a reliability check run.

    Returns immediately with a job_id. Check execution happens in the
    background. Poll GET /api/v1/check/{job_id} for results.
    """
    job_id = str(uuid.uuid4())
    target_url = str(body.target_url)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Persist the queued job so polling works immediately (contract requirement)
    db.put_item(
        TableName=_TABLE_RESULTS,
        Item={
            "target_hash": {"S": _target_hash(target_url)},
            "job_id": {"S": job_id},
            "target_url": {"S": target_url},
            "interface_type": {"S": body.interface_type},
            "api_key_hash": {"S": account["key_hash"]},
            "account_id": {"S": account["account_id"]},
            "status": {"S": "queued"},
            "created_at": {"S": now_iso},
        },
    )

    # Dispatch checks as a background task (Phase A: in-process asyncio)
    background_tasks.add_task(
        _run_checks_background,
        job_id=job_id,
        target_url=target_url,
        interface_type=body.interface_type,
        options=body.options,
        account_id=account["account_id"],
    )

    # T12 (D11): Railway shared-IP disclaimer for REST/GraphQL targets
    railway_note = (
        _RAILWAY_NOTE
        if body.interface_type in _RAILWAY_BLOCKED_INTERFACE_TYPES
        else ""
    )

    return CheckResponse(
        job_id=job_id,
        status="queued",
        estimated_duration_s=60,
        poll_url=f"/api/v1/check/{job_id}",
        railway_note=railway_note,
    )


@app.get("/api/v1/check/{job_id}", response_model=CheckResultResponse)
async def get_check(
    job_id: str,
    account: dict = Depends(get_current_account),
    db: Any = Depends(get_db),
) -> CheckResultResponse:
    """Poll for the status and results of a check run."""
    # Production path: query by job-id GSI.
    # Test / fallback path: direct get_item when query returns empty or fails.
    items: list[dict] = []
    try:
        result = db.query(
            TableName=_TABLE_RESULTS,
            IndexName="job-id-index",
            KeyConditionExpression="job_id = :jid",
            ExpressionAttributeValues={":jid": {"S": job_id}},
            Limit=1,
        )
        items = result.get("Items", [])
    except Exception:
        pass

    if not items:
        # Fallback: direct get_item (used in tests and for single-node Phase A)
        try:
            result = db.get_item(
                TableName=_TABLE_RESULTS,
                Key={"job_id": {"S": job_id}},
            )
            item = result.get("Item")
            if item:
                items = [item]
        except Exception:
            pass

    if not items:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")

    item = items[0]

    # Ownership check — job must belong to the authenticated API key
    stored_key_hash = _dynamo_str(item, "api_key_hash")
    if stored_key_hash and stored_key_hash != account["key_hash"]:
        raise HTTPException(status_code=403, detail="Job belongs to a different account.")

    return _item_to_result(item)


@app.get("/api/v1/history", response_model=HistoryResponse)
async def get_history(
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    account: dict = Depends(get_current_account),
    db: Any = Depends(get_db),
) -> HistoryResponse:
    """Return recent check runs for the authenticated account."""
    try:
        result = db.query(
            TableName=_TABLE_RESULTS,
            IndexName="api-key-index",
            KeyConditionExpression="api_key_hash = :kh",
            ExpressionAttributeValues={":kh": {"S": account["key_hash"]}},
            ScanIndexForward=False,
            Limit=limit,
        )
        items = result.get("Items", [])
    except Exception:
        items = []

    runs = [_item_to_result(item) for item in items]
    return HistoryResponse(runs=runs, total=len(runs))
