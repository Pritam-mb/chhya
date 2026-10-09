"""
Chhaya agent wrapper.

A small tool-calling agent that sits over the FastAPI services. It mirrors the
Mastra tool set in `agent/` (plan_route, best_window, get_shadows, list_pois):

  * If GROQ_API_KEY is set, the agent runs an open-weight Groq model
    (gpt-oss-120b / qwen, override with GROQ_MODEL) with OpenAI-style function
    calling so the model picks the tools itself.
  * Otherwise it runs a deterministic planner so the app still works offline
    (this is the honest offline path, not a local-model claim).

Tool calls are wrapped in retries and, if SENTRY_DSN is set, in Sentry spans so
the agent's tool calls are visible as traces.
"""
import os
import time
import json
import datetime
from typing import Dict, Any, List, Callable, Optional

from backend.routing import get_routing_engine
from backend.geo_shadows import get_shadow_engine
from backend.best_window import get_window_model
from backend.agent_parser import offline_parse_request, GROQ_MODEL_CANDIDATES

try:
    from groq import Groq
    HAS_GROQ = True
except Exception:
    HAS_GROQ = False

try:
    import sentry_sdk
    HAS_SENTRY = True
except Exception:
    HAS_SENTRY = False

_sentry_ready = False


def init_sentry() -> bool:
    global _sentry_ready
    dsn = os.environ.get("SENTRY_DSN")
    if dsn and HAS_SENTRY and not _sentry_ready:
        try:
            from sentry_sdk.integrations.starlette import StarletteIntegration
            from sentry_sdk.integrations.fastapi import FastApiIntegration

            sentry_sdk.init(
                dsn=dsn,
                traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "1.0")),
                environment=os.environ.get("SENTRY_ENVIRONMENT", "chhaya"),
                send_default_pii=False,
                integrations=[StarletteIntegration(), FastApiIntegration()],
            )
            _sentry_ready = True
        except Exception:
            _sentry_ready = False
    return _sentry_ready


# --------------------------------------------------------------------- tools
def _tool_plan_route(origin: str, destination: str, depart_time: str = "15:00",
                     sun_tolerance: str = "low", speed_kmh: float = 3.0) -> Dict[str, Any]:
    return get_routing_engine().plan_route(origin, destination, depart_time, sun_tolerance, speed_kmh)


def _tool_best_window(date: Optional[str] = None) -> Dict[str, Any]:
    date = date or datetime.date.today().isoformat()
    return get_window_model().predict_for_date(date)


def _tool_get_shadows(time_str: str = "15:00") -> Dict[str, Any]:
    parts = time_str.split(":")
    hr = int(parts[0]) if parts and parts[0].isdigit() else 15
    mn = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    now = datetime.datetime.now()
    dt = now.replace(hour=hr, minute=mn, second=0, microsecond=0)
    return get_shadow_engine().compute_shadows(dt)


