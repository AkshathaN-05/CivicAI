"""Groq API integration for CivicAI — T2-8.

Provides async functions that call Groq LLM models with structured prompts
and return validated outputs.

Public API:

    async def call_groq(prompt: str, *, api_key: str | None = None,
                        timeout: float = 30.0) -> LLMOutput

    async def civic_classify_image(
        image_bytes: bytes,
        address: str = "",
        *,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> CivicClassificationResult

Design decisions (LOCKED — Part A §9):
- Text model: ``openai/gpt-oss-20b`` on Groq API.
  (llama-3.1-8b-instant was removed from Groq on 2025-07-21 — returns HTTP 404;
   openai/gpt-oss-20b is the confirmed available lightweight replacement.)
- Vision model: ``qwen/qwen3.8-27b`` on Groq API.
- Output is expected as JSON embedded in the model's text response.
- Every response is validated with :func:`~llm.output_validator.validate_output`.
- Any error (network, timeout, bad JSON, schema violation) raises
  :class:`~llm.output_validator.LLMOutputInvalid` so callers can fall back
  to the deterministic template engine (T2-9).
- API key is read from the ``GROQ_API_KEY`` environment variable if not
  supplied explicitly.  It is NEVER logged or exposed to the frontend.
- A sane default timeout of 30 seconds is enforced.

Failure modes handled:
- :class:`groq.GroqError` (auth, rate-limit, server error)
- :class:`TimeoutError` / ``httpx.TimeoutException``
- JSON parse failure (model returned non-JSON text)
- Schema validation failure (:class:`LLMOutputInvalid` from output_validator)
- Empty / missing response content
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import groq

from llm.output_validator import LLMOutput, LLMOutputInvalid

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LOCKED: model identifiers (Part A §9)
# ---------------------------------------------------------------------------
# llama-3.1-8b-instant was removed from Groq (HTTP 404 as of 2025-07-21).
# openai/gpt-oss-20b is the confirmed available lightweight text replacement
# on this Groq account — verified callable, JSON-capable, and compatible with
# the existing COMPLAINT_DESCRIPTION_PROMPT / RTI_DRAFT_PROMPT / CATEGORY_CLASSIFICATION_PROMPT.
GROQ_MODEL: str = "openai/gpt-oss-20b"
# Vision model — supports image input via base64 URL.
# qwen/qwen3.8-27b is the current Groq-hosted vision model that accepts
# image_url content blocks.  meta-llama/llama-4-scout-17b-16e-instruct
# was decommissioned / unavailable on this account.
GROQ_VISION_MODEL: str = "qwen/qwen3.8-27b"

# ---------------------------------------------------------------------------
# Module-level Groq client singletons (keyed by api_key).
# Avoids recreating the HTTP connection pool on every request.
# ---------------------------------------------------------------------------
_groq_text_client: Optional[groq.AsyncGroq] = None
_groq_vision_client: Optional[groq.AsyncGroq] = None
_groq_client_key: Optional[str] = None  # tracks which key the singletons were built with


def _get_groq_client(api_key: str, timeout: float) -> groq.AsyncGroq:
    """Return a cached AsyncGroq client, recreating it only when the key changes."""
    global _groq_text_client, _groq_client_key
    if _groq_text_client is None or _groq_client_key != api_key:
        _groq_text_client = groq.AsyncGroq(api_key=api_key, timeout=timeout)
        _groq_client_key = api_key
    return _groq_text_client


def _get_groq_vision_client(api_key: str, timeout: float) -> groq.AsyncGroq:
    """Return a cached AsyncGroq vision client, recreating it only when the key changes."""
    global _groq_vision_client, _groq_client_key
    if _groq_vision_client is None or _groq_client_key != api_key:
        _groq_vision_client = groq.AsyncGroq(api_key=api_key, timeout=timeout)
        _groq_client_key = api_key
    return _groq_vision_client


def reset_groq_clients_for_testing() -> None:
    """Reset the Groq client singletons to None.

    Intended for use in tests only — ensures each test that patches
    ``groq.AsyncGroq`` gets a fresh client instance from the mock constructor
    rather than the cached instance from a prior test.
    """
    global _groq_text_client, _groq_vision_client, _groq_client_key
    _groq_text_client = None
    _groq_vision_client = None
    _groq_client_key = None

# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

# Matches a JSON object inside a markdown code fence (```json ... ``` or ``` ... ```)
_JSON_BLOCK_RE: re.Pattern[str] = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL
)

# Matches any {...} block — used as fallback after stripping think blocks
_JSON_BARE_RE: re.Pattern[str] = re.compile(r"\{.*?\}", re.DOTALL)

# Matches qwen/reasoning-model <think>...</think> blocks.
# These appear BEFORE the answer in models with Chain-of-Thought reasoning
# (e.g. qwen3.8-27b returns: <think>reasoning here</think>\n{"valid":...}).
# Stripping them before JSON extraction prevents accidentally extracting a
# JSON-like fragment from the thinking chain instead of the final answer.
_THINK_BLOCK_RE: re.Pattern[str] = re.compile(
    r"<think>.*?</think>", re.DOTALL | re.IGNORECASE
)

# Matches an UN-CLOSED <think> block — produced when max_tokens truncates the
# response mid-reasoning so the closing </think> tag is never emitted.
# Strips everything from <think> to end-of-string to prevent treating
# reasoning fragments as the final JSON answer.
_THINK_UNCLOSED_RE: re.Pattern[str] = re.compile(
    r"<think>.*$", re.DOTALL | re.IGNORECASE
)


def _extract_json(text: str) -> dict:
    """Extract the final JSON answer object from *text*.

    Handles four output shapes produced by Groq-hosted models:
    1. Bare JSON:  ``{"valid": true, "category": ...}``
    2. Fenced JSON: ````json\\n{"valid": ...}\\n````
    3. Think+JSON (qwen reasoning models, normal):
       ``<think>...reasoning...</think>\\n{"valid": ...}``
    4. Truncated think block (qwen, max_tokens cut off before </think>):
       ``<think>...truncated reasoning...``  — no closing tag, no JSON after.
       After stripping the unclosed block, falls through to bare extraction
       on whatever text preceded the <think> open tag (typically empty for
       pure reasoning models, raising LLMOutputInvalid as expected).

    Strategy:
    - Strip any closed ``<think>...</think>`` blocks first to avoid extracting
      a JSON-like fragment from the model's reasoning chain.
    - Strip any remaining unclosed ``<think>...`` block (truncated output).
    - Try a fenced code block next.
    - Fall back to the LAST valid ``{...}`` block in the remaining text.
      Using the *last* match is important: the reasoning model's preamble
      may contain partial JSON examples, while the final answer JSON is
      always at the end of the response.

    Args:
        text: Raw string from the LLM completion.

    Returns:
        Parsed Python dict.

    Raises:
        :class:`~llm.output_validator.LLMOutputInvalid`: If no valid JSON
            object is found or JSON parsing fails.
    """
    # Step 1a: strip closed <think>...</think> blocks
    clean_text = _THINK_BLOCK_RE.sub("", text).strip()
    # Step 1b: strip any remaining unclosed <think>... block (truncated output)
    clean_text = _THINK_UNCLOSED_RE.sub("", clean_text).strip()

    # Step 2: try fenced block first (``` json ... ```)
    match = _JSON_BLOCK_RE.search(clean_text)
    if match:
        raw_json = match.group(1)
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            pass  # fall through to bare extraction

    # Step 3: collect ALL bare {...} blocks and try from LAST to FIRST.
    # The final answer is always last; earlier blocks may be reasoning fragments.
    all_matches = list(_JSON_BARE_RE.finditer(clean_text))
    if not all_matches:
        raise LLMOutputInvalid(
            f"No JSON object found in LLM response: {text[:300]!r}"
        )

    last_exc: Exception = LLMOutputInvalid("No valid JSON found")
    for m in reversed(all_matches):
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue

    raise LLMOutputInvalid(
        f"Failed to parse JSON from LLM response: {last_exc}"
    )


# ---------------------------------------------------------------------------
# CivicClassificationResult — result of vision-based civic image classification
# ---------------------------------------------------------------------------

@dataclass
class CivicClassificationResult:
    """Result of vision-based civic image classification.

    Attributes:
        valid:               True when the image shows a genuine civic issue.
        category:            Civic category string (e.g. 'pothole', 'sewage',
                             'invalid'). Uses the vision-model vocabulary which
                             is then mapped to IssueCategory by the caller.
        category_confidence: Model confidence in the category (0.0–1.0).
        severity:            'low', 'medium', 'high', or None.
        severity_score:      Numeric severity in [0.0, 1.0].
        description:         Specific, evidence-based description of what is
                             visible in the image.
        reason:              Brief reason for the validity decision.
        primary_issue:       Short factual description of the actual civic
                             problem visible (e.g. "large garbage pile on
                             roadside").  Used for internal evidence validation
                             to catch category/description mismatches.
    """
    valid: bool
    category: str
    category_confidence: float
    severity: Optional[str]
    severity_score: float
    description: str
    reason: str
    primary_issue: str = ""


# ---------------------------------------------------------------------------
# Canonical civic category set expected in the vision response.
# The vision model may return synonyms or slight variations; these are
# normalised to canonical keys before being returned to the caller.
#
# ---------------------------------------------------------------------------
# Canonical categories accepted from the vision model.
#
# The new prompt returns DB enum values directly:
#   pothole, road_damage, broken_streetlight, garbage_overflow,
#   open_drain, illegal_construction, waterlogging, water_supply, sewage, other
#
# Internal-only bucket (resolved to DB value via reason):
#   water_sewage → water_supply | sewage | waterlogging
#
# Legacy/synonym keys (kept for backward compat with old responses):
#   streetlight, garbage, electrical, drainage, water_leakage, etc.
# ---------------------------------------------------------------------------
_CANONICAL_CATEGORIES: frozenset[str] = frozenset({
    # DB enum values returned directly by the new prompt
    "pothole",
    "road_damage",
    "broken_streetlight",    # DB enum value — used directly in new prompt
    "garbage_overflow",      # DB enum value — used directly in new prompt
    "open_drain",            # DB enum value — used directly in new prompt
    "illegal_construction",  # DB enum value — used directly in new prompt
    "waterlogging",          # DB enum value — used directly in new prompt
    "water_supply",          # DB enum value — used directly in new prompt
    "sewage",                # DB enum value — used directly in new prompt
    "other",
    "invalid",
    # Internal water_sewage bucket (resolved via reason subtype)
    "water_sewage",
    # Legacy/synonym keys (old prompt format — kept for backward compat)
    "streetlight",           # legacy → broken_streetlight
    "garbage",               # legacy → garbage_overflow
    "electrical",            # legacy → broken_streetlight
    "drainage",              # legacy → open_drain
    "water_leakage",         # legacy → water_supply
    "broken_road_marking",   # legacy → road_damage
    "other_civic",           # legacy alias → other
})

# Synonym → canonical category mapping.
# Normalises free-form model outputs to canonical keys.
_CATEGORY_SYNONYMS: dict[str, str] = {
    # pothole synonyms
    "pot hole": "pothole",
    "pot_hole": "pothole",
    "road hole": "pothole",
    "road pit": "pothole",
    "crater": "pothole",
    "road crater": "pothole",
    # road_damage synonyms
    "cracked road": "road_damage",
    "road crack": "road_damage",
    "road cracks": "road_damage",
    "road surface damage": "road_damage",
    "damaged road": "road_damage",
    "broken road": "road_damage",
    "broken road surface": "road_damage",
    "road deterioration": "road_damage",
    "deteriorated road": "road_damage",
    "damaged pavement": "road_damage",
    "cracked pavement": "road_damage",
    # road marking synonyms → road_damage (broken_road_marking legacy → road_damage)
    "road marking":        "road_damage",
    "broken road marking": "road_damage",
    "faded road marking":  "road_damage",
    "missing road marking":"road_damage",
    "road_marking":        "road_damage",
    "faded marking":       "road_damage",
    "lane marking":        "road_damage",
    "missing lane marking":"road_damage",
    "damaged road marking":"road_damage",
    # open_drain synonyms — map directly to the DB enum value
    "drain":           "open_drain",
    "open drain":      "open_drain",
    "blocked drain":   "open_drain",
    "broken drain":    "open_drain",
    "damaged drain":   "open_drain",
    "stormwater":      "open_drain",
    "stormwater drain":"open_drain",
    "culvert":         "open_drain",
    "open_drain":      "open_drain",
    "gutter":          "open_drain",
    # water_sewage synonyms — covers all water-related terms
    "water sewage": "water_sewage",
    "water/sewage": "water_sewage",
    "water issue": "water_sewage",
    "water problem": "water_sewage",
    # sewage synonyms (legacy — also map to water_sewage in new scheme)
    "sewer": "sewage",
    "sewage overflow": "sewage",
    "sewer overflow": "sewage",
    "sewage leak": "sewage",
    "wastewater": "sewage",
    "manhole overflow": "sewage",
    # waterlogging synonyms (legacy)
    "flooding": "waterlogging",
    "flood": "waterlogging",
    "standing water": "waterlogging",
    "stagnant water": "waterlogging",
    "stagnant rainwater": "waterlogging",
    "water logging": "waterlogging",
    "waterlogged": "waterlogging",
    "flooded road": "waterlogging",
    "flooded street": "waterlogging",
    # water_supply synonyms (legacy water_leakage forms → now map to water_supply directly)
    "water pipe leak": "water_supply",
    "water leakage":   "water_supply",
    "leaking pipe":    "water_supply",
    "pipe leak":       "water_supply",
    "pipe burst":      "water_supply",
    "burst pipe":      "water_supply",
    "pipe leakage":    "water_supply",
    "water pipe":      "water_supply",
    "water leak":      "water_supply",
    "water supply":    "water_supply",
    "water_supply":    "water_supply",
    # garbage_overflow synonyms — all map directly to "garbage_overflow"
    "trash":                 "garbage_overflow",
    "waste":                 "garbage_overflow",
    "rubbish":               "garbage_overflow",
    "litter":                "garbage_overflow",
    "dumped waste":          "garbage_overflow",
    "garbage overflow":      "garbage_overflow",
    "garbage_overflow":      "garbage_overflow",
    "waste accumulation":    "garbage_overflow",
    "overflowing bin":       "garbage_overflow",
    "solid waste":           "garbage_overflow",
    "garbage dump":          "garbage_overflow",
    "waste pile":            "garbage_overflow",
    "dumped garbage":        "garbage_overflow",
    "waste dump":            "garbage_overflow",
    "illegal dumping":       "garbage_overflow",
    "roadside garbage":      "garbage_overflow",
    "roadside waste":        "garbage_overflow",
    "municipal solid waste": "garbage_overflow",
    # broken_streetlight synonyms (legacy "streetlight" + free-text variants)
    "streetlight":                  "broken_streetlight",
    "street light":                 "broken_streetlight",
    "lamp post":                    "broken_streetlight",
    "street lamp":                  "broken_streetlight",
    "broken lamp":                  "broken_streetlight",
    "damaged street lamp":          "broken_streetlight",
    "broken streetlight":           "broken_streetlight",
    "broken_streetlight":           "broken_streetlight",
    "non-functional streetlight":   "broken_streetlight",
    "non functional streetlight":   "broken_streetlight",
    "nonfunctional street light":   "broken_streetlight",
    "damaged lamp":                 "broken_streetlight",
    # electrical → broken_streetlight
    "electric pole":                       "broken_streetlight",
    "electric wire":                       "broken_streetlight",
    "exposed wire":                        "broken_streetlight",
    "exposed electrical wire":             "broken_streetlight",
    "fallen wire":                         "broken_streetlight",
    "electrical hazard":                   "broken_streetlight",
    "electrical damage":                   "broken_streetlight",
    "electric pole damage":                "broken_streetlight",
    "damaged electrical pole":             "broken_streetlight",
    "damaged electrical infrastructure":   "broken_streetlight",
    "electrical":                          "broken_streetlight",
    # open_drain synonyms (legacy "drainage")
    "drainage":         "open_drain",
    "drain":            "open_drain",
    "open drain":       "open_drain",
    "blocked drain":    "open_drain",
    "broken drain":     "open_drain",
    "damaged drain":    "open_drain",
    "stormwater":       "open_drain",
    "stormwater drain": "open_drain",
    "culvert":          "open_drain",
    "open_drain":       "open_drain",
    "gutter":           "open_drain",
    # other/other_civic synonyms — map both to canonical "other"
    "other civic": "other",
    "other_civic": "other",
    "civic_other": "other",
}


def _normalise_category(raw_cat: str) -> str:
    """Normalise a raw category string from the vision model to a canonical key.

    Resolution order:
    1. Strip whitespace and lower-case.
    2. If the result is already in _CANONICAL_CATEGORIES, return it (with
       legacy alias remapping for "other_civic").
    3. Otherwise look up the synonym table for free-text variants.
    4. If still unknown, return 'other' rather than falling through to an
       error — unknown-but-clearly-civic outputs should not become 'invalid'.

    The new prompt returns DB enum values directly (e.g. "broken_streetlight",
    "garbage_overflow") so those pass through step 2 unchanged.  Legacy short
    forms ("streetlight", "garbage", "electrical") are remapped in the synonym
    table to their full DB enum names.

    Args:
        raw_cat: Raw category string from the vision model.

    Returns:
        A canonical category key from :data:`_CANONICAL_CATEGORIES`.
    """
    key = raw_cat.strip().lower()
    if key in _CANONICAL_CATEGORIES:
        # Normalise legacy aliases to their canonical form
        _LEGACY_REMAP = {
            "other_civic": "other",
            "streetlight":  "broken_streetlight",
            "garbage":      "garbage_overflow",
            "electrical":   "broken_streetlight",
            "drainage":     "open_drain",
            "water_leakage": "water_supply",
            "broken_road_marking": "road_damage",
        }
        return _LEGACY_REMAP.get(key, key)
    synonym_hit = _CATEGORY_SYNONYMS.get(key)
    if synonym_hit:
        logger.debug(
            "groq_provider: normalised category %r → %r via synonym table",
            raw_cat, synonym_hit,
        )
        return synonym_hit
    # Unknown output — log and fall back to "other" to avoid losing valid images
    logger.warning(
        "groq_provider: unknown category %r from vision model — normalising to 'other'",
        raw_cat,
    )
    return "other"


def _parse_civic_classification(raw: dict) -> CivicClassificationResult:
    """Parse and validate a raw dict into a CivicClassificationResult.

    Handles two JSON output formats from the vision model:
    - NEW format (current prompt): ``confidence`` (float) + ``severity`` (float)
    - OLD format (legacy prompt):  ``category_confidence`` (float) + ``severity``
      (string) + ``severity_score`` (float)

    Both formats are normalised to the same ``CivicClassificationResult`` fields:
    - ``category_confidence``: float confidence [0.0, 1.0]
    - ``severity``: string 'low'/'medium'/'high'/None
    - ``severity_score``: float [0.0, 1.0]

    The category string is normalised via :func:`_normalise_category` before
    returning so the caller always receives a canonical category key.

    Raises LLMOutputInvalid on missing / invalid fields.
    """
    try:
        valid = bool(raw.get("valid", False))
        raw_category = str(raw.get("category", "invalid")).strip().lower()
        category = _normalise_category(raw_category)
        # If category is 'invalid', force valid=False regardless of what the model said
        if category == "invalid":
            valid = False

        # --- confidence ---
        # New prompt: "confidence"; legacy: "category_confidence"
        raw_conf = raw.get("confidence", raw.get("category_confidence", 0.0))
        cat_conf = float(raw_conf) if raw_conf is not None else 0.0
        cat_conf = max(0.0, min(1.0, cat_conf))

        # --- severity ---
        # New prompt: "severity" is a float (0.0 / 0.5 / 0.85)
        # Legacy:     "severity" is a string ('low'/'medium'/'high') +
        #             "severity_score" is a float
        severity_raw = raw.get("severity")
        sev_score_raw = raw.get("severity_score")

        if isinstance(severity_raw, (int, float)):
            # New format: severity is numeric
            sev_score = float(severity_raw)
            sev_score = max(0.0, min(1.0, sev_score))
            # Derive string severity from numeric value
            if sev_score >= 0.75:
                severity: Optional[str] = "high"
            elif sev_score >= 0.35:
                severity = "medium"
            else:
                severity = "low"
        else:
            # Legacy format: severity is a string, severity_score is separate
            if severity_raw and str(severity_raw).lower() != "null":
                sev_str = str(severity_raw).lower()
                if sev_str in ("low", "medium", "high"):
                    severity = sev_str
                else:
                    severity = None
            else:
                severity = None
            sev_score = float(sev_score_raw) if sev_score_raw is not None else 0.0
            sev_score = max(0.0, min(1.0, sev_score))
            # If still no severity string, derive from sev_score
            if severity is None and sev_score > 0:
                if sev_score >= 0.75:
                    severity = "high"
                elif sev_score >= 0.35:
                    severity = "medium"
                else:
                    severity = "low"

        description = str(raw.get("description", ""))[:500]
        reason = str(raw.get("reason", ""))[:200]
        primary_issue = str(raw.get("primary_issue", ""))[:300]
    except (TypeError, ValueError) as exc:
        raise LLMOutputInvalid(
            f"CivicClassificationResult parse error: {exc}"
        ) from exc

    # ------------------------------------------------------------------
    # Evidence mismatch guard: if the model's own primary_issue text
    # strongly implies a different category than what it returned, correct
    # the classification.
    #
    # Two modes:
    #   1. road_damage mismatch: model said road_damage but primary_issue
    #      describes garbage/water/drain/streetlight/construction → override.
    #   2. other rescue: model returned 'other' but primary_issue clearly
    #      describes a specific civic category → upgrade to that category.
    #
    # Only fires when primary_issue is non-empty (new schema).
    # 'invalid' is never touched — it is always authoritative.
    # ------------------------------------------------------------------
    if primary_issue and category != "invalid":
        pi_lower = primary_issue.lower()

        # Keywords that indicate a road-damage override is wrong
        _GARBAGE_WORDS = (
            "garbage", "waste", "litter", "trash", "rubbish", "dump",
            "bin", "debris", "solid waste", "refuse",
        )
        _WATER_WORDS = (
            "water", "flood", "waterlog", "sewage", "drain overflow",
            "stagnant", "standing water", "leaking pipe", "burst pipe",
            "wastewater", "effluent",
        )
        _DRAIN_WORDS = (
            "open drain", "uncovered drain", "drain channel", "gutter",
            "storm drain", "missing cover", "drain cover",
        )
        _STREETLIGHT_WORDS = (
            "streetlight", "street light", "lamp post", "lamp", "light pole",
            "broken light", "fallen pole",
        )
        _CONSTRUCTION_WORDS = (
            "construction", "encroachment", "encroaching", "unauthorized",
            "illegal structure", "building site",
        )

        def _matches_any(text: str, words: tuple) -> bool:
            return any(w in text for w in words)

        # If model said road_damage but primary_issue sounds like something else
        if category == "road_damage":
            if _matches_any(pi_lower, _GARBAGE_WORDS):
                logger.info(
                    "_parse_civic_classification: evidence mismatch — "
                    "category=road_damage but primary_issue='%s' → overriding to garbage_overflow",
                    primary_issue[:100],
                )
                category = "garbage_overflow"
            elif _matches_any(pi_lower, _DRAIN_WORDS):
                logger.info(
                    "_parse_civic_classification: evidence mismatch — "
                    "category=road_damage but primary_issue='%s' → overriding to open_drain",
                    primary_issue[:100],
                )
                category = "open_drain"
            elif _matches_any(pi_lower, _STREETLIGHT_WORDS):
                logger.info(
                    "_parse_civic_classification: evidence mismatch — "
                    "category=road_damage but primary_issue='%s' → overriding to broken_streetlight",
                    primary_issue[:100],
                )
                category = "broken_streetlight"
            elif _matches_any(pi_lower, _CONSTRUCTION_WORDS):
                logger.info(
                    "_parse_civic_classification: evidence mismatch — "
                    "category=road_damage but primary_issue='%s' → overriding to illegal_construction",
                    primary_issue[:100],
                )
                category = "illegal_construction"
            elif _matches_any(pi_lower, _WATER_WORDS):
                logger.info(
                    "_parse_civic_classification: evidence mismatch — "
                    "category=road_damage but primary_issue='%s' → overriding to water_sewage",
                    primary_issue[:100],
                )
                category = "water_sewage"

        # If model said "other" but primary_issue strongly implies a specific category
        elif category == "other":
            if _matches_any(pi_lower, _GARBAGE_WORDS):
                logger.info(
                    "_parse_civic_classification: evidence rescue — "
                    "category=other but primary_issue='%s' → upgrading to garbage_overflow",
                    primary_issue[:100],
                )
                category = "garbage_overflow"
            elif _matches_any(pi_lower, _DRAIN_WORDS):
                logger.info(
                    "_parse_civic_classification: evidence rescue — "
                    "category=other but primary_issue='%s' → upgrading to open_drain",
                    primary_issue[:100],
                )
                category = "open_drain"
            elif _matches_any(pi_lower, _STREETLIGHT_WORDS):
                logger.info(
                    "_parse_civic_classification: evidence rescue — "
                    "category=other but primary_issue='%s' → upgrading to broken_streetlight",
                    primary_issue[:100],
                )
                category = "broken_streetlight"
            elif _matches_any(pi_lower, _WATER_WORDS):
                logger.info(
                    "_parse_civic_classification: evidence rescue — "
                    "category=other but primary_issue='%s' → upgrading to water_sewage",
                    primary_issue[:100],
                )
                category = "water_sewage"

    return CivicClassificationResult(
        valid=valid,
        category=category,
        category_confidence=cat_conf,
        severity=severity,
        severity_score=sev_score,
        description=description,
        reason=reason,
        primary_issue=primary_issue,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def call_groq(
    prompt: str,
    *,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> LLMOutput:
    """Call the Groq API with *prompt* and return a validated :class:`LLMOutput`.

    The prompt must already have citizen text sanitized via
    :func:`~llm.prompts.sanitize_for_prompt` before being passed here.

    Args:
        prompt:  A fully rendered prompt string.  Must not contain
                 unsanitized citizen-supplied text.
        api_key: Groq API key.  Defaults to the ``GROQ_API_KEY`` environment
                 variable.  Never log or expose this value.
        timeout: Maximum seconds to wait for the Groq API response.
                 Defaults to 30 seconds.

    Returns:
        A validated :class:`~llm.output_validator.LLMOutput` instance.

    Raises:
        :class:`~llm.output_validator.LLMOutputInvalid`: On any failure
            (network, auth, timeout, bad JSON, schema violation, empty
            response).  Callers MUST catch this and activate the
            deterministic fallback (T2-9).
    """
    resolved_key: str | None = api_key or os.environ.get("GROQ_API_KEY")
    if not resolved_key:
        raise LLMOutputInvalid(
            "GROQ_API_KEY is not set — cannot call Groq API."
        )

    try:
        client = _get_groq_client(resolved_key, timeout)
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a civic complaint assistant for Mangaluru, India. "
                        "Always respond with valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,  # low temperature for deterministic, factual output
            max_tokens=512,
        )
    except groq.GroqError as exc:
        logger.warning("Groq API error: %s", exc)
        raise LLMOutputInvalid(f"Groq API error: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — network, timeout, etc.
        logger.warning("Groq call failed with unexpected error: %s", exc)
        raise LLMOutputInvalid(f"Groq call failed: {exc}") from exc

    # Extract text content from the response
    try:
        content: str = response.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise LLMOutputInvalid(
            f"Unexpected Groq response structure: {exc}"
        ) from exc

    if not content.strip():
        raise LLMOutputInvalid("Groq returned an empty response.")

    logger.debug("Groq raw response (%d chars): %.200s", len(content), content)

    # Parse JSON and validate against LLMOutput schema
    raw_dict = _extract_json(content)
    return validate_output(raw_dict)


async def civic_classify_image(
    image_bytes: bytes,
    address: str = "",
    *,
    road_model_hint: str = "",
    api_key: str | None = None,
    timeout: float = 30.0,
) -> CivicClassificationResult:
    """Classify a civic image using Groq's vision model.

    Groq Vision is ALWAYS the final semantic authority.  The road model hint
    (if provided) is passed into the prompt as supporting evidence but does NOT
    override the model's own visual assessment.

    Args:
        image_bytes:      JPEG bytes of the redacted image.
        address:          Human-readable address/location string (may be empty).
        road_model_hint:  Optional hint from the local road-damage specialist
                          model, e.g. "specialist road model detected: pothole
                          (conf=0.82, raw class D40)".  Empty string if road
                          model was not run or was not confident.
        api_key:          Groq API key. Defaults to GROQ_API_KEY env var.
        timeout:          Maximum seconds to wait for the Groq API response.

    Returns:
        :class:`CivicClassificationResult` with classification details.

    Raises:
        :class:`~llm.output_validator.LLMOutputInvalid`: On any failure
            (network, auth, timeout, bad JSON).  Callers MUST catch this
            and activate the deterministic fallback.
    """
    from llm.prompts import CIVIC_IMAGE_CLASSIFICATION_PROMPT, sanitize_for_prompt

    resolved_key: str | None = api_key or os.environ.get("GROQ_API_KEY")
    if not resolved_key:
        raise LLMOutputInvalid(
            "GROQ_API_KEY is not set — cannot call Groq vision API."
        )

    safe_address = sanitize_for_prompt(address or "")
    safe_hint = sanitize_for_prompt(road_model_hint or "")

    # Resize the already-redacted image for Groq Vision upload.
    # 1024px gives the model enough resolution to distinguish garbage/water/drain
    # details from road-surface context.  Privacy redaction and road-model inference
    # always use the full-resolution bytes; only this Groq Vision upload path uses
    # the downsized copy.
    _GROQ_VISION_MAX_PX: int = 1024
    try:
        import io as _io
        from PIL import Image as _Image
        _pil = _Image.open(_io.BytesIO(image_bytes)).convert("RGB")
        _w, _h = _pil.size
        if max(_w, _h) > _GROQ_VISION_MAX_PX:
            _scale = _GROQ_VISION_MAX_PX / max(_w, _h)
            _new_w = max(1, int(_w * _scale))
            _new_h = max(1, int(_h * _scale))
            _pil = _pil.resize((_new_w, _new_h), _Image.LANCZOS)
            _buf = _io.BytesIO()
            _pil.save(_buf, format="JPEG", quality=82)
            upload_bytes = _buf.getvalue()
            logger.debug(
                "groq_provider: resized image for Groq Vision %dx%d → %dx%d (%d bytes)",
                _w, _h, _new_w, _new_h, len(upload_bytes),
            )
        else:
            upload_bytes = image_bytes
        del _pil
    except Exception as _resize_exc:
        logger.warning(
            "groq_provider: image resize for Groq Vision failed — using original bytes: %s",
            _resize_exc,
        )
        upload_bytes = image_bytes

    # Encode image as base64 data URL
    b64_image = base64.b64encode(upload_bytes).decode("utf-8")
    image_url = f"data:image/jpeg;base64,{b64_image}"

    prompt_text = CIVIC_IMAGE_CLASSIFICATION_PROMPT.format(
        address=safe_address,
        road_model_hint=safe_hint if safe_hint else "none",
    )

    # Strict JSON Schema for structured output.
    # Every property must appear in "required" and additionalProperties=False
    # for Groq strict=True mode (confirmed working in live API test).
    _VISION_RESPONSE_SCHEMA = {
        "type": "json_schema",
        "json_schema": {
            "name": "civic_classification",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "valid":          {"type": "boolean"},
                    "category":       {"type": "string"},
                    "confidence":     {"type": "number"},
                    "severity":       {"type": "number"},
                    "primary_issue":  {"type": "string"},
                    "description":    {"type": "string"},
                    "reason":         {"type": "string"},
                },
                "required": [
                    "valid",
                    "category",
                    "confidence",
                    "severity",
                    "primary_issue",
                    "description",
                    "reason",
                ],
                "additionalProperties": False,
            },
        },
    }

    try:
        client = _get_groq_vision_client(resolved_key, timeout)
        response = await client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt_text,
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                }
            ],
            temperature=0.1,       # low temperature for deterministic classification
            max_tokens=2048,       # budget for reasoning chain + final JSON answer
            reasoning_format="hidden",   # suppress <think> tokens in message.content
            reasoning_effort="high",     # maximise reasoning depth for accuracy
            response_format=_VISION_RESPONSE_SCHEMA,  # enforce strict JSON schema
        )
    except groq.GroqError as exc:
        logger.warning("Groq vision API error: %s", exc)
        raise LLMOutputInvalid(f"Groq vision API error: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("Groq vision call failed: %s", exc)
        raise LLMOutputInvalid(f"Groq vision call failed: {exc}") from exc

    try:
        msg = response.choices[0].message
        content: str = msg.content or ""
        # qwen3.8-27b (and other reasoning models) may route chain-of-thought
        # output to a separate 'thinking' or 'reasoning_content' field on the
        # message object when the Groq API is configured with a thinking budget.
        # In that case message.content can be empty while the actual answer
        # (or the full think+answer text) lives in the auxiliary field.
        # We check both known field names defensively without assuming either
        # exists on the SDK response object.
        if not content.strip():
            for _thinking_attr in ("thinking", "reasoning_content"):
                _thinking_val = getattr(msg, _thinking_attr, None)
                if _thinking_val and isinstance(_thinking_val, str) and _thinking_val.strip():
                    content = _thinking_val
                    logger.debug(
                        "groq_provider: content was empty; using message.%s "
                        "(%d chars) for JSON extraction",
                        _thinking_attr,
                        len(content),
                    )
                    break
    except (AttributeError, IndexError) as exc:
        raise LLMOutputInvalid(
            f"Unexpected Groq vision response structure: {exc}"
        ) from exc

    if not content.strip():
        raise LLMOutputInvalid("Groq vision returned an empty response.")

    logger.debug(
        "Groq vision raw response (%d chars): %.300s", len(content), content
    )

    raw_dict = _extract_json(content)
    return _parse_civic_classification(raw_dict)


# ---------------------------------------------------------------------------
# Import helper so callers can use a single import
# ---------------------------------------------------------------------------
from llm.output_validator import validate_output  # noqa: E402 — intentional re-export
