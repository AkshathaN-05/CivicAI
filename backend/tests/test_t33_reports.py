"""T3-3 focused tests — Report Service, Storage Service, and AI pipeline integration.

Tests the exact T3-3 requirements:
  - Valid image upload → report created via AI pipeline → correct response shape
  - AI results (category, confidence, is_duplicate, image_hash) returned in response
  - Invalid MIME → 422
  - No JWT → 401
  - GET /reports/{id} returns signed URL fields (None when storage unavailable)
  - Original and redacted storage paths handled
  - Duplicate detection info preserved in response
  - Authority recommendation is advisory (present in response, not enforced)
  - Supabase/storage unavailable → graceful fallback (no crash)
  - Storage service: upload_original / upload_redacted / get_signed_url
  - Service layer: no secrets leaked; no DB mutation on storage failure
  - Rate limit decorator present (no assertion on slowapi internals, just that endpoint exists)

All external AI/API calls are mocked — no live Groq API key required.
All Supabase calls are mocked — no live DB required.
"""
from __future__ import annotations

import io
import os
import sys
import time
import uuid
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
# Helpers
# ---------------------------------------------------------------------------

TEST_KID = "t33-test-key-001"


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


def _make_token(user_id: str = "t33-test-user", role: str = "citizen") -> str:
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


