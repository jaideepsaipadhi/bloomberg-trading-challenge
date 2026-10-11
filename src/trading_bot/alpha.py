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


def book_weights(names, vol_row, mode="invvol", cap=0.20) -> dict:
    """Portfolio weights for the held names. 'invvol' = inverse trailing
    volatility (down-weight jumpy winners), capped at `cap`, renormalised;
    'equal' = equal-weight. Always sums to ~1 (fully invested)."""
    if not names:
        return {}
    if mode != "invvol":
        return {nm: 1.0 / len(names) for nm in names}
    iv = {}
    for nm in names:
        v = vol_row.get(nm, np.nan)
        iv[nm] = 1.0 / (v + 1e-9) if (v is not None and np.isfinite(v) and v > 0) else 0.0
    if sum(iv.values()) <= 0:
        return {nm: 1.0 / len(names) for nm in names}
    # Water-fill so no weight exceeds `cap`: cap the over-weight names and
    # redistribute the freed budget across the rest until stable.
    weights, remaining, capped_total = {}, set(names), 0.0
    while remaining:
        tot = sum(iv[nm] for nm in remaining)
        budget = 1.0 - capped_total
        if tot <= 0:
            for nm in remaining:
                weights[nm] = budget / len(remaining)
            break
        over = [nm for nm in remaining if budget * iv[nm] / tot > cap]
        if not over:
            for nm in remaining:
                weights[nm] = budget * iv[nm] / tot
            break
        for nm in over:
            weights[nm] = cap
            capped_total += cap
            remaining.discard(nm)
    return weights


def momentum_score(closes: pd.DataFrame, lookback: int, skip: int,
                   vol_window: int = 0) -> pd.DataFrame:
    """Trailing return over `lookback` days, skipping the last `skip` days.

    If ``vol_window`` > 0, divide by trailing return volatility (risk-adjusted
    momentum). This does NOT raise the edge vs raw momentum, but in testing it
    shrank the worst-case windows markedly — a smoother ride for "place well".
    """
    raw = closes.shift(skip) / closes.shift(lookback) - 1.0
    if vol_window and vol_window > 0:
        vol = closes.pct_change().rolling(vol_window).std()
        raw = raw / (vol + 1e-9)
    return raw


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
    score = momentum_score(closes, cfg.mom_lookback, cfg.mom_skip, getattr(cfg, "mom_vol_window", 0))
    mode = getattr(cfg, "mom_weight", "equal")
    wvol = rets.rolling(getattr(cfg, "mom_weight_vol_window", 63)).std()

    idx = cal[start:end]
    port_daily = pd.Series(0.0, index=idx)
    weights: dict = {}
    for k, d in enumerate(idx):
        if k == 0:
            continue
        if (k - 1) % cfg.mom_rebalance_days == 0:
            s = score.loc[idx[k - 1]].replace([np.inf, -np.inf], np.nan).dropna()
            names = list(s.sort_values(ascending=False).head(top_k).index) if len(s) else []
            weights = book_weights(names, wvol.loc[idx[k - 1]], mode)
        if weights:
            dr = sum(w * rets.loc[d, nm] for nm, w in weights.items()
                     if np.isfinite(rets.loc[d, nm]))
            port_daily.loc[d] = float(dr)

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
    """Today's ranked top-K cross-sectional momentum book.

    Returns a list of dicts {symbol, momentum, price, weight} strongest first,
    where weight is the inverse-vol (or equal) portfolio weight — the live book
    this alpha would hold right now.
    """
    top_k = top_k or cfg.mom_top_k
    closes = close_panel(symbol_data)
    score = momentum_score(closes, cfg.mom_lookback, cfg.mom_skip, getattr(cfg, "mom_vol_window", 0))
    latest = score.iloc[-1].replace([np.inf, -np.inf], np.nan).dropna()
    ranked = latest.sort_values(ascending=False).head(top_k)
    prices = closes.iloc[-1]
    wvol = closes.pct_change().rolling(getattr(cfg, "mom_weight_vol_window", 63)).std().iloc[-1]
    weights = book_weights(list(ranked.index), wvol, getattr(cfg, "mom_weight", "equal"))
    return [{"symbol": s, "momentum": round(float(ranked[s]), 4),
             "price": round(float(prices.get(s, float("nan"))), 2),
             "weight": round(float(weights.get(s, 0.0)), 4)}
            for s in ranked.index]
