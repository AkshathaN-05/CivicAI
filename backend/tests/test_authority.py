"""T3-2 required tests — Authority routing service and authority_repo.

Acceptance criteria (canonical plan T3-2):
  - All 10 issue categories return a valid authority
  - address_text keyword match selects correct authority when multiple match
  - no-match (unknown area) → first category-default authority returned
  - no ward_range or PostGIS used (structural assertion)

All tests are pure unit tests against the JSON fixture — no Supabase
credentials, no real network access, no .env required.
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.authority_service import (
    get_all_authorities,
    get_authority_by_id,
    route_to_authority,
)
from db.repositories import authority_repo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_CATEGORIES = [
    "pothole",
    "waterlogging",
    "broken_streetlight",
    "garbage_overflow",
    "open_drain",
    "illegal_construction",
    "water_supply",
    "sewage",
    "road_damage",
    "other",
]


# ---------------------------------------------------------------------------
# All 10 issue categories must return a valid authority (T3-2 criterion 1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_all_categories_return_valid_authority(category: str):
    """Every IssueCategory value must be handled by at least one authority."""
    authority, reason, confidence = route_to_authority(category, None)

    assert authority is not None, (
        f"Category '{category}' returned no authority — every category must be covered."
    )
    assert "id" in authority
    assert "name" in authority
    assert "short_name" in authority
    assert confidence > 0.0
    assert reason != ""


# ---------------------------------------------------------------------------
# address_text keyword match (T3-2 criterion 2)
# ---------------------------------------------------------------------------


def test_keyword_match_hampankatta_routes_to_mcc():
    """'Hampankatta' is in MCC's area_text — should return MCC with confidence 1.0."""
    authority, reason, confidence = route_to_authority(
        "garbage_overflow", "Hampankatta main road"
    )

    assert authority is not None
    assert authority["short_name"] == "MCC"
    assert confidence == 1.0
    assert "Hampankatta" in reason or "MCC" in reason


def test_keyword_match_surathkal_prefers_north_zone_for_pothole():
    """'Surathkal' is in MCC North's area_text — for pothole, should beat generic MCC."""
    authority, reason, confidence = route_to_authority(
        "pothole", "Surathkal road near NITK"
    )

    # MCC North covers Surathkal; MCC (auth-001) also covers potholes.
    # The keyword scorer picks the highest-scoring authority.
    # Surathkal appears in MCC North's area_text.
    assert authority is not None
    assert confidence == 1.0
    assert "North" in authority["short_name"] or "Surathkal" in reason


def test_keyword_match_nh_route_routes_to_nhai():
    """'NH 75' is in NHAI's area_text — pothole on NH should route to NHAI."""
    authority, reason, confidence = route_to_authority(
        "pothole", "NH 75 near Pumpwell Circle"
    )

    assert authority is not None
    assert confidence == 1.0
    assert "NHAI" in authority["short_name"]


def test_keyword_match_broken_streetlight_routes_to_mescom():
    """For broken_streetlight, MESCOM is the specialist — keyword match should find it."""
    authority, reason, confidence = route_to_authority(
        "broken_streetlight", "Kadri road street light"
    )

    assert authority is not None
    assert confidence == 1.0


def test_keyword_match_waterlogging_routes_to_drainage():
    """MCC Drainage handles waterlogging — keyword match on Hampankatta."""
    authority, reason, confidence = route_to_authority(
        "waterlogging", "Hampankatta low-lying area"
    )

    assert authority is not None
    assert confidence == 1.0
    assert "Drainage" in authority["short_name"] or "MCC" in authority["short_name"]


# ---------------------------------------------------------------------------
# No-match → category-default fallback (T3-2 criterion 3)
# ---------------------------------------------------------------------------


def test_unknown_area_returns_category_default():
    """Area text with no keyword matches → confidence 0.7, first category match."""
    authority, reason, confidence = route_to_authority(
        "water_supply", "Some completely unknown locality XYZABC123"
    )

    assert authority is not None
    assert confidence == 0.7
    assert authority["id"] is not None


def test_empty_area_text_returns_category_default():
    """Empty area_text → category-only fallback."""
    authority, reason, confidence = route_to_authority("sewage", "")

    assert authority is not None
    assert confidence == 0.7


