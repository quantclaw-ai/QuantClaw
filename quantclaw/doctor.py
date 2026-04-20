"""QuantClaw Doctor: health check and auto-repair for the full stack."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Status(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"
    FIXED = "fixed"


@dataclass(frozen=True)
class CheckResult:
    status: Status
    message: str


# ── Colors ──

_COLORS = {
    Status.OK: "\033[32m",     # green
    Status.WARN: "\033[33m",   # yellow
    Status.FAIL: "\033[31m",   # red
    Status.SKIP: "\033[90m",   # gray
    Status.FIXED: "\033[36m",  # cyan
}
_RESET = "\033[0m"
_BOLD = "\033[1m"

_LABELS = {
    Status.OK: "OK",
    Status.WARN: "WARN",
    Status.FAIL: "FAIL",
    Status.SKIP: "SKIP",
    Status.FIXED: "FIXED",
}


def _print_result(result: CheckResult) -> None:
    color = _COLORS[result.status]
    label = _LABELS[result.status]
    print(f"  {color}[{label:>5}]{_RESET}  {result.message}")


# ── Port checking ──

def _is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


# ── Checks ──

def check_python() -> CheckResult:
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if v.major == 3 and v.minor >= 12:
        return CheckResult(Status.OK, f"Python {version_str}")
    return CheckResult(Status.FAIL, f"Python {version_str} — requires 3.12+")


def check_pip_deps(repair: bool) -> CheckResult:
    try:
        import quantclaw  # noqa: F401
        import fastapi  # noqa: F401
        import aiosqlite  # noqa: F401
        import croniter  # noqa: F401
        return CheckResult(Status.OK, "pip dependencies installed")
    except ImportError as e:
        if repair:
            root = Path(__file__).parent.parent
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", str(root), "-q"],
                capture_output=True,
            )
            return CheckResult(Status.FIXED, f"pip dependencies installed (was missing: {e.name})")
        return CheckResult(Status.WARN, f"Missing pip dependency: {e.name} — run with --repair")


def check_node() -> CheckResult:
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=5
        )
        version = result.stdout.strip()
        return CheckResult(Status.OK, f"Node.js {version}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return CheckResult(Status.FAIL, "Node.js not found — install from nodejs.org")


def check_dashboard_deps(repair: bool) -> CheckResult:
    dashboard = Path(__file__).parent / "dashboard" / "app"
    node_modules = dashboard / "node_modules"
    if node_modules.exists():
        return CheckResult(Status.OK, "Dashboard dependencies installed")
    if repair:
        subprocess.run(
            ["npm", "install"], cwd=str(dashboard), capture_output=True, shell=True,
        )
        if node_modules.exists():
            return CheckResult(Status.FIXED, "Dashboard dependencies installed")
        return CheckResult(Status.FAIL, "npm install failed in dashboard/app")
    return CheckResult(Status.WARN, "Dashboard deps missing — run with --repair")


def check_data_dir(repair: bool) -> CheckResult:
    data_dir = Path("data")
    if data_dir.exists():
        return CheckResult(Status.OK, "Data directory exists")
    if repair:
        data_dir.mkdir(parents=True, exist_ok=True)
        return CheckResult(Status.FIXED, "Data directory created")
    return CheckResult(Status.WARN, "Data directory missing — run with --repair")


def check_sqlite(repair: bool) -> CheckResult:
    db_path = Path("data/quantclaw.db")
    if not db_path.parent.exists():
        if repair:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            return CheckResult(Status.WARN, "Data directory missing")

    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        expected = {"tasks", "events", "sessions", "plans"}
        missing = expected - tables

        if not missing:
            return CheckResult(Status.OK, f"SQLite database ({len(tables)} tables)")

        if repair:
            # Import and run schema creation
            import asyncio
            from quantclaw.state.db import StateDB
            asyncio.run(StateDB.create(str(db_path)))
            return CheckResult(Status.FIXED, f"SQLite schema updated (added {missing})")

        return CheckResult(Status.WARN, f"Missing tables: {missing} — run with --repair")
    except Exception as e:
        return CheckResult(Status.FAIL, f"SQLite error: {e}")


def check_playbook(repair: bool) -> CheckResult:
    pb_path = Path("data/playbook.jsonl")
    if not pb_path.exists():
        if repair:
            pb_path.parent.mkdir(parents=True, exist_ok=True)
            pb_path.touch()
            return CheckResult(Status.FIXED, "Playbook created (empty)")
        return CheckResult(Status.WARN, "Playbook missing — run with --repair")

    # Validate JSONL
    entry_count = 0
    try:
        with open(pb_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                json.loads(line)  # Validates JSON
                entry_count += 1
        return CheckResult(Status.OK, f"Playbook ({entry_count} entries)")
    except json.JSONDecodeError as e:
        return CheckResult(Status.FAIL, f"Playbook has invalid JSON at line {i + 1}: {e}")


def check_config(repair: bool) -> CheckResult:
    config_path = Path("quantclaw.yaml")
    default_path = Path(__file__).parent / "config" / "default.yaml"

    if config_path.exists():
        return CheckResult(Status.OK, "Config loaded (quantclaw.yaml)")

    if default_path.exists():
        if repair:
            import shutil
            shutil.copy2(default_path, config_path)
            return CheckResult(Status.FIXED, "Config created from defaults")
        return CheckResult(Status.OK, "Using default config")

    return CheckResult(Status.WARN, "No config found")


def check_llm_provider() -> CheckResult:
    providers = []

    # Check Ollama
    if _is_port_open(11434):
        providers.append("Ollama (localhost:11434)")

    # Check API keys
    for name, env_var in [
        ("Anthropic", "ANTHROPIC_API_KEY"),
        ("OpenAI", "OPENAI_API_KEY"),
        ("Google", "GEMINI_API_KEY"),
        ("DeepSeek", "DEEPSEEK_API_KEY"),
    ]:
        if os.environ.get(env_var):
            providers.append(f"{name} (${env_var})")

    if providers:
        return CheckResult(Status.OK, f"LLM providers: {', '.join(providers)}")
    return CheckResult(
        Status.FAIL,
        "No LLM provider — install Ollama or set ANTHROPIC_API_KEY / OPENAI_API_KEY",
    )


def check_backend() -> CheckResult:
    if _is_port_open(8000):
        return CheckResult(Status.OK, "Backend (port 8000)")
    return CheckResult(Status.SKIP, "Backend (port 8000) — not running")


def check_sidecar() -> CheckResult:
    if _is_port_open(8001):
        return CheckResult(Status.OK, "Sidecar (port 8001)")
    return CheckResult(Status.SKIP, "Sidecar (port 8001) — not running")


def check_dashboard() -> CheckResult:
    if _is_port_open(3000):
        return CheckResult(Status.OK, "Dashboard (port 3000)")
    return CheckResult(Status.SKIP, "Dashboard (port 3000) — not running")


def check_agents() -> CheckResult:
    try:
        from quantclaw.agents import ALL_AGENTS
        count = len(ALL_AGENTS)
        return CheckResult(Status.OK, f"{count} agents registered")
    except Exception as e:
        return CheckResult(Status.FAIL, f"Agent loading failed: {e}")


def check_ooda() -> CheckResult:
    if not _is_port_open(8000):
        return CheckResult(Status.SKIP, "OODA loop — server not running")
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://127.0.0.1:8000/api/orchestration/status", timeout=3)
        data = json.loads(resp.read())
        phase = data.get("ooda_phase", "unknown")
        mode = data.get("autonomy_mode", "unknown")
        return CheckResult(Status.OK, f"OODA loop (phase: {phase}, mode: {mode})")
    except Exception:
        return CheckResult(Status.WARN, "OODA loop — endpoint not responding")


# ── Runner ──

def run_doctor(repair: bool = False) -> int:
    print(f"\n  {_BOLD}QuantClaw Doctor{_RESET}\n")

    checks = [
        check_python(),
        check_pip_deps(repair),
        check_node(),
        check_dashboard_deps(repair),
        check_data_dir(repair),
        check_sqlite(repair),
        check_playbook(repair),
        check_config(repair),
        check_llm_provider(),
        check_backend(),
        check_sidecar(),
        check_dashboard(),
        check_agents(),
        check_ooda(),
    ]

    for result in checks:
        _print_result(result)

    # Summary
    counts = {}
    for r in checks:
        counts[r.status] = counts.get(r.status, 0) + 1

    ok = counts.get(Status.OK, 0) + counts.get(Status.FIXED, 0)
    failed = counts.get(Status.FAIL, 0)
    warned = counts.get(Status.WARN, 0)
    skipped = counts.get(Status.SKIP, 0)
    fixed = counts.get(Status.FIXED, 0)

    parts = [f"{ok} passed"]
    if failed:
        parts.append(f"{failed} failed")
    if warned:
        parts.append(f"{warned} warnings")
    if skipped:
        parts.append(f"{skipped} skipped")
    if fixed:
        parts.append(f"{fixed} fixed")

    print(f"\n  {', '.join(parts)}")

    if warned and not repair:
        print(f"  Run '{_BOLD}quantclaw doctor --repair{_RESET}' to fix warnings.")
    print()

    return 1 if failed else 0


# ── CLI entry point ──

def main():
    repair = "--repair" in sys.argv or "--fix" in sys.argv
    exit_code = run_doctor(repair=repair)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