def _tool_list_pois() -> Dict[str, Any]:
    return {"pois": get_routing_engine().pois}


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "plan_route": {
        "fn": _tool_plan_route,
        "description": "Compute the shortest and shade-aware walking routes with sun-minutes.",
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Start place name or 'lat,lon'"},
                "destination": {"type": "string", "description": "End place name or 'lat,lon'"},
                "depart_time": {"type": "string", "description": "Departure time HH:MM (IST)"},
                "sun_tolerance": {"type": "string", "enum": ["low", "medium", "high"]},
                "speed_kmh": {"type": "number"},
            },
            "required": ["origin", "destination"],
        },
    },
    "best_window": {
        "fn": _tool_best_window,
        "description": "Rank 2-hour daylight walking windows for a date using TabPFN.",
        "parameters": {
            "type": "object",
            "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": [],
        },
    },
    "get_shadows": {
        "fn": _tool_get_shadows,
        "description": "Building shadow polygons (GeoJSON) for a time of day.",
        "parameters": {
            "type": "object",
            "properties": {"time": {"type": "string", "description": "HH:MM"}},
            "required": [],
        },
    },
    "list_pois": {
        "fn": _tool_list_pois,
        "description": "List known landmarks and their aliases in the demo area.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

_WINDOW_KEYWORDS = ["when", "best time", "what time", "coolest", "least sun", "window", "kobe", "kokhon"]


def _retry(fn: Callable, attempts: int = 3, backoff: float = 0.4):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # transient geometry / network issues
            last = e
            time.sleep(backoff * (i + 1))
    raise last


class ChhayaAgent:
    def __init__(self):
        init_sentry()
        self.tool_calls: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------- tracing
    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        spec = TOOL_REGISTRY[name]
        self.tool_calls.append({"tool": name, "arguments": arguments})

        if _sentry_ready:
            with sentry_sdk.start_span(op="tool", description=name) as span:
                span.set_data("arguments", arguments)
                return _retry(lambda: spec["fn"](**arguments))
        return _retry(lambda: spec["fn"](**arguments))

    # ------------------------------------------------------------- llm agent
    def _llm_loop(self, message: str) -> Optional[Dict[str, Any]]:
        key = os.environ.get("GROQ_API_KEY")
        if not key or not HAS_GROQ:
            return None
        client = Groq(api_key=key)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": spec["description"],
                    "parameters": spec["parameters"],
                },
            }
            for name, spec in TOOL_REGISTRY.items()
        ]
        for model_name in GROQ_MODEL_CANDIDATES:
            try:
                return self._tool_loop(client, model_name, tools, message)
            except Exception as e:
                print(f"Groq agent model {model_name} failed ({e}).")
        return None

    def _tool_loop(self, client, model_name: str, tools, message: str) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Chhaya, a Kolkata shade-aware walking agent. Use the tools "
                    "to plan shaded routes and answer in one friendly sentence. If a place "
                    "is unknown, ask the user to clarify instead of guessing."
                ),
            },
            {"role": "user", "content": message},
        ]
        route_result = None
        window_result = None
        agent_label = f"mastra-style groq tool-calling ({model_name})"
        for _ in range(4):
            resp = client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                return {
                    "reply": msg.content,
                    "agent": agent_label,
                    "route_data": route_result,
                    "window_data": window_result,
                }
            messages.append(msg)
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                try:
                    result = self.call_tool(tc.function.name, args)
                except Exception as e:
                    result = {"error": str(e)}
                if tc.function.name == "plan_route":
                    route_result = result
                elif tc.function.name == "best_window":
                    window_result = result
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result)[:4000],
                    }
                )
        return {
            "reply": "I gathered the route data but hit my tool-step limit.",
            "agent": agent_label,
            "route_data": route_result,
            "window_data": window_result,
        }

    # ------------------------------------------------------- deterministic
    def _deterministic(self, message: str) -> Dict[str, Any]:
        parsed = offline_parse_request(message)
        routing = get_routing_engine()

        unresolved = []
        if not routing.resolve_location(parsed["origin"]):
            unresolved.append(parsed["origin"])
        if not routing.resolve_location(parsed["destination"]):
            unresolved.append(parsed["destination"])

        if unresolved:
            known = ", ".join(p["name"] for p in routing.pois[:6])
            return {
                "reply": (
                    f"I couldn't place {', '.join(unresolved)} in the demo area. "
                    f"Known places include: {known}. Which one did you mean?"
                ),
                "agent": "deterministic offline planner",
                "clarification": True,
                "parsed_parameters": parsed,
                "route_data": None,
                "window_data": None,
            }

        route_result = self.call_tool(
            "plan_route",
            {
                "origin": parsed["origin"],
                "destination": parsed["destination"],
                "depart_time": parsed.get("depart_time", "15:00"),
                "sun_tolerance": parsed.get("sun_tolerance", "low"),
                "speed_kmh": parsed.get("speed_kmh", 3.0),
            },
        )

        window_result = None
        if any(k in message.lower() for k in _WINDOW_KEYWORDS):
            window_result = self.call_tool("best_window", {})

        reply = (
            f"Shaded walk from {route_result['origin']['name']} to "
            f"{route_result['destination']['name']} at {route_result['depart_time']} IST. "
            f"{route_result['trade_off_sentence']}"
        )
        if window_result:
            reply += f" Best window today: {window_result['best_window']} ({window_result['best_window_label']})."

        return {
            "reply": reply,
            "agent": "deterministic offline planner",
            "parsed_parameters": parsed,
            "route_data": route_result,
            "window_data": window_result,
        }

    # ------------------------------------------------------------------ run
    def run(self, message: str) -> Dict[str, Any]:
        self.tool_calls = []
        result = self._llm_loop(message)
        # The hosted model is a fine reasoner but weaker than the rule parser on
        # romanized Bengali/Hindi. If it could not produce a route, let the
        # deterministic planner try before accepting a clarification request.
        if result is None or result.get("route_data") is None:
            self.tool_calls = []
            offline = self._deterministic(message)
            if result is None or offline.get("route_data") is not None:
                result = offline
        result["tool_calls"] = self.tool_calls
        result.setdefault("parsed_parameters", None)
        result.setdefault("route_data", None)
        result.setdefault("window_data", None)
        if _sentry_ready:
            result["tracing"] = "sentry"
        return result


_agent: Optional[ChhayaAgent] = None


def get_agent() -> ChhayaAgent:
    global _agent
    if _agent is None:
        _agent = ChhayaAgent()
    return _agent
