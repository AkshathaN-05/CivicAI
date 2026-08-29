"""Tests for Task 1-3 additions: camera image upload, location area_text,
and role-based API access.

Camera and geolocation are browser APIs — they cannot be invoked in a headless
pytest context.  These tests therefore verify:

  CAMERA:
  - An image uploaded via the existing photo field (regardless of how it was
    captured) is accepted and produces a valid 201 response.
  - A fake JPEG blob (simulating a canvas.toBlob() output) is accepted.
  - Only allowed MIME types pass; others return 422.

  LOCATION:
  - The area_text field (the existing location contract used by the API)
    accepts latitude/longitude coordinate strings produced by the browser's
    geolocation API.
  - The coordinates populate area_text and are stored correctly.
  - Manual text location still works unchanged.

  ROLE UI (backend enforcement):
  - Admin cannot POST a new citizen report via the citizen endpoint.
    (The backend does NOT have a role restriction on POST /reports/ — any
    authenticated user may submit.  The role restriction is enforced at the
    UI layer.  This test documents that admin JWTs are still valid JWTs and
    the backend would accept a POST — meaning the UI is the correct layer to
    hide "Report Issue" from admins, not a new backend restriction that would
    break admin test accounts.)
  - Admin CAN access /api/v1/admin/reports → 200.
  - Citizen CANNOT access /api/v1/admin/reports → 403.
  - Admin CAN access /api/v1/admin/stats → 200.
  - Citizen CANNOT access /api/v1/admin/stats → 403.
  - Unauthenticated request to citizen endpoint → 401.
  - Unauthenticated request to admin endpoint → 401.
"""
from __future__ import annotations

import io
import os
import sys
import time
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
# Key pair and token helpers (same pattern as test_reports.py)
# ---------------------------------------------------------------------------

TEST_KID = "tasks-1-3-test-key"


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


def _make_token(user_id: str = "user-tasks-test", role: str = "citizen") -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
        "app_metadata": {"role": role},
    }
    return jose_jwt.encode(payload, _PRIVATE_PEM, algorithm="ES256", headers={"kid": TEST_KID})


@pytest.fixture(autouse=True)
def _patch_jwks():
    import security.jwt_verify as jv
    with patch.object(jv, "_jwks_cache", {TEST_KID: _PUBLIC_KEY_OBJ}):
        with patch.object(jv, "_fetch_jwks", return_value={TEST_KID: _PUBLIC_KEY_OBJ}):
            yield


# ---------------------------------------------------------------------------
# Minimal valid JPEG bytes (1×1 pixel) — simulates a canvas.toBlob() output.
# This is the same as what the camera capture flow produces.
# ---------------------------------------------------------------------------
_MINIMAL_JPEG = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
    0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
    0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
    0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
    0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
    0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
    0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
    0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
    0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
    0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
    0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
    0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
    0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
    0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8A, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4,
    0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7,
    0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA,
    0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2, 0xE3,
    0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5,
    0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00,
    0x00, 0x3F, 0x00, 0xFB, 0x26, 0xA4, 0x00, 0xFF, 0xD9,
])


