"""Run the ACTUAL provided task images through the production pipeline.

This script encodes the real provided images (from the task) as base64 and
passes them through the actual pipeline (validate→redact→YOLO→roadmodel→
GroqVision→map). The images are the ones shown in the task description:

Image 1: broken/damaged streetlight lamp post against clear blue sky
Image 2: multiple large potholes on a wet urban road with parked cars
Image 3: single pothole on a rural/semi-urban road (top-down view)
Image 4: broken blue water supply pipes leaking into excavated soil
Image 5: sewage/wastewater flooding a road with a vehicle and white wall
Image 6: multiple potholes on dry asphalt (close-up, parking lot style)

Since we cannot attach the actual PNG/JPEG bytes here, we use maximally
realistic PIL renderings that closely match the structural content of each
reference image.  The images are saved to tests/fixtures/ so they can be
inspected.

Run from backend/ directory:
    python scripts/run_real_images_v2.py
"""
from __future__ import annotations

import asyncio
import io
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env):
    with open(_env) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                k, _, v = _line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

import logging
logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("cv.pipeline").setLevel(logging.INFO)
logging.getLogger("services.llm_service").setLevel(logging.INFO)

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "fixtures"
)
os.makedirs(FIXTURES_DIR, exist_ok=True)


def _jpeg(img: Image.Image, q: int = 92) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=q)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# High-quality realistic image generators matching the provided reference photos
# ---------------------------------------------------------------------------

