"""
Persistent SQLite database service for Trips, Checkins, and Cards in Chhaya.
Fulfills Section 4, P1 (Trips & Checkins) & P2 (Cards, Proximity & Moderation).
"""
import os
import re
import math
import sqlite3
import datetime
from typing import Dict, List, Any, Optional, Tuple
import qrcode
import io
import base64

from backend.config import (
    CARD_NEAR_RADIUS_M,
    CARD_RADAR_RADIUS_M,
    CARD_MAX_CHARS,
    CARD_DEFAULT_TTL_HOURS,
    CARD_RATE_LIMIT_PER_MINUTE,
    OBS_MATCH_TOLERANCE,
    OBS_MIN_TAPS_FOR_CORRECTION,
    OBS_MAX_CORRECTION,
)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chhaya.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes tables and indexes."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                code TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                reached INTEGER DEFAULT 0,
                reached_at TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_code TEXT NOT NULL,
                walker_name TEXT NOT NULL,
                stop_index INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (trip_code) REFERENCES trips(code)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id TEXT PRIMARY KEY,
                trip_code TEXT,
                type TEXT NOT NULL,
                text TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                visibility TEXT DEFAULT 'public',
                to_group TEXT,
                shade_at_creation REAL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                hidden INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_code TEXT NOT NULL,
                walker_name TEXT NOT NULL,
                label TEXT NOT NULL,
                stop_index INTEGER,
                predicted_shade REAL NOT NULL,
                observed_shade REAL NOT NULL,
                matched INTEGER NOT NULL,
                sun_elevation REAL,
                sun_azimuth REAL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_observations_label
            ON observations (label)
        """)
        conn.commit()


# --------------------------------------------------------------------- Trips
def save_trip(code: str, mode: str, plan_dict: Dict[str, Any]) -> None:
    import json
    now = datetime.datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO trips (code, mode, plan_json, created_at)
            VALUES (?, ?, ?, ?)
        """, (code, mode, json.dumps(plan_dict), now))
        conn.commit()


def get_trip(code: str) -> Optional[Dict[str, Any]]:
    import json
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM trips WHERE code = ?", (code,)).fetchone()
        if not row:
            return None
        return {
            "code": row["code"],
            "mode": row["mode"],
            "plan": json.loads(row["plan_json"]),
            "reached": bool(row["reached"]),
            "reached_at": row["reached_at"],
            "created_at": row["created_at"],
        }


def mark_trip_reached(code: str) -> bool:
    now = datetime.datetime.now().isoformat()
    with get_connection() as conn:
        cur = conn.execute("UPDATE trips SET reached = 1, reached_at = ? WHERE code = ?", (now, code))
        conn.commit()
        return cur.rowcount > 0


# ------------------------------------------------------------------ Checkins
def record_checkin(trip_code: str, walker_name: str, stop_index: int) -> Dict[str, Any]:
    now = datetime.datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO checkins (trip_code, walker_name, stop_index, timestamp)
            VALUES (?, ?, ?, ?)
        """, (trip_code, walker_name, stop_index, now))
        conn.commit()

    return {
        "trip_code": trip_code,
        "walker": walker_name,
        "stop_index": stop_index,
        "timestamp": now,
    }


def get_trip_checkins(trip_code: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT walker_name, stop_index, timestamp
            FROM checkins
            WHERE trip_code = ?
            ORDER BY id ASC
        """, (trip_code,)).fetchall()
        return [
            {"walker": r["walker_name"], "stop_index": r["stop_index"], "timestamp": r["timestamp"]}
            for r in rows
        ]


# ------------------------------------------------------- Shade observations
def record_observation(
    trip_code: str,
    walker_name: str,
    label: str,
    predicted_shade: float,
    observed_shade: float,
    stop_index: Optional[int] = None,
    sun_elevation: Optional[float] = None,
    sun_azimuth: Optional[float] = None,
) -> Dict[str, Any]:
    """Stores one checkpoint shade tap with the predicted value beside it.

    Fulfills Section 3.6: every tap keeps predicted vs observed, the label,
    the time and the sun position so calibration is auditable.
    """
    now = datetime.datetime.now().isoformat()
    try:
        pred = max(0.0, min(1.0, float(predicted_shade)))
    except (TypeError, ValueError):
        pred = 0.0
    try:
        obs = max(0.0, min(1.0, float(observed_shade)))
    except (TypeError, ValueError):
        obs = 0.0
    matched = 1 if abs(obs - pred) <= OBS_MATCH_TOLERANCE else 0
    clean_label = (label or "checkpoint").strip()[:80] or "checkpoint"
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO observations
                (trip_code, walker_name, label, stop_index, predicted_shade,
                 observed_shade, matched, sun_elevation, sun_azimuth, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (trip_code, walker_name, clean_label, stop_index, pred, obs,
              matched, sun_elevation, sun_azimuth, now))
        conn.commit()
    return {
        "trip_code": trip_code,
        "walker": walker_name,
        "label": clean_label,
        "predicted_shade": pred,
        "observed_shade": obs,
        "matched": bool(matched),
        "timestamp": now,
    }


