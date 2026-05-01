"""Random Picks: Random stock selection. Sanity check baseline."""
import random


class Strategy:
    name = "Random Picks"
    description = "Randomly select stocks. Your strategy should beat this."
    style = "baseline"
    universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "UNH"]
    frequency = "weekly"
    pick_n = 3

    def signals(self, data):
        return {s: random.random() for s in self.universe}

    def allocate(self, scores, portfolio):
        ranked = sorted(scores, key=scores.get, reverse=True)[:self.pick_n]
        return {s: 1.0 / len(ranked) for s in ranked}
