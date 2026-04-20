"""FastAPI backend for QuantClaw web dashboard."""
from __future__ import annotations
import asyncio
import logging

# Configure root logger so our logs are visible in uvicorn
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from quantclaw.config.loader import load_config
from quantclaw.state.db import StateDB
from quantclaw.state.tasks import TaskStore, TaskStatus
from quantclaw.strategy.loader import list_templates
from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType
from quantclaw.plugins.manager import PluginManager

logger = logging.getLogger(__name__)

# Shared state
_db: StateDB | None = None
_bus = EventBus()
_pm = PluginManager()
_config = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db, _config
    # Load defaults, then merge the user's per-install overrides from
    # quantclaw.yaml (written at onboarding). Without this merge the
    # `llm_provider` and agent-model pinning written at onboarding would
    # never make it into the runtime config on subsequent launches.
    user_yaml = "quantclaw.yaml" if Path("quantclaw.yaml").exists() else None
    _config = load_config(user_yaml)

    # Back-fill agent model pinning for installs that onboarded before
    # per-agent pinning existed. If llm_provider is set but models dict
    # still points some agents at providers the user never authenticated
    # with, coerce them to the chosen provider's default model key.
    _pin_agents_to_llm_provider(_config)
    _db = await StateDB.create("data/quantclaw.db")
    _pm.discover()

    # ── Orchestration setup ──
    from quantclaw.orchestration.playbook import Playbook
    from quantclaw.orchestration.trust import TrustManager
    from quantclaw.orchestration.autonomy import AutonomyManager
    from quantclaw.orchestration.ooda import OODALoop
    from quantclaw.execution.dispatcher import Dispatcher
    from quantclaw.execution.pool import AgentPool
    from quantclaw.state.event_persister import EventPersister
    from quantclaw.state.plans import PlanStore
    from quantclaw.agents import ALL_AGENTS
    import json as _json

    playbook = Playbook("data/playbook.jsonl")
    trust = await TrustManager.from_playbook(playbook, bus=_bus)
    autonomy = await AutonomyManager.from_playbook(playbook)

    pool = AgentPool(bus=_bus, config=_config)
    for name, agent_cls in ALL_AGENTS.items():
        pool.register(name, agent_cls)

    cancel_event = asyncio.Event()
    dispatcher = Dispatcher(pool=pool, bus=_bus, cancel_event=cancel_event)

    ooda = OODALoop(
        bus=_bus, playbook=playbook, trust=trust, autonomy=autonomy,
        dispatcher=dispatcher, config=_config,
    )

    await ooda.restore_persistent_state()

    # Restore pending tasks from SQLite
    task_store = TaskStore(_db)
    pending = await task_store.list_by_status(TaskStatus.PENDING)
    for task in pending:
        try:
            task_data = _json.loads(task["command"])
            ooda.add_pending_task(task_data)
        except (ValueError, KeyError):
            pass

    # Event persistence (batched)
    persister = EventPersister(_db)
    _bus.subscribe("*", persister.handle_event)
    persister.start()

    # Store on app.state for endpoint access
    app.state.ooda = ooda
    app.state.trust = trust
    app.state.autonomy = autonomy
    app.state.playbook = playbook
    app.state.dispatcher = dispatcher
    app.state.cancel_event = cancel_event
    app.state.task_store = task_store
    app.state.plan_store = PlanStore(_db)
    app.state.persister = persister

    # Start OODA background task
    async def _ooda_background():
        while True:
            try:
                await ooda.run_continuous()
            except asyncio.CancelledError:
                break
            except Exception as e:
                await _bus.publish(Event(
                    type=EventType.CHAT_NARRATIVE,
                    payload={"message": f"Scheduler restarting after error: {e}",
                             "role": "scheduler"},
                    source_agent="scheduler",
                ))
                await asyncio.sleep(5)

    ooda_task = asyncio.create_task(_ooda_background())
    app.state.ooda_task = ooda_task

    yield

    # Shutdown
    ooda_task.cancel()
    try:
        await ooda_task
    except asyncio.CancelledError:
        pass
    await persister.stop()
    if _db:
        await _db.close()

app = FastAPI(
    title="QuantClaw Dashboard API",
    description="Backend for the QuantClaw quant trading dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:24121", "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ──
@app.get("/api/health")
def health():
    import platform
    import sys
    import os
    import time
    from datetime import datetime, timezone
    from quantclaw.agents import ALL_AGENTS

    # LLM availability check
    llm_available = any(
        _provider_runtime_status(provider)["available"]
        for provider in ["ollama", *PROVIDER_CONFIGS.keys()]
    )

    # Notification sinks status
    nc = _config.get("notifications", {})
    sinks = {}
    for channel in ["telegram", "discord", "slack"]:
        if channel in nc:
            conf = nc[channel]
            # Check if credentials are configured (not still env var placeholders)
            has_creds = all(not str(v).startswith("$") for v in conf.values())
            sinks[channel] = "connected" if has_creds else "not_configured"

    # Plugin status
    plugin_counts = {}
    for ptype in ["broker", "data", "engine", "asset"]:
        plugin_counts[ptype] = len(_pm.list_plugins(ptype))

    # Agent status — every agent is always available.
    daemon_agents = [name for name, cls in ALL_AGENTS.items() if cls.daemon]

    return {
        "status": "ok",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "python": sys.version,
            "platform": platform.platform(),
            "pid": os.getpid(),
        },
        "agents": {
            "total": len(ALL_AGENTS),
            "enabled": len(ALL_AGENTS),
            "daemon_running": daemon_agents,
        },
        "plugins": plugin_counts,
        "notifications": sinks,
        "websocket_clients": len(_ws_clients),
        "config_loaded": bool(_config),
        "database": "connected" if _db else "disconnected",
        "llm_available": llm_available,
    }


