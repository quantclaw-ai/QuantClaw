"""MA Crossover: Buy when 50d MA crosses above 200d MA."""


class Strategy:
    name = "Moving Average Crossover"
    description = "Buy when the 50-day moving average crosses above the 200-day moving average."
    style = "classic"
    universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "UNH"]
    frequency = "weekly"

    def signals(self, data):
        scores = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=210)
            if len(df) >= 200:
                ma50 = df["close"].rolling(50).mean().iloc[-1]
                ma200 = df["close"].rolling(200).mean().iloc[-1]
                scores[symbol] = float(ma50 / ma200 - 1)
        return scores

    def allocate(self, scores, portfolio):
        longs = {s: sc for s, sc in scores.items() if sc > 0}
        if not longs:
            return {}
        weight = min(1.0 / len(longs), 0.20)
        return {s: weight for s in longs}
