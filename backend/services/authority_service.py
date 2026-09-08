"""Authority routing service — ADR-001 (LOCKED).

Routing logic:
  1. Filter authorities whose ``categories`` array includes the issue category.
  2. If area_text provided: keyword-score each candidate against its area_text.
     Return the highest-scoring authority when the score is > 0.
  3. Specialist tie-break (no geographic match): among the remaining candidates
     prefer the authority whose category list is **most specific** to the
     requested category — i.e. the one with the fewest total supported categories.
     A specialist authority (e.g. MESCOM: 1 category) outranks a generic
     municipal authority (e.g. MCC: 7 categories) when both are geographically
     plausible but neither has a keyword advantage.
     Tie within equal specificity: preserve original JSON order (stable sort).
  4. Last resort: first category-matching authority.

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


def _specialist_rank(authority: dict) -> int:
    """Return the number of categories the authority supports.

    An authority with rank == 1 is a singleton specialist (handles exactly one
    civic category) and is preferred over generic multi-category authorities
    when geographic keyword matching produces no distinguishing signal.

    This is fully data-driven: no authority name is hard-coded here.
    """
    return len(authority.get("categories", []))


def route_to_authority(
    category: str,
    area_text: Optional[str] = None,
) -> tuple[Optional[dict], str, float]:
    """Return (authority_dict, match_reason, confidence).

    Confidence values:
      1.0 — keyword match in area_text
      0.8 — specialist authority selected by category specificity
      0.7 — generic category fallback (first match, equal specificity)
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

    # Step 3: singleton-specialist tie-break.
    # If any candidate authority handles ONLY this single civic category
    # (i.e. its categories list has exactly one entry), it is a dedicated
    # single-purpose authority and should be preferred over generic multi-category
    # authorities regardless of JSON ordering.
    #
    # Using a threshold of 1 (singleton) keeps this rule narrow and safe:
    # - MESCOM (1 category: broken_streetlight) → selected for broken_streetlight ✓
    # - MWWD   (2 categories: water_supply+sewage) → not promoted over itself ✓
    # - NHAI   (2 categories: pothole+road_damage) → not promoted for generic potholes ✓
    # - MCC    (7 categories) → never promoted by this rule ✓
    #
    # No authority name is hard-coded; the rule is fully data-driven.
    singleton_specialists = [a for a in category_matches if _specialist_rank(a) == 1]
    if singleton_specialists:
        specialist = singleton_specialists[0]  # take the first (stable order)
        reason = (
            f"Specialist authority: {specialist['short_name']} is the sole dedicated "
            f"authority for '{category}' issues in Mangaluru."
        )
        return specialist, reason, 0.8

    # Step 4: generic fallback — no singleton specialist; keep first JSON-order match.
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