# ── Welcome / Onboarding ──
@app.get("/api/welcome")
def welcome_status():
    """Check if user has completed onboarding."""
    config_exists = Path("quantclaw.yaml").exists()
    return {"onboarded": config_exists}


# ── Onboarding Complete ──

# Default model id per provider, for mapping `llm_provider` -> agent routing.
# Keys of this map match what the LLMRouter expects as model keys (see the
# `providers:` block of config/default.yaml).
_PROVIDER_DEFAULT_MODEL_KEY: dict[str, str] = {
    "anthropic": "opus",
    "openai": "gpt",
    "ollama": "local",
    "google": "gemini",  # populated below if requested
}

_KNOWN_AGENTS = [
    "scheduler", "sentinel", "ingestor", "miner", "trainer", "validator",
    "researcher", "executor", "risk_monitor", "reporter",
    "compliance", "debugger", "planner",
]


def _pin_agents_to_llm_provider(config: dict) -> None:
    """Ensure every agent is routed to the user's chosen llm_provider.

    Mutates ``config["models"]`` in-place. If the user picked a single
    provider at onboarding, every agent should use that provider's default
    model key — otherwise agents silently route to providers the user may
    never have signed into. Per-agent overrides the user explicitly set
    (via Settings → Agents) are preserved.
    """
    llm_provider = config.get("llm_provider")
    if not llm_provider or llm_provider == "mixed":
        return
    target_key = _PROVIDER_DEFAULT_MODEL_KEY.get(llm_provider)
    if not target_key:
        return
    providers = config.get("providers", {}) or {}
    # If the chosen provider's model key isn't defined, bail out silently —
    # the user would get a clearer error later through the router.
    if target_key not in providers and target_key != "gemini":
        return
    if target_key == "gemini" and "gemini" not in providers:
        providers["gemini"] = {"provider": "google", "model": "gemini-2.5-flash"}
        config["providers"] = providers
    models = config.setdefault("models", {})
    for agent in _KNOWN_AGENTS:
        # Only pin agents that aren't already mapped to a provider the user
        # explicitly wants — here we detect "auto" by checking whether the
        # current mapping points at a provider that matches llm_provider.
        current_key = models.get(agent)
        current_provider = providers.get(current_key, {}).get("provider") if current_key else None
        if current_provider != llm_provider:
            models[agent] = target_key


@app.post("/api/onboarding/complete")
async def onboarding_complete(body: dict):
    """Save onboarding settings to quantclaw.yaml.

    Crucially, when a single ``llm_provider`` is chosen we also pin every
    agent's model to that provider. Otherwise default.yaml's per-agent
    mapping (which assumes Anthropic + OpenAI + Ollama all available) wins,
    and agents silently route to providers the user hasn't authenticated with.
    """
    import yaml

    llm_provider = body.get("llm_provider", "ollama")
    default_model_key = _PROVIDER_DEFAULT_MODEL_KEY.get(llm_provider, "local")

    config_data = {
        "llm_provider": llm_provider,
        "search_provider": body.get("search_provider", "duckduckgo"),
        "data_sources": body.get("data_sources", ["yfinance"]),
        "broker_type": body.get("broker_type", "paper"),
        "watchlist": body.get("watchlist", []),
        "language": body.get("language", "en"),
    }

    # Pin every known agent to the chosen provider. Users can still override
    # per-agent later in Settings → Agents.
    known_agents = [
        "scheduler", "sentinel", "ingestor", "miner", "trainer", "validator",
        "researcher", "executor", "risk_monitor", "reporter",
        "compliance", "debugger", "planner",
    ]
    config_data["models"] = {name: default_model_key for name in known_agents}

    # Ensure the provider mapping exists (for google/ollama users who may not
    # have an entry in their live config yet).
    if llm_provider == "google":
        config_data["providers"] = {
            "gemini": {"provider": "google", "model": "gemini-2.5-flash"},
        }

    # Write quantclaw.yaml — this marks onboarding as complete
    config_path = Path("quantclaw.yaml")
    config_path.write_text(yaml.dump(config_data, default_flow_style=False), encoding="utf-8")

    # Update runtime config
    _config.update(config_data)

    return {"status": "complete", "config_saved": True, "models_pinned_to": default_model_key}


