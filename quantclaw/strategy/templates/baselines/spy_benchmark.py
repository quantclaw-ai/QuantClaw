"""SPY Benchmark: Buy and hold SPY. The bar every strategy must beat."""


class Strategy:
    name = "SPY Benchmark"
    description = "100% SPY buy-and-hold. This is the baseline."
    style = "baseline"
    universe = ["SPY"]
    frequency = "monthly"

    def signals(self, data):
        return {"SPY": 1.0}

    def allocate(self, scores, portfolio):
        return {"SPY": 0.99}
