"""RSI Mean Reversion: Buy oversold, sell overbought."""


class Strategy:
    name = "RSI Mean Reversion"
    description = "Buy when RSI drops below 30, sell when RSI rises above 70."
    style = "classic"
    universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "UNH"]
    frequency = "daily"
    rsi_period = 14
    buy_threshold = 30

    def _compute_rsi(self, closes):
        deltas = closes.diff()
        gain = deltas.clip(lower=0).rolling(self.rsi_period).mean()
        loss = (-deltas.clip(upper=0)).rolling(self.rsi_period).mean()
        rs = gain / loss.clip(lower=1e-10)
        return 100 - (100 / (1 + rs))

    def signals(self, data):
        scores = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=30)
            if len(df) >= self.rsi_period + 1:
                rsi = self._compute_rsi(df["close"])
                scores[symbol] = -float(rsi.iloc[-1])
        return scores

    def allocate(self, scores, portfolio):
        buys = {s: sc for s, sc in scores.items() if -sc < self.buy_threshold}
        if not buys:
            return {}
        weight = min(1.0 / len(buys), 0.20)
        return {s: weight for s in buys}
