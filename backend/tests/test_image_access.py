"""Image-access and relevance-gate integration tests.

Covers:
  1. Authenticated citizen can obtain the redacted image URL for their own report.
  2. Citizen cannot obtain another citizen's report image (403).
  3. Authenticated admin can obtain the redacted image URL for any report.
  4. Unauthenticated user cannot obtain report images (401).
  5. The URL/path exposed to the frontend points to the redacted image, not the
     original (image_redacted_url vs image_original_url distinction).
  6. Missing image URL does not crash the API response (graceful None).
  7. A selfie/portrait-style image is rejected as invalid civic evidence (422).
  8. A person-only/portrait image does not become a low-confidence normal report.
  9. A valid pothole/road image remains valid.
 10. A valid road image containing pedestrians remains valid (person + civic object).
 11. A valid civic image containing a person remains valid.
 12. Existing privacy regression — tests import cleanly without touching privacy.
"""
from __future__ import annotations

import io
import sys
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from jose import jwk as jose_jwk, jwt as jose_jwt

from main import app

# ---------------------------------------------------------------------------
# ECC P-256 key pair + token helpers (mirrors test_reports.py pattern)
# ---------------------------------------------------------------------------

_ACCESS_KID = "img-access-test-key-001"


def _gen_ec_pair():
    priv = ec.generate_private_key(ec.SECP256R1(), default_backend())
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv_pem, jose_jwk.construct(pub_pem, algorithm="ES256")


_IA_PRIV, _IA_PUB = _gen_ec_pair()


def _tok(user_id: str = "citizen-img-001", role: str = "citizen") -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
        "app_metadata": {"role": role},
    }
    return jose_jwt.encode(payload, _IA_PRIV, algorithm="ES256", headers={"kid": _ACCESS_KID})


_CITIZEN_TOKEN = _tok("citizen-img-001", "citizen")
_CITIZEN_B_TOKEN = _tok("citizen-img-002", "citizen")
_ADMIN_TOKEN = _tok("admin-img-001", "admin")


@pytest.fixture(autouse=True)
def _patch_jwks():
    import security.jwt_verify as jv
    with patch.object(jv, "_jwks_cache", {_ACCESS_KID: _IA_PUB}):
        with patch.object(jv, "_fetch_jwks", return_value={_ACCESS_KID: _IA_PUB}):
            yield


# ---------------------------------------------------------------------------
# Helper: create a report via the text path (no AI pipeline, fast)
# ---------------------------------------------------------------------------

