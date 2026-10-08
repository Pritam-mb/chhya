from fastapi.testclient import TestClient
import datetime
from backend.main import app

client = TestClient(app)

def test_deep_endpoints():
    print("Testing /shadows...")
    res = client.get("/shadows")
    assert res.status_code == 200
    assert "type" in res.json()
    assert res.json()["type"] == "FeatureCollection"
    
    print("Testing /window...")
    res = client.get("/window")
    assert res.status_code == 200
    assert "best_window" in res.json()

    print("Testing /route...")
    res = client.post("/route", json={"origin":"home", "destination":"clinic", "depart_time":"15:00", "sun_tolerance":"low", "speed_kmh":3.0})
    assert res.status_code == 200
    data = res.json()
    assert "shade_route" in data
    assert "comparison" in data
    
    print("Testing /agent/chat offline fallback...")
    res = client.post("/agent/chat", json={"message": "walk to clinic at 3 pm"})
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    
    print("All endpoints tested successfully!")

if __name__ == "__main__":
    test_deep_endpoints()
