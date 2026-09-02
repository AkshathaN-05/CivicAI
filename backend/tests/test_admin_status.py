"""Tests for admin status management — PATCH /api/v1/admin/reports/{id}/status.

Covers the requirements from the task specification:

Security / auth:
  - unauthenticated user cannot update status → 401
  - citizen cannot update status → 403
  - admin can update status → 200

Report lookup:
  - nonexistent report returns 404

Status transitions (from SUBMITTED):
  - SUBMITTED → UNDER_REVIEW succeeds
  - SUBMITTED → REJECTED requires reason; succeeds with reason
  - SUBMITTED → ARCHIVED succeeds
  - SUBMITTED → RESOLVED is invalid → 422

Status transitions (from UNDER_REVIEW):
  - UNDER_REVIEW → RESOLVED succeeds
  - UNDER_REVIEW → REJECTED requires reason; succeeds with reason
  - UNDER_REVIEW → SUBMITTED is invalid → 422

Terminal state:
  - ARCHIVED → anything is invalid → 422

Rejection reason rules:
  - REJECTED without reason → 422
  - REJECTED with empty reason → 422
  - REJECTED with reason → 200, reason persisted
  - Non-REJECTED with reason → 422 (reason not allowed)
  - Rejection reason is returned in response safely

Schema validation:
  - Attempting to set status=SUBMITTED (not admin-allowed) → 422
  - Attempting to set status=DRAFT (not admin-allowed) → 422

Backward compatibility:
  - Existing report creation (POST /reports/) still works
  - Existing in-memory report store untouched by this patch

Ownership:
  - Report ownership (user_id) remains unchanged after status update
"""
from __future__ import annotations

import sys
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from jose import jwk as jose_jwk, jwt as jose_jwt

from main import app

# ---------------------------------------------------------------------------
# Key generation & token helpers (mirror existing test pattern)
# ---------------------------------------------------------------------------

TEST_KID = "admin-status-test-key-001"


def _generate_ec_key_pair():
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    jose_public = jose_jwk.construct(public_pem, algorithm="ES256")
    return private_pem, jose_public


_PRIVATE_PEM, _PUBLIC_KEY_OBJ = _generate_ec_key_pair()


def _make_token(user_id: str = "test-user", role: str = "citizen") -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
        "app_metadata": {"role": role},
    }
    return jose_jwt.encode(
        payload,
        _PRIVATE_PEM,
        algorithm="ES256",
        headers={"kid": TEST_KID},
    )


_ADMIN_TOKEN = _make_token(user_id="admin-001", role="admin")
_CITIZEN_TOKEN = _make_token(user_id="citizen-001", role="citizen")
_ADMIN_HEADERS = {"Authorization": f"Bearer {_ADMIN_TOKEN}"}
_CITIZEN_HEADERS = {"Authorization": f"Bearer {_CITIZEN_TOKEN}"}


@pytest.fixture(autouse=True)
def _patch_jwks():
    """Patch JWKS cache so no live Supabase connection is required."""
    import security.jwt_verify as jv
    with patch.object(jv, "_jwks_cache", {TEST_KID: _PUBLIC_KEY_OBJ}):
        with patch.object(jv, "_fetch_jwks", return_value={TEST_KID: _PUBLIC_KEY_OBJ}):
            yield


@pytest.fixture(autouse=True)
def _disable_supabase():
    """Force Supabase to appear unconfigured for all in-memory tests.

    These tests seed reports into the in-memory _STORE.  Real Supabase
    credentials may be present in the environment (.env file), which would
    cause service functions to attempt live DB calls against a Supabase
    instance that does not contain the test UUIDs.  Patching _supabase_enabled
    to return False ensures the in-memory path is exercised exclusively.
    """
    with patch("services.report_service._supabase_enabled", return_value=False):
        yield


# ---------------------------------------------------------------------------
# Helpers: seed an in-memory report at a given status
# ---------------------------------------------------------------------------

def _seed_report(
    report_id: Optional[str] = None,
    status: str = "SUBMITTED",
    owner_user_id: str = "citizen-001",
    rejection_reason: Optional[str] = None,
) -> str:
    """Insert a ReportOut directly into the service's in-memory store."""
    from services import report_service
    from schemas.report import (
        IssueCategory,
        ReportOut,
        ReportStatus,
        CATEGORY_LABELS,
    )

    rid = report_id or str(uuid.uuid4())
    report = ReportOut(
        report_id=rid,
        category=IssueCategory.pothole,
        category_label=CATEGORY_LABELS["pothole"],
        area_text="Hampankatta, Mangaluru",
        description="Test pothole report for status tests.",
        status=ReportStatus(status),
        confidence=0.75,
        created_at=datetime.now(timezone.utc),
        rejection_reason=rejection_reason,
    )
    report_service._STORE[rid] = report
    report_service._OWNER_STORE[rid] = owner_user_id
    return rid


