"""Factor evaluation metrics: IC, Rank IC, turnover, long-short Sharpe.

This module runs INSIDE the sandbox subprocess. It's imported by
Miner-generated scripts to evaluate factor quality.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def evaluate_factor(
    scores: dict[str, pd.Series],
    data: dict[str, pd.DataFrame],
    forward_period: int = 5,
) -> dict[str, float]:
    """Evaluate a factor's predictive power.

    Args:
        scores: {symbol: Series of factor scores} indexed by date
        data: {symbol: DataFrame with 'close' column} indexed by date
        forward_period: number of days for forward returns

    Returns:
        {ic, rank_ic, turnover, sharpe}
    """
    if not scores or not data:
        return {"ic": 0.0, "rank_ic": 0.0, "turnover": 0.0, "sharpe": 0.0}

    all_ic = []
    all_rank_ic = []
    all_turnover = []
    all_ls_returns = []

    for symbol, factor_scores in scores.items():
        if symbol not in data or "close" not in data[symbol].columns:
            continue

        close = data[symbol]["close"]
        fwd_returns = close.pct_change(forward_period).shift(-forward_period)

        common = factor_scores.index.intersection(fwd_returns.dropna().index)
        if len(common) < 10:
            continue

        fs = factor_scores.loc[common]
        fr = fwd_returns.loc[common]

        ic = float(fs.corr(fr))
        if not np.isnan(ic):
            all_ic.append(ic)

        rank_ic = float(fs.rank().corr(fr.rank()))
        if not np.isnan(rank_ic):
            all_rank_ic.append(rank_ic)

        ranks = fs.rank(pct=True)
        rank_diff = ranks.diff().abs()
        turnover = float(rank_diff.mean()) if len(rank_diff.dropna()) > 0 else 0.0
        all_turnover.append(turnover)

        # Long-short returns: long top quartile, short bottom quartile
        q75 = fs.quantile(0.75)
        q25 = fs.quantile(0.25)
        long_mask = fs >= q75
        short_mask = fs <= q25
        if long_mask.sum() > 0 and short_mask.sum() > 0:
            ls_ret = fr[long_mask].mean() - fr[short_mask].mean()
            if not np.isnan(ls_ret):
                all_ls_returns.append(ls_ret)

    mean_ic = float(np.mean(all_ic)) if all_ic else 0.0

    # Sharpe from actual long-short returns, not IC approximation
    if all_ls_returns:
        mean_ret = float(np.mean(all_ls_returns))
        std_ret = float(np.std(all_ls_returns)) if len(all_ls_returns) > 1 else abs(mean_ret) + 1e-8
        sharpe = mean_ret / max(std_ret, 1e-8) * np.sqrt(252 / max(forward_period, 1))
    else:
        sharpe = 0.0

    return {
        "ic": round(mean_ic, 4),
        "rank_ic": round(float(np.mean(all_rank_ic)) if all_rank_ic else 0.0, 4),
        "turnover": round(float(np.mean(all_turnover)) if all_turnover else 0.0, 4),
        "sharpe": round(sharpe, 4),
    }
