from quantclaw.config.loader import load_config

def test_load_default_config():
    config = load_config()
    assert "models" in config
    assert "schedules" in config
    assert "notification_routes" in config
    assert config["models"]["planner"] == "opus"

def test_load_config_override(tmp_path):
    override = tmp_path / "override.yaml"
    override.write_text("models:\n  planner: sonnet\n")
    config = load_config(str(override))
    assert config["models"]["planner"] == "sonnet"
