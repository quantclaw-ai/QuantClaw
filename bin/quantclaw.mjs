#!/usr/bin/env node
/**
 * QuantClaw CLI — single entry point for all operations.
 *
 * Usage:
 *   quantclaw start       Start all services (backend + sidecar + dashboard)
 *   quantclaw stop        Stop all services
 *   quantclaw status      Show service status
 */
import { spawn, spawnSync, execSync } from "child_process";
import { existsSync, readFileSync, writeFileSync, unlinkSync, realpathSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { createServer, createConnection } from "net";

// Resolve symlinks to find the actual package location (not the npm bin symlink)
const __filename_real = realpathSync(fileURLToPath(import.meta.url));
const __dirname = dirname(__filename_real);
const ROOT = join(__dirname, "..");
const SIDECAR = join(ROOT, "quantclaw", "sidecar");
const DASHBOARD = join(ROOT, "quantclaw", "dashboard", "app");
const PID_FILE = join(ROOT, "data", ".quantclaw.pids");
const LOG_DIR = join(ROOT, "data", "logs");

const BACKEND_PORT = 24120;
const DASHBOARD_PORT = 24121;
const SIDECAR_PORT = 24122;

const cmd = process.argv[2];

function findPython() {
  for (const py of ["python", "python3"]) {
    try {
      spawnSync(py, ["--version"], { stdio: "pipe", timeout: 5000 });
      return py;
    } catch {}
  }
  return null;
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const socket = createConnection({ port, host: "127.0.0.1" });
    socket.once("connect", () => { socket.destroy(); resolve(false); }); // in use
    socket.once("error", () => { socket.destroy(); resolve(true); });    // free
    socket.setTimeout(1000, () => { socket.destroy(); resolve(true); }); // timeout = free
  });
}

function killByPid(pid) {
  if (process.platform === "win32") {
    try {
      execSync(`taskkill /PID ${pid} /F`, { stdio: "ignore" });
      return true;
    } catch { return false; }
  } else {
    try {
      process.kill(pid);
      return true;
    } catch { return false; }
  }
}

function killByPort(port) {
  if (process.platform === "win32") {
    try {
      const result = execSync(
        `for /f "tokens=5" %a in ('netstat -ano ^| findstr :${port} ^| findstr LISTENING') do @echo %a`,
        { stdio: "pipe", shell: true }
      ).toString().trim();
      for (const pid of result.split("\n")) {
        const p = pid.trim();
        if (p && /^\d+$/.test(p)) {
          killByPid(parseInt(p));
        }
      }
    } catch {}
  }
}

async function startServices() {
  const py = findPython();
  if (!py) {
    console.error("Python not found. Install Python 3.12+ from python.org");
    process.exit(1);
  }

  // Stop any existing services first
  stopServices(true);

  // Ensure log directory exists
  mkdirSync(LOG_DIR, { recursive: true });

  const env = {
    ...process.env,
    PYTHONPATH: ROOT + (process.platform === "win32" ? ";" : ":") + (process.env.PYTHONPATH || ""),
    PYTHONIOENCODING: "utf-8",
  };

  console.log("\nStarting QuantClaw...\n");
  const pids = [];

  // 1. Backend
  const backend = spawn(py, [
    "-m", "uvicorn", "quantclaw.dashboard.api:app",
    "--host", "0.0.0.0", "--port", String(BACKEND_PORT), "--log-level", "info",
  ], {
    cwd: ROOT, stdio: "ignore", detached: true, env,
  });
  backend.unref();
  pids.push({ name: "backend", pid: backend.pid, port: BACKEND_PORT });
  console.log(`  [OK] Backend     -> http://localhost:${BACKEND_PORT}  (pid ${backend.pid})`);

  // 2. Sidecar
  const sidecar = spawn("node", ["server.js"], {
    cwd: SIDECAR, stdio: "ignore", detached: true,
  });
  sidecar.unref();
  pids.push({ name: "sidecar", pid: sidecar.pid, port: SIDECAR_PORT });
  console.log(`  [OK] Sidecar     -> http://localhost:${SIDECAR_PORT}  (pid ${sidecar.pid})`);

  // 3. Dashboard — use node directly to avoid shell wrapper orphan issues
  const nextCli = join(DASHBOARD, "node_modules", "next", "dist", "bin", "next");
  const dash = spawn("node", [nextCli, "dev", "-p", String(DASHBOARD_PORT)], {
    cwd: DASHBOARD, stdio: "ignore", detached: true,
  });
  dash.unref();
  pids.push({ name: "dashboard", pid: dash.pid, port: DASHBOARD_PORT });

  // Wait for Next.js to start
  await new Promise((r) => setTimeout(r, 4000));
  console.log(`  [OK] Dashboard   -> http://localhost:${DASHBOARD_PORT}  (pid ${dash.pid})`);

  // Save PIDs
  writeFileSync(PID_FILE, JSON.stringify(pids, null, 2));

  // Auto-open dashboard in default browser
  const url = `http://localhost:${DASHBOARD_PORT}`;
  const openCmd = process.platform === "win32" ? `start ${url}`
    : process.platform === "darwin" ? `open ${url}`
    : `xdg-open ${url}`;
  try { execSync(openCmd, { stdio: "ignore" }); } catch {}

  console.log(`
  QuantClaw is running!

  Dashboard:  ${url}
  Backend:    http://localhost:${BACKEND_PORT}
  Sidecar:    http://localhost:${SIDECAR_PORT}

  Run 'quantclaw stop' to shut down.
`);
}

