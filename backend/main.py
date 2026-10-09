import os
import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.geo_shadows import get_shadow_engine, calculate_solar_position
from backend.routing import get_routing_engine
from backend.agent import get_agent, TOOL_REGISTRY
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

    now = datetime.datetime.now()
    dt_ist = now.replace(hour=hr, minute=mn, second=0, microsecond=0)
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
def get_best_window(date: Optional[str] = Query(None, description="Date YYYY-MM-DD")):
    """
    Fulfills F6 (TabPFN partner category): predicts the best 2-hour daylight
    walking window from the live Open-Meteo forecast, ranked by a TabPFN
    feels-like prediction, with held-out MAE vs a climatology baseline.
    """
    model = get_window_model()
    target_date = date if date else datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        return model.predict_for_date(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date. Use YYYY-MM-DD.")
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
    """
    Full agent flow: the agent parses a natural-language request, calls the
    routing / best-window tools, and explains the trade-off in one sentence.
    Uses a Groq open-weight tool-calling model when GROQ_API_KEY is set, and a
    deterministic offline planner otherwise.
    """
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
    """
    Fulfills F7 (ElevenLabs partner category): generates spoken briefing audio.
    """
    res = await synthesize_briefing_audio(req.text, req.voice_id)
    return res


from fastapi.responses import FileResponse

# Mount data folder for GeoJSON assets
if os.path.exists("data"):
    app.mount("/static/data", StaticFiles(directory="data"), name="data")

# Mount static web assets
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_index():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "Chhaya API active. Access /docs for API documentation."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
