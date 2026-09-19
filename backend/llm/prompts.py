"""Prompt templates and prompt injection protection — T2-8.

Four prompt templates are provided:

    COMPLAINT_DESCRIPTION_PROMPT      — generate a civic complaint description
    RTI_DRAFT_PROMPT                   — draft an RTI letter
    CATEGORY_CLASSIFICATION_PROMPT    — classify an ambiguous civic category (text-only)
    CIVIC_IMAGE_CLASSIFICATION_PROMPT — classify a civic image using vision model

Public API:

    sanitize_for_prompt(text: str) -> str
        Strips prompt-injection patterns and enforces a hard length cap.

LOCKED decisions (Part A §9):
- All citizen-supplied text must be sanitized before injection.
- Hard length limit: 2 000 characters per field.
- Injection patterns defined in architecture Part B §LLM Prompt Construction.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Injection patterns (architecture Part B §LLM Prompt Construction)
# ---------------------------------------------------------------------------

INJECTION_PATTERNS: list[str] = [
    r"ignore previous instructions",
    r"system prompt",
    r"\bforget\b.{0,20}\binstructions\b",
    r"<\|.*?\|>",  # special tokens (e.g. <|endoftext|>)
]

_COMPILED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.DOTALL) for p in INJECTION_PATTERNS
]

_MAX_PROMPT_INPUT_LENGTH: int = 2_000  # hard cap per field (architecture §13)


def sanitize_for_prompt(text: str) -> str:
    """Sanitize citizen-supplied text before injecting it into an LLM prompt.

    1. Replace each injection pattern with the literal token ``[removed]``.
    2. Truncate to :data:`_MAX_PROMPT_INPUT_LENGTH` characters.

    Args:
        text: Raw citizen-supplied string (description, area_text, etc.).

    Returns:
        Sanitized string safe to embed in a prompt.
    """
    for pattern in _COMPILED_PATTERNS:
        text = pattern.sub("[removed]", text)
    return text[:_MAX_PROMPT_INPUT_LENGTH]


# ---------------------------------------------------------------------------
# Prompt templates — architecture Part B §LLM Prompt Construction
# ---------------------------------------------------------------------------

COMPLAINT_DESCRIPTION_PROMPT: str = (
    "You are a civic complaint assistant for Mangaluru, India.\n"
    "Given the following information, generate a clear complaint description.\n"
    "\n"
    "Category: {category}\n"
    "Location: {address}\n"
    "Evidence confidence: {confidence:.0%}\n"
    "Detected objects: {detected_objects}\n"
    "\n"
    "Generate a complaint description in 2-3 sentences.\n"
    "Do not invent information not present above.\n"
    'Return JSON: {{"description": "...", "category": "...", '
    '"authority_recommendation": "...", "confidence": 0.0}}'
)

RTI_DRAFT_PROMPT: str = (
    "You are drafting an RTI (Right to Information) application under the RTI Act 2005.\n"
    "\n"
    "Complaint details:\n"
    "- Category: {category}\n"
    "- Location: {address}\n"
    "- Submitted: {submitted_at}\n"
    "- Authority: {authority_name}\n"
    "- Reference: {mock_gov_ref}\n"
    "- Status: {status} (no resolution for {days_elapsed} days)\n"
    "\n"
    "Relevant RTI context:\n"
    "{rag_context}\n"
    "\n"
    "Draft a formal RTI application addressing:\n"
    "1. Information sought about complaint status\n"
    "2. Actions taken by authority\n"
    "3. Timeline of events\n"
    "\n"
    "Format as a formal letter. Max 500 words.\n"
    'Return JSON: {{"draft_text": "..."}}'
)

CATEGORY_CLASSIFICATION_PROMPT: str = (
    "You are a civic issue classifier for Mangaluru, India.\n"
    "Given the following image context, classify the civic issue category.\n"
    "\n"
    "Detected objects: {detected_objects}\n"
    "Location: {address}\n"
    "Additional context: {extra_context}\n"
    "\n"
    "Valid categories: pothole, waterlogging, broken_streetlight, garbage_overflow, "
    "open_drain, illegal_construction, water_supply, sewage, road_damage, other\n"
    "\n"
    "Pick the single most appropriate category.\n"
    "Do not invent new categories.\n"
    'Return JSON: {{"description": "...", "category": "...", '
    '"authority_recommendation": "...", "confidence": 0.0}}'
)

# ---------------------------------------------------------------------------
# Vision-based civic image classification prompt
# Used with Groq vision models (e.g. qwen/qwen3.8-27b).
#
# Output categories map 1:1 to the existing IssueCategory DB enum values,
# plus "water_sewage" (resolved to water_supply/sewage/waterlogging via reason)
# and "invalid" (not a civic issue).
#
# DB enum values used directly as output:
#   pothole, road_damage, broken_streetlight, garbage_overflow,
#   open_drain, illegal_construction, waterlogging, water_supply, sewage, other
# Internal-only bucket (resolved by caller):
#   water_sewage → water_supply | sewage | waterlogging (via reason subtype)
# Rejection marker:
#   invalid → raises ImageValidationError
# ---------------------------------------------------------------------------

CIVIC_IMAGE_CLASSIFICATION_PROMPT: str = (
    "You are a civic infrastructure classifier for a municipal complaint app in "
    "Mangaluru, India.\n"
    "\n"
    "TASK: Identify the PRIMARY CIVIC PROBLEM the citizen is reporting.\n"
    "Return EXACTLY one category from the list below.\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "CRITICAL: ROAD VISIBLE ≠ ROAD DAMAGE\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "Roads, vehicles, buildings, poles, people, and trees are BACKGROUND CONTEXT.\n"
    "You are classifying the CIVIC PROBLEM, not the largest object in the frame.\n"
    "\n"
    "These situations do NOT produce road_damage:\n"
    "  • Garbage/waste on or beside a road          → garbage_overflow\n"
    "  • Standing/flooded water on a road           → water_sewage (waterlogging)\n"
    "  • Sewage/wastewater discharge near a road    → water_sewage (sewage)\n"
    "  • Burst/leaking water pipe near a road       → water_sewage (water_leakage)\n"
    "  • Open/uncovered drain beside a road         → open_drain\n"
    "  • Construction encroaching near a road       → illegal_construction\n"
    "  • Broken streetlight beside a road           → broken_streetlight\n"
    "  • A road that is merely visible/undamaged    → NOT road_damage (use other\n"
    "                                                  or most specific category)\n"
    "\n"
    "road_damage is valid ONLY when the road SURFACE ITSELF is visibly broken,\n"
    "cracked, eroded, collapsed, or severely deteriorated.\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "CLASSIFICATION PRIORITY ORDER\n"
    "(check each in order; use the FIRST one that fits the image)\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "1. pothole\n"
    "   A distinct localized HOLE, pit, cavity, or depression in the road surface.\n"
    "   Use for: clear hole in asphalt, water-filled pit, multiple potholes.\n"
    "   A visible hole ALWAYS wins over surface cracks.\n"
    "   The road is the subject AND it has a hole → pothole.\n"
    "\n"
    "2. garbage_overflow\n"
    "   Accumulated garbage, dumped waste, overflowing bins, or litter is the\n"
    "   DOMINANT visible civic problem.\n"
    "   Use for: waste pile on roadside, illegal garbage dump, overflowing bin,\n"
    "   solid/household/commercial waste on any public space.\n"
    "   !! Road visible behind/under garbage → garbage_overflow, NOT road_damage.\n"
    "   !! Vehicles, buildings, people in frame → still garbage_overflow.\n"
    "   !! Any scene where waste is the obvious reported problem → garbage_overflow.\n"
    "\n"
    "3. water_sewage\n"
    "   Any water or sewage civic problem. ALWAYS prefer over 'other'.\n"
    "   Road presence does NOT change this.\n"
    "   Subtypes — put ONE subtype keyword in the 'reason' field:\n"
    "     water_leakage : burst/leaking/broken water supply pipe, water gushing\n"
    "     sewage        : sewage overflow, wastewater discharge, dark/foul water\n"
    "     waterlogging  : standing/flood/stagnant water on road/public space\n"
    "   !! Flooded road surface → water_sewage (waterlogging), NOT road_damage.\n"
    "   !! Dark water discharging from manhole/drain → water_sewage (sewage).\n"
    "   !! Pipe spraying/leaking water → water_sewage (water_leakage).\n"
    "\n"
    "4. open_drain\n"
    "   An exposed, uncovered, unprotected, or blocked drainage channel/gutter\n"
    "   that poses a public hazard.\n"
    "   Use for: open storm drain, missing drain cover, blocked/broken drain.\n"
    "   !! Road beside the drain is only context → open_drain, NOT road_damage.\n"
    "\n"
    "5. broken_streetlight\n"
    "   A street lamp, lamp post, or related lighting infrastructure is visibly\n"
    "   broken, fallen, damaged, or non-functional.\n"
    "   !! Road, vehicles, or buildings visible → still broken_streetlight.\n"
    "   !! Do NOT return 'other' for a clearly damaged lamp or post.\n"
    "\n"
    "6. illegal_construction\n"
    "   Construction or structure visibly encroaching on public land, a road,\n"
    "   or a footpath in a way that constitutes a civic hazard or obstruction.\n"
    "   Only use when visual evidence clearly suggests unauthorized encroachment.\n"
    "   If uncertain whether construction is unauthorized, prefer 'other'.\n"
    "   !! Construction beside a road is not road_damage.\n"
    "\n"
    "7. road_damage\n"
    "   The ROAD SURFACE ITSELF is the primary civic problem, showing:\n"
    "   cracks, broken pavement, severe surface deterioration, erosion, or\n"
    "   collapsed road surface — without a distinct identifiable hole.\n"
    "   !! ONLY use when the road surface itself is visibly and clearly damaged.\n"
    "   !! A road that is merely visible as background is NOT road_damage.\n"
    "   !! Do NOT use road_damage when any of 1–6 above is the real problem.\n"
    "\n"
    "8. other\n"
    "   A genuine civic problem that clearly does not fit any category above.\n"
    "   Use as last resort. Do NOT use 'other' when a specific category fits.\n"
    "\n"
    "9. invalid\n"
    "   NOT a civic issue: selfie, portrait, indoor scene, food, animal,\n"
    "   nature, or abstract content with no civic infrastructure context.\n"
    "   Set valid=false.\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "DISAMBIGUATION EXAMPLES:\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "  • Hole/pit in road surface                       → pothole\n"
    "  • Cracks/broken asphalt, no hole                 → road_damage\n"
    "  • Garbage pile ON a road (road visible)          → garbage_overflow\n"
    "  • Garbage beside road, vehicles in background    → garbage_overflow\n"
    "  • Standing/stagnant water on road surface        → water_sewage (waterlogging)\n"
    "  • Flooded road with vehicles visible             → water_sewage (waterlogging)\n"
    "  • Sewage/dark water from manhole or drain        → water_sewage (sewage)\n"
    "  • Burst/leaking pipe on a road                  → water_sewage (water_leakage)\n"
    "  • Open/uncovered drain beside road               → open_drain\n"
    "  • Construction encroaching on footpath/road      → illegal_construction\n"
    "  • Broken/fallen street lamp (road in background) → broken_streetlight\n"
    "  • Road visible but undamaged — garbage is issue  → garbage_overflow\n"
    "  • Road visible but undamaged — water is issue    → water_sewage (waterlogging)\n"
    "  • Road visible but undamaged — drain is issue    → open_drain\n"
    "  • Road itself cracked/broken (no garbage/water)  → road_damage\n"
    "  • Selfie / portrait / person-only photo          → invalid\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "DESCRIPTION RULE:\n"
    "The 'description' field must describe the SAME problem as 'category'.\n"
    "If category=garbage_overflow → describe the garbage/waste, not the road.\n"
    "If category=water_sewage    → describe the water/sewage, not the road.\n"
    "If category=open_drain      → describe the drain, not the road.\n"
    "If category=road_damage     → describe the road surface damage specifically.\n"
    "NEVER write a road-damage description when category is not road_damage.\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "ABSOLUTE RULES:\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "A. road_damage REQUIRES visible physical road surface deterioration.\n"
    "   A road that is merely visible or has traffic on it is NOT road_damage.\n"
    "B. Always classify by the abnormal/problematic civic element, not the\n"
    "   largest or most prominent background element.\n"
    "C. The road model hint below is NON-AUTHORITATIVE secondary evidence\n"
    "   from a specialist that only sees road surfaces. It can be wrong when\n"
    "   garbage, water, a drain, or a streetlight is the real problem.\n"
    "   Your visual judgment and the priority order above override the hint.\n"
    "D. Do not hallucinate civic problems not visible in the image.\n"
    "   If uncertain, use 'other' rather than inventing a specific problem.\n"
    "\n"
    "Road model hint (NON-AUTHORITATIVE — may be wrong, treat as weak evidence only):\n"
    "{road_model_hint}\n"
    "Location context (may be empty): {address}\n"
    "\n"
    "Respond with ONLY a valid JSON object — no markdown, no preamble, no extra text.\n"
    "The JSON must have exactly these fields:\n"
    '{{"valid": true, "category": "garbage_overflow", "confidence": 0.91, '
    '"severity": 0.5, '
    '"primary_issue": "Short factual description of the actual civic problem (e.g. large garbage pile on roadside).", '
    '"description": "One sentence describing the primary civic problem visible.", '
    '"reason": "One sentence explaining why this category was chosen."}}\n'
    "\n"
    "primary_issue: Describe ONLY the civic problem itself — not the road, not the background.\n"
    "  garbage_overflow → describe the garbage/waste\n"
    "  water_sewage     → describe the water/sewage issue\n"
    "  open_drain       → describe the exposed drain\n"
    "  road_damage      → describe the road surface damage\n"
    "  broken_streetlight → describe the damaged lamp/pole\n"
    "  illegal_construction → describe the encroaching structure\n"
    "NEVER mention 'road' or 'road damage' in primary_issue when category is not road_damage."
)
