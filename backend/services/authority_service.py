"""Authority routing service — ADR-001 (LOCKED).

Routing logic:
  1. Filter authorities whose `categories` array includes the issue category.
  2. If area_text provided: substring-match (case-insensitive) against each
     authority's area_text field.  Return best match.
  3. Fallback: first category-matching authority.

Forbidden: ward numbers, ward ranges, GeoJSON, PostGIS polygon containment.
Source: backend/data/mangaluru_authorities.json — IMMUTABLE, loaded once.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

DATA_FILE = Path(__file__).parent.parent / "data" / "mangaluru_authorities.json"


@lru_cache(maxsize=1)
def _load_authorities() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)["authorities"]


def _keyword_score(area_text: str, authority_area: str) -> int:
    """Count how many words from area_text appear in authority_area."""
    words = re.findall(r"\w+", area_text.lower())
    target = authority_area.lower()
    return sum(1 for w in words if w in target)


def route_to_authority(
    category: str,
    area_text: Optional[str] = None,
) -> tuple[Optional[dict], str, float]:
    """Return (authority_dict, match_reason, confidence).

    Confidence values:
      1.0 — keyword match in area_text
      0.7 — category-only fallback
      0.0 — no matching authority
    """
    authorities = _load_authorities()

    # Step 1: filter by category
    category_matches = [a for a in authorities if category in a["categories"]]
    if not category_matches:
        return None, "No authority found for this category.", 0.0

    # Step 2: keyword match on area_text
    if area_text and area_text.strip():
        scored = [
            (a, _keyword_score(area_text, a["area_text"]))
            for a in category_matches
        ]
        best_authority, best_score = max(scored, key=lambda x: x[1])
        if best_score > 0:
            reason = (
                f"Area keyword match: '{area_text}' matched "
                f"{best_authority['short_name']} jurisdiction."
            )
            return best_authority, reason, 1.0

    # Step 3: category fallback
    fallback = category_matches[0]
    reason = (
        f"Category default: {fallback['short_name']} handles "
        f"'{category}' issues in Mangaluru."
    )
    return fallback, reason, 0.7


def get_all_authorities() -> list[dict]:
    return _load_authorities()


def get_authority_by_id(authority_id: str) -> Optional[dict]:
    return next(
        (a for a in _load_authorities() if a["id"] == authority_id),
        None,
    )
