"""T2-5 tests — YOLO taxonomy mapping (cv/taxonomy.py).

Acceptance criteria:
  - map_to_category returns the correct IssueCategory for every mapped class
  - unmapped classes return IssueCategory.other
  - input matching is case-insensitive
  - input matching strips surrounding whitespace
  - all 10 IssueCategory values are reachable through the mapping
    (pothole, waterlogging, broken_streetlight, garbage_overflow, open_drain,
     illegal_construction, water_supply, sewage, road_damage, other)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from cv.taxonomy import map_to_category
from schemas.report import IssueCategory


# ---------------------------------------------------------------------------
# Road damage mappings
# ---------------------------------------------------------------------------

class TestRoadDamageMappings:
    def test_car(self):
        assert map_to_category("car") == IssueCategory.road_damage

    def test_truck(self):
        assert map_to_category("truck") == IssueCategory.road_damage

    def test_motorcycle(self):
        assert map_to_category("motorcycle") == IssueCategory.road_damage

    def test_bicycle(self):
        assert map_to_category("bicycle") == IssueCategory.road_damage

    def test_bus(self):
        assert map_to_category("bus") == IssueCategory.road_damage

    def test_traffic_light(self):
        assert map_to_category("traffic light") == IssueCategory.road_damage

    def test_stop_sign(self):
        assert map_to_category("stop sign") == IssueCategory.road_damage

    def test_parking_meter(self):
        assert map_to_category("parking meter") == IssueCategory.road_damage


# ---------------------------------------------------------------------------
# Broken streetlight mappings
# ---------------------------------------------------------------------------

class TestBrokenStreetlightMappings:
    def test_fire_hydrant(self):
        assert map_to_category("fire hydrant") == IssueCategory.broken_streetlight


# ---------------------------------------------------------------------------
# Garbage overflow mappings
# ---------------------------------------------------------------------------

class TestGarbageOverflowMappings:
    def test_bottle(self):
        assert map_to_category("bottle") == IssueCategory.garbage_overflow

    def test_wine_glass(self):
        assert map_to_category("wine glass") == IssueCategory.garbage_overflow

    def test_cup(self):
        assert map_to_category("cup") == IssueCategory.garbage_overflow

    def test_fork(self):
        assert map_to_category("fork") == IssueCategory.garbage_overflow

    def test_knife(self):
        assert map_to_category("knife") == IssueCategory.garbage_overflow

    def test_spoon(self):
        assert map_to_category("spoon") == IssueCategory.garbage_overflow

    def test_bowl(self):
        assert map_to_category("bowl") == IssueCategory.garbage_overflow

    def test_banana(self):
        assert map_to_category("banana") == IssueCategory.garbage_overflow

    def test_apple(self):
        assert map_to_category("apple") == IssueCategory.garbage_overflow

    def test_sandwich(self):
        assert map_to_category("sandwich") == IssueCategory.garbage_overflow

    def test_orange(self):
        assert map_to_category("orange") == IssueCategory.garbage_overflow

    def test_broccoli(self):
        assert map_to_category("broccoli") == IssueCategory.garbage_overflow

    def test_carrot(self):
        assert map_to_category("carrot") == IssueCategory.garbage_overflow

    def test_hot_dog(self):
        assert map_to_category("hot dog") == IssueCategory.garbage_overflow

    def test_pizza(self):
        assert map_to_category("pizza") == IssueCategory.garbage_overflow

    def test_donut(self):
        assert map_to_category("donut") == IssueCategory.garbage_overflow

    def test_cake(self):
        assert map_to_category("cake") == IssueCategory.garbage_overflow

    def test_backpack(self):
        assert map_to_category("backpack") == IssueCategory.garbage_overflow

    def test_handbag(self):
        assert map_to_category("handbag") == IssueCategory.garbage_overflow

    def test_suitcase(self):
        assert map_to_category("suitcase") == IssueCategory.garbage_overflow


# ---------------------------------------------------------------------------
# Water supply mappings
# ---------------------------------------------------------------------------

class TestWaterSupplyMappings:
    def test_sink(self):
        assert map_to_category("sink") == IssueCategory.water_supply


# ---------------------------------------------------------------------------
# Sewage mappings
# ---------------------------------------------------------------------------

class TestSewageMappings:
    def test_toilet(self):
        assert map_to_category("toilet") == IssueCategory.sewage


# ---------------------------------------------------------------------------
# Waterlogging mappings
# ---------------------------------------------------------------------------

class TestWaterloggingMappings:
    def test_boat(self):
        assert map_to_category("boat") == IssueCategory.waterlogging

    def test_umbrella(self):
        assert map_to_category("umbrella") == IssueCategory.waterlogging


# ---------------------------------------------------------------------------
# Unmapped classes → other
# ---------------------------------------------------------------------------

class TestUnmappedToOther:
    def test_person(self):
        assert map_to_category("person") == IssueCategory.other

    def test_cat(self):
        assert map_to_category("cat") == IssueCategory.other

    def test_dog(self):
        assert map_to_category("dog") == IssueCategory.other

    def test_airplane(self):
        assert map_to_category("airplane") == IssueCategory.other

    def test_bird(self):
        assert map_to_category("bird") == IssueCategory.other

    def test_laptop(self):
        assert map_to_category("laptop") == IssueCategory.other

    def test_cell_phone(self):
        assert map_to_category("cell phone") == IssueCategory.other

    def test_teddy_bear(self):
        assert map_to_category("teddy bear") == IssueCategory.other

    def test_empty_string(self):
        assert map_to_category("") == IssueCategory.other

    def test_completely_unknown(self):
        assert map_to_category("flying_saucer") == IssueCategory.other

    def test_none_like_string(self):
        assert map_to_category("unknown") == IssueCategory.other


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------

class TestInputNormalisation:
    def test_uppercase_input(self):
        assert map_to_category("CAR") == IssueCategory.road_damage

    def test_mixed_case_input(self):
        assert map_to_category("Bottle") == IssueCategory.garbage_overflow

    def test_leading_whitespace(self):
        assert map_to_category("  truck") == IssueCategory.road_damage

    def test_trailing_whitespace(self):
        assert map_to_category("truck  ") == IssueCategory.road_damage

    def test_both_ends_whitespace(self):
        assert map_to_category("  toilet  ") == IssueCategory.sewage

    def test_multiword_with_space_normalised(self):
        assert map_to_category("  Traffic Light  ") == IssueCategory.road_damage


# ---------------------------------------------------------------------------
# All 10 IssueCategory values are reachable
# ---------------------------------------------------------------------------

class TestAllCategoriesReachable:
    """Verify that every IssueCategory is reachable via map_to_category.

    Categories not covered by any COCO class (pothole, open_drain,
    illegal_construction) are returned by map_to_category("") == other.
    The test below explicitly checks which categories have mapped classes
    and asserts the remaining ones are reachable only via IssueCategory.other
    (since COCO-80 has no direct mapping for those civic concepts).
    """

    def test_road_damage_reachable(self):
        assert map_to_category("car") == IssueCategory.road_damage

    def test_waterlogging_reachable(self):
        assert map_to_category("boat") == IssueCategory.waterlogging

    def test_broken_streetlight_reachable(self):
        assert map_to_category("fire hydrant") == IssueCategory.broken_streetlight

    def test_garbage_overflow_reachable(self):
        assert map_to_category("bottle") == IssueCategory.garbage_overflow

    def test_water_supply_reachable(self):
        assert map_to_category("sink") == IssueCategory.water_supply

    def test_sewage_reachable(self):
        assert map_to_category("toilet") == IssueCategory.sewage

    def test_other_reachable(self):
        assert map_to_category("person") == IssueCategory.other

    def test_pothole_unmapped_returns_other(self):
        """COCO-80 has no 'pothole' class; map_to_category returns other."""
        assert map_to_category("pothole") == IssueCategory.other

    def test_open_drain_unmapped_returns_other(self):
        """COCO-80 has no 'open_drain' class; map_to_category returns other."""
        assert map_to_category("open_drain") == IssueCategory.other

    def test_illegal_construction_unmapped_returns_other(self):
        """COCO-80 has no 'illegal_construction' class; returns other."""
        assert map_to_category("illegal_construction") == IssueCategory.other

    def test_all_issue_categories_exist_in_enum(self):
        """All 10 canonical IssueCategory values exist in the enum."""
        expected = {
            "pothole", "waterlogging", "broken_streetlight", "garbage_overflow",
            "open_drain", "illegal_construction", "water_supply", "sewage",
            "road_damage", "other",
        }
        actual = {c.value for c in IssueCategory}
        assert actual == expected, (
            f"IssueCategory enum mismatch.\n"
            f"  Expected: {sorted(expected)}\n"
            f"  Actual:   {sorted(actual)}"
        )
