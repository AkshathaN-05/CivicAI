"""Supabase Storage service — T3-3.

Manages image uploads to private Supabase Storage buckets and generates
15-minute signed URLs for image access.

Buckets (Part A §20):
  report-originals — private; original un-redacted images
  report-redacted  — private; privacy-processed redacted images

Path format (UUID-only — no user-controlled path components, Part A §28):
  {report_id}.jpg

Signed URL expiry: 900 seconds (15 minutes) per Part A §20 / T3-3.

Failure handling:
  All functions return None when Supabase is unavailable or storage fails.
  The caller (report_service) gracefully handles None — report creation
  continues with in-memory fallback; signed URLs are omitted from the response.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

BUCKET_ORIGINALS = "report-originals"
BUCKET_REDACTED = "report-redacted"
SIGNED_URL_EXPIRY_SECONDS = 900  # 15 minutes (Part A §20)


def _get_storage_client():
    """Return Supabase storage client, or None if unavailable."""
    from db.supabase_client import get_client

    client = get_client()
    if client is None:
        return None
    return client.storage


def upload_original(report_id: str, image_bytes: bytes) -> Optional[str]:
    """Upload original (un-redacted) image to report-originals bucket.

    Args:
        report_id:   UUID string — used as the storage path (UUID-only, no
                     user-controlled components, Part A §28 path traversal prevention).
        image_bytes: Raw JPEG bytes of the original validated image.

    Returns:
        Storage path string (e.g. ``"{report_id}.jpg"``) on success.
        None if Supabase is unavailable or upload fails.
    """
    storage = _get_storage_client()
    if storage is None:
        logger.debug("upload_original: Supabase unavailable — skipping storage upload.")
        return None

    path = f"{report_id}.jpg"
    try:
        storage.from_(BUCKET_ORIGINALS).upload(
            path=path,
            file=image_bytes,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )
        logger.debug("upload_original: uploaded %d bytes → %s/%s", len(image_bytes), BUCKET_ORIGINALS, path)
        return path
    except Exception:
        logger.warning(
            "upload_original: failed to upload to %s/%s.", BUCKET_ORIGINALS, path, exc_info=True
        )
        return None


def upload_redacted(report_id: str, image_bytes: bytes) -> Optional[str]:
    """Upload redacted image to report-redacted bucket.

    Args:
        report_id:   UUID string — used as the storage path.
        image_bytes: JPEG bytes of the privacy-redacted image.

    Returns:
        Storage path string on success; None on failure.
    """
    storage = _get_storage_client()
    if storage is None:
        logger.debug("upload_redacted: Supabase unavailable — skipping storage upload.")
        return None

    path = f"{report_id}.jpg"
    try:
        storage.from_(BUCKET_REDACTED).upload(
            path=path,
            file=image_bytes,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )
        logger.debug("upload_redacted: uploaded %d bytes → %s/%s", len(image_bytes), BUCKET_REDACTED, path)
        return path
    except Exception:
        logger.warning(
            "upload_redacted: failed to upload to %s/%s.", BUCKET_REDACTED, path, exc_info=True
        )
        return None


def get_signed_url(bucket: str, path: str) -> Optional[str]:
    """Generate a 15-minute signed URL for a storage object.

    Args:
        bucket: Bucket name (e.g. BUCKET_ORIGINALS or BUCKET_REDACTED).
        path:   Object path within the bucket.

    Returns:
        Signed URL string with 15-minute expiry; None if generation fails.
    """
    if not bucket or not path:
        return None

    storage = _get_storage_client()
    if storage is None:
        return None

    try:
        result = storage.from_(bucket).create_signed_url(
            path=path,
            expires_in=SIGNED_URL_EXPIRY_SECONDS,
        )
        # supabase-py 2.7.4 / storage3 returns a dict with key "signedURL"
        # (the full absolute URL is assembled by the client before returning).
        # Earlier versions used "signed_url" or "signedUrl" — check all variants
        # so the code is robust across patch upgrades.
        url = (
            result.get("signedURL")
            or result.get("signed_url")
            or result.get("signedUrl")
        )
        if not url:
            logger.warning(
                "get_signed_url: Supabase returned a response for %s/%s but "
                "no signed URL key was found. Response keys: %s. "
                "Check that the bucket exists and RLS policies allow signed URLs.",
                bucket, path, list(result.keys()) if isinstance(result, dict) else type(result),
            )
        return url
    except Exception:
        logger.warning(
            "get_signed_url: failed to create signed URL for %s/%s. "
            "Possible causes: bucket does not exist, RLS policy blocks access, "
            "or storage credentials are invalid.",
            bucket, path, exc_info=True,
        )
        return None


def get_original_signed_url(original_path: str) -> Optional[str]:
    """Convenience: signed URL for a report-originals path."""
    return get_signed_url(BUCKET_ORIGINALS, original_path)


def get_redacted_signed_url(redacted_path: str) -> Optional[str]:
    """Convenience: signed URL for a report-redacted path."""
    return get_signed_url(BUCKET_REDACTED, redacted_path)
