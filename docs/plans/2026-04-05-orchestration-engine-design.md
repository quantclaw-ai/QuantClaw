# QuantClaw Orchestration Engine — Design Document

**Date:** 2026-04-05
**Status:** Approved
**Author:** Harry + Claude

## Overview

The Scheduler agent becomes an autonomous quant portfolio manager — a creative, self-evolving chief of staff that receives high-level intent ("go find me money", "make my portfolio grow") and autonomously plans, delegates, executes, learns, and adapts. It has maximum creative latitude, constrained only by risk guardrails. It interprets intent, not instructions.

**References:**
- OpenClaw: LLM-driven subagent spawning, push-based announce pattern, depth-limited tree execution
- DeerFlow (ByteDance): Lead agent pattern, TodoMiddleware for progress, ThreadPoolExecutor with concurrency caps
- QuantaAlpha: Evolutionary factor mining with LLM-generated hypotheses, mutation/crossover/exploration

## Three Autonomy Modes

| Mode | Behavior | Auto-Escalation |
|------|----------|-----------------|
| **Autopilot** | Plans + executes + reports results. Never asks. | Escalates to Plan Mode for high-risk actions (first live trade, position size increase, drawdown near limit) |
| **Plan Mode** | Shows plan, waits for CEO approval. CEO can modify steps. | Default for trust level 0-1 |
| **Interactive** | Step-by-step with real-time updates. CEO can intervene/redirect. | Available at all trust levels |

Mode can change mid-workflow: "switch to autopilot" or "hold on, show me the plan." The Scheduler respects mode per-action and auto-escalates regardless of mode for safety-critical decisions.

## The OODA Loop

The Scheduler runs a continuous Observe-Orient-Decide-Act-Learn loop:

### 1. OBSERVE — What's happening?
- Check market state via Ingestor (prices, news, events)
- Check portfolio state via Reporter (positions, P&L, exposure)
- Check pending tasks and agent statuses
- Read playbook for relevant notes and past results

### 2. ORIENT — What should we do?
- Compare current state to the CEO's goal
- Check for market events needing immediate response
- Review what worked/failed before (from playbook)
- Start goal-driven; become market-driven as playbook grows

### 3. DECIDE — Generate plan
- LLM creates task DAG as structured JSON
- In Plan Mode: show CEO, wait for approval
- In Autopilot: validate against risk guardrails, proceed
- In Interactive: show each step, allow intervention

### 4. ACT — Execute the plan
- Dispatch tasks to agents in parallel/sequence per DAG
- Collect results, pass between dependent agents
- Stream progress to trading floor (WebSocket events)
- Handle failures: retry, re-plan, or escalate

### 5. LEARN — Update playbook
- Record what worked, what failed, and why
- Update factor library with new discoveries
- Adjust confidence scores and strategy rankings
- Track trust milestones

### 6. SLEEP — Wait for next trigger
- Timer (configurable check interval)
- Market event (price alert, news, earnings)
- CEO instruction (new chat message)
- Agent completion (backtest finished, signal detected)

## Task DAG

The Scheduler LLM generates plans as JSON task graphs:

```json
{
  "goal": "Find profitable trading strategies",
  "reasoning": "CEO wants returns. Starting with momentum factor exploration across multiple timeframes.",
  "steps": [
    { "id": 0, "agent": "ingestor", "task": "Pull 2 years daily data for S&P 500 + crawl recent market news", "depends": [] },
    { "id": 1, "agent": "researcher", "task": "Identify promising factor categories from academic literature and news", "depends": [] },
    { "id": 2, "agent": "miner", "task": "Generate and evolve alpha factors using evolutionary mining", "depends": [0, 1] },
    { "id": 3, "agent": "backtester", "task": "Backtest top factors with realistic costs", "depends": [2] },
    { "id": 4, "agent": "risk_monitor", "task": "Risk analysis on backtest results", "depends": [3] },
    { "id": 5, "agent": "executor", "task": "Paper trade the winner", "depends": [4] },
    { "id": 6, "agent": "reporter", "task": "Generate summary report for CEO", "depends": [5] }
  ]
}
```

