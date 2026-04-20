# Tools

The infrastructure layer that agents use to interact with the world.

## Sandbox

**Location:** `quantclaw/sandbox/sandbox.py`

Process-isolated code execution for untrusted computations (model training, backtesting, factor evaluation).

| Setting | Default | Purpose |
|---------|---------|---------|
| `timeout` | 60s | Max execution time |
| `max_output` | 100KB | Stdout/stderr cap |
| `max_memory_mb` | 512MB | Memory limit |
| `max_concurrent` | 3 | Parallel sandbox slots |

**Components:**
- `sandbox.py` -- Async subprocess executor with temp directory isolation
- `model_trainer.py` -- Generates sklearn training scripts
- `factor_evaluator.py` -- Factor quality metrics (IC, Rank IC, Sharpe)
- `runner.py` -- Strategy backtest execution
- `security.py` -- AST-based import validation

**Flow:**
```
Code string -> write to temp dir -> subprocess.create_subprocess_exec()
  -> capture stdout/stderr -> parse last line as JSON -> cleanup temp dir
  -> return SandboxResult(status, stdout, stderr, parsed_result)
```

## Plugins

**Location:** `quantclaw/plugins/`

Swappable integrations for data, broker, and compute:

| Plugin Type | Default | Purpose |
|-------------|---------|---------|
| `data` | `data_yfinance` | Market data (OHLCV + fundamentals + sentiment) |
| `broker` | `broker_ib` | Order execution (Interactive Brokers) |
| `engine` | `engine_builtin` | Backtest engine |
| `asset` | `asset_us_equities` | Universe definition |

Configured in `quantclaw.yaml` or `quantclaw/config/default.yaml`:
```yaml
plugins:
  broker: broker_ib
  data: [data_yfinance]
  engine: engine_builtin
  asset: [asset_us_equities]
```

### Dynamic Data Fields

Data plugins expose `available_fields()` — a catalog of fetchable field categories:

| Category | Fields | Type |
|----------|--------|------|
| `ohlcv` | open, high, low, close, volume | Time-series |
| `fundamentals` | trailingPE, forwardPE, priceToBook, profitMargins, returnOnEquity, revenueGrowth, earningsGrowth, debtToEquity, freeCashflow, etc. | Scalar (broadcast) |
| `sentiment` | shortRatio, shortPercentOfFloat, heldPercentInsiders, heldPercentInstitutions | Scalar (broadcast) |
| `technical` | beta, fiftyDayAverage, twoHundredDayAverage, fiftyTwoWeekHigh/Low, marketCap, enterpriseValue | Scalar (broadcast) |

**Dynamic flow:** Researcher discovers useful data types -> suggests `data_sources` -> Ingestor fetches those fields via `fetch_fields()` -> Miner receives enriched DataFrames with extra columns -> factor code can reference fundamentals/sentiment alongside price data.

New data plugins can register additional field categories (e.g. `data_fred` for macro, `data_sec` for filings) — the Researcher discovers them, the Ingestor fetches them, and the Miner mines from them.

## EventBus

**Location:** `quantclaw/events/bus.py`

Pub-sub system for decoupled communication between agents and orchestration:
- Agents publish events on start/complete/fail
- Sentinel subscribes to monitor for anomalies
- Dashboard subscribes for real-time narration
- OODA loop wakes on relevant events

## LLM Router

**Location:** `quantclaw/execution/router.py`

Routes LLM calls to configured providers:

| Model ID | Provider | Model |
|----------|----------|-------|
| `opus` | Anthropic | claude-opus-4-6 |
| `sonnet` | Anthropic | claude-sonnet-4-6 |
| `gpt` | OpenAI | gpt-4o |
| `local` | Ollama | llama3.1 |

Temperature overrides per agent. OAuth tokens route through the Node.js sidecar; API keys go direct to SDKs.

## Playbook

**Location:** `quantclaw/orchestration/playbook.py`

Append-only JSONL knowledge store. The system's long-term memory.

**Entry Types:**
| Type | Purpose |
|------|---------|
| `strategy_result` | Backtest/live performance metrics |
| `what_failed` | Failed approaches with context |
| `market_observation` | Market regime notes |
| `ceo_preference` | User settings (autonomy mode, etc.) |
| `agent_performance` | Agent reliability tracking |
| `factor_library` | Discovered alpha factors |
| `trust_milestone` | Trust level changes |

**Operations:** `add()`, `query(tags, entry_type)`, `search(text)`, `recent(n)`

## Web Search

**Provider:** DuckDuckGo (default), configurable via `search.provider`

Used by Ingestor and Researcher for market intelligence gathering.

## Notifications

**Location:** `quantclaw/notifications/`

| Channel | Config |
|---------|--------|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Discord | `DISCORD_WEBHOOK_URL` |
| Slack | `SLACK_WEBHOOK_URL` |

Routed by event pattern and urgency level.

## Dashboard

**Location:** `quantclaw/dashboard/`

Next.js trading floor UI with:
- Real-time agent activity narration
- Chat interface with localStorage persistence
- Log viewer
- LLM provider banner and model picker
- Onboarding flow with OAuth setup

API served by FastAPI at `quantclaw/dashboard/api.py`.

## Sidecar

**Location:** `quantclaw/sidecar/`

Node.js OAuth proxy for browser-based LLM authentication. Handles token refresh and routes requests to OpenAI/Anthropic APIs when using OAuth flow instead of direct API keys.