function stopServices(quiet = false) {
  // Kill by PID file first
  if (existsSync(PID_FILE)) {
    const pids = JSON.parse(readFileSync(PID_FILE, "utf8"));
    for (const { name, pid } of pids) {
      if (killByPid(pid)) {
        if (!quiet) console.log(`  Stopped ${name} (pid ${pid})`);
      } else {
        if (!quiet) console.log(`  ${name} (pid ${pid}) already stopped`);
      }
    }
    try { unlinkSync(PID_FILE); } catch {}
  }

  // Also kill anything still on our ports (catches orphan child processes)
  for (const [name, port] of [["backend", BACKEND_PORT], ["sidecar", SIDECAR_PORT], ["dashboard", DASHBOARD_PORT]]) {
    killByPort(port);
  }

  if (!quiet) console.log("\n  All services stopped.");
}

async function showStatus() {
  console.log("\n  QuantClaw Status\n");
  const checks = [
    ["Backend", BACKEND_PORT],
    ["Dashboard", DASHBOARD_PORT],
    ["Sidecar", SIDECAR_PORT],
  ];
  for (const [name, port] of checks) {
    const free = await isPortFree(port);
    const running = !free;
    console.log(`  ${name.padEnd(12)}  port ${port}  ${running ? "[running]" : "[stopped]"}`);
  }
  console.log();
}

function showHelp() {
  console.log(`
  QuantClaw - Open-source quant trading superagent harness

  Usage:
    quantclaw start     Start all services (backend, sidecar, dashboard)
    quantclaw stop      Stop all services
    quantclaw status    Show running services
    quantclaw doctor    Health check (add --repair to auto-fix)
    quantclaw reset     Reset to fresh state (deletes config, data, cache)
    quantclaw help      Show this help

  Ports:
    Backend:    ${BACKEND_PORT}
    Dashboard:  ${DASHBOARD_PORT}
    Sidecar:    ${SIDECAR_PORT}

  First time? Just run 'quantclaw start' and open the URL in your browser.
`);
}

function resetAll() {
  import("fs").then(({ rmSync }) => {
    console.log("\n  Resetting QuantClaw to fresh state...\n");

    stopServices(true);

    const items = [
      { path: join(ROOT, "quantclaw.yaml"), label: "Config (quantclaw.yaml)", isDir: false },
      { path: join(ROOT, "data", "quantclaw.db"), label: "Database (data/quantclaw.db)", isDir: false },
      { path: join(ROOT, "data", "playbook.jsonl"), label: "Playbook (data/playbook.jsonl)", isDir: false },
      { path: join(ROOT, "data", "oauth_credentials.json"), label: "OAuth credentials", isDir: false },
      { path: join(ROOT, "data", "models"), label: "Trained models (data/models/)", isDir: true },
      { path: join(ROOT, "data", "strategies"), label: "Generated strategies (data/strategies/)", isDir: true },
      { path: PID_FILE, label: "PID file", isDir: false },
    ];

    for (const { path, label, isDir } of items) {
      if (!existsSync(path)) {
        console.log(`  [--] ${label} (not found)`);
        continue;
      }
      try {
        if (isDir) {
          rmSync(path, { recursive: true, force: true });
        } else {
          unlinkSync(path);
        }
        console.log(`  [OK] Deleted ${label}`);
      } catch (e) {
        console.log(`  [!!] Failed to delete ${label}: ${e.message}`);
      }
    }

    console.log(`
  QuantClaw has been reset to a fresh state.
  Run 'quantclaw start' to begin onboarding again.
`);
  });
}

switch (cmd) {
  case "start":
    await startServices();
    break;
  case "stop":
    console.log("\n  Stopping QuantClaw...\n");
    stopServices();
    break;
  case "status":
    await showStatus();
    break;
  case "doctor": {
    const py = findPython();
    if (!py) { console.error("Python not found."); process.exit(1); }
    const env = { ...process.env, PYTHONPATH: ROOT + (process.platform === "win32" ? ";" : ":") + (process.env.PYTHONPATH || "") };
    const args = ["-m", "quantclaw.doctor"];
    if (process.argv.includes("--repair") || process.argv.includes("--fix")) args.push("--repair");
    const result = spawnSync(py, args, { cwd: ROOT, stdio: "inherit", env });
    process.exit(result.status || 0);
    break;
  }
  case "reset":
    resetAll();
    break;
  case "help":
  case "--help":
  case "-h":
  case undefined:
    showHelp();
    break;
  default:
    console.log(`Unknown command: ${cmd}`);
    showHelp();
}
