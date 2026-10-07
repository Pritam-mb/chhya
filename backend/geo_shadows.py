import math
import datetime
import json
import os
from typing import Dict, List, Tuple, Any, Optional
import pyproj
from shapely.geometry import Polygon, MultiPolygon, LineString, Point, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

# Kolkata Reference Coordinates
KOLKATA_LAT = 22.5510
KOLKATA_LON = 88.3530
TZ_OFFSET_HOURS = 5.5  # IST is UTC+5:30

# Projections
# EPSG:4326 <-> EPSG:32645 (WGS 84 / UTM zone 45N covers West Bengal & Kolkata)
transformer_to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True)
transformer_to_wgs84 = pyproj.Transformer.from_crs("EPSG:32645", "EPSG:4326", always_xy=True)

def to_utm(lon: float, lat: float) -> Tuple[float, float]:
    return transformer_to_utm.transform(lon, lat)

def to_wgs84(x: float, y: float) -> Tuple[float, float]:
    return transformer_to_wgs84.transform(x, y)


def calculate_solar_position(dt_ist: datetime.datetime, lat: float = KOLKATA_LAT, lon: float = KOLKATA_LON) -> Dict[str, float]:
    """
    Computes accurate solar elevation and azimuth using standard astronomical solar equations (NOAA solar algorithm).
    lat: degrees North
    lon: degrees East
    Returns:
        elevation: degrees above horizon (-90 to 90)
        azimuth: degrees from North (0=N, 90=E, 180=S, 270=W)
        shadow_factor: building_height multiplier = 1 / tan(elevation)
    """
    # Day of year
    day_of_year = dt_ist.timetuple().tm_yday
    hour_float = dt_ist.hour + dt_ist.minute / 60.0 + dt_ist.second / 3600.0
    
    # Fractional year (radians)
    gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1 + (hour_float - 12.0) / 24.0)
    
    # Equation of time in minutes
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    
    # Solar declination in radians
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    
    # Time offset in minutes: lst = standard_time + 4*(lon - std_meridian) + eqtime
    # IST standard meridian is 82.5° E
    time_offset = eqtime + 4.0 * (lon - 82.5)
    
    # True solar time in minutes
    tst = hour_float * 60.0 + time_offset
    # Solar hour angle in degrees
    ha_deg = (tst / 4.0) - 180.0
    ha = math.radians(ha_deg)
    
    lat_rad = math.radians(lat)
    
    # Solar zenith angle
    cos_zenith = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl) * math.cos(ha)
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    zenith_rad = math.acos(cos_zenith)
    elevation_rad = (math.pi / 2.0) - zenith_rad
    elevation_deg = math.degrees(elevation_rad)
    
    # Solar azimuth angle (from North clockwise)
    # cos(azimuth) = (sin(decl) - sin(lat)*cos(zenith)) / (cos(lat)*sin(zenith))
    sin_zenith = math.sin(zenith_rad)
    if sin_zenith > 1e-5:
        cos_az = (math.sin(decl) - math.sin(lat_rad) * cos_zenith) / (math.cos(lat_rad) * sin_zenith)
        cos_az = max(-1.0, min(1.0, cos_az))
        az_deg = math.degrees(math.acos(cos_az))
        if ha_deg > 0:
            az_deg = 360.0 - az_deg
    else:
        az_deg = 180.0
        
    shadow_factor = 0.0
    if elevation_deg > 1.5:
        shadow_factor = 1.0 / math.tan(elevation_rad)
        
    return {
        "elevation": round(elevation_deg, 2),
        "azimuth": round(az_deg, 2),
        "shadow_factor": round(shadow_factor, 3),
        "is_daylight": elevation_deg > 0.0
    }


