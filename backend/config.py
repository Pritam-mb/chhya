"""
Chhaya Central Configuration
Contains model names, thresholds, sun budgets, weights, and grace periods.
(Satisfies Rule 7: Config, not hard-coding)
"""
import os

# --- Model Configuration ---
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# --- Sun Sensitivity Base Budgets (Minutes of Direct Sun Exposure) ---
# Placeholder thresholds for planning comparison, NOT medical guidance.
BASE_SUN_BUDGET_MIN = {
    "high": 4.0,     # Very sensitive (e.g., Dadu / elders / children)
    "normal": 12.0,  # Standard walker
    "low": 25.0,     # High sun tolerance / runner
}

# --- Walking Pace Defaults (km/h) ---
PACE_KMH = {
    "slow": 2.8,    # ~46.7 meters/min (elderly or stroll)
    "normal": 4.2,  # ~70 meters/min (steady walking)
    "fast": 5.4,    # ~90 meters/min (brisk / jogging)
}

# --- Weather Scaling Thresholds (Section 4, P0.2) ---
# Formula:
# factor = 1.0
# if apparent_temperature >= 38: factor *= 0.5
# elif apparent_temperature >= 33: factor *= 0.75
# if uv_index >= 8: factor *= 0.75
# effective_budget = base_budget * factor
WEATHER_APPARENT_TEMP_HOT = 33.0        # °C
WEATHER_APPARENT_TEMP_EXTREME = 38.0    # °C
WEATHER_UV_EXTREME = 8.0                # UV Index

WEATHER_FACTOR_HOT = 0.75
WEATHER_FACTOR_EXTREME = 0.50
WEATHER_FACTOR_UV_EXTREME = 0.75

# Cache duration for weather forecast
WEATHER_CACHE_TTL_HOURS = 2

# --- Rest & Regroup Stop Thresholds ---
REST_STOP_EVERY_MIN = 8                 # Default interval between rest stops for slow walker
REST_STOP_SEARCH_RADIUS_M = 40.0        # Search radius around cumulative route point
REST_STOP_MIN_SHADE = 0.60              # Minimum required shade ratio at arrival time (0.0 to 1.0)

# --- Straggler Detection & Repair (Section 4, P1.3-1.4) ---
BEHIND_GRACE_PERIOD_MIN = 3.0           # Walker is behind if now > expected_checkin + grace

# Repair Option Ranking Weights:
# score = w1 * group_wait_min + w2 * max_walker_sun_min + w3 * rejoin_delay_min
REPAIR_WEIGHTS = {
    "w1_group_wait": 1.0,
    "w2_max_walker_sun": 2.5,
    "w3_rejoin_delay": 1.2,
}

# --- Trail Mode Turnaround Settings ---
TRAIL_SUNSET_BUFFER_MIN = 30.0          # Buffer before sunset for trail safe return

# --- Cards & Proximity Scanning ---
CARD_NEAR_RADIUS_M = 60.0               # "What's here?" immediate proximity
CARD_RADAR_RADIUS_M = 300.0             # Extended discovery radar
CARD_MAX_CHARS = 140
CARD_DEFAULT_TTL_HOURS = 24
CARD_RATE_LIMIT_PER_MINUTE = 5

# --- Shade Observation & Calibration (Section 3.6) ---
# A tap counts as a match when |observed - predicted| <= tolerance.
OBS_MATCH_TOLERANCE = 0.25              # shade-fraction tolerance for a "match"
OBS_MIN_TAPS_FOR_CORRECTION = 5         # taps on one label before learning a correction
OBS_MAX_CORRECTION = 0.40               # clamp per-label correction to +-0.40

# --- Geographic Center & Coordinate Reference ---
KOLKATA_CENTER_LAT = 22.5510
KOLKATA_CENTER_LON = 88.3530
TIMEZONE = "Asia/Kolkata"
