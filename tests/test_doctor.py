"""Tests for quantclaw doctor health checks."""
import json
import pytest
from pathlib import Path

from quantclaw.doctor import (
    CheckResult, Status,
    check_python, check_pip_deps, check_node,
    check_data_dir, check_playbook, check_config,
    check_agents, check_llm_provider,
)


def test_check_python_ok():
    result = check_python()
    assert result.status == Status.OK
    assert "3.12" in result.message


def test_check_pip_deps_ok():
    result = check_pip_deps(repair=False)
    assert result.status == Status.OK


def test_check_node():
    result = check_node()
    # Either OK (node installed) or FAIL (not installed) — both valid
    assert result.status in (Status.OK, Status.FAIL)


def test_check_data_dir_creates_on_repair(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = check_data_dir(repair=False)
    assert result.status == Status.WARN

    result = check_data_dir(repair=True)
    assert result.status == Status.FIXED
    assert (tmp_path / "data").exists()


def test_check_playbook_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    result = check_playbook(repair=False)
    assert result.status == Status.WARN


def test_check_playbook_creates_on_repair(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    result = check_playbook(repair=True)
    assert result.status == Status.FIXED
    assert (tmp_path / "data" / "playbook.jsonl").exists()


def test_check_playbook_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pb = tmp_path / "data" / "playbook.jsonl"
    pb.parent.mkdir()
    pb.write_text(
        json.dumps({"entry_type": "strategy_result", "content": {}, "tags": [], "timestamp": "t"}) + "\n"
    )
    result = check_playbook(repair=False)
    assert result.status == Status.OK
    assert "1 entries" in result.message


def test_check_playbook_invalid_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pb = tmp_path / "data" / "playbook.jsonl"
    pb.parent.mkdir()
    pb.write_text("not json\n")
    result = check_playbook(repair=False)
    assert result.status == Status.FAIL


def test_check_config_default():
    result = check_config(repair=False)
    # Either OK (config exists) or OK (using defaults)
    assert result.status in (Status.OK, Status.FIXED)


def test_check_agents():
    result = check_agents()
    assert result.status == Status.OK
    assert "12" in result.message


def test_check_llm_provider():
    result = check_llm_provider()
    # Either OK (some provider available) or FAIL (none)
    assert result.status in (Status.OK, Status.FAIL)
