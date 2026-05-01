"""Risk Parity: Weight inversely by volatility."""


class Strategy:
    name = "Risk Parity"
    description = "Weight each position inversely by its volatility so each contributes equal risk."
    style = "portfolio"
    universe = ["SPY", "TLT", "GLD", "VNQ", "DBC"]
    frequency = "monthly"

    def signals(self, data):
        vols = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=65)
            if len(df) >= 20:
                vol = float(df["close"].pct_change().dropna().std())
                vols[symbol] = max(vol, 1e-8)
        return vols

    def allocate(self, scores, portfolio):
        inv_vols = {s: 1.0 / v for s, v in scores.items()}
        total = sum(inv_vols.values())
        if total <= 0:
            return {}
        return {s: v / total * 0.95 for s, v in inv_vols.items()}
