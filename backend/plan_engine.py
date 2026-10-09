"""
Unified Plan Engine for Chhaya.
Implements Rule 3 (One engine, three presets: Family, Club, Trail)
and Section 4, P0 (Plan Builder, Weather Budget, Start Sweep, Rest Stops, Share Message).
"""
import os
import re
import json
import random
import datetime
from typing import Dict, List, Any, Optional

from backend.config import (
    BASE_SUN_BUDGET_MIN,
    PACE_KMH,
    REST_STOP_EVERY_MIN,
    REST_STOP_MIN_SHADE,
    GROQ_MODEL,
    GROQ_API_KEY,
)
from backend.weather import get_weather_adjusted_budget
from backend.routing import get_routing_engine
from backend.start_sweep import sweep_start_times
from backend.rest_stops import find_rest_stops
from backend.db import save_trip


def parse_message_to_constraints(message: str) -> Dict[str, Any]:
    """
    Parses natural language walking requests into structured JSON constraints.
    Tries open LLM (Groq or Ollama) with strict JSON output, and falls back to deterministic regex parser.
    Fulfills Section 4, P0.1.
    """
    # 1. Try Groq open-weight LLM if available
    if GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            prompt = f"""You are Chhaya's constraint parser. Parse this walking request into JSON matching this exact schema:
{{
  "mode": "family" | "club" | "trail",
  "start_window": {{"date": "YYYY-MM-DD", "earliest": "HH:MM", "latest": "HH:MM"}},
  "walkers": [{{"name": string, "sun_sensitivity": "high"|"normal"|"low", "pace": "slow"|"normal"|"fast"}}],
  "destinations": [{{"text": string}}],
  "origin": string or null,
  "requests": [string],
  "sun_budget_min": number or null
}}
Rules:
- Infer mode: "family" if mentions elder, dadu, baby, patient; "club" if group of friends, runners, or multiple people; "trail" if hike or gpx.
- Unknown fields MUST be null, never guess.
- Return ONLY raw JSON without markdown or commentary.

Request: "{message}"
"""
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            content = resp.choices[0].message.content
            parsed = json.loads(content)
            parsed["parser_engine"] = f"Groq {GROQ_MODEL}"
            parsed["parsed_with_fallback"] = False
            return _normalize_parsed_schema(parsed, message)
        except Exception as e:
            print(f"LLM parsing failed ({e}), falling back to deterministic parser...")

    # 2. Fallback: Deterministic Regex Parser
    return _deterministic_parse(message)


def _deterministic_parse(message: str) -> Dict[str, Any]:
    text = message.lower().strip()

    # Mode detection
    mode = "family"
    if any(k in text for k in ["club", "group", "us", "friends", "team", "runners", "loop", "pack"]):
        mode = "club"
    elif any(k in text for k in ["trail", "hike", "gpx", "nature"]):
        mode = "trail"

    # Walkers detection
    walkers = []
    if any(k in text for k in ["dadu", "grandpa", "elder", "nana", "dadi", "senior"]):
        walkers.append({"name": "Dadu", "sun_sensitivity": "high", "pace": "slow"})
    elif any(k in text for k in ["baby", "child"]):
        walkers.append({"name": "Child", "sun_sensitivity": "high", "pace": "slow"})

    # Check for group count: e.g. "6 of us"
    cnt_match = re.search(r'(\d+)\s*(?:of us|people|walkers|runners|members)', text)
    if cnt_match:
        count = int(cnt_match.group(1))
        # Add default walkers for club
        if not walkers:
            walkers.append({"name": "Lead", "sun_sensitivity": "normal", "pace": "normal"})
        for i in range(len(walkers), min(count, 8)):
            walkers.append({"name": f"Walker {i+1}", "sun_sensitivity": "normal", "pace": "normal"})

    # Name mentions: e.g. "Rina wants chai"
    if "rina" in text and not any(w["name"] == "Rina" for w in walkers):
        walkers.append({"name": "Rina", "sun_sensitivity": "high", "pace": "slow"})

    if not walkers:
        walkers.append({"name": "Walker", "sun_sensitivity": "high" if "sun" in text else "normal", "pace": "slow" if mode == "family" else "normal"})

    # Start Window Detection
    today = datetime.date.today().isoformat()
    earliest = "11:30"
    latest = "12:30"

    # Explicit time detection
    hhmm = re.search(r'\b(\d{1,2}):(\d{2})\s*(am|pm)?\b', text)
    hmer = re.search(r'\b(\d{1,2})\s*(am|pm)\b', text)

    def _fmt(hr, mn, mer):
        if mer == "pm" and hr < 12: hr += 12
        elif mer == "am" and hr == 12: hr = 0
        return f"{hr:02d}:{mn:02d}"

    if hhmm:
        mid_time = _fmt(int(hhmm.group(1)), int(hhmm.group(2)), hhmm.group(3))
        h, m = map(int, mid_time.split(":"))
        earliest = f"{max(6, h-1):02d}:30"
        latest = f"{min(18, h+1):02d}:30"
    elif hmer:
        mid_time = _fmt(int(hmer.group(1)), 0, hmer.group(2))
        h, m = map(int, mid_time.split(":"))
        earliest = f"{max(6, h):02d}:00"
        latest = f"{min(18, h+1):02d}:00"
    elif "noon" in text or "12" in text:
        earliest, latest = "11:30", "12:30"
    elif "morning" in text:
        earliest, latest = "08:30", "10:30"
    elif "evening" in text or "afternoon" in text or "4" in text:
        earliest, latest = "15:30", "16:30"

    # Destination & Origin text
    dest_text = "clinic"
    origin_text = "home"

    if "camac" in text:
        dest_text = "Camac Street Mall & Offices"
        origin_text = "Flurys Tea Room"
    elif "clinic" in text or "doctor" in text or "hospital" in text:
        dest_text = "Belle Vue Clinic"
        origin_text = "Dadu's Residence (Middleton Row)"
    elif "pharmacy" in text or "market" in text:
        dest_text = "Russell Street Market & Pharmacy"
        origin_text = "Oxford Bookstore"
    elif "oxford" in text or "books" in text:
        dest_text = "Oxford Bookstore"

    return {
        "mode": mode,
        "start_window": {"date": today, "earliest": earliest, "latest": latest},
        "walkers": walkers,
        "destinations": [{"text": dest_text}],
        "origin": origin_text,
        "requests": ["chai"] if "chai" in text else [],
        "sun_budget_min": None,
        "parser_engine": "Deterministic Regex Parser",
        "parsed_with_fallback": True,
    }


