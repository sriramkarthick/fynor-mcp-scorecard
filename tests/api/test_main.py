"""
tests/api/test_main.py — Unit tests for fynor.api.main (FastAPI app).

Written FIRST (decision D8 — test-first locked) before implementing main.py.

Covers:
  - GET /health
  - POST /api/v1/check  (validation, auth, job creation, background dispatch)
  - GET /api/v1/check/{job_id}  (poll, 404, 403)
  - GET /api/v1/history
  - T8 — HEAD /health warm-up probe works (unblocks Railway cold-start fix)
  - T12 — Railway IP disclaimer in results for REST/GraphQL targets
  - Client IP extraction from CF-Connecting-IP header
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App fixture — import after mocking boto3 so no real AWS calls happen
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_db():
    """A lightweight stand-in for the DynamoDB boto3 client."""
    db = MagicMock()
    db.put_item.return_value = {}
    db.get_item.return_value = {"Item": None}   # default: not found
    db.query.return_value = {"Items": []}
    return db


@pytest.fixture()
def fake_account():
    return {
        "account_id": "acct-test-001",
        "tier": "pro",
        "key_hash": "testhash",
        "key_prefix": "fynor_live",
    }


@pytest.fixture()
def client(mock_db, fake_account):
    """TestClient with all external dependencies overridden."""
    from fynor.api.main import app, get_db, get_current_account

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_account] = lambda: fake_account

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def unauthed_client(mock_db):
    """TestClient with no auth override — auth dependency fires normally."""
    from fynor.api.main import app, get_db

    app.dependency_overrides[get_db] = lambda: mock_db

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


# ===========================================================================
# GET /health
# ===========================================================================

class TestHealth:

    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_returns_status_ok(self, client):
        r = client.get("/health")
        assert r.json()["status"] == "ok"

    def test_returns_version(self, client):
        r = client.get("/health")
        assert "version" in r.json()

    def test_head_request_returns_200(self, client):
        """T8 — HEAD /health must succeed (warm-up probe before POST /check)."""
        r = client.head("/health")
        assert r.status_code == 200

    def test_head_has_no_body(self, client):
        """RFC 7231: HEAD response must not include a body."""
        r = client.head("/health")
        assert r.content == b""


# ===========================================================================
# POST /api/v1/check
# ===========================================================================

VALID_CHECK_BODY = {
    "target_url": "https://example.com/mcp",
    "interface_type": "mcp",
}


class TestSubmitCheck:

    def test_valid_request_returns_202(self, client):
        r = client.post("/api/v1/check", json=VALID_CHECK_BODY)
        assert r.status_code == 202

    def test_response_has_job_id(self, client):
        r = client.post("/api/v1/check", json=VALID_CHECK_BODY)
        assert "job_id" in r.json()

    def test_job_id_is_uuid(self, client):
        r = client.post("/api/v1/check", json=VALID_CHECK_BODY)
        job_id = r.json()["job_id"]
        uuid.UUID(job_id)   # raises if not a valid UUID

    def test_response_has_poll_url(self, client):
        r = client.post("/api/v1/check", json=VALID_CHECK_BODY)
        assert "poll_url" in r.json()

    def test_poll_url_contains_job_id(self, client):
        r = client.post("/api/v1/check", json=VALID_CHECK_BODY)
        data = r.json()
        assert data["job_id"] in data["poll_url"]

    def test_status_is_queued(self, client):
        r = client.post("/api/v1/check", json=VALID_CHECK_BODY)
        assert r.json()["status"] == "queued"

    def test_job_written_to_dynamo(self, client, mock_db):
        client.post("/api/v1/check", json=VALID_CHECK_BODY)
        assert mock_db.put_item.called

    def test_estimated_duration_present(self, client):
        r = client.post("/api/v1/check", json=VALID_CHECK_BODY)
        assert "estimated_duration_s" in r.json()

    # -- validation errors ---------------------------------------------------

    def test_cli_type_rejected_400(self, client):
        r = client.post("/api/v1/check", json={**VALID_CHECK_BODY, "interface_type": "cli"})
        assert r.status_code == 400

    def test_cli_type_error_mentions_pip(self, client):
        r = client.post("/api/v1/check", json={**VALID_CHECK_BODY, "interface_type": "cli"})
        assert "pip install fynor" in r.json()["detail"]

    def test_auth_token_in_options_rejected_400(self, client):
        body = {**VALID_CHECK_BODY, "options": {"auth_token": "secret123"}}
        r = client.post("/api/v1/check", json=body)
        assert r.status_code == 400

    def test_auth_token_error_mentions_env_var(self, client):
        body = {**VALID_CHECK_BODY, "options": {"auth_token": "secret123"}}
        r = client.post("/api/v1/check", json=body)
        assert "FYNOR_AUTH_TOKEN" in r.json()["detail"]

    def test_missing_target_url_returns_422(self, client):
        r = client.post("/api/v1/check", json={"interface_type": "mcp"})
        assert r.status_code == 422

    def test_unknown_interface_type_returns_400(self, client):
        r = client.post("/api/v1/check", json={**VALID_CHECK_BODY, "interface_type": "telnet"})
        assert r.status_code == 400

    # -- auth ----------------------------------------------------------------

    def test_missing_api_key_returns_401(self, unauthed_client):
        r = unauthed_client.post("/api/v1/check", json=VALID_CHECK_BODY)
        assert r.status_code == 401

    # -- T12: Railway IP disclaimer ------------------------------------------

    def test_rest_target_response_includes_railway_note(self, client):
        """T12 — REST targets get a Railway IP disclaimer in the response."""
        body = {**VALID_CHECK_BODY, "interface_type": "rest"}
        r = client.post("/api/v1/check", json=body)
        data = r.json()
        # The note field is present for REST interface on Railway
        assert "railway_note" in data

    def test_mcp_target_has_no_railway_note_or_empty(self, client):
        """MCP targets don't have the Railway note (not a known blocked type)."""
        r = client.post("/api/v1/check", json=VALID_CHECK_BODY)
        data = r.json()
        # Either not present or empty string
        assert data.get("railway_note", "") == ""

    def test_graphql_target_response_includes_railway_note(self, client):
        """T12 — GraphQL targets also get the disclaimer (Stripe/GitHub pattern)."""
        body = {**VALID_CHECK_BODY, "interface_type": "graphql"}
        r = client.post("/api/v1/check", json=body)
        assert "railway_note" in r.json()
        assert r.json()["railway_note"] != ""


