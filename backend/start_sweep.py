"""
Start time curve evaluation for Chhaya.
Fulfills Section 4, P0.4: Best start time sweep across allowed window.
"""
import datetime
from typing import Dict, List, Any, Optional
from backend.routing import get_routing_engine


def sweep_start_times(
    origin: str,
    destination: str,
    earliest_time: str = "11:30",
    latest_time: str = "12:30",
    speed_kmh: float = 2.8,
    effective_budget_min: float = 4.0,
    step_minutes: int = 10,
) -> Dict[str, Any]:
    """
    Sweeps departure times across the allowed window in step_minutes intervals.
    Returns the exposure curve, best departure time, and budget compliance.
    """
    routing = get_routing_engine()

    try:
        eh, em = map(int, earliest_time.split(":"))
        lh, lm = map(int, latest_time.split(":"))
    except Exception:
        eh, em = 11, 30
        lh, lm = 12, 30

    start_mins = eh * 60 + em
    end_mins = lh * 60 + lm

    if end_mins < start_mins:
        end_mins = start_mins + 60

    curve = []
    best_time = earliest_time
    min_sun_mins = float("inf")
    best_route_res = None

    cur = start_mins
    while cur <= end_mins:
        h = cur // 60
        m = cur % 60
        t_str = f"{h:02d}:{m:02d}"

        try:
            res = routing.plan_route(
                origin_query=origin,
                destination_query=destination,
                depart_time_str=t_str,
                sun_tolerance="low",
                speed_kmh=speed_kmh,
            )
            shade_info = res["shade_route"]
            sun_mins = float(shade_info.get("sun_minutes", 0.0))
            shade_pct = float(shade_info.get("shade_percentage", 0.0))
            walk_mins = float(shade_info.get("duration_minutes", 0.0))

            fits = sun_mins <= (effective_budget_min + 0.05)

            curve_point = {
                "time": t_str,
                "sun_minutes": sun_mins,
                "walk_minutes": walk_mins,
                "shade_percentage": shade_pct,
                "fits_budget": fits,
            }
            curve.append(curve_point)

            if sun_mins < min_sun_mins:
                min_sun_mins = sun_mins
                best_time = t_str
                best_route_res = res
        except Exception as e:
            pass

        cur += step_minutes

    has_comfortable_start = any(p["fits_budget"] for p in curve)

    if not has_comfortable_start:
        warning = (
            f"No comfortable window today: best available is {best_time} with {min_sun_mins:.1f} sun-minutes, "
            f"which exceeds your safe budget of {effective_budget_min:.1f} sun-minutes. Try leaving earlier/later, or use a ride."
        )
    else:
        warning = None

    return {
        "best_start_time": best_time,
        "best_sun_minutes": round(min_sun_mins, 1) if min_sun_mins != float("inf") else 0.0,
        "effective_budget_min": effective_budget_min,
        "has_comfortable_window": has_comfortable_start,
        "warning_message": warning,
        "curve": curve,
        "best_route_data": best_route_res,
    }
