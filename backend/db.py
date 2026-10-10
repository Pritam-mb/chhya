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


def get_unlocked_stories(walker_name: str) -> List[Dict[str, Any]]:
    name = (walker_name or "Walker").strip()[:40] or "Walker"
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.id, c.trip_code, c.text, c.lat, c.lon, c.photo, c.shade_at_creation, u.timestamp
            FROM story_unlocks u
            JOIN cards c ON u.card_id = c.id
            WHERE u.walker_name = ?
            ORDER BY u.timestamp DESC
        """, (name,)).fetchall()
        return [
            {
                "card_id": r["id"],
                "trip_code": r["trip_code"],
                "text": r["text"],
                "lat": r["lat"],
                "lon": r["lon"],
                "photo": r["photo"],
                "shade_at_creation": r["shade_at_creation"],
                "unlocked_at": r["timestamp"],
            }
            for r in rows
        ]


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
            ag = plan.get("agenda") or ("help" if r["mode"] == "family" else ("self" if r["mode"] == "trail" else "hike"))
            feed.append({
                "trip_code": r["code"],
                "title": r["title"],
                "mode": r["mode"],
                "agenda": ag,
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
    try:
        from backend.routing import get_routing_engine
        _eng = get_routing_engine()
        dadu_plan["route_data"] = _eng.plan_route("poi_dadu_home", "poi_clinic_bellevue", "08:30", sun_tolerance="low")
    except Exception:
        pass
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
    try:
        club_plan["route_data"] = _eng.plan_route("poi_flurys", "poi_camac_square", "16:00", sun_tolerance="normal")
    except Exception:
        pass
    save_trip("parkst-club", "club", club_plan)

    # 3. Heritage Food Trail (Short stroll with Food Package)
    food_trail_plan = {
        "mode": "club",
        "trip_code": "heritage-food-trail",
        "title": "Bow Barracks & Heritage Shaded Food Trail",
        "status": "simulated",
        "walkers": [
            {"name": "Suman (Lead)", "sun_sensitivity": "normal", "pace_kmh": 3.8},
            {"name": "Trisha", "sun_sensitivity": "high", "pace_kmh": 3.2},
            {"name": "Walker", "sun_sensitivity": "normal", "pace_kmh": 4.0}
        ],
        "origin": {"name": "Bow Barracks Historic Quarter", "lat": 22.5535, "lon": 88.3510},
        "destination": {"name": "New Market Shaded Arcade", "lat": 22.5490, "lon": 88.3540},
        "depart_time": "15:30",
        "effective_budgets": {"high": 5.0, "normal": 14.0},
        "sun_minutes": 2.2,
        "baseline_sun_minutes": 8.0,
        "sun_minutes_saved": 5.8,
        "shade_percentage": 82.0,
        "distance_meters": 1180,
        "stops": [
            {
                "stop_index": 1,
                "name": "Anglo-Indian Heritage Bakery",
                "kind": "cafe",
                "lat": 22.5525,
                "lon": 88.3530,
                "cumulative_walk_min": 6.0,
                "arrival_time": "15:36",
                "shade_at_arrival": 0.88,
                "description": "Hot freshly baked coconut patties & shaded courtyard"
            },
            {
                "stop_index": 2,
                "name": "Free School St Shaded Juicery",
                "kind": "cafe",
                "lat": 22.5508,
                "lon": 88.3535,
                "cumulative_walk_min": 12.0,
                "arrival_time": "15:42",
                "shade_at_arrival": 0.80,
                "description": "Cold sugarcane juice under deep awning"
            }
        ],
        "share_message": "Bow Barracks food trail: 82% shaded, hot patties at Stop 1 and cold juice at Stop 2."
    }
    try:
        food_trail_plan["route_data"] = _eng.plan_route("poi_oxford", "poi_camac_square", "15:30", sun_tolerance="normal")
    except Exception:
        pass
    save_trip("heritage-food-trail", "club", food_trail_plan)

    # 4. Rabindra Sarobar Lake Trek (Long haul with Hydration Package)
    lake_trek_plan = {
        "mode": "trail",
        "trip_code": "sarobar-lake-trek",
        "title": "Rabindra Sarobar Canopy & Lake Trek",
        "status": "simulated",
        "walkers": [
            {"name": "Rahul (Scout)", "sun_sensitivity": "normal", "pace_kmh": 5.0},
            {"name": "Priya", "sun_sensitivity": "normal", "pace_kmh": 4.5},
            {"name": "Vikram", "sun_sensitivity": "low", "pace_kmh": 5.2}
        ],
        "origin": {"name": "Southern Avenue Shaded Gate", "lat": 22.5540, "lon": 88.3505},
        "destination": {"name": "Lakeside Memorial Walk", "lat": 22.5460, "lon": 88.3570},
        "depart_time": "08:00",
        "effective_budgets": {"normal": 20.0, "low": 35.0},
        "sun_minutes": 5.1,
        "baseline_sun_minutes": 18.5,
        "sun_minutes_saved": 13.4,
        "shade_percentage": 78.0,
        "distance_meters": 4850,
        "stops": [
            {
                "stop_index": 1,
                "name": "Green Coconut Shaded Stand",
                "kind": "shelter",
                "lat": 22.5510,
                "lon": 88.3530,
                "cumulative_walk_min": 16.0,
                "arrival_time": "08:16",
                "shade_at_arrival": 0.85,
                "description": "Coconut water and giant banyan canopy"
            }
        ],
        "share_message": "Sarobar morning canopy trek: 78% shaded tree-lined lake route, 4.8 km."
    }
    try:
        # Use flurys→camac_square to simulate a longer shaded lake-loop route within graph area
        lake_trek_plan["route_data"] = _eng.plan_route("poi_flurys", "poi_camac_square", "08:00", sun_tolerance="low")
    except Exception:
        pass
    save_trip("sarobar-lake-trek", "trail", lake_trek_plan)

    # 5. College Street Boi Para Passage (Self Travel / Heritage Literature stroll)
    collegest_plan = {
        "mode": "trail",
        "trip_code": "collegest-trail",
        "title": "College Street Boi Para & Coffee House Passage",
        "agenda": "self",
        "status": "simulated",
        "walkers": [
            {"name": "Anirban (Reader)", "sun_sensitivity": "normal", "pace_kmh": 3.6},
            {"name": "Debjani", "sun_sensitivity": "normal", "pace_kmh": 4.0}
        ],
        "origin": {"name": "Presidency Gate (College St)", "lat": 22.5538, "lon": 88.3515},
        "destination": {"name": "Indian Coffee House Balcony", "lat": 22.5488, "lon": 88.3535},
        "depart_time": "16:30",
        "effective_budgets": {"normal": 16.0},
        "sun_minutes": 2.9,
        "baseline_sun_minutes": 9.4,
        "sun_minutes_saved": 6.5,
        "shade_percentage": 76.0,
        "distance_meters": 1420,
        "stops": [
            {
                "stop_index": 1,
                "name": "Century-Old Wooden Book Kiosks",
                "kind": "shelter",
                "lat": 22.5522,
                "lon": 88.3519,
                "cumulative_walk_min": 7.0,
                "arrival_time": "16:37",
                "shade_at_arrival": 0.84,
                "description": "Sheltered tin awnings with rare Bengali paperbacks and second-hand prints"
            },
            {
                "stop_index": 2,
                "name": "Indian Coffee House Shaded Verandah",
                "kind": "cafe",
                "lat": 22.5495,
                "lon": 88.3532,
                "cumulative_walk_min": 14.0,
                "arrival_time": "16:44",
                "shade_at_arrival": 0.88,
                "description": "Historic shaded verandah with infusion coffee and chicken cutlet"
            }
        ],
        "share_message": "College St Boi Para passage: 76% shaded heritage book corridor, infusion coffee at finish."
    }
    try:
        # College Street passage: oxford→bellevue clinic corridor mirrors real heritage book-lane direction
        collegest_plan["route_data"] = _eng.plan_route("poi_oxford", "poi_clinic_bellevue", "16:30", sun_tolerance="normal")
    except Exception:
        pass
    save_trip("collegest-trail", "trail", collegest_plan)

    # Publish groups to Feed when running in live app (not during empty-feed unit tests)
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        publish_trip("parkst-club", "Park Street Sun-Smart Trail Club")
        publish_trip("dadu-clinic", "Dadu's Morning Shaded Clinic Walk")
        publish_trail = publish_trip("heritage-food-trail", "Bow Barracks Heritage Shaded Food Trail")
        publish_lake = publish_trip("sarobar-lake-trek", "Rabindra Sarobar Canopy & Lake Trek")
        publish_college = publish_trip("collegest-trail", "College Street Boi Para & Coffee House Passage")

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

    # Seed Individualized Group Chat Messages
    with get_connection() as conn:
        conn.execute("DELETE FROM trip_messages WHERE trip_code IN ('parkst-club', 'dadu-clinic', 'heritage-food-trail', 'sarobar-lake-trek', 'collegest-trail')")
        conn.commit()

    post_trip_message("parkst-club", "Aarav (Lead)", "Everyone ready at Flurys? We are taking the shaded colonnade route.")
    post_trip_message("parkst-club", "Ananya", "Sun is fierce today on Park Street, sticking strictly to the chhaya path!")
    post_trip_message("parkst-club", "Rina", "Hey I am taking a rest, I will continue shortly! Caught some breath at the chai stall bench.")
    post_trip_message("parkst-club", "Kabir", "Take your time Rina! There is 85% continuous canopy here, we'll regroup at Stop 2.")

    post_trip_message("dadu-clinic", "Pritam", "Leaving home with Dadu at 11:40 AM.")
    post_trip_message("dadu-clinic", "Dadu", "Middleton Row bench is breezy and cool. Resting 5 minutes.")

    post_trip_message("heritage-food-trail", "Suman (Lead)", "First stop at Anglo-Indian bakery for hot coconut patties!")
    post_trip_message("heritage-food-trail", "Trisha", "Deep shade between the red brick buildings. Loving this trail.")

    post_trip_message("collegest-trail", "Anirban (Reader)", "Starting from Presidency Gate. Taking the shaded wooden stall lane.")
    post_trip_message("collegest-trail", "Debjani", "Browsing vintage poetry prints under the 84% shade awnings. Meet at Coffee House!")

    # 5. Seeded Story & Tip Cards (Multi-Group pinned notes with photos & paragraphs)
    with get_connection() as conn:
        conn.execute("DELETE FROM cards WHERE id LIKE 'seed_%'")
        conn.commit()

    # Story photo: Rich SVG data URI of Kolkata heritage shaded banyan tree
    banyan_photo = (
        "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 380' width='100%' height='100%'>"
        "<rect width='600' height='380' fill='%23F4E9D4'/>"
        "<rect x='20' y='20' width='560' height='340' fill='%23E8D6B5' stroke='%232A1F17' stroke-width='3'/>"
        "<path d='M40 330 Q 300 310 560 330 L 560 360 L 40 360 Z' fill='%232A1F17'/>"
        "<path d='M260 330 C 270 240, 230 180, 180 120 C 230 140, 280 200, 300 240 C 320 180, 380 140, 440 100 C 380 160, 330 220, 340 330 Z' fill='%232A1F17'/>"
        "<ellipse cx='200' cy='90' rx='140' ry='65' fill='%231F4D3A'/>"
        "<ellipse cx='320' cy='70' rx='160' ry='60' fill='%23173D2E'/>"
        "<ellipse cx='430' cy='95' rx='130' ry='55' fill='%231F4D3A'/>"
        "<ellipse cx='300' cy='110' rx='190' ry='70' fill='%235E8C6A' opacity='0.9'/>"
        "<line x1='160' y1='120' x2='160' y2='330' stroke='%232A1F17' stroke-width='4'/>"
        "<line x1='220' y1='140' x2='210' y2='330' stroke='%232A1F17' stroke-width='3.5'/>"
        "<line x1='380' y1='130' x2='390' y2='330' stroke='%232A1F17' stroke-width='3.5'/>"
        "<line x1='440' y1='110' x2='450' y2='330' stroke='%232A1F17' stroke-width='4'/>"
        "<rect x='140' y='270' width='90' height='40' rx='4' fill='%23B8553A' stroke='%232A1F17' stroke-width='2.5'/>"
        "<text x='185' y='295' font-family='serif' font-size='12' font-weight='bold' fill='%23FBF7EE' text-anchor='middle'>CHAI BENCH</text>"
        "<circle cx='500' cy='65' r='28' fill='%23F2A900' opacity='0.4'/>"
        "<text x='300' y='348' font-family='monospace' font-size='12' font-weight='bold' fill='%23FBF7EE' text-anchor='middle'>PARK ST · 110-YR BANYAN CANOPY · 92% SHADE</text></svg>"
    )

    bakery_photo = (
        "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 380' width='100%' height='100%'>"
        "<rect width='600' height='380' fill='%23F4E9D4'/>"
        "<rect x='20' y='20' width='560' height='340' fill='%23E8D6B5' stroke='%232A1F17' stroke-width='3'/>"
        "<rect x='60' y='60' width='480' height='260' fill='%23B8553A' stroke='%232A1F17' stroke-width='3'/>"
        "<path d='M100 60 L180 180 L100 180 Z' fill='%232A1F17'/>"
        "<rect x='160' y='120' width='280' height='160' rx='8' fill='%23FBF7EE' stroke='%232A1F17' stroke-width='3'/>"
        "<text x='300' y='170' font-family='serif' font-size='20' font-weight='bold' fill='%23B8553A' text-anchor='middle'>BOW BARRACKS BAKERY</text>"
        "<text x='300' y='210' font-family='serif' font-size='14' fill='%232A1F17' text-anchor='middle'>Fresh Coconut Patties &amp; Walnut Cake</text>"
        "<circle cx='300' cy='250' r='18' fill='%23F2A900'/>"
        "<text x='300' y='255' font-family='monospace' font-size='12' font-weight='bold' fill='%232A1F17' text-anchor='middle'>EST. 1942</text>"
        "<text x='300' y='350' font-family='monospace' font-size='12' font-weight='bold' fill='%232A1F17' text-anchor='middle'>HERITAGE SHADED LANE · 88% SHADE</text></svg>"
    )

    create_card(
        trip_code="parkst-club",
        card_type="story",
        text="110-Year-Old Heritage Banyan Canopy: Offers 92% continuous shade. Fresh breeze and clay cups of Elaichi Chai right across the alley. Rest here to recover before the sunlit crossing.",
        lat=22.5518,
        lon=88.3518,
        visibility="public",
        shade_at_creation=0.92,
        photo=banyan_photo
    )

    create_card(
        trip_code="heritage-food-trail",
        card_type="story",
        text="Bow Barracks Anglo-Indian Bakery: Fresh hot coconut patties and walnut cake baked since 1942. Hidden in a shaded lane that stays cool all noon.",
        lat=22.5525,
        lon=88.3530,
        visibility="public",
        shade_at_creation=0.88,
        photo=bakery_photo
    )

    create_card(
        trip_code="dadu-clinic",
        card_type="tip",
        text="Deep continuous shade along Middleton Row colonnade. Rest benches available.",
        lat=22.5516,
        lon=88.3522,
        visibility="public",
        shade_at_creation=0.82
    )

    collegest_photo = (
        "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 380' width='100%' height='100%'>"
        "<rect width='600' height='380' fill='%23F4E9D4'/>"
        "<rect x='20' y='20' width='560' height='340' fill='%23E8D6B5' stroke='%232A1F17' stroke-width='3'/>"
        "<rect x='50' y='60' width='500' height='260' fill='%231F4D3A' stroke='%232A1F17' stroke-width='3'/>"
        "<text x='300' y='110' font-family='serif' font-size='22' font-weight='bold' fill='%23FBF7EE' text-anchor='middle'>COLLEGE STREET BOI PARA</text>"
        "<text x='300' y='140' font-family='sans-serif' font-size='14' fill='%23F2A900' text-anchor='middle'>World Largest Second-Hand Book Market · Est. 1817</text>"
        "<rect x='100' y='170' width='180' height='120' rx='6' fill='%23B8553A' stroke='%232A1F17' stroke-width='2'/>"
        "<text x='190' y='210' font-family='serif' font-size='15' font-weight='bold' fill='%23FBF7EE' text-anchor='middle'>BOOK STALL #14</text>"
        "<text x='190' y='240' font-family='sans-serif' font-size='12' fill='%23FBF7EE' text-anchor='middle'>Under Canvas Awning</text>"
        "<rect x='320' y='170' width='180' height='120' rx='6' fill='%23FBF7EE' stroke='%232A1F17' stroke-width='2'/>"
        "<text x='410' y='210' font-family='serif' font-size='15' font-weight='bold' fill='%232A1F17' text-anchor='middle'>COFFEE HOUSE</text>"
        "<text x='410' y='240' font-family='monospace' font-size='12' fill='%23C8321E' text-anchor='middle'>Hot Infusion Coffee</text>"
        "<text x='300' y='350' font-family='monospace' font-size='12' font-weight='bold' fill='%232A1F17' text-anchor='middle'>HERITAGE SHADED VERANDAH · 88% SHADE</text></svg>"
    )

    create_card(
        trip_code="collegest-trail",
        card_type="story",
        text="College Street Wooden Kiosks: Endless stacks of books sheltered beneath wide green tin awnings. Smell of old paper and shade that keeps the temperature 4 degrees cooler than the main street.",
        lat=22.5522,
        lon=88.3519,
        visibility="public",
        shade_at_creation=0.88,
        photo=collegest_photo
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

    # Seed grass points for walkers
    award_points("parkst-club", "Aarav (Lead)", 85, "leader")
    award_points("parkst-club", "Kabir", 60, "regular")
    award_points("parkst-club", "Ananya", 50, "regular")
    award_points("parkst-club", "Dev", 45, "regular")
    award_points("parkst-club", "Rina", 35, "regular")
    award_points("parkst-club", "Walker", 40, "starter")

