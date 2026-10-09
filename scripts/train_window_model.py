"""
Evaluate the TabPFN best-window model against the climatology baseline on the
held-out October (2025) days and write results/window_eval.json.

Run:  python scripts/train_window_model.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.best_window import get_window_model, EVAL_JSON  # noqa: E402


def main():
    print("Loading archive + fitting TabPFN on CPU (this can take a moment) ...")
    model = get_window_model()
    if not model.ready:
        raise SystemExit("No archive data found. Run scripts/fetch_openmeteo.py first.")

    eval_result = model.evaluate_heldout()
    os.makedirs("results", exist_ok=True)
    with open(EVAL_JSON, "w") as f:
        json.dump(eval_result, f, indent=2)

    print(json.dumps(eval_result, indent=2))
    print(f"\nWrote {EVAL_JSON}")


if __name__ == "__main__":
    main()
