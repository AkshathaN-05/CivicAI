"""Test qwen/qwen3.8-27b for vision classification capability."""
import asyncio
import base64
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")) as f:
    for line in f:
        if line.startswith("GROQ_API_KEY="):
            os.environ["GROQ_API_KEY"] = line.strip().split("=", 1)[1]

import groq
from PIL import Image, ImageDraw


def make_gray_jpeg():
    img = Image.new("RGB", (200, 200), color=(80, 80, 80))
    draw = ImageDraw.Draw(img)
    draw.ellipse([70, 70, 130, 130], fill=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


PROMPT = (
    "You are a civic infrastructure classifier for Mangaluru, India.\n"
    "\n"
    "YOUR JOB: Look at the ENTIRE image. Identify the PRIMARY civic infrastructure "
    "problem. Classify it into EXACTLY one of the categories below.\n"
    "\n"
    "VALID CATEGORIES:\n"
    "  pothole      - A LOCALIZED HOLE, depression, cavity, or crater in road\n"
    "  road_damage  - Road surface deterioration WITHOUT a distinct hole\n"
    "  streetlight  - Broken/damaged/non-functional street lamp or lamp post\n"
    "  water_sewage - Any water/sewage civic problem (leakage, sewage, waterlogging)\n"
    "  other        - LAST RESORT: genuine civic problem not fitting above\n"
    "  invalid      - NOT a civic issue at all\n"
    "\n"
    "Road model hint: none\n"
    "Location hint: test\n"
    "\n"
    'Respond ONLY with valid JSON:\n'
    '{"valid": true, "category": "pothole", "confidence": 0.92, "severity": 0.85, '
    '"description": "Description.", "reason": "Reason."}'
)


async def test_model(model_id: str) -> None:
    img_bytes = make_gray_jpeg()
    b64 = base64.b64encode(img_bytes).decode()
    url = f"data:image/jpeg;base64,{b64}"

    client = groq.AsyncGroq(api_key=os.environ["GROQ_API_KEY"], timeout=30)
    try:
        resp = await client.chat.completions.create(
            model=model_id,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }],
            max_tokens=400,
            temperature=0.1,
        )
        content = resp.choices[0].message.content or ""
        print(f"\nModel: {model_id}")
        print(f"Raw response ({len(content)} chars):")
        print(content[:400])

        # Try parsing JSON
        import re
        block_m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        bare_m = re.search(r"\{.*?\}", content, re.DOTALL)
        raw_json_str = (block_m.group(1) if block_m else (bare_m.group(0) if bare_m else None))
        if raw_json_str:
            d = json.loads(raw_json_str)
            print(f"\nParsed JSON: {d}")
        else:
            print("\nNo JSON found in response")
    except groq.GroqError as exc:
        print(f"\nModel {model_id}: GroqError: {exc}")
    except Exception as exc:
        print(f"\nModel {model_id}: Error: {exc}")


async def main():
    print("Testing vision models for civic classification...")
    await test_model("qwen/qwen3.8-27b")
    await test_model("qwen/qwen3.6-27b")


if __name__ == "__main__":
    asyncio.run(main())
