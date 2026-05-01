"""Sector Rotation: Rotate into strongest sectors by relative strength."""


class Strategy:
    name = "Sector Rotation"
    description = "Buy the top 3 sector ETFs ranked by 60-day momentum."
    style = "portfolio"
    universe = ["XLK", "XLV", "XLF", "XLY", "XLI", "XLE", "XLU", "XLP", "XLB", "XLRE", "XLC"]
    frequency = "monthly"
    top_n = 3

    def signals(self, data):
        scores = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=65)
            if len(df) >= 60:
                scores[symbol] = float(df["close"].iloc[-1] / df["close"].iloc[-60] - 1)
        return scores

    def allocate(self, scores, portfolio):
        ranked = sorted(scores, key=scores.get, reverse=True)[:self.top_n]
        if not ranked:
            return {}
        return {s: 1.0 / len(ranked) for s in ranked}
