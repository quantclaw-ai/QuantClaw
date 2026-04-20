# Quick Start Guide

Get from zero to your first backtest in 5 minutes.

## Install

```bash
pip install quantclaw
```

## Setup

```bash
quantclaw init
```

This starts the interactive setup wizard. For your first time, just hit Enter for all defaults:
- Data: yfinance (free, no API key needed)
- Broker: Paper trading (no real money)
- Risk: 10% max drawdown, 5% per position
- Schedule: Weekly rebalance on Mondays

## Create Your First Strategy

```bash
quantclaw new --template momentum --name my_first
```

This creates `strategies/my_first.py` from the Momentum template.

## Run a Backtest

```bash
quantclaw backtest strategies/my_first.py
```

This tests your strategy against 5 years of historical data and shows:
- Sharpe ratio (risk-adjusted returns)
- Annual return
- Maximum drawdown
- Comparison vs SPY (the bar to beat)

## Start Paper Trading

```bash
quantclaw start
```

This starts the daemon which paper trades your strategy with fake money. Check status anytime:

```bash
quantclaw status
```

## Open the Dashboard

```bash
quantclaw dashboard
```

Opens the web dashboard at http://localhost:3000 where you can see your portfolio, strategies, and agent status.

## What's Next?

- Browse more templates: `quantclaw list`
- Try different strategies and compare results
- Read the [Strategy Guide](strategy-guide.md) to write your own
- Level up to unlock more features!
