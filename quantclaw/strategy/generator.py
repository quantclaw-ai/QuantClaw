"""Generate strategy files from natural language descriptions."""
from __future__ import annotations
from pathlib import Path
from quantclaw.execution.router import LLMRouter

STRATEGY_GEN_PROMPT = """You are a quant strategy code generator. Given a natural language description of a trading strategy, generate a complete Python strategy file.

The strategy MUST follow this exact format:

```python
class Strategy:
    name = "Strategy Name"
    description = "What it does"
    universe = ["AAPL", "MSFT", ...]  # list of ticker symbols
    frequency = "weekly"  # daily, weekly, or monthly

    def signals(self, data):
        # data.history(symbol, bars=N) returns a DataFrame with open/high/low/close/volume
        # Return a dict of {{symbol: score}} where higher score = more bullish
        scores = {{}}
        for symbol in self.universe:
            df = data.history(symbol, bars=60)
            if len(df) >= 20:
                scores[symbol] = float(df["close"].iloc[-1] / df["close"].iloc[-20] - 1)
        return scores

    def allocate(self, scores, portfolio):
        # portfolio.equity = current portfolio value
        # portfolio.drawdown = current drawdown from peak
        # Return dict of {{symbol: weight}} where weights sum to <= 1.0
        ranked = sorted(scores, key=scores.get, reverse=True)[:3]
        return {{s: 1/3 for s in ranked}}

    def risk_check(self, orders, portfolio):
        # Return True to proceed, False to skip this rebalance
        return portfolio.drawdown > -0.10
```

Rules:
- Only use data.history(symbol, bars=N) for data access
- Only use pandas operations on the returned DataFrame
- Do NOT import external libraries except math and statistics
- The universe should be relevant to the strategy description
- Include a risk_check method with sensible defaults
- Output ONLY the Python code, no explanation or markdown

User request: {description}"""


class StrategyGenerator:
    def __init__(self, router: LLMRouter):
        self._router = router

    async def generate(self, description: str, save_path: str = None) -> str:
        """Generate a strategy from natural language. Returns the Python code."""
        prompt = STRATEGY_GEN_PROMPT.format(description=description)
        response = await self._router.call(
            "planner",
            messages=[{"role": "user", "content": prompt}],
        )

        # Clean up response - extract code if wrapped in markdown
        code = response.strip()
        if code.startswith("```python"):
            code = code[len("```python"):].strip()
        if code.startswith("```"):
            code = code[3:].strip()
        if code.endswith("```"):
            code = code[:-3].strip()

        # Validate it has the Strategy class
        if "class Strategy" not in code:
            raise ValueError("Generated code does not contain a Strategy class")

        # Save if path provided
        if save_path:
            path = Path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code)

        return code

    def generate_sync(self, description: str, save_path: str = None) -> str:
        """Synchronous wrapper for generate."""
        import asyncio
        return asyncio.run(self.generate(description, save_path))
