# Goals

## Primary Objective

Generate consistent, risk-adjusted returns through autonomous alpha discovery, model training, and disciplined execution.

## Priority Stack

1. **Capital preservation** -- never risk more than the guardrails allow
2. **Alpha discovery** -- find factors that predict returns
3. **Strategy validation** -- backtest before deploying anything
4. **Disciplined execution** -- paper trade first, live trade only when proven
5. **Continuous learning** -- record what works and what fails

## Orchestration Goals

### Per-Cycle
- Observe market state and pending events
- Orient toward the current strategic goal
- Decide on an optimal agent DAG (template or LLM-planned)
- Act by executing agents with parallelism
- Learn by recording results to Playbook
- Evaluate: pursue, iterate, or abandon

### Exploration vs Exploitation
The system balances discovery of new factors against refinement of known winners:

| Playbook Size | Temperature | Mode |
|---------------|-------------|------|
| < 5 entries | 0.7 | Explore (cast wide net) |
| 5-15 entries | 0.4 | Balanced |
| > 15 entries | 0.2 | Exploit (refine best) |

### Iteration Discipline
- Max 3 iterations per cycle (configurable)
- LLM evaluator judges each iteration: `pursue` / `iterate` / `abandon`
- Loop similarity detection (threshold 0.85) prevents spinning

## Risk Goals

| Guardrail | Default | Purpose |
|-----------|---------|---------|
| Max drawdown | -10% | Stop losses before catastrophic |
| Max position % | 5% | No single-stock concentration |
| Auto-liquidate | -15% | Emergency circuit breaker |

## Trust Progression

| Level | Name | Capabilities |
|-------|------|-------------|
| 0 | Observer | Research, analyze, report |
| 1 | Paper Trader | Paper trade within limits |
| 2 | Proven | Can request live trading |
| 3 | Trusted | Live trading within budget |
| 4 | Autonomous | Full autonomy within budget |

The system cannot skip levels. Each upgrade requires demonstrated performance at the current level.

## Budget Goals

- Track every LLM call cost
- Estimate pipeline costs before execution
- Warn at budget threshold
- Halt non-critical work if budget exhausted
