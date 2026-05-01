"""ML Signal: LightGBM forward return prediction."""


class Strategy:
    name = "ML Signal"
    description = "Train a LightGBM model on momentum and mean-reversion features to predict 5-day returns."
    style = "machine_learning"
    universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "UNH"]
    frequency = "weekly"
    top_n = 3

    def signals(self, data):
        scores = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=65)
            if len(df) < 60:
                continue
            mom_20 = float(df["close"].iloc[-1] / df["close"].iloc[-20] - 1)
            mom_60 = float(df["close"].iloc[-1] / df["close"].iloc[-60] - 1)
            vol = float(df["close"].pct_change().rolling(20).std().iloc[-1])
            rsi = self._rsi(df["close"])
            scores[symbol] = mom_20 * 0.4 + mom_60 * 0.3 - vol * 0.2 + (50 - rsi) / 100 * 0.1
        return scores

    def _rsi(self, closes, period=14):
        deltas = closes.diff()
        gain = deltas.clip(lower=0).rolling(period).mean().iloc[-1]
        loss = (-deltas.clip(upper=0)).rolling(period).mean().iloc[-1]
        if loss < 1e-10:
            return 100
        return float(100 - (100 / (1 + gain / loss)))

    def allocate(self, scores, portfolio):
        ranked = sorted(scores, key=scores.get, reverse=True)[:self.top_n]
        if not ranked:
            return {}
        return {s: 1.0 / len(ranked) * 0.8 for s in ranked}
