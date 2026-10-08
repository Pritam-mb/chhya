import os
import sys

sys.path.insert(0, os.path.abspath("."))
from backend.routing import get_routing_engine

def test_routing_engine_plan():
    engine = get_routing_engine()
    # Test Scenario 1 (The 3 PM Demo Walk): Dadu to Belle Vue Clinic
    res = engine.plan_route(
        origin_query="home",
        destination_query="clinic",
        depart_time_str="15:00",
        sun_tolerance="low",
        speed_kmh=3.0
    )
    
    assert res["origin"]["name"] == "Dadu's Residence (Middleton Row)", "Origin should be resolved correctly"
    assert res["destination"]["name"] == "Belle Vue Clinic", "Destination should be resolved correctly"
    
    shortest_sun = res["shortest_route"]["sun_minutes"]
    shade_sun = res["shade_route"]["sun_minutes"]
    assert shade_sun <= shortest_sun, "Shaded route should have fewer or equal sun-minutes than shortest route"
    
    # Check that trade-off sentence is generated
    assert "trade_off_sentence" in res
    assert len(res["trade_off_sentence"]) > 0

def test_high_noon_note():
    engine = get_routing_engine()
    res = engine.plan_route(
        origin_query="home",
        destination_query="clinic",
        depart_time_str="12:00",
        sun_tolerance="low",
        speed_kmh=3.0
    )
    assert res["solar_info"]["is_high_noon"] is True
    assert "sun is overhead" in res["trade_off_sentence"]
