import os
import sys
import json

sys.path.insert(0, os.path.abspath("."))
from backend.agent_parser import offline_parse_request, parse_request_with_llm

HANDWRITTEN_TEST_SET = [
    {
        "query": "Walk dadu to the clinic around 3 pm, he can't take much sun.",
        "expected": {"origin": "home", "destination": "clinic", "depart_time": "15:00", "sun_tolerance": "low"}
    },
    {
        "query": "Take dadu to Belle Vue Clinic at 3 pm, avoid sun exposure please.",
        "expected": {"origin": "home", "destination": "belle vue clinic", "depart_time": "15:00", "sun_tolerance": "low"}
    },
    {
        "query": "Walk from Flurys to Camac Square at noon, fast pace.",
        "expected": {"origin": "flurys", "destination": "camac square", "depart_time": "12:00", "sun_tolerance": "medium"}
    },
    {
        "query": "Need to go from Oxford Bookstore to Park Clinic around 4 pm, dadu walks slowly.",
        "expected": {"origin": "oxford bookstore", "destination": "park clinic", "depart_time": "16:00", "sun_tolerance": "low"}
    },
    {
        "query": "Bring dadu to the doctor at 10 am, keep in shade.",
        "expected": {"origin": "home", "destination": "doctor", "depart_time": "10:00", "sun_tolerance": "low"}
    },
    {
        "query": "Walk to Russell Street Pharmacy at 9 am from home.",
        "expected": {"origin": "home", "destination": "russell street pharmacy", "depart_time": "09:00"}
    },
    {
        "query": "From Middleton Row to Belle Vue around 2 pm, patient can't take direct heat.",
        "expected": {"origin": "middleton row", "destination": "belle vue", "depart_time": "14:00", "sun_tolerance": "low"}
    },
    {
        "query": "Quick stroll from Flurys to Oxford Bookstore at 5 pm, don't mind sun.",
        "expected": {"origin": "flurys", "destination": "oxford bookstore", "depart_time": "17:00", "sun_tolerance": "high"}
    },
    {
        "query": "Dadu needs to visit the clinic around 15:00, sensitive to sun.",
        "expected": {"origin": "home", "destination": "clinic", "depart_time": "15:00", "sun_tolerance": "low"}
    },
    {
        "query": "Walk from Camac Street to Flurys at 11 am, shaded only.",
        "expected": {"origin": "camac street", "destination": "flurys", "depart_time": "11:00", "sun_tolerance": "low"}
    },
    {
        "query": "Going to Belle Vue Clinic around 3 pm with grandpa.",
        "expected": {"origin": "home", "destination": "belle vue clinic", "depart_time": "15:00", "sun_tolerance": "low"}
    },
    {
        "query": "Walk to Park Clinic from Flurys around 1 pm, speed 3 km/h.",
        "expected": {"origin": "flurys", "destination": "park clinic", "depart_time": "13:00"}
    },
    {
        "query": "Head to Russell Street Market from home at 8 am.",
        "expected": {"origin": "home", "destination": "russell street market", "depart_time": "08:00"}
    },
    {
        "query": "Take grandma to the clinic at 3:30 pm, minimum sun.",
        "expected": {"origin": "home", "destination": "clinic", "depart_time": "15:30", "sun_tolerance": "low"}
    },
    {
        "query": "Fast walk from Oxford Bookstore to Camac Square at noon.",
        "expected": {"origin": "oxford bookstore", "destination": "camac square", "depart_time": "12:00"}
    },
    {
        "query": "Walk from home to Belle Vue Clinic around 16:00, dadu has skin allergy.",
        "expected": {"origin": "home", "destination": "belle vue clinic", "depart_time": "16:00", "sun_tolerance": "low"}
    },
    {
        "query": "From Flurys to Russell Street at 2 pm.",
        "expected": {"origin": "flurys", "destination": "russell street", "depart_time": "14:00"}
    },
    {
        "query": "Go to clinic around 3 pm, no sun please.",
        "expected": {"origin": "home", "destination": "clinic", "depart_time": "15:00", "sun_tolerance": "low"}
    },
    {
        "query": "Walk dadu gently to pharmacy at 10:30 am.",
        "expected": {"origin": "home", "destination": "pharmacy", "depart_time": "10:30", "sun_tolerance": "low"}
    },
    {
        "query": "From Russell Street to Belle Vue Clinic at 3 pm, elderly walk.",
        "expected": {"origin": "russell street", "destination": "belle vue clinic", "depart_time": "15:00", "sun_tolerance": "low"}
    },
    {
        "query": "Rush to Park Clinic from Camac Square at 1 pm, fastest route.",
        "expected": {"origin": "camac square", "destination": "park clinic", "depart_time": "13:00", "sun_tolerance": "high"}
    },
    {
        "query": "Walk from Middleton Row to Flurys tea room at 4 pm.",
        "expected": {"origin": "middleton row", "destination": "flurys tea room", "depart_time": "16:00"}
    },
    {
        "query": "Take patient to clinic around 15:00, zero sun tolerance.",
        "expected": {"origin": "home", "destination": "clinic", "depart_time": "15:00", "sun_tolerance": "low"}
    },
    {
        "query": "Stroll to Oxford Bookstore at 5 pm, avoid direct afternoon sun.",
        "expected": {"origin": "home", "destination": "oxford bookstore", "depart_time": "17:00", "sun_tolerance": "low"}
    },
    {
        "query": "Walk dadu to the clinic around noon, he can't take much sun.",
        "expected": {"origin": "home", "destination": "clinic", "depart_time": "12:00", "sun_tolerance": "low"}
    }
]

def test_parser_accuracy():
    passed = 0
    failures = []
    
    for idx, test in enumerate(HANDWRITTEN_TEST_SET, 1):
        q = test["query"]
        exp = test["expected"]
        res = offline_parse_request(q)
        
        # Check criteria
        errors = []
        if exp.get("origin") and exp["origin"] not in res["origin"] and res["origin"] not in exp["origin"]:
            errors.append(f"Origin mismatch: got '{res['origin']}', expected '{exp['origin']}'")
        if exp.get("destination") and exp["destination"] not in res["destination"] and res["destination"] not in exp["destination"]:
            errors.append(f"Destination mismatch: got '{res['destination']}', expected '{exp['destination']}'")
        if exp.get("depart_time") and res["depart_time"] != exp["depart_time"]:
            errors.append(f"Depart time mismatch: got '{res['depart_time']}', expected '{exp['depart_time']}'")
        if exp.get("sun_tolerance") and res["sun_tolerance"] != exp["sun_tolerance"]:
            errors.append(f"Sun tolerance mismatch: got '{res['sun_tolerance']}', expected '{exp['sun_tolerance']}'")
            
        if not errors:
            passed += 1
        else:
            failures.append({"query": q, "errors": errors, "parsed": res})
            
    accuracy = (passed / len(HANDWRITTEN_TEST_SET))
    
    # Save benchmark report for submission documentation and README
    report = {
        "timestamp": "2026-10-08",
        "total_tests": len(HANDWRITTEN_TEST_SET),
        "passed": passed,
        "failed": len(failures),
        "accuracy_pct": round(accuracy * 100, 1),
        "failures": failures
    }
    
    os.makedirs("data", exist_ok=True)
    with open("data/parser_benchmark_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    assert accuracy >= 0.90, f"Parser accuracy {accuracy * 100}% is below 90% threshold"

