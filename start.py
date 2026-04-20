"""QuantClaw -- single command to install, start, and stop everything."""
import subprocess
import sys
import os
import time
import signal
import json
from pathlib import Path

ROOT = Path(__file__).parent
SIDECAR_DIR = ROOT / "quantclaw" / "sidecar"
DASHBOARD_DIR = ROOT / "quantclaw" / "dashboard" / "app"
PID_FILE = ROOT / "data" / ".quantclaw.pids"

BACKEND_PORT = 24120
DASHBOARD_PORT = 24121
SIDECAR_PORT = 24122

processes: list[subprocess.Popen] = []


def run(cmd: list[str], cwd: str | Path = ROOT, env: dict | None = None) -> int:
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, cwd=str(cwd), env=merged_env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARN: {' '.join(cmd[:3])}... exited {result.returncode}")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-3:]:
                print(f"    {line}")
    return result.returncode


def check_command(cmd: str) -> bool:
    try:
        subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _find_npm() -> str:
    """Find npm executable, handling Windows PATH issues."""
    for candidate in ["npm", "npm.cmd"]:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
            return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "npm"


def _find_node() -> str:
    """Find node executable."""
    for candidate in ["node", "node.exe"]:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
            return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "node"


def _save_pids(pids: list[dict]):
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(json.dumps(pids, indent=2))


