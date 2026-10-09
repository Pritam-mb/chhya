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
    CARD_ALLOWED_TYPES,
    CARD_PHOTO_MAX_BYTES,
    CHAT_MAX_CHARS,
    CHAT_POLL_LIMIT,
    POINTS_JOIN,
    POINTS_CHECKIN,
    POINTS_STORY_UNLOCK,
    POINTS_COMPLETION,
    STORY_UNLOCK_RADIUS_M,
    POSITION_STALE_S,
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trip_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_code TEXT NOT NULL,
                walker_name TEXT NOT NULL,
                is_system INTEGER DEFAULT 0,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_trip
            ON trip_messages (trip_code, id)
        """)
        # Photo attachments for cards (migrates existing databases)
        try:
            conn.execute("ALTER TABLE cards ADD COLUMN photo TEXT")
        except Exception:
            pass
        # Feed: public trip announcements (migrates existing databases)
        try:
            conn.execute("ALTER TABLE trips ADD COLUMN is_public INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE trips ADD COLUMN title TEXT")
        except Exception:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS walker_positions (
                trip_code TEXT NOT NULL,
                walker_name TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                timestamp TEXT NOT NULL,
                PRIMARY KEY (trip_code, walker_name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS grass_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_code TEXT NOT NULL,
                walker_name TEXT NOT NULL,
                points INTEGER NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS story_unlocks (
                card_id TEXT NOT NULL,
                walker_name TEXT NOT NULL,
                trip_code TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                PRIMARY KEY (card_id, walker_name)
            )
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
        cols = row.keys()
        return {
            "code": row["code"],
            "mode": row["mode"],
            "plan": json.loads(row["plan_json"]),
            "reached": bool(row["reached"]),
            "reached_at": row["reached_at"],
            "created_at": row["created_at"],
            "is_public": bool(row["is_public"]) if "is_public" in cols else False,
            "title": row["title"] if "title" in cols else None,
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
    photo: Optional[str] = None,
) -> Dict[str, Any]:
    cleaned_text, is_safe, status = clean_and_moderate_card_text(text)
    card_id = f"card_{datetime.datetime.now().strftime('%y%m%d%H%M%S')}_{os.urandom(3).hex()}"
    now = datetime.datetime.now()
    expires_at = (now + datetime.timedelta(hours=ttl_hours)).isoformat()

    # Photo attachments stay small and honest: data-URL images only, capped.
    clean_photo = None
    if photo and isinstance(photo, str) and photo.startswith("data:image/"):
        if len(photo) <= CARD_PHOTO_MAX_BYTES:
            clean_photo = photo
        else:
            status = "photo_too_large_dropped"

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO cards (id, trip_code, type, text, lat, lon, visibility, to_group, shade_at_creation, created_at, expires_at, hidden, photo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
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
            expires_at,
            clean_photo,
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
        "has_photo": clean_photo is not None,
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
            cols = r.keys()
            # Geo-locked stories: teaser only until the walker is close enough.
            locked = r["type"] == "story" and d > STORY_UNLOCK_RADIUS_M
            full_text = r["text"] or ""
            shown_text = (full_text[:24] + "… (locked — get closer)") if locked and full_text else full_text
            card_dict = {
                "id": r["id"],
                "type": r["type"],
                "text": shown_text,
                "locked": locked,
                "lat": r["lat"],
                "lon": r["lon"],
                "distance_m": round(d),
                "bearing": bearing,
                "is_immediate": d <= CARD_NEAR_RADIUS_M,
                "visibility": vis,
                "to_group": c_to,
                "shade_at_creation": r["shade_at_creation"],
                "created_at": r["created_at"],
                "has_photo": (bool(r["photo"]) and not locked) if "photo" in cols else False,
                # Full photo bytes only for immediate, unlocked cards; radar rows carry the flag.
                "photo": (r["photo"] if d <= CARD_NEAR_RADIUS_M and not locked else None) if "photo" in cols else None,
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


# ------------------------------------------------------------ Trip chat room
def clean_chat_text(text: str) -> str:
    """PII-stripped chat text capped at CHAT_MAX_CHARS (same rules as cards)."""
    cleaned = (text or "").strip()[:CHAT_MAX_CHARS]
    cleaned = re.sub(PHONE_REGEX, "[PHONE REMOVED]", cleaned)
    cleaned = re.sub(EMAIL_REGEX, "[EMAIL REMOVED]", cleaned)
    return cleaned


def post_trip_message(trip_code: str, walker_name: str, text: str, is_system: bool = False) -> Dict[str, Any]:
    now = datetime.datetime.now().isoformat()
    cleaned = clean_chat_text(text)
    if not cleaned:
        raise ValueError("Empty message.")
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO trip_messages (trip_code, walker_name, is_system, text, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (trip_code, walker_name[:40] or "Walker", 1 if is_system else 0, cleaned, now))
        conn.commit()
        msg_id = cur.lastrowid
    return {"id": msg_id, "trip_code": trip_code, "walker": walker_name[:40] or "Walker",
            "is_system": is_system, "text": cleaned, "timestamp": now}


def get_trip_messages(trip_code: str, since_id: int = 0, limit: int = CHAT_POLL_LIMIT) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, walker_name, is_system, text, timestamp
            FROM trip_messages
            WHERE trip_code = ? AND id > ?
            ORDER BY id ASC
            LIMIT ?
        """, (trip_code, since_id, limit)).fetchall()
        return [{"id": r["id"], "walker": r["walker_name"], "is_system": bool(r["is_system"]),
                 "text": r["text"], "timestamp": r["timestamp"]} for r in rows]


