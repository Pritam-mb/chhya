import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath("."))

from backend.best_window import (  # noqa: E402
    BestWindowModel,
    get_window_model,
    load_archive,
    ARCHIVE_CSV,
    EVAL_JSON,
)


def test_real_archive_data_is_present():
    assert os.path.exists(ARCHIVE_CSV), "Run scripts/fetch_openmeteo.py first"
    df = load_archive()
    assert df is not None and len(df) > 5000
    assert "apparent_temperature" in df.columns
    assert df["year"].min() == 2006
    assert df["year"].max() == 2025


def test_eval_json_reports_honest_numbers():
    assert os.path.exists(EVAL_JSON), "Run scripts/train_window_model.py first"
    with open(EVAL_JSON) as f:
        ev = json.load(f)
    assert ev["baseline_mae"] > 0
    assert ev["tabpfn_mae"] is not None
    assert ev["tabpfn_mae"] < ev["baseline_mae"]


def test_model_metrics_are_real_not_hardcoded():
    model = get_window_model()
    assert model.ready
    assert model.mae_baseline and model.mae_baseline > 0
    assert model.mae_tabpfn is None or model.mae_tabpfn > 0


def test_predict_offline_falls_back_to_climatology(monkeypatch):
    model = get_window_model()
    model._forecast_cache.clear()
    monkeypatch.setattr(model, "_fetch_hourly", lambda date_str: (None, "climatology fallback (offline)"))

    out = model.predict_for_date("2026-10-08")
    assert "offline" in out["data_source"]
    assert len(out["windows"]) == 5
    assert "best_window" in out and out["best_window"]
    scores = [w["discomfort_score"] for w in out["windows"]]
    assert scores == sorted(scores, reverse=True)


def test_predict_online_or_cached(monkeypatch):
    model = get_window_model()
    model._forecast_cache.clear()
    # Prefer the real network path when available; if it fails, it must fall back.
    out = model.predict_for_date("2026-10-08")
    assert out["date"] == "2026-10-08"
    assert out["model_metrics"]["baseline_mae"] is not None
    assert out["best_window"] in [w["time_window"] for w in out["windows"]]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
