"""Cross-sectional momentum alpha.

Rank the whole universe each day by trailing return (lookback, skipping the
most recent ``skip`` days to avoid short-term reversal), hold an equal-weight
top-K long book, and rebalance every ``rebalance`` trading days. This was the
strongest and most out-of-sample-robust alpha in the alpha-lab study — it fits
a *relative-return* competition because you simply hold the strongest names.

Pure functions over a price panel (DataFrame: index=dates, columns=symbols),
so they're fast and easy to test. No look-ahead: a rebalance ranks on the prior
close and earns forward returns.

NOTE on survivorship bias: momentum + a "today's index members only" universe
inflates backtested magnitude (momentum selects winners; survivorship keeps
only the ones that survived). Trust the relative ordering and the out-of-sample
hit-rate, not the headline total return.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


def close_panel(symbol_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Aligned close-price panel from {symbol: ohlcv_df}."""
    return pd.DataFrame({s: df["close"] for s, df in symbol_data.items()}).sort_index()


def momentum_score(closes: pd.DataFrame, lookback: int, skip: int) -> pd.DataFrame:
    """Trailing return over `lookback` days, skipping the last `skip` days."""
    return closes.shift(skip) / closes.shift(lookback) - 1.0


@dataclass
class AlphaResult:
    start: str
    end: str
    total_return: float
    benchmark_return: float
    relative_return: float
    max_drawdown: float
    equity_curve: list = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "start": self.start, "end": self.end,
            "total_return_pct": round(self.total_return * 100, 2),
            "benchmark_return_pct": round(self.benchmark_return * 100, 2),
            "relative_return_pct": round(self.relative_return * 100, 2),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
        }


def momentum_backtest(closes: pd.DataFrame, bench_close, cfg,
                      top_k=None, start=0, end=None) -> AlphaResult:
    """Equal-weight top-K cross-sectional momentum, rebalanced periodically.

    ``closes`` is the price panel; ``cfg`` a StrategyConfig (mom_* params).
    ``start``/``end`` are integer positions into the calendar.
    """
    top_k = top_k or cfg.mom_top_k
    cal = closes.index
    n = len(cal)
    end = n if end is None else min(end, n)
    rets = closes.pct_change()
    score = momentum_score(closes, cfg.mom_lookback, cfg.mom_skip)

    idx = cal[start:end]
    port_daily = pd.Series(0.0, index=idx)
    held: list[str] = []
    for k, d in enumerate(idx):
        if k == 0:
            continue
        if (k - 1) % cfg.mom_rebalance_days == 0:
            s = score.loc[idx[k - 1]].replace([np.inf, -np.inf], np.nan).dropna()
            held = list(s.sort_values(ascending=False).head(top_k).index) if len(s) else []
        if held:
            dr = rets.loc[d, held].mean()
            port_daily.loc[d] = 0.0 if not np.isfinite(dr) else float(dr)

    equity = (1 + port_daily).cumprod()
    total = float(equity.iloc[-1] - 1) if len(equity) else 0.0
    peak = equity.cummax()
    max_dd = float((equity / peak - 1).min()) if len(equity) else 0.0

    bench_return = 0.0
    if bench_close is not None:
        b = bench_close.reindex(idx).ffill().dropna()
        if len(b) >= 2:
            bench_return = float(b.iloc[-1] / b.iloc[0] - 1)

    return AlphaResult(
        start=str(idx[0].date()) if len(idx) else "",
        end=str(idx[-1].date()) if len(idx) else "",
        total_return=total, benchmark_return=bench_return,
        relative_return=total - bench_return, max_drawdown=max_dd,
        equity_curve=list(zip([str(x.date()) for x in idx], equity.tolist())),
    )


def momentum_walk_forward(closes, bench_close, cfg, top_k=None,
                          window_days=30, step_days=30, start=None):
    """Consecutive ~window_days windows; returns a list of AlphaResult."""
    n = len(closes.index)
    warmup = start if start is not None else (cfg.mom_lookback + cfg.mom_skip + 5)
    out = []
    i = warmup
    while i + window_days <= n:
        out.append(momentum_backtest(closes, bench_close, cfg, top_k,
                                     start=i, end=i + window_days))
        i += step_days
    return out


def momentum_picks(symbol_data, cfg, top_k=None):
    """Today's ranked top-K cross-sectional momentum names.

    Returns a list of dicts {symbol, momentum, price} strongest first — the
    live book this alpha would hold right now.
    """
    top_k = top_k or cfg.mom_top_k
    closes = close_panel(symbol_data)
    score = momentum_score(closes, cfg.mom_lookback, cfg.mom_skip)
    latest = score.iloc[-1].replace([np.inf, -np.inf], np.nan).dropna()
    ranked = latest.sort_values(ascending=False).head(top_k)
    prices = closes.iloc[-1]
    return [{"symbol": s, "momentum": round(float(ranked[s]), 4),
             "price": round(float(prices.get(s, float("nan"))), 2)}
            for s in ranked.index]