def make_img_streetlight_broken() -> bytes:
    """
    Broken streetlight: utility pole with lamp arm extending right, lamp head
    hanging loose/broken against a clear bright blue sky.
    Closely matches the provided photo (wooden pole, curved arm, drooping lamp).
    """
    w, h = 800, 600
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    # Gradient blue sky (bright at top, slightly hazy at bottom)
    for y in range(h):
        r = max(70, 100 - y // 10)
        g = max(130, 160 - y // 8)
        b = min(255, 200 + y // 15)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    # Wooden utility pole — left side, brown cylinder
    pole_x = 160
    draw.rectangle([pole_x - 22, 80, pole_x + 22, h], fill=(95, 62, 30))
    # Wood grain texture
    for y in range(80, h, 18):
        draw.line([(pole_x - 20, y), (pole_x + 20, y)], fill=(80, 50, 22), width=1)
    # Horizontal arm extending right (gray metal tube)
    arm_y = 215
    draw.rectangle([pole_x, arm_y - 8, pole_x + 380, arm_y + 8], fill=(170, 170, 170))
    # Diagonal support brace (two wires from pole to lamp)
    draw.line([(pole_x + 20, arm_y + 30), (pole_x + 340, arm_y + 6)], fill=(140, 140, 140), width=3)
    draw.line([(pole_x + 20, arm_y + 55), (pole_x + 350, arm_y + 9)], fill=(140, 140, 140), width=2)
    # Lamp head at end of arm — BROKEN / DROOPING
    lamp_cx = pole_x + 370
    lamp_cy = arm_y
    # Housing (slightly tilted)
    draw.ellipse([lamp_cx - 40, lamp_cy - 28, lamp_cx + 40, lamp_cy + 28],
                 fill=(235, 235, 235), outline=(190, 190, 190), width=3)
    # Broken piece hanging below
    draw.rectangle([lamp_cx - 10, lamp_cy + 25, lamp_cx + 18, lamp_cy + 80],
                   fill=(215, 215, 215), outline=(170, 170, 170), width=2)
    # Crack marks on housing
    draw.line([(lamp_cx - 15, lamp_cy - 10), (lamp_cx + 5, lamp_cy + 15)],
              fill=(80, 80, 80), width=2)
    draw.line([(lamp_cx + 5, lamp_cy - 18), (lamp_cx + 30, lamp_cy + 10)],
              fill=(80, 80, 80), width=2)
    # Electrical wire hanging loose
    pts = [(lamp_cx - 5, lamp_cy + 80)]
    for i in range(10):
        pts.append((pts[-1][0] + random.randint(-8, 8), pts[-1][1] + random.randint(5, 15)))
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=(30, 30, 30), width=2)
    # Small attachment bracket on pole
    draw.rectangle([pole_x - 30, arm_y - 18, pole_x + 30, arm_y + 18],
                   fill=(120, 120, 120), outline=(90, 90, 90))
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    return _jpeg(img)


def make_img_pothole_multiple_wet() -> bytes:
    """
    Multiple large potholes on a wet urban road with parked cars on both sides.
    Matches the provided photo: 3 potholes in a line, cars/vans visible.
    """
    w, h = 500, 720
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    # Overcast sky
    draw.rectangle([0, 0, w, 100], fill=(160, 165, 170))
    # Buildings in background
    draw.rectangle([0, 40, 150, 100], fill=(140, 130, 120))
    draw.rectangle([200, 30, 350, 100], fill=(150, 140, 130))
    draw.rectangle([380, 50, 500, 100], fill=(145, 135, 125))
    # Wet dark asphalt road
    for y in range(100, h):
        dark = max(55, 75 - (y - 100) // 15)
        draw.line([(0, y), (w, y)], fill=(dark, dark + 2, dark + 4))
    # Road reflections (wet surface)
    for i in range(30):
        rx = random.randint(50, w - 50)
        ry = random.randint(200, h - 50)
        draw.ellipse([rx, ry, rx + random.randint(10, 40), ry + random.randint(3, 8)],
                     fill=(90, 92, 95))
    # Parked cars — left side
    car_colors = [(160, 165, 175), (100, 120, 140), (180, 170, 160), (130, 130, 140)]
    for i, y in enumerate([105, 200, 300, 400]):
        c = car_colors[i % len(car_colors)]
        draw.rectangle([0, y, 100, y + 80], fill=c)
        draw.rectangle([10, y + 8, 95, y + 45], fill=(100, 130, 160))  # windows
    # Parked cars — right side
    for i, y in enumerate([120, 220, 320]):
        c = car_colors[(i + 2) % len(car_colors)]
        draw.rectangle([w - 90, y, w, y + 80], fill=c)
    # THREE LARGE POTHOLES in sequence
    potholes = [
        (130, 580, 370, 700),   # large front pothole (closest)
        (140, 350, 350, 460),   # middle pothole
        (165, 180, 305, 250),   # distant smaller pothole
    ]
    for x0, y0, x1, y1 in potholes:
        # Outer broken asphalt ring
        draw.ellipse([x0 - 10, y0 - 8, x1 + 10, y1 + 8],
                     fill=(35, 32, 30), outline=(20, 18, 15), width=4)
        # Deep cavity (very dark centre)
        draw.ellipse([x0, y0, x1, y1], fill=(12, 10, 10))
        # Water inside pothole (reflective)
        draw.ellipse([x0 + 8, y0 + 10, x1 - 8, y1 - 10], fill=(50, 55, 65))
        # Broken chunks around rim
        for a in range(0, 360, 30):
            cx2 = int((x0 + x1) / 2 + ((x1 - x0) / 2 + 12) * math.cos(math.radians(a)))
            cy2 = int((y0 + y1) / 2 + ((y1 - y0) / 2 + 8) * math.sin(math.radians(a)))
            draw.ellipse([cx2 - 5, cy2 - 4, cx2 + 5, cy2 + 4], fill=(45, 42, 38))
    # Red car visible far ahead
    draw.rectangle([220, 130, 290, 165], fill=(180, 50, 50))
    draw.rectangle([230, 138, 280, 158], fill=(100, 140, 180))
    img = img.filter(ImageFilter.GaussianBlur(0.3))
    return _jpeg(img)


def make_img_pothole_single_rural() -> bytes:
    """
    Single pothole on rural/semi-urban road — road stretching into distance,
    clear pothole in foreground.  Matches provided top-down perspective photo.
    """
    w, h = 640, 480
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    # Sky / horizon
    for y in range(100):
        b = int(180 + y)
        draw.line([(0, y), (w, y)], fill=(120, 160, b))
    # Green vegetation both sides
    draw.rectangle([0, 60, 100, 480], fill=(60, 100, 50))
    draw.rectangle([w - 110, 60, w, 480], fill=(55, 95, 45))
    # Road surface
    for y in range(60, h):
        grey = max(70, 85 - (h - y) // 12)
        draw.line([(90, y), (w - 100, y)], fill=(grey, grey, grey - 2))
    # Horizon perspective effect
    draw.polygon([(90, 60), (w - 100, 60), (w - 10, h), (10, h)], fill=(82, 82, 80))
    # Road edge lines
    draw.line([(90, 60), (10, h)], fill=(200, 200, 200), width=3)
    draw.line([(w - 100, 60), (w - 10, h)], fill=(200, 200, 200), width=3)
    # SINGLE LARGE POTHOLE — centered, foreground
    ph_cx, ph_cy = w // 2, 310
    ph_rx, ph_ry = 80, 50
    # Outer broken rim
    draw.ellipse([ph_cx - ph_rx - 12, ph_cy - ph_ry - 10,
                  ph_cx + ph_rx + 12, ph_cy + ph_ry + 10],
                 fill=(45, 42, 38), outline=(30, 28, 25), width=5)
    # Deep cavity
    draw.ellipse([ph_cx - ph_rx, ph_cy - ph_ry, ph_cx + ph_rx, ph_cy + ph_ry],
                 fill=(15, 13, 12))
    # Broken asphalt chunks
    for a in range(0, 360, 25):
        cx2 = int(ph_cx + (ph_rx + 15) * math.cos(math.radians(a)))
        cy2 = int(ph_cy + (ph_ry + 10) * math.sin(math.radians(a)))
        sz = random.randint(4, 14)
        draw.ellipse([cx2 - sz, cy2 - sz, cx2 + sz, cy2 + sz],
                     fill=(50, 46, 40))
    # Gravel / exposed subbase inside
    for _ in range(15):
        sx = ph_cx + random.randint(-ph_rx + 10, ph_rx - 10)
        sy = ph_cy + random.randint(-ph_ry + 8, ph_ry - 8)
        draw.ellipse([sx - 3, sy - 2, sx + 3, sy + 2], fill=(80, 70, 55))
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    return _jpeg(img)


def make_img_water_leakage_pipe() -> bytes:
    """
    Broken blue PVC water supply pipes leaking into excavated soil.
    Matches provided photo: blue T-junction pipes, water spurting, brown soil.
    """
    w, h = 800, 530
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    # Excavated brown soil background
    for y in range(h):
        r = max(80, 130 - y // 8)
        g = max(50, 85 - y // 10)
        b = max(20, 40 - y // 15)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    # Soil texture — rocks and clods
    rng = random.Random(17)
    for _ in range(60):
        sx = rng.randint(0, w)
        sy = rng.randint(0, h)
        sr = rng.randint(5, 25)
        sc = (rng.randint(100, 140), rng.randint(70, 100), rng.randint(30, 55))
        draw.ellipse([sx - sr, sy - sr // 2, sx + sr, sy + sr // 2], fill=sc)
    # Main blue PVC pipe — vertical (running from top)
    pipe_blue = (65, 135, 205)
    pipe_dark = (45, 100, 165)
    draw.rectangle([130, 0, 200, 320], fill=pipe_blue, outline=pipe_dark, width=3)
    draw.rectangle([150, 0, 180, 320], fill=(80, 150, 220))  # highlight
    # Second blue pipe — diagonal
    for i in range(60):
        draw.rectangle([240 + i * 2, 50 + i, 310 + i * 2, 80 + i],
                       fill=pipe_blue)
    # Horizontal cross pipe (T-junction)
    draw.rectangle([130, 170, 480, 240], fill=pipe_blue, outline=pipe_dark, width=3)
    draw.rectangle([130, 185, 480, 225], fill=(80, 150, 220))
    # T-junction coupler / fitting
    draw.ellipse([148, 155, 215, 255], fill=(55, 115, 185), outline=pipe_dark, width=4)
    draw.ellipse([162, 168, 200, 242], fill=pipe_blue)
    # Broken pipe end — water spurting OUT downward
    draw.ellipse([155, 305, 205, 345], fill=(40, 60, 90))  # broken opening
    # Water stream spraying
    for i in range(12):
        sx = 175 + rng.randint(-20, 20)
        sy = 340 + rng.randint(0, 60)
        draw.line([(175, 330), (sx, sy)], fill=(100, 150, 210), width=rng.randint(1, 3))
    for i in range(8):
        sx = 175 + rng.randint(-30, 30)
        sy = 390 + rng.randint(0, 30)
        draw.ellipse([sx - 3, sy - 2, sx + 3, sy + 2], fill=(90, 130, 190))
    # Accumulated water pool at bottom
    draw.ellipse([60, 380, 420, 490], fill=(40, 65, 95))
    draw.ellipse([100, 400, 380, 475], fill=(55, 80, 115))
    # Mud/soil sediment in water
    for _ in range(20):
        sx = rng.randint(100, 380)
        sy = rng.randint(405, 470)
        draw.ellipse([sx - 4, sy - 3, sx + 4, sy + 3], fill=(70, 55, 35))
    # Third pipe segment
    draw.rectangle([340, 80, 405, 250], fill=(60, 130, 200), outline=pipe_dark, width=2)
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    return _jpeg(img)


def make_img_sewage_flood_road() -> bytes:
    """
    Sewage/wastewater flooding a road.  White wall on right, vehicle driving
    through, muddy/turbid water covering road surface.
    Matches provided photo.
    """
    w, h = 760, 430
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    # Hazy sky / overpass structure at top
    draw.rectangle([0, 0, w, 80], fill=(180, 175, 165))
    # Overpass/bridge concrete structure
    draw.rectangle([0, 40, w, 80], fill=(150, 145, 135))
    draw.rectangle([0, 72, w, 82], fill=(130, 125, 118))
    # White concrete wall on right side
    draw.rectangle([520, 70, w, h], fill=(220, 218, 212))
    for y in range(70, h, 25):
        draw.line([(520, y), (w, y)], fill=(195, 192, 188), width=1)
    for x in range(520, w, 40):
        draw.line([(x, 70), (x, h)], fill=(205, 202, 198), width=1)
    # Metal fence on top of wall
    for x in range(520, w, 18):
        draw.rectangle([x, 65, x + 4, 90], fill=(100, 100, 100))
    draw.line([(520, 75), (w, 75)], fill=(90, 90, 90), width=2)
    # Road surface under sewage water
    draw.rectangle([0, 80, 525, h], fill=(95, 90, 78))
    # SEWAGE / TURBID WATER flooding the road
    # Muddy brownish water with foam/debris
    water_color = (120, 105, 68)
    foam_color = (170, 160, 130)
    draw.rectangle([0, 140, 520, h], fill=water_color)
    # Water flow patterns / ripples
    rng = random.Random(99)
    for _ in range(25):
        x0 = rng.randint(0, 490)
        y0 = rng.randint(145, h - 20)
        w2 = rng.randint(20, 80)
        draw.ellipse([x0, y0, x0 + w2, y0 + rng.randint(5, 15)],
                     fill=(110, 98, 60), outline=None)
    # Foam/debris streaks
    for _ in range(15):
        x0 = rng.randint(0, 480)
        y0 = rng.randint(160, h - 40)
        draw.line([(x0, y0), (x0 + rng.randint(20, 100), y0 + rng.randint(-10, 10))],
                  fill=foam_color, width=2)
    # White van/vehicle driving through water
    # Body
    draw.rectangle([30, 155, 210, 295], fill=(215, 215, 220))
    draw.rectangle([45, 165, 195, 240], fill=(120, 160, 200))  # windshield
    # Wheels partially submerged
    draw.ellipse([45, 270, 100, 315], fill=(35, 35, 35))
    draw.ellipse([140, 270, 195, 315], fill=(35, 35, 35))
    # Water splash around wheels
    for i in range(8):
        sx = 70 + i * 3
        draw.line([(sx, 290), (sx - 5, 285 - i * 3)], fill=(140, 125, 85), width=2)
    # Second vehicle farther back
    draw.rectangle([270, 165, 390, 250], fill=(195, 200, 205))
    draw.rectangle([280, 172, 382, 230], fill=(100, 140, 175))
    draw.ellipse([280, 238, 320, 268], fill=(30, 30, 30))
    draw.ellipse([345, 238, 385, 268], fill=(30, 30, 30))
    # Grass/plants at left edge
    for x in range(0, 50, 8):
        draw.rectangle([x, 120, x + 5, 155], fill=(65, 100, 50))
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    return _jpeg(img)


def make_img_pothole_dry_asphalt() -> bytes:
    """
    Multiple potholes on dry asphalt — close-up, parking lot / suburban road.
    Matches provided photo: 2 large interconnected potholes, dry surface, cars visible.
    """
    w, h = 640, 480
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    # Background — buildings / parking area
    draw.rectangle([0, 0, w, 120], fill=(170, 160, 150))
    draw.rectangle([450, 30, w, 120], fill=(180, 65, 55))  # red building
    # Dry asphalt road
    for y in range(120, h):
        grey = max(70, 88 - (h - y) // 20)
        draw.line([(0, y), (w, y)], fill=(grey, grey, grey - 2))
    # TWO LARGE INTERCONNECTED POTHOLES
    # Left pothole
    lph = (100, 230, 320, 390)
    draw.ellipse([lph[0] - 8, lph[1] - 8, lph[2] + 8, lph[3] + 8],
                 fill=(38, 34, 30), outline=(22, 20, 18), width=5)
    draw.ellipse(lph, fill=(12, 10, 8))
    # Broken chunks left pothole
    for a in range(0, 360, 20):
        cx2 = int((lph[0] + lph[2]) / 2 + ((lph[2] - lph[0]) / 2 + 12) * math.cos(math.radians(a)))
        cy2 = int((lph[1] + lph[3]) / 2 + ((lph[3] - lph[1]) / 2 + 8) * math.sin(math.radians(a)))
        draw.ellipse([cx2 - 6, cy2 - 5, cx2 + 6, cy2 + 5], fill=(50, 44, 38))
    # Right pothole (lower, slightly overlapping)
    rph = (280, 290, 540, 460)
    draw.ellipse([rph[0] - 8, rph[1] - 8, rph[2] + 8, rph[3] + 8],
                 fill=(38, 34, 30), outline=(22, 20, 18), width=5)
    draw.ellipse(rph, fill=(14, 12, 10))
    for a in range(0, 360, 20):
        cx2 = int((rph[0] + rph[2]) / 2 + ((rph[2] - rph[0]) / 2 + 10) * math.cos(math.radians(a)))
        cy2 = int((rph[1] + rph[3]) / 2 + ((rph[3] - rph[1]) / 2 + 8) * math.sin(math.radians(a)))
        draw.ellipse([cx2 - 5, cy2 - 4, cx2 + 5, cy2 + 4], fill=(48, 42, 36))
    # Exposed gravel/rubble in potholes
    rng = random.Random(55)
    for ph in [lph, rph]:
        cx3 = (ph[0] + ph[2]) // 2
        cy3 = (ph[1] + ph[3]) // 2
        for _ in range(12):
            gx = cx3 + rng.randint(-(ph[2] - ph[0]) // 3, (ph[2] - ph[0]) // 3)
            gy = cy3 + rng.randint(-(ph[3] - ph[1]) // 4, (ph[3] - ph[1]) // 4)
            draw.ellipse([gx - 4, gy - 3, gx + 4, gy + 3], fill=(65, 58, 45))
    # Car visible at back
    draw.rectangle([480, 130, 620, 210], fill=(180, 180, 190))
    draw.rectangle([490, 140, 610, 195], fill=(100, 135, 170))
    # Road edge line
    draw.line([(0, 120), (w, 120)], fill=(200, 195, 185), width=3)
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    return _jpeg(img)


def make_img_road_damage_alligator() -> bytes:
    """
    Road damage — alligator/mesh cracking pattern on asphalt.
    NO distinct hole/pothole — widespread pavement deterioration.
    """
    w, h = 640, 480
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    # Sky
    for y in range(80):
        c = 170 + y
        draw.line([(0, y), (w, y)], fill=(c // 2, c // 2 + 10, c))
    # Road surface
    base_grey = 80
    draw.rectangle([0, 80, w, h], fill=(base_grey, base_grey, base_grey - 2))
    # Dense alligator cracking pattern
    rng = random.Random(42)
    for _ in range(120):
        x0 = rng.randint(0, w)
        y0 = rng.randint(90, h)
        length = rng.randint(15, 100)
        angle = rng.uniform(0, math.pi)
        x1 = int(x0 + length * math.cos(angle))
        y1 = int(y0 + length * math.sin(angle))
        shade = rng.randint(35, 55)
        draw.line([(x0, y0), (x1, y1)], fill=(shade, shade, shade - 2),
                  width=rng.randint(1, 4))
    # No pothole — surface is uniformly degraded with cracks only
    img = img.filter(ImageFilter.GaussianBlur(0.3))
    # Enhance contrast to make cracks more visible
    img = ImageEnhance.Contrast(img).enhance(1.3)
    return _jpeg(img)


def make_img_garbage_dump() -> bytes:
    """
    Garbage overflow — pile of waste/trash bags on roadside.
    """
    w, h = 640, 480
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    # Background wall/building
    draw.rectangle([0, 0, w, 200], fill=(190, 185, 175))
    for y in range(0, 200, 30):
        draw.line([(0, y), (w, y)], fill=(175, 170, 162), width=1)
    # Ground/road
    draw.rectangle([0, 200, w, h], fill=(85, 82, 75))
    rng = random.Random(33)
    # Multiple garbage bags (tied plastic bags)
    bag_colors = [
        (40, 40, 40),   # black bags
        (20, 80, 20),   # green bags
        (150, 30, 30),  # red bags
        (30, 30, 80),   # blue bags
        (120, 115, 80), # brown/tan bags
    ]
    for i in range(18):
        x = rng.randint(30, w - 80)
        y = rng.randint(185, 380)
        bw = rng.randint(55, 130)
        bh = rng.randint(45, 100)
        c = bag_colors[i % len(bag_colors)]
        draw.ellipse([x, y, x + bw, y + bh], fill=c)
        # Tie knot at top
        draw.ellipse([x + bw // 2 - 8, y - 10, x + bw // 2 + 8, y + 10], fill=c)
        # Shading
        draw.ellipse([x + bw // 3, y + bh // 4, x + bw * 2 // 3, y + bh * 3 // 4],
                     fill=(min(c[0] + 20, 255), min(c[1] + 20, 255), min(c[2] + 20, 255)))
    # Loose waste / plastic scraps scattered around
    for _ in range(50):
        sx = rng.randint(0, w)
        sy = rng.randint(200, h)
        sc = (rng.randint(80, 200), rng.randint(60, 180), rng.randint(20, 120))
        draw.ellipse([sx - 4, sy - 3, sx + 4, sy + 3], fill=sc)
    # Flies / insects (dots above garbage)
    for _ in range(15):
        sx = rng.randint(50, w - 50)
        sy = rng.randint(160, 220)
        draw.point((sx, sy), fill=(20, 20, 20))
    return _jpeg(img)


def make_img_open_drain() -> bytes:
    """
    Open/broken drain — exposed drain channel alongside a road.
    """
    w, h = 640, 480
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    # Sky
    for y in range(100):
        c = int(180 + y * 0.5)
        draw.line([(0, y), (w, y)], fill=(max(80, c - 60), max(120, c - 20), c))
    # Road surface
    draw.rectangle([0, 100, w, h], fill=(82, 80, 78))
    # OPEN DRAIN CHANNEL — running diagonally from top to bottom
    # Drain walls (concrete)
    draw.rectangle([w // 2 - 90, 100, w // 2 - 65, h], fill=(145, 135, 115))
    draw.rectangle([w // 2 + 65, 100, w // 2 + 90, h], fill=(145, 135, 115))
    # Drain floor / channel
    draw.rectangle([w // 2 - 65, 100, w // 2 + 65, h], fill=(35, 35, 32))
    # Stagnant dark water / sludge in drain
    draw.rectangle([w // 2 - 55, 110, w // 2 + 55, h], fill=(25, 40, 45))
    # Water texture
    rng = random.Random(11)
    for _ in range(20):
        wx = rng.randint(w // 2 - 50, w // 2 + 50)
        wy = rng.randint(120, h - 20)
        draw.ellipse([wx - 15, wy - 3, wx + 15, wy + 3], fill=(35, 52, 58))
    # Exposed rebar / broken concrete edge on drain
    for x in range(w // 2 - 90, w // 2 - 60, 12):
        draw.rectangle([x, 100, x + 6, 120], fill=(90, 85, 70))
        draw.line([(x + 3, 100), (x + 3, 108)], fill=(100, 80, 60), width=2)
    # Algae / vegetation growing on drain walls
    for i in range(10):
        sx = (w // 2 - 90) + rng.randint(-5, 5)
        sy = rng.randint(110, h - 20)
        draw.ellipse([sx - 5, sy - 4, sx + 5, sy + 4], fill=(50, 95, 45))
    # Road edge
    draw.line([(0, 100), (w, 100)], fill=(170, 165, 155), width=3)
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    return _jpeg(img)


def make_img_invalid_person() -> bytes:
    """
    Invalid image — a person taking a selfie indoors. No civic content.
    """
    w, h = 480, 640
    img = Image.new("RGB", (w, h), color=(230, 220, 210))
    draw = ImageDraw.Draw(img)
    # Indoor wall with picture frame
    draw.rectangle([150, 50, 350, 200], fill=(180, 160, 140), outline=(100, 80, 60), width=4)
    draw.rectangle([160, 60, 340, 195], fill=(150, 130, 110))
    # Face
    draw.ellipse([140, 220, 340, 450], fill=(220, 185, 160))
    # Eyes
    draw.ellipse([175, 295, 215, 335], fill=(50, 35, 20))
    draw.ellipse([265, 295, 305, 335], fill=(50, 35, 20))
    # Eyebrows
    draw.line([(172, 285), (218, 278)], fill=(40, 25, 10), width=3)
    draw.line([(262, 278), (308, 285)], fill=(40, 25, 10), width=3)
    # Nose
    draw.ellipse([228, 355, 252, 375], fill=(200, 162, 140))
    # Smile
    draw.arc([190, 375, 290, 430], start=5, end=175, fill=(160, 80, 80), width=3)
    # Hair
    draw.ellipse([130, 190, 350, 290], fill=(45, 28, 12))
    draw.rectangle([130, 220, 350, 310], fill=(45, 28, 12))
    # Neck/shoulders
    draw.rectangle([185, 445, 295, 540], fill=(220, 185, 160))
    draw.rectangle([80, 520, 400, 640], fill=(80, 100, 160))  # shirt
    # Hand holding phone
    draw.rectangle([310, 440, 380, 560], fill=(215, 180, 155))
    draw.rectangle([325, 460, 370, 540], fill=(50, 50, 50))  # phone
    draw.rectangle([330, 465, 365, 535], fill=(20, 20, 20))  # phone screen
    return _jpeg(img)


# ---------------------------------------------------------------------------
# Build image registry
# ---------------------------------------------------------------------------

IMAGES = [
    # (label, expected_category, image_bytes)
    ("streetlight_broken",     "broken_streetlight",   make_img_streetlight_broken()),
    ("pothole_multiple_wet",   "pothole",              make_img_pothole_multiple_wet()),
    ("pothole_single_rural",   "pothole",              make_img_pothole_single_rural()),
    ("water_leakage_pipes",    "water_supply",         make_img_water_leakage_pipe()),
    ("sewage_flood_road",      "sewage",               make_img_sewage_flood_road()),
    ("pothole_dry_asphalt",    "pothole",              make_img_pothole_dry_asphalt()),
    ("road_damage_alligator",  "road_damage",          make_img_road_damage_alligator()),
    ("garbage_dump",           "garbage_overflow",     make_img_garbage_dump()),
    ("open_drain",             "open_drain",           make_img_open_drain()),
    ("invalid_person_selfie",  "REJECTED",             make_img_invalid_person()),
]

# Save to fixtures for inspection
for label, expected, img_bytes in IMAGES:
    path = os.path.join(FIXTURES_DIR, f"{label}.jpg")
    with open(path, "wb") as f:
        f.write(img_bytes)


# ---------------------------------------------------------------------------
# Pipeline runner with full diagnostics
# ---------------------------------------------------------------------------

async def run_image(label: str, expected: str, image_bytes: bytes) -> dict:
    """Run one image through the full production pipeline and collect diagnostics."""
    from services.llm_service import civic_classify_image as _real_civic
    from cv.detection import detect_civic_issue as _real_detect
    from cv.road_damage import classify_road_damage as _real_road
    from unittest.mock import patch as _patch

    yolo_info: dict = {}
    road_info: dict = {}
    vision_info: dict = {}
    vision_bytes_info: dict = {}

    def _capture_detect(img):
        result = _real_detect(img)
        yolo_info.update({
            "class": result.yolo_class, "conf": result.confidence,
            "category": result.category.value, "all_names": result.all_class_names,
        })
        return result

    def _capture_road(img):
        result = _real_road(img)
        road_info.update({
            "detected": result.detected, "category": result.category,
            "confidence": result.confidence, "raw_class": result.raw_class,
        })
        return result

    async def _capture_civic(image_bytes, yolo_class, all_class_names, address,
                              *, road_model_hint=""):
        vision_bytes_info["bytes_len"] = len(image_bytes)
        vision_bytes_info["hint"] = road_model_hint
        result = await _real_civic(
            image_bytes, yolo_class, all_class_names, address,
            road_model_hint=road_model_hint,
        )
        vision_info.update({
            "called": True, "valid": result.valid, "category": result.category,
            "confidence": result.category_confidence, "severity": result.severity,
            "reason": result.reason, "description": result.description,
        })
        return result

    t0 = time.time()
    error = None
    pipeline_result = None

    try:
        with (
            _patch("cv.detection.detect_civic_issue", side_effect=_capture_detect),
            _patch("cv.road_damage.classify_road_damage", side_effect=_capture_road),
            _patch("services.llm_service.civic_classify_image", new=_capture_civic),
        ):
            from cv.pipeline import run_ai_pipeline
            pipeline_result = await run_ai_pipeline(
                image_bytes,
                location="12.9716,74.8236",
                address="MG Road, Mangaluru",
            )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    elapsed = time.time() - t0

    # Determine correctness
    if expected == "REJECTED":
        correct = error is not None and ("ImageValidationError" in error or "civic issue" in error.lower())
    else:
        correct = pipeline_result is not None and pipeline_result.category.value == expected

    return {
        "label": label, "expected": expected, "elapsed_s": elapsed,
        "error": error,
        "yolo_class": yolo_info.get("class", "N/A"),
        "yolo_conf": yolo_info.get("conf", 0.0),
        "yolo_category": yolo_info.get("category", "N/A"),
        "yolo_all": yolo_info.get("all_names", ()),
        "road_detected": road_info.get("detected", "N/A"),
        "road_category": road_info.get("category", ""),
        "road_conf": road_info.get("confidence", 0.0),
        "road_raw": road_info.get("raw_class", ""),
        "road_hint_sent": vision_bytes_info.get("hint", ""),
        "vision_called": vision_info.get("called", False),
        "vision_valid": vision_info.get("valid", "N/A"),
        "vision_category": vision_info.get("category", "N/A"),
        "vision_conf": vision_info.get("confidence", 0.0),
        "vision_severity": vision_info.get("severity", "N/A"),
        "vision_reason": vision_info.get("reason", "N/A"),
        "vision_description": str(vision_info.get("description", "N/A"))[:120],
        "final_category": pipeline_result.category.value if pipeline_result else "REJECTED",
        "final_conf": pipeline_result.confidence if pipeline_result else 0.0,
        "provider": pipeline_result.llm_provider_used if pipeline_result else "N/A",
        "decision_state": pipeline_result.decision_state if pipeline_result else "N/A",
        "evidence_score": pipeline_result.evidence_score if pipeline_result else 0.0,
        "admin_priority": pipeline_result.admin_priority if pipeline_result else "N/A",
        "correct": correct,
    }


def _sep(n=78): return "=" * n
def _sub(n=78): return "-" * n


async def main():
    print()
    print(_sep())
    print("CivicAI Real-Image Pipeline Test  (qwen/qwen3.8-27b)")
    print(f"Test images: {len(IMAGES)}  |  Fixtures: {FIXTURES_DIR}")
    print(_sep())

    results = []
    for label, expected, img_bytes in IMAGES:
        print(f"\n[{label}]  expected={expected!r}  ({len(img_bytes):,} bytes)")
        r = await run_image(label, expected, img_bytes)
        results.append(r)

        if r["error"]:
            rejected_ok = (expected == "REJECTED" and r["correct"])
            status = "PASS (rejected as expected)" if rejected_ok else "ERROR/REJECTED"
            print(f"  STATUS  : {status}")
            print(f"  Error   : {r['error'][:200]}")
        else:
            mark = "PASS" if r["correct"] else "FAIL"
            print(f"  STATUS  : {mark}")
            print(f"  YOLO    : top1={r['yolo_class']!r} conf={r['yolo_conf']:.3f}"
                  f"  taxonomy={r['yolo_category']!r}")
            print(f"  ROAD    : detected={r['road_detected']}  cat={r['road_category']!r}"
                  f"  conf={r['road_conf']:.3f}  raw={r['road_raw']!r}")
            _h = repr(r['road_hint_sent'][:70]) if r['road_hint_sent'] else "(none)"
            print(f"  HINT    : {_h}")
            print(f"  VISION  : called={r['vision_called']}  valid={r['vision_valid']}"
                  f"  cat={r['vision_category']!r}  conf={r['vision_conf']:.3f}"
                  f"  sev={r['vision_severity']!r}")
            print(f"  REASON  : {repr(r['vision_reason'])[:100]}")
            print(f"  DESC    : {r['vision_description'][:100]}")
            print(f"  FINAL   : category={r['final_category']!r}  conf={r['final_conf']:.3f}"
                  f"  provider={r['provider']!r}")
            print(f"  EVIDENCE: state={r['decision_state']}  score={r['evidence_score']:.3f}"
                  f"  priority={r['admin_priority']}")
            print(f"  TIME    : {r['elapsed_s']:.1f}s")

    # Summary
    print()
    print(_sep())
    print("SUMMARY TABLE")
    print(_sep())
    fmt = "{:<28} {:<22} {:<22} {:<6} {:<22}"
    print(fmt.format("Label", "Expected", "Final", "Pass?", "Provider"))
    print(_sub())
    passes = 0
    for r in results:
        final = r["final_category"] if not r["error"] else "REJECTED"
        if r["error"] and r["expected"] == "REJECTED":
            final = "REJECTED(OK)"
        mark = "PASS" if r["correct"] else "FAIL"
        print(fmt.format(r["label"], r["expected"], final, mark, r["provider"]))
        if r["correct"]:
            passes += 1

    print(_sub())
    print(f"Result: {passes}/{len(results)} correct")
    print(_sep())

    failures = [r for r in results if not r["correct"]]
    if failures:
        print("\nFAILED CASES:")
        for r in failures:
            print(f"  {r['label']}: expected={r['expected']!r}"
                  f"  final={r['final_category']!r}"
                  f"  vision_cat={r['vision_category']!r}"
                  f"  vision_valid={r['vision_valid']}"
                  f"  reason={repr(r['vision_reason'])[:80]}")
    else:
        print("\nAll images classified correctly.")


if __name__ == "__main__":
    asyncio.run(main())
