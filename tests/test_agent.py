import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("."))

from backend.main import app  # noqa: E402
from backend.agent import get_agent, TOOL_REGISTRY  # noqa: E402

client = TestClient(app)


def test_tool_registry_exposes_four_tools():
    assert set(TOOL_REGISTRY) == {"plan_route", "best_window", "get_shadows", "list_pois"}
    for spec in TOOL_REGISTRY.values():
        assert "description" in spec and "parameters" in spec


def test_agent_deterministic_plans_a_shaded_route():
    agent = get_agent()
    out = agent.run("Walk dadu from home to the clinic at 3 pm, he can't take much sun")
    assert out["reply"]
    assert out["route_data"] is not None
    assert out["route_data"]["depart_time"] == "15:00"
    assert out["route_data"]["comparison"]["sun_minutes_saved"] >= 0
    assert any(c["tool"] == "plan_route" for c in out["tool_calls"])


def test_agent_asks_for_clarification_on_unknown_place():
    agent = get_agent()
    out = agent.run("walk from spaceport to moonbase at 3 pm")
    assert out.get("clarification") is True
    assert out["route_data"] is None
    assert "couldn't place" in out["reply"]


def test_agent_tools_endpoint():
    res = client.get("/agent/tools")
    assert res.status_code == 200
    names = {t["name"] for t in res.json()["tools"]}
    assert {"plan_route", "best_window"}.issubset(names)


def test_agent_chat_endpoint():
    res = client.post("/agent/chat", json={"message": "walk to the clinic at 3 pm"})
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert "tool_calls" in data


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