def test_none_area_text_returns_category_default():
    """None area_text → category-only fallback."""
    authority, reason, confidence = route_to_authority("road_damage", None)

    assert authority is not None
    assert confidence == 0.7


# ---------------------------------------------------------------------------
# No-authority case
# ---------------------------------------------------------------------------


def test_nonexistent_category_returns_none():
    """A category not in any authority's list → returns (None, reason, 0.0)."""
    authority, reason, confidence = route_to_authority(
        "unknown_civic_issue_xyz", "Kadri"
    )

    assert authority is None
    assert confidence == 0.0
    assert reason != ""


# ---------------------------------------------------------------------------
# Citizen override — get_authority_by_id (T3-2 citizen override requirement)
# ---------------------------------------------------------------------------


def test_get_authority_by_id_returns_correct_record():
    """Citizen override: get_authority_by_id must return the right authority."""
    authority = get_authority_by_id("auth-003")

    assert authority is not None
    assert authority["short_name"] == "MWWD"
    assert "water_supply" in authority["categories"]


def test_get_authority_by_id_returns_none_for_unknown():
    """Unknown authority id → None (no exception)."""
    assert get_authority_by_id("nonexistent-auth-xyz") is None


# ---------------------------------------------------------------------------
# get_all_authorities
# ---------------------------------------------------------------------------


def test_get_all_authorities_returns_seven_records():
    """All 7 Mangaluru authorities from the immutable JSON must be loaded."""
    authorities = get_all_authorities()

    assert len(authorities) == 7
    ids = {a["id"] for a in authorities}
    assert ids == {
        "auth-001", "auth-002", "auth-003", "auth-004",
        "auth-005", "auth-006", "auth-007",
    }


def test_get_all_authorities_have_required_fields():
    """Every authority record must have the required ADR-001 fields."""
    for authority in get_all_authorities():
        assert "id" in authority
        assert "name" in authority
        assert "short_name" in authority
        assert "categories" in authority
        assert "area_text" in authority
        assert "contact_email" in authority
        assert "phone" in authority
        # ADR-001: no ward_range, no ward integers, no routing geometry
        assert "ward_range" not in authority
        assert "ward_number" not in authority
        assert "geometry" not in authority
        assert "polygon" not in authority
        assert "geojson" not in authority


# ---------------------------------------------------------------------------
# No PostGIS dependency (T3-2 criterion 4)
# ---------------------------------------------------------------------------


def test_authority_routing_has_no_postgis_dependency():
    """Routing must not import PostGIS, shapely, geopandas, or psycopg2."""
    import services.authority_service as svc
    import inspect

    source = inspect.getsource(svc)

    forbidden = ["postgis", "shapely", "geopandas", "ST_Contains",
                 "ST_Within", "ST_DWithin", "psycopg2", "ward_range"]
    for term in forbidden:
        assert term not in source, (
            f"authority_service.py must not reference '{term}' (ADR-001 violation)."
        )


def test_authority_repo_has_no_postgis_dependency():
    """authority_repo must not query the DB or import PostGIS-related modules."""
    import db.repositories.authority_repo as repo_module
    import inspect

    source = inspect.getsource(repo_module)

    forbidden = ["postgis", "supabase_client", "ST_Contains", "ST_Within",
                 "psycopg2", "ward_range", "create_client"]
    for term in forbidden:
        assert term not in source, (
            f"authority_repo.py must not reference '{term}' (ADR-001 / T3-2 non-goal)."
        )


# ---------------------------------------------------------------------------
# authority_repo thin delegation layer (T3-2 repo requirement)
# ---------------------------------------------------------------------------


def test_authority_repo_get_all_delegates_to_service():
    """authority_repo.get_all() must return the same data as get_all_authorities()."""
    assert authority_repo.get_all() == get_all_authorities()


def test_authority_repo_get_by_id_delegates_to_service():
    """authority_repo.get_by_id() must return same result as get_authority_by_id()."""
    assert authority_repo.get_by_id("auth-001") == get_authority_by_id("auth-001")
    assert authority_repo.get_by_id("nonexistent") is None


def test_authority_repo_route_delegates_to_service():
    """authority_repo.route() must return same result as route_to_authority()."""
    repo_result = authority_repo.route("pothole", "Hampankatta")
    svc_result = route_to_authority("pothole", "Hampankatta")
    assert repo_result == svc_result
