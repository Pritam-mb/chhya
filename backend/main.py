import os
import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.geo_shadows import get_shadow_engine, calculate_solar_position
from backend.routing import get_routing_engine
from backend.agent_parser import parse_request_with_llm, offline_parse_request
from backend.best_window import get_window_model
from backend.voice import synthesize_briefing_audio

app = FastAPI(
    title="Chhaya API",
    description="Kolkata Shade-Aware Navigation & Building Shadow Routing Engine",
    version="1.0.0"
)

# Enable CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
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


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "Chhaya Kolkata Shade Engine",
        "timestamp": datetime.datetime.now().isoformat(),
        "neighborhood": "Park Street & Camac Street, Kolkata (UTM Zone 45N)"
    }


@app.get("/pois")
def get_pois():
    routing = get_routing_engine()
    return {"pois": routing.pois}


@app.get("/shadows")
def get_shadows(time: str = Query("15:00", description="Time in HH:MM 24-hr format (IST)")):
    """
    Returns GeoJSON FeatureCollection of building shadows extruded in UTM Zone 45N
    for the requested 30-min time slot.
    """
    try:
        parts = time.split(":")
        hr = int(parts[0])
        mn = int(parts[1]) if len(parts) > 1 else 0
    except:
        hr, mn = 15, 0

    dt_ist = datetime.datetime(2026, 10, 8, hr, mn)
    engine = get_shadow_engine()
    geojson = engine.compute_shadows(dt_ist)
    return geojson


@app.post("/route")
def calculate_route(req: RouteRequest):
    """
    Computes both Shortest Path and Shade-Aware Path with sun-minutes counter,
    exposure-colored segments, and 1-sentence trade-off explanation.
    """
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
def get_best_window(date: str = Query("2026-10-08", description="Date YYYY-MM-DD")):
    """
    Fulfills F6 (TabPFN partner category): predicts best 2-hour daylight walking window
    with MAE statistics compared against a 15-year climatology baseline.
    """
    model = get_window_model()
    return model.get_best_windows(date)


@app.post("/agent/chat")
def agent_chat(req: ChatRequest):
    """
    Full agent flow: natural-language request parsed by local open model (or Groq),
    calling the routing tool, generating dual routes, sun-minutes counter, and trade-off.
    """
    # 1. Parse natural language
    parsed = parse_request_with_llm(req.message)
    
    # Override if explicitly passed
    if req.depart_time:
        parsed["depart_time"] = req.depart_time
    if req.sun_tolerance:
        parsed["sun_tolerance"] = req.sun_tolerance
        
    # 2. Call routing tool
    routing = get_routing_engine()
    try:
        route_result = routing.plan_route(
            origin_query=parsed["origin"],
            destination_query=parsed["destination"],
            depart_time_str=parsed.get("depart_time", "15:00"),
            sun_tolerance=parsed.get("sun_tolerance", "low"),
            speed_kmh=parsed.get("speed_kmh", 3.0)
        )
        
        # 3. Create succinct agent response
        trade_off = route_result["trade_off_sentence"]
        agent_reply = (
            f"I've mapped the shaded route from {route_result['origin']['name']} to {route_result['destination']['name']} for {route_result['depart_time']} IST. "
            f"{trade_off}"
        )
        
        return {
            "reply": agent_reply,
            "parsed_parameters": parsed,
            "route_data": route_result
        }
    except Exception as e:
        return {
            "reply": f"I couldn't resolve the exact walking path: {str(e)}. Please check origin and destination.",
            "parsed_parameters": parsed,
            "route_data": None,
            "error": str(e)
        }


@app.post("/voice/briefing")
async def voice_briefing(req: VoiceRequest):
    """
    Fulfills F7 (ElevenLabs partner category): generates spoken briefing audio.
    """
    res = await synthesize_briefing_audio(req.text, req.voice_id)
    return res


# Mount static frontend if exists
if os.path.exists("frontend/dist"):
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
