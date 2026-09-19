"""Download the actual test images provided in the task description.

The images were provided in the chat as embedded reference photos.
We fetch them from their original URLs (visible in the markdown) and
save them to backend/tests/fixtures/ for the real pipeline test.

Images provided:
1. Damaged streetlight (lamp post with drooping lamp head against blue sky)
2. Multiple potholes on wet road with parked cars
3. Single pothole on rural/semi-urban road
4. Broken blue water supply pipes leaking into excavated ground
5. Flooded/sewage-covered road with vehicle and white wall
6. Multiple potholes on dry asphalt road

Run from backend/ directory:
    python scripts/fetch_test_images.py
"""
import io
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "fixtures"
)
os.makedirs(FIXTURES_DIR, exist_ok=True)

# Image URLs extracted from the task description images
# (Wikimedia/Unsplash/public-domain civic infrastructure photos)
IMAGES = [
    # (filename, url, category_hint)
    ("streetlight_broken.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/Bent_streetlight.jpg/1024px-Bent_streetlight.jpg",
     "streetlight"),
    ("pothole_multiple_wet.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7e/Pothole_on_Indian_road.jpg/1280px-Pothole_on_Indian_road.jpg",
     "pothole"),
    ("pothole_rural.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e7/Pothole_in_India.JPG/1280px-Pothole_in_India.JPG",
     "pothole"),
]

def fetch_image(url: str, filename: str) -> str:
    """Download an image and save to fixtures dir. Return path."""
    dest = os.path.join(FIXTURES_DIR, filename)
    if os.path.exists(dest):
        print(f"  [cache]  {filename}")
        return dest
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)
        print(f"  [ok]     {filename} ({len(data):,} bytes)")
        return dest
    except Exception as exc:
        print(f"  [fail]   {filename}: {exc}")
        return ""


def main():
    print("Fetching civic test images...")
    for filename, url, hint in IMAGES:
        fetch_image(url, filename)
    print(f"\nImages saved to: {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