# ---------------------------------------------------------------------------
# TASK 1 — Camera image upload tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_camera_jpeg_blob_accepted():
    """A JPEG blob produced by canvas.toBlob() is accepted by the report endpoint.

    The camera capture flow converts the video frame to a JPEG file/blob and
    submits it as the existing 'photo' multipart field.  This test verifies
    the backend accepts it exactly as it accepts a file-picker upload.
    """
    token = _make_token(user_id="camera-test-citizen")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "pothole",
                "area_text": "Camera test location Mangaluru",
                "description": "Pothole captured via device camera at the junction.",
            },
            files={"photo": ("civic-photo-1234567890.jpg", io.BytesIO(_MINIMAL_JPEG), "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 201, f"Camera JPEG blob must be accepted, got {r.status_code}: {r.text}"
    body = r.json()
    assert body["photo_filename"] == "civic-photo-1234567890.jpg"


@pytest.mark.anyio
async def test_camera_capture_filename_pattern_accepted():
    """Report accepts any JPEG filename (including the camera timestamp pattern)."""
    token = _make_token(user_id="camera-filename-test")
    for fname in ["civic-photo-1700000000000.jpg", "photo.jpg", "camera_shot.jpg"]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/api/v1/reports/",
                data={
                    "category": "waterlogging",
                    "area_text": "Camera filename test area Mangaluru",
                    "description": "Waterlogging issue at this specific location here.",
                },
                files={"photo": (fname, io.BytesIO(_MINIMAL_JPEG), "image/jpeg")},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 201, f"Filename '{fname}' must be accepted: {r.text}"


@pytest.mark.anyio
async def test_non_image_mime_type_rejected():
    """Non-image MIME types (even with a .jpg filename) must return 422.

    The camera can only produce image/* blobs; anything else is invalid.
    """
    token = _make_token(user_id="camera-mime-test")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "garbage_overflow",
                "area_text": "MIME test area Mangaluru",
                "description": "Garbage overflow at this location for the test.",
            },
            files={"photo": ("photo.jpg", io.BytesIO(b"not an image"), "application/octet-stream")},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 422, f"Non-image MIME must be rejected: {r.status_code}"


@pytest.mark.anyio
async def test_camera_photo_not_required():
    """Submitting a report without a photo (camera or file) is still valid.

    Camera is optional — the citizen can submit without any photo.
    """
    token = _make_token(user_id="no-photo-test")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "road_damage",
                "area_text": "No photo test area Mangaluru",
                "description": "Road damage without attached photo at this location.",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 201
    assert r.json()["photo_filename"] is None


# ---------------------------------------------------------------------------
# TASK 2 — Location / area_text contract tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_location_coordinate_string_accepted():
    """Coordinates from navigator.geolocation are accepted in area_text.

    The frontend formats them as "lat, lon" (e.g. "12.86783, 74.84239") and
    populates the existing area_text field.  This must be a valid submission.
    """
    token = _make_token(user_id="location-coord-test")
    coord_text = "12.86783, 74.84239"  # sample Mangaluru coordinates
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "sewage",
                "area_text": coord_text,
                "description": "Sewage overflow at the detected GPS coordinates here.",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 201, f"Coordinate area_text must be accepted: {r.text}"
    assert r.json()["area_text"] == coord_text


@pytest.mark.anyio
async def test_location_manual_text_accepted():
    """Manual text location still works — coordinate auto-fill is optional."""
    token = _make_token(user_id="location-manual-test")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "pothole",
                "area_text": "Hampankatta main road near the bus stand",
                "description": "Large pothole at the bus stand junction location.",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 201
    assert r.json()["area_text"] == "Hampankatta main road near the bus stand"


@pytest.mark.anyio
async def test_location_too_short_rejected():
    """area_text shorter than 2 characters must still be rejected (validation unchanged)."""
    token = _make_token(user_id="location-short-test")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "pothole",
                "area_text": "X",
                "description": "Description long enough for the test validation here.",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 422, "area_text < 2 chars must be rejected"


# ---------------------------------------------------------------------------
# TASK 3 — Role-based API access tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_citizen_cannot_access_admin_endpoint():
    """Citizen JWT → 403 on /api/v1/admin/reports."""
    token = _make_token(user_id="citizen-role-test", role="citizen")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/admin/reports", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_citizen_cannot_access_admin_stats():
    """Citizen JWT → 403 on /api/v1/admin/stats."""
    token = _make_token(user_id="citizen-stats-role-test", role="citizen")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_admin_can_access_admin_reports():
    """Admin JWT → 200 on /api/v1/admin/reports."""
    token = _make_token(user_id="admin-role-test", role="admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/admin/reports", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "reports" in r.json()


@pytest.mark.anyio
async def test_admin_can_access_admin_stats():
    """Admin JWT → 200 on /api/v1/admin/stats."""
    token = _make_token(user_id="admin-stats-test-2", role="admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


@pytest.mark.anyio
async def test_unauthenticated_citizen_endpoint_returns_401():
    """No token on citizen endpoint → 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/reports/")
    assert r.status_code == 401


@pytest.mark.anyio
async def test_unauthenticated_admin_endpoint_returns_401():
    """No token on admin endpoint → 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/admin/reports")
    assert r.status_code == 401


@pytest.mark.anyio
async def test_role_ui_admin_not_blocked_at_backend_from_posting():
    """Document: the backend does NOT block admin JWT from POST /api/v1/reports/.

    The UI hides 'Report Issue' from admins; the backend enforces role for
    admin-only endpoints (RBAC).  Citizens and admins are both 'authenticated'
    and may technically submit a report.  The admin role separation is at the
    UI layer (Header.tsx), not via a new backend restriction.

    This test documents and preserves that contract.
    """
    token = _make_token(user_id="admin-can-post-doc", role="admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "other",
                "area_text": "Admin role-UI backend doc test area",
                "description": "Documentation test: admin JWT accepted at citizen endpoint.",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    # Backend accepts (201) — the role restriction is enforced at the UI layer.
    assert r.status_code == 201, (
        "Backend does not restrict POST /reports/ by role — UI is responsible for "
        "not showing 'Report Issue' to admins.  Backend RBAC is for admin-only endpoints."
    )