# ------------------------------------------------- Live positions + grass
def upsert_position(trip_code: str, walker_name: str, lat: float, lon: float) -> Dict[str, Any]:
    """Opt-in live spot sharing: one latest row per walker per trip."""
    now = datetime.datetime.now().isoformat()
    name = (walker_name or "Walker")[:40]
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO walker_positions (trip_code, walker_name, lat, lon, timestamp)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (trip_code, walker_name)
            DO UPDATE SET lat = excluded.lat, lon = excluded.lon, timestamp = excluded.timestamp
        """, (trip_code, name, float(lat), float(lon), now))
        conn.commit()
    return {"trip_code": trip_code, "walker": name, "lat": float(lat), "lon": float(lon), "timestamp": now}


def get_positions(trip_code: str) -> List[Dict[str, Any]]:
    now = datetime.datetime.now()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT walker_name, lat, lon, timestamp
            FROM walker_positions WHERE trip_code = ?
        """, (trip_code,)).fetchall()
        out = []
        for r in rows:
            try:
                age = (now - datetime.datetime.fromisoformat(r["timestamp"])).total_seconds()
            except Exception:
                age = 1e9
            out.append({"walker": r["walker_name"], "lat": r["lat"], "lon": r["lon"],
                        "timestamp": r["timestamp"], "stale": age > POSITION_STALE_S})
        return out


def award_points(trip_code: str, walker_name: str, points: int, reason: str) -> Dict[str, Any]:
    now = datetime.datetime.now().isoformat()
    name = (walker_name or "Walker")[:40]
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO grass_ledger (trip_code, walker_name, points, reason, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (trip_code, name, int(points), reason, now))
        conn.commit()
    return {"trip_code": trip_code, "walker": name, "points": int(points), "reason": reason}


def trip_leaderboard(trip_code: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT walker_name, SUM(points) AS points, COUNT(*) AS events
            FROM grass_ledger WHERE trip_code = ?
            GROUP BY walker_name ORDER BY points DESC
        """, (trip_code,)).fetchall()
        return [{"walker": r["walker_name"], "points": r["points"], "events": r["events"]} for r in rows]


def global_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT walker_name, SUM(points) AS points, COUNT(*) AS events
            FROM grass_ledger
            GROUP BY walker_name ORDER BY points DESC LIMIT ?
        """, (limit,)).fetchall()
        return [{"walker": r["walker_name"], "points": r["points"], "events": r["events"]} for r in rows]


