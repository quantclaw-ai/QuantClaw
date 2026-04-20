"""Tests for orchestration API endpoints."""
import pytest
from fastapi.testclient import TestClient


def test_get_orchestration_status():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/orchestration/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "autonomy_mode" in data
    assert "trust_level" in data
    assert "ooda_phase" in data


def test_set_autonomy_mode():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.post("/api/orchestration/mode", json={"mode": "autopilot"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "autopilot"


def test_get_playbook_recent():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/orchestration/playbook/recent")
    assert resp.status_code == 200
    assert "entries" in resp.json()


def test_get_trust_status():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/orchestration/trust")
    assert resp.status_code == 200
    data = resp.json()
    assert "level" in data
    assert "metrics" in data


def test_kill_switch():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.post("/api/orchestration/kill")
    assert resp.status_code == 200
    assert resp.json()["status"] == "halted"