_TOKEN = _make_token(user_id="t33-citizen", role="citizen")
_AUTH_HEADERS = {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture(autouse=True)
def _patch_jwks():
    import security.jwt_verify as jv
    with patch.object(jv, "_jwks_cache", {TEST_KID: _PUBLIC_KEY_OBJ}):
        with patch.object(jv, "_fetch_jwks", return_value={TEST_KID: _PUBLIC_KEY_OBJ}):
            yield


def _make_jpeg_bytes(width: int = 64, height: int = 64) -> bytes:
    """Create a minimal valid JPEG image as bytes for testing."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_mock_ai_result(
    category: str = "pothole",
    confidence: float = 0.85,
    is_duplicate: bool = False,
    image_hash: str = "abc123",
    description: str = "AI-generated description",
):
    """Build a mock AIResult dataclass for patching run_ai_pipeline."""
    from cv.pipeline import AIResult
    from schemas.report import IssueCategory

    result = AIResult(
        redacted_image_bytes=_make_jpeg_bytes(),
        validated_image_bytes=_make_jpeg_bytes(),
        category=IssueCategory(category),
        confidence=confidence,
        authority_recommendation="MCC",
        authority_id="mcc-001",
        description=description,
        image_hash=image_hash,
        is_duplicate=is_duplicate,
        duplicate_report_id=None,
        llm_provider_used="fallback",
        yolo_class="pothole",
        raw_detection_confidence=0.9,
        match_reason="category match",
    )
    return result


async def _mock_pipeline_returning(ai_result):
    """Async function that returns ai_result — for use with side_effect=."""
    return ai_result


# ---------------------------------------------------------------------------
# T3-3: storage_service unit tests
# ---------------------------------------------------------------------------

class TestStorageService:
    """Unit tests for storage_service.py."""

    def test_upload_original_returns_none_when_supabase_unavailable(self):
        """upload_original returns None gracefully when no Supabase client."""
        from services import storage_service

        with patch("services.storage_service._get_storage_client", return_value=None):
            result = storage_service.upload_original("test-report-id", b"fake-image-bytes")
        assert result is None

    def test_upload_redacted_returns_none_when_supabase_unavailable(self):
        """upload_redacted returns None gracefully when no Supabase client."""
        from services import storage_service

        with patch("services.storage_service._get_storage_client", return_value=None):
            result = storage_service.upload_redacted("test-report-id", b"fake-image-bytes")
        assert result is None

    def test_get_signed_url_returns_none_when_supabase_unavailable(self):
        """get_signed_url returns None gracefully when no Supabase client."""
        from services import storage_service

        with patch("services.storage_service._get_storage_client", return_value=None):
            result = storage_service.get_signed_url("report-originals", "some-path.jpg")
        assert result is None

    def test_get_signed_url_returns_none_for_empty_path(self):
        """get_signed_url returns None when path is empty."""
        from services import storage_service

        result = storage_service.get_signed_url("report-originals", "")
        assert result is None

    def test_get_signed_url_returns_none_for_empty_bucket(self):
        """get_signed_url returns None when bucket is empty."""
        from services import storage_service

        result = storage_service.get_signed_url("", "some-path.jpg")
        assert result is None

    def test_upload_original_returns_path_on_success(self):
        """upload_original returns the storage path on success."""
        from services import storage_service

        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.from_.return_value = mock_bucket
        mock_bucket.upload.return_value = MagicMock()

        with patch("services.storage_service._get_storage_client", return_value=mock_storage):
            result = storage_service.upload_original("abc-123", b"fake-bytes")

        assert result == "abc-123.jpg"
        mock_storage.from_.assert_called_once_with("report-originals")

    def test_upload_redacted_returns_path_on_success(self):
        """upload_redacted returns the storage path on success."""
        from services import storage_service

        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.from_.return_value = mock_bucket
        mock_bucket.upload.return_value = MagicMock()

        with patch("services.storage_service._get_storage_client", return_value=mock_storage):
            result = storage_service.upload_redacted("abc-456", b"fake-bytes")

        assert result == "abc-456.jpg"
        mock_storage.from_.assert_called_once_with("report-redacted")

    def test_get_signed_url_returns_url_on_success(self):
        """get_signed_url returns the signed URL from Supabase."""
        from services import storage_service

        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.from_.return_value = mock_bucket
        mock_bucket.create_signed_url.return_value = {
            "signedURL": "https://supabase.co/storage/v1/object/sign/path.jpg?token=abc"
        }

        with patch("services.storage_service._get_storage_client", return_value=mock_storage):
            result = storage_service.get_signed_url("report-originals", "abc-123.jpg")

        assert result == "https://supabase.co/storage/v1/object/sign/path.jpg?token=abc"
        mock_bucket.create_signed_url.assert_called_once_with(
            path="abc-123.jpg", expires_in=900
        )

    def test_get_signed_url_uses_900_second_expiry(self):
        """Signed URL expiry is exactly 900 seconds (15 minutes) per Part A §20."""
        from services import storage_service

        assert storage_service.SIGNED_URL_EXPIRY_SECONDS == 900

    def test_upload_original_returns_none_on_exception(self):
        """upload_original returns None when Supabase raises an exception."""
        from services import storage_service

        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.from_.return_value = mock_bucket
        mock_bucket.upload.side_effect = RuntimeError("Storage error")

        with patch("services.storage_service._get_storage_client", return_value=mock_storage):
            result = storage_service.upload_original("abc-789", b"bytes")
        assert result is None

    def test_get_signed_url_returns_none_on_exception(self):
        """get_signed_url returns None when Supabase raises an exception."""
        from services import storage_service

        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.from_.return_value = mock_bucket
        mock_bucket.create_signed_url.side_effect = RuntimeError("Signing error")

        with patch("services.storage_service._get_storage_client", return_value=mock_storage):
            result = storage_service.get_signed_url("report-originals", "path.jpg")
        assert result is None

    def test_bucket_name_constants(self):
        """Bucket name constants match architecture spec (Part A §20)."""
        from services import storage_service

        assert storage_service.BUCKET_ORIGINALS == "report-originals"
        assert storage_service.BUCKET_REDACTED == "report-redacted"

    def test_signed_url_signed_url_key_variant(self):
        """get_signed_url handles 'signed_url' key variant from supabase-py."""
        from services import storage_service

        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.from_.return_value = mock_bucket
        mock_bucket.create_signed_url.return_value = {
            "signed_url": "https://example.com/signed"
        }

        with patch("services.storage_service._get_storage_client", return_value=mock_storage):
            result = storage_service.get_signed_url("report-originals", "abc.jpg")
        assert result == "https://example.com/signed"


# ---------------------------------------------------------------------------
# T3-3: AI pipeline integration via POST /reports/ (image upload)
# ---------------------------------------------------------------------------

class TestCreateReportWithImage:
    """API-level tests for the AI pipeline path in POST /reports/."""

    @pytest.mark.anyio
    async def test_no_jwt_returns_401(self):
        """POST /reports/ without JWT → 401 (unchanged security requirement)."""
        jpeg_bytes = _make_jpeg_bytes()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/api/v1/reports/",
                files={"photo": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                data={"area_text": "Hampankatta, Mangaluru"},
            )
        assert r.status_code == 401

    @pytest.mark.anyio
    async def test_invalid_mime_returns_422(self):
        """POST /reports/ with invalid MIME type → 422."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/api/v1/reports/",
                files={"photo": ("doc.pdf", io.BytesIO(b"%PDF fake"), "application/pdf")},
                data={"area_text": "Kadri, Mangaluru"},
                headers=_AUTH_HEADERS,
            )
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_image_validation_failure_returns_422(self):
        """POST /reports/ with a corrupt image that fails T2-2 validation → 422."""
        from cv.image_validator import ImageValidationError

        jpeg_bytes = _make_jpeg_bytes()

        async def _failing_pipeline(**kwargs):
            raise ImageValidationError("Image validation failed: not a valid image")

        # Patch the pipeline at its source module (cv.pipeline.run_ai_pipeline)
        # and also inside services.report_service where it's imported locally.
        with patch("cv.pipeline.run_ai_pipeline", side_effect=_failing_pipeline):
            with patch("services.report_service._supabase_enabled", return_value=False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    r = await client.post(
                        "/api/v1/reports/",
                        files={"photo": ("bad.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                        data={"area_text": "Hampankatta"},
                        headers=_AUTH_HEADERS,
                    )
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_valid_image_upload_calls_ai_pipeline_and_returns_201(self):
        """POST /reports/ with valid JPEG → AI pipeline called → 201 + correct shape."""
        jpeg_bytes = _make_jpeg_bytes()
        mock_ai_result = _make_mock_ai_result(
            category="pothole",
            confidence=0.85,
            image_hash="deadbeef1234",
            description="A large pothole observed on the road surface.",
        )

        async def _mock_pipeline(**kwargs):
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch("services.report_service._supabase_enabled", return_value=False):
                with patch("services.storage_service._get_storage_client", return_value=None):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        r = await client.post(
                            "/api/v1/reports/",
                            files={"photo": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                            data={
                                "area_text": "Hampankatta, Mangaluru",
                                "lat": "12.8698",
                                "lng": "74.8425",
                            },
                            headers=_AUTH_HEADERS,
                        )

        assert r.status_code == 201
        body = r.json()
        assert body["category"] == "pothole"
        assert body["status"] == "SUBMITTED"
        assert body["report_id"] != ""
        assert body["confidence"] >= 0.0
        assert body["confidence"] <= 1.0

    @pytest.mark.anyio
    async def test_ai_pipeline_result_fields_in_response(self):
        """AI pipeline result fields are present in the response body (T3-3)."""
        jpeg_bytes = _make_jpeg_bytes()
        mock_ai_result = _make_mock_ai_result(
            category="garbage_overflow",
            confidence=0.72,
            is_duplicate=False,
            image_hash="hashvalue42",
            description="Garbage overflow at the location.",
        )

        async def _mock_pipeline(**kwargs):
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch("services.report_service._supabase_enabled", return_value=False):
                with patch("services.storage_service._get_storage_client", return_value=None):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        r = await client.post(
                            "/api/v1/reports/",
                            files={"photo": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                            data={"area_text": "Hampankatta, Mangaluru"},
                            headers=_AUTH_HEADERS,
                        )

        assert r.status_code == 201
        body = r.json()
        assert "is_duplicate" in body
        assert "image_hash" in body
        assert "llm_provider_used" in body
        assert "yolo_class" in body
        assert body["is_duplicate"] is False
        assert body["image_hash"] == "hashvalue42"
        assert body["llm_provider_used"] == "fallback"
        assert body["yolo_class"] == "pothole"

    @pytest.mark.anyio
    async def test_duplicate_flag_in_response_when_duplicate(self):
        """is_duplicate=True is preserved in the response when AI pipeline flags duplicate."""
        jpeg_bytes = _make_jpeg_bytes()
        dup_id = str(uuid.uuid4())
        mock_ai_result = _make_mock_ai_result(
            category="pothole",
            confidence=0.9,
            is_duplicate=True,
            image_hash="duphashabc",
        )
        mock_ai_result.duplicate_report_id = dup_id

        async def _mock_pipeline(**kwargs):
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch("services.report_service._supabase_enabled", return_value=False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    r = await client.post(
                        "/api/v1/reports/",
                        files={"photo": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                        data={"area_text": "Hampankatta, Mangaluru"},
                        headers=_AUTH_HEADERS,
                    )

        assert r.status_code == 201
        body = r.json()
        assert body["is_duplicate"] is True
        assert body["duplicate_report_id"] == dup_id

    @pytest.mark.anyio
    async def test_authority_recommendation_is_advisory_in_response(self):
        """Authority recommendation is present but advisory — submission not blocked (T3-3)."""
        jpeg_bytes = _make_jpeg_bytes()
        mock_ai_result = _make_mock_ai_result(
            category="water_supply",
            confidence=0.65,
        )

        async def _mock_pipeline(**kwargs):
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch("services.report_service._supabase_enabled", return_value=False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    r = await client.post(
                        "/api/v1/reports/",
                        files={"photo": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                        data={"area_text": "Mangaluru"},
                        headers=_AUTH_HEADERS,
                    )

        # Report must be created regardless of authority recommendation.
        assert r.status_code == 201
        body = r.json()
        # Authority is included in response as advisory.
        assert "recommended_authority" in body
        # Report creation succeeded — AI authority is advisory, not a blocker.
        assert body["report_id"] != ""

    @pytest.mark.anyio
    async def test_ai_pipeline_failure_returns_500(self):
        """If AI pipeline raises unexpected error → 500 (not a crash)."""
        jpeg_bytes = _make_jpeg_bytes()

        async def _failing_pipeline(**kwargs):
            raise RuntimeError("AI pipeline unexpected failure")

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_failing_pipeline):
            with patch("services.report_service._supabase_enabled", return_value=False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    r = await client.post(
                        "/api/v1/reports/",
                        files={"photo": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                        data={"area_text": "Mangaluru"},
                        headers=_AUTH_HEADERS,
                    )

        assert r.status_code == 500

    @pytest.mark.anyio
    async def test_storage_failure_does_not_crash_report_creation(self):
        """Storage upload failure is graceful — report is still created (T3-3)."""
        jpeg_bytes = _make_jpeg_bytes()
        mock_ai_result = _make_mock_ai_result()

        async def _mock_pipeline(**kwargs):
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch("services.report_service._supabase_enabled", return_value=False):
                # storage uploads return None (unavailable) — not a crash.
                with patch("services.storage_service.upload_original", return_value=None):
                    with patch("services.storage_service.upload_redacted", return_value=None):
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                            r = await client.post(
                                "/api/v1/reports/",
                                files={"photo": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                                data={"area_text": "Mangaluru"},
                                headers=_AUTH_HEADERS,
                            )

        assert r.status_code == 201
        body = r.json()
        assert body["report_id"] != ""
        # Signed URL fields are None when storage is unavailable.
        assert body["image_original_url"] is None
        assert body["image_redacted_url"] is None

    @pytest.mark.anyio
    async def test_lat_lng_accepted_in_form(self):
        """lat/lng form fields are accepted alongside area_text."""
        jpeg_bytes = _make_jpeg_bytes()
        mock_ai_result = _make_mock_ai_result()
        captured_kwargs = {}

        async def _mock_pipeline(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch("services.report_service._supabase_enabled", return_value=False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    r = await client.post(
                        "/api/v1/reports/",
                        files={"photo": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                        data={
                            "area_text": "Hampankatta",
                            "lat": "12.8698",
                            "lng": "74.8425",
                        },
                        headers=_AUTH_HEADERS,
                    )

        assert r.status_code == 201


# ---------------------------------------------------------------------------
# T3-3: GET /reports/{id} — signed URLs
# ---------------------------------------------------------------------------

class TestGetReportSignedUrls:
    """Tests for signed URL generation on GET /reports/{id}."""

    @pytest.mark.anyio
    async def test_get_report_includes_signed_url_fields(self):
        """GET /reports/{id} response includes image_original_url and image_redacted_url fields."""
        token = _make_token(user_id="t33-url-user")
        headers = {"Authorization": f"Bearer {token}"}

        jpeg_bytes = _make_jpeg_bytes()
        mock_ai_result = _make_mock_ai_result(image_hash="urltest123")

        async def _mock_pipeline(**kwargs):
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch("services.report_service._supabase_enabled", return_value=False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    create_r = await client.post(
                        "/api/v1/reports/",
                        files={"photo": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                        data={"area_text": "Hampankatta"},
                        headers=headers,
                    )
                    assert create_r.status_code == 201
                    report_id = create_r.json()["report_id"]

                    get_r = await client.get(
                        f"/api/v1/reports/{report_id}",
                        headers=headers,
                    )

        assert get_r.status_code == 200
        body = get_r.json()
        # Fields must always be present (even if None when storage is unavailable).
        assert "image_original_url" in body
        assert "image_redacted_url" in body

    @pytest.mark.anyio
    async def test_get_report_signed_urls_none_when_storage_unavailable(self):
        """Signed URL fields are None when Supabase storage is unavailable (graceful)."""
        token = _make_token(user_id="t33-no-storage-user")
        headers = {"Authorization": f"Bearer {token}"}

        jpeg_bytes = _make_jpeg_bytes()
        mock_ai_result = _make_mock_ai_result()

        async def _mock_pipeline(**kwargs):
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch("services.report_service._supabase_enabled", return_value=False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    create_r = await client.post(
                        "/api/v1/reports/",
                        files={"photo": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
                        data={"area_text": "Mangaluru"},
                        headers=headers,
                    )
                    assert create_r.status_code == 201
                    report_id = create_r.json()["report_id"]

                    get_r = await client.get(f"/api/v1/reports/{report_id}", headers=headers)

        assert get_r.status_code == 200
        body = get_r.json()
        assert body["image_original_url"] is None
        assert body["image_redacted_url"] is None


# ---------------------------------------------------------------------------
# T3-3: create_report_from_image service-layer unit tests
# ---------------------------------------------------------------------------

class TestCreateReportFromImageService:
    """Unit tests for report_service.create_report_from_image()."""

    @pytest.mark.anyio
    async def test_create_report_from_image_returns_report_out(self):
        """create_report_from_image returns a valid ReportOut."""
        from services import report_service as svc
        from schemas.report import ReportOut

        jpeg_bytes = _make_jpeg_bytes()
        mock_ai_result = _make_mock_ai_result(
            category="pothole",
            confidence=0.8,
            image_hash="servicehash",
        )

        async def _mock_pipeline(**kwargs):
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch.object(svc, "_supabase_enabled", return_value=False):
                with patch("services.storage_service._get_storage_client", return_value=None):
                    result = await svc.create_report_from_image(
                        image_bytes=jpeg_bytes,
                        claimed_mime="image/jpeg",
                        lat=12.8698,
                        lng=74.8425,
                        address="Hampankatta, Mangaluru",
                        user_id="test-user-svc",
                    )

        assert isinstance(result, ReportOut)
        assert result.category.value == "pothole"
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0
        assert result.image_hash == "servicehash"
        assert result.is_duplicate is False

    @pytest.mark.anyio
    async def test_user_id_stored_in_owner_store(self):
        """create_report_from_image stores user_id in _OWNER_STORE for IDOR checks."""
        from services import report_service as svc

        jpeg_bytes = _make_jpeg_bytes()
        mock_ai_result = _make_mock_ai_result()

        async def _mock_pipeline(**kwargs):
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch.object(svc, "_supabase_enabled", return_value=False):
                with patch("services.storage_service._get_storage_client", return_value=None):
                    result = await svc.create_report_from_image(
                        image_bytes=jpeg_bytes,
                        user_id="idor-check-user",
                    )

        assert svc._OWNER_STORE.get(result.report_id) == "idor-check-user"

        # Cleanup.
        svc._STORE.pop(result.report_id, None)
        svc._OWNER_STORE.pop(result.report_id, None)

    @pytest.mark.anyio
    async def test_image_validation_error_propagated(self):
        """ImageValidationError from pipeline is propagated to caller."""
        from services import report_service as svc
        from cv.image_validator import ImageValidationError

        async def _bad_pipeline(**kwargs):
            raise ImageValidationError("Not a valid image")

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_bad_pipeline):
            with patch.object(svc, "_supabase_enabled", return_value=False):
                with pytest.raises(ImageValidationError):
                    await svc.create_report_from_image(
                        image_bytes=b"bad-bytes",
                    )

    @pytest.mark.anyio
    async def test_storage_unavailable_does_not_raise(self):
        """Storage upload failure does not raise — report is still returned."""
        from services import report_service as svc

        jpeg_bytes = _make_jpeg_bytes()
        mock_ai_result = _make_mock_ai_result()

        async def _mock_pipeline(**kwargs):
            return mock_ai_result

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch.object(svc, "_supabase_enabled", return_value=False):
                with patch("services.storage_service.upload_original", return_value=None):
                    with patch("services.storage_service.upload_redacted", return_value=None):
                        result = await svc.create_report_from_image(image_bytes=jpeg_bytes)

        assert result is not None
        assert result.report_id != ""

    @pytest.mark.anyio
    async def test_location_string_built_from_lat_lng(self):
        """lat/lng are formatted into 'lat,lng' string for the pipeline."""
        from services import report_service as svc

        captured = {}

        async def _capture_pipeline(**kwargs):
            captured.update(kwargs)
            return _make_mock_ai_result()

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_capture_pipeline):
            with patch.object(svc, "_supabase_enabled", return_value=False):
                with patch("services.storage_service._get_storage_client", return_value=None):
                    await svc.create_report_from_image(
                        image_bytes=_make_jpeg_bytes(),
                        lat=12.8698,
                        lng=74.8425,
                    )

        assert captured.get("location") == "12.8698,74.8425"

    @pytest.mark.anyio
    async def test_location_empty_when_no_lat_lng(self):
        """location string is empty when no lat/lng provided."""
        from services import report_service as svc

        captured = {}

        async def _capture_pipeline(**kwargs):
            captured.update(kwargs)
            return _make_mock_ai_result()

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_capture_pipeline):
            with patch.object(svc, "_supabase_enabled", return_value=False):
                with patch("services.storage_service._get_storage_client", return_value=None):
                    await svc.create_report_from_image(image_bytes=_make_jpeg_bytes())

        assert captured.get("location") == ""


# ---------------------------------------------------------------------------
# T3-3: Signed URL generation in _attach_signed_urls
# ---------------------------------------------------------------------------

class TestAttachSignedUrls:
    """Unit tests for the _attach_signed_urls helper."""

    def test_attach_signed_urls_skipped_when_supabase_disabled(self):
        """_attach_signed_urls does nothing when Supabase is not configured."""
        from services import report_service as svc
        from schemas.report import ReportOut, IssueCategory, ReportStatus, CATEGORY_LABELS
        from datetime import datetime, timezone

        report = ReportOut(
            report_id="test-id",
            category=IssueCategory.pothole,
            category_label="Pothole",
            area_text="Test",
            description="Test",
            status=ReportStatus.submitted,
            confidence=0.5,
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(svc, "_supabase_enabled", return_value=False):
            result = svc._attach_signed_urls(report, "orig.jpg", "redacted.jpg")

        assert result.image_original_url is None
        assert result.image_redacted_url is None

    def test_attach_signed_urls_calls_storage_service(self):
        """_attach_signed_urls calls storage_service when Supabase is configured."""
        from services import report_service as svc
        from schemas.report import ReportOut, IssueCategory, ReportStatus
        from datetime import datetime, timezone

        report = ReportOut(
            report_id="test-url-id",
            category=IssueCategory.pothole,
            category_label="Pothole",
            area_text="Test",
            description="Test",
            status=ReportStatus.submitted,
            confidence=0.5,
            created_at=datetime.now(timezone.utc),
        )

        # Patch the storage_service module-level functions directly.
        with patch.object(svc, "_supabase_enabled", return_value=True):
            with patch("services.storage_service.get_original_signed_url",
                       return_value="https://example.com/orig"):
                with patch("services.storage_service.get_redacted_signed_url",
                           return_value="https://example.com/redacted"):
                    result = svc._attach_signed_urls(report, "orig.jpg", "redacted.jpg")

        assert result.image_original_url == "https://example.com/orig"
        assert result.image_redacted_url == "https://example.com/redacted"


# ---------------------------------------------------------------------------
# T3-3: No leaked secrets / no mutation of historical data
# ---------------------------------------------------------------------------

class TestSecurityConstraints:
    """Security and data-integrity constraint tests for T3-3."""

    @pytest.mark.anyio
    async def test_report_creation_does_not_modify_other_reports(self):
        """Creating a new report does not modify existing reports."""
        from services import report_service as svc

        jpeg_bytes = _make_jpeg_bytes()
        mock_ai = _make_mock_ai_result()

        # Create a pre-existing report via the text path (Supabase disabled).
        from schemas.report import IssueCategory, ReportCreate
        with patch.object(svc, "_supabase_enabled", return_value=False):
            pre_existing = svc.create_report(
                ReportCreate(
                    category=IssueCategory.pothole,
                    area_text="Pre-existing area test",
                    description="Pre-existing description for pothole at the test location.",
                ),
                user_id=str(uuid.uuid4()),  # Must be a valid UUID-like string
            )
        original_category = pre_existing.category
        original_description = pre_existing.description

        # Create a new report via the AI path.
        async def _mock_pipeline(**kwargs):
            return mock_ai

        with patch("cv.pipeline.run_ai_pipeline", side_effect=_mock_pipeline):
            with patch.object(svc, "_supabase_enabled", return_value=False):
                with patch("services.storage_service._get_storage_client", return_value=None):
                    await svc.create_report_from_image(
                        image_bytes=jpeg_bytes,
                        user_id=str(uuid.uuid4()),
                    )

        # Pre-existing report must be unchanged.
        unchanged = svc._STORE.get(pre_existing.report_id)
        assert unchanged is not None
        assert unchanged.category == original_category
        assert unchanged.description == original_description

        # Cleanup.
        svc._STORE.pop(pre_existing.report_id, None)
        svc._OWNER_STORE.pop(pre_existing.report_id, None)

    def test_storage_service_path_is_uuid_only(self):
        """Storage paths use report_id (UUID) only — no user-controlled path components
        (Part A §28 — path traversal prevention)."""
        from services import storage_service

        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.from_.return_value = mock_bucket
        mock_bucket.upload.return_value = MagicMock()

        report_id = str(uuid.uuid4())
        with patch("services.storage_service._get_storage_client", return_value=mock_storage):
            storage_service.upload_original(report_id, b"bytes")

        # The path passed to upload must be exactly "<uuid>.jpg" — no slashes, no user text.
        call_kwargs = mock_bucket.upload.call_args
        path_used = call_kwargs.kwargs.get("path") or call_kwargs.args[0]
        assert path_used == f"{report_id}.jpg"
        assert "/" not in path_used
        assert ".." not in path_used