def unlock_story(card_id: str, walker_name: str, trip_code: str, lat: float, lon: float) -> Dict[str, Any]:
    """Geo-locked story unlock: must be within STORY_UNLOCK_RADIUS_M, once per walker."""
    now_iso = datetime.datetime.now().isoformat()
    with get_connection() as conn:
        card = conn.execute("SELECT * FROM cards WHERE id = ? AND hidden = 0 AND expires_at > ?",
                            (card_id, now_iso)).fetchone()
        if not card:
            raise LookupError("Story not found or expired.")
        if card["type"] != "story":
            raise ValueError("Only story cards unlock for points.")
        cols = card.keys()
        photo = card["photo"] if "photo" in cols else None
        d = haversine_distance_m(lat, lon, card["lat"], card["lon"])
        if d > STORY_UNLOCK_RADIUS_M:
            return {"unlocked": False, "distance_m": round(d),
                    "need_m": STORY_UNLOCK_RADIUS_M,
                    "message": f"Get within {STORY_UNLOCK_RADIUS_M:.0f} m to unlock this story."}
        name = (walker_name or "Walker")[:40]
        already = conn.execute("SELECT 1 FROM story_unlocks WHERE card_id = ? AND walker_name = ?",
                               (card_id, name)).fetchone()
        if already:
            return {"unlocked": True, "already": True, "distance_m": round(d),
                    "text": card["text"], "photo": photo, "points": 0}
        conn.execute("INSERT INTO story_unlocks (card_id, walker_name, trip_code, timestamp) VALUES (?, ?, ?, ?)",
                     (card_id, name, trip_code, now_iso))
        conn.commit()
    award = award_points(trip_code, name, POINTS_STORY_UNLOCK, f"story:{card_id}")
    return {"unlocked": True, "already": False, "distance_m": round(d),
            "text": card["text"], "photo": photo, "points": award["points"]}


# ------------------------------------------------------- Feed: publish/join
def publish_trip(code: str, title: str) -> bool:
    clean = (title or "").strip()[:80]
    if not clean:
        raise ValueError("Feed posts need a title.")
    with get_connection() as conn:
        cur = conn.execute("UPDATE trips SET is_public = 1, title = ? WHERE code = ?", (clean, code))
        conn.commit()
        return cur.rowcount > 0


def join_trip(code: str, walker_name: str) -> Dict[str, Any]:
    """Adds a walker to the plan's walker list without touching reached state."""
    import json
    name = (walker_name or "Walker").strip()[:40] or "Walker"
    with get_connection() as conn:
        row = conn.execute("SELECT plan_json FROM trips WHERE code = ?", (code,)).fetchone()
        if not row:
            raise LookupError("Trip not found.")
        plan = json.loads(row["plan_json"])
        walkers = plan.get("walkers") or []
        if not any((w.get("name", "").lower() == name.lower()) for w in walkers if isinstance(w, dict)):
            walkers.append({"name": name, "sun_sensitivity": "normal", "pace": "normal"})
            plan["walkers"] = walkers
            conn.execute("UPDATE trips SET plan_json = ? WHERE code = ?", (json.dumps(plan), code))
            conn.commit()
            award = award_points(code, name, POINTS_JOIN, "join")
        else:
            award = {"points": 0, "reason": "already-joined"}
    post_trip_message(code, name, "joined the group", is_system=True)
    return {"trip_code": code, "walker": name, "walkers": walkers, "points": award["points"]}


def trip_category(distance_m: float) -> str:
    if distance_m < 1000:
        return "Short stroll"
    if distance_m < 3000:
        return "Medium march"
    return "Long haul"


def get_feed(limit: int = 20) -> List[Dict[str, Any]]:
    import json
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT code, mode, plan_json, title, created_at
            FROM trips WHERE is_public = 1 ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        feed = []
        for r in rows:
            try:
                plan = json.loads(r["plan_json"])
            except Exception:
                continue
            dist = float(plan.get("distance_meters") or 0)
            stops = plan.get("stops") or []
            food = sum(1 for s in stops if isinstance(s, dict) and s.get("kind") == "cafe")
            feed.append({
                "trip_code": r["code"],
                "title": r["title"],
                "mode": r["mode"],
                "from": (plan.get("origin") or {}).get("name"),
                "to": (plan.get("destination") or {}).get("name"),
                "distance_m": round(dist),
                "category": trip_category(dist),
                "shade_percentage": plan.get("shade_percentage"),
                "sun_minutes": plan.get("sun_minutes"),
                "walkers": [w.get("name") for w in (plan.get("walkers") or []) if isinstance(w, dict)],
                "food_stops": food,
                "package": "food package" if food else "carry water",
                "created_at": r["created_at"],
            })
        return feed


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

