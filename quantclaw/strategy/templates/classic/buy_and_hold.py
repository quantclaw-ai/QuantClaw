"""Buy and Hold: Equal-weight the universe."""


class Strategy:
    name = "Buy and Hold"
    description = "Equal-weight buy and hold. Simple passive strategy."
    style = "classic"
    universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    frequency = "monthly"

    def signals(self, data):
        return {s: 1.0 for s in self.universe}

    def allocate(self, scores, portfolio):
        n = len(self.universe)
        return {s: 1.0 / n for s in self.universe}