class ShadowEngine:
    def __init__(self, buildings_geojson_path: str = "data/buildings.geojson"):
        self.buildings = []
        self.load_buildings(buildings_geojson_path)
        
    def load_buildings(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Buildings file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        features = data.get("features", [])
        for feat in features:
            geom = shape(feat["geometry"])
            props = feat.get("properties", {})
            height = float(props.get("height", 16.0))
            
            # Project building coordinates to UTM for metric geometry
            if geom.geom_type == "Polygon":
                utm_exterior = [to_utm(x, y) for x, y in geom.exterior.coords]
                utm_poly = Polygon(utm_exterior)
                self.buildings.append({
                    "id": feat.get("id"),
                    "name": props.get("name", "Building"),
                    "height": height,
                    "wgs_poly": geom,
                    "utm_poly": utm_poly
                })
        print(f"ShadowEngine loaded {len(self.buildings)} buildings.")

    def compute_shadows(self, dt_ist: datetime.datetime) -> Dict[str, Any]:
        """
        Extrudes building footprints along anti-solar vector in UTM Zone 45N.
        Returns GeoJSON FeatureCollection of shadow polygons in WGS84 with solar stats.
        """
        solar = calculate_solar_position(dt_ist)
        elevation = solar["elevation"]
        azimuth = solar["azimuth"]
        shadow_factor = solar["shadow_factor"]
        
        if elevation <= 1.0:
            # Sun below horizon or twilight
            return {
                "type": "FeatureCollection",
                "properties": {
                    "time_ist": dt_ist.strftime("%H:%M"),
                    "solar_elevation": elevation,
                    "solar_azimuth": azimuth,
                    "shadow_factor": 0.0,
                    "status": "night" if elevation <= 0 else "twilight"
                },
                "features": []
            }
            
        # Anti-solar azimuth: direction shadows are cast away from sun
        anti_azimuth_deg = (azimuth + 180.0) % 360.0
        anti_azimuth_rad = math.radians(anti_azimuth_deg)
        
        # Unit vector in UTM: North is +Y, East is +X
        # Azimuth 0 = North -> dx=0, dy=+1
        # Azimuth 90 = East -> dx=+1, dy=0
        ux = math.sin(anti_azimuth_rad)
        uy = math.cos(anti_azimuth_rad)
        
        shadow_utm_polys = []
        
        for b in self.buildings:
            h = b["height"]
            d = h * shadow_factor
            dx = ux * d
            dy = uy * d
            
            poly = b["utm_poly"]
            base_coords = list(poly.exterior.coords)
            
            # Extruded roof vertices
            top_coords = [(x + dx, y + dy) for x, y in base_coords]
            
            # Shadow polygon is convex hull of base footprint and extruded roof points
            all_points = base_coords + top_coords
            shadow_poly = Polygon(all_points).convex_hull
            if shadow_poly.is_valid and not shadow_poly.is_empty:
                shadow_utm_polys.append(shadow_poly)
                
        # Union shadows to merge overlaps
        if shadow_utm_polys:
            # Batch union for performance
            merged_utm = unary_union(shadow_utm_polys)
            if merged_utm.geom_type == "Polygon":
                polys = [merged_utm]
            elif merged_utm.geom_type == "MultiPolygon":
                polys = list(merged_utm.geoms)
            else:
                polys = []
        else:
            polys = []
            
        # Convert merged shadow polygons back to WGS84 GeoJSON
        shadow_features = []
        for p in polys:
            if p.is_empty or p.area < 2.0:
                continue
            wgs_exterior = [to_wgs84(x, y) for x, y in p.exterior.coords]
            wgs_interiors = [[to_wgs84(x, y) for x, y in ring.coords] for ring in p.interiors]
            wgs_poly = Polygon(wgs_exterior, wgs_interiors)
            
            shadow_features.append({
                "type": "Feature",
                "properties": {
                    "area_sqm": round(p.area, 1)
                },
                "geometry": mapping(wgs_poly)
            })
            
        return {
            "type": "FeatureCollection",
            "properties": {
                "time_ist": dt_ist.strftime("%H:%M"),
                "solar_elevation": elevation,
                "solar_azimuth": azimuth,
                "shadow_factor": shadow_factor,
                "sun_status": "high_noon" if elevation > 55 else ("afternoon" if dt_ist.hour >= 12 else "morning"),
                "shadow_count": len(shadow_features)
            },
            "features": shadow_features
        }


# Singleton instance
_engine_instance: Optional[ShadowEngine] = None

def get_shadow_engine() -> ShadowEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ShadowEngine()
    return _engine_instance