def get_accuracy_summary() -> Dict[str, Any]:
    """Live accuracy meter with counts, plus per-label corrections.

    A correction is learned only once a label has OBS_MIN_TAPS_FOR_CORRECTION
    taps, is clamped to +-OBS_MAX_CORRECTION, and is never shown without its
    tap count (honest about small samples per Section 3.6).
    """
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"]
        matched = conn.execute("SELECT COUNT(*) AS n FROM observations WHERE matched = 1").fetchone()["n"]
        rows = conn.execute("""
            SELECT label,
                   COUNT(*) AS taps,
                   SUM(matched) AS matched,
                   AVG(observed_shade - predicted_shade) AS mean_error
            FROM observations
            GROUP BY label
            ORDER BY taps DESC
        """).fetchall()

    streets = []
    corrections = {}
    for r in rows:
        taps = r["taps"]
        label = r["label"]
        correction = None
        if taps >= OBS_MIN_TAPS_FOR_CORRECTION and r["mean_error"] is not None:
            correction = max(-OBS_MAX_CORRECTION, min(OBS_MAX_CORRECTION, float(r["mean_error"])))
            corrections[label] = correction
        streets.append({
            "label": label,
            "taps": taps,
            "matched": r["matched"] or 0,
            "correction": correction,
            "correction_ready": correction is not None,
        })

    return {
        "taps": total,
        "matched": matched,
        "streets": streets,
        "corrections": corrections,
        "min_taps_for_correction": OBS_MIN_TAPS_FOR_CORRECTION,
    }


# --------------------------------------------------------------------- Cards
PHONE_REGEX = r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\b\d{10}\b'
EMAIL_REGEX = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'


def clean_and_moderate_card_text(text: str) -> Tuple[str, bool, str]:
    """
    Cleans card text by stripping personal information (phone numbers, emails)
    and validates character constraints.
    Returns: (cleaned_text, is_safe, status_label)
    """
    cleaned = text.strip()[:CARD_MAX_CHARS]

    has_pii = False
    if re.search(PHONE_REGEX, cleaned):
        cleaned = re.sub(PHONE_REGEX, "[PHONE REMOVED]", cleaned)
        has_pii = True

    if re.search(EMAIL_REGEX, cleaned):
        cleaned = re.sub(EMAIL_REGEX, "[EMAIL REMOVED]", cleaned)
        has_pii = True

    status = "flagged_pii_cleaned" if has_pii else "ok"
    return cleaned, True, status


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0  # meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def calculate_compass_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]
    return directions[int((deg + 22.5) // 45)]


def create_card(
    trip_code: Optional[str],
    card_type: str,
    text: str,
    lat: float,
    lon: float,
    visibility: str = "public",
    to_group: Optional[str] = None,
    shade_at_creation: Optional[float] = None,
    ttl_hours: int = CARD_DEFAULT_TTL_HOURS,
) -> Dict[str, Any]:
    cleaned_text, is_safe, status = clean_and_moderate_card_text(text)
    card_id = f"card_{datetime.datetime.now().strftime('%y%m%d%H%M%S')}_{os.urandom(3).hex()}"
    now = datetime.datetime.now()
    expires_at = (now + datetime.timedelta(hours=ttl_hours)).isoformat()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO cards (id, trip_code, type, text, lat, lon, visibility, to_group, shade_at_creation, created_at, expires_at, hidden)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            card_id,
            trip_code,
            card_type,
            cleaned_text,
            lat,
            lon,
            visibility,
            to_group,
            shade_at_creation or 0.75,
            now.isoformat(),
            expires_at
        ))
        conn.commit()

    return {
        "id": card_id,
        "trip_code": trip_code,
        "type": card_type,
        "text": cleaned_text,
        "lat": lat,
        "lon": lon,
        "visibility": visibility,
        "to_group": to_group,
        "shade_at_creation": shade_at_creation or 0.75,
        "created_at": now.isoformat(),
        "expires_at": expires_at,
        "moderation_status": status,
    }


