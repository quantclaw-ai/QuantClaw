# Identity

## What QuantClaw Is

QuantClaw is an autonomous quantitative trading system powered by an AI orchestration engine. It discovers alpha factors, trains ML models, backtests strategies, and executes trades -- all coordinated by an OODA loop that plans, acts, learns, and adapts.

## Architecture

```
CEO (User)
  |
  v
Scheduler (OODA Loop)
  |-- Observe: gather state, events, playbook
  |-- Orient: determine goal alignment
  |-- Decide: Planner generates DAG (LLM or template)
  |-- Act: Dispatcher executes agents in parallel
  |-- Learn: record results to Playbook
  |-- Sleep: wait for next trigger
  |
  v
13 Specialized Agents
  |
  v
Sandbox (isolated execution) + Plugins (data, broker) + EventBus (pub-sub)
```

## Core Components

| Component | Location | Purpose |
|-----------|----------|---------|
| OODA Loop | `quantclaw/orchestration/ooda.py` | 6-phase orchestration engine |
| Planner | `quantclaw/execution/planner.py` | NL -> DAG task decomposition |
| Dispatcher | `quantclaw/execution/dispatcher.py` | DAG execution with parallelism |
| Playbook | `quantclaw/orchestration/playbook.py` | Append-only JSONL knowledge store |
| Trust Manager | `quantclaw/orchestration/trust.py` | Progressive trust levels |
| Autonomy Manager | `quantclaw/orchestration/autonomy.py` | Autopilot / Plan / Interactive modes |
| Sandbox | `quantclaw/sandbox/sandbox.py` | Process-isolated code execution |
| EventBus | `quantclaw/events/bus.py` | Pub-sub event system |
| Agents | `quantclaw/agents/` | 13 specialized workers |
| Dashboard | `quantclaw/dashboard/` | Next.js trading floor UI |
| Config | `quantclaw/config/` | YAML with env var expansion |

## Design Principles

1. **Event-driven, not polling.** The OODA loop sleeps until woken by events (market, cron, chat, agent completion).
2. **DAG-based planning.** Every cycle produces a directed acyclic graph of agent tasks. The Dispatcher handles parallelism and dependency injection.
3. **Sandbox isolation.** All model training and backtesting runs in subprocesses with memory/timeout limits.
4. **Progressive trust.** The system starts as Observer and must earn the right to paper trade, then live trade.
5. **LLM-minimal.** Code-only agents skip LLM calls entirely. Only Miner, Researcher, Reporter, Planner, and Debugger use LLMs.
6. **Playbook learning.** Every cycle appends results to a JSONL store. Future planning uses this context to avoid repeating failures.
7. **Template-first planning.** Common workflows match templates without an LLM call, saving ~2K tokens per cycle.