### Execution Rules
- Steps with empty `depends` run in parallel
- Steps wait for all dependencies before starting
- Each step's output passes as context to dependent steps
- On failure: Scheduler re-plans (retry, skip, try alternative)
- Trading floor shows each step in real-time

### Scheduler Creative Latitude
The Scheduler is NOT a command parser. It has full creative freedom to:
- Brainstorm its own research directions from vague intent
- Try unconventional combinations nobody asked for
- Run parallel experiments to see what sticks
- Abandon dead ends and double down on promising leads
- Surprise the CEO with approaches they didn't think of

The 8 workflow types (signal hunting, strategy development, backtest & compare, go live, portfolio management, risk response, research report, ML pipeline) are examples the Scheduler knows about, not hardcoded templates. It can invent new workflows.

## Per-Agent LLM Temperature

Each agent gets a tuned temperature based on its role:

| Agent | Temp | Role |
|-------|------|------|
| Miner | 0.9-1.0 | Creative divergent thinking for novel factor discovery |
| Researcher | 0.7 | Balance creativity and accuracy |
| Scheduler | 0.5 | Structured reliable planning |
| Trainer | 0.5 | Creative feature engineering + precise ML code |
| Debugger | 0.3 | Methodical diagnosis with some creative problem-solving |
| Reporter | 0.3 | Structured summaries, accurate numbers |
| Ingestor | 0.2 | Accurate data pulling, structured output |
| Backtester | 0.2 | Precise code generation |
| Sentinel | 0.2 | Alert monitoring, low false positives |
| Risk Monitor | 0.1 | Conservative exact risk calculations |
| Executor | 0.1 | Zero creativity — execute precisely |
| Compliance | 0.1 | Rule-following, no interpretation |
| Cost Tracker | 0.1 | Exact calculations |

Defaults overridable per-task by the Scheduler.

## Web Crawler / News Ingestion

The Ingestor agent crawls the web for market intelligence:

**Sources:** Financial news (Reuters, Bloomberg, CNBC), SEC filings (EDGAR), earnings transcripts, Reddit/social sentiment, research papers, central bank announcements, analyst reports.

**How:** Uses the configured search provider (Brave, Tavily, Exa, etc.). Crawls articles, extracts content, summarizes at low temperature (0.2) for accuracy. Passes structured summaries to Researcher/Miner as context.

**Triggers:** Scheduler OODA loop (daily scan), market events, CEO request, Miner requesting context.

## Evolutionary Factor Mining

The Miner agent runs an evolutionary loop (inspired by QuantaAlpha):

### The Loop
1. **Hypothesize** — LLM proposes factor ideas with structured reasoning
2. **Implement** — Generate executable factor code
3. **Evaluate** — Backtester agent tests factor (IC, Rank IC, Sharpe, drawdown, Calmar)
4. **Feedback** — Results feed back to LLM with full trace history
5. **Evolve** — Three strategies:
   - **Mutation**: Tweak the best factor (change parameters, add filters)
   - **Crossover**: Combine top 2 factors into a hybrid
   - **Exploration**: Try a completely new idea
6. **Record** — Save to playbook's Factor Library with full provenance

### Factor Library
Stored in playbook. Each factor has: hypothesis, code, evaluation metrics, lineage (what it evolved from). Scheduler queries: "What are my best factors?" — gets a ranked list. Factors combine into multi-factor strategies.

The Miner is the most autonomous agent — can run for extended periods in autopilot, continuously discovering and refining alpha.

## The Playbook — Self-Evolving Memory

Persistent knowledge store that grows with every workflow.

