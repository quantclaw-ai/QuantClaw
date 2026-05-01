"""Simple Momentum: Buy stocks with highest 20-day returns."""


class Strategy:
    name = "Simple Momentum"
    description = "Buy the top N stocks ranked by 20-day price momentum."
    style = "classic"
    universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "UNH"]
    frequency = "weekly"
    top_n = 3

    def signals(self, data):
        scores = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=25)
            if len(df) >= 20:
                scores[symbol] = float(df["close"].iloc[-1] / df["close"].iloc[-20] - 1)
        return scores

    def allocate(self, scores, portfolio):
        ranked = sorted(scores, key=scores.get, reverse=True)[:self.top_n]
        if not ranked:
            return {}
        weight = min(1.0 / len(ranked), 0.33)
        return {s: weight for s in ranked}

    def risk_check(self, orders, portfolio):
        return portfolio.drawdown > -0.10
