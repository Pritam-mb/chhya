import os
import sys
import json

sys.path.insert(0, os.path.abspath("."))

from backend.routing import get_routing_engine

def main():
    print("=== Testing Chhaya Shade-Aware Routing Engine ===")
    engine = get_routing_engine()
    
    # Test pairs
    test_cases = [
        {
            "title": "Scenario 1 (The 3 PM Demo Walk): Dadu to Belle Vue Clinic",
            "origin": "home",
            "destination": "clinic",
            "time": "15:00",
            "tolerance": "low",
            "speed": 3.0
        },
        {
            "title": "Scenario 2: Flurys to Camac Square Mall at 15:00",
            "origin": "flurys",
            "destination": "camac square",
            "time": "15:00",
            "tolerance": "low",
            "speed": 3.5
        },
        {
            "title": "Scenario 3 (High Noon honesty): Home to Belle Vue Clinic at 12:00",
            "origin": "home",
            "destination": "clinic",
            "time": "12:00",
            "tolerance": "low",
            "speed": 3.0
        }
    ]
    
    for tc in test_cases:
        print(f"\n--- {tc['title']} ---")
        res = engine.plan_route(
            origin_query=tc["origin"],
            destination_query=tc["destination"],
            depart_time_str=tc["time"],
            sun_tolerance=tc["tolerance"],
            speed_kmh=tc["speed"]
        )
        
        print(f"Origin: {res['origin']['name']} -> Destination: {res['destination']['name']}")
        print(f"Time: {res['depart_time']} IST | Solar Elev: {res['solar_info']['elevation']}° | Shadow Factor: {res['solar_info']['shadow_factor']}x")
        print(f"Shortest Path: {res['shortest_route']['distance_meters']}m | Duration: {res['shortest_route']['duration_minutes']} min | Sun-minutes: {res['shortest_route']['sun_minutes']} min | Shade: {res['shortest_route']['shade_percentage']}%")
        print(f"Shaded Route:  {res['shade_route']['distance_meters']}m | Duration: {res['shade_route']['duration_minutes']} min | Sun-minutes: {res['shade_route']['sun_minutes']} min | Shade: {res['shade_route']['shade_percentage']}%")
        print(f"Comparison: Extra Dist: {res['comparison']['extra_distance_m']}m | Sun-Mins Saved: {res['comparison']['sun_minutes_saved']} min")
        print(f"Trade-off: \"{res['trade_off_sentence']}\"")

if __name__ == "__main__":
    main()
