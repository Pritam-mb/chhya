import json
import os
import math
from shapely.geometry import Polygon, LineString, Point, mapping
from shapely.ops import unary_union
import pyproj

# EPSG:4326 (WGS84 lat/lon) to EPSG:32645 (UTM Zone 45N for Kolkata in meters)
proj_to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True).transform
proj_to_wgs84 = pyproj.Transformer.from_crs("EPSG:32645", "EPSG:4326", always_xy=True).transform

def process_osm(raw_path="data/osm_raw.json"):
    print("Loading raw OSM data...")
    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    elements = data.get("elements", [])
    nodes = {}
    ways = []
    
    for el in elements:
        if el["type"] == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])
        elif el["type"] == "way":
            ways.append(el)

    print(f"Loaded {len(nodes)} nodes and {len(ways)} ways.")

    # 1. Process Buildings
    buildings_features = []
    default_height = 16.0  # Park St / Camac St typical building height (4-5 stories)

    for way in ways:
        tags = way.get("tags", {})
        if "building" in tags:
            node_ids = way.get("nodes", [])
            coords = [nodes[nid] for nid in node_ids if nid in nodes]
            if len(coords) >= 4 and coords[0] == coords[-1]:
                # Valid closed polygon
                h = default_height
                if "height" in tags:
                    try:
                        h = float(tags["height"].replace("m", "").strip())
                    except:
                        pass
                elif "building:levels" in tags:
                    try:
                        levels = float(tags["building:levels"])
                        h = max(levels * 3.2, 6.0)
                    except:
                        pass

                name = tags.get("name", tags.get("addr:housename", "Building"))
                b_type = tags.get("building", "yes")

                feature = {
                    "type": "Feature",
                    "id": str(way["id"]),
                    "properties": {
                        "id": way["id"],
                        "name": name,
                        "type": b_type,
                        "height": round(h, 1),
                        "levels": tags.get("building:levels", str(round(h / 3.2))),
                        "is_default_height": ("height" not in tags and "building:levels" not in tags)
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords]
                    }
                }
                buildings_features.append(feature)

    print(f"Extracted {len(buildings_features)} building footprints.")

    # 2. Process Walkable Street Network
    walkable_highways = {
        "pedestrian", "footway", "residential", "living_street", 
        "tertiary", "secondary", "primary", "service", "unclassified", "path"
    }

    street_edges = []
    street_features = []
    graph_nodes = {}
    edge_id = 0

    for way in ways:
        tags = way.get("tags", {})
        highway = tags.get("highway")
        if highway and highway in walkable_highways:
            node_ids = way.get("nodes", [])
            valid_coords = [nodes[nid] for nid in node_ids if nid in nodes]
            if len(valid_coords) < 2:
                continue

            street_name = tags.get("name", tags.get("ref", "Lane / Alley"))
            is_lane = highway in ["service", "footway", "path", "living_street"] or ("lane" in street_name.lower())

            # Break way into edge segments between consecutive nodes
            for i in range(len(valid_coords) - 1):
                c1 = valid_coords[i]
                c2 = valid_coords[i+1]
                n1_id = node_ids[i]
                n2_id = node_ids[i+1]

                # Project to UTM to compute length in meters
                u1_x, u1_y = proj_to_utm(c1[0], c1[1])
                u2_x, u2_y = proj_to_utm(c2[0], c2[1])
                length_m = math.hypot(u2_x - u1_x, u2_y - u1_y)
                if length_m < 0.5:
                    continue

                graph_nodes[str(n1_id)] = {"id": str(n1_id), "lon": c1[0], "lat": c1[1]}
                graph_nodes[str(n2_id)] = {"id": str(n2_id), "lon": c2[0], "lat": c2[1]}

                edge_info = {
                    "edge_id": f"e_{edge_id}",
                    "way_id": way["id"],
                    "source": str(n1_id),
                    "target": str(n2_id),
                    "name": street_name,
                    "highway": highway,
                    "length_m": round(length_m, 2),
                    "coordinates": [c1, c2],
                    "utm_coords": [[u1_x, u1_y], [u2_x, u2_y]]
                }
                street_edges.append(edge_info)

                # Feature for GeoJSON rendering
                street_features.append({
                    "type": "Feature",
                    "id": f"e_{edge_id}",
                    "properties": {
                        "edge_id": f"e_{edge_id}",
                        "name": street_name,
                        "highway": highway,
                        "length_m": round(length_m, 2)
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [c1, c2]
                    }
                })
                edge_id += 1

    print(f"Extracted {len(street_edges)} street segments across {len(graph_nodes)} intersection nodes.")

    # 3. Create Key Points of Interest dynamically from OSM tags
    pois = [
        {
            "id": "poi_dadu_home",
            "name": "Dadu's Residence (Middleton Row)",
            "category": "home",
            "address": "7 Middleton Row, near Loreto House",
            "lat": 22.5512,
            "lon": 88.3524,
            "aliases": ["home", "dadu's home", "house", "middleton row residence"],
            "is_illustrative": True
        }
    ]

    for el in elements:
        tags = el.get("tags", {})
        amenity = tags.get("amenity")
        shop = tags.get("shop")
        healthcare = tags.get("healthcare")
        
        category = amenity or shop or healthcare
        if category and "name" in tags:
            lat, lon = None, None
            if el["type"] == "node":
                lat, lon = el["lat"], el["lon"]
            elif el["type"] == "way":
                way_nodes = el.get("nodes", [])
                valid_coords = [nodes[nid] for nid in way_nodes if nid in nodes]
                if valid_coords:
                    lon = sum(c[0] for c in valid_coords) / len(valid_coords)
                    lat = sum(c[1] for c in valid_coords) / len(valid_coords)
                    
            if lat is not None and lon is not None:
                name = tags["name"]
                pois.append({
                    "id": f"poi_{el['id']}",
                    "name": name,
                    "category": category,
                    "lat": lat,
                    "lon": lon,
                    "aliases": [name.lower()]
                })

    # Save outputs
    with open("data/buildings.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": buildings_features}, f, indent=2)
    print("Saved data/buildings.geojson")

    with open("data/streets.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": street_features}, f, indent=2)
    print("Saved data/streets.geojson")

    graph_data = {
        "nodes": graph_nodes,
        "edges": street_edges
    }
    with open("data/street_graph.json", "w", encoding="utf-8") as f:
        json.dump(graph_data, f)
    print("Saved data/street_graph.json")

    with open("data/pois.json", "w", encoding="utf-8") as f:
        json.dump(pois, f, indent=2)
    print("Saved data/pois.json")

if __name__ == "__main__":
    process_osm()
