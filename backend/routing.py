import math
import heapq
import json
import os
import datetime
from typing import Dict, List, Tuple, Any, Optional
import pyproj
from shapely.geometry import LineString, Point, Polygon, MultiPolygon, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from backend.geo_shadows import get_shadow_engine, to_utm, to_wgs84, calculate_solar_position

class RoutingEngine:
    def __init__(self, graph_path: str = "data/street_graph.json", pois_path: str = "data/pois.json"):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        self.adjacency: Dict[str, List[Dict[str, Any]]] = {}
        self.pois: List[Dict[str, Any]] = []
        self._exposure_cache: Dict[str, Dict[str, float]] = {}
        self.load_graph(graph_path)
        self.load_pois(pois_path)
        
    def load_graph(self, graph_path: str):
        if not os.path.exists(graph_path):
            raise FileNotFoundError(f"Street graph file not found: {graph_path}")
        with open(graph_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.nodes = data.get("nodes", {})
        self.edges = data.get("edges", [])
        
        for nid, ninfo in self.nodes.items():
            ux, uy = to_utm(ninfo["lon"], ninfo["lat"])
            ninfo["utm_x"] = ux
            ninfo["utm_y"] = uy
        
        # Build bidirectional adjacency list for walking
        self.adjacency = {nid: [] for nid in self.nodes}
        
        for e in self.edges:
            u = e["source"]
            v = e["target"]
            if u in self.adjacency and v in self.adjacency:
                # Add forward edge
                self.adjacency[u].append({
                    "target": v,
                    "edge": e,
                    "reverse": False
                })
                # Add reverse edge (walkable both ways)
                self.adjacency[v].append({
                    "target": u,
                    "edge": e,
                    "reverse": True
                })
                
        print(f"RoutingEngine loaded {len(self.nodes)} nodes and {len(self.edges)} bidirectional walkable edges.")

    def load_pois(self, pois_path: str):
        if os.path.exists(pois_path):
            with open(pois_path, "r", encoding="utf-8") as f:
                self.pois = json.load(f)
        else:
            self.pois = []
            
    def resolve_location(self, query: str) -> Optional[Tuple[float, float, str]]:
        """
        Resolves a string (place name, alias, or 'lat,lon') to (lon, lat, name).
        """
        query_clean = query.strip().lower()
        
        # Check POIs and aliases
        for poi in self.pois:
            if query_clean == poi["id"].lower() or query_clean in poi["name"].lower():
                return (poi["lon"], poi["lat"], poi["name"])
            for alias in poi.get("aliases", []):
                if alias in query_clean or query_clean in alias:
                    return (poi["lon"], poi["lat"], poi["name"])
                    
        # Check if coordinates "lat, lon"
        if "," in query:
            parts = query.split(",")
            try:
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                return (lon, lat, f"Coordinates ({lat:.4f}, {lon:.4f})")
            except:
                pass
                
        return None

    def find_nearest_node(self, lon: float, lat: float) -> str:
        """Finds the nearest graph node to given WGS84 coordinates."""
        ux, uy = to_utm(lon, lat)
        best_nid = None
        min_dist = float("inf")
        
        for nid, ninfo in self.nodes.items():
            d = math.hypot(ninfo["utm_x"] - ux, ninfo["utm_y"] - uy)
            if d < min_dist:
                min_dist = d
                best_nid = nid
                
        return best_nid

    def compute_edge_exposure(self, dt_ist: datetime.datetime) -> Dict[str, float]:
        """
        Intersects all street edges with current building shadows in UTM space.
        Returns dict: { edge_id -> sunlit_share s_e in [0, 1] }
        """
        b_min = 30 if dt_ist.minute >= 30 else 0
        cache_key = f"{dt_ist.hour:02d}:{b_min:02d}"
        if cache_key in self._exposure_cache:
            return self._exposure_cache[cache_key]

        engine = get_shadow_engine()
        shadow_geojson = engine.compute_shadows(dt_ist)
        
        # If no shadows (night or high sun directly overhead)
        if not shadow_geojson["features"]:
            return {e["edge_id"]: 1.0 for e in self.edges}
            
        # Build union of shadows in UTM for spatial intersection
        shadow_utm_shapes = []
        for feat in shadow_geojson["features"]:
            geom = shape(feat["geometry"])
            if geom.geom_type == "Polygon":
                coords = [to_utm(x, y) for x, y in geom.exterior.coords]
                shadow_utm_shapes.append(Polygon(coords))
            elif geom.geom_type == "MultiPolygon":
                for poly in geom.geoms:
                    coords = [to_utm(x, y) for x, y in poly.exterior.coords]
                    shadow_utm_shapes.append(Polygon(coords))
                    
        if not shadow_utm_shapes:
            return {e["edge_id"]: 1.0 for e in self.edges}
            
        merged_shadows = unary_union(shadow_utm_shapes)
        tree = STRtree([merged_shadows]) if merged_shadows.is_valid else None
        
        exposure_map = {}
        for e in self.edges:
            utm_c = e["utm_coords"]
            line = LineString(utm_c)
            total_len = e["length_m"]
            
            if total_len <= 0.1:
                exposure_map[e["edge_id"]] = 1.0
                continue
                
            import shapely.errors
            try:
                if merged_shadows.intersects(line):
                    inter = merged_shadows.intersection(line)
                    shaded_len = inter.length
                    sunlit_len = max(0.0, total_len - shaded_len)
                    sunlit_fraction = sunlit_len / total_len
                    exposure_map[e["edge_id"]] = max(0.0, min(1.0, sunlit_fraction))
                else:
                    exposure_map[e["edge_id"]] = 1.0
            except shapely.errors.TopologicalError as err:
                print(f"TopologicalError during intersection: {err}")
                exposure_map[e["edge_id"]] = 1.0
                
        self._exposure_cache[cache_key] = exposure_map
        return exposure_map

    def _dijkstra(self, start_node: str, end_node: str, exposure_map: Dict[str, float], k_penalty: float) -> Optional[List[Dict[str, Any]]]:
        """
        Finds lowest-cost path from start_node to end_node using cost function:
        c_e = length_e * (1 + k_penalty * s_e)
        """
        dist = {nid: float("inf") for nid in self.nodes}
        dist[start_node] = 0.0
        prev = {}  # nid -> (prev_node, edge_dict, reverse_bool)
        
        pq = [(0.0, start_node)]
        visited = set()
        
        while pq:
            current_cost, u = heapq.heappop(pq)
            if u in visited:
                continue
            visited.add(u)
            
            if u == end_node:
                break
                
            for neighbor in self.adjacency.get(u, []):
                v = neighbor["target"]
                edge = neighbor["edge"]
                eid = edge["edge_id"]
                length = edge["length_m"]
                s_e = exposure_map.get(eid, 1.0)
                
                # Formula: c_e = l_e * (1 + k * s_e)
                edge_cost = length * (1.0 + k_penalty * s_e)
                new_cost = current_cost + edge_cost
                
                if new_cost < dist[v]:
                    dist[v] = new_cost
                    prev[v] = (u, edge, neighbor["reverse"])
                    heapq.heappush(pq, (new_cost, v))
                    
        if end_node not in prev and start_node != end_node:
            return None
            
        # Reconstruct path
        path_segments = []
        curr = end_node
        while curr != start_node:
            p_node, edge, is_rev = prev[curr]
            eid = edge["edge_id"]
            s_e = exposure_map.get(eid, 1.0)
            coords = list(edge["coordinates"])
            if is_rev:
                coords.reverse()
                
            path_segments.append({
                "edge_id": eid,
                "name": edge["name"],
                "highway": edge["highway"],
                "length_m": edge["length_m"],
                "exposure": round(s_e, 3),
                "is_shaded": (s_e < 0.40),
                "coordinates": coords
            })
            curr = p_node
            
        path_segments.reverse()
        return path_segments

    def plan_route(self, 
                   origin_query: str, 
                   destination_query: str, 
                   depart_time_str: str = "15:00", 
                   sun_tolerance: str = "low", 
                   speed_kmh: float = 3.0) -> Dict[str, Any]:
        """
        Full routing pipeline returning both Shortest Path and Shade-Aware Path.
        """
        # Resolve locations
        orig = self.resolve_location(origin_query)
        if not orig:
            raise ValueError(f"Origin location '{origin_query}' could not be resolved.")
            
        dest = self.resolve_location(destination_query)
        if not dest:
            raise ValueError(f"Destination location '{destination_query}' could not be resolved.")
            
        orig_lon, orig_lat, orig_name = orig
        dest_lon, dest_lat, dest_name = dest
        
        start_nid = self.find_nearest_node(orig_lon, orig_lat)
        end_nid = self.find_nearest_node(dest_lon, dest_lat)
        
        if not start_nid or not end_nid:
            raise ValueError("No reachable street nodes found near requested locations.")
            
        # Parse time
        try:
            parts = depart_time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except:
            hour, minute = 15, 0
        now = datetime.datetime.now()
        dt_ist = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Determine sun penalty k
        tol_lower = sun_tolerance.lower().strip()
        if "low" in tol_lower or "zero" in tol_lower or "none" in tol_lower or "cant" in tol_lower or "can't" in tol_lower:
            k_penalty = 4.5  # High aversion to sun exposure
        elif "medium" in tol_lower or "moderate" in tol_lower:
            k_penalty = 1.8
        else:
            k_penalty = 0.6  # High tolerance (slight preference for shade)
            
        # Compute edge exposure for this time slot (with caching for performance)
        if hasattr(self, "_exposure_cache") and dt_ist.strftime("%Y-%m-%d %H:%M") in self._exposure_cache:
            exposure_map = self._exposure_cache[dt_ist.strftime("%Y-%m-%d %H:%M")]
        else:
            exposure_map = self.compute_edge_exposure(dt_ist)
            if not hasattr(self, "_exposure_cache"):
                self._exposure_cache = {}
            self._exposure_cache[dt_ist.strftime("%Y-%m-%d %H:%M")] = exposure_map

        
        # 1. Shortest Path (k = 0)
        shortest_segments = self._dijkstra(start_nid, end_nid, exposure_map, k_penalty=0.0)
        
        # 2. Shade-Aware Path (k = k_penalty)
        shade_segments = self._dijkstra(start_nid, end_nid, exposure_map, k_penalty=k_penalty)
        
        if not shortest_segments or not shade_segments:
            raise ValueError("No walkable path found between these two locations.")
            
        # Walking speed: km/h to meters/minute
        speed_m_per_min = (speed_kmh * 1000.0) / 60.0  # 3.0 km/h = 50 m/min
        
        # Calculate statistics
        def calc_stats(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
            total_dist = sum(s["length_m"] for s in segments)
            sunlit_dist = sum(s["length_m"] * s["exposure"] for s in segments)
            shaded_dist = total_dist - sunlit_dist
            
            total_duration_mins = total_dist / speed_m_per_min if speed_m_per_min > 0 else 0
            sun_minutes = sunlit_dist / speed_m_per_min if speed_m_per_min > 0 else 0
            shade_percentage = (shaded_dist / total_dist * 100.0) if total_dist > 0 else 0.0
            
            # Build merged GeoJSON LineString
            line_coords = []
            for s in segments:
                if not line_coords:
                    line_coords.extend(s["coordinates"])
                else:
                    line_coords.extend(s["coordinates"][1:])
                    
            return {
                "distance_meters": round(total_dist, 1),
                "duration_minutes": round(total_duration_mins, 1),
                "sun_minutes": round(sun_minutes, 1),
                "sunlit_meters": round(sunlit_dist, 1),
                "shaded_meters": round(shaded_dist, 1),
                "shade_percentage": round(shade_percentage, 1),
                "coordinates": line_coords,
                "segments": segments
            }
            
        shortest_stats = calc_stats(shortest_segments)
        shade_stats = calc_stats(shade_segments)
        
        # Check difference
        extra_dist_m = round(shade_stats["distance_meters"] - shortest_stats["distance_meters"], 1)
        extra_time_mins = round(shade_stats["duration_minutes"] - shortest_stats["duration_minutes"], 1)
        sun_mins_saved = round(shortest_stats["sun_minutes"] - shade_stats["sun_minutes"], 1)
        
        # Generate 1-sentence trade-off explanation as mandated by PRD & MVP
        solar = calculate_solar_position(dt_ist)
        elev = solar["elevation"]
        
        is_high_noon = (elev > 55.0)
        noon_note = ""
        if is_high_noon:
            noon_note = f" Honest note: The sun is overhead ({elev:.1f}° elevation), so building shadows are narrow (0.5x height); leaving before 10 AM or after 2:30 PM offers far more shade."
            
        if sun_mins_saved > 0.5:
            trade_off_sentence = (
                f"Taking the shaded route is {int(extra_dist_m)}m longer (+{extra_time_mins:.1f} mins) "
                f"but saves {sun_mins_saved:.1f} sun-minutes, providing {shade_stats['shade_percentage']:.0f}% continuous shade "
                f"instead of the exposed {shortest_stats['shade_percentage']:.0f}% on the direct avenue.{noon_note}"
            )
        else:
            trade_off_sentence = (
                f"The direct path is already well shaded ({shade_stats['shade_percentage']:.0f}% shade); "
                f"the shade route matches the shortest path with {shade_stats['sun_minutes']:.1f} sun-minutes.{noon_note}"
            )
            
        # Generate turn-by-turn directions along shade route
        directions = self._generate_directions(shade_segments, orig_name, dest_name)
        shade_stats["directions"] = directions

        return {
            "origin": {"name": orig_name, "lon": orig_lon, "lat": orig_lat},
            "destination": {"name": dest_name, "lon": dest_lon, "lat": dest_lat},
            "depart_time": dt_ist.strftime("%H:%M"),
            "sun_tolerance": sun_tolerance,
            "speed_kmh": speed_kmh,
            "solar_info": {
                "elevation": elev,
                "azimuth": solar["azimuth"],
                "shadow_factor": solar["shadow_factor"],
                "is_high_noon": is_high_noon
            },
            "shade_route": shade_stats,
            "shortest_route": shortest_stats,
            "directions": directions,
            "comparison": {
                "extra_distance_m": extra_dist_m,
                "extra_time_mins": extra_time_mins,
                "sun_minutes_saved": max(0.0, sun_mins_saved),
                "shade_gain_percentage": round(shade_stats["shade_percentage"] - shortest_stats["shade_percentage"], 1)
            },
            "trade_off_sentence": trade_off_sentence
        }

    def _generate_directions(self, segments: List[Dict[str, Any]], orig_name: str, dest_name: str) -> List[Dict[str, Any]]:
        if not segments:
            return []

        steps = []
        # Step 1: Start at Origin
        first_coords = segments[0]["coordinates"][0] if segments[0].get("coordinates") else None
        steps.append({
            "step": 1,
            "type": "start",
            "instruction": f"Depart from {orig_name}",
            "distance_m": 0,
            "shade_pct": 100 if segments[0]["is_shaded"] else 25,
            "is_shaded": segments[0]["is_shaded"],
            "street": segments[0].get("name") or "Origin Passage",
            "coords": first_coords
        })

        current_street = None
        accum_dist = 0.0
        accum_sun = 0.0
        seg_coords = None

        for s in segments:
            st_name = s.get("name") or "Shaded Arcade"
            if current_street is None:
                current_street = st_name
                accum_dist = s["length_m"]
                accum_sun = s["length_m"] * s.get("exposure", 0.5)
                seg_coords = s["coordinates"][0] if s.get("coordinates") else None
            elif st_name == current_street:
                accum_dist += s["length_m"]
                accum_sun += s["length_m"] * s.get("exposure", 0.5)
            else:
                shade_pct = max(0, min(100, int((1.0 - (accum_sun / max(accum_dist, 1.0))) * 100)))
                verb = "Turn onto" if len(steps) > 1 else "Walk along"
                hint = f" ({shade_pct}% shade)" if shade_pct >= 60 else f" ({100-shade_pct}% exposed)"
                steps.append({
                    "step": len(steps) + 1,
                    "type": "turn",
                    "instruction": f"{verb} {current_street} for {round(accum_dist)}m{hint}",
                    "distance_m": round(accum_dist, 1),
                    "shade_pct": shade_pct,
                    "is_shaded": (shade_pct >= 60),
                    "street": current_street,
                    "coords": seg_coords
                })
                current_street = st_name
                accum_dist = s["length_m"]
                accum_sun = s["length_m"] * s.get("exposure", 0.5)
                seg_coords = s["coordinates"][0] if s.get("coordinates") else None

        if current_street and accum_dist > 0:
            shade_pct = max(0, min(100, int((1.0 - (accum_sun / max(accum_dist, 1.0))) * 100)))
            hint = f" ({shade_pct}% shade)" if shade_pct >= 60 else f" ({100-shade_pct}% exposed)"
            steps.append({
                "step": len(steps) + 1,
                "type": "walk",
                "instruction": f"Continue along {current_street} for {round(accum_dist)}m{hint}",
                "distance_m": round(accum_dist, 1),
                "shade_pct": shade_pct,
                "is_shaded": (shade_pct >= 60),
                "street": current_street,
                "coords": seg_coords
            })

        # Final Arrival Step
        last_coords = segments[-1]["coordinates"][-1] if segments[-1].get("coordinates") else None
        steps.append({
            "step": len(steps) + 1,
            "type": "finish",
            "instruction": f"Arrive at {dest_name}",
            "distance_m": 0,
            "shade_pct": 100,
            "is_shaded": True,
            "street": dest_name,
            "coords": last_coords
        })

        return steps


_routing_instance: Optional[RoutingEngine] = None

def get_routing_engine() -> RoutingEngine:
    global _routing_instance
    if _routing_instance is None:
        _routing_instance = RoutingEngine()
    return _routing_instance
