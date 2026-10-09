"""
Trip chat room + cards-anywhere (motives, photos) tests.
- chat posts, polls with since_id, strips PII, rejects empty, 404s unknown trips
- check-ins leave a system chat message
- card types hike/story accepted, unknown types 422
- oversized photos are dropped but the text still pins
"""
import pytest
from fastapi.testclient import TestClient

import backend.db as db
from backend.db import init_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "chat.db"))
    import backend.main as main
    init_db()
    with TestClient(main.app) as c:
        yield c


def _trip(client):
    return client.post("/api/plan", json={
        "message": "Walk Dadu to the clinic around noon.", "mode": "family",
    }).json()["trip_code"]


def test_chat_post_poll_and_pii(client):
    code = _trip(client)
    r = client.post(f"/api/trip/{code}/chat", json={"walker": "Rina", "text": "Wait at the bench, call 9876543210"})
    assert r.status_code == 200
    body = r.json()
    assert "[PHONE REMOVED]" in body["text"]
    # check-in leaves a system message
    client.post(f"/api/trip/{code}/checkin", json={"walker": "Dadu", "stop_index": 1})
    all_msgs = client.get(f"/api/trip/{code}/chat").json()["messages"]
    assert len(all_msgs) == 2
    assert all_msgs[1]["is_system"] is True
    assert "Stop 1" in all_msgs[1]["text"]
    # polling with since_id returns only newer
    newer = client.get(f"/api/trip/{code}/chat", params={"since_id": all_msgs[0]["id"]}).json()["messages"]
    assert len(newer) == 1
    assert newer[0]["is_system"] is True


def test_chat_empty_and_unknown_trip(client):
    code = _trip(client)
    assert client.post(f"/api/trip/{code}/chat", json={"walker": "R", "text": "   "}).status_code == 400
    assert client.post("/api/trip/nope/chat", json={"walker": "R", "text": "hi"}).status_code == 404
    assert client.get("/api/trip/nope/chat").status_code == 404


def test_card_motives_and_photo(client):
    base = {"trip_code": "t1", "text": "Shady steps behind the market", "lat": 22.551, "lon": 88.353}
    for motive in ["hike", "story", "tip", "warning", "meetup", "note"]:
        r = client.post("/api/cards", json={**base, "type": motive})
        assert r.status_code == 200, motive
    bad = client.post("/api/cards", json={**base, "type": "party"})
    assert bad.status_code == 422
    # photo round-trips on immediate cards
    photo = "data:image/jpeg;base64," + "A" * 1000
    r = client.post("/api/cards", json={**base, "type": "story", "photo": photo})
    assert r.json()["has_photo"] is True
    near = client.get("/api/cards/near", params={"lat": 22.551, "lon": 88.353}).json()
    mine = [c for c in near["immediate_cards"] if c["text"] == base["text"] and c["has_photo"]]
    assert mine and mine[0]["photo"] == photo
    # oversized photo dropped, text still pinned
    big = "data:image/jpeg;base64," + "B" * 400000
    r2 = client.post("/api/cards", json={**base, "type": "story", "text": "big photo tale", "photo": big})
    assert r2.status_code == 200
    assert r2.json()["moderation_status"] == "photo_too_large_dropped"
    assert r2.json()["has_photo"] is False
