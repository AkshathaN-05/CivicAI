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
    "TASK: Look at the image. Identify the PRIMARY civic problem visible.\n"
    "Return EXACTLY one category from the list below.\n"
    "\n"
    "You are classifying the CIVIC PROBLEM, not the most prominent object.\n"
    "Roads, poles, vehicles, people, buildings, and trees are BACKGROUND CONTEXT.\n"
    "The civic damage or civic hazard is what must be classified.\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "VALID OUTPUT VALUES (return the exact string shown):\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "  pothole\n"
    "    A localized hole, pit, cavity, or depression in the road surface.\n"
    "    Use for: distinct hole in asphalt, water-filled pit, broken asphalt forming "
    "a hole, multiple potholes.\n"
    "    KEY: A visible hole always wins over surface cracks.\n"
    "\n"
    "  road_damage\n"
    "    Physical deterioration of the road surface itself — but WITHOUT a distinct hole.\n"
    "    Use for: cracks (longitudinal, transverse, alligator/mesh), broken pavement,\n"
    "    collapsed or severely deteriorated road surface with no single identifiable hole.\n"
    "    !! DO NOT use road_damage just because a road is visible in the background.\n"
    "    !! Garbage on a road is still garbage_overflow, NOT road_damage.\n"
    "    !! A streetlight on a road is still broken_streetlight, NOT road_damage.\n"
    "\n"
    "  broken_streetlight\n"
    "    A civic problem with street lighting or lamp infrastructure.\n"
    "    Use for: broken/damaged/fallen street lamp, damaged lamp post, cracked lamp\n"
    "    housing, non-functional streetlight, exposed wiring on a lamp pole,\n"
    "    damaged electric pole that carries street lighting.\n"
    "    !! Use broken_streetlight whenever the LAMP or POST is the obvious problem.\n"
    "    !! Do NOT classify a broken streetlight as 'other' just because a road or\n"
    "    !! pole is visible. The damaged light infrastructure IS the civic problem.\n"
    "\n"
    "  garbage_overflow\n"
    "    Accumulated garbage, dumped waste, or overflowing bins as the dominant civic issue.\n"
    "    Use for: large roadside waste pile, illegal garbage dump, overflowing municipal bin,\n"
    "    accumulated household/solid/commercial waste on a public road or public space.\n"
    "    !! Garbage dumped ON a road is still garbage_overflow, NOT road_damage.\n"
    "    !! The presence of a road under/behind the garbage does NOT change the category.\n"
    "    !! Use garbage_overflow whenever waste accumulation is the primary problem.\n"
    "\n"
    "  water_sewage\n"
    "    Any water or sewage civic problem. Always prefer this over 'other' for water/sewage.\n"
    "    Subtypes — put the subtype word in the 'reason' field:\n"
    "      water_leakage : burst/leaking/broken water supply pipe, water gushing from pipe\n"
    "      sewage        : sewage overflow, wastewater discharge, dark foul water from drain\n"
    "      waterlogging  : standing/flood water on road or public space, no visible pipe\n"
    "\n"
    "  open_drain\n"
    "    Exposed, uncovered, or blocked storm/drainage channels posing a hazard.\n"
    "    Use for: open drain without cover, blocked stormwater drain, broken drain cover.\n"
    "\n"
    "  illegal_construction\n"
    "    Unauthorised construction encroaching on public land, road, or footpath.\n"
    "\n"
    "  other\n"
    "    LAST RESORT ONLY — a genuine civic problem that clearly does NOT fit any\n"
    "    category above. Use 'other' only when none of the specific categories apply.\n"
    "    !! Do NOT return 'other' for a clearly broken streetlight.\n"
    "    !! Do NOT return 'other' for visible garbage/waste.\n"
    "    !! Do NOT return 'other' for water/sewage problems.\n"
    "\n"
    "  invalid\n"
    "    Not a civic issue: selfie, portrait, indoor photo, food, animal,\n"
    "    nature scenery, abstract/random content with no civic infrastructure.\n"
    "    Use valid=false with this category.\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "DISAMBIGUATION EXAMPLES:\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "  • Hole/pit in road surface                 → pothole\n"
    "  • Cracks/broken asphalt, no hole           → road_damage\n"
    "  • Garbage pile on/beside a road            → garbage_overflow  (NOT road_damage)\n"
    "  • Garbage bags on a road with cars         → garbage_overflow  (NOT road_damage)\n"
    "  • Broken/damaged street lamp or post       → broken_streetlight (NOT other)\n"
    "  • Dangling lamp fixture on a pole          → broken_streetlight (NOT other)\n"
    "  • Burst water pipe spraying water          → water_sewage (reason: water_leakage)\n"
    "  • Sewage/dark water discharging from drain → water_sewage (reason: sewage)\n"
    "  • Flooded road, no visible pipe            → water_sewage (reason: waterlogging)\n"
    "  • Selfie / portrait / person-only photo    → invalid\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "ABSOLUTE RULES (never violate these):\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "A. road_damage requires the road SURFACE ITSELF to be damaged (cracked/broken "
    "pavement). A road that is merely visible as background is NOT road damage.\n"
    "B. broken_streetlight must be used whenever a lamp post, street lamp, or lamp "
    "fixture is visibly damaged — even if a road, pole, vehicles, or people are also "
    "in the frame.\n"
    "C. garbage_overflow must be used whenever accumulated waste/garbage is the "
    "dominant civic problem — even if the waste is located on a road or roadside.\n"
    "D. water_sewage must be used for any visible water pipe burst, sewage discharge, "
    "or flooding — never classify these as 'other'.\n"
    "E. 'other' and 'invalid' are last resorts — never use them when a specific "
    "category fits.\n"
    "F. Your classification is based entirely on the IMAGE. The road model hint "
    "below is NON-AUTHORITATIVE secondary evidence from a specialist detector that "
    "only sees road surfaces. IT CAN BE WRONG, especially when garbage, a streetlight, "
    "or a water pipe is the real issue. Your visual judgment overrides the hint.\n"
    "\n"
    "Road model hint (NON-AUTHORITATIVE — may be wrong, treat as weak evidence only):\n"
    "{road_model_hint}\n"
    "Location context (may be empty): {address}\n"
    "\n"
    "Respond with ONLY a valid JSON object — no markdown, no preamble, no extra text.\n"
    "The JSON must have exactly these fields:\n"
    '{{"valid": true, "category": "garbage_overflow", "confidence": 0.91, '
    '"severity": 0.5, '
    '"description": "One sentence describing what is visible in the image.", '
    '"reason": "One sentence explaining the classification decision."}}'
)