# ── Full reset ──
@app.post("/api/reset")
async def reset_workings(request: Request) -> dict:
    """Wipe every agent's durable working state so a fresh campaign can start.

    CLEARED:
      * Playbook entries (campaigns, deployments, strategy results, allocator
        decisions, evaluator divergences, CEO preferences, agent performance,
        factor library, trust milestones, scaffolding experiments).
      * Playbook archives (``data/playbook.jsonl.archive.*.gz``).
      * State DB tables: tasks, events, plans, sessions.
      * Generated strategy files (``data/strategies/*.py``).
      * Trained models (``data/models/*``).
      * Rolling log files (``data/logs/``).
      * In-memory OODA state (active campaign, goal, iteration context).

    PRESERVED:
      * Ingested market data cache (``data/cache/``) — re-downloading all OHLCV
        would be wasteful; cache is immutable per date range anyway.
      * ``data/kroness.db`` — user's raw market data store.
      * ``data/oauth_credentials.json`` — so the user stays signed in.
      * ``quantclaw.yaml`` and the runtime config.
    """
    import shutil
    from quantclaw.orchestration.autonomy import AutonomyMode

    cleared: dict[str, int | str] = {}

    # 1a. Stop any in-flight cycle BEFORE wiping state. Without this, the
    # running cycle keeps emitting narratives (errors, verdicts, reports)
    # that arrive after the UI "clear" — making it look like reset failed.
    # Mirrors the /api/orchestration/stop pattern.
    try:
        cancel = request.app.state.cancel_event
        autonomy = request.app.state.autonomy
        cancel.set()
        # Flip out of autopilot so the next wake-up doesn't immediately
        # relaunch a cycle. User must explicitly re-enable autopilot.
        autonomy.set_mode(AutonomyMode.PLAN)
        await asyncio.sleep(0.3)  # Let cancellation propagate through dispatcher
        cancel.clear()
        cleared["in_flight"] = "cancelled"
        cleared["autonomy_mode"] = "plan"
    except Exception as exc:
        cleared["stop_error"] = str(exc)

    # 1b. In-memory OODA state
    try:
        ooda = request.app.state.ooda
        ooda.reset_campaign_state()
        cleared["ooda_state"] = "reset"
    except Exception as exc:
        cleared["ooda_state_error"] = str(exc)

    # 2. Playbook (live file + in-memory cache)
    try:
        playbook = request.app.state.playbook
        playbook_path = Path("data/playbook.jsonl")
        if playbook_path.exists():
            playbook_path.write_text("", encoding="utf-8")
        playbook.invalidate()
        cleared["playbook"] = "truncated"
    except Exception as exc:
        cleared["playbook_error"] = str(exc)

    # 3. Playbook archives
    archives = list(Path("data").glob("playbook.jsonl.archive.*.gz"))
    for archive in archives:
        try:
            archive.unlink()
        except OSError:
            pass
    cleared["archives_removed"] = len(archives)

    # 4. State DB tables
    try:
        if _db:
            for table in ("tasks", "events", "plans", "sessions"):
                try:
                    await _db.conn.execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            await _db.conn.commit()
        cleared["state_db"] = "tables_cleared"
    except Exception as exc:
        cleared["state_db_error"] = str(exc)

    # 5. Generated strategies
    strategies_dir = Path("data/strategies")
    strategy_count = 0
    if strategies_dir.exists():
        for path in strategies_dir.glob("*.py"):
            try:
                path.unlink()
                strategy_count += 1
            except OSError:
                pass
    cleared["strategies_removed"] = strategy_count

    # 6. Trained models
    models_dir = Path("data/models")
    model_count = 0
    if models_dir.exists():
        for path in models_dir.iterdir():
            try:
                if path.is_file():
                    path.unlink()
                    model_count += 1
                elif path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                    model_count += 1
            except OSError:
                pass
    cleared["models_removed"] = model_count

    # 7. Logs
    logs_dir = Path("data/logs")
    log_count = 0
    if logs_dir.exists():
        for path in logs_dir.iterdir():
            try:
                if path.is_file():
                    path.unlink()
                    log_count += 1
            except OSError:
                pass
    cleared["logs_removed"] = log_count

    # Broadcast a narrative so any listening UI knows state was wiped.
    try:
        await _bus.publish(Event(
            type=EventType.CHAT_NARRATIVE,
            payload={
                "message": "Reset complete. Cleared all agent history; ingested market data preserved.",
                "role": "scheduler",
            },
            source_agent="scheduler",
        ))
    except Exception:
        pass

    return {"status": "reset", "cleared": cleared}


# ── Strategies ──
@app.get("/api/strategies/templates")
def get_templates():
    return {"available": list_templates(), "locked": []}


# ── Agents ──
@app.get("/api/agents")
def get_agents():
    from quantclaw.agents import ALL_AGENTS
    agents = [
        {"name": name, "model": cls.model, "daemon": cls.daemon, "enabled": True}
        for name, cls in ALL_AGENTS.items()
    ]
    return {"agents": agents}


# ── Tasks ──
@app.get("/api/tasks")
async def get_tasks():
    if not _db:
        return {"tasks": []}
    store = TaskStore(_db)
    running = await store.list_by_status(TaskStatus.RUNNING)
    pending = await store.list_by_status(TaskStatus.PENDING)
    completed = await store.list_by_status(TaskStatus.COMPLETED)
    failed = await store.list_by_status(TaskStatus.FAILED)
    return {
        "running": running,
        "pending": pending,
        "completed": completed[:20],
        "failed": failed[:10],
    }

@app.get("/api/tasks/history")
async def get_task_history():
    if not _db:
        return {"tasks": []}
    store = TaskStore(_db)
    return {"tasks": await store.list_today()}


# ── Plugins ──
@app.get("/api/plugins")
def get_plugins():
    plugins = {}
    for ptype in ["broker", "data", "engine", "asset"]:
        plugins[ptype] = _pm.list_plugins(ptype)
    return {"plugins": plugins}


# ── Events (WebSocket) ──
_ws_clients: list[WebSocket] = []

@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.remove(websocket)

async def broadcast_event(event: Event):
    import json
    data = json.dumps({
        "type": str(event.type),
        "payload": event.payload,
        "source_agent": event.source_agent,
        "timestamp": event.timestamp.isoformat(),
    })
    for ws in _ws_clients[:]:
        try:
            await ws.send_text(data)
        except Exception:
            logger.exception("WebSocket broadcast failed")
            _ws_clients.remove(ws)

