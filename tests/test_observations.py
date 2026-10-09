"""
Unit tests for shade observations and calibration (Section 3.6 / V10).
- taps store predicted vs observed with sun position and time
- meter reports counts alongside matches, never a bare percentage
- per-label correction is learned only after enough taps, and is clamped
"""
import pytest
from fastapi.testclient import TestClient

import backend.db as db
from backend.db import init_db, record_observation, get_accuracy_summary
from backend.config import OBS_MIN_TAPS_FOR_CORRECTION, OBS_MAX_CORRECTION


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    init_db()
    return db


def test_match_counts_and_tolerance(tmp_db):
    # |1.0 - 0.82| = 0.18 <= 0.25 -> match
    r1 = record_observation("t1", "A", "Lane X", 0.82, 1.0)
    assert r1["matched"] is True
    # |0.0 - 0.82| = 0.82 -> miss
    r2 = record_observation("t1", "A", "Lane X", 0.82, 0.0)
    assert r2["matched"] is False
    s = get_accuracy_summary()
    assert s["taps"] == 2
    assert s["matched"] == 1
    assert s["streets"][0]["taps"] == 2


def test_no_correction_before_enough_taps(tmp_db):
    for _ in range(OBS_MIN_TAPS_FOR_CORRECTION - 1):
        record_observation("t1", "A", "Lane Y", 0.9, 1.0)
    s = get_accuracy_summary()
    assert s["streets"][0]["correction"] is None
    assert s["streets"][0]["correction_ready"] is False
    assert s["corrections"] == {}


def test_correction_learned_and_clamped(tmp_db):
    # mean error = -0.9 -> clamped to -OBS_MAX_CORRECTION
    for _ in range(OBS_MIN_TAPS_FOR_CORRECTION):
        record_observation("t1", "A", "Lane Z", 0.9, 0.0)
    s = get_accuracy_summary()
    assert s["streets"][0]["correction"] == pytest.approx(-OBS_MAX_CORRECTION)
    assert s["corrections"] == {"Lane Z": pytest.approx(-OBS_MAX_CORRECTION)}


def test_observation_endpoints(tmp_path, monkeypatch):
    # main.py's handlers call backend.db functions, which read DB_PATH at
    # call time, so patching the module attribute keeps this hermetic.
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "api.db"))
    import backend.main as main
    init_db()
    client = TestClient(main.app)
    code = client.post("/api/plan", json={"message": "Walk Dadu to the clinic around noon.", "mode": "family"}).json()["trip_code"]
    r = client.post(f"/api/trip/{code}/observation", json={
        "walker": "Tester", "label": "Test Lane", "observed": "shade",
        "predicted_shade": 0.8, "stop_index": 1,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is True
    assert body["label"] == "Test Lane"
    # unknown trip -> 404, never a silent save
    r404 = client.post("/api/trip/does-not-exist/observation", json={
        "walker": "T", "label": "X", "observed": "sun",
    })
    assert r404.status_code == 404
    acc = client.get("/api/accuracy").json()
    assert acc["taps"] >= 1
    assert "matched" in acc and "streets" in acc and "corrections" in acc
