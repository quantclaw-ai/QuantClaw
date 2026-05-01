"""QuantClaw daemon: always-on event loop with scheduler and daemon agents."""
from __future__ import annotations
import asyncio
import logging
import signal
from datetime import datetime
from pathlib import Path
from croniter import croniter
from quantclaw.config.loader import load_config
from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType
from quantclaw.events.routing import EventRouter
from quantclaw.notifications.formatter import format_event
from quantclaw.notifications.config import build_notification_sinks
from quantclaw.execution.pool import AgentPool
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.router import LLMRouter
from quantclaw.orchestration.playbook import Playbook
from quantclaw.orchestration.trust import TrustManager, RiskGuardrails
from quantclaw.orchestration.autonomy import AutonomyManager
from quantclaw.orchestration.ooda import OODALoop
from quantclaw.state.db import StateDB
from quantclaw.state.tasks import TaskStore
from quantclaw.agents import ALL_AGENTS
from quantclaw.plugins.manager import PluginManager

logger = logging.getLogger(__name__)

class QuantClawDaemon:
    def __init__(self):
        self._running = False
        self._config = load_config("quantclaw.yaml" if Path("quantclaw.yaml").exists() else None)
        self._bus = EventBus()
        self._router = LLMRouter(self._config)
        self._pool = AgentPool(bus=self._bus, config=self._config)
        self._dispatcher = Dispatcher(pool=self._pool, bus=self._bus)
        self._playbook = Playbook("data/playbook.jsonl")
        self._guardrails = RiskGuardrails.from_config(self._config)
        self._autonomy = AutonomyManager()
        self._trust = TrustManager(bus=self._bus, playbook=self._playbook)
        self._event_router = EventRouter.from_config(self._config)
        self._plugin_manager = PluginManager()
        self._sinks = {}
        self._db = None
        self._task_store = None

    async def _init_sinks(self):
        self._sinks = build_notification_sinks(self._config)

    async def _notification_handler(self, event: Event):
        routes = self._event_router.get_routes(str(event.type))
        for route in routes:
            msg = format_event(event, urgency=route.urgency)
            for channel in route.channels:
                sink = self._sinks.get(channel)
                if sink:
                    try:
                        await sink.send(msg)
                    except Exception:
                        logger.exception("Failed to send notification to %s", channel)

    async def _scheduler_loop(self):
        """Run OODA loop with cron triggers and event-driven wakeup."""
        schedules = self._config.get("schedules", {})
        crons = {}
        for name, sched in schedules.items():
            cron_iter = croniter(sched["cron"], datetime.now())
            crons[name] = {
                "iter": cron_iter,
                "agent": sched["agent"],
                "task": sched.get("task", name),
                "depends_on": sched.get("depends_on"),
                "next": cron_iter.get_next(datetime),
            }

        check_interval = self._config.get("ooda_interval", 30)

        while self._running:
            # Check cron triggers
            now = datetime.now()
            for name, cron in crons.items():
                if now >= cron["next"]:
                    await self._bus.publish(Event(
                        type=EventType.SCHEDULE_TRIGGERED,
                        payload={"schedule": name, "agent": cron["agent"], "task": cron["task"]},
                    ))
                    self._ooda.add_pending_task({
                        "agent": cron["agent"],
                        "task": cron["task"],
                        "source": "cron",
                        "schedule": name,
                    })
                    cron["next"] = cron["iter"].get_next(datetime)

            # Run one full OODA cycle, including evaluation and campaign updates.
            await self._ooda.run_cycle(chat_history=[])

            # Event-driven sleep
            await self._ooda.sleep_until_trigger(timeout=check_interval)

    async def start(self):
        self._running = True
        self._db = await StateDB.create("data/quantclaw.db")
        self._task_store = TaskStore(self._db)
        await self._init_sinks()

        # Discover and register plugins
        self._plugin_manager.discover()

        # Register all agents
        for name, agent_cls in ALL_AGENTS.items():
            self._pool.register(name, agent_cls)

        self._bus.subscribe("*", self._notification_handler)

        # Restore execution trust state from playbook
        self._trust = await TrustManager.from_playbook(
            self._playbook, bus=self._bus
        )
        self._autonomy = await AutonomyManager.from_playbook(self._playbook)

        self._ooda = OODALoop(
            bus=self._bus,
            playbook=self._playbook,
            trust=self._trust,
            autonomy=self._autonomy,
            dispatcher=self._dispatcher,
            config=self._config,
        )
        await self._ooda.restore_persistent_state()

        print("QuantClaw daemon started")
        print(f"  Agents: {len(ALL_AGENTS)} registered")
        print(f"  Schedules: {len(self._config.get('schedules', {}))}")
        print(f"  Notification sinks: {list(self._sinks.keys())}")
        print(f"  OODA interval: {self._config.get('ooda_interval', 30)}s")
        print(f"  Execution trust state: {self._trust.level.name}")

        await self._scheduler_loop()

    async def stop(self):
        self._running = False
        if self._db:
            await self._db.close()
        print("QuantClaw daemon stopped")

async def run_daemon():
    daemon = QuantClawDaemon()
    loop = asyncio.get_event_loop()

    def handle_signal():
        asyncio.create_task(daemon.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    await daemon.start()
