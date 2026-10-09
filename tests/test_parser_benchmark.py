import os
import sys
import json

sys.path.insert(0, os.path.abspath("."))
from backend.agent_parser import offline_parse_request
from backend.parser_benchmark import load_test_set, score_parser


def test_parser_accuracy():
    report = score_parser(offline_parse_request, "offline_deterministic")

    os.makedirs("data", exist_ok=True)
    with open("data/parser_benchmark_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    assert report["total"] == len(load_test_set())
    assert report["accuracy_pct"] >= 90.0, (
        f"Parser accuracy {report['accuracy_pct']}% is below 90% threshold"
    )