def _load_pids() -> list[dict]:
    if PID_FILE.exists():
        try:
            return json.loads(PID_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _kill_pid(pid: int) -> bool:
    """Kill a process by PID. Returns True if killed."""
    if sys.platform == "win32":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True, text=True,
        )
        return result.returncode == 0
    else:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def _is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def install():
    print("\n> QuantClaw Setup\n")

    print("1/6  Checking prerequisites...")
    missing = []
    if not check_command("python"):
        missing.append("Python 3.12+ (python.org)")
    if not check_command(_find_node()):
        missing.append("Node.js 20+ (nodejs.org)")
    if not check_command(_find_npm()):
        missing.append("npm (comes with Node.js)")

    if missing:
        print("  Missing requirements:")
        for m in missing:
            print(f"    [FAIL] {m}")
        print("\n  Install the above and re-run this script.")
        sys.exit(1)

    py_ver = sys.version_info
    print(f"  [OK] Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    node_ver = subprocess.run([_find_node(), "--version"], capture_output=True, text=True).stdout.strip()
    print(f"  [OK] Node.js {node_ver}")

    print("\n2/6  Installing Python dependencies...")
    run([sys.executable, "-m", "pip", "install", "-e", ".", "-q"])
    run([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    print("  [OK] Python packages installed")

    print("\n3/6  Installing Node.js sidecar...")
    run([_find_npm(), "install"], cwd=SIDECAR_DIR)
    print("  [OK] Sidecar dependencies installed")

    print("\n4/6  Installing dashboard...")
    run([_find_npm(), "install"], cwd=DASHBOARD_DIR)
    print("  [OK] Dashboard dependencies installed")

    print("\n5/6  Initializing data directory...")
    (ROOT / "data").mkdir(exist_ok=True)
    print("  [OK] data/ directory ready")

    print("\n6/6  Checking Ollama...")
    if check_command("ollama"):
        print("  [OK] Ollama installed")
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if result.returncode == 0 and len(result.stdout.strip().split("\n")) > 1:
            print("  [OK] Models available")
        else:
            print("  [WARN] No models found. Run: ollama pull qwen3:8b")
    else:
        print("  [WARN] Ollama not installed (optional -- download from ollama.com)")

    print("\n[OK] Installation complete!\n")


def start():
    print("\n> Starting QuantClaw...\n")

    # Stop any existing services first
    stop(quiet=True)

    pids = []
    node = _find_node()
    npm = _find_npm()

    # Log files for service output
    log_dir = ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 1. Backend
    print(f"  Starting backend (port {BACKEND_PORT})...")
    backend_log = open(log_dir / "backend.log", "w")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "quantclaw.dashboard.api:app",
         "--host", "0.0.0.0", "--port", str(BACKEND_PORT), "--log-level", "info"],
        cwd=str(ROOT),
        stdout=backend_log,
        stderr=backend_log,
    )
    processes.append(backend)
    pids.append({"name": "backend", "pid": backend.pid, "port": BACKEND_PORT})
    time.sleep(2)
    if backend.poll() is not None:
        print("  [FAIL] Backend failed to start")
    else:
        print(f"  [OK] Backend running (pid {backend.pid})")

    # 2. Sidecar
    print(f"  Starting sidecar (port {SIDECAR_PORT})...")
    sidecar_log = open(log_dir / "sidecar.log", "w")
    sidecar = subprocess.Popen(
        [node, "server.js"],
        cwd=str(SIDECAR_DIR),
        stdout=sidecar_log,
        stderr=sidecar_log,
    )
    processes.append(sidecar)
    pids.append({"name": "sidecar", "pid": sidecar.pid, "port": SIDECAR_PORT})
    time.sleep(2)
    if sidecar.poll() is not None:
        print("  [FAIL] Sidecar failed to start")
    else:
        print(f"  [OK] Sidecar running (pid {sidecar.pid})")

    # 3. Dashboard (use node directly to get the real PID, not a shell wrapper)
    print(f"  Starting dashboard (port {DASHBOARD_PORT})...")
    node = _find_node()
    next_cli = str(DASHBOARD_DIR / "node_modules" / "next" / "dist" / "bin" / "next")
    dashboard = subprocess.Popen(
        [node, next_cli, "dev", "-p", str(DASHBOARD_PORT)],
        cwd=str(DASHBOARD_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    processes.append(dashboard)
    pids.append({"name": "dashboard", "pid": dashboard.pid, "port": DASHBOARD_PORT})

    dashboard_url = f"http://localhost:{DASHBOARD_PORT}"
    start_time = time.time()
    while time.time() - start_time < 20:
        if dashboard.poll() is not None:
            print("  [FAIL] Dashboard failed to start")
            break
        line = dashboard.stdout.readline().decode("utf-8", errors="replace") if dashboard.stdout else ""
        if "Local:" in line or "Ready" in line:
            if "Local:" in line:
                url = line.split("Local:")[1].strip()
                if url:
                    dashboard_url = url
            print(f"  [OK] Dashboard running at {dashboard_url} (pid {dashboard.pid})")
            break
        time.sleep(0.5)
    else:
        if _is_port_in_use(DASHBOARD_PORT):
            print(f"  [OK] Dashboard running at {dashboard_url}")
        else:
            print(f"  [WARN] Dashboard may still be starting at {dashboard_url}")

    # Save PIDs for stop command
    _save_pids(pids)

    print(f"""
  > QuantClaw is running!

  Dashboard:  {dashboard_url}
  Backend:    http://localhost:{BACKEND_PORT}
  Sidecar:    http://localhost:{SIDECAR_PORT}

  Run 'python start.py stop' to shut down.
  Press Ctrl+C to stop all services.
""")

    # Signal handler for Ctrl+C
    def cleanup(*_):
        print("\n\nShutting down...")
        stop(quiet=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Keep alive
    try:
        while True:
            for p in processes:
                if p.poll() is not None:
                    pass
            time.sleep(5)
    except KeyboardInterrupt:
        cleanup()


def stop(quiet: bool = False):
    """Stop all QuantClaw services."""
    pids = _load_pids()

    if not pids and not quiet:
        # Fallback: try to kill by port
        for name, port in [("backend", BACKEND_PORT), ("sidecar", SIDECAR_PORT), ("dashboard", DASHBOARD_PORT)]:
            if _is_port_in_use(port):
                if sys.platform == "win32":
                    result = subprocess.run(
                        f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :{port} ^| findstr LISTENING\') do @echo %a',
                        capture_output=True, text=True, shell=True,
                    )
                    pid_str = result.stdout.strip()
                    if pid_str:
                        for pid in pid_str.split("\n"):
                            pid = pid.strip()
                            if pid.isdigit():
                                _kill_pid(int(pid))
                                if not quiet:
                                    print(f"  Stopped {name} (pid {pid})")
        if not quiet:
            print("  All services stopped.")
        return

    killed = 0
    for entry in pids:
        name = entry.get("name", "?")
        pid = entry.get("pid", 0)
        if pid and _kill_pid(pid):
            if not quiet:
                print(f"  Stopped {name} (pid {pid})")
            killed += 1
        else:
            if not quiet:
                print(f"  {name} (pid {pid}) already stopped")

    # Also kill any process still on our ports (catches child processes)
    for name, port in [("backend", BACKEND_PORT), ("sidecar", SIDECAR_PORT), ("dashboard", DASHBOARD_PORT)]:
        if _is_port_in_use(port):
            if sys.platform == "win32":
                result = subprocess.run(
                    f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :{port} ^| findstr LISTENING\') do @echo %a',
                    capture_output=True, text=True, shell=True,
                )
                for pid in result.stdout.strip().split("\n"):
                    pid = pid.strip()
                    if pid.isdigit():
                        _kill_pid(int(pid))

    # Clean up PID file
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass

    if not quiet:
        print("\n  All services stopped.")


def status():
    """Show status of all services."""
    print("\n> QuantClaw Status\n")
    for name, port in [("Backend", BACKEND_PORT), ("Dashboard", DASHBOARD_PORT), ("Sidecar", SIDECAR_PORT)]:
        if _is_port_in_use(port):
            print(f"  {name:12s}  port {port}  [running]")
        else:
            print(f"  {name:12s}  port {port}  [stopped]")
    print()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "start":
        start()
    elif cmd == "stop":
        print("\n> Stopping QuantClaw...\n")
        stop()
    elif cmd == "status":
        status()
    elif cmd == "install":
        install()
    else:
        install()
        start()
