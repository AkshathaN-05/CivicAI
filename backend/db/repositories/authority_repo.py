"""Authority repository — T3-2.

Reads authority data exclusively from the immutable JSON file
(backend/data/mangaluru_authorities.json) via the authority_service.

Per the T3-2 specification and ADR-001:
  - NEVER queries the Supabase ``authorities`` table for routing.
  - NEVER uses PostGIS, ward polygons, GeoJSON, or ward-range integers.
  - The Supabase ``authorities`` table exists for reference data only;
    application routing always uses the JSON source of truth.

This thin repository module exists as the data-access boundary required
by the plan's repository pattern (Part A §6).  It delegates entirely to
``services.authority_service`` which owns the JSON-loading and caching logic.
"""
from __future__ import annotations

from typing import Optional

from services.authority_service import (
    get_all_authorities,
    get_authority_by_id,
    route_to_authority,
)


def get_all() -> list[dict]:
    """Return all authority records from the immutable JSON.

    Returns:
        List of authority dicts with keys: id, name, short_name, categories,
        area_text, contact_email, phone.
    """
    return get_all_authorities()


def get_by_id(authority_id: str) -> Optional[dict]:
    """Return the authority dict for *authority_id*, or None if not found.

    Used for citizen override selection (Part A §12, step 6).

    Args:
        authority_id: The authority's string id (e.g. 'auth-001').

    Returns:
        Authority dict, or None if the id does not match any authority.
    """
    return get_authority_by_id(authority_id)


def route(
    category: str,
    area_text: Optional[str] = None,
) -> tuple[Optional[dict], str, float]:
    """Route a complaint to the best-matching authority.

    Delegates to ``authority_service.route_to_authority`` which implements
    the full ADR-001 algorithm:
      1. Filter by category
      2. Keyword-score area_text against authority area_text fields
      3. Return best match, or category-default fallback

    Args:
        category:  Issue category string (must match an IssueCategory value).
        area_text: Free-text location description from the report (optional).

    Returns:
        (authority_dict, match_reason, confidence)
        confidence == 1.0  → keyword match
        confidence == 0.7  → category-default fallback
        confidence == 0.0  → no authority found for this category
    """
    return route_to_authority(category, area_text)
