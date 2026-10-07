import datetime
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

from backend.geo_shadows import calculate_solar_position, get_shadow_engine

print("=== Chhaya Solar & Shadow Verification ===")
for hour, minute in [(9, 0), (12, 0), (15, 0), (16, 30)]:
    dt = datetime.datetime(2026, 10, 8, hour, minute)
    sol = calculate_solar_position(dt)
    print(f"{hour:02d}:{minute:02d} IST -> Elevation: {sol['elevation']} deg, Azimuth: {sol['azimuth']} deg, Shadow factor: {sol['shadow_factor']}x")

print("\nComputing 3:00 PM shadows...")
engine = get_shadow_engine()
t0 = datetime.datetime.now()
res_3pm = engine.compute_shadows(datetime.datetime(2026, 10, 8, 15, 0))
elapsed = (datetime.datetime.now() - t0).total_seconds()

print(f"Done in {elapsed:.3f}s!")
print(f"Extracted {len(res_3pm['features'])} shadow polygons.")
print(f"Properties: {res_3pm['properties']}")
