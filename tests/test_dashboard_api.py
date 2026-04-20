import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    # Need to handle the lifespan
    import asyncio
    from quantclaw.dashboard.api import app, _bus
    from quantclaw.state.db import StateDB

    # Override DB path for testing
    with TestClient(app) as c:
        yield c

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "system" in data
    assert "agents" in data
    assert "plugins" in data
    assert "notifications" in data
    assert data["agents"]["total"] == 12
    assert data["database"] == "connected"

def test_welcome_status(client):
    r = client.get("/api/welcome")
    assert r.status_code == 200
    assert "onboarded" in r.json()

def test_get_templates(client):
    r = client.get("/api/strategies/templates")
    assert r.status_code == 200
    assert "available" in r.json()

def test_get_agents(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    assert len(r.json()["agents"]) == 12

def test_get_plugins(client):
    r = client.get("/api/plugins")
    assert r.status_code == 200
    assert "broker" in r.json()["plugins"]

def test_get_events(client):
    r = client.get("/api/events")
    assert r.status_code == 200
    assert "events" in r.json()

def test_get_portfolio(client):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    assert r.json()["equity"] == 100000

def test_get_risk(client):
    r = client.get("/api/risk")
    assert r.status_code == 200
    assert "max_drawdown" in r.json()
