"""
Parser benchmark: scores the offline deterministic parser and (when a
GROQ_API_KEY is available) the Groq open-weight parser on a hand-written,
code-mixed request set (English + romanized Bengali/Hindi).

Place names are scored by the same resolver the router uses, so synonyms
("clinic", "daktar", "hospital") all count as correct.
"""
import os
import json
import datetime
from typing import Dict, Any, List, Callable

from backend.routing import get_routing_engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_SET_PATH = os.path.join(ROOT, "tests", "parser_test_set.json")

PLACE_FIELDS = ("origin", "destination")
SCALAR_FIELDS = ("depart_time", "sun_tolerance")


def load_test_set(path: str = TEST_SET_PATH) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _canonical(engine, value: Any) -> Any:
    if value is None:
        return None
    resolved = engine.resolve_location(str(value))
    return resolved[2] if resolved else str(value).strip().lower()


def _score_case(engine, parsed: Dict[str, Any], expected: Dict[str, Any]) -> List[str]:
    errors = []
    for field in PLACE_FIELDS:
        if expected.get(field):
            got = _canonical(engine, parsed.get(field))
            exp = _canonical(engine, expected[field])
            if got != exp:
                errors.append(f"{field}: got '{parsed.get(field)}', expected '{expected[field]}'")
    for field in SCALAR_FIELDS:
        if expected.get(field) and parsed.get(field) != expected[field]:
            errors.append(f"{field}: got '{parsed.get(field)}', expected '{expected[field]}'")
    return errors


def score_parser(parser_fn: Callable[[str], Dict[str, Any]], parser_name: str,
                 test_set: List[Dict[str, Any]] = None,
                 require_source_prefix: str = None) -> Dict[str, Any]:
    engine = get_routing_engine()
    test_set = test_set if test_set is not None else load_test_set()

    failures = []
    per_lang: Dict[str, Dict[str, int]] = {}
    source_counts: Dict[str, int] = {}
    field_totals = {f: 0 for f in PLACE_FIELDS + SCALAR_FIELDS}
    field_hits = {f: 0 for f in PLACE_FIELDS + SCALAR_FIELDS}
    passed = 0

    for case in test_set:
        lang = case.get("lang", "en")
        bucket = per_lang.setdefault(lang, {"total": 0, "passed": 0})
        bucket["total"] += 1

        try:
            parsed = parser_fn(case["query"])
        except Exception as e:  # a parser crash is a failure, not a benchmark abort
            parsed = {"error": str(e)}

        src = str(parsed.get("parser_source", "unknown"))
        source_counts[src] = source_counts.get(src, 0) + 1

        errors = _score_case(engine, parsed, case["expected"])

        for field in PLACE_FIELDS:
            if case["expected"].get(field):
                field_totals[field] += 1
                if not any(err.startswith(f"{field}:") for err in errors):
                    field_hits[field] += 1
        for field in SCALAR_FIELDS:
            if case["expected"].get(field):
                field_totals[field] += 1
                if not any(err.startswith(f"{field}:") for err in errors):
                    field_hits[field] += 1

        if errors:
            failures.append({"id": case.get("id"), "lang": lang, "query": case["query"],
                             "errors": errors, "parsed": parsed})
        else:
            passed += 1
            bucket["passed"] += 1

    total = len(test_set)
    genuine_cases = sum(
        c for s, c in source_counts.items()
        if require_source_prefix and s.startswith(require_source_prefix)
    )
    status = "ok"
    if require_source_prefix and genuine_cases == 0:
        status = "model_unavailable: every request fell back, accuracy below reflects the fallback"

    return {
        "parser": parser_name,
        "timestamp": datetime.datetime.now().isoformat(),
        "status": status,
        "total": total,
        "passed": passed,
        "failed": len(failures),
        "accuracy_pct": round(passed / total * 100, 1) if total else 0.0,
        "parser_sources": source_counts,
        "per_language": {
            lang: {**b, "accuracy_pct": round(b["passed"] / b["total"] * 100, 1)}
            for lang, b in sorted(per_lang.items())
        },
        "field_accuracy": {
            f: round(field_hits[f] / field_totals[f] * 100, 1) if field_totals[f] else None
            for f in field_totals
        },
        "failures": failures,
    }
