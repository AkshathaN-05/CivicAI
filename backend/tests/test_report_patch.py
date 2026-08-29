"""Tests for PATCH /api/v1/reports/{id} — citizen AI-first report patch (Priority 3).

Covers:

Auth / security:
  - unauthenticated PATCH → 401
  - citizen can patch own report → 200
  - citizen cannot patch another user's report → 403
  - admin can patch any report (bypasses ownership) → 200

Not-found:
  - PATCH on nonexistent report_id → 404

Input validation:
  - empty body (no fields) succeeds — all fields optional
  - category override is applied
  - description override is applied
  - authority_id override is applied
  - description too short after sanitization → 422
  - invalid category value → 422

State invariants:
  - PATCH never advances the report status (stays SUBMITTED)
  - GET /reports/{id} after PATCH reflects updated fields

Backward-compatibility:
  - existing POST /reports/ text path unaffected
"""
from __future__ import annotations

import sys
import os
import time
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from jose import jwk as jose_jwk, jwt as jose_jwt

from main import app

# ---------------------------------------------------------------------------
# Key / token helpers — mirrors the pattern in test_reports.py / test_admin_status.py
# ---------------------------------------------------------------------------

TEST_KID = "report-patch-test-key-001"


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


def _make_token(sub: str, role: str = "citizen", exp_offset: int = 3600) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "aud": "authenticated",
        "iat": now,
        "exp": now + exp_offset,
        # Role in app_metadata — matches how dependencies.py extracts app_role
        "app_metadata": {"role": role},
    }
    return jose_jwt.encode(
        payload,
        _PRIVATE_PEM,
        algorithm="ES256",
        headers={"kid": TEST_KID},
    )


# ---------------------------------------------------------------------------
# Auto-use fixture: inject the test public key into the JWKS cache
# (same pattern as test_reports.py and test_admin_status.py)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_jwks():
    import security.jwt_verify as jv
    with patch.object(jv, "_jwks_cache", {TEST_KID: _PUBLIC_KEY_OBJ}):
        with patch.object(jv, "_fetch_jwks", return_value={TEST_KID: _PUBLIC_KEY_OBJ}):
            yield


# ---------------------------------------------------------------------------
# Test users
# ---------------------------------------------------------------------------

CITIZEN_A = str(uuid.uuid4())
CITIZEN_B = str(uuid.uuid4())
ADMIN_USER = str(uuid.uuid4())


def _auth(sub: str, role: str = "citizen") -> dict:
    return {"Authorization": f"Bearer {_make_token(sub, role)}"}


async def _create_text_report(client: AsyncClient, sub: str, role: str = "citizen") -> str:
    """Create a report via the text path; return its report_id."""
    resp = await client.post(
        "/api/v1/reports/",
        data={
            "area_text": "Hampankatta main road",
            "category": "pothole",
            "description": "Large pothole causing traffic hazard near bus stand.",
        },
        headers=_auth(sub, role),
    )
    assert resp.status_code == 201, f"Setup POST failed: {resp.text}"
    return resp.json()["report_id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_unauthenticated_returns_401():
    """No JWT → 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={"description": "Updated description here longer."},
        )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_patch_own_report_returns_200():
    """Citizen can patch their own report."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={"description": "Updated description with more details about the large pothole."},
            headers=_auth(CITIZEN_A),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_id"] == report_id
    assert "Updated description" in data["description"]


@pytest.mark.anyio
async def test_patch_other_users_report_returns_403():
    """Citizen B cannot patch Citizen A's report (IDOR protection)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={"description": "Citizen B trying to modify someone else's report illegally."},
            headers=_auth(CITIZEN_B),
        )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_patch_admin_can_patch_any_report():
    """Admin bypasses ownership check."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={"description": "Admin corrected the description for accuracy here."},
            headers=_auth(ADMIN_USER, role="admin"),
        )
    assert resp.status_code == 200
    assert "Admin corrected" in resp.json()["description"]


@pytest.mark.anyio
async def test_patch_nonexistent_report_returns_404():
    """Patching a report_id that does not exist → 404."""
    fake_id = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/reports/{fake_id}",
            json={"description": "This report does not exist at all anywhere."},
            headers=_auth(CITIZEN_A),
        )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_patch_empty_body_succeeds():
    """Empty PATCH body is valid — all fields are optional."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={},
            headers=_auth(CITIZEN_A),
        )
    assert resp.status_code == 200
    assert resp.json()["report_id"] == report_id


@pytest.mark.anyio
async def test_patch_category_override_applied():
    """Citizen can override the AI category."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={"category": "road_damage"},
            headers=_auth(CITIZEN_A),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "road_damage"
    assert data["category_label"] == "Road Damage"


@pytest.mark.anyio
async def test_patch_description_override_applied():
    """Citizen can replace the AI-generated description."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={"description": "Citizen corrected description with full details about pothole."},
            headers=_auth(CITIZEN_A),
        )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Citizen corrected description with full details about pothole."


@pytest.mark.anyio
async def test_patch_authority_id_override_applied():
    """Citizen can override the recommended authority."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={"authority_id": "auth-005"},
            headers=_auth(CITIZEN_A),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["recommended_authority"] is not None
    assert data["recommended_authority"]["id"] == "auth-005"
    assert data["recommended_authority"]["short_name"] == "MESCOM"


@pytest.mark.anyio
async def test_patch_description_too_short_returns_422():
    """Description under 10 characters after sanitization → 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={"description": "Too short"},
            headers=_auth(CITIZEN_A),
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_patch_invalid_category_returns_422():
    """Unknown category value → Pydantic 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={"category": "not_a_real_category"},
            headers=_auth(CITIZEN_A),
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_patch_does_not_change_status():
    """PATCH never changes the report status — it must remain SUBMITTED."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        resp = await client.patch(
            f"/api/v1/reports/{report_id}",
            json={"description": "Status must remain SUBMITTED after this patch is applied."},
            headers=_auth(CITIZEN_A),
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUBMITTED"


@pytest.mark.anyio
async def test_get_report_after_patch_reflects_changes():
    """GET /reports/{id} after PATCH returns the updated fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_id = await _create_text_report(client, CITIZEN_A)
        await client.patch(
            f"/api/v1/reports/{report_id}",
            json={
                "category": "waterlogging",
                "description": "Severe waterlogging near the main drain outlet on Balmatta road.",
            },
            headers=_auth(CITIZEN_A),
        )
        get_resp = await client.get(
            f"/api/v1/reports/{report_id}",
            headers=_auth(CITIZEN_A),
        )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["category"] == "waterlogging"
    assert "waterlogging" in data["description"].lower() or "drain" in data["description"].lower()


@pytest.mark.anyio
async def test_existing_post_text_path_unaffected():
    """POST /reports/ text path still works correctly after Priority 3 changes."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/reports/",
            data={
                "area_text": "Bejai cross road",
                "category": "garbage_overflow",
                "description": "Overflowing garbage bin near the park entrance on main road here.",
            },
            headers=_auth(CITIZEN_A),
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "garbage_overflow"
    assert data["status"] == "SUBMITTED"
