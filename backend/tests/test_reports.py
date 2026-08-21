"""Tests for reports API — Part A §18, T3-2, T3-3 requirements."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app


@pytest.mark.anyio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_create_report_basic():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "pothole",
                "area_text": "Hampankatta, Mangaluru",
                "description": "Large pothole near the main junction causing traffic delays.",
            },
        )
    assert r.status_code == 201
    body = r.json()
    assert body["category"] == "pothole"
    assert body["status"] == "SUBMITTED"
    assert body["report_id"] != ""
    assert body["recommended_authority"] is not None
    assert body["confidence"] > 0


@pytest.mark.anyio
async def test_create_report_area_keyword_match():
    """Hampankatta should route to MCC (area keyword match)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "garbage_overflow",
                "area_text": "Hampankatta main road",
                "description": "Overflowing garbage bins near the bus stand area.",
            },
        )
    assert r.status_code == 201
    body = r.json()
    assert body["confidence"] == 1.0  # keyword match
    assert "MCC" in body["recommended_authority"]["short_name"]


@pytest.mark.anyio
async def test_create_report_category_fallback():
    """Unknown area should still return category default authority."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "water_supply",
                "area_text": "Some unknown locality XYZ",
                "description": "No water supply for three days in this area.",
            },
        )
    assert r.status_code == 201
    body = r.json()
    assert body["recommended_authority"] is not None
    assert body["confidence"] == 0.7  # category fallback


@pytest.mark.anyio
async def test_create_report_validation_short_description():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/reports/",
            data={
                "category": "pothole",
                "area_text": "Kadri",
                "description": "Short",  # < 10 chars
            },
        )
    assert r.status_code == 422


@pytest.mark.anyio
async def test_create_report_invalid_mime(tmp_path):
    fake_pdf = tmp_path / "doc.pdf"
    fake_pdf.write_bytes(b"%PDF fake")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with open(fake_pdf, "rb") as f:
            r = await client.post(
                "/api/v1/reports/",
                data={
                    "category": "pothole",
                    "area_text": "Kadri",
                    "description": "Test description long enough.",
                },
                files={"photo": ("doc.pdf", f, "application/pdf")},
            )
    assert r.status_code == 422


@pytest.mark.anyio
async def test_list_reports():
    # Create one first
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/v1/reports/",
            data={
                "category": "road_damage",
                "area_text": "Kadri road",
                "description": "Road damage near the Kadri park entrance.",
            },
        )
        r = await client.get("/api/v1/reports/")
    assert r.status_code == 200
    body = r.json()
    assert "reports" in body
    assert isinstance(body["reports"], list)
    assert body["total"] >= 1


@pytest.mark.anyio
async def test_get_report_by_id():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/reports/",
            data={
                "category": "broken_streetlight",
                "area_text": "Bejai junction",
                "description": "Street light not working for the past week near Bejai junction.",
            },
        )
        report_id = create.json()["report_id"]
        r = await client.get(f"/api/v1/reports/{report_id}")
    assert r.status_code == 200
    assert r.json()["report_id"] == report_id


@pytest.mark.anyio
async def test_get_report_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/reports/nonexistent-id")
    assert r.status_code == 404
