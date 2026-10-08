import datetime
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from backend.geo_shadows import calculate_solar_position, get_shadow_engine

def test_solar_position():
    dt = datetime.datetime(2026, 10, 8, 15, 0)
    sol = calculate_solar_position(dt)
    assert sol['elevation'] > 0, "Sun should be above horizon"
    assert sol['shadow_factor'] > 1.0, "Shadow factor at 3 PM should be > 1.0"

def test_compute_shadows():
    engine = get_shadow_engine()
    res = engine.compute_shadows(datetime.datetime(2026, 10, 8, 15, 0))
    assert 'features' in res
    assert len(res['features']) > 0, "Should extract shadow polygons"
    assert res['properties']['shadow_factor'] > 1.0