def find_nearby_cards(
    lat: float,
    lon: float,
    trip_code: Optional[str] = None,
    radius_m: float = CARD_RADAR_RADIUS_M,
) -> Dict[str, Any]:
    """
    Returns immediate cards (< 60m) and radar cards (< 300m) with distance and bearing.
    """
    now_iso = datetime.datetime.now().isoformat()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM cards
            WHERE hidden = 0 AND expires_at > ?
        """, (now_iso,)).fetchall()

    immediate_cards = []
    radar_cards = []

    for r in rows:
        # Visibility filter
        vis = r["visibility"]
        c_to = r["to_group"]
        c_trip = r["trip_code"]

        if vis == "group" and trip_code != c_trip:
            continue
        if vis == "addressed" and trip_code != c_to:
            continue

        d = haversine_distance_m(lat, lon, r["lat"], r["lon"])
        if d <= radius_m:
            bearing = calculate_compass_bearing(lat, lon, r["lat"], r["lon"])
            card_dict = {
                "id": r["id"],
                "type": r["type"],
                "text": r["text"],
                "lat": r["lat"],
                "lon": r["lon"],
                "distance_m": round(d),
                "bearing": bearing,
                "is_immediate": d <= CARD_NEAR_RADIUS_M,
                "visibility": vis,
                "to_group": c_to,
                "shade_at_creation": r["shade_at_creation"],
                "created_at": r["created_at"],
            }
            if d <= CARD_NEAR_RADIUS_M:
                immediate_cards.append(card_dict)
            else:
                radar_cards.append(card_dict)

    # Sort nearest first
    immediate_cards.sort(key=lambda x: x["distance_m"])
    radar_cards.sort(key=lambda x: x["distance_m"])

    return {
        "user_lat": lat,
        "user_lon": lon,
        "immediate_count": len(immediate_cards),
        "immediate_cards": immediate_cards,
        "radar_count": len(radar_cards),
        "radar_cards": radar_cards,
    }


def report_and_hide_card(card_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("UPDATE cards SET hidden = 1 WHERE id = ?", (card_id,))
        conn.commit()
        return cur.rowcount > 0


def generate_trip_qr_base64(trip_code: str, base_url: str = "http://localhost:8000") -> str:
    """Generates QR code PNG image encoded as base64."""
    url = f"{base_url}/t/{trip_code}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#000000", back_color="#ffffff")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def seed_demo_data():
    """
    Seeds simulated demo data for Family and Club modes, plus multi-group cards.
    Satisfies Rule 6: seeded data labeled 'simulated' in the UI.
    """
    init_db()

    # 1. Family Walk: Dadu to Clinic
    dadu_plan = {
        "mode": "family",
        "trip_code": "dadu-clinic",
        "title": "Dadu's Clinic Walk",
        "status": "simulated",
        "walkers": [
            {"name": "Dadu", "sun_sensitivity": "high", "pace_kmh": 2.8, "rest_every_min": 8},
            {"name": "Pritam (Companion)", "sun_sensitivity": "normal", "pace_kmh": 4.0, "rest_every_min": 15}
        ],
        "origin": {"name": "Dadu's Residence (Middleton Row)", "lat": 22.5512, "lon": 88.3524},
        "destination": {"name": "Belle Vue Clinic", "lat": 22.5482, "lon": 88.3562},
        "depart_time": "11:40",
        "effective_budgets": {"high": 3.0, "normal": 9.0},
        "sun_minutes": 2.8,
        "baseline_sun_minutes": 8.5,
        "sun_minutes_saved": 5.7,
        "shade_percentage": 68.0,
        "stops": [
            {
                "stop_index": 1,
                "name": "Middleton Row Heritage Bench",
                "kind": "rest",
                "lat": 22.5516,
                "lon": 88.3522,
                "cumulative_walk_min": 8.0,
                "arrival_time": "11:48",
                "shade_at_arrival": 0.82,
                "approximate": False,
                "description": "Shaded wooden bench under building portico on Middleton Row"
            },
            {
                "stop_index": 2,
                "name": "Belle Vue Clinic Shaded Courtyard",
                "kind": "destination",
                "lat": 22.5482,
                "lon": 88.3562,
                "cumulative_walk_min": 14.5,
                "arrival_time": "11:55",
                "shade_at_arrival": 0.75,
                "approximate": False,
                "description": "Clinic arrival destination"
            }
        ],
        "share_message": "Dadu's clinic walk: leave 11:40, 68% shaded, 2.8 sun-minutes vs 8.5 on shortest path. Rest on shaded bench at 8-min mark."
    }
    save_trip("dadu-clinic", "family", dadu_plan)

    # 2. Club Outing: Park Street Sunset Run / Walk (5 walkers, 1 straggler)
    club_plan = {
        "mode": "club",
        "trip_code": "parkst-club",
        "title": "Park Street Sun-Smart Club Loop",
        "status": "simulated",
        "walkers": [
            {"name": "Aarav (Lead)", "sun_sensitivity": "normal", "pace_kmh": 4.2},
            {"name": "Rina", "sun_sensitivity": "high", "pace_kmh": 3.0}, # Straggler in demo
            {"name": "Kabir", "sun_sensitivity": "low", "pace_kmh": 5.0},
            {"name": "Ananya", "sun_sensitivity": "normal", "pace_kmh": 4.2},
            {"name": "Dev", "sun_sensitivity": "normal", "pace_kmh": 4.2}
        ],
        "origin": {"name": "Flurys Tea Room", "lat": 22.5532, "lon": 88.3526},
        "destination": {"name": "Camac Street Mall & Offices", "lat": 22.5492, "lon": 88.3538},
        "depart_time": "16:00",
        "effective_budgets": {"high": 4.0, "normal": 12.0, "low": 25.0},
        "sun_minutes": 3.5,
        "baseline_sun_minutes": 10.2,
        "sun_minutes_saved": 6.7,
        "shade_percentage": 74.0,
        "stops": [
            {
                "stop_index": 1,
                "name": "Russell Street Shaded Chai Stall",
                "kind": "regroup",
                "lat": 22.5523,
                "lon": 88.3512,
                "cumulative_walk_min": 7.5,
                "arrival_time": "16:08",
                "shade_at_arrival": 0.85,
                "description": "Covered tea stall regroup point"
            },
            {
                "stop_index": 2,
                "name": "Loreto Covered Colonnade",
                "kind": "regroup",
                "lat": 22.5505,
                "lon": 88.3527,
                "cumulative_walk_min": 14.0,
                "arrival_time": "16:15",
                "shade_at_arrival": 0.78,
                "description": "Deep covered portico bench"
            },
            {
                "stop_index": 3,
                "name": "Camac Street Mall & Offices",
                "kind": "destination",
                "lat": 22.5492,
                "lon": 88.3538,
                "cumulative_walk_min": 21.0,
                "arrival_time": "16:22",
                "shade_at_arrival": 0.80,
                "description": "Final finish and regroup"
            }
        ],
        "share_message": "Sun-smart walk, Park St loop. Meet 4:00 PM. 74% shaded, 3.5 sun-minutes vs 10.2. Chai regroup stop at 8-minute mark."
    }
    save_trip("parkst-club", "club", club_plan)

    # Checkins for the club outing demonstrating straggler:
    # At elapsed 18 min: Aarav, Kabir, Ananya, Dev checked into Stop 2 at 16:15.
    # Rina only checked into Stop 1 at 16:08 (she is lagging ~5.5 mins behind expected Stop 2).
    with get_connection() as conn:
        conn.execute("DELETE FROM checkins WHERE trip_code = 'parkst-club'")
        conn.commit()

    record_checkin("parkst-club", "Aarav (Lead)", 1)
    record_checkin("parkst-club", "Aarav (Lead)", 2)
    record_checkin("parkst-club", "Kabir", 1)
    record_checkin("parkst-club", "Kabir", 2)
    record_checkin("parkst-club", "Ananya", 1)
    record_checkin("parkst-club", "Ananya", 2)
    record_checkin("parkst-club", "Dev", 1)
    record_checkin("parkst-club", "Dev", 2)
    record_checkin("parkst-club", "Rina", 1) # Rina has only reached stop 1

    # 3. Seeded Cards (Multi-Group pinned notes)
    with get_connection() as conn:
        conn.execute("DELETE FROM cards WHERE id LIKE 'seed_%'")
        conn.commit()

    create_card(
        trip_code="dadu-clinic",
        card_type="tip",
        text="Deep continuous shade along Middleton Row colonnade. Rest benches available.",
        lat=22.5516,
        lon=88.3522,
        visibility="public",
        shade_at_creation=0.82
    )
    create_card(
        trip_code="parkst-club",
        card_type="meetup",
        text="Chai stall open near Russell Street market. Fresh ginger tea and deep shade.",
        lat=22.5523,
        lon=88.3512,
        visibility="public",
        shade_at_creation=0.88
    )
    create_card(
        trip_code=None,
        card_type="warning",
        text="High noon sun hits Camac crossing directly. Walk under the ICICI bank canopy.",
        lat=22.5495,
        lon=88.3536,
        visibility="public",
        shade_at_creation=0.45
    )
    create_card(
        trip_code="dadu-clinic",
        card_type="note",
        text="Clinic gate opens at 11:30 AM, use ramp entrance on right.",
        lat=22.5482,
        lon=88.3562,
        visibility="group",
        to_group="dadu-clinic",
        shade_at_creation=0.75
    )

