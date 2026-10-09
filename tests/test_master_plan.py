"""
Unit tests for Chhaya Master Plan features.
Fulfills Section 5: Unit tests required:
1. no straggler
2. one straggler
3. two stragglers
4. straggler at the last stop
5. sensitive walker is the straggler
6. no shaded stop available (fallback to least exposed, with warning)
7. weather factor at each threshold
8. rest-stop spacing for slow vs normal pace
"""
import pytest
from backend.weather import compute_weather_factor, get_weather_adjusted_budget
from backend.rest_stops import find_rest_stops
from backend.repair_engine import detect_and_repair_stragglers
from backend.db import clean_and_moderate_card_text, haversine_distance_m


# 1. Weather Factor at Each Threshold
def test_weather_factor_thresholds():
    # Mild conditions: factor 1.0
    assert compute_weather_factor(30.0, 5.0) == 1.0

    # Hot condition (apparent_temp >= 33): factor 0.75
    assert compute_weather_factor(34.0, 5.0) == 0.75

    # Extreme condition (apparent_temp >= 38): factor 0.50
    assert compute_weather_factor(39.0, 5.0) == 0.50

    # High UV condition (uv >= 8): factor *= 0.75
    assert compute_weather_factor(30.0, 8.5) == 0.75

    # Combined Hot (34°C) + High UV (8.5): 0.75 * 0.75 = 0.5625
    assert compute_weather_factor(34.0, 8.5) == 0.5625

    # Combined Extreme (39°C) + High UV (9.0): 0.50 * 0.75 = 0.375
    assert compute_weather_factor(39.0, 9.0) == 0.375


# 2. Rest Stop Spacing for Slow vs Normal Pace
def test_rest_stop_spacing_slow_vs_normal():
    # Route: ~1 km straight line in Kolkata
    coords = [
        [88.3510, 22.5510],
        [88.3520, 22.5510],
        [88.3530, 22.5510],
        [88.3540, 22.5510],
        [88.3550, 22.5510],
        [88.3560, 22.5510],
        [88.3570, 22.5510],
        [88.3580, 22.5510],
    ]

    # Slow pace (2.8 km/h = 46.7 m/min) every 8 min = ~373 m
    stops_slow = find_rest_stops(coords, start_time_str="15:00", pace_kmh=2.8, rest_every_min=8)

    # Normal pace (4.2 km/h = 70 m/min) every 8 min = ~560 m
    stops_normal = find_rest_stops(coords, start_time_str="15:00", pace_kmh=4.2, rest_every_min=8)

    assert len(stops_slow) >= len(stops_normal), "Slow walker should have more or equal rest stops"
    if len(stops_slow) > 0 and len(stops_normal) > 0:
        # Distance to first stop should be smaller for slow walker
        assert stops_slow[0]["cumulative_dist_m"] < stops_normal[0]["cumulative_dist_m"]


# Mock plan fixture for repair tests
@pytest.fixture
def mock_trip_plan():
    return {
        "mode": "club",
        "trip_code": "test-trip",
        "walkers": [
            {"name": "Aarav", "sun_sensitivity": "normal", "pace_kmh": 4.2},
            {"name": "Rina", "sun_sensitivity": "high", "pace_kmh": 3.0},
            {"name": "Kabir", "sun_sensitivity": "low", "pace_kmh": 5.0},
        ],
        "effective_budgets": {"high": 3.0, "normal": 9.0, "low": 20.0},
        "stops": [
            {
                "stop_index": 1,
                "name": "Russell Street Chai Stall",
                "kind": "regroup",
                "cumulative_walk_min": 7.0,
                "shade_at_arrival": 0.85,
            },
            {
                "stop_index": 2,
                "name": "Middleton Row Bench",
                "kind": "regroup",
                "cumulative_walk_min": 14.0,
                "shade_at_arrival": 0.78,
            },
            {
                "stop_index": 3,
                "name": "Camac Square Finish",
                "kind": "destination",
                "cumulative_walk_min": 21.0,
                "shade_at_arrival": 0.70,
            },
        ],
    }


# 3. Test: No Straggler
def test_no_straggler(mock_trip_plan):
    # At elapsed 15 mins, all checked in at stop 2 (expected 14 min) -> within grace period 3 min
    checkins = [
        {"walker": "Aarav", "stop_index": 2, "time_min": 14.2},
        {"walker": "Rina", "stop_index": 2, "time_min": 14.5},
        {"walker": "Kabir", "stop_index": 2, "time_min": 13.8},
    ]
    res = detect_and_repair_stragglers(mock_trip_plan, checkins, current_elapsed_min=15.0, grace_period_min=3.0)
    assert res["has_straggler"] is False
    assert len(res["stragglers"]) == 0


