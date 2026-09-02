"""Regression tests for status persistence + citizen status synchronisation.

These tests target the specific bugs fixed in the CivicAI status tracking
flow:

  1. SUBMITTED → UNDER_REVIEW must succeed and persist.
  2. After UNDER_REVIEW is persisted: UNDER_REVIEW → RESOLVED must succeed.
  3. SUBMITTED → RESOLVED remains invalid (422).
  4. Reject (SUBMITTED → REJECTED with reason) continues to work.
  5. Rejection reason is persisted/read correctly (reports table, not complaints).
  6. Citizen fetching after admin sets UNDER_REVIEW receives UNDER_REVIEW.
  7. Citizen fetching after rejection receives REJECTED.
  8. Citizen fetching after resolution receives RESOLVED.
  9. DB failure (Supabase returns None) does NOT produce a 200 success response —
     returns 502 instead.
 10. Existing ownership/RBAC protections remain intact after status updates.

Architecture note:
  The authoritative lifecycle record is the ``public.reports`` table.
  The ``complaints`` table is defined in the schema but is NOT used by any
  current service or router code — all admin status actions and citizen reads
  target ``reports``.

All tests use in-memory storage (Supabase disabled via mock).  Supabase-specific
behaviour (the .select() fix) is covered by direct unit tests of the repo and
service layers.
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
# Key generation & token helpers
# ---------------------------------------------------------------------------

_TEST_KID = "status-persist-test-key-001"


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
        headers={"kid": _TEST_KID},
    )


_ADMIN_TOKEN = _make_token(user_id="admin-persist-001", role="admin")
_CITIZEN_TOKEN = _make_token(user_id="citizen-persist-001", role="citizen")
_ADMIN_HEADERS = {"Authorization": f"Bearer {_ADMIN_TOKEN}"}
_CITIZEN_HEADERS = {"Authorization": f"Bearer {_CITIZEN_TOKEN}"}


# ---------------------------------------------------------------------------
# JWKS patch — no live Supabase connection required
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_jwks():
    import security.jwt_verify as jv
    with patch.object(jv, "_jwks_cache", {_TEST_KID: _PUBLIC_KEY_OBJ}):
        with patch.object(jv, "_fetch_jwks", return_value={_TEST_KID: _PUBLIC_KEY_OBJ}):
            yield


@pytest.fixture(autouse=True)
def _disable_supabase():
    """Force Supabase to appear unconfigured for all in-memory tests.

    Tests in this module seed reports into the in-memory _STORE.  Real Supabase
    credentials may be present in the environment (.env file), which would cause
    service functions to attempt live DB calls against an instance that does not
    contain the test UUIDs.  Patching _supabase_enabled to return False ensures
    the in-memory path is exercised exclusively — EXCEPT for tests in
    TestDbFailureReturns502 which override this fixture locally.
    """
    with patch("services.report_service._supabase_enabled", return_value=False):
        yield


# ---------------------------------------------------------------------------
# In-memory store reset
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_store():
    from services import report_service
    report_service._STORE.clear()
    report_service._OWNER_STORE.clear()
    yield
    report_service._STORE.clear()
    report_service._OWNER_STORE.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_report(
    report_id: Optional[str] = None,
    status: str = "SUBMITTED",
    owner_user_id: str = "citizen-persist-001",
    rejection_reason: Optional[str] = None,
) -> str:
    """Insert a ReportOut directly into the service's in-memory store."""
    from services import report_service
    from schemas.report import IssueCategory, ReportOut, ReportStatus, CATEGORY_LABELS

    rid = report_id or str(uuid.uuid4())
    report = ReportOut(
        report_id=rid,
        category=IssueCategory.pothole,
        category_label=CATEGORY_LABELS["pothole"],
        area_text="Hampankatta, Mangaluru",
        description="Test pothole for status persistence tests.",
        status=ReportStatus(status),
        confidence=0.80,
        created_at=datetime.now(timezone.utc),
        rejection_reason=rejection_reason,
    )
    report_service._STORE[rid] = report
    report_service._OWNER_STORE[rid] = owner_user_id
    return rid


def _status_url(report_id: str) -> str:
    return f"/api/v1/admin/reports/{report_id}/status"


# ===========================================================================
# 1. SUBMITTED → UNDER_REVIEW: succeeds and persists
# ===========================================================================

