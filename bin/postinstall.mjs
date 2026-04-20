#!/usr/bin/env node
/**
 * QuantClaw postinstall — installs Python deps + Node.js sidecar + dashboard deps.
 * Runs automatically after `npm install -g quantclaw`.
 */
import { execSync, spawnSync } from "child_process";
import { existsSync, mkdirSync, realpathSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

// Resolve symlinks to find the actual package location
let __dirname_resolved;
try {
  __dirname_resolved = dirname(realpathSync(fileURLToPath(import.meta.url)));
} catch {
  __dirname_resolved = dirname(fileURLToPath(import.meta.url));
}
const ROOT = join(__dirname_resolved, "..");
const SIDECAR = join(ROOT, "quantclaw", "sidecar");
const DASHBOARD = join(ROOT, "quantclaw", "dashboard", "app");

function log(msg) { console.log(`  ${msg}`); }
function ok(msg) { console.log(`  [OK] ${msg}`); }
function warn(msg) { console.log(`  [!] ${msg}`); }

function run(cmd, cwd = ROOT) {
  try {
    execSync(cmd, { cwd, stdio: "pipe", timeout: 120000 });
    return true;
  } catch { return false; }
}

function hasCommand(cmd) {
  try {
    spawnSync(cmd, ["--version"], { stdio: "pipe", timeout: 5000 });
    return true;
  } catch { return false; }
}

console.log("\nQuantClaw postinstall\n");

// 1. Check Python and install dependencies directly (no pip install of quantclaw itself)
if (hasCommand("python") || hasCommand("python3")) {
  const pyCmd = hasCommand("python") ? "python" : "python3";
  log("Installing Python dependencies...");
  const deps = "click pyyaml aiosqlite aiohttp croniter rich pandas numpy yfinance fastapi uvicorn websockets httpx";
  if (run(`${pyCmd} -m pip install ${deps} -q`)) {
    ok("Python packages");
  } else {
    warn("Python deps install failed — run manually: pip install " + deps);
  }
} else {
  warn("Python not found. Install Python 3.12+ from python.org");
}

// 2. Sidecar deps
if (existsSync(join(SIDECAR, "package.json"))) {
  log("Installing sidecar dependencies...");
  if (run("npm install --omit=dev", SIDECAR)) {
    ok("Node.js sidecar");
  } else {
    warn("Sidecar install failed");
  }
}

// 3. Dashboard deps
if (existsSync(join(DASHBOARD, "package.json"))) {
  log("Installing dashboard dependencies...");
  if (run("npm install", DASHBOARD)) {
    ok("Next.js dashboard");
  } else {
    warn("Dashboard install failed");
  }
}

// 4. Data dir
const dataDir = join(ROOT, "data");
if (!existsSync(dataDir)) {
  mkdirSync(dataDir, { recursive: true });
}

// 5. Check PATH — warn if npm global bin isn't accessible
const npmBin = execSync("npm config get prefix", { encoding: "utf8" }).trim();
const pathEnv = process.env.PATH || process.env.Path || "";
const npmBinInPath = pathEnv.split(process.platform === "win32" ? ";" : ":").some(
  (p) => p.replace(/\\/g, "/").toLowerCase() === npmBin.replace(/\\/g, "/").toLowerCase()
);

if (!npmBinInPath && process.platform === "win32") {
  console.log("");
  warn("npm global directory is not in your PATH.");
  log("");
  log("You can still start QuantClaw with:");
  log("  npx quantclaw start");
  log("");
  log("To fix permanently, add this to your PATH:");
  log(`  ${npmBin}`);
  log("");
  log("Quick fix (PowerShell as admin):");
  log(`  [Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";${npmBin}", "User")`);
  log("Then restart your terminal.");
} else {
  console.log("\n[OK] QuantClaw installed. Run: quantclaw start\n");
}
