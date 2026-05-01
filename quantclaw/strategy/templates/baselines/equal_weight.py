"""Equal Weight: Naive equal-weight diversification baseline."""


class Strategy:
    name = "Equal Weight"
    description = "Equal-weight all stocks in universe. Naive diversification baseline."
    style = "baseline"
    universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "UNH"]
    frequency = "monthly"

    def signals(self, data):
        return {s: 1.0 for s in self.universe}

    def allocate(self, scores, portfolio):
        n = len(self.universe)
        return {s: 0.95 / n for s in self.universe}
