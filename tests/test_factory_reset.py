"""Integration test for the /api/factory_reset endpoint.

The button in Settings hits this endpoint, then wipes localStorage and
redirects to /. The contract is: after this call, /api/welcome must
return ``onboarded: false`` and oauth credentials must be gone.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Run the dashboard in a tmp working dir so the test can scribble
    quantclaw.yaml + data/ files without touching the user's real install."""
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir()
    from quantclaw.dashboard.api import app
    with TestClient(app) as c:
        yield c


def test_factory_reset_removes_yaml_and_credentials(client, tmp_path):
    # Seed the state we expect factory_reset to wipe.
    yaml_path = tmp_path / "quantclaw.yaml"
    yaml_path.write_text("llm_provider: openai\n", encoding="utf-8")
    creds_path = tmp_path / "data" / "oauth_credentials.json"
    creds_path.write_text(json.dumps({"openai": {"access_token": "xyz"}}), encoding="utf-8")

    # Sanity: /api/welcome should report onboarded=true while yaml exists.
    r = client.get("/api/welcome")
    assert r.status_code == 200
    assert r.json()["onboarded"] is True

    r = client.post("/api/factory_reset")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "factory_reset"
    cleared = body["cleared"]
    assert cleared.get("onboarding_config") == "removed"
    assert cleared.get("oauth_credentials") == "removed"

    assert not yaml_path.exists(), "factory_reset should delete quantclaw.yaml"
    assert not creds_path.exists(), "factory_reset should delete oauth_credentials.json"

    # Now /api/welcome must signal onboarding required so the dashboard
    # routes the user to the language picker on next load.
    r = client.get("/api/welcome")
    assert r.json()["onboarded"] is False


def test_factory_reset_idempotent_when_files_absent(client):
    """Pressing the button twice (or pressing it on a clean install)
    must not error — just no-op the missing pieces."""
    r = client.post("/api/factory_reset")
    assert r.status_code == 200
    cleared = r.json()["cleared"]
    assert cleared.get("onboarding_config") == "absent"
    assert cleared.get("oauth_credentials") == "absent"


def test_factory_reset_clears_in_memory_oauth_state(client):
    """A flow that's mid-handshake when the user clicks reset must not
    leave a stale 'waiting' entry that confuses the next OAuth attempt."""
    from quantclaw.dashboard import oauth
    oauth._auth_state["openai"] = {"status": "waiting", "state": "abc"}

    r = client.post("/api/factory_reset")
    assert r.status_code == 200
    assert "openai" not in oauth._auth_state
