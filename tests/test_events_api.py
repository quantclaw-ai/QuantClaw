"""Tests for events API with filters."""
from fastapi.testclient import TestClient


def test_events_default():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/events")
    assert resp.status_code == 200
    assert "events" in resp.json()


def test_events_with_limit():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/events?limit=5")
    assert resp.status_code == 200


def test_events_with_agent_filter():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/events?agent=scheduler")
    assert resp.status_code == 200


def test_events_with_type_filter():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/events?type=orchestration.*")
    assert resp.status_code == 200
