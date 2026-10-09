import os
import sys
import datetime
from typing import Dict, Any, Optional, List

# Allow `python backend/main.py` from a fresh clone (repo root on sys.path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.geo_shadows import get_shadow_engine, calculate_solar_position
from backend.routing import get_routing_engine
from backend.agent import get_agent, TOOL_REGISTRY, init_sentry
from backend.best_window import get_window_model
from backend.voice import synthesize_briefing_audio
from backend.weather import get_weather_adjusted_budget, fetch_forecast_data
from backend.plan_engine import parse_message_to_constraints, build_trip_plan
from backend.repair_engine import detect_and_repair_stragglers
from backend.config import KOLKATA_CENTER_LAT, KOLKATA_CENTER_LON
from backend.db import (
    init_db,
    seed_demo_data,
    save_trip,
    get_trip,
    mark_trip_reached,
    record_checkin,
    get_trip_checkins,
    record_observation,
    get_accuracy_summary,
    create_card,
    find_nearby_cards,
    report_and_hide_card,
    generate_trip_qr_base64,
)

app = FastAPI(
    title="Chhaya API",
    description="Kolkata Shade-Aware Navigation, Multi-Mode Planning & Straggler Repair Engine",
    version="2.0.0"
)

# Initialise Sentry as early as possible
init_sentry()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auto-seed database at startup
@app.on_event("startup")
def on_startup():
    init_db()
    seed_demo_data()


# --------------------------------------------------------------------- Request Models
class RouteRequest(BaseModel):
    origin: str
    destination: str
    depart_time: Optional[str] = "15:00"
    sun_tolerance: Optional[str] = "low"
    speed_kmh: Optional[float] = 3.0

class ChatRequest(BaseModel):
    message: str
    depart_time: Optional[str] = None
    sun_tolerance: Optional[str] = None

class VoiceRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None

class PlanApiRequest(BaseModel):
    message: Optional[str] = None
    mode: Optional[str] = None  # family, club, trail
    origin: Optional[str] = None
    destination: Optional[str] = None
    earliest_time: Optional[str] = None
    latest_time: Optional[str] = None
    walkers: Optional[List[Dict[str, Any]]] = None

class CheckinRequest(BaseModel):
    walker: str
    stop_index: int

class ObservationRequest(BaseModel):
    walker: str
    label: str
    observed: str  # "shade" or "sun"
    predicted_shade: Optional[float] = None
    stop_index: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

class CardCreateRequest(BaseModel):
    trip_code: Optional[str] = None
    type: str  # note, warning, meetup, tip
    text: str
    lat: float
    lon: float
    visibility: Optional[str] = "public"  # public, group, addressed
    to_group: Optional[str] = None
    shade_at_creation: Optional[float] = None


# --------------------------------------------------------------------- Core Existing Endpoints
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "Chhaya Kolkata Shade Engine (v2 Master Plan)",
        "timestamp": datetime.datetime.now().isoformat(),
        "neighborhood": "Park Street & Camac Street, Kolkata (UTM Zone 45N)"
    }


@app.get("/pois")
def get_pois():
    routing = get_routing_engine()
    return {"pois": routing.pois}


@app.get("/shadows")
def get_shadows(time: str = Query("15:00", description="Time in HH:MM 24-hr format (IST)")):
    try:
        parts = time.split(":")
        hr = int(parts[0])
        mn = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        hr, mn = 15, 0

    now = datetime.datetime.now()
    dt_ist = now.replace(hour=hr, minute=mn, second=0, microsecond=0)
    engine = get_shadow_engine()
    geojson = engine.compute_shadows(dt_ist)
    return geojson