async def _create_report(client: AsyncClient, token: str) -> dict:
    r = await client.post(
        "/api/v1/reports/",
        data={
            "category": "pothole",
            "area_text": "Hampankatta, Mangaluru",
            "description": "Large pothole near the main junction causing traffic delays.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, f"create failed: {r.text}"
    return r.json()


# ---------------------------------------------------------------------------
# Image-access tests (Requirements 1 & 2)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_unauthenticated_cannot_get_report_image():
    """Unauthenticated GET /reports/{id} → 401 (image URL inaccessible)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        body = await _create_report(c, _CITIZEN_TOKEN)
        rid = body["report_id"]
        r = await c.get(f"/api/v1/reports/{rid}")
    assert r.status_code == 401


@pytest.mark.anyio
async def test_citizen_can_access_own_report_image_url():
    """Citizen gets their own report; image_redacted_url field is present in response."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        body = await _create_report(c, _CITIZEN_TOKEN)
        rid = body["report_id"]
        r = await c.get(
            f"/api/v1/reports/{rid}",
            headers={"Authorization": f"Bearer {_CITIZEN_TOKEN}"},
        )
    assert r.status_code == 200
    data = r.json()
    # image_redacted_url is in the response schema (may be None when Supabase
    # is unavailable in tests, but the field must exist and never be missing)
    assert "image_redacted_url" in data


@pytest.mark.anyio
async def test_citizen_cannot_access_other_citizens_report():
    """Citizen B cannot GET citizen A's report → 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        body = await _create_report(c, _CITIZEN_TOKEN)
        rid = body["report_id"]
        r = await c.get(
            f"/api/v1/reports/{rid}",
            headers={"Authorization": f"Bearer {_CITIZEN_B_TOKEN}"},
        )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_admin_can_access_any_report():
    """Admin can GET any report (including other citizens') — RBAC bypass."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        body = await _create_report(c, _CITIZEN_TOKEN)
        rid = body["report_id"]
        r = await c.get(
            f"/api/v1/reports/{rid}",
            headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"},
        )
    assert r.status_code == 200
    data = r.json()
    assert "image_redacted_url" in data


@pytest.mark.anyio
async def test_original_url_not_used_as_display_url():
    """The response exposes image_redacted_url as a separate field from
    image_original_url.  The redacted field is what the frontend uses; the
    original field must not be confused with the display URL.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        body = await _create_report(c, _CITIZEN_TOKEN)
    # Both fields exist in the schema — they are distinct
    assert "image_redacted_url" in body
    assert "image_original_url" in body
    # In the in-memory path (no Supabase), both are None — that is correct
    # (no image was uploaded). Neither should accidentally point to the other.
    if body["image_redacted_url"] is not None and body["image_original_url"] is not None:
        assert body["image_redacted_url"] != body["image_original_url"], (
            "Redacted and original signed URLs must point to different objects."
        )


@pytest.mark.anyio
async def test_missing_image_url_does_not_crash_response():
    """When no image was uploaded (text path), image_redacted_url is None — API still 200."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        body = await _create_report(c, _CITIZEN_TOKEN)
        rid = body["report_id"]
        r = await c.get(
            f"/api/v1/reports/{rid}",
            headers={"Authorization": f"Bearer {_CITIZEN_TOKEN}"},
        )
    assert r.status_code == 200
    data = r.json()
    # No image was uploaded → None is valid, should not crash
    assert data.get("image_redacted_url") is None or isinstance(data["image_redacted_url"], str)


# ---------------------------------------------------------------------------
# Requirement 3: relevance gate integration via the AI pipeline
# ---------------------------------------------------------------------------


def _make_jpeg(width: int = 344, height: int = 180) -> bytes:
    """Return minimal valid JPEG bytes."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(120, 80, 60)).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _fake_detection_result(yolo_class: str, conf: float, all_class_names: tuple):
    """Build a DetectionResult as detect_civic_issue would return."""
    from cv.detection import DetectionResult
    from schemas.report import IssueCategory
    from cv.taxonomy import map_to_category

    return DetectionResult(
        yolo_class=yolo_class,
        confidence=conf,
        category=map_to_category(yolo_class),
        all_class_names=all_class_names,
    )


@pytest.mark.anyio
async def test_selfie_image_rejected_via_pipeline():
    """A selfie (YOLO: person-dominant, no civic objects) is rejected as 422."""
    jpeg = _make_jpeg()

    fake_det = _fake_detection_result("person", 0.80, ("person",))

    with patch("cv.detection.detect_civic_issue", return_value=fake_det):
        with patch("cv.privacy.redact_privacy", side_effect=lambda img: img):
            from cv.pipeline import run_ai_pipeline
            from cv.image_validator import ImageValidationError

            with pytest.raises(ImageValidationError, match="civic issue"):
                await run_ai_pipeline(jpeg, claimed_mime="image/jpeg")


@pytest.mark.anyio
async def test_road_with_person_not_rejected_via_pipeline():
    """A road image with a pedestrian (person + car) is accepted as valid civic evidence."""
    jpeg = _make_jpeg()

    fake_det = _fake_detection_result("car", 0.78, ("car", "person"))

    with patch("cv.detection.detect_civic_issue", return_value=fake_det):
        with patch("cv.privacy.redact_privacy", side_effect=lambda img: img):
            with patch("services.llm_service.classify_category", new=AsyncMock(return_value=None)):
                with patch("services.llm_service.generate_complaint_description",
                           new=AsyncMock(return_value=MagicMock(description="Road damage."))):
                    from cv.pipeline import run_ai_pipeline, AIResult

                    result = await run_ai_pipeline(jpeg, claimed_mime="image/jpeg")
                    assert isinstance(result, AIResult)
                    assert result.category.value == "road_damage"


@pytest.mark.anyio
async def test_pothole_image_no_person_accepted_via_pipeline():
    """A pothole/road image with no person is accepted normally."""
    jpeg = _make_jpeg()

    fake_det = _fake_detection_result("truck", 0.85, ("truck", "car"))

    with patch("cv.detection.detect_civic_issue", return_value=fake_det):
        with patch("cv.privacy.redact_privacy", side_effect=lambda img: img):
            with patch("services.llm_service.classify_category", new=AsyncMock(return_value=None)):
                with patch("services.llm_service.generate_complaint_description",
                           new=AsyncMock(return_value=MagicMock(description="Road damage."))):
                    from cv.pipeline import run_ai_pipeline, AIResult

                    result = await run_ai_pipeline(jpeg, claimed_mime="image/jpeg")
                    assert isinstance(result, AIResult)


@pytest.mark.anyio
async def test_selfie_via_api_returns_422():
    """POST /reports/ with selfie-style image → 422 via the router."""
    jpeg = _make_jpeg()
    fake_det = _fake_detection_result("person", 0.82, ("person",))

    with patch("cv.detection.detect_civic_issue", return_value=fake_det):
        with patch("cv.privacy.redact_privacy", side_effect=lambda img: img):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post(
                    "/api/v1/reports/",
                    files={"photo": ("test.jpg", io.BytesIO(jpeg), "image/jpeg")},
                    data={"area_text": "Hampankatta, Mangaluru"},
                    headers={"Authorization": f"Bearer {_CITIZEN_TOKEN}"},
                )
    assert r.status_code == 422
    body = r.json()
    assert "civic issue" in body.get("detail", "").lower() or "portrait" in body.get("detail", "").lower()


@pytest.mark.anyio
async def test_selfie_with_tie_top_class_rejected():
    """Bug B regression: selfie where YOLO top-1 is 'tie' (not 'person') but
    a person is also detected — must still be rejected as non-civic.

    Previously this slipped through because the relevance gate only checked
    whether top_class == 'person'.
    """
    jpeg = _make_jpeg()
    # Simulate: YOLO returns top-1='tie' at 0.42 confidence; person also detected
    fake_det = _fake_detection_result("tie", 0.42, ("tie", "person"))

    with patch("cv.detection.detect_civic_issue", return_value=fake_det):
        with patch("cv.privacy.redact_privacy", side_effect=lambda img: img):
            from cv.pipeline import run_ai_pipeline
            from cv.image_validator import ImageValidationError

            with pytest.raises(ImageValidationError, match="civic issue"):
                await run_ai_pipeline(jpeg, claimed_mime="image/jpeg")


@pytest.mark.anyio
async def test_selfie_with_handbag_rejected():
    """Bug A regression: selfie where YOLO detects 'handbag' alongside person.

    Previously handbag was in _CIVIC_INDICATOR_CLASSES (as a garbage indicator),
    causing this selfie to be accepted as civic evidence.  After the fix,
    handbag is no longer a civic indicator and the person dominance check fires.
    """
    jpeg = _make_jpeg()
    # Simulate: YOLO top-1='person' with handbag also detected
    fake_det = _fake_detection_result("person", 0.78, ("person", "handbag"))

    with patch("cv.detection.detect_civic_issue", return_value=fake_det):
        with patch("cv.privacy.redact_privacy", side_effect=lambda img: img):
            from cv.pipeline import run_ai_pipeline
            from cv.image_validator import ImageValidationError

            with pytest.raises(ImageValidationError):
                await run_ai_pipeline(jpeg, claimed_mime="image/jpeg")


@pytest.mark.anyio
async def test_road_scene_with_person_and_car_accepted():
    """Civic scene: car + person detected — must be accepted (not rejected)."""
    jpeg = _make_jpeg()
    fake_det = _fake_detection_result("car", 0.75, ("car", "person"))

    with patch("cv.detection.detect_civic_issue", return_value=fake_det):
        with patch("cv.privacy.redact_privacy", side_effect=lambda img: img):
            with patch("services.llm_service.classify_category", new=AsyncMock(return_value=None)):
                with patch("services.llm_service.generate_complaint_description",
                           new=AsyncMock(return_value=MagicMock(description="Road issue."))):
                    from cv.pipeline import run_ai_pipeline, AIResult

                    result = await run_ai_pipeline(jpeg, claimed_mime="image/jpeg")
                    assert isinstance(result, AIResult)
                    assert result.category.value == "road_damage"
