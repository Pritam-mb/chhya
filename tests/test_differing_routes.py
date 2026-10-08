import os
import sys
import datetime
import pytest

sys.path.insert(0, os.path.abspath("."))
from backend.routing import get_routing_engine

def test_differing_routes():
    engine = get_routing_engine()
    dt_3pm = datetime.datetime(2026, 10, 8, 15, 0)
    exposure_map = engine.compute_edge_exposure(dt_3pm)

    exposed_count = sum(1 for e in engine.edges if exposure_map.get(e["edge_id"], 1.0) > 0.4)
    shaded_count = sum(1 for e in engine.edges if exposure_map.get(e["edge_id"], 1.0) <= 0.4)
    
    assert shaded_count > 0, "There should be shaded edges at 3 PM"

    pois = engine.pois
    differing_pairs = []

    for p1 in pois:
        for p2 in pois:
            if p1["id"] == p2["id"]:
                continue
            try:
                res = engine.plan_route(p1["id"], p2["id"], "15:00", sun_tolerance="low", speed_kmh=3.0)
                comp = res["comparison"]
                if comp["extra_distance_m"] > 0 or comp["sun_minutes_saved"] > 0.1:
                    differing_pairs.append((p1["name"], p2["name"], comp))
            except Exception:
                pass

    assert len(differing_pairs) > 0, "Should find pairs with differing shade vs shortest paths"