async def emit_floor_event(event_type: str, agent: str = "", targets: list[str] | None = None, progress: int = 0, message: str = ""):
    """Emit a trading floor event to all WebSocket clients."""
    import json
    from datetime import datetime, timezone
    data = json.dumps({
        "type": event_type,
        "agent": agent,
        "targets": targets or [],
        "progress": progress,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    for ws in _ws_clients[:]:
        try:
            await ws.send_text(data)
        except Exception:
            logger.exception("WebSocket broadcast failed")
            _ws_clients.remove(ws)

# Subscribe event bus to broadcast
_bus.subscribe("*", broadcast_event)


# ── Events (REST) ──
@app.get("/api/events")
def get_events(limit: int = 50, offset: int = 0, agent: str = "",
               type: str = "", since: str = ""):
    """Get events with optional filters."""
    import fnmatch as _fnmatch
    recent = _bus.recent(500)

    filtered = recent
    if agent:
        filtered = [e for e in filtered if e.source_agent == agent]
    if type:
        filtered = [e for e in filtered if _fnmatch.fnmatch(str(e.type), type)]
    if since:
        filtered = [e for e in filtered if e.timestamp.isoformat() >= since]

    total = len(filtered)
    filtered = filtered[offset:offset + limit]

    return {"events": [{"type": str(e.type), "payload": e.payload,
                        "source_agent": e.source_agent,
                        "timestamp": e.timestamp.isoformat()} for e in filtered],
            "total": total}


# ── Strategy Generation ──
@app.post("/api/strategies/generate")
async def generate_strategy(body: dict):
    """Generate a strategy from natural language."""
    from quantclaw.strategy.generator import StrategyGenerator
    from quantclaw.execution.router import LLMRouter
    description = body.get("description", "")
    if not description:
        return {"error": "description is required"}
    router = LLMRouter(_config)
    generator = StrategyGenerator(router)
    try:
        code = await generator.generate(description, save_path=body.get("save_path"))
        return {"code": code, "status": "generated"}
    except Exception as e:
        return {"error": str(e), "status": "failed"}


# ── Observability ──
_observability = None

@app.get("/api/observability")
def get_observability():
    """Get agent run observability data."""
    from quantclaw.state.observability import ObservabilityStore
    global _observability
    if _observability is None:
        _observability = ObservabilityStore()
    active = [r.to_dict() for r in _observability.get_active()]
    recent = [r.to_dict() for r in _observability.get_recent()]
    return {"active_runs": active, "recent_runs": recent}


# ── Plans ──
@app.post("/api/plans/create")
async def create_plan(body: dict):
    """Create a plan from natural language."""
    from quantclaw.execution.planner import Planner
    from quantclaw.execution.router import LLMRouter
    request = body.get("request", "")
    if not request:
        return {"error": "request is required"}
    router = LLMRouter(_config)
    planner = Planner(router)
    try:
        plan = await planner.create_plan(request)
        return plan.to_dict()
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/plans/{plan_id}/approve")
async def approve_plan(plan_id: str, request: Request):
    """Approve all steps in a plan."""
    plan_store = getattr(request.app.state, "plan_store", None)
    if plan_store:
        plan = await plan_store.get(plan_id)
        if plan:
            plan.approve_all()
            await plan_store.save(plan)
            return {"status": "approved", "plan_id": plan_id}
    return {"status": "approved", "plan_id": plan_id}

@app.post("/api/plans/{plan_id}/steps/{step_id}/skip")
async def skip_step(plan_id: str, step_id: int, request: Request):
    """Skip a specific step."""
    plan_store = getattr(request.app.state, "plan_store", None)
    if plan_store:
        plan = await plan_store.get(plan_id)
        if plan:
            plan.skip_step(step_id)
            await plan_store.save(plan)
            return {"status": "skipped", "plan_id": plan_id, "step_id": step_id}
    return {"status": "skipped", "plan_id": plan_id, "step_id": step_id}


# ── Strategy Memory ──
@app.get("/api/memory/stats")
async def get_memory_stats():
    """Get strategy memory statistics."""
    from quantclaw.state.memory import StrategyMemory
    if not _db:
        return {"total_backtests": 0, "avg_sharpe": 0, "best_sharpe": 0}
    memory = StrategyMemory(_db)
    return await memory.get_stats()

@app.get("/api/memory/suggestions/{strategy_type}")
async def get_suggestions(strategy_type: str):
    """Get suggestions for a strategy type based on past runs."""
    from quantclaw.state.memory import StrategyMemory
    if not _db:
        return {"strategy_type": strategy_type, "total_past_runs": 0, "best_configurations": [], "anti_patterns": []}
    memory = StrategyMemory(_db)
    return await memory.get_suggestions(strategy_type)

@app.get("/api/memory/anti-patterns")
async def get_anti_patterns():
    """Get strategies that have consistently failed."""
    from quantclaw.state.memory import StrategyMemory
    if not _db:
        return {"anti_patterns": []}
    memory = StrategyMemory(_db)
    patterns = await memory.get_anti_patterns()
    return {"anti_patterns": patterns}


# ── Audit Trail ──
@app.get("/api/audit/{backtest_id}")
def get_audit(backtest_id: str):
    """Get backtest audit trail."""
    return {"backtest_id": backtest_id, "status": "not_found", "message": "Audit trails are recorded during backtests and stored in results metadata."}


# ── Tools ──
@app.get("/api/tools")
def get_tools():
    """List all purpose-built domain tools per agent."""
    from quantclaw.agents.tools import create_default_registry
    registry = create_default_registry()
    tools = {}
    for agent, tool_names in registry.list_all().items():
        agent_tools = registry.get_tools(agent)
        tools[agent] = [{"name": t.name, "description": t.description} for t in agent_tools]
    return {"tools": tools}


# ── Portfolio (placeholder) ──
@app.get("/api/portfolio")
def get_portfolio():
    return {
        "equity": 100000,
        "cash": 100000,
        "positions": [],
        "daily_pnl": 0,
        "total_return": 0,
    }


# ── Risk (placeholder) ──
@app.get("/api/risk")
def get_risk():
    risk_config = _config.get("risk", {})
    return {
        "max_drawdown": risk_config.get("max_drawdown", -0.10),
        "max_position_pct": risk_config.get("max_position_pct", 0.05),
        "current_drawdown": 0,
        "current_exposure": 0,
    }


# ── OAuth ──
from quantclaw.dashboard.oauth import (
    start_oauth_flow, exchange_token, get_auth_status,
    disconnect_provider, get_access_token, refresh_token as refresh_oauth_token,
)

@app.post("/api/oauth/start/{provider_id}")
def oauth_start(provider_id: str):
    """Start OAuth flow — opens browser for authentication."""
    return start_oauth_flow(provider_id)

@app.get("/api/oauth/status/{provider_id}")
def oauth_status(provider_id: str):
    """Poll for OAuth flow completion."""
    return get_auth_status(provider_id)

@app.post("/api/oauth/exchange/{provider_id}")
async def oauth_exchange(provider_id: str):
    """Exchange authorization code for access token."""
    return await exchange_token(provider_id)

@app.post("/api/oauth/disconnect/{provider_id}")
def oauth_disconnect(provider_id: str):
    """Remove stored OAuth credentials."""
    return disconnect_provider(provider_id)


# ── Orchestration ──
@app.get("/api/orchestration/status")
def orchestration_status(request: Request):
    ooda = request.app.state.ooda
    autonomy = request.app.state.autonomy
    trust = request.app.state.trust
    return {
        "autonomy_mode": autonomy.mode.value,
        "trust_level": trust.level.name,
        "trust_level_id": int(trust.level),
        "ooda_phase": ooda.phase.value,
        "trust_metrics": trust.get_metrics(),
    }

@app.post("/api/orchestration/mode")
def set_orchestration_mode(body: dict, request: Request):
    from quantclaw.orchestration.autonomy import AutonomyMode
    autonomy = request.app.state.autonomy
    mode_str = body.get("mode", "plan")
    try:
        mode = AutonomyMode(mode_str)
    except ValueError:
        return {"error": f"Invalid mode: {mode_str}"}
    autonomy.set_mode(mode)
    return {"mode": autonomy.mode.value}

@app.get("/api/orchestration/playbook/recent")
async def get_playbook_recent(request: Request):
    playbook = request.app.state.playbook
    entries = await playbook.recent(20)
    return {
        "entries": [
            {
                "type": e.entry_type.value,
                "content": e.content,
                "tags": e.tags,
                "timestamp": e.timestamp,
            }
            for e in entries
        ]
    }

@app.get("/api/orchestration/trust")
def get_trust(request: Request):
    trust = request.app.state.trust
    return {
        "level": trust.level.name,
        "level_id": int(trust.level),
        "metrics": trust.get_metrics(),
        "can_paper_trade": trust.can_paper_trade(),
        "can_live_trade": trust.can_live_trade(),
    }

@app.post("/api/orchestration/trust/upgrade")
async def upgrade_trust(body: dict, request: Request):
    from quantclaw.orchestration.trust import TrustLevel
    trust = request.app.state.trust
    target = body.get("level", 1)
    try:
        await trust.upgrade(TrustLevel(target))
        return {"level": trust.level.name, "level_id": int(trust.level)}
    except ValueError as e:
        return {"error": str(e)}

@app.post("/api/orchestration/kill")
async def kill_switch(request: Request):
    """Emergency halt: stop all trading and pending tasks."""
    from quantclaw.orchestration.autonomy import AutonomyMode
    autonomy = request.app.state.autonomy
    autonomy.set_mode(AutonomyMode.PLAN)
    await _bus.publish(Event(
        type=EventType.ORCHESTRATION_BROADCAST,
        payload={"action": "kill_switch", "message": "CEO activated kill switch"},
        source_agent="scheduler",
    ))
    return {"status": "halted", "mode": autonomy.mode.value}

@app.post("/api/orchestration/goal")
async def set_goal(body: dict, request: Request):
    ooda = request.app.state.ooda
    goal = body.get("goal", "")
    await ooda.set_goal_persistent(goal)
    return {"goal": goal, "status": "set"}

@app.post("/api/orchestration/stop")
async def stop_workflow(request: Request):
    """Stop button -- cancel current workflow."""
    from quantclaw.orchestration.autonomy import AutonomyMode
    cancel = request.app.state.cancel_event
    cancel.set()
    request.app.state.autonomy.set_mode(AutonomyMode.PLAN)
    await _bus.publish(Event(
        type=EventType.CHAT_NARRATIVE,
        payload={"message": "Workflow stopped.", "role": "scheduler"},
        source_agent="scheduler",
    ))
    await asyncio.sleep(0.2)  # Let cancellation propagate
    cancel.clear()
    return {"status": "stopped"}


# ── Chat (Ollama / LLM routing) ──
AGENT_SYSTEM_PROMPTS = {
    "scheduler": "You are the Scheduler agent for QuantClaw, a quant trading platform. You coordinate tasks between agents and help users plan their trading workflows.",
    "validator": "You are the Validator agent for QuantClaw. You replay strategies in the sandbox and validate them on held-out data to flag overfit candidates.",
    "risk_monitor": "You are the Risk Monitor agent for QuantClaw. You analyze portfolio risk, drawdowns, exposure, and Value at Risk.",
    "ingestor": "You are the Ingestor agent for QuantClaw. You pull market data, scan for trading signals, and process data feeds.",
    "reporter": "You are the Reporter agent for QuantClaw. You summarize portfolio performance, positions, and P&L.",
    "executor": "You are the Executor agent for QuantClaw. You handle trade execution, order management, and broker integration.",
    "researcher": "You are the Researcher agent for QuantClaw. You analyze markets, academic papers, and factor performance.",
    "trainer": "You are the Trainer agent for QuantClaw. You help users train ML models for trading signal generation.",
    "debugger": "You are the Debugger agent for QuantClaw. You diagnose system issues, trace errors, and run diagnostics.",
    "compliance": "You are the Compliance agent for QuantClaw. You check trading activity against regulatory rules.",
}

AGENT_KEYWORDS = {
    "validator": ["backtest", "validate", "回测", "校验", "バックテスト", "バリデート", "test strategy"],
    "risk_monitor": ["risk", "drawdown", "exposure", "风险", "风控", "リスク"],
    "ingestor": ["signal", "ingest", "data", "信号", "采集", "シグナル"],
    "reporter": ["portfolio", "position", "holdings", "投资组合", "持仓", "ポートフォリオ"],
    "executor": ["execute", "buy", "sell", "trade", "买", "卖", "order"],
    "researcher": ["research", "analyze", "find", "研究", "分析", "調査"],
    "trainer": ["train", "model", "ml", "训练", "学習", "モデル"],
    "debugger": ["debug", "error", "fix", "调试", "デバッグ"],
    "compliance": ["compliance", "regulation", "合规"],
}

def _route_to_agent(message: str) -> str:
    lower = message.lower()
    for agent, keywords in AGENT_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return agent
    return "scheduler"

# Provider API base URLs and configurations
PROVIDER_CONFIGS = {
    "openai": {"base_url": "https://api.openai.com/v1", "env_key": "OPENAI_API_KEY"},
    "anthropic": {"base_url": "https://api.anthropic.com", "env_key": "ANTHROPIC_API_KEY", "is_anthropic": True},
    "google": {"base_url": "https://generativelanguage.googleapis.com/v1beta", "env_key": "GEMINI_API_KEY", "is_google": True},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "env_key": "DEEPSEEK_API_KEY"},
    "xai": {"base_url": "https://api.x.ai/v1", "env_key": "XAI_API_KEY"},
    "mistral": {"base_url": "https://api.mistral.ai/v1", "env_key": "MISTRAL_API_KEY"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "env_key": "GROQ_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "env_key": "OPENROUTER_API_KEY"},
    "together": {"base_url": "https://api.together.xyz/v1", "env_key": "TOGETHER_API_KEY"},
}

def _validate_api_key(provider: str, key: str) -> bool:
    """Basic format validation for API keys."""
    if not key:
        return False
    prefixes = {
        "anthropic": "sk-ant-",
        "openai": "sk-",
        "google": "AI",
    }
    expected = prefixes.get(provider, "")
    if expected and not key.startswith(expected):
        import logging
        logging.getLogger(__name__).warning(
            "Client-provided API key for %s has unexpected format", provider
        )
    return True  # Still allow it — warning only, not a hard block


def _get_api_key(provider: str) -> str | None:
    """Get API key from OAuth credentials or environment."""
    import os
    # Check OAuth tokens first
    token = get_access_token(provider)
    if token:
        return token
    # Check environment variable
    config = PROVIDER_CONFIGS.get(provider, {})
    env_key = config.get("env_key", "")
    if env_key:
        val = os.environ.get(env_key)
        if val:
            return val
    return None


def _provider_runtime_status(provider: str) -> dict:
    """Report whether a provider is usable from server-side credentials."""
    import os
    import socket

    provider = provider.lower()

    if provider == "ollama":
        try:
            s = socket.create_connection(("127.0.0.1", 11434), timeout=1)
            s.close()
            return {"available": True, "source": "ollama"}
        except (ConnectionRefusedError, OSError, TimeoutError):
            return {"available": False, "source": None}

    oauth_token = get_access_token(provider)
    if oauth_token:
        return {"available": True, "source": "oauth"}

    config = PROVIDER_CONFIGS.get(provider, {})
    env_key = config.get("env_key", "")
    if env_key and os.environ.get(env_key):
        return {"available": True, "source": "env"}

    return {
        "available": False,
        "source": None,
        "reason": "unknown_provider" if provider not in PROVIDER_CONFIGS else "not_configured",
    }


@app.get("/api/llm/provider-status/{provider}")
def llm_provider_status(provider: str):
    status = _provider_runtime_status(provider)
    return {"provider": provider, **status}


@app.post("/api/chat")
async def chat(body: dict, request: Request):
    """Route a message to the appropriate agent via the selected provider."""
    import httpx, json
    import asyncio as _asyncio

    message = body.get("message", "")
    lang = body.get("lang", "en")
    history = body.get("history", [])
    model = body.get("model", "")
    provider = body.get("provider", "ollama")
    api_key_from_client = body.get("api_key", "")  # Frontend can pass stored key
    query_only = body.get("query_only", False)  # Simple question, answer directly with LLM

    if api_key_from_client:
        _validate_api_key(provider, api_key_from_client)

    if not message:
        return {"error": "message is required"}

    # Route to agent — only honor explicit @mentions, not ambient "Talking to" state
    explicit_agent = body.get("agent", "")
    is_mention = body.get("mention", False)
    if not is_mention:
        explicit_agent = ""  # Ignore ambient agent — always route through OODA

    # ── Check if message is conversational (not a goal/task) ──
    # Short greetings and simple chat should get a direct response, not orchestration
    _CONVERSATIONAL_PATTERNS = [
        "hi", "hello", "hey", "sup", "yo", "thanks", "thank you", "ok", "okay",
        "yes", "no", "sure", "cool", "nice", "great", "good", "bye", "goodbye",
        "what are you", "who are you", "how are you", "what can you do",
        "what's your", "whats your", "whats our", "what's our",
        "tell me about", "explain", "describe",
        "help", "help me", "can you", "do you",
        "model", "version", "status", "available",
        "你好", "谢谢", "こんにちは",
    ]
    _is_conversational = (
        len(message.split()) <= 8
        and any(message.lower().strip().startswith(p) for p in _CONVERSATIONAL_PATTERNS)
    ) or query_only

    # ── Orchestration path: route through OODA unless explicitly @agent or conversational ──
    if not _is_conversational and (not explicit_agent or explicit_agent == "scheduler" or explicit_agent not in AGENT_SYSTEM_PROMPTS):
        ooda = getattr(request.app.state, "ooda", None)
        if ooda is not None:
            cancel = request.app.state.cancel_event

            # Cancel-and-replace if mid-cycle
            if ooda.phase != "sleep":
                cancel.set()
                await _asyncio.sleep(0.2)
                cancel.clear()
                await emit_floor_event("agent.task.started", agent="scheduler",
                                       message="Switching to new request...")

            # Set goal and trigger cycle
            await ooda.set_goal_persistent(message)
            chat_history = history[-10:] if history else []

            # Apply user's model/provider selection + API key
            # agent_models: per-agent assignments from Agents tab (localStorage)
            # model/provider: user's chat model selection
            # api_key: from localStorage or OAuth
            user_api_key = api_key_from_client or _get_api_key(provider) or ""
            import logging as _logging
            _logging.getLogger(__name__).info(
                "OODA: provider=%s, model=%s, api_key=%s",
                provider, model, f"{user_api_key[:8]}..." if user_api_key else "NONE"
            )
            agent_models = body.get("agent_models", {})
            if agent_models:
                ooda.set_model_overrides(agent_models, provider, api_key=user_api_key)
            elif model and provider:
                ooda.set_model_overrides({}, provider, default_model=model, api_key=user_api_key)
            elif user_api_key:
                ooda.set_model_overrides({}, provider, api_key=user_api_key)

            # Run cycle in background (only if not already running)
            if not ooda._cycle_lock.locked():
                async def _run_ooda_cycle():
                    try:
                        await ooda.run_cycle(chat_history=chat_history, auto_approve=True)
                    except Exception as e:
                        await _bus.publish(Event(
                            type=EventType.CHAT_NARRATIVE,
                            payload={"message": f"Error: {e}", "role": "scheduler"},
                            source_agent="scheduler",
                        ))
                    finally:
                        ooda._wake_event.clear()  # Prevent run_continuous from double-firing

                _asyncio.create_task(_run_ooda_cycle())

            await emit_floor_event("agent.task.started", agent="scheduler",
                                   message=f"Planning: {message[:50]}...")

            return {"status": "orchestrating", "agent": "scheduler"}

    # ── Direct agent chat path (existing behavior) ──
    agent = explicit_agent if explicit_agent in AGENT_SYSTEM_PROMPTS else _route_to_agent(message)

    # Use a general-purpose prompt for simple queries, agent-specific for others
    if query_only:
        system_prompt = (
            "You are a helpful AI assistant for QuantClaw, a quantitative trading platform. "
            "Answer user questions concisely and naturally. Be informative, friendly, and direct. "
            "If asked about features or capabilities, describe what QuantClaw can do. "
            "Keep responses to 2-3 sentences unless more detail is needed."
        )
    else:
        system_prompt = AGENT_SYSTEM_PROMPTS.get(agent, AGENT_SYSTEM_PROMPTS["scheduler"])

    # Emit task started event
    await emit_floor_event("agent.task.started", agent=agent, message=f"Processing: {message[:50]}...")

    lang_instructions = {
        "zh": "\n\nIMPORTANT: Always respond in 简体中文 (Simplified Chinese).",
        "ja": "\n\nIMPORTANT: Always respond in 日本語 (Japanese).",
    }
    system_prompt += lang_instructions.get(lang, "")

    # Build message list (OpenAI-compatible format)
    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-10:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    # ── Ollama (local) ──
    if provider == "ollama":
        ollama_url = "http://localhost:11434"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                tags_resp = await client.get(f"{ollama_url}/api/tags")
                available = [m["name"] for m in tags_resp.json().get("models", [])]
        except Exception:
            return {"error": "Ollama is not running.", "agent": agent}

        if not available:
            return {"error": "No Ollama models installed.", "agent": agent}

        use_model = model if model in available else available[0]
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{ollama_url}/api/chat",
                    json={"model": use_model, "messages": messages, "stream": False},
                )
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                await emit_floor_event("agent.task.completed", agent=agent, message=content[:100])
                return {"response": content, "agent": agent, "model": use_model, "provider": "ollama"}
        except Exception as e:
            await emit_floor_event("agent.task.failed", agent=agent, message=str(e)[:100])
            return {"error": str(e), "agent": agent}

    # ── Google Gemini (OAuth or API key) ──
    if provider == "google":
        oauth_token = get_access_token("google")
        api_key = api_key_from_client  # Only use explicitly provided API key, not OAuth
        if not oauth_token and not api_key:
            return {"error": "Google Gemini not authenticated. Sign in via OAuth or add an API key in Settings.", "agent": agent}

        use_model = model or "gemini-2.5-flash"
        gemini_contents = []
        for m in messages:
            if m["role"] == "system":
                continue
            role = "model" if m["role"] == "assistant" else "user"
            gemini_contents.append({"role": role, "parts": [{"text": m["content"]}]})

        gemini_body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": gemini_contents,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                if oauth_token and not api_key:
                    # OAuth: use Generative Language API with Bearer token
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent",
                        headers={
                            "Authorization": f"Bearer {oauth_token}",
                            "Content-Type": "application/json",
                            "x-goog-user-project": "",
                        },
                        json=gemini_body,
                    )
                    # If scope/permission error, try refreshing token
                    if resp.status_code in (401, 403):
                        new_token = await refresh_oauth_token("google")
                        if new_token:
                            resp = await client.post(
                                f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent",
                                headers={"Authorization": f"Bearer {new_token}", "Content-Type": "application/json"},
                                json=gemini_body,
                            )
                        if resp.status_code != 200:
                            return {"error": f"Google Gemini error {resp.status_code}: {resp.text[:200]}", "agent": agent}
                else:
                    # API key in URL
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={api_key}",
                        json=gemini_body,
                    )
                data = resp.json()
                if resp.status_code != 200:
                    return {"error": data.get("error", {}).get("message", f"Gemini error {resp.status_code}"), "agent": agent}
                content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return {"response": content, "agent": agent, "model": use_model, "provider": "google"}
        except Exception as e:
            return {"error": str(e), "agent": agent}

    SIDECAR_URL = "http://localhost:24122"

    # ── OpenAI (OAuth via sidecar or API key) ──
    if provider == "openai":
        import os
        oauth_token = get_access_token("openai")
        api_key = api_key_from_client or os.environ.get("OPENAI_API_KEY")
        use_model = model or "gpt-5.4"

        if oauth_token:
            # Proxy to Node.js sidecar for OAuth
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        f"{SIDECAR_URL}/chat/openai",
                        json={"model": use_model, "messages": messages, "system_prompt": system_prompt, "access_token": oauth_token},
                    )
                    data = resp.json()
                    if data.get("error"):
                        # Try refreshing token
                        if "401" in str(data["error"]) or "unauthorized" in str(data["error"]).lower():
                            new_token = await refresh_oauth_token("openai")
                            if new_token:
                                resp2 = await client.post(
                                    f"{SIDECAR_URL}/chat/openai",
                                    json={"model": use_model, "messages": messages, "system_prompt": system_prompt, "access_token": new_token},
                                )
                                data = resp2.json()
                        if data.get("error"):
                            return {"error": data["error"], "agent": agent}
                    return {"response": data.get("response", ""), "agent": agent, "model": use_model, "provider": data.get("provider", "openai-oauth")}
            except httpx.ConnectError:
                return {"error": "Node.js sidecar not running. Start it with: node quantclaw/sidecar/server.js", "agent": agent}
            except Exception as e:
                return {"error": str(e), "agent": agent}

        elif api_key:
            # API key path: standard api.openai.com
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"model": use_model, "messages": messages, "max_tokens": 4096},
                    )
                    data = resp.json()
                    if resp.status_code != 200:
                        err = data.get("error", {})
                        err_msg = err.get("message", "") if isinstance(err, dict) else str(err)
                        return {"error": err_msg or f"OpenAI API error {resp.status_code}", "agent": agent}
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return {"response": content, "agent": agent, "model": use_model, "provider": "openai-api"}
            except Exception as e:
                return {"error": str(e), "agent": agent}
        else:
            return {"error": "OpenAI not authenticated. Sign in via OAuth or add an API key in Settings.", "agent": agent}

    # ── Anthropic (OAuth via sidecar or API key) ──
    if provider == "anthropic":
        oauth_token = get_access_token("anthropic")
        api_key = api_key_from_client
        use_model = model or "claude-sonnet-4-6"
        anthropic_messages = [m for m in messages if m["role"] != "system"]

        if not oauth_token and not api_key:
            return {"error": "Anthropic not authenticated. Sign in via OAuth or add an API key in Settings.", "agent": agent}

        if oauth_token and not api_key:
            # Proxy to sidecar for OAuth
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        f"{SIDECAR_URL}/chat/anthropic",
                        json={"model": use_model, "messages": messages, "system_prompt": system_prompt, "access_token": oauth_token},
                    )
                    data = resp.json()
                    if data.get("error"):
                        if "401" in str(data["error"]) or "unauthorized" in str(data["error"]).lower():
                            new_token = await refresh_oauth_token("anthropic")
                            if new_token:
                                resp2 = await client.post(
                                    f"{SIDECAR_URL}/chat/anthropic",
                                    json={"model": use_model, "messages": messages, "system_prompt": system_prompt, "access_token": new_token},
                                )
                                data = resp2.json()
                        if data.get("error"):
                            return {"error": data["error"], "agent": agent}
                    return {"response": data.get("response", ""), "agent": agent, "model": use_model, "provider": data.get("provider", "anthropic-oauth")}
            except httpx.ConnectError:
                return {"error": "Node.js sidecar not running. Start it with: node quantclaw/sidecar/server.js", "agent": agent}
            except Exception as e:
                return {"error": str(e), "agent": agent}
        else:
            # API key path
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                        json={"model": use_model, "max_tokens": 4096, "system": system_prompt, "messages": anthropic_messages},
                    )
                    data = resp.json()
                    if resp.status_code != 200:
                        return {"error": data.get("error", {}).get("message", f"Anthropic error {resp.status_code}"), "agent": agent}
                    content = "".join(b.get("text", "") for b in data.get("content", []))
                    return {"response": content, "agent": agent, "model": use_model, "provider": "anthropic-api"}
            except Exception as e:
                return {"error": str(e), "agent": agent}

    # ── All other OpenAI-compatible providers (DeepSeek, xAI, Mistral, Groq, OpenRouter, Together) ──
    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        return {"error": f"Unknown provider: {provider}", "agent": agent}

    api_key = api_key_from_client or _get_api_key(provider)
    if not api_key:
        return {"error": f"{provider} not authenticated. Sign in via OAuth or add an API key in Settings.", "agent": agent}

    base_url = config["base_url"]
    use_model = model or "gpt-5.4"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://quantclaw.com"
        headers["X-Title"] = "QuantClaw"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": use_model,
                    "messages": messages,
                    "max_tokens": 4096,
                },
            )
            data = resp.json()
            if resp.status_code != 200:
                err = data.get("error", {})
                err_msg = err.get("message", "") if isinstance(err, dict) else str(err)
                return {"error": err_msg or f"API error {resp.status_code}", "agent": agent}
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"response": content, "agent": agent, "model": use_model, "provider": provider}
    except Exception as e:
        return {"error": str(e), "agent": agent}


def run_dashboard(host: str = "0.0.0.0", port: int = 8000):
    """Run the dashboard API server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)
