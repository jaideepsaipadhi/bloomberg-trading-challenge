"""Honest backtester for the EMA + momentum setup.

Evaluates every historical setup the screen would have fired and reports the
REAL performance statistics. It makes realistic, slightly pessimistic
assumptions:

* A setup is identified at a bar's close. The trade is ENTERED at the NEXT
  bar's open (no look-ahead; you can't trade on a close you haven't seen yet).
* Each subsequent day, the stop is checked against the day's LOW and the
  target against the day's HIGH. If both could have been hit in one day we
  assume the STOP hit first (pessimistic — real intraday path is unknown).
* If neither hits within ``max_hold_days``, the trade is closed at that day's
  close (the time stop).

The headline number you should care about is EXPECTANCY (average R per trade),
not win rate. A positive expectancy with a sub-60% win rate is a good system.
A 99% win rate is not a real target for this style of trading.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .indicators import add_indicators
from .strategy import _passes_filters


@dataclass
class Trade:
    symbol: str
    entry_date: str
    exit_date: str
    entry: float
    stop: float
    target: float
    exit_price: float
    outcome: str          # "target", "stop", "time"
    r_multiple: float     # P/L in units of initial risk
    bars_held: int


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.r_multiple > 0)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.r_multiple < 0)

    @property
    def win_rate(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def expectancy_r(self) -> float:
        """Average R per trade — the single most important edge metric."""
        if not self.n:
            return 0.0
        return float(np.mean([t.r_multiple for t in self.trades]))

    @property
    def avg_win_r(self) -> float:
        w = [t.r_multiple for t in self.trades if t.r_multiple > 0]
        return float(np.mean(w)) if w else 0.0

    @property
    def avg_loss_r(self) -> float:
        l = [t.r_multiple for t in self.trades if t.r_multiple < 0]
        return float(np.mean(l)) if l else 0.0

    @property
    def profit_factor(self) -> float:
        gross_win = sum(t.r_multiple for t in self.trades if t.r_multiple > 0)
        gross_loss = -sum(t.r_multiple for t in self.trades if t.r_multiple < 0)
        if gross_loss == 0:
            return float("inf") if gross_win > 0 else 0.0
        return float(gross_win / gross_loss)

    @property
    def max_drawdown_r(self) -> float:
        """Max peak-to-trough drawdown of the cumulative-R equity curve."""
        if not self.n:
            return 0.0
        equity = np.cumsum([t.r_multiple for t in self.trades])
        peak = np.maximum.accumulate(equity)
        dd = equity - peak
        return float(dd.min())

    def summary(self) -> dict:
        return {
            "trades": self.n,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 4),
            "expectancy_r": round(self.expectancy_r, 4),
            "avg_win_r": round(self.avg_win_r, 4),
            "avg_loss_r": round(self.avg_loss_r, 4),
            "profit_factor": round(self.profit_factor, 4) if np.isfinite(self.profit_factor) else None,
            "max_drawdown_r": round(self.max_drawdown_r, 4),
        }


def backtest_symbol(symbol: str, df: pd.DataFrame, cfg) -> list[Trade]:
    """Replay the strategy over one symbol's history."""
    if df is None or len(df) < cfg.min_bars_required + cfg.max_hold_days + 1:
        return []

    data = add_indicators(df, cfg)
    trades: list[Trade] = []
    n = len(data)

    i = cfg.min_bars_required
    while i < n - 1:  # need at least a next bar to enter on
        row = data.iloc[i]
        if not _passes_filters(row, cfg):
            i += 1
            continue

        atr_val = float(row["atr"])
        risk = cfg.stop_atr_mult * atr_val
        if risk <= 0:
            i += 1
            continue

        # Enter at NEXT bar's open (no look-ahead).
        entry_idx = i + 1
        entry = float(data.iloc[entry_idx]["open"])
        stop = entry - risk
        target = entry + risk * cfg.reward_risk_ratio

        outcome = "time"
        exit_price = entry
        exit_idx = entry_idx
        bars_held = 0

        for h in range(cfg.max_hold_days):
            bar_idx = entry_idx + h
            if bar_idx >= n:
                exit_idx = n - 1
                exit_price = float(data.iloc[exit_idx]["close"])
                break
            bar = data.iloc[bar_idx]
            bars_held = h + 1
            low = float(bar["low"])
            high = float(bar["high"])
            # Pessimistic: if both touched, assume stop first.
            if low <= stop:
                outcome, exit_price, exit_idx = "stop", stop, bar_idx
                break
            if high >= target:
                outcome, exit_price, exit_idx = "target", target, bar_idx
                break
            # time stop at the last allowed bar
            if h == cfg.max_hold_days - 1:
                outcome, exit_price, exit_idx = "time", float(bar["close"]), bar_idx

        r_multiple = (exit_price - entry) / risk if risk else 0.0

        def _d(idx):
            v = data.index[idx]
            return str(v.date()) if hasattr(v, "date") else str(v)

        trades.append(
            Trade(
                symbol=symbol,
                entry_date=_d(entry_idx),
                exit_date=_d(exit_idx),
                entry=round(entry, 4),
                stop=round(stop, 4),
                target=round(target, 4),
                exit_price=round(exit_price, 4),
                outcome=outcome,
                r_multiple=round(float(r_multiple), 4),
                bars_held=bars_held,
            )
        )

        # Move past this trade so we don't re-enter the same setup every bar.
        i = exit_idx + 1

    return trades


def backtest(symbol_data: dict[str, pd.DataFrame], cfg) -> BacktestResult:
    result = BacktestResult()
    for symbol, df in symbol_data.items():
        try:
            result.trades.extend(backtest_symbol(symbol, df, cfg))
        except Exception:
            continue
    # chronological order for the equity curve / drawdown
    result.trades.sort(key=lambda t: t.entry_date)
    return result
