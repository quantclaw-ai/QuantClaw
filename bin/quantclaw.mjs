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
import { existsSync, readFileSync, writeFileSync, unlinkSync, realpathSync, mkdirSync, openSync } from "fs";
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
// OAuth callback servers bound by the backend during sign-in flows.
// Their listening sockets live inside the backend process — tree-kill
// usually takes them down — but listing them here ensures the
// port-listener sweep catches a stray child that survived.
const OAUTH_CALLBACK_PORTS = [1455, 53692, 8085];
const ALL_OWNED_PORTS = [BACKEND_PORT, DASHBOARD_PORT, SIDECAR_PORT, ...OAUTH_CALLBACK_PORTS];
const LOCAL_HOST = "127.0.0.1";

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

function pidExists(pid) {
  if (!pid || isNaN(pid)) return false;
  if (process.platform === "win32") {
    try {
      const out = execSync(`tasklist /FI "PID eq ${pid}" /NH`, { stdio: "pipe" }).toString();
      // /NH suppresses the header; if the PID is gone, output is "INFO: No tasks..."
      return /^\s*\S/.test(out) && !out.includes("No tasks");
    } catch { return false; }
  } else {
    try { process.kill(pid, 0); return true; } catch { return false; }
  }
}

function killByPid(pid) {
  if (!pidExists(pid)) return false;
  if (process.platform === "win32") {
    try {
      // /T kills the entire process tree so uvicorn workers don't linger
      execSync(`taskkill /PID ${pid} /F /T`, { stdio: "ignore" });
      return true;
    } catch { return false; }
  } else {
    // Try graceful shutdown first; escalate to SIGKILL if still alive
    // after a short grace window. SIGTERM-only is a known stop-command
    // pitfall — any process ignoring it (or wedged in a syscall) keeps
    // the port bound and the next ``quantclaw start`` fails to bind.
    try { process.kill(pid, "SIGTERM"); } catch { return false; }
    const deadline = Date.now() + 2000;
    while (Date.now() < deadline) {
      if (!pidExists(pid)) return true;
      // Tiny synchronous wait — we're already in a stop-everything path
      // so blocking briefly is fine and simpler than async polling here.
      try { execSync("sleep 0.1", { stdio: "ignore" }); }
      catch { for (let i = 0; i < 1e7; i++) {} }
    }
    try { process.kill(pid, "SIGKILL"); } catch {}
    return !pidExists(pid);
  }
}

function pidsOnPort(port) {
  if (process.platform !== "win32") return [];
  try {
    const out = execSync("netstat -ano", { stdio: "pipe" }).toString();
    const pids = [];
    for (const line of out.split("\n")) {
      const parts = line.trim().split(/\s+/);
      // columns: Proto  Local  Foreign  State  PID
      if (parts.length >= 5 && parts[3] === "LISTENING") {
        const local = parts[1];
        if (local.endsWith(`:${port}`)) {
          const pid = parseInt(parts[4], 10);
          if (!isNaN(pid) && !pids.includes(pid)) pids.push(pid);
        }
      }
    }
    return pids;
  } catch { return []; }
}

function killByPort(port) {
  for (const pid of pidsOnPort(port)) {
    killByPid(pid);
  }
}

