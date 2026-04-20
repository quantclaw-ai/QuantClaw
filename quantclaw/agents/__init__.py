"""QuantClaw agent definitions."""
from quantclaw.agents.sentinel import SentinelAgent
from quantclaw.agents.risk_monitor import RiskMonitorAgent
from quantclaw.agents.scheduler import SchedulerAgent
from quantclaw.agents.ingestor import IngestorAgent
from quantclaw.agents.validator import ValidatorAgent
from quantclaw.agents.miner import MinerAgent
from quantclaw.agents.researcher import ResearcherAgent
from quantclaw.agents.executor import ExecutorAgent
from quantclaw.agents.reporter import ReporterAgent
from quantclaw.agents.trainer import TrainerAgent
from quantclaw.agents.compliance import ComplianceAgent
from quantclaw.agents.debugger import DebuggerAgent

ALL_AGENTS = {
    "sentinel": SentinelAgent,
    "risk_monitor": RiskMonitorAgent,
    "scheduler": SchedulerAgent,
    "ingestor": IngestorAgent,
    "validator": ValidatorAgent,
    "miner": MinerAgent,
    "researcher": ResearcherAgent,
    "executor": ExecutorAgent,
    "reporter": ReporterAgent,
    "trainer": TrainerAgent,
    "compliance": ComplianceAgent,
    "debugger": DebuggerAgent,
}
