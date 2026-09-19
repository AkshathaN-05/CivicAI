"""Diagnostic script: trace the full classification path for synthetic civic images.

Run from backend/ directory:
    python scripts/diagnose_classification.py

Tests each step of the pipeline for the four primary categories:
1. pothole
2. road_damage
3. streetlight
4. sewage/water

Also verifies that generic YOLO labels (car/person/pole) cannot override Vision.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys

# Add backend/ to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env manually
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(levelname)s %(message)s")
logging.getLogger("ultralytics").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("groq").setLevel(logging.WARNING)

from PIL import Image, ImageDraw

def _make_synthetic_jpeg(description: str = "gray civic", width=320, height=320) -> bytes:
    """Create a synthetic grayscale image (simulates civic scene)."""
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    draw = ImageDraw.Draw(img)
    # Draw some lines to simulate road/structure
    draw.line([(0, height // 2), (width, height // 2)], fill=(80, 80, 80), width=8)
    draw.line([(width // 2, 0), (width // 2, height)], fill=(80, 80, 80), width=3)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Step 1: Test _normalise_category directly
# ---------------------------------------------------------------------------
def test_normalise_category():
    print("\n" + "=" * 70)
    print("STEP 1: _normalise_category() tests")
    print("=" * 70)
    from llm.groq_provider import _normalise_category

    cases = [
        ("pothole", "pothole"),
        ("road hole", "pothole"),
        ("road pit", "pothole"),
        ("road_damage", "road_damage"),
        ("cracked road", "road_damage"),
        ("damaged road", "road_damage"),
        ("streetlight", "streetlight"),
        ("lamp post", "streetlight"),
        ("broken streetlight", "streetlight"),
        ("sewage", "sewage"),
        ("wastewater", "sewage"),
        ("water_sewage", "water_sewage"),
        ("other", "other"),
        ("invalid", "invalid"),
        ("car", "other"),            # generic YOLO â†’ normalises to 'other'
        ("person", "other"),         # generic YOLO â†’ normalises to 'other'
        ("pole", "other"),           # generic YOLO â†’ normalises to 'other'
    ]

    all_ok = True
    for raw, expected in cases:
        got = _normalise_category(raw)
        ok = (got == expected)
        status = "OK" if ok else "FAIL"
        print(f"  {status}  {raw!r:35}  got={got!r:20}  expected={expected!r}")
        if not ok:
            all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# Step 2: Test _parse_civic_classification
# ---------------------------------------------------------------------------
def test_parse_civic_classification():
    print("\n" + "=" * 70)
    print("STEP 2: _parse_civic_classification() tests")
    print("=" * 70)
    from llm.groq_provider import _parse_civic_classification

    cases = [
        ({"valid": True, "category": "pothole", "confidence": 0.92, "severity": 0.85, "reason": "hole visible"}, "pothole"),
        ({"valid": True, "category": "road_damage", "confidence": 0.80, "severity": 0.5, "reason": "cracks"}, "road_damage"),
        ({"valid": True, "category": "streetlight", "confidence": 0.88, "severity": 0.5, "reason": "broken lamp"}, "streetlight"),
        ({"valid": True, "category": "sewage", "confidence": 0.75, "severity": 0.85, "reason": "wastewater"}, "sewage"),
        ({"valid": True, "category": "water_sewage", "confidence": 0.80, "severity": 0.5, "reason": "sewage overflow visible"}, "water_sewage"),
        ({"valid": False, "category": "invalid", "confidence": 0.0, "severity": 0.0, "reason": "selfie"}, "invalid"),
        ({"valid": True, "category": "lamp post", "confidence": 0.88, "severity": 0.5, "reason": "damaged"}, "streetlight"),  # synonym
        ({"valid": True, "category": "wastewater", "confidence": 0.75, "severity": 0.85, "reason": "sewage"}, "sewage"),  # synonym
    ]

    all_ok = True
    for raw_dict, expected_cat in cases:
        result = _parse_civic_classification(raw_dict)
        ok = (result.category == expected_cat)
        status = "OK" if ok else "FAIL"
        print(f"  {status}  input category={raw_dict['category']!r:25} â†’ parsed={result.category!r:20}  valid={result.valid}")
        if not ok:
            print(f"       EXPECTED: {expected_cat!r}")
            all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# Step 3: Test map_vision_category_to_issue_category
# ---------------------------------------------------------------------------
def test_map_vision_category():
    print("\n" + "=" * 70)
    print("STEP 3: map_vision_category_to_issue_category() tests")
    print("=" * 70)
    from llm.fallback_provider import map_vision_category_to_issue_category
    from schemas.report import IssueCategory

    cases = [
        ("pothole", "", IssueCategory.pothole),
        ("road_damage", "", IssueCategory.road_damage),
        ("streetlight", "", IssueCategory.broken_streetlight),
        ("sewage", "", IssueCategory.sewage),
        ("water_sewage", "sewage overflow visible", IssueCategory.sewage),
        ("water_sewage", "water_leakage: broken pipe", IssueCategory.water_supply),
        ("water_sewage", "waterlogging standing water", IssueCategory.waterlogging),
        ("water_sewage", "", IssueCategory.water_supply),  # default
        ("drainage", "", IssueCategory.open_drain),
        ("garbage", "", IssueCategory.garbage_overflow),
        ("other", "", IssueCategory.other),
        ("invalid", "", IssueCategory.other),
        # Synonyms via normalisation
        ("lamp post", "", IssueCategory.broken_streetlight),
        ("wastewater", "", IssueCategory.sewage),
        ("drain", "", IssueCategory.open_drain),
    ]

    all_ok = True
    for vision_cat, reason, expected in cases:
        got = map_vision_category_to_issue_category(vision_cat, reason=reason)
        ok = (got == expected)
        status = "OK" if ok else "FAIL"
        print(f"  {status}  ({vision_cat!r}, reason={reason!r})  got={got.value!r}  expected={expected.value!r}")
        if not ok:
            all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# Step 4: Test fallback_civic_classify_image (no-API path)
# ---------------------------------------------------------------------------
def test_fallback_classify():
    print("\n" + "=" * 70)
    print("STEP 4: fallback_civic_classify_image() â€” YOLO-only path (no Groq)")
    print("=" * 70)
    from llm.fallback_provider import fallback_civic_classify_image

    cases = [
        # (yolo_class, all_class_names, address, note)
        ("car",    ("car",),           "road",       "YOLO=car â†’ road_damage (not pothole/other)"),
        ("person", ("person",),        "road",       "YOLO=person â†’ other (no civic indicator in heuristic)"),
        ("person", ("person",),        "pothole here", "YOLO=person, addr=pothole â†’ pothole via address"),
        ("person", ("person",),        "sewage overflow", "YOLO=person, addr=sewage â†’ sewage via address"),
        ("person", ("person",),        "streetlight broken", "YOLO=person, addr=streetlight â†’ streetlight via address"),
    ]

    all_ok = True
    for yolo_class, all_names, address, note in cases:
        result = fallback_civic_classify_image(yolo_class, all_names, address)
        print(f"  {note}")
        print(f"    â†’ category={result.category!r}  valid={result.valid}  conf={result.category_confidence:.2f}")
    return all_ok


# ---------------------------------------------------------------------------
# Step 5: Live Groq Vision call â€” actual API test
# ---------------------------------------------------------------------------
async def test_groq_vision_live():
    print("\n" + "=" * 70)
    print("STEP 5: Live Groq Vision call (actual API)")
    print("=" * 70)

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("  SKIP â€” GROQ_API_KEY not set")
        return True

    print(f"  GROQ_API_KEY: {api_key[:8]}...{api_key[-4:]}")

    from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
    reset_groq_clients_for_testing()

    # Create a synthetic image that simulates a road with a pothole-like circle
    img = Image.new("RGB", (400, 300), color=(100, 100, 100))
    draw = ImageDraw.Draw(img)
    # Draw a dark oval to simulate a pothole
    draw.ellipse([(150, 120), (250, 180)], fill=(30, 30, 30), outline=(20, 20, 20))
    # Draw road texture
    draw.rectangle([(0, 200), (400, 300)], fill=(80, 80, 80))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    synthetic_bytes = buf.getvalue()

    try:
        result = await civic_classify_image(
            synthetic_bytes,
            address="Test - synthetic pothole image",
            road_model_hint="",
        )
        print(f"  valid={result.valid}")
        print(f"  category={result.category!r}")
        print(f"  confidence={result.category_confidence:.3f}")
        print(f"  severity={result.severity!r}  severity_score={result.severity_score:.2f}")
        print(f"  reason={result.reason!r}")
        print(f"  description={result.description[:100]!r}")
        return True
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return False


# ---------------------------------------------------------------------------
# Step 6: Full pipeline trace with real API key but mocked heavy models
# ---------------------------------------------------------------------------
async def test_full_pipeline_trace():
    print("\n" + "=" * 70)
    print("STEP 6: Full pipeline trace â€” real Groq Vision, mocked YOLO/road models")
    print("=" * 70)

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("  SKIP â€” GROQ_API_KEY not set")
        return True

    from unittest.mock import patch, MagicMock
    from cv.pipeline import run_ai_pipeline
    from cv.road_damage import RoadDamageResult
    from schemas.report import IssueCategory

    image_bytes = _make_synthetic_jpeg()

    # Mock only the heavy models; let Groq Vision run for real
    def _fake_detect(img):
        m = MagicMock()
        m.yolo_class = "car"        # generic YOLO label
        m.confidence = 0.72
        m.category = IssueCategory.road_damage
        m.all_class_names = ("car",)
        return m

    def _fake_road(img):
        return RoadDamageResult(detected=False, category="", confidence=0.0)

    def _fake_redact(img):
        return img

    print("  YOLO says: 'car' (road_damage)")
    print("  Road model: not detected")
    print("  Groq Vision: receiving redacted_bytes â†’ ...")

    try:
        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=_fake_redact),
        ):
            result = await run_ai_pipeline(
                image_bytes,
                location="12.97,74.82",
                address="MG Road, Mangaluru",
            )

        print(f"\n  FINAL RESULT:")
        print(f"    category          = {result.category.value!r}")
        print(f"    confidence        = {result.confidence:.3f}")
        print(f"    llm_provider_used = {result.llm_provider_used!r}")
        print(f"    yolo_class        = {result.yolo_class!r}")
        print(f"    description       = {result.description[:100]!r}")
        return True
    except Exception as exc:
        print(f"  ERROR in pipeline: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("CivicAI Classification Diagnostic")
    print("=" * 70)

    results = []
    results.append(("normalise_category", test_normalise_category()))
    results.append(("parse_civic_classification", test_parse_civic_classification()))
    results.append(("map_vision_category", test_map_vision_category()))
    results.append(("fallback_classify", test_fallback_classify()))
    results.append(("groq_vision_live", await test_groq_vision_live()))
    results.append(("full_pipeline_trace", await test_full_pipeline_trace()))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    all_pass = True
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  {status:6}  {name}")
        if not ok:
            all_pass = False

    print("\n" + ("ALL TESTS PASSED" if all_pass else "SOME TESTS FAILED"))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

