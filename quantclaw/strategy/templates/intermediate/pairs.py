"""Pairs Trading: Trade mean-reverting spread between two correlated stocks."""


class Strategy:
    name = "Pairs Trading"
    description = "Trade the z-score of the spread between two cointegrated assets."
    difficulty = "intermediate"
    universe = ["GLD", "GDX"]
    frequency = "daily"
    lookback = 60
    entry_z = 2.0
    exit_z = 0.5

    def signals(self, data):
        a = data.history(self.universe[0], bars=self.lookback)
        b = data.history(self.universe[1], bars=self.lookback)
        if len(a) < self.lookback or len(b) < self.lookback:
            return {}
        spread = a["close"].values - b["close"].values
        z = (spread[-1] - spread.mean()) / max(spread.std(), 1e-8)
        return {"spread_z": float(z)}

    def allocate(self, scores, portfolio):
        z = scores.get("spread_z", 0)
        if z > self.entry_z:
            return {self.universe[0]: -0.3, self.universe[1]: 0.3}
        elif z < -self.entry_z:
            return {self.universe[0]: 0.3, self.universe[1]: -0.3}
        elif abs(z) < self.exit_z:
            return {}
        return {}