### Entry Types
| Type | Content |
|------|---------|
| Strategy results | Performance metrics, market conditions, what worked |
| What failed | Strategies that broke down, with analysis of why |
| Market observations | Patterns detected (e.g., "VIX > 30 correlates with momentum crashes") |
| CEO preferences | Risk tolerance, asset preferences, reporting style |
| Agent performance | Which models work best for which agents |
| Factor library | Mined factors with full provenance and lineage |
| Trust milestones | Performance track record for progressive trust |

### Usage
- Scheduler queries playbook before every decision
- Relevant entries injected into LLM system prompt
- Playbook grows continuously — the more the system runs, the smarter it gets
- No fixed timelines — just continuous evolution

### Storage
JSON-lines file at `data/playbook.jsonl`. Each entry: timestamp, type, tags, content. Searchable by tag and full-text.

## Progressive Trust System

The Scheduler earns capabilities through demonstrated performance.

| Level | Name | Capabilities | How to Earn |
|-------|------|-------------|-------------|
| 0 | Observer | Research, analyze, report. No trading. | Default |
| 1 | Paper Trader | Paper trade autonomously within risk limits | CEO approves first paper trade request |
| 2 | Proven | Can request live trading access | Positive paper trading track record |
| 3 | Trusted | Live trading within risk budget | CEO approves after reviewing paper results |
| 4 | Autonomous | Full autonomy within risk budget, explore new strategies | Sustained live performance |

The Scheduler tracks its own metrics and requests upgrades when ready. CEO approves or denies. Auto-escalation to Plan Mode for safety-critical actions regardless of trust level.

### Risk Guardrails (Always Enforced)
- Max drawdown limit (CEO-configured, default -10%)
- Max position size (default 5% of portfolio)
- Kill switch: CEO says "stop everything" → all trading halts immediately

## Trading Floor Integration

### Visual Feedback
- Scheduler lights up → broadcast pulse to target agents
- Agents light up as DAG steps execute (parallel/sequence)
- Progress bars fill on each station
- Speech bubbles show what each agent is doing
- Complete/error flashes as steps finish

### WebSocket Events
| Event | Trigger |
|-------|---------|
| `orchestration.plan.created` | Scheduler generates a new plan |
| `orchestration.step.started` | Agent begins a task |
| `orchestration.step.completed` | Agent finishes a task |
| `orchestration.step.failed` | Agent task fails |
| `orchestration.broadcast` | Scheduler dispatches to multiple agents |
| `playbook.entry.added` | New knowledge recorded |
| `trust.level.changed` | Trust level upgrade/downgrade |

### Chat Panel Narrative
The chat shows the full story: plan → delegation → agent results → Scheduler analysis → next steps → playbook updates. The CEO watches their trading desk work.

## Architecture Summary

```
CEO (chat input)
  |
  v
Scheduler (LLM, temp 0.5)
  |
  +-- OODA Loop (continuous)
  |     |
  |     +-- Observe: Ingestor + Reporter + Market Events
  |     +-- Orient: Playbook + Goal comparison
  |     +-- Decide: Generate Task DAG (JSON)
  |     +-- Act: Execute DAG via Agent Dispatch
  |     +-- Learn: Update Playbook
  |     +-- Sleep: Wait for trigger
  |
  +-- Agent Dispatch
  |     |
  |     +-- Parallel/Sequential execution per DAG
  |     +-- Each agent: LLM call with role prompt + context + temperature
  |     +-- Results flow between dependent steps
  |     +-- Progress streamed via WebSocket to floor
  |
  +-- Playbook (data/playbook.jsonl)
  |     |
  |     +-- Strategy results, market observations
  |     +-- Factor library with evolutionary lineage
  |     +-- CEO preferences, agent performance notes
  |
  +-- Trust System
        |
        +-- Performance tracking
        +-- Level requests to CEO
        +-- Risk guardrails (always enforced)
```

## Non-Requirements
- No real-money trading without explicit CEO approval at Trust Level 3+
- No access to CEO's personal accounts/data outside QuantClaw
- No self-modifying code — agents generate strategies, not system code
- No bypassing risk guardrails at any trust level
