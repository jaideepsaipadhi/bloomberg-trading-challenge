"""Portfolio construction: turn ranked signals into position sizes.

The competition rewards *relative return*, long-only, no leverage, with a hard
20%-per-name cap. To place well you concentrate — fewer, bigger positions — so
a handful of winners move the needle, while staying diversified enough not to
be a pure lottery ticket.

``allocate`` takes ranked signals (strongest first) and current equity and
returns conviction-weighted dollar/share sizes, capped at ``max_position_pct``
and aiming for ~full deployment across up to ``target_positions`` names.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .strategy import signal_frame


@dataclass
class Allocation:
    symbol: str
    price: float
    weight: float      # fraction of equity
    dollars: float
    shares: int
    score: float


def _weights(scores: list[float], max_pct: float, sizing_mode: str) -> list[float]:
    """Conviction (or equal) weights that sum to ~1.0, each <= max_pct.

    Uses water-filling: cap the over-weight names at max_pct and redistribute
    the freed budget across the rest, repeating until stable.
    """
    n = len(scores)
    if n == 0:
        return []
    # Guard: if the cap can't fit n names, equal-weight at the cap is the best
    # we can do (deployment will be < 100%).
    if max_pct * n <= 1.0:
        return [max_pct] * n

    if sizing_mode == "equal":
        raw = [1.0] * n
    else:  # score-weighted; shift to keep positives even if a score is ~0
        base = min(scores)
        raw = [max(s - base, 0.0) + 1e-9 for s in scores]

    weights = [0.0] * n
    free = set(range(n))
    assigned = 0.0
    raw_free_sum = sum(raw[i] for i in free)

    while free:
        budget = 1.0 - assigned
        over = []
        for i in list(free):
            w = budget * raw[i] / raw_free_sum if raw_free_sum > 0 else 0.0
            if w > max_pct:
                over.append(i)
        if not over:
            # No one exceeds the cap: assign proportionally and finish.
            for i in free:
                weights[i] = budget * raw[i] / raw_free_sum if raw_free_sum > 0 else 0.0
            break
        for i in over:
            weights[i] = max_pct
            assigned += max_pct
            free.discard(i)
        raw_free_sum = sum(raw[i] for i in free)
    return weights


def allocate(signals, equity: float, pcfg) -> list[Allocation]:
    """Size the top ``target_positions`` signals into a concentrated book.

    ``signals`` must be ranked strongest-first; each needs ``.symbol``,
    ``.entry`` (price) and ``.score``.
    """
    if equity <= 0 or not signals:
        return []

    picks = list(signals[: pcfg.target_positions])

    # Drop would-be dust positions, then re-weight the survivors so we still
    # deploy ~fully across the remaining names.
    while picks:
        weights = _weights([s.score for s in picks], pcfg.max_position_pct, pcfg.sizing_mode)
        small = [i for i, w in enumerate(weights) if w < pcfg.min_position_pct]
        if not small or len(picks) == 1:
            break
        # Remove the single smallest and retry.
        drop = min(range(len(picks)), key=lambda i: weights[i])
        picks.pop(drop)

    allocations: list[Allocation] = []
    for sig, w in zip(picks, weights):
        price = float(sig.entry)
        if price <= 0 or w <= 0:
            continue
        dollars = w * equity
        shares = int(math.floor(dollars / price))
        if shares <= 0:
            continue
        allocations.append(
            Allocation(
                symbol=sig.symbol,
                price=round(price, 4),
                weight=round(w, 4),
                dollars=round(shares * price, 2),
                shares=shares,
                score=getattr(sig, "score", 0.0),
            )
        )
    return allocations


# ---------------------------------------------------------------------------
# Portfolio simulation — the metric the competition actually scores.
# ---------------------------------------------------------------------------

@dataclass
class PortfolioResult:
    start: str
    end: str
    start_equity: float
    end_equity: float
    total_return: float          # strategy return over the window
    benchmark_return: float      # buy-and-hold benchmark over the same window
    relative_return: float       # total_return - benchmark_return (what wins)
    max_drawdown: float          # peak-to-trough of the equity curve
    n_trades: int
    win_rate: float
    equity_curve: list = field(default_factory=list)   # [(date, equity)]

    def summary(self) -> dict:
        return {
            "start": self.start, "end": self.end,
            "total_return_pct": round(self.total_return * 100, 2),
            "benchmark_return_pct": round(self.benchmark_return * 100, 2),
            "relative_return_pct": round(self.relative_return * 100, 2),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "n_trades": self.n_trades,
            "win_rate": round(self.win_rate, 3),
        }


def _prepare(symbol_data: dict[str, pd.DataFrame], cfg):
    """Pre-compute aligned numpy arrays for every symbol on a common calendar."""
    frames = {}
    for sym, df in symbol_data.items():
        try:
            f = signal_frame(df, cfg)
        except Exception:
            continue
        if len(f):
            frames[sym] = f
    if not frames:
        return None, {}

    calendar = sorted(set().union(*[set(f.index) for f in frames.values()]))
    calendar = pd.DatetimeIndex(calendar)

    prepared = {}
    for sym, f in frames.items():
        g = f.reindex(calendar)
        prepared[sym] = {
            "open": g["open"].to_numpy(dtype="float64"),
            "high": g["high"].to_numpy(dtype="float64"),
            "low": g["low"].to_numpy(dtype="float64"),
            "close": g["close"].to_numpy(dtype="float64"),
            "atr": g["atr"].to_numpy(dtype="float64"),
            "ema_mid": g["ema_mid"].to_numpy(dtype="float64"),
            "passes": g["passes"].fillna(False).to_numpy(dtype="bool"),
            "score": g["score"].fillna(0.0).to_numpy(dtype="float64"),
        }
    return calendar, prepared


def simulate(symbol_data, cfg, pcfg, benchmark_close=None,
             start_idx=None, end_idx=None, _prepared=None):
    """Event-driven daily long-only portfolio simulation.

    Each day: (1) manage/exit held positions on that day's bar, (2) buy any
    entries queued yesterday at today's open, (3) from today's close signals,
    queue the top-ranked new names to fill free slots tomorrow. No look-ahead:
    decisions at a close are executed at the next open.

    Returns a PortfolioResult. ``benchmark_close`` (e.g. SPY) is bought-and-held
    over the same window for the relative-return figure the competition scores.
    """
    if _prepared is not None:
        calendar, data = _prepared
    else:
        calendar, data = _prepare(symbol_data, cfg)
    if calendar is None or len(calendar) < 3:
        return None

    n = len(calendar)
    i0 = 0 if start_idx is None else max(0, start_idx)
    i1 = n - 1 if end_idx is None else min(n - 1, end_idx)
    if i1 - i0 < 2:
        return None

    cash = float(pcfg.total_capital)
    start_equity = cash
    positions: dict[str, dict] = {}
    pending: list[str] = []
    equity_curve = []
    closed = []  # list of r-style P&L fraction per trade for win-rate

    trail = cfg.trail_atr_mult
    per_slot_target = 1.0 / max(1, pcfg.target_positions)

    for t in range(i0, i1 + 1):
        # ---- 1. manage existing positions on today's bar ----
        for sym in list(positions.keys()):
            d = data[sym]
            low, high, close = d["low"][t], d["high"][t], d["close"][t]
            if np.isnan(close):
                continue
            pos = positions[sym]
            exit_price = None
            if cfg.exit_mode == "trend":
                pos["highest"] = max(pos["highest"], high if not np.isnan(high) else pos["highest"])
                pos["stop"] = max(pos["stop"], pos["highest"] - trail * pos["atr"])
                if not np.isnan(low) and low <= pos["stop"]:
                    exit_price = pos["stop"]
                elif cfg.use_ema_trend_exit and not np.isnan(d["ema_mid"][t]) and close < d["ema_mid"][t]:
                    exit_price = close
                elif (t - pos["entry_t"]) >= cfg.max_trend_days:
                    exit_price = close
            else:  # swing
                if not np.isnan(low) and low <= pos["stop"]:
                    exit_price = pos["stop"]
                elif not np.isnan(high) and high >= pos["target"]:
                    exit_price = pos["target"]
                elif (t - pos["entry_t"]) >= cfg.max_hold_days:
                    exit_price = close
            if exit_price is not None:
                cash += pos["shares"] * exit_price
                closed.append(exit_price / pos["entry"] - 1.0)
                del positions[sym]

        # ---- 2. execute entries queued yesterday, at today's open ----
        for sym in pending:
            if sym in positions or len(positions) >= pcfg.target_positions:
                continue
            d = data[sym]
            price = d["open"][t]
            if np.isnan(price) or price <= 0:
                continue
            equity_now = cash + sum(p["shares"] * data[s]["close"][t]
                                    for s, p in positions.items()
                                    if not np.isnan(data[s]["close"][t]))
            target_dollars = min(per_slot_target, pcfg.max_position_pct) * equity_now
            target_dollars = min(target_dollars, cash)
            shares = int(math.floor(target_dollars / price))
            if shares <= 0:
                continue
            cash -= shares * price
            atr0 = d["atr"][t] if not np.isnan(d["atr"][t]) else price * 0.02
            positions[sym] = {
                "shares": shares, "entry": price, "entry_t": t,
                "stop": price - cfg.stop_atr_mult * atr0,
                "target": price + cfg.stop_atr_mult * atr0 * cfg.reward_risk_ratio,
                "atr": atr0, "highest": price,
            }
        pending = []

        # ---- 3. queue tomorrow's entries from today's close signals ----
        free = pcfg.target_positions - len(positions)
        if free > 0 and t < i1:
            cands = []
            for sym, d in data.items():
                if sym in positions:
                    continue
                if d["passes"][t] and not np.isnan(d["open"][t + 1]):
                    cands.append((d["score"][t], sym))
            cands.sort(reverse=True)
            pending = [sym for _, sym in cands[:free]]

        # ---- mark-to-market equity ----
        mtm = cash + sum(p["shares"] * data[s]["close"][t]
                         for s, p in positions.items()
                         if not np.isnan(data[s]["close"][t]))
        equity_curve.append((calendar[t], mtm))

    # liquidate at final close
    tN = i1
    for sym, pos in positions.items():
        c = data[sym]["close"][tN]
        if not np.isnan(c):
            cash += pos["shares"] * c
            closed.append(c / pos["entry"] - 1.0)
    end_equity = equity_curve[-1][1] if equity_curve else start_equity

    # metrics
    eq = np.array([e for _, e in equity_curve], dtype="float64")
    peak = np.maximum.accumulate(eq)
    max_dd = float((eq / peak - 1.0).min()) if len(eq) else 0.0
    total_return = end_equity / start_equity - 1.0

    bench_return = 0.0
    if benchmark_close is not None:
        b = benchmark_close.reindex(calendar[i0:i1 + 1]).ffill().dropna()
        if len(b) >= 2:
            bench_return = float(b.iloc[-1] / b.iloc[0] - 1.0)

    wins = sum(1 for r in closed if r > 0)
    win_rate = wins / len(closed) if closed else 0.0

    return PortfolioResult(
        start=str(calendar[i0].date()), end=str(calendar[i1].date()),
        start_equity=start_equity, end_equity=end_equity,
        total_return=total_return, benchmark_return=bench_return,
        relative_return=total_return - bench_return, max_drawdown=max_dd,
        n_trades=len(closed), win_rate=win_rate, equity_curve=equity_curve,
    )


def walk_forward(symbol_data, cfg, pcfg, benchmark_close=None,
                 window_days=30, step_days=30):
    """Run the simulation over consecutive windows (default ~6 trading weeks,
    the competition length) and summarise the distribution of outcomes —
    the honest answer to "how would this place?"."""
    calendar, data = _prepare(symbol_data, cfg)
    if calendar is None:
        return []
    n = len(calendar)
    # Skip warmup where indicators are still NaN.
    warmup = min(cfg.min_bars_required + 5, n - 1)
    results = []
    i = warmup
    while i + window_days <= n - 1:
        r = simulate(symbol_data, cfg, pcfg, benchmark_close,
                     start_idx=i, end_idx=i + window_days,
                     _prepared=(calendar, data))
        if r is not None:
            results.append(r)
        i += step_days
    return results
