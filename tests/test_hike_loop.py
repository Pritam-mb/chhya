"""
Hike-loop tests: live positions, grass points, geo-locked stories, feed/join.
"""
import pytest
from fastapi.testclient import TestClient

import backend.db as db
from backend.db import init_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "hike.db"))
    import backend.main as main
    init_db()
    with TestClient(main.app) as c:
        yield c


def _trip(client):
    return client.post("/api/plan", json={
        "message": "Walk Dadu to the clinic around noon.", "mode": "family",
    }).json()["trip_code"]


def test_positions_and_stale_flag(client):
    code = _trip(client)
    r = client.post(f"/api/trip/{code}/position", json={"walker": "Rina", "lat": 22.551, "lon": 88.353})
    assert r.status_code == 200
    members = client.get(f"/api/trip/{code}/positions").json()["members"]
    assert len(members) == 1
    assert members[0]["walker"] == "Rina" and members[0]["stale"] is False
    assert client.post("/api/trip/nope/position", json={"walker": "R", "lat": 0, "lon": 0}).status_code == 404


def test_points_flow_checkin_and_completion(client):
    code = _trip(client)
    client.post(f"/api/trip/{code}/checkin", json={"walker": "Dadu", "stop_index": 1})
    board = client.get(f"/api/trip/{code}/points").json()["leaderboard"]
    assert board[0] == {"walker": "Dadu", "points": 10, "events": 1}
    r = client.post(f"/api/trip/{code}/reached", params={"walker": "Dadu"})
    assert r.json()["grass_points"]["points"] == 50
    board = client.get(f"/api/trip/{code}/points").json()["leaderboard"]
    assert board[0]["points"] == 60 and board[0]["events"] == 2
    top = client.get("/api/leaderboard").json()["leaderboard"]
    assert any(w["walker"] == "Dadu" and w["points"] == 60 for w in top)


def test_story_lock_unlock_and_no_double_points(client):
    code = _trip(client)
    lat, lon = 22.5510, 88.3530
    card = client.post("/api/cards", json={
        "trip_code": code, "type": "story", "text": "Old banyan with hornbills",
        "lat": lat, "lon": lon,
    }).json()
    # ~155 m away: inside the 300 m radar but outside the 60 m unlock ring
    far_lat, far_lon = 22.5524, 88.3530
    far = client.get("/api/cards/near", params={"lat": far_lat, "lon": far_lon}).json()
    mine = [c for c in far["radar_cards"] if c["id"] == card["id"]][0]
    assert mine["locked"] is True and "locked" in mine["text"]
    # unlock attempt from far away fails honestly
    r = client.post(f"/api/cards/{card['id']}/unlock", json={
        "walker": "Rina", "trip_code": code, "lat": far_lat, "lon": far_lon})
    assert r.json()["unlocked"] is False
    # at the spot: unlock + 25, full text
    r2 = client.post(f"/api/cards/{card['id']}/unlock", json={
        "walker": "Rina", "trip_code": code, "lat": lat, "lon": lon})
    body = r2.json()
    assert body["unlocked"] is True and body["points"] == 25
    assert body["text"] == "Old banyan with hornbills"
    # repeat unlock: no repeat points
    r3 = client.post(f"/api/cards/{card['id']}/unlock", json={
        "walker": "Rina", "trip_code": code, "lat": lat, "lon": lon})
    assert r3.json()["already"] is True and r3.json()["points"] == 0
    board = client.get(f"/api/trip/{code}/points").json()["leaderboard"]
    assert board[0] == {"walker": "Rina", "points": 25, "events": 1}
    # non-story cards cannot unlock
    tip = client.post("/api/cards", json={
        "trip_code": code, "type": "tip", "text": "bench here", "lat": lat, "lon": lon}).json()
    assert client.post(f"/api/cards/{tip['id']}/unlock", json={
        "walker": "R", "trip_code": code, "lat": lat, "lon": lon}).status_code == 400


def test_feed_publish_join_and_category(client):
    code = _trip(client)
    assert client.get("/api/feed").json()["trips"] == []
    assert client.post(f"/api/trip/{code}/publish", json={"title": " "}).status_code == 400
    r = client.post(f"/api/trip/{code}/publish", json={"title": "Sunday shade hike"})
    assert r.json()["published"] is True
    feed = client.get("/api/feed").json()["trips"]
    assert len(feed) == 1
    item = feed[0]
    assert item["title"] == "Sunday shade hike"
    assert item["category"] in ("Short stroll", "Medium march", "Long haul")
    assert item["package"] in ("food package", "carry water")
    assert "from" in item and "to" in item and "walkers" in item
    j = client.post(f"/api/trip/{code}/join", json={"walker": "Newbie"})
    assert j.json()["points"] == 5
    assert "Newbie" in [w["name"] for w in j.json()["walkers"]]
    # joining twice: no double points, no duplicate walker
    j2 = client.post(f"/api/trip/{code}/join", json={"walker": "newbie"})
    assert j2.json()["points"] == 0
    assert [w["name"] for w in j.json()["walkers"]] == [w["name"] for w in j2.json()["walkers"]]
    assert client.post("/api/trip/nope/join", json={"walker": "X"}).status_code == 404