class TestUnderReviewPersistence:

    @pytest.mark.anyio
    async def test_submitted_to_under_review_succeeds(self):
        """SUBMITTED → UNDER_REVIEW returns 200 with updated status."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "UNDER_REVIEW"

    @pytest.mark.anyio
    async def test_submitted_to_under_review_persists_in_store(self):
        """After SUBMITTED → UNDER_REVIEW, the in-memory store holds UNDER_REVIEW."""
        from services import report_service
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.patch(
                _status_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        stored = report_service._STORE.get(rid)
        assert stored is not None
        assert stored.status.value == "UNDER_REVIEW"


# ===========================================================================
# 2. After UNDER_REVIEW is persisted: UNDER_REVIEW → RESOLVED succeeds
# ===========================================================================

class TestResolveAfterUnderReview:

    @pytest.mark.anyio
    async def test_under_review_to_resolved_succeeds(self):
        """UNDER_REVIEW → RESOLVED must succeed (not fail with stale SUBMITTED)."""
        rid = _seed_report(status="UNDER_REVIEW")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "RESOLVED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "RESOLVED"

    @pytest.mark.anyio
    async def test_two_step_under_review_then_resolve(self):
        """Two-step: first move to UNDER_REVIEW, then Resolve from persisted state."""
        from services import report_service
        rid = _seed_report(status="SUBMITTED")

        # Step 1: Admin sets UNDER_REVIEW
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r1 = await client.patch(
                _status_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        assert r1.status_code == 200

        # Verify persisted
        assert report_service._STORE[rid].status.value == "UNDER_REVIEW"

        # Step 2: Admin resolves from UNDER_REVIEW (this is the previously failing case)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r2 = await client.patch(
                _status_url(rid),
                json={"new_status": "RESOLVED"},
                headers=_ADMIN_HEADERS,
            )
        assert r2.status_code == 200, (
            f"Expected 200 for UNDER_REVIEW → RESOLVED, got {r2.status_code}: {r2.json()}"
        )
        assert r2.json()["status"] == "RESOLVED"


# ===========================================================================
# 3. SUBMITTED → RESOLVED remains invalid
# ===========================================================================

class TestSubmittedToResolvedInvalid:

    @pytest.mark.anyio
    async def test_submitted_to_resolved_is_422(self):
        """SUBMITTED → RESOLVED must still be rejected (state machine preserved)."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "RESOLVED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 422
        detail = r.json()["detail"].lower()
        assert "invalid status transition" in detail

    @pytest.mark.anyio
    async def test_submitted_to_resolved_detail_mentions_states(self):
        """Error detail for SUBMITTED → RESOLVED names both states clearly."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "RESOLVED"},
                headers=_ADMIN_HEADERS,
            )
        detail = r.json()["detail"]
        assert "SUBMITTED" in detail
        assert "RESOLVED" in detail


# ===========================================================================
# 4. Reject continues to work
# ===========================================================================

class TestRejectFlowPreserved:

    @pytest.mark.anyio
    async def test_submitted_to_rejected_with_reason_succeeds(self):
        """Reject with a reason from SUBMITTED → 200 with REJECTED status."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "REJECTED", "rejection_reason": "Duplicate report"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "REJECTED"
        assert body["rejection_reason"] == "Duplicate report"

    @pytest.mark.anyio
    async def test_under_review_to_rejected_succeeds(self):
        """Reject from UNDER_REVIEW → 200."""
        rid = _seed_report(status="UNDER_REVIEW")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "REJECTED", "rejection_reason": "Invalid / unclear image"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "REJECTED"

    @pytest.mark.anyio
    async def test_rejected_without_reason_returns_422(self):
        """Reject without a reason → 422 (rule preserved)."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "REJECTED"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 422


# ===========================================================================
# 5. Rejection reason schema — reports table (not complaints)
# ===========================================================================

class TestRejectionReasonSchema:

    def test_report_out_has_rejection_reason_field(self):
        """ReportOut must include rejection_reason — it lives in reports table."""
        from schemas.report import ReportOut, IssueCategory, ReportStatus, CATEGORY_LABELS
        r = ReportOut(
            report_id=str(uuid.uuid4()),
            category=IssueCategory.pothole,
            category_label=CATEGORY_LABELS["pothole"],
            area_text="test",
            description="testing rejection reason field presence",
            status=ReportStatus.rejected,
            confidence=0.5,
            created_at=datetime.now(timezone.utc),
            rejection_reason="Not a civic issue",
        )
        assert r.rejection_reason == "Not a civic issue"

    @pytest.mark.anyio
    async def test_rejection_reason_readable_from_store_after_reject(self):
        """Rejection reason is persisted in the in-memory store and readable back."""
        from services import report_service
        rid = _seed_report(status="SUBMITTED")
        reason = "Not a civic issue"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "REJECTED", "rejection_reason": reason},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200
        stored = report_service._STORE[rid]
        assert stored.rejection_reason == reason

    def test_row_to_report_out_reads_rejection_reason_from_db_row(self):
        """_row_to_report_out maps rejection_reason from DB column to ReportOut."""
        from services.report_service import _row_to_report_out

        row = {
            "id": str(uuid.uuid4()),
            "ai_category": "pothole",
            "address_text": "Hampankatta",
            "ai_confidence": 0.7,
            "ai_authority_id": None,
            "ai_raw_response": {"description": "test desc"},
            "image_original_path": None,
            "image_redacted_path": None,
            "image_hash": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "status": "REJECTED",
            "rejection_reason": "Duplicate report",
        }
        result = _row_to_report_out(row)
        assert result is not None
        assert result.status.value == "REJECTED"
        assert result.rejection_reason == "Duplicate report"

    def test_row_to_report_out_reads_status_from_db_row(self):
        """_row_to_report_out reads status column (not default SUBMITTED) from DB."""
        from services.report_service import _row_to_report_out

        for status_val in ("SUBMITTED", "UNDER_REVIEW", "RESOLVED", "REJECTED"):
            row = {
                "id": str(uuid.uuid4()),
                "ai_category": "pothole",
                "address_text": "Test",
                "ai_confidence": 0.5,
                "ai_authority_id": None,
                "ai_raw_response": {"description": "desc"},
                "image_original_path": None,
                "image_redacted_path": None,
                "image_hash": None,
                "created_at": "2024-01-01T00:00:00+00:00",
                "status": status_val,
                "rejection_reason": None,
            }
            result = _row_to_report_out(row)
            assert result is not None, f"_row_to_report_out returned None for status={status_val}"
            assert result.status.value == status_val


# ===========================================================================
# 6–8. Citizen fetching sees the persisted status (in-memory path)
# ===========================================================================

class TestCitizenSeesPersistedStatus:

    @pytest.mark.anyio
    async def test_citizen_sees_under_review_after_admin_update(self):
        """After admin sets UNDER_REVIEW, citizen GET /reports returns UNDER_REVIEW."""
        rid = _seed_report(status="SUBMITTED", owner_user_id="citizen-persist-001")

        # Admin sets UNDER_REVIEW
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            patch_r = await client.patch(
                _status_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        assert patch_r.status_code == 200

        # Citizen lists their reports
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_r = await client.get(
                "/api/v1/reports/",
                headers=_CITIZEN_HEADERS,
            )
        assert list_r.status_code == 200
        reports = list_r.json()["reports"]
        matching = [rpt for rpt in reports if rpt["report_id"] == rid]
        assert matching, "Citizen's report not found in list response"
        assert matching[0]["status"] == "UNDER_REVIEW"

    @pytest.mark.anyio
    async def test_citizen_sees_rejected_after_admin_reject(self):
        """After admin rejects, citizen GET /reports returns REJECTED with reason."""
        rid = _seed_report(status="SUBMITTED", owner_user_id="citizen-persist-001")
        reason = "Insufficient / unclear evidence"

        # Admin rejects
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            patch_r = await client.patch(
                _status_url(rid),
                json={"new_status": "REJECTED", "rejection_reason": reason},
                headers=_ADMIN_HEADERS,
            )
        assert patch_r.status_code == 200

        # Citizen sees REJECTED
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_r = await client.get(
                "/api/v1/reports/",
                headers=_CITIZEN_HEADERS,
            )
        assert list_r.status_code == 200
        matching = [rpt for rpt in list_r.json()["reports"] if rpt["report_id"] == rid]
        assert matching
        assert matching[0]["status"] == "REJECTED"
        assert matching[0]["rejection_reason"] == reason

    @pytest.mark.anyio
    async def test_citizen_sees_resolved_after_admin_resolve(self):
        """After admin resolves (from UNDER_REVIEW), citizen sees RESOLVED."""
        rid = _seed_report(status="UNDER_REVIEW", owner_user_id="citizen-persist-001")

        # Admin resolves
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            patch_r = await client.patch(
                _status_url(rid),
                json={"new_status": "RESOLVED"},
                headers=_ADMIN_HEADERS,
            )
        assert patch_r.status_code == 200

        # Citizen sees RESOLVED
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_r = await client.get(
                "/api/v1/reports/",
                headers=_CITIZEN_HEADERS,
            )
        assert list_r.status_code == 200
        matching = [rpt for rpt in list_r.json()["reports"] if rpt["report_id"] == rid]
        assert matching
        assert matching[0]["status"] == "RESOLVED"

    @pytest.mark.anyio
    async def test_citizen_get_single_report_sees_correct_status(self):
        """Citizen GET /reports/{id} also returns the persisted status."""
        rid = _seed_report(status="SUBMITTED", owner_user_id="citizen-persist-001")

        # Admin moves to UNDER_REVIEW
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.patch(
                _status_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )

        # Citizen fetches single report
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            get_r = await client.get(
                f"/api/v1/reports/{rid}",
                headers=_CITIZEN_HEADERS,
            )
        assert get_r.status_code == 200
        assert get_r.json()["status"] == "UNDER_REVIEW"


# ===========================================================================
# 9. DB failure → 502 (not a fake 200 success)
# ===========================================================================

class TestDbFailureReturns502:

    @pytest.mark.anyio
    async def test_supabase_enabled_but_update_returns_none_gives_502(self):
        """When Supabase is 'enabled' but update_report_status returns None,
        the service must return 502 rather than a fake 200 success.

        This is the exact scenario that was producing the silent data divergence:
        admin UI showed UNDER_REVIEW while DB still held SUBMITTED.
        """
        rid = _seed_report(status="SUBMITTED")

        with patch("services.report_service._supabase_enabled", return_value=True):
            with patch(
                "db.repositories.report_repo.update_report_status",
                return_value=None,  # Simulates empty data returned by supabase-py
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    r = await client.patch(
                        _status_url(rid),
                        json={"new_status": "UNDER_REVIEW"},
                        headers=_ADMIN_HEADERS,
                    )

        # Must NOT be 200 — that would be the fake success that causes citizen staleness
        assert r.status_code == 502, (
            f"Expected 502 when DB update returns None, got {r.status_code}: {r.json()}"
        )
        detail = r.json()["detail"].lower()
        assert "database" in detail or "confirmed" in detail

    @pytest.mark.anyio
    async def test_supabase_enabled_but_exception_gives_502(self):
        """When Supabase raises an exception during update, service returns 502."""
        rid = _seed_report(status="SUBMITTED")

        def _raise(*args, **kwargs):
            raise RuntimeError("Simulated Supabase connection failure")

        with patch("services.report_service._supabase_enabled", return_value=True):
            with patch(
                "db.repositories.report_repo.update_report_status",
                side_effect=_raise,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    r = await client.patch(
                        _status_url(rid),
                        json={"new_status": "UNDER_REVIEW"},
                        headers=_ADMIN_HEADERS,
                    )

        assert r.status_code == 502

    @pytest.mark.anyio
    async def test_supabase_disabled_uses_in_memory_and_returns_200(self):
        """When Supabase is NOT configured (local dev), in-memory path returns 200."""
        rid = _seed_report(status="SUBMITTED")

        with patch("services.report_service._supabase_enabled", return_value=False):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.patch(
                    _status_url(rid),
                    json={"new_status": "UNDER_REVIEW"},
                    headers=_ADMIN_HEADERS,
                )

        assert r.status_code == 200
        assert r.json()["status"] == "UNDER_REVIEW"


# ===========================================================================
# 10. Ownership/RBAC protections remain intact
# ===========================================================================

class TestOwnershipRbacIntact:

    @pytest.mark.anyio
    async def test_citizen_cannot_update_status(self):
        """Citizen role cannot call the admin status update endpoint."""
        rid = _seed_report(status="SUBMITTED", owner_user_id="citizen-persist-001")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_CITIZEN_HEADERS,
            )
        assert r.status_code == 403

    @pytest.mark.anyio
    async def test_unauthenticated_cannot_update_status(self):
        """No token → 401 on admin status endpoint."""
        rid = _seed_report(status="SUBMITTED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "UNDER_REVIEW"},
            )
        assert r.status_code == 401

    @pytest.mark.anyio
    async def test_other_citizen_cannot_read_report_after_status_update(self):
        """IDOR protection: a different citizen cannot access a report after admin update."""
        owner_id = "original-owner-789"
        rid = _seed_report(status="SUBMITTED", owner_user_id=owner_id)

        # Admin sets UNDER_REVIEW
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                _status_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )
        assert r.status_code == 200

        # Different citizen tries to read the report
        other_token = _make_token(user_id="different-citizen-999", role="citizen")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(
                f"/api/v1/reports/{rid}",
                headers={"Authorization": f"Bearer {other_token}"},
            )
        assert r.status_code == 403

    @pytest.mark.anyio
    async def test_owner_can_still_read_own_report_after_status_update(self):
        """Owner can still read their report after an admin status change."""
        rid = _seed_report(status="SUBMITTED", owner_user_id="citizen-persist-001")

        # Admin updates
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.patch(
                _status_url(rid),
                json={"new_status": "UNDER_REVIEW"},
                headers=_ADMIN_HEADERS,
            )

        # Owner reads their own report — should succeed
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(
                f"/api/v1/reports/{rid}",
                headers=_CITIZEN_HEADERS,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "UNDER_REVIEW"