# ===========================================================================
# GET /api/v1/check/{job_id}
# ===========================================================================

def _make_dynamo_job(job_id: str, status: str = "queued", api_key_hash: str = "testhash") -> dict:
    """Return a DynamoDB Item dict for a job record."""
    return {
        "job_id": {"S": job_id},
        "status": {"S": status},
        "target_url": {"S": "https://example.com/mcp"},
        "interface_type": {"S": "mcp"},
        "api_key_hash": {"S": api_key_hash},
        "created_at": {"S": "2026-05-15T10:00:00Z"},
    }


class TestGetCheck:

    def test_existing_job_returns_200(self, client, mock_db):
        job_id = str(uuid.uuid4())
        mock_db.get_item.return_value = {"Item": _make_dynamo_job(job_id)}
        r = client.get(f"/api/v1/check/{job_id}")
        assert r.status_code == 200

    def test_existing_job_returns_job_id(self, client, mock_db):
        job_id = str(uuid.uuid4())
        mock_db.get_item.return_value = {"Item": _make_dynamo_job(job_id)}
        r = client.get(f"/api/v1/check/{job_id}")
        assert r.json()["job_id"] == job_id

    def test_existing_job_returns_status(self, client, mock_db):
        job_id = str(uuid.uuid4())
        mock_db.get_item.return_value = {"Item": _make_dynamo_job(job_id, status="running")}
        r = client.get(f"/api/v1/check/{job_id}")
        assert r.json()["status"] == "running"

    def test_unknown_job_returns_404(self, client, mock_db):
        mock_db.get_item.return_value = {"Item": None}
        r = client.get(f"/api/v1/check/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_job_owned_by_other_key_returns_403(self, client, mock_db):
        job_id = str(uuid.uuid4())
        mock_db.get_item.return_value = {
            "Item": _make_dynamo_job(job_id, api_key_hash="differenthash")
        }
        r = client.get(f"/api/v1/check/{job_id}")
        assert r.status_code == 403

    def test_completed_job_has_grade(self, client, mock_db):
        job_id = str(uuid.uuid4())
        item = _make_dynamo_job(job_id, status="completed")
        item["grade"] = {"S": "A"}
        item["weighted_score"] = {"N": "94.5"}
        mock_db.get_item.return_value = {"Item": item}
        r = client.get(f"/api/v1/check/{job_id}")
        assert r.json()["grade"] == "A"

    def test_missing_api_key_returns_401(self, unauthed_client):
        r = unauthed_client.get(f"/api/v1/check/{uuid.uuid4()}")
        assert r.status_code == 401


# ===========================================================================
# GET /api/v1/history
# ===========================================================================

class TestHistory:

    def test_returns_200(self, client):
        r = client.get("/api/v1/history")
        assert r.status_code == 200

    def test_returns_list(self, client):
        r = client.get("/api/v1/history")
        assert isinstance(r.json()["runs"], list)

    def test_empty_when_no_runs(self, client, mock_db):
        mock_db.query.return_value = {"Items": []}
        r = client.get("/api/v1/history")
        assert r.json()["runs"] == []

    def test_missing_api_key_returns_401(self, unauthed_client):
        r = unauthed_client.get("/api/v1/history")
        assert r.status_code == 401

    def test_limit_param_accepted(self, client):
        r = client.get("/api/v1/history?limit=5")
        assert r.status_code == 200

    def test_limit_above_100_rejected(self, client):
        r = client.get("/api/v1/history?limit=101")
        assert r.status_code == 422


# ===========================================================================
# Client IP extraction (T8 Cloudflare header)
# ===========================================================================

class TestGetClientIp:

    def test_returns_cf_connecting_ip_when_trusted_header_set(self):
        from fynor.api.main import get_client_ip
        import os

        request = MagicMock()
        request.headers = {"CF-Connecting-IP": "203.0.113.42"}
        request.client = MagicMock()
        request.client.host = "10.0.0.1"  # Cloudflare edge IP

        with patch.dict(os.environ, {"TRUSTED_PROXY_HEADER": "CF-Connecting-IP"}):
            ip = get_client_ip(request)

        assert ip == "203.0.113.42"

    def test_falls_back_to_direct_ip_when_header_not_set(self):
        from fynor.api.main import get_client_ip
        import os

        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "198.51.100.7"

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TRUSTED_PROXY_HEADER", None)
            ip = get_client_ip(request)

        assert ip == "198.51.100.7"

    def test_falls_back_when_cf_header_absent_from_request(self):
        from fynor.api.main import get_client_ip
        import os

        request = MagicMock()
        request.headers = {}   # no CF-Connecting-IP header
        request.client = MagicMock()
        request.client.host = "192.0.2.1"

        with patch.dict(os.environ, {"TRUSTED_PROXY_HEADER": "CF-Connecting-IP"}):
            ip = get_client_ip(request)

        assert ip == "192.0.2.1"

    def test_returns_unknown_when_no_client(self):
        from fynor.api.main import get_client_ip
        import os

        request = MagicMock()
        request.headers = {}
        request.client = None

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TRUSTED_PROXY_HEADER", None)
            ip = get_client_ip(request)

        assert ip == "unknown"
