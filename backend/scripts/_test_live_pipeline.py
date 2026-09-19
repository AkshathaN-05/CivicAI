"""Test the full production civic_classify_image path with a realistic garbage-like image.

Creates a synthetic garbage-color image (browns, yellows, messy texture) to verify
the production path works end-to-end with reasoning_effort=high + strict JSON schema.
"""
import asyncio, base64, io, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

key = ""
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip().startswith("GROQ_API_KEY="):
                key = line.strip().split("=", 1)[1].strip()

os.environ["GROQ_API_KEY"] = key

from cv.pipeline import run_ai_pipeline
from cv.detection import DetectionResult
from cv.road_damage import RoadDamageResult
from schemas.report import IssueCategory
from unittest.mock import patch
from PIL import Image, ImageDraw
import random


def make_garbage_image() -> bytes:
    """Create a 800x600 image with heavy garbage-like colours (browns, yellows, greens)
    to simulate a garbage pile scene."""
    random.seed(42)
    img = Image.new("RGB", (800, 600))
    draw = ImageDraw.Draw(img)
    # Gray road at bottom 20%
    draw.rectangle([0, 480, 800, 600], fill=(100, 100, 100))
    # Garbage pile fills most of the frame
    for _ in range(300):
        x = random.randint(0, 780)
        y = random.randint(20, 470)
        w = random.randint(10, 60)
        h = random.randint(10, 40)
        color = random.choice([
            (180, 140, 60),   # cardboard
            (200, 170, 80),   # paper
            (80, 120, 60),    # rotting organic
            (220, 80, 40),    # plastic bag orange
            (60, 80, 50),     # dark organic waste
            (240, 220, 100),  # yellow plastic
            (100, 60, 40),    # dark waste
        ])
        draw.rectangle([x, y, x+w, y+h], fill=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def make_waterlogging_image() -> bytes:
    """Create an image with blue/dark water flooding a road."""
    random.seed(7)
    img = Image.new("RGB", (800, 600))
    draw = ImageDraw.Draw(img)
    # Sky
    draw.rectangle([0, 0, 800, 200], fill=(150, 180, 220))
    # Buildings
    draw.rectangle([0, 100, 200, 350], fill=(180, 160, 140))
    draw.rectangle([600, 80, 800, 350], fill=(170, 150, 130))
    # Flooded road - fills most of frame
    for y_start in range(300, 600, 5):
        blue = 100 + (y_start - 300) // 10
        draw.rectangle([0, y_start, 800, y_start+4],
                       fill=(30, 60, blue))
    # Reflections
    for _ in range(50):
        x = random.randint(0, 780)
        y = random.randint(310, 590)
        draw.ellipse([x, y, x+20, y+8], fill=(180, 200, 230), outline=None)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


async def run_pipeline_with_image(label: str, img_bytes: bytes,
                                   mock_road_detected: bool = True) -> None:
    """Run the production pipeline end to end on the given image bytes."""
    print(f"\n{'='*60}")
    print(f"Testing: {label}")
    print(f"Image size: {len(img_bytes)} bytes")

    def _fake_detect(_img):
        return DetectionResult(
            yolo_class="car", confidence=0.5, category=IssueCategory.road_damage,
            all_class_names=("car",),
        )

    def _fake_road(_img):
        if mock_road_detected:
            return RoadDamageResult(detected=True, category="road_damage",
                                    confidence=0.60, raw_class="D20")
        return RoadDamageResult(detected=False, category="", confidence=0.1)

    async def _fake_desc(cv_result, location, address):
        from llm.output_validator import LLMOutput
        cat = str(getattr(cv_result.get("category"), "value", cv_result.get("category", "other")))
        return LLMOutput(category="other", description=f"Issue: {cat}",
                         authority_recommendation="MCC", confidence=0.5)

    async def _fake_classify_cat(ctx):
        return IssueCategory.other

    with patch("cv.detection.detect_civic_issue", _fake_detect), \
         patch("cv.road_damage.classify_road_damage", _fake_road), \
         patch("services.llm_service.generate_complaint_description", _fake_desc), \
         patch("services.llm_service.classify_category", _fake_classify_cat):
        try:
            result = await run_ai_pipeline(img_bytes, location="12.9,74.8",
                                           address="MG Road, Mangaluru")
            print(f"  category:    {result.category.value}")
            print(f"  confidence:  {result.confidence:.2f}")
            print(f"  provider:    {result.llm_provider_used}")
            print(f"  authority:   {result.authority_recommendation}")
            print(f"  description: {result.description[:120]}")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {str(e)[:200]}")


async def main():
    print("Live production-path test with synthetic civic images")
    print("(API key present, not printed)")
    print("Road specialist will return road_damage hint for both images")
    print("Groq Vision should still override to the correct category")

    garbage_bytes = make_garbage_image()
    water_bytes = make_waterlogging_image()

    await run_pipeline_with_image("GARBAGE IMAGE + road specialist road_damage hint",
                                   garbage_bytes, mock_road_detected=True)
    await run_pipeline_with_image("WATERLOGGING IMAGE + road specialist road_damage hint",
                                   water_bytes, mock_road_detected=True)

    print("\nDone.")


asyncio.run(main())