async function startServices() {
  const py = findPython();
  if (!py) {
    console.error("Python not found. Install Python 3.12+ from python.org");
    process.exit(1);
  }

  // Stop any existing services first
  await stopServices(true);

  // Ensure log directory exists
  mkdirSync(LOG_DIR, { recursive: true });

  const env = {
    ...process.env,
    PYTHONPATH: ROOT + (process.platform === "win32" ? ";" : ":") + (process.env.PYTHONPATH || ""),
    PYTHONIOENCODING: "utf-8",
  };

  console.log("\nStarting QuantClaw...\n");
  const pids = [];

  // Redirect each service's output to a log file instead of discarding it.
  // windowsHide suppresses the blank console windows Windows creates for
  // detached node/python processes.
  const spawnOpts = (logName, extraEnv = {}) => {
    const logPath = join(LOG_DIR, logName);
    const fd = openSync(logPath, "w");
    return {
      stdio: ["ignore", fd, fd],
      detached: true,
      windowsHide: true,
      env: { ...env, ...extraEnv },
    };
  };

  // 1. Backend
  const backend = spawn(py, [
    "-m", "uvicorn", "quantclaw.dashboard.api:app",
    "--host", LOCAL_HOST, "--port", String(BACKEND_PORT), "--log-level", "info",
  ], { cwd: ROOT, ...spawnOpts("backend.log") });
  backend.unref();
  pids.push({ name: "backend", pid: backend.pid, port: BACKEND_PORT });
  console.log(`  [OK] Backend     -> http://localhost:${BACKEND_PORT}  (pid ${backend.pid})`);

  // 2. Sidecar
  const sidecar = spawn("node", ["server.js"], {
    cwd: SIDECAR, ...spawnOpts("sidecar.log"),
  });
  sidecar.unref();
  pids.push({ name: "sidecar", pid: sidecar.pid, port: SIDECAR_PORT });
  console.log(`  [OK] Sidecar     -> http://localhost:${SIDECAR_PORT}  (pid ${sidecar.pid})`);

  // 3. Dashboard
  const nextCli = join(DASHBOARD, "node_modules", "next", "dist", "bin", "next");
  const dash = spawn("node", [nextCli, "dev", "-H", LOCAL_HOST, "-p", String(DASHBOARD_PORT)], {
    cwd: DASHBOARD, ...spawnOpts("dashboard.log"),
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

  Logs:       ${LOG_DIR}

  Run 'quantclaw stop' to shut down.
`);
}

async function isPortFreeAsync(port) {
  return await isPortFree(port);
}

function sleepSync(ms) {
  // execSync ``sleep`` works on POSIX; ``timeout`` on Windows. Fall back
  // to a busy spin so we never throw — this only runs during stop and a
  // brief stall is acceptable.
  try {
    if (process.platform === "win32") {
      execSync(`timeout /T 1 /NOBREAK > NUL`, { stdio: "ignore" });
    } else {
      execSync(`sleep ${ms / 1000}`, { stdio: "ignore" });
    }
  } catch {
    const end = Date.now() + ms;
    while (Date.now() < end) { /* spin */ }
  }
}

async function stopServices(quiet = false) {
  // 1. Kill by PID file. Guarded so a corrupted file doesn't abort the
  //    rest of the cleanup (we still have the port-listener sweep).
  let pidsFromFile = [];
  if (existsSync(PID_FILE)) {
    try {
      pidsFromFile = JSON.parse(readFileSync(PID_FILE, "utf8"));
      if (!Array.isArray(pidsFromFile)) pidsFromFile = [];
    } catch (e) {
      if (!quiet) console.log(`  PID file unreadable (${e.message}); falling back to port sweep`);
      pidsFromFile = [];
    }
  }
  for (const entry of pidsFromFile) {
    const { name, pid } = entry || {};
    if (typeof pid !== "number") continue;
    if (killByPid(pid)) {
      if (!quiet) console.log(`  Stopped ${name || "service"} (pid ${pid})`);
    } else {
      if (!quiet) console.log(`  ${name || "service"} (pid ${pid}) already stopped`);
    }
  }
  try { if (existsSync(PID_FILE)) unlinkSync(PID_FILE); } catch {}

  // 2. Sweep every port we own (services + OAuth callback ports) for
  //    orphan child processes — Next.js workers, leftover OAuth callback
  //    servers from a crashed sign-in, etc.
  for (const port of ALL_OWNED_PORTS) {
    killByPort(port);
  }

  // 3. Give the OS a moment to tear down sockets so the verification
  //    pass below doesn't race against still-closing connections.
  sleepSync(500);

  // 4. Verify ports are actually free; one retry if anything's still up.
  const stillBound = [];
  for (const port of ALL_OWNED_PORTS) {
    if (!(await isPortFreeAsync(port))) stillBound.push(port);
  }
  if (stillBound.length > 0) {
    for (const port of stillBound) killByPort(port);
    sleepSync(500);
  }

  const finalBound = [];
  for (const port of ALL_OWNED_PORTS) {
    if (!(await isPortFreeAsync(port))) finalBound.push(port);
  }

  if (finalBound.length > 0) {
    if (!quiet) {
      console.log(`\n  WARNING: ports still in use: ${finalBound.join(", ")}`);
      console.log(`  A process is holding them — try 'quantclaw status' to investigate.`);
    }
    return false;
  }

  if (!quiet) console.log("\n  All services stopped.");
  return true;
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

async function resetAll() {
  const { rmSync } = await import("fs");
  console.log("\n  Resetting QuantClaw to fresh state...\n");

  await stopServices(true);

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
}

switch (cmd) {
  case "start":
    await startServices();
    break;
  case "stop": {
    console.log("\n  Stopping QuantClaw...\n");
    const ok = await stopServices();
    // Non-zero exit so scripts/CI know the stop didn't fully succeed.
    if (!ok) process.exit(1);
    break;
  }
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
    await resetAll();
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
