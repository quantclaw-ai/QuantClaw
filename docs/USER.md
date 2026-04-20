# User

The user is the CEO -- the human who sets goals, approves plans, and retains ultimate authority over capital deployment.

## Interaction Model

### Chat Interface
The CEO communicates through the trading floor chat. Messages route through the dashboard API to the OODA loop's DECIDE phase.

```
CEO message -> API -> Workflow template match?
                        yes -> auto-approve, execute
                        no  -> Planner generates DAG -> approval gate
```

### Autonomy Modes

The CEO controls how much autonomy QuantClaw has:

| Mode | CEO Involvement |
|------|----------------|
| **Interactive** | Approve every step |
| **Plan** (default) | Review plan, approve once, agents execute |
| **Autopilot** | System runs independently; CEO monitors |

### What the CEO Sees

- **Trading floor:** Real-time narration of agent activity
- **Chat:** Conversational interface with typing indicator
- **Logs:** Full agent execution history
- **Notifications:** Telegram, Discord, Slack alerts by urgency

### What the CEO Controls

- **Goals:** "Go make money", "Find momentum factors", "Backtest this strategy"
- **Autonomy mode:** Switch between Interactive / Plan / Autopilot
- **Trust escalation:** Approve upgrades (Observer -> Paper Trader -> Trusted)
- **Risk guardrails:** Max drawdown, position limits, auto-liquidation
- **Model assignments:** Which LLM each agent uses
- **Schedules:** Cron jobs for recurring tasks
- **Budget:** LLM API spending limits

### Notification Routing

| Event | Channels | Urgency |
|-------|----------|---------|
| Market events | Telegram, Discord | Immediate |
| Trade reconciliation fail | Telegram, Discord, Slack | Immediate |
| Agent failures | Telegram, Discord | High |
| Budget warnings | Telegram | High |
| Pipeline events | Discord | Normal |
| Factor events | Discord | Normal |
| Schedule triggers | Discord | Low |

## CEO Preferences

Stored in the Playbook as `ceo_preference` entries. Persisted across restarts. Currently tracked:
- Autonomy mode
- Approved trust levels
- Chat-triggered auto-approval (enabled)
