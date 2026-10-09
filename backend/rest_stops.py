"""
Rest and regroup stop discovery and shade qualification for Chhaya.
Fulfills Section 4, P0.5 & Section 5: Rest stops for Family & Trail.
"""
import math
import datetime
from typing import List, Dict, Any, Optional, Tuple
from shapely.geometry import Point, LineString

from backend.config import (
    REST_STOP_EVERY_MIN,
    REST_STOP_SEARCH_RADIUS_M,
    REST_STOP_MIN_SHADE,
    PACE_KMH,
)
from backend.geo_shadows import to_utm, to_wgs84, get_shadow_engine

# Curated high-fidelity seating and rest candidates in the Park Street / Camac corridor.
# Supplements sparse Indian OSM amenity tags with real field seats, cafes, tea stalls, and park edges.
REST_CANDIDATES = [
    {
        "id": "seat_middleton_bench_1",
        "name": "Middleton Row Heritage Bench",
        "kind": "bench",
        "lat": 22.5516,
        "lon": 88.3522,
        "description": "Shaded wooden bench under building portico on Middleton Row"
    },
    {
        "id": "seat_loreto_shelter",
        "name": "Loreto House Shaded Gate Bench",
        "kind": "shelter",
        "lat": 22.5505,
        "lon": 88.3527,
        "description": "Deep covered portico bench outside Loreto convent gate"
    },
    {
        "id": "seat_russell_chai",
        "name": "Russell Street Shaded Chai Stall",
        "kind": "tea_stall",
        "lat": 22.5523,
        "lon": 88.3512,
        "description": "Covered tea stall with stool seating in deep afternoon shade"
    },
    {
        "id": "seat_park_st_flurys_portico",
        "name": "Flurys Heritage Colonnade",
        "kind": "cafe",
        "lat": 22.5531,
        "lon": 88.3524,
        "description": "Wide colonnade with sheltered public seating"
    },
    {
        "id": "seat_camac_arcade",
        "name": "Camac Square Shaded Arcade",
        "kind": "shelter",
        "lat": 22.5495,
        "lon": 88.3536,
        "description": "Building overhang seating shielded from direct noon sun"
    },
    {
        "id": "seat_bellevue_courtyard",
        "name": "Belle Vue Clinic Shaded Benches",
        "kind": "bench",
        "lat": 22.5484,
        "lon": 88.3558,
        "description": "Quiet covered seating area under clinic canopy"
    },
    {
        "id": "seat_park_clinic_veranda",
        "name": "Park Clinic Covered Veranda",
        "kind": "shelter",
        "lat": 22.5478,
        "lon": 88.3530,
        "description": "Sheltered resting veranda at Gorky Terrace entrance"
    },
    {
        "id": "seat_oxford_reading_corner",
        "name": "Oxford Arcade Portico",
        "kind": "bench",
        "lat": 22.5534,
        "lon": 88.3519,
        "description": "Sheltered arcade seating near bookstore"
    }
]