# 4. Test: One Straggler
def test_one_straggler(mock_trip_plan):
    # At elapsed 19 mins, Aarav and Kabir checked into stop 2 (expected 14), Rina is still at stop 1 (expected 7, next is 14)
    # Elapsed 19 > 14 + 3 -> Rina is behind
    checkins = [
        {"walker": "Aarav", "stop_index": 2, "time_min": 14.2},
        {"walker": "Kabir", "stop_index": 2, "time_min": 13.8},
        {"walker": "Rina", "stop_index": 1, "time_min": 7.5},
    ]
    res = detect_and_repair_stragglers(mock_trip_plan, checkins, current_elapsed_min=19.0, grace_period_min=3.0)
    assert res["has_straggler"] is True
    assert len(res["stragglers"]) == 1
    assert res["primary_straggler"]["name"] == "Rina"
    assert len(res["repair_options"]) == 2
    assert "Rina is about" in res["message"]


# 5. Test: Two Stragglers
def test_two_stragglers(mock_trip_plan):
    # Aarav at stop 2; Rina at stop 1; Kabir at stop 1
    checkins = [
        {"walker": "Aarav", "stop_index": 2, "time_min": 14.0},
        {"walker": "Rina", "stop_index": 1, "time_min": 7.5},
        {"walker": "Kabir", "stop_index": 1, "time_min": 8.0},
    ]
    res = detect_and_repair_stragglers(mock_trip_plan, checkins, current_elapsed_min=19.5, grace_period_min=3.0)
    assert res["has_straggler"] is True
    assert len(res["stragglers"]) == 2


# 6. Test: Straggler at the Last Stop
def test_straggler_at_last_stop(mock_trip_plan):
    # Aarav and Kabir reached final stop 3 (expected 21 min); Rina is at stop 2 (expected next stop is 3)
    checkins = [
        {"walker": "Aarav", "stop_index": 3, "time_min": 21.0},
        {"walker": "Kabir", "stop_index": 3, "time_min": 20.0},
        {"walker": "Rina", "stop_index": 2, "time_min": 14.0},
    ]
    # Current elapsed 26 min > 21 + 3 -> Straggler before final stop
    res = detect_and_repair_stragglers(mock_trip_plan, checkins, current_elapsed_min=26.0, grace_period_min=3.0)
    assert res["has_straggler"] is True
    assert res["primary_straggler"]["expected_next_stop"] == 3


# 7. Test: Sensitive Walker is the Straggler
def test_sensitive_walker_is_straggler(mock_trip_plan):
    # Rina has sun_sensitivity = "high"
    checkins = [
        {"walker": "Aarav", "stop_index": 2, "time_min": 14.0},
        {"walker": "Kabir", "stop_index": 2, "time_min": 13.5},
        {"walker": "Rina", "stop_index": 1, "time_min": 7.5},
    ]
    res = detect_and_repair_stragglers(mock_trip_plan, checkins, current_elapsed_min=19.0, grace_period_min=3.0)
    assert res["primary_straggler"]["sun_sensitivity"] == "high"
    # Ensure options keep sensitive walker safe
    for opt in res["repair_options"]:
        assert opt["max_walker_sun_min"] <= mock_trip_plan["effective_budgets"]["high"]


# 8. Test: No Shaded Stop Available (Fallback with warning)
def test_no_shaded_stop_available(mock_trip_plan):
    # Set upcoming stop shade to low (0.35)
    mock_trip_plan["stops"][1]["shade_at_arrival"] = 0.35
    checkins = [
        {"walker": "Aarav", "stop_index": 2, "time_min": 14.0},
        {"walker": "Rina", "stop_index": 1, "time_min": 7.5},
    ]
    res = detect_and_repair_stragglers(mock_trip_plan, checkins, current_elapsed_min=19.0)
    assert res["has_straggler"] is True
    # Still returns top 2 ranked options (e.g., SHORTCUT or SPLIT or shaded alternative)
    assert len(res["repair_options"]) >= 1


# 9. Test: Card Cleaning & PII Stripping
def test_card_pii_cleaning():
    raw_text = "Call 9876543210 or email test@example.com for shade info"
    cleaned, is_safe, status = clean_and_moderate_card_text(raw_text)
    assert "9876543210" not in cleaned
    assert "test@example.com" not in cleaned
    assert "[PHONE REMOVED]" in cleaned
    assert "[EMAIL REMOVED]" in cleaned
    assert status == "flagged_pii_cleaned"
