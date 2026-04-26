<div align="center">

<img src="quantclaw/dashboard/app/public/mascot.png" alt="QuantClaw" width="180" />

# QuantClaw

### Open-source campaign-driven agent harness for quantitative trading

*autonomous quant trading just one prompt away*

[![npm](https://img.shields.io/npm/v/quantclaw.svg)](https://www.npmjs.com/package/quantclaw)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Node 20+](https://img.shields.io/badge/node-20+-green.svg)](https://nodejs.org/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

[Documentation](docs/quickstart.md) | [Contributing](CONTRIBUTING.md) | [Discord](#)

</div>

---

QuantClaw is an open-source quant trading harness that orchestrates 12 AI agents — your **crewmates** on the trading floor — to handle the full lifecycle: data ingestion, signal generation, validation, live execution, risk monitoring, and reporting. You set a goal like *"go make me cash"*; the campaign engine compiles it into a paper-first state machine that only promotes to live when held-out validation passes.

Two commands. Five minutes. You're trading.

## Install

```bash
npm install -g quantclaw@latest
quantclaw start
```

Open [http://localhost:24121](http://localhost:24121) in your browser.

> **If `quantclaw start` is not recognized**, use `npx quantclaw start` instead. This works without PATH configuration.

### Prerequisites

- [Node.js 20+](https://nodejs.org/)
- [Python 3.12+](https://www.python.org/downloads/)
- [Ollama](https://ollama.com/) (optional, for local AI models)

## What Happens

1. **`npm install -g quantclaw@latest`** installs everything: Python backend, Node.js sidecar, Next.js dashboard
2. **`quantclaw start`** boots all three services in the background
3. **Browser onboarding** walks you through language, model provider, search, data sources, broker, and watchlist setup
4. **You're live** with a chat-first trading interface powered by AI agents

```bash
quantclaw start     # Start all services
quantclaw stop      # Stop all services
quantclaw status    # Check what's running
```

## Model Providers

QuantClaw supports multiple AI providers. Pick one during onboarding or configure later in Settings.

| Provider | Auth | Models |
|----------|------|--------|
| **Ollama** | Local, no key | qwen3, llama, mistral, etc. |
| **OpenAI** | OAuth (subscription) or API key | gpt-5.4, gpt-5.3-codex |
| **Anthropic** | OAuth (subscription) or API key | claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5 |
| **Google Gemini** | Free API key from [aistudio.google.com](https://aistudio.google.com/apikey) | gemini-3.1-pro, gemini-2.5-flash |
| **DeepSeek** | API key | deepseek-chat, deepseek-reasoner |
| **xAI** | API key | grok-4.20, grok-4-1-fast |
| **Mistral** | API key | mistral-large, mistral-small, codestral |
| **Groq** | API key | llama-3.3-70b, gpt-oss-120b, qwen3-32b |
| **OpenRouter** | API key | 200+ models from all providers |
| **Together AI** | API key | Llama, DeepSeek, Qwen open models |

**China users:** QuantClaw auto-detects your region and shows Chinese providers (DeepSeek, Qwen, Doubao, GLM, Kimi, ERNIE, Spark, etc.) with Chinese-language UI.

## 12 Crewmates on the Floor

Each crewmate is an agent with a scoped job, declared inputs/outputs, and a matching pet on the dashboard trading floor. Assign different models to different crewmates based on their compute needs.

| Crewmate | Role | Tier |
|----------|------|------|
| **Scheduler** | Cron-triggered daemon that wakes the floor | Light |
| **Sentinel** | Always-on market and event monitor | Medium |
| **Researcher** | LLM-driven web search for factors and signals | Heavy |
| **Ingestor** | Pulls market data and normalizes feeds into the parquet cache | Medium |
| **Miner** | Factor mining with LLM-powered discovery | Heavy |
| **Reporter** | Generates portfolio summaries and P&L reports | Light |
| **Trainer** | Trains ML models for signal generation | Heavy |
| **Validator** | Runs backtests + held-out evaluation in one pass *(was Backtester + Evaluator)* | Heavy |
| **Executor** | Handles order execution and broker integration | Medium |
| **Risk Monitor** | Monitors drawdowns, exposure, and VaR | Medium |
| **Compliance** | Checks trading against regulatory rules | Medium |
| **Debugger** | Diagnoses pipeline failures and routes diagnostic feedback | Medium |

## Market Data

44+ free data sources enabled by default, covering:

- **Stocks & ETFs** -- Yahoo Finance, Stooq, Finnhub, Twelve Data, Alpha Vantage, and more
- **Crypto** -- CoinGecko, Binance, CCXT (100+ exchanges), CoinPaprika, Kraken, Coinbase
- **Forex** -- ExchangeRate-API, Open Exchange Rates, Fixer.io
- **Commodities** -- Oil Price API, Alpha Vantage, Commodities-API, Metals-API
- **Economic Data** -- FRED, World Bank, US Treasury, IMF, BLS
- **Alternative** -- SEC EDGAR, ApeWisdom (Reddit sentiment), FINRA dark pool data
- **Kroness** -- Built-in unified feed across all markets

**China users** get AKShare, BaoStock, Tushare, EastMoney, Sina Finance, and other domestic sources.

Add API keys for premium providers anytime -- QuantClaw auto-upgrades routing based on rate limits.

## Web Dashboard

Dark-mode, multilingual (English / Chinese / Japanese) dashboard with:

- **Chat-first interface** -- Talk to your agents, route messages automatically
- **Model selector** -- Switch providers and models per conversation
- **Agent configuration** -- Assign models to each agent, auto-assign by tier
- **Portfolio overview** -- Positions, P&L, equity curve
- **Strategy browser** -- templates grouped by strategy family
- **Backtest runner** -- One-click strategy testing
- **Risk monitoring** -- Drawdown, exposure, VaR limits
- **Settings** -- Provider OAuth, API keys, language, notifications

### Notifications

Set up Telegram, Discord, and Slack during onboarding or later from **Dashboard -> Settings -> Notifications**. Credentials are written to your local `quantclaw.yaml`, which is ignored by git and npm packaging. Event routing rules live in `quantclaw/config/default.yaml` under `notification_routes`.

## Strategy Templates

Write strategies as simple Python files:

```python
class Strategy:
    name = "Simple Momentum"
    universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    frequency = "weekly"

    def signals(self, data):
        scores = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=25)
            if len(df) >= 20:
                scores[symbol] = df["close"].iloc[-1] / df["close"].iloc[-20] - 1
        return scores

    def allocate(self, scores, portfolio):
        ranked = sorted(scores, key=scores.get, reverse=True)[:3]
        return {s: 1/3 for s in ranked}
```

55 templates included: momentum, mean reversion, pairs trading, risk parity, sector rotation, ML signal, options wheel, and more.

## Architecture

```
quantclaw start
    |
    +-- Python Backend (FastAPI, localhost-only port 24120)
    |       Agent orchestration, data APIs, OAuth
    |
    +-- Node.js Sidecar (Express, localhost-only port 24122)
    |       OpenAI/Anthropic OAuth proxy (subscription-based)
    |
    +-- Next.js Dashboard (localhost-only port 24121)
            Chat UI, onboarding, settings, i18n
```

## Plugin System

```bash
quantclaw install broker-alpaca      # Add Alpaca broker
quantclaw install data-polygon       # Add Polygon data
quantclaw install engine-vectorbt    # Add vectorbt backtest engine
quantclaw install asset-crypto       # Add crypto trading
```

## Search Providers

Agents use web search for market research and news analysis:

Brave Search, Tavily, Exa, Perplexity, Firecrawl, Gemini Search, Grok Search, Kimi, DuckDuckGo (free fallback), SearXNG (self-hosted).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