@app.post("/route")
def calculate_route(req: RouteRequest):
    routing = get_routing_engine()
    try:
        res = routing.plan_route(
            origin_query=req.origin,
            destination_query=req.destination,
            depart_time_str=req.depart_time or "15:00",
            sun_tolerance=req.sun_tolerance or "low",
            speed_kmh=req.speed_kmh or 3.0
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/window")
def get_best_window(date: Optional[str] = Query(None, description="Date YYYY-MM-DD")):
    model = get_window_model()
    target_date = date if date else datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        return model.predict_for_date(target_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Window forecast failed: {e}")


@app.get("/agent/tools")
def agent_tools():
    """Lists the tools the agent can call (Mastra-compatible descriptions)."""
    return {
        "agent": "Chhaya",
        "tools": [
            {"name": name, "description": spec["description"], "parameters": spec["parameters"]}
            for name, spec in TOOL_REGISTRY.items()
        ],
    }


@app.post("/agent/chat")
def agent_chat(req: ChatRequest):
    agent = get_agent()
    try:
        result = agent.run(req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent failed: {e}")

    parsed = result.get("parsed_parameters")
    if req.depart_time and parsed:
        parsed["depart_time"] = req.depart_time
        try:
            result["route_data"] = agent.call_tool(
                "plan_route",
                {
                    "origin": parsed["origin"],
                    "destination": parsed["destination"],
                    "depart_time": req.depart_time,
                    "sun_tolerance": parsed.get("sun_tolerance", "low"),
                    "speed_kmh": parsed.get("speed_kmh", 3.0),
                },
            )
        except Exception:
            pass
    if req.sun_tolerance and parsed and not req.depart_time:
        parsed["sun_tolerance"] = req.sun_tolerance

    return result


@app.post("/voice/briefing")
async def voice_briefing(req: VoiceRequest):
    res = await synthesize_briefing_audio(req.text, req.voice_id)
    return res


# --------------------------------------------------------------------- Master Plan Endpoints (P0 - P2)

@app.post("/api/plan")
def api_create_plan(req: PlanApiRequest):
    """
    Fulfills Section 4, P0 (Plan Builder):
    Parses pasted message into constraints, scales budget by Open-Meteo weather,
    sweeps start times, and places shaded rest stops.
    """
    if req.message:
        constraints = parse_message_to_constraints(req.message)
    else:
        constraints = {
            "mode": req.mode or "family",
            "start_window": {
                "date": datetime.date.today().isoformat(),
                "earliest": req.earliest_time or "11:30",
                "latest": req.latest_time or "12:30",
            },
            "walkers": req.walkers or [{"name": "Walker", "sun_sensitivity": "high", "pace": "slow"}],
            "destinations": [{"text": req.destination or "Belle Vue Clinic"}],
            "origin": req.origin or "Dadu's Residence (Middleton Row)",
        }

    plan = build_trip_plan(
        parsed_constraints=constraints,
        user_origin_override=req.origin,
        user_destination_override=req.destination,
        user_mode_override=req.mode,
    )
    return plan


@app.get("/api/weather")
def api_get_weather(
    date: Optional[str] = Query(None),
    sensitivity: str = Query("high"),
    time: str = Query("12:00")
):
    """
    Fulfills Section 4, P0.2: Weather-adjusted sun budget from live Open-Meteo.
    """
    return get_weather_adjusted_budget(
        sun_sensitivity=sensitivity,
        time_str=time,
        date_str=date
    )


@app.get("/api/trip/{code}")
def api_get_trip(code: str):
    """
    Fulfills Section 4, P1.1: Trip link details, stops, and check-ins.
    """
    trip = get_trip(code)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    checkins = get_trip_checkins(code)
    trip["checkins"] = checkins
    return trip


@app.post("/api/trip/{code}/checkin")
def api_checkin(code: str, req: CheckinRequest):
    """
    Fulfills Section 4, P1.1: Walker taps 'I'm at Stop N'. No accounts required.
    """
    trip = get_trip(code)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    res = record_checkin(code, req.walker, req.stop_index)
    return res


@app.post("/api/trip/{code}/reached")
def api_trip_reached(code: str):
    """
    Fulfills Section 4, P1.2: Family 'We reached safely' ping.
    """
    ok = mark_trip_reached(code)
    if not ok:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return {"status": "reached", "trip_code": code, "reached_at": datetime.datetime.now().isoformat()}


@app.post("/api/trip/{code}/observation")
def api_record_observation(code: str, req: ObservationRequest):
    """
    Fulfills Section 3.6: a walker taps "shaded" or "sunny" at a checkpoint.
    Stores observed vs predicted shade with the sun position at tap time.
    """
    trip = get_trip(code)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    observed = 1.0 if req.observed.strip().lower().startswith("shad") else 0.0
    try:
        elev = azim = None
        now = datetime.datetime.now()
        lat = req.lat if req.lat is not None else KOLKATA_CENTER_LAT
        lon = req.lon if req.lon is not None else KOLKATA_CENTER_LON
        sol = calculate_solar_position(now, lat=lat, lon=lon)
        elev = sol.get("elevation")
        azim = sol.get("azimuth")
    except Exception:
        pass
    res = record_observation(
        trip_code=code,
        walker_name=req.walker,
        label=req.label,
        predicted_shade=req.predicted_shade if req.predicted_shade is not None else 0.0,
        observed_shade=observed,
        stop_index=req.stop_index,
        sun_elevation=elev,
        sun_azimuth=azim,
    )
    return res


@app.get("/api/accuracy")
def api_accuracy():
    """
    Fulfills Section 3.6 + V10: live "predicted vs observed" tally with tap
    counts, plus per-label corrections once enough taps exist.
    """
    return get_accuracy_summary()


@app.get("/api/trip/{code}/repair")
def api_trip_repair(code: str, elapsed_min: Optional[float] = Query(None)):
    """
    Fulfills Section 4, P1.3-1.4: Straggler behind detection and ranked repair options (WAIT, SHORTCUT, SWEEP, SPLIT).
    """
    trip = get_trip(code)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")

    checkins = get_trip_checkins(code)
    plan = trip["plan"]

    # If elapsed_min not provided, default to demo club elapsed time (18 min)
    current_elapsed = elapsed_min if elapsed_min is not None else 18.0

    repair_result = detect_and_repair_stragglers(
        trip_plan=plan,
        checkins=checkins,
        current_elapsed_min=current_elapsed,
    )
    return repair_result


@app.post("/api/cards")
def api_create_card(req: CardCreateRequest):
    """
    Fulfills Section 4, P2: Leave a card with text cleaning and moderation.
    """
    card = create_card(
        trip_code=req.trip_code,
        card_type=req.type,
        text=req.text,
        lat=req.lat,
        lon=req.lon,
        visibility=req.visibility or "public",
        to_group=req.to_group,
        shade_at_creation=req.shade_at_creation,
    )
    return card


@app.get("/api/cards/near")
def api_get_near_cards(
    lat: float = Query(...),
    lon: float = Query(...),
    trip_code: Optional[str] = Query(None),
    radius: float = Query(300.0)
):
    """
    Fulfills Section 4, P2.2: 'What's here?' proximity scan (<60m immediate, <300m radar).
    """
    return find_nearby_cards(lat=lat, lon=lon, trip_code=trip_code, radius_m=radius)


@app.post("/api/cards/{card_id}/report")
def api_report_card(card_id: str):
    """
    Fulfills Section 4, P2.4: Report card button hides offending card immediately.
    """
    ok = report_and_hide_card(card_id)
    return {"success": ok, "card_id": card_id, "hidden": True}


@app.get("/api/trip/{code}/qr")
def api_trip_qr(code: str):
    """
    Fulfills Section 4, P2.2: Trip QR code generator encoding /t/<code>.
    """
    b64 = generate_trip_qr_base64(code)
    return {
        "trip_code": code,
        "qr_base64": b64,
        "qr_url": f"/t/{code}",
        "mime": "image/png"
    }


@app.get("/api/demo/seed")
def api_reseed_demo():
    """Seeds simulated demo trips (dadu-clinic, parkst-club) and sample cards."""
    seed_demo_data()
    return {"status": "seeded", "trips": ["dadu-clinic", "parkst-club"]}


# --------------------------------------------------------------------- Static & Single Page Shell
# Mount data folder for GeoJSON assets
if os.path.exists("data"):
    app.mount("/static/data", StaticFiles(directory="data"), name="data")

# Mount static web assets
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_index():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html", headers={"Cache-Control": "no-cache"})
    return {"message": "Chhaya API active."}

# Support clean URLs /t/{code} and /t/{code}/watch for walkers and watchers
@app.get("/t/{code}")
@app.get("/t/{code}/watch")
def serve_trip_client(code: str):
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html", headers={"Cache-Control": "no-cache"})
    return {"trip_code": code}


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "true").lower() == "true"
    uvicorn.run("backend.main:app", host=host, port=port, reload=reload)