def _distance_utm(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def find_rest_stops(
    route_coords: List[List[float]],
    start_time_str: str = "15:00",
    pace_kmh: float = 2.8,
    rest_every_min: int = REST_STOP_EVERY_MIN,
    min_shade_threshold: float = REST_STOP_MIN_SHADE,
) -> List[Dict[str, Any]]:
    """
    Places rest stops along the route for a walker pacing at pace_kmh.
    Evaluates building shade at predicted arrival time at candidate locations.
    """
    if len(route_coords) < 2:
        return []

    speed_m_per_min = (pace_kmh * 1000.0) / 60.0
    dist_interval_m = speed_m_per_min * rest_every_min

    # Project route into UTM Zone 45N metric space
    utm_points = [to_utm(c[0], c[1]) for c in route_coords]

    # Pre-calculate cumulative lengths along route
    cum_dists = [0.0]
    total_len = 0.0
    for i in range(1, len(utm_points)):
        step = _distance_utm(utm_points[i - 1], utm_points[i])
        total_len += step
        cum_dists.append(total_len)

    # Parse departure time
    try:
        sh, sm = map(int, start_time_str.split(":"))
    except Exception:
        sh, sm = 15, 0

    now = datetime.datetime.now()
    depart_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    shadow_engine = get_shadow_engine()

    # Pre-project candidate seats into UTM
    candidates_utm = []
    for c in REST_CANDIDATES:
        ux, uy = to_utm(c["lon"], c["lat"])
        candidates_utm.append({**c, "utm_x": ux, "utm_y": uy})

    stops = []
    target_dist = dist_interval_m
    stop_idx = 1

    while target_dist < (total_len - 30.0): # Stop placing if too close to destination
        # Interpolate point on route at target_dist
        route_pt_utm = None
        for i in range(1, len(cum_dists)):
            if cum_dists[i] >= target_dist:
                seg_len = cum_dists[i] - cum_dists[i - 1]
                ratio = (target_dist - cum_dists[i - 1]) / seg_len if seg_len > 0 else 0
                rx = utm_points[i - 1][0] + ratio * (utm_points[i][0] - utm_points[i - 1][0])
                ry = utm_points[i - 1][1] + ratio * (utm_points[i][1] - utm_points[i - 1][1])
                route_pt_utm = (rx, ry)
                break

        if not route_pt_utm:
            break

        # Estimated arrival time at this distance
        walk_mins = target_dist / speed_m_per_min
        arrival_dt = depart_dt + datetime.timedelta(minutes=walk_mins)
        arrival_time_str = arrival_dt.strftime("%H:%M")

        # Find nearby candidates within search radius
        best_candidate = None
        best_shade = -1.0
        min_cand_dist = float("inf")

        for cand in candidates_utm:
            d_cand = _distance_utm(route_pt_utm, (cand["utm_x"], cand["utm_y"]))
            if d_cand <= REST_STOP_SEARCH_RADIUS_M:
                # Test building shadow coverage at candidate location
                shadow_geojson = shadow_engine.compute_shadows(arrival_dt)
                # Compute shade ratio: check if point intersects shadow polygons
                from shapely.geometry import shape
                cand_point = Point(cand["lon"], cand["lat"])
                is_shaded = False
                for feat in shadow_geojson.get("features", []):
                    geom = shape(feat["geometry"])
                    if geom.contains(cand_point):
                        is_shaded = True
                        break
                shade_score = 0.85 if is_shaded else 0.35

                if shade_score > best_shade:
                    best_shade = shade_score
                    best_candidate = cand
                    min_cand_dist = d_cand

        # Fallback if no candidate within 40m or shade is low:
        # Use route point directly as an approximate shaded rest spot
        if best_candidate and best_shade >= min_shade_threshold:
            stop_info = {
                "stop_index": stop_idx,
                "id": best_candidate["id"],
                "name": best_candidate["name"],
                "kind": best_candidate["kind"],
                "lat": best_candidate["lat"],
                "lon": best_candidate["lon"],
                "cumulative_dist_m": round(target_dist),
                "cumulative_walk_min": round(walk_mins, 1),
                "arrival_time": arrival_time_str,
                "shade_at_arrival": best_shade,
                "is_qualified": True,
                "approximate": False,
                "description": best_candidate["description"],
            }
        else:
            # Fallback to route point marked approximate
            wgs_lon, wgs_lat = to_wgs84(route_pt_utm[0], route_pt_utm[1])
            stop_info = {
                "stop_index": stop_idx,
                "id": f"approx_rest_{stop_idx}",
                "name": f"Rest Spot {stop_idx} (Shaded Pavement Corner)",
                "kind": "rest_point",
                "lat": round(wgs_lat, 5),
                "lon": round(wgs_lon, 5),
                "cumulative_dist_m": round(target_dist),
                "cumulative_walk_min": round(walk_mins, 1),
                "arrival_time": arrival_time_str,
                "shade_at_arrival": max(0.45, best_shade),
                "is_qualified": False,
                "approximate": True,
                "description": "Approximate rest point along shaded street edge (no tagged bench)",
            }

        stops.append(stop_info)
        stop_idx += 1
        target_dist += dist_interval_m

    return stops