def _normalize_parsed_schema(parsed: Dict[str, Any], raw_message: str) -> Dict[str, Any]:
    if not parsed.get("mode"):
        parsed["mode"] = "family" if "dadu" in raw_message.lower() else "club"
    if not parsed.get("start_window"):
        parsed["start_window"] = {"date": datetime.date.today().isoformat(), "earliest": "11:30", "latest": "12:30"}
    if not parsed.get("walkers"):
        parsed["walkers"] = [{"name": "Walker", "sun_sensitivity": "high", "pace": "slow"}]
    if not parsed.get("destinations"):
        parsed["destinations"] = [{"text": "Belle Vue Clinic"}]
    return parsed


def build_trip_plan(
    parsed_constraints: Dict[str, Any],
    user_origin_override: Optional[str] = None,
    user_destination_override: Optional[str] = None,
    user_mode_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Core planning engine that builds a full sun-aware trip plan.
    Fulfills Section 4, P0.3 & Section 3 (One engine, three presets).
    """
    mode = user_mode_override or parsed_constraints.get("mode", "family")
    walkers = parsed_constraints.get("walkers", [{"name": "Walker", "sun_sensitivity": "high", "pace": "slow"}])
    start_window = parsed_constraints.get("start_window", {"earliest": "11:30", "latest": "12:30"})
    earliest_time = start_window.get("earliest", "11:30")
    latest_time = start_window.get("latest", "12:30")

    # Determine pacing & sensitivity constraints
    paces = [PACE_KMH.get(w.get("pace", "normal"), PACE_KMH["normal"]) for w in walkers]
    slowest_pace_kmh = min(paces) if paces else PACE_KMH["slow"]

    # Strictest sun budget
    sensitivities = [w.get("sun_sensitivity", "normal") for w in walkers]
    has_high_sensitivity = any(s == "high" for s in sensitivities)
    strictest_sensitivity = "high" if has_high_sensitivity else ("normal" if any(s == "normal" for s in sensitivities) else "low")

    # Resolve locations against preloaded POI index
    routing = get_routing_engine()
    raw_dest = user_destination_override or (parsed_constraints.get("destinations", [{}])[0].get("text", "Belle Vue Clinic"))
    raw_origin = user_origin_override or parsed_constraints.get("origin") or "Dadu's Residence (Middleton Row)"

    origin_resolved = routing.resolve_location(raw_origin) or routing.resolve_location("home") or (88.3524, 22.5512, "Dadu's Residence (Middleton Row)")
    dest_resolved = routing.resolve_location(raw_dest) or routing.resolve_location("clinic") or (88.3562, 22.5482, "Belle Vue Clinic")

    origin_name = origin_resolved[2]
    dest_name = dest_resolved[2]

    # Weather-adjusted sun budget for earliest time
    weather_adj = get_weather_adjusted_budget(
        sun_sensitivity=strictest_sensitivity,
        time_str=earliest_time,
        date_str=start_window.get("date"),
    )
    effective_budget = weather_adj["effective_budget_min"]

    # Compute best start time sweep across window
    sweep_res = sweep_start_times(
        origin=origin_name,
        destination=dest_name,
        earliest_time=earliest_time,
        latest_time=latest_time,
        speed_kmh=slowest_pace_kmh,
        effective_budget_min=effective_budget,
        step_minutes=10,
    )

    best_start = sweep_res["best_start_time"]
    best_route_data = sweep_res.get("best_route_data")

    # If sweep did not produce route, run direct route plan
    if not best_route_data:
        best_route_data = routing.plan_route(
            origin_query=origin_name,
            destination_query=dest_name,
            depart_time_str=best_start,
            sun_tolerance="low" if has_high_sensitivity else "normal",
            speed_kmh=slowest_pace_kmh,
        )

    shade_route = best_route_data["shade_route"]
    shortest_route = best_route_data["shortest_route"]

    # Rest stop frequency
    # Family mode: rest stops for the slow walker every rest_every_min (default 8)
    # Club mode: regroup stops
    rest_interval = 8 if mode in ["family", "trail"] else 12
    route_coords = shade_route.get("coordinates", [])

    stops = find_rest_stops(
        route_coords=route_coords,
        start_time_str=best_start,
        pace_kmh=slowest_pace_kmh,
        rest_every_min=rest_interval,
        min_shade_threshold=REST_STOP_MIN_SHADE,
    )

    # Add final destination as the closing stop
    stops.append({
        "stop_index": len(stops) + 1,
        "id": "dest_arrival",
        "name": dest_name,
        "kind": "destination",
        "lat": dest_resolved[1],
        "lon": dest_resolved[0],
        "cumulative_dist_m": shade_route.get("distance_meters", 600),
        "cumulative_walk_min": shade_route.get("duration_minutes", 12.0),
        "arrival_time": best_route_data.get("arrival_time", "12:00"),
        "shade_at_arrival": 0.75,
        "approximate": False,
        "description": "Final destination arrival",
    })

    # Generate shareable message from pure numbers (Section 4, P0.6)
    sun_mins = shade_route.get("sun_minutes", 3.0)
    base_sun_mins = shortest_route.get("sun_minutes", 8.0)
    shade_pct = shade_route.get("shade_percentage", 65.0)
    sun_saved = round(max(0.0, base_sun_mins - sun_mins), 1)

    rest_note = ""
    if len(stops) > 1 and mode == "family":
        rest_note = f" Rest on the shaded bench at the {round(stops[0]['cumulative_walk_min'])}-minute mark."
    elif len(stops) > 1 and mode == "club":
        rest_note = f" Chai regroup stop at the {round(stops[0]['cumulative_walk_min'])}-minute mark."

    trip_code = f"trip-{random.randint(1000, 9999)}"

    if mode == "family":
        share_msg = (
            f"Dadu's clinic walk: leave {best_start}, {shade_pct}% shaded, "
            f"about {sun_mins} sun-minutes against {base_sun_mins} on the shortest path.{rest_note} "
            f"Link: /t/{trip_code}"
        )
    elif mode == "club":
        share_msg = (
            f"Sun-smart walk, {origin_name} to {dest_name}. Meet {best_start}. "
            f"{shade_pct}% shaded, {sun_mins} sun-minutes vs {base_sun_mins}.{rest_note} "
            f"Link: /t/{trip_code}"
        )
    else: # trail
        share_msg = (
            f"Trail hike: depart {best_start}, {shade_pct}% shaded, "
            f"{sun_mins} sun-minutes vs {base_sun_mins}. Turnaround buffer: 30 min before sunset. "
            f"Link: /t/{trip_code}"
        )

    plan_result = {
        "trip_code": trip_code,
        "mode": mode,
        "status": "planned",
        "walkers": walkers,
        "origin": {"name": origin_name, "lat": origin_resolved[1], "lon": origin_resolved[0]},
        "destination": {"name": dest_name, "lat": dest_resolved[1], "lon": dest_resolved[0]},
        "start_window": start_window,
        "best_start_time": best_start,
        "slowest_pace_kmh": slowest_pace_kmh,
        "strictest_sensitivity": strictest_sensitivity,
        "weather_adjusted_budget": weather_adj,
        "effective_budgets": {
            "high": weather_adj["effective_budget_min"],
            "normal": round(BASE_SUN_BUDGET_MIN["normal"] * weather_adj["weather_factor"], 1),
            "low": round(BASE_SUN_BUDGET_MIN["low"] * weather_adj["weather_factor"], 1),
        },
        "sun_minutes": sun_mins,
        "baseline_sun_minutes": base_sun_mins,
        "sun_minutes_saved": sun_saved,
        "shade_percentage": shade_pct,
        "duration_minutes": shade_route.get("duration_minutes", 12.0),
        "distance_meters": shade_route.get("distance_meters", 600),
        "has_comfortable_window": sweep_res["has_comfortable_window"],
        "budget_warning": sweep_res["warning_message"],
        "start_time_curve": sweep_res["curve"],
        "stops": stops,
        "route_data": best_route_data,
        "share_message": share_msg,
        "created_at": datetime.datetime.now().isoformat(),
    }

    # Save to persistent SQLite
    save_trip(trip_code, mode, plan_result)

    return plan_result
