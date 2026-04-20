"""Wheel Strategy: Sell puts, get assigned, sell covered calls."""


class Strategy:
    name = "Wheel Strategy"
    description = "Sell cash-secured puts on stocks you want to own. If assigned, sell covered calls."
    difficulty = "advanced"
    universe = ["AAPL", "MSFT", "GOOGL"]
    frequency = "weekly"

    def signals(self, data):
        scores = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=30)
            if len(df) >= 20:
                mom = float(df["close"].iloc[-1] / df["close"].iloc[-20] - 1)
                scores[symbol] = mom
        return scores

    def allocate(self, scores, portfolio):
        bullish = {s: sc for s, sc in scores.items() if sc > 0}
        if not bullish:
            return {}
        return {s: 0.25 for s in list(bullish.keys())[:2]}
