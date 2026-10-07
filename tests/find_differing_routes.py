import os
import sys
import datetime

sys.path.insert(0, os.path.abspath("."))
from backend.routing import get_routing_engine

engine = get_routing_engine()
dt_3pm = datetime.datetime(2026, 10, 8, 15, 0)
exposure_map = engine.compute_edge_exposure(dt_3pm)

# Find edges that are exposed vs shaded
exposed_count = sum(1 for e in engine.edges if exposure_map.get(e["edge_id"], 1.0) > 0.4)
shaded_count = sum(1 for e in engine.edges if exposure_map.get(e["edge_id"], 1.0) <= 0.4)
print(f"Total edges: {len(engine.edges)}, Shaded edges: {shaded_count}, Exposed edges: {exposed_count}")

# Test multiple POI pairs
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
        except Exception as ex:
            pass

print(f"Found {len(differing_pairs)} pairs with different shade vs shortest paths:")
for p1_name, p2_name, comp in differing_pairs[:10]:
    print(f"  * {p1_name} -> {p2_name}: +{comp['extra_distance_m']}m extra distance, saves {comp['sun_minutes_saved']} sun-mins!")
