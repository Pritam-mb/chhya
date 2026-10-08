import json
import os
import sys
sys.path.insert(0, os.path.abspath("."))
import random
import datetime
from backend.routing import get_routing_engine
from backend.geo_shadows import calculate_solar_position

def main():
    print("Initializing Routing Engine...")
    engine = get_routing_engine()
    
    times_to_test = ["09:00", "15:00", "16:00"]
    results_pois = {t: [] for t in times_to_test}
    results_nodes = {t: [] for t in times_to_test}
    
    # 1. Test all pairs of POIs
    pois = engine.pois
    print(f"Testing {len(pois)} POIs...")
    for t in times_to_test:
        for p1 in pois:
            for p2 in pois:
                if p1["id"] == p2["id"]:
                    continue
                try:
                    res = engine.plan_route(
                        origin_query=p1["id"],
                        destination_query=p2["id"],
                        depart_time_str=t,
                        sun_tolerance="low",
                        speed_kmh=3.0
                    )
                    comp = res["comparison"]
                    if comp["extra_distance_m"] >= 0:
                        results_pois[t].append({
                            "origin": p1["name"],
                            "destination": p2["name"],
                            "extra_distance_m": comp["extra_distance_m"],
                            "sun_minutes_saved": comp["sun_minutes_saved"],
                            "trade_off": res["trade_off_sentence"]
                        })
                except Exception as e:
                    pass

        # Sort by most sun minutes saved
        results_pois[t].sort(key=lambda x: x["sun_minutes_saved"], reverse=True)
        
    os.makedirs("results", exist_ok=True)
    with open("results/route_search_pois.json", "w") as f:
        json.dump(results_pois, f, indent=2)

    # 2. Test random node pairs 500-1200m apart
    print("Testing random node pairs...")
    nodes = list(engine.nodes.values())
    random.seed(42)
    node_pairs = []
    
    # Simple distance in degrees approx to meters (1 deg lat ~ 111km, 1 deg lon at 22.5N ~ 102km)
    for _ in range(5000):
        n1 = random.choice(nodes)
        n2 = random.choice(nodes)
        dx = (n1["lon"] - n2["lon"]) * 102000
        dy = (n1["lat"] - n2["lat"]) * 111000
        dist = (dx**2 + dy**2)**0.5
        if 500 <= dist <= 1200:
            node_pairs.append((n1, n2))
            if len(node_pairs) >= 332:
                break
                
    for t in times_to_test:
        for n1, n2 in node_pairs:
            try:
                res = engine.plan_route(
                    origin_query=f"{n1['lat']},{n1['lon']}",
                    destination_query=f"{n2['lat']},{n2['lon']}",
                    depart_time_str=t,
                    sun_tolerance="low",
                    speed_kmh=3.0
                )
                comp = res["comparison"]
                results_nodes[t].append({
                    "origin_id": n1["id"],
                    "destination_id": n2["id"],
                    "extra_distance_m": comp["extra_distance_m"],
                    "sun_minutes_saved": comp["sun_minutes_saved"]
                })
            except Exception:
                pass
                
        results_nodes[t].sort(key=lambda x: x["sun_minutes_saved"], reverse=True)

    with open("results/route_search_nodes.json", "w") as f:
        json.dump(results_nodes, f, indent=2)
        
    print("Search complete. Check results in results/")

if __name__ == "__main__":
    main()
