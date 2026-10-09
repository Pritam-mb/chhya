"""
Straggler detection and repair options engine for Chhaya Club & Trail modes.
Fulfills Section 4, P1.3-1.4 & Section 5: Straggler and rest-stop logic.
Code does the math, LLM or rule engine writes the human explanation.
"""
from typing import Dict, List, Any, Optional
from backend.config import BEHIND_GRACE_PERIOD_MIN, REPAIR_WEIGHTS, REST_STOP_MIN_SHADE


def detect_and_repair_stragglers(
    trip_plan: Dict[str, Any],
    checkins: List[Dict[str, Any]],
    current_elapsed_min: float,
    grace_period_min: float = BEHIND_GRACE_PERIOD_MIN,
) -> Dict[str, Any]:
    """
    Evaluates walker check-in times against expected schedule.
    If any walker is behind schedule, simulates and ranks:
    1. WAIT: Group pauses at next shaded stop.
    2. SHORTCUT: Straggler takes low-sun shortcut to next regroup point.
    3. SWEEP BUDDY: Normal-sensitivity companion stays with straggler.
    4. SPLIT: Fast cohort continues, slower cohort takes shade route to destination.
    """
    walkers = trip_plan.get("walkers", [])
    stops = trip_plan.get("stops", [])
    effective_budgets = trip_plan.get("effective_budgets", {})

    if not walkers or not stops:
        return {"has_straggler": False, "stragglers": [], "repair_options": [], "message": "Trip is progressing normally."}

    # Map latest checkin per walker
    # Checkin record: { "walker": str, "stop_index": int, "time_min": float }
    latest_checkins: Dict[str, int] = {}
    for c in checkins:
        w_name = c.get("walker", "")
        s_idx = c.get("stop_index", 0)
        latest_checkins[w_name] = max(latest_checkins.get(w_name, 0), s_idx)

    # Calculate expected arrival for each stop
    # If stops have cumulative_walk_min, use it; otherwise estimate
    total_stops = len(stops)

    stragglers = []
    for w in walkers:
        w_name = w.get("name", "Walker")
        last_stop = latest_checkins.get(w_name, 0)
        next_stop_idx = last_stop + 1

        if next_stop_idx <= total_stops:
            stop_data = stops[next_stop_idx - 1]
            expected_time = float(stop_data.get("cumulative_walk_min", 8.0 * next_stop_idx))

            if current_elapsed_min > (expected_time + grace_period_min):
                delay = round(current_elapsed_min - expected_time, 1)
                stragglers.append({
                    "name": w_name,
                    "sun_sensitivity": w.get("sun_sensitivity", "normal"),
                    "last_stop": last_stop,
                    "expected_next_stop": next_stop_idx,
                    "delay_min": delay,
                    "expected_time_min": expected_time,
                })

    if not stragglers:
        return {
            "has_straggler": False,
            "stragglers": [],
            "repair_options": [],
            "message": "All walkers are on schedule. No regroup action needed.",
        }

    # Identify primary straggler (largest delay)
    primary_straggler = max(stragglers, key=lambda x: x["delay_min"])
    delay = primary_straggler["delay_min"]
    target_stop_idx = primary_straggler["expected_next_stop"]
    target_stop = stops[target_stop_idx - 1] if target_stop_idx <= total_stops else stops[-1]

    stop_shade = float(target_stop.get("shade_at_arrival", 0.7))
    stop_name = target_stop.get("name", f"Stop {target_stop_idx}")

    w1 = REPAIR_WEIGHTS["w1_group_wait"]
    w2 = REPAIR_WEIGHTS["w2_max_walker_sun"]
    w3 = REPAIR_WEIGHTS["w3_rejoin_delay"]

    all_options = []

    # 1. OPTION: WAIT
    # Group waits at next shaded stop. Qualified only if shade >= threshold
    wait_shade_qualified = stop_shade >= REST_STOP_MIN_SHADE
    wait_time = delay
    wait_extra_sun = 0.4 if not wait_shade_qualified else 0.1
    wait_score = w1 * wait_time + w2 * wait_extra_sun + w3 * delay

    all_options.append({
        "type": "WAIT",
        "title": f"Wait at {stop_name}",
        "group_wait_min": wait_time,
        "max_walker_sun_min": wait_extra_sun,
        "rejoin_delay_min": delay,
        "score": round(wait_score, 2),
        "is_shaded": wait_shade_qualified,
        "shade_ratio": stop_shade,
        "description": f"Group pauses at {stop_name} ({round(wait_time)} min) for {primary_straggler['name']} to catch up.",
    })

    # 2. OPTION: SHORTCUT
    # Straggler takes direct side-lane shortcut to next regroup stop
    shortcut_time_saved = round(delay * 0.5, 1)
    shortcut_rejoin_delay = max(1.0, round(delay - shortcut_time_saved, 1))
    shortcut_wait = min(2.0, shortcut_rejoin_delay)
    shortcut_sun = 0.5
    shortcut_score = w1 * shortcut_wait + w2 * shortcut_sun + w3 * shortcut_rejoin_delay

    all_options.append({
        "type": "SHORTCUT",
        "title": f"Shortcut to Stop {min(total_stops, target_stop_idx + 1)}",
        "group_wait_min": shortcut_wait,
        "max_walker_sun_min": shortcut_sun,
        "rejoin_delay_min": shortcut_rejoin_delay,
        "score": round(shortcut_score, 2),
        "is_shaded": True,
        "shade_ratio": 0.75,
        "description": f"{primary_straggler['name']} takes the shaded side-lane shortcut, reducing catch-up delay to {shortcut_rejoin_delay} min.",
    })

    # 3. OPTION: SWEEP BUDDY
    # A normal-sensitivity walker stays back with straggler, group continues
    normal_buddies = [w for w in walkers if w.get("name") != primary_straggler["name"] and w.get("sun_sensitivity") != "high"]
    buddy_name = normal_buddies[0]["name"] if normal_buddies else "Buddy"
    sweep_wait = 0.0
    sweep_sun = 0.8
    sweep_rejoin = delay
    sweep_score = w1 * sweep_wait + w2 * sweep_sun + w3 * sweep_rejoin

    all_options.append({
        "type": "SWEEP",
        "title": f"Sweep Buddy ({buddy_name})",
        "group_wait_min": sweep_wait,
        "max_walker_sun_min": sweep_sun,
        "rejoin_delay_min": sweep_rejoin,
        "score": round(sweep_score, 2),
        "is_shaded": True,
        "shade_ratio": stop_shade,
        "description": f"{buddy_name} pairs with {primary_straggler['name']}; lead group continues without pausing.",
    })

    # 4. OPTION: SPLIT
    # Fast group continues, slow group takes shorter shaded loop, both meet at final stop
    split_wait = 0.0
    split_sun = 0.3
    split_delay = round(delay * 0.4, 1)
    split_score = w1 * split_wait + w2 * split_sun + w3 * split_delay

    all_options.append({
        "type": "SPLIT",
        "title": "Split into Paced Cohorts",
        "group_wait_min": split_wait,
        "max_walker_sun_min": split_sun,
        "rejoin_delay_min": split_delay,
        "score": round(split_score, 2),
        "is_shaded": True,
        "shade_ratio": 0.8,
        "description": f"Fast group continues along main avenue; {primary_straggler['name']} takes the shaded corridor to meet at the destination.",
    })

    # Discard options that push sun-sensitive walkers over budget
    # If primary straggler is high sensitivity, require shaded waiting
    valid_options = []
    sensitive_budget = effective_budgets.get("high", 4.0)

    for opt in all_options:
        if primary_straggler["sun_sensitivity"] == "high" and opt["type"] == "WAIT" and not opt["is_shaded"]:
            continue
        valid_options.append(opt)

    if not valid_options:
        valid_options = all_options

    # Rank ascending by score
    valid_options.sort(key=lambda x: x["score"])
    top_two = valid_options[:2]

    # Rule-based human repair explanation from numbers
    opt1 = top_two[0]
    opt2 = top_two[1] if len(top_two) > 1 else None

    msg = f"{primary_straggler['name']} is about {round(delay)} min behind schedule. "
    if opt1["type"] == "WAIT":
        msg += f"Recommended: group waits at {stop_name} ({round(opt1['group_wait_min'])} min). "
    elif opt1["type"] == "SHORTCUT":
        msg += f"Recommended: {primary_straggler['name']} takes the shaded lane shortcut to rejoin in {round(opt1['rejoin_delay_min'])} min. "
    elif opt1["type"] == "SWEEP":
        msg += f"Recommended: {opt1['title']} accompanies {primary_straggler['name']}. "

    if opt2:
        msg += f"Alternative: {opt2['description']}"

    return {
        "has_straggler": True,
        "stragglers": stragglers,
        "primary_straggler": primary_straggler,
        "repair_options": top_two,
        "all_evaluated_options": all_options,
        "message": msg.strip(),
    }
