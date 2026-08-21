"""T0-3 required test: GET /api/v1/health → 200, {"status": "ok"}"""
import pytest
from httpx import AsyncClient, ASGITransport

# Import the app; config.py has safe defaults so no .env needed
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app


@pytest.mark.anyio
async def test_health_returns_200():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
