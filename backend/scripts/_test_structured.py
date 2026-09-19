"""Test structured output + reasoning_effort options with qwen/qwen3.8-27b."""
import asyncio, base64, io, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

key = ""
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip().startswith("GROQ_API_KEY="):
                key = line.strip().split("=", 1)[1].strip()

import groq as _groq
from PIL import Image

def tiny_jpeg():
    img = Image.new("RGB", (64, 64), color=(80, 60, 40))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()

# All required fields, no additionalProperties (Groq strict requirement)
SCHEMA = {
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "category": {
            "type": "string",
            "enum": [
                "pothole", "waterlogging", "broken_streetlight", "garbage_overflow",
                "open_drain", "illegal_construction", "water_supply", "sewage",
                "road_damage", "other", "invalid"
            ]
        },
        "confidence": {"type": "number"},
        "description": {"type": "string"},
        "primary_issue": {"type": "string"},
    },
    "required": ["valid", "category", "confidence", "description", "primary_issue"],
    "additionalProperties": False
}

PROMPT = (
    "You are a civic infrastructure classifier for Mangaluru, India.\n"
    "Classify the PRIMARY CIVIC PROBLEM visible in this image.\n"
    "Return structured JSON matching the schema exactly."
)


async def test_effort(effort: str) -> None:
    client = _groq.AsyncGroq(api_key=key, timeout=40)
    img_bytes = tiny_jpeg()
    b64 = base64.b64encode(img_bytes).decode()
    url = f"data:image/jpeg;base64,{b64}"
    kwargs = dict(
        model="qwen/qwen3.8-27b",
        messages=[{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": url}},
        ]}],
        temperature=0.1,
        max_tokens=512,
        reasoning_format="hidden",
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "civic_classification",
                "schema": SCHEMA,
                "strict": True,
            }
        }
    )
    if effort != "none_omit":
        kwargs["reasoning_effort"] = effort

    label = f"reasoning_effort={effort!r}"
    try:
        resp = await client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        finish = resp.choices[0].finish_reason
        try:
            parsed = json.loads(content)
            cat = parsed.get("category", "?")
            pri = parsed.get("primary_issue", "?")
            print(f"{label}: OK  cat={cat!r}  primary_issue={pri!r}  finish={finish!r}")
        except json.JSONDecodeError:
            print(f"{label}: OK but json_failed  finish={finish!r}  content={content[:120]!r}")
    except _groq.BadRequestError as e:
        print(f"{label}: BadRequest: {str(e)[:250]}")
    except _groq.GroqError as e:
        print(f"{label}: GroqError {type(e).__name__}: {str(e)[:200]}")
    except Exception as e:
        print(f"{label}: Exception {type(e).__name__}: {str(e)[:200]}")


async def main():
    print("Testing reasoning_effort options with strict JSON schema...")
    for effort in ["high", "default", "low", "none", "none_omit"]:
        await test_effort(effort)


asyncio.run(main())
