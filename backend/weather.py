"""
Weather service and sun budget scaling for Chhaya.
Fulfills Section 4, P0.2: Weather-adjusted sun budget.
"""
import os
import json
import datetime
from typing import Dict, Any, Optional
import httpx

from backend.config import (
    KOLKATA_CENTER_LAT,
    KOLKATA_CENTER_LON,
    TIMEZONE,
    BASE_SUN_BUDGET_MIN,
    WEATHER_APPARENT_TEMP_HOT,
    WEATHER_APPARENT_TEMP_EXTREME,
    WEATHER_UV_EXTREME,
    WEATHER_FACTOR_HOT,
    WEATHER_FACTOR_EXTREME,
    WEATHER_FACTOR_UV_EXTREME,
)

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "weather_cache.json")
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# In-memory cache
_weather_memory_cache: Optional[Dict[str, Any]] = None


def compute_weather_factor(apparent_temp: float, uv_index: float) -> float:
    """
    Computes budget scaling factor based on thermal and solar stress.
    Thresholds are planning placeholders, NOT medical guidance.
    """
    factor = 1.0
    if apparent_temp >= WEATHER_APPARENT_TEMP_EXTREME:
        factor *= WEATHER_FACTOR_EXTREME
    elif apparent_temp >= WEATHER_APPARENT_TEMP_HOT:
        factor *= WEATHER_FACTOR_HOT

    if uv_index >= WEATHER_UV_EXTREME:
        factor *= WEATHER_FACTOR_UV_EXTREME

    return round(factor, 4)


def fetch_forecast_data(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches live hourly forecast from Open-Meteo with caching and offline fallback.
    """
    global _weather_memory_cache

    target_date = date_str or datetime.date.today().isoformat()

    # Try live fetch
    params = {
        "latitude": KOLKATA_CENTER_LAT,
        "longitude": KOLKATA_CENTER_LON,
        "hourly": "temperature_2m,relative_humidity_2m,apparent_temperature,uv_index",
        "timezone": TIMEZONE,
        "start_date": target_date,
        "end_date": target_date,
    }

    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(OPEN_METEO_FORECAST_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                hourly = data.get("hourly", {})
                times = hourly.get("time", [])
                records = {}
                for idx, t in enumerate(times):
                    hr = int(t.split("T")[1].split(":")[0])
                    records[hr] = {
                        "temperature_2m": hourly.get("temperature_2m", [30.0])[idx],
                        "relative_humidity_2m": hourly.get("relative_humidity_2m", [65.0])[idx],
                        "apparent_temperature": hourly.get("apparent_temperature", [32.0])[idx],
                        "uv_index": hourly.get("uv_index", [5.0])[idx],
                    }

                payload = {
                    "date": target_date,
                    "hourly": records,
                    "is_live": True,
                    "source": "Open-Meteo live forecast",
                    "fetched_at": datetime.datetime.now().isoformat(),
                }

                # Save to cache
                _weather_memory_cache = payload
                try:
                    with open(CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(payload, f)
                except Exception:
                    pass

                return payload
    except Exception as e:
        print(f"Weather live fetch failed ({e}), loading cache...")

    # Fallback to cache file if network is unavailable
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                cached["is_live"] = False
                cached["source"] = "Cached forecast (weather not live)"
                return cached
        except Exception:
            pass

    # Default offline synthetic climatology if cache is missing
    hourly = {}
    for h in range(6, 19):
        # Peak noon has higher heat and UV
        temp = 28.0 + 6.0 * (1.0 - abs(h - 13) / 7.0)
        app_temp = temp + 3.0
        uv = max(0.0, 9.5 * (1.0 - abs(h - 12) / 6.0))
        hourly[h] = {
            "temperature_2m": round(temp, 1),
            "relative_humidity_2m": 68.0,
            "apparent_temperature": round(app_temp, 1),
            "uv_index": round(uv, 1),
        }

    return {
        "date": target_date,
        "hourly": hourly,
        "is_live": False,
        "source": "Offline fallback (weather not live)",
        "fetched_at": datetime.datetime.now().isoformat(),
    }


def get_weather_adjusted_budget(
    sun_sensitivity: str = "high",
    time_str: str = "15:00",
    date_str: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes the effective sun budget scaled by temperature and UV index.
    """
    forecast = fetch_forecast_data(date_str)
    hourly = forecast.get("hourly", {})

    try:
        hr = int(time_str.split(":")[0])
    except Exception:
        hr = 15

    hour_data = hourly.get(hr) or hourly.get(str(hr)) or {
        "temperature_2m": 31.0,
        "apparent_temperature": 34.0,
        "uv_index": 5.5,
    }

    apparent_temp = float(hour_data.get("apparent_temperature", 34.0))
    uv_index = float(hour_data.get("uv_index", 5.5))
    base_budget = BASE_SUN_BUDGET_MIN.get(sun_sensitivity.lower(), BASE_SUN_BUDGET_MIN["normal"])

    factor = compute_weather_factor(apparent_temp, uv_index)
    effective_budget = round(base_budget * factor, 1)

    reason = []
    if apparent_temp >= WEATHER_APPARENT_TEMP_EXTREME:
        reason.append(f"extreme feels-like {apparent_temp}°C (budget ×{WEATHER_FACTOR_EXTREME})")
    elif apparent_temp >= WEATHER_APPARENT_TEMP_HOT:
        reason.append(f"warm feels-like {apparent_temp}°C (budget ×{WEATHER_FACTOR_HOT})")

    if uv_index >= WEATHER_UV_EXTREME:
        reason.append(f"high UV index {uv_index} (budget ×{WEATHER_FACTOR_UV_EXTREME})")

    if not reason:
        reason_text = "moderate weather, full budget applies"
    else:
        reason_text = ", ".join(reason)

    return {
        "sun_sensitivity": sun_sensitivity,
        "base_budget_min": base_budget,
        "weather_factor": factor,
        "effective_budget_min": effective_budget,
        "apparent_temperature": apparent_temp,
        "uv_index": uv_index,
        "is_live": forecast.get("is_live", False),
        "source": forecast.get("source", "Open-Meteo"),
        "explanation": f"Base budget {base_budget} min → {effective_budget} min due to {reason_text}.",
    }
