"""
Benchmark the request parsers on the hand-written code-mixed test set.

Writes:
  results/parser_offline.json  (always)
  results/parser_groq.json     (only when GROQ_API_KEY is set)

Run:  python scripts/benchmark_parser.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.agent_parser import offline_parse_request, parse_request_with_llm  # noqa: E402
from backend.parser_benchmark import load_test_set, score_parser  # noqa: E402


def main():
    test_set = load_test_set()
    os.makedirs("results", exist_ok=True)

    offline = score_parser(offline_parse_request, "offline_deterministic", test_set)
    with open("results/parser_offline.json", "w", encoding="utf-8") as f:
        json.dump(offline, f, indent=2, ensure_ascii=False)
    _print_summary(offline)

    if os.environ.get("GROQ_API_KEY"):
        groq = score_parser(parse_request_with_llm, "groq_open_weight", test_set)
        with open("results/parser_groq.json", "w", encoding="utf-8") as f:
            json.dump(groq, f, indent=2, ensure_ascii=False)
        _print_summary(groq)
    else:
        print("\n[groq] skipped: GROQ_API_KEY not set. Set it and re-run to benchmark "
              "the open-weight model path (results/parser_groq.json).")


def _print_summary(report):
    print(f"\n=== {report['parser']} === accuracy {report['accuracy_pct']}% "
          f"({report['passed']}/{report['total']})")
    for lang, b in report["per_language"].items():
        print(f"  {lang:>4}: {b['passed']}/{b['total']}  ({b['accuracy_pct']}%)")
    for fail in report["failures"]:
        print(f"  FAIL {fail['id']} [{fail['lang']}]: {fail['query']}")
        for err in fail["errors"]:
            print(f"       - {err}")


if __name__ == "__main__":
    main()