@pytest.fixture(autouse=True)
def _clear_store():
    """Reset the in-memory store before each test."""
    from services import report_service
    report_service._STORE.clear()
    report_service._OWNER_STORE.clear()
    yield
    report_service._STORE.clear()
    report_service._OWNER_STORE.clear()


# ---------------------------------------------------------------------------
# Helper: base URL for the PATCH endpoint
# ---------------------------------------------------------------------------

def _patch_url(report_id: str) -> str:
    return f"/api/v1/admin/reports/{report_id}/status"


# ===========================================================================
# Security / auth
# ===========================================================================

class TestStatusUpdateAuth:

    @pytest.mark.anyio
    async def test_unauthenticated_returns_401(self):
        """No JWT → 401."""
        rid = _seed_report()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "UNDER_REVIEW"},
            )
        assert r.status_code == 401

    @pytest.mark.anyio
    async def test_citizen_returns_403(self):
        """Citizen JWT → 403 (wrong role)."""
        rid = _seed_report()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_CITIZEN_HEADERS,
            )
        assert r.status_code == 403

    @pytest.mark.anyio
    async def test_admin_can_update_status(self):
        """Admin JWT → 200 on a valid transition."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "UNDER_REVIEW"
        assert body["report_id"] == rid

    @pytest.mark.anyio
    async def test_invalid_jwt_returns_401(self):
        """Garbage token → 401."""
        rid = _seed_report()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers={"Authorization": "Bearer not.a.real.token"},
            )
        assert r.status_code == 401


# ===========================================================================
# Report lookup
# ===========================================================================

class TestStatusUpdateLookup:

    @pytest.mark.anyio
    async def test_nonexistent_report_returns_404(self):
        """PATCH with an ID that does not exist → 404."""
        nonexistent_id = str(uuid.uuid4())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(nonexistent_id),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()


# ===========================================================================
# Status transitions — valid
# ===========================================================================

class TestValidTransitions:

    @pytest.mark.anyio
    async def test_submitted_to_under_review(self):
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "UNDER_REVIEW"

    @pytest.mark.anyio
    async def test_submitted_to_rejected_with_reason(self):
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={
                    "new_status": "REJECTED",
                    "rejection_reason": "Duplicate report",
                },
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "REJECTED"
        assert body["rejection_reason"] == "Duplicate report"

    @pytest.mark.anyio
    async def test_submitted_to_archived(self):
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "ARCHIVED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "ARCHIVED"

    @pytest.mark.anyio
    async def test_under_review_to_resolved(self):
        rid = _seed_report(status="UNDER_REVIEW")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "RESOLVED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "RESOLVED"

    @pytest.mark.anyio
    async def test_under_review_to_rejected_with_reason(self):
        rid = _seed_report(status="UNDER_REVIEW")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={
                    "new_status": "REJECTED",
                    "rejection_reason": "Invalid / unclear image",
                },
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "REJECTED"
        assert r.json()["rejection_reason"] == "Invalid / unclear image"

    @pytest.mark.anyio
    async def test_under_review_to_archived(self):
        rid = _seed_report(status="UNDER_REVIEW")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "ARCHIVED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "ARCHIVED"

    @pytest.mark.anyio
    async def test_resolved_to_archived(self):
        rid = _seed_report(status="RESOLVED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "ARCHIVED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "ARCHIVED"

    @pytest.mark.anyio
    async def test_rejected_to_archived(self):
        rid = _seed_report(status="REJECTED", rejection_reason="Duplicate report")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "ARCHIVED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "ARCHIVED"


# ===========================================================================
# Status transitions — invalid
# ===========================================================================

class TestInvalidTransitions:

    @pytest.mark.anyio
    async def test_submitted_to_resolved_is_invalid(self):
        """SUBMITTED → RESOLVED is not an allowed transition."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "RESOLVED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 422
        assert "invalid status transition" in r.json()["detail"].lower()

    @pytest.mark.anyio
    async def test_under_review_to_submitted_is_invalid(self):
        """Cannot go backward: UNDER_REVIEW → SUBMITTED."""
        rid = _seed_report(status="UNDER_REVIEW")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # SUBMITTED is not in ADMIN_ALLOWED_STATUSES so expect 422 at schema level
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "SUBMITTED"},
                headers=_ADMIN_HEADERS,
            )
        # Caught at Pydantic validation (not an admin-allowed status) → 422
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_archived_to_anything_is_invalid(self):
        """ARCHIVED is a terminal state — no further transitions."""
        rid = _seed_report(status="ARCHIVED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 422
        detail = r.json()["detail"].lower()
        assert "terminal" in detail or "invalid status transition" in detail

    @pytest.mark.anyio
    async def test_cannot_set_status_to_submitted(self):
        """SUBMITTED is not an admin-allowed target status."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "SUBMITTED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_cannot_set_status_to_draft(self):
        """DRAFT does not exist in the admin-allowed set."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "DRAFT"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 422


# ===========================================================================
# Rejection reason rules
# ===========================================================================

class TestRejectionReason:

    @pytest.mark.anyio
    async def test_rejected_without_reason_returns_422(self):
        """REJECTED with no rejection_reason → 422."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "REJECTED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_rejected_with_empty_reason_returns_422(self):
        """REJECTED with empty/whitespace rejection_reason → 422."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "REJECTED", "rejection_reason": "   "},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_rejected_with_reason_persisted_in_response(self):
        """REJECTED with a valid reason → reason returned in response."""
        rid = _seed_report(status="SUBMITTED")
        reason = "Insufficient information"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "REJECTED", "rejection_reason": reason},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "REJECTED"
        assert body["rejection_reason"] == reason

    @pytest.mark.anyio
    async def test_rejection_reason_persisted_in_memory_store(self):
        """After REJECTED, the reason is stored in the in-memory ReportOut."""
        from services import report_service

        rid = _seed_report(status="SUBMITTED")
        reason = "Not a civic issue"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "REJECTED", "rejection_reason": reason},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        stored = report_service._STORE.get(rid)
        assert stored is not None
        assert stored.rejection_reason == reason
        assert stored.status.value == "REJECTED"

    @pytest.mark.anyio
    async def test_non_rejected_status_with_reason_returns_422(self):
        """rejection_reason must not be provided for non-REJECTED statuses."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={
                    "new_status": "UNDER_REVIEW",
                    "rejection_reason": "This should not be allowed",
                },
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_rejection_reason_length_too_long_returns_422(self):
        """Rejection reason exceeding 500 chars → 422."""
        rid = _seed_report(status="SUBMITTED")
        long_reason = "X" * 501  # 501 chars, limit is 500
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "REJECTED", "rejection_reason": long_reason},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_rejection_reason_exactly_500_chars_succeeds(self):
        """Rejection reason at the 500-char limit → accepted."""
        rid = _seed_report(status="SUBMITTED")
        reason = "A" * 500
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "REJECTED", "rejection_reason": reason},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["rejection_reason"] == reason


# ===========================================================================
# Ownership — unchanged after status update
# ===========================================================================

class TestOwnershipPreserved:

    @pytest.mark.anyio
    async def test_report_ownership_unchanged_after_status_update(self):
        """Status update by admin does not alter report ownership."""
        from services import report_service

        owner_id = "original-citizen-456"
        rid = _seed_report(status="SUBMITTED", owner_user_id=owner_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200

        # Ownership must be unchanged in the in-memory store
        assert report_service._OWNER_STORE.get(rid) == owner_id

    @pytest.mark.anyio
    async def test_citizen_cannot_access_other_citizen_report_after_admin_update(self):
        """After admin status update, IDOR protection still holds for different citizen."""
        owner_id = "real-citizen-789"
        rid = _seed_report(status="SUBMITTED", owner_user_id=owner_id)

        # Admin updates status
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _patch_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200

        # Different citizen tries to read the report → 403
        other_citizen_token = _make_token(user_id="different-citizen-999", role="citizen")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(
                f"/api/v1/reports/{rid}",
                headers={"Authorization": f"Bearer {other_citizen_token}"},
            )
        assert r.status_code == 403


# ===========================================================================
# Schema — AdminStatusUpdate unit tests
# ===========================================================================

class TestAdminStatusUpdateSchema:

    def test_valid_under_review(self):
        from schemas.report import AdminStatusUpdate, ReportStatus
        obj = AdminStatusUpdate(new_status=ReportStatus.under_review)
        assert obj.new_status == ReportStatus.under_review
        assert obj.rejection_reason is None

    def test_valid_rejected_with_reason(self):
        from schemas.report import AdminStatusUpdate, ReportStatus
        obj = AdminStatusUpdate(new_status=ReportStatus.rejected, rejection_reason="Duplicate report")
        assert obj.rejection_reason == "Duplicate report"

    def test_rejected_without_reason_raises(self):
        from pydantic import ValidationError
        from schemas.report import AdminStatusUpdate, ReportStatus
        with pytest.raises(ValidationError):
            AdminStatusUpdate(new_status=ReportStatus.rejected)

    def test_non_rejected_with_reason_raises(self):
        from pydantic import ValidationError
        from schemas.report import AdminStatusUpdate, ReportStatus
        with pytest.raises(ValidationError):
            AdminStatusUpdate(new_status=ReportStatus.under_review, rejection_reason="nope")

    def test_submitted_is_not_allowed_target(self):
        from pydantic import ValidationError
        from schemas.report import AdminStatusUpdate, ReportStatus
        with pytest.raises(ValidationError):
            AdminStatusUpdate(new_status=ReportStatus.submitted)

    def test_reason_stripped_of_whitespace(self):
        from schemas.report import AdminStatusUpdate, ReportStatus
        obj = AdminStatusUpdate(new_status=ReportStatus.rejected, rejection_reason="  Duplicate  ")
        assert obj.rejection_reason == "Duplicate"

    def test_empty_reason_string_treated_as_none(self):
        """Whitespace-only reason is stripped to None → rejected without reason raises."""
        from pydantic import ValidationError
        from schemas.report import AdminStatusUpdate, ReportStatus
        with pytest.raises(ValidationError):
            AdminStatusUpdate(new_status=ReportStatus.rejected, rejection_reason="   ")


# ===========================================================================
# STATUS_TRANSITIONS correctness
# ===========================================================================

class TestStatusTransitionMap:
    """Unit test the transition map directly."""

    def test_submitted_allows_expected_transitions(self):
        from schemas.report import STATUS_TRANSITIONS, ReportStatus
        allowed = STATUS_TRANSITIONS[ReportStatus.submitted]
        assert ReportStatus.under_review in allowed
        assert ReportStatus.rejected in allowed
        assert ReportStatus.archived in allowed
        # Should NOT include
        assert ReportStatus.submitted not in allowed
        assert ReportStatus.resolved not in allowed

    def test_under_review_allows_expected_transitions(self):
        from schemas.report import STATUS_TRANSITIONS, ReportStatus
        allowed = STATUS_TRANSITIONS[ReportStatus.under_review]
        assert ReportStatus.resolved in allowed
        assert ReportStatus.rejected in allowed
        assert ReportStatus.archived in allowed
        assert ReportStatus.submitted not in allowed
        assert ReportStatus.under_review not in allowed

    def test_resolved_only_allows_archived(self):
        from schemas.report import STATUS_TRANSITIONS, ReportStatus
        allowed = STATUS_TRANSITIONS[ReportStatus.resolved]
        assert allowed == frozenset({ReportStatus.archived})

    def test_rejected_only_allows_archived(self):
        from schemas.report import STATUS_TRANSITIONS, ReportStatus
        allowed = STATUS_TRANSITIONS[ReportStatus.rejected]
        assert allowed == frozenset({ReportStatus.archived})

    def test_archived_is_terminal(self):
        from schemas.report import STATUS_TRANSITIONS, ReportStatus
        allowed = STATUS_TRANSITIONS[ReportStatus.archived]
        assert len(allowed) == 0


# ===========================================================================
# Backward compatibility — existing report creation still works
# ===========================================================================

class TestBackwardCompatibility:

    @pytest.mark.anyio
    async def test_create_report_text_path_still_works(self):
        """POST /api/v1/reports/ text path is unaffected (backward-compat)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/api/v1/reports/",
                data={
                    "category": "pothole",
                    "area_text": "Hampankatta main road",
                    "description": "Large pothole near the junction causing accidents.",
                },
                headers=_CITIZEN_HEADERS,
            )
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "SUBMITTED"
        assert body["rejection_reason"] is None

    @pytest.mark.anyio
    async def test_new_report_starts_as_submitted(self):
        """A freshly created report starts at SUBMITTED status."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/api/v1/reports/",
                data={
                    "category": "waterlogging",
                    "area_text": "Falnir road",
                    "description": "Waterlogging after rain blocking foot traffic near hospital.",
                },
                headers=_CITIZEN_HEADERS,
            )
        assert r.status_code == 201
        assert r.json()["status"] == "SUBMITTED"

    @pytest.mark.anyio
    async def test_get_report_returns_rejection_reason_field(self):
        """GET /reports/{id} includes rejection_reason in response body."""
        rid = _seed_report(status="REJECTED", rejection_reason="Not a civic issue")
        token = _make_token(user_id="citizen-001", role="citizen")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(
                f"/api/v1/reports/{rid}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 200
        assert r.json()["rejection_reason"] == "Not a civic issue"

    @pytest.mark.anyio
    async def test_admin_list_reports_returns_rejection_reason_field(self):
        """GET /admin/reports includes rejection_reason field in response shape.

        Uses in-memory path (Supabase disabled) to verify that the rejection_reason
        field is correctly surfaced in the list response for a REJECTED report.
        """
        rid = _seed_report(status="REJECTED", rejection_reason="Duplicate report")

        with patch("services.report_service._supabase_enabled", return_value=False) as _mock:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.get(
                    "/api/v1/admin/reports",
                    headers=_ADMIN_HEADERS,
                )
        assert r.status_code == 200
        reports = r.json()["reports"]
        matching = [rpt for rpt in reports if rpt["report_id"] == rid]
        assert matching, f"Seeded report {rid} not found in admin list (in-memory path)"
        assert matching[0]["rejection_reason"] == "Duplicate report"
