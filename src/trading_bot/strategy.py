"""The EMA + momentum setup strategy.

Design goals (read the README for the honest rationale):

* Trade WITH the short-term trend, confirmed by a stacked EMA structure.
* Require genuine momentum (ROC + RSI in a constructive band, not overbought).
* Require participation (above-average volume).
* Avoid chasing parabolic moves (cap how far above the fast EMA we'll buy).
* Define risk BEFORE entry with an ATR stop, and target a reward that is a
  multiple of that risk so the system has positive expectancy even with a
  win rate well under 100%.

This produces *candidate long setups*. It is not a promise that any given
trade wins. Across many trades the goal is positive expectancy.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import math
import numpy as np
import pandas as pd

from .indicators import add_indicators


@dataclass
class Signal:
    symbol: str
    date: str                 # the bar on which the setup was identified (signal date)
    direction: str            # always "long" in this strategy
    entry: float              # suggested entry (last close; enter next session)
    stop: float               # protective stop
    target: float             # profit target
    atr: float
    risk_per_share: float
    reward_per_share: float
    reward_risk: float
    shares: int               # sized to the fixed notional
    notional: float           # shares * entry
    dollar_risk: float        # shares * risk_per_share  (what you actually risk)
    score: float              # ranking score (higher = stronger setup)
    # context, for the message
    rsi: float
    roc: float
    vol_ratio: float
    ema_fast: float
    ema_mid: float
    ema_slow: float
    exit_plan: str = ""       # how to manage the exit (trail vs fixed target)

    def to_dict(self) -> dict:
        return asdict(self)


def _passes_filters(row: pd.Series, cfg, regime_ok: bool = True) -> bool:
    """Boolean screen on a single (already-indicator-augmented) bar.

    ``regime_ok`` is the market-regime verdict for this bar's date (benchmark
    above its EMA). It only matters when ``cfg.use_regime_filter`` is set.
    """
    # Need valid indicator values.
    needed = ["ema_fast", "ema_mid", "ema_slow", "roc", "rsi", "atr",
              "vol_ratio", "atr_extension", "close", "high"]
    if cfg.use_adx_filter:
        needed.append("adx")
    if cfg.use_slope_filter:
        needed.append("ema_slow_slope")
    if any(pd.isna(row.get(c)) for c in needed):
        return False
    if row["atr"] <= 0:
        return False

    close = row["close"]

    # 1) EMA trend stack: fast > mid > slow, and price above the mid EMA.
    stacked = row["ema_fast"] > row["ema_mid"] > row["ema_slow"]
    above_mid = close > row["ema_mid"]

    # 2) Momentum: positive rate of change and RSI in a constructive band
    #    (strong but not yet overbought/blow-off).
    momentum = (row["roc"] >= cfg.roc_min) and (cfg.rsi_min <= row["rsi"] <= cfg.rsi_max)

    # 3) Participation: above-average volume.
    volume_ok = row["vol_ratio"] >= cfg.volume_ratio_min

    # 4) Anti-chasing: don't buy a move already stretched far above the fast EMA.
    not_overextended = row["atr_extension"] <= cfg.max_atr_extension

    if not (stacked and above_mid and momentum and volume_ok and not_overextended):
        return False

    # --- Optional win-rate filters (only applied when enabled in config) ---
    if cfg.use_regime_filter and not regime_ok:
        return False
    if cfg.use_adx_filter and row["adx"] < cfg.adx_min:
        return False
    if cfg.use_slope_filter and row["ema_slow_slope"] < cfg.slope_min:
        return False
    if cfg.use_pullback_entry and row["atr_extension"] > cfg.pullback_max_extension:
        return False

    return True


def _compute_score(roc, rsi, vol_ratio, atr_extension, atr, close, cfg):
    """Shared ranking score. Works elementwise, so it serves BOTH the scalar
    path (build_signal, passing floats/Series values) and the vectorised path
    (signal_frame, passing columns) — one formula, no divergence.

    Blend of momentum (ROC), trend strength (RSI above 50), volume surge, a
    tightness term (prefer entries near the fast EMA = lower risk), and, when
    enabled, a volatility tilt (prefer bigger-ATR% movers).
    """
    roc_c = np.tanh(roc / 10.0)                       # saturates, ~0..1
    rsi_c = np.clip((rsi - 50.0) / 25.0, 0, 1)         # 50->0, 75->1
    vol_c = np.clip((vol_ratio - 1.0) / 2.0, 0, 1)
    tight_c = np.clip(1.0 - (atr_extension / cfg.max_atr_extension), 0, 1)

    if cfg.use_vol_tilt:
        atrpct_c = np.clip((atr / close) / cfg.vol_tilt_ref, 0, 1)
        return (0.35 * roc_c + 0.20 * rsi_c + 0.15 * vol_c
                + 0.10 * tight_c + 0.20 * atrpct_c)
    return 0.40 * roc_c + 0.25 * rsi_c + 0.20 * vol_c + 0.15 * tight_c


def _score(row: pd.Series, cfg) -> float:
    """Scalar score for a single bar (used by build_signal)."""
    return float(_compute_score(
        row["roc"], row["rsi"], row["vol_ratio"], row["atr_extension"],
        row["atr"], row["close"], cfg))


def signal_frame(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Vectorised per-bar signal table for the whole history of one symbol.

    Returns a DataFrame indexed by date with columns:
      passes (bool), score (float), close, open, high, low, atr, ema_mid.
    This mirrors _passes_filters / _score exactly but computed column-wise, so
    the portfolio simulator can scan hundreds of symbols across thousands of
    days without a per-bar Python loop. (The market-regime gate, if enabled, is
    applied by the simulator against its own benchmark series.)
    """
    d = add_indicators(df, cfg)

    stacked = (d["ema_fast"] > d["ema_mid"]) & (d["ema_mid"] > d["ema_slow"])
    above_mid = d["close"] > d["ema_mid"]
    momentum = (d["roc"] >= cfg.roc_min) & (d["rsi"] >= cfg.rsi_min) & (d["rsi"] <= cfg.rsi_max)
    volume_ok = d["vol_ratio"] >= cfg.volume_ratio_min
    not_overext = d["atr_extension"] <= cfg.max_atr_extension

    passes = stacked & above_mid & momentum & volume_ok & not_overext & (d["atr"] > 0)
    passes = passes.fillna(False)

    if cfg.use_adx_filter:
        passes &= (d["adx"] >= cfg.adx_min).fillna(False)
    if cfg.use_slope_filter:
        passes &= (d["ema_slow_slope"] >= cfg.slope_min).fillna(False)
    if cfg.use_pullback_entry:
        passes &= (d["atr_extension"] <= cfg.pullback_max_extension).fillna(False)

    score = _compute_score(
        d["roc"], d["rsi"], d["vol_ratio"], d["atr_extension"],
        d["atr"], d["close"], cfg).fillna(0.0)

    out = pd.DataFrame({
        "passes": passes.astype(bool),
        "score": score.astype(float),
        "open": d["open"], "high": d["high"], "low": d["low"], "close": d["close"],
        "atr": d["atr"], "ema_mid": d["ema_mid"],
    }, index=d.index)
    return out


def build_signal(symbol: str, df: pd.DataFrame, cfg, portfolio,
                 regime_ok: bool = True) -> Optional[Signal]:
    """Evaluate the MOST RECENT bar of ``df`` for a setup.

    Returns a Signal if the latest bar qualifies, else None.
    ``df`` columns: open, high, low, close, volume (lower-case), datetime index.
    ``regime_ok`` is the benchmark regime verdict for the latest bar (only used
    when cfg.use_regime_filter is set).
    """
    if df is None or len(df) < cfg.min_bars_required:
        return None

    data = add_indicators(df, cfg)
    row = data.iloc[-1]

    if not _passes_filters(row, cfg, regime_ok=regime_ok):
        return None

    entry = float(row["close"])
    atr_val = float(row["atr"])
    risk_per_share = cfg.stop_atr_mult * atr_val
    if risk_per_share <= 0:
        return None

    stop = entry - risk_per_share
    reward_per_share = risk_per_share * cfg.reward_risk_ratio
    target = entry + reward_per_share

    shares = int(math.floor(portfolio.notional_per_trade / entry)) if entry > 0 else 0
    if shares <= 0:
        return None

    notional = shares * entry
    dollar_risk = shares * risk_per_share

    if cfg.exit_mode == "trend":
        trail = cfg.trail_atr_mult * atr_val
        exit_plan = (
            f"TREND: initial stop {stop:.2f}; trail {cfg.trail_atr_mult:g}xATR "
            f"(~{trail:.2f}) under the highs; exit on a close below EMA{cfg.ema_mid} "
            f"or after {cfg.max_trend_days}d. Let it run."
        )
    else:
        exit_plan = (
            f"SWING: target {target:.2f} (1:{cfg.reward_risk_ratio:g}), "
            f"stop {stop:.2f}, time-stop {cfg.max_hold_days}d."
        )

    return Signal(
        symbol=symbol,
        date=str(data.index[-1].date()) if hasattr(data.index[-1], "date") else str(data.index[-1]),
        direction="long",
        entry=round(entry, 4),
        stop=round(stop, 4),
        target=round(target, 4),
        atr=round(atr_val, 4),
        risk_per_share=round(risk_per_share, 4),
        reward_per_share=round(reward_per_share, 4),
        reward_risk=round(cfg.reward_risk_ratio, 2),
        shares=shares,
        notional=round(notional, 2),
        dollar_risk=round(dollar_risk, 2),
        score=round(_score(row, cfg), 4),
        rsi=round(float(row["rsi"]), 2),
        roc=round(float(row["roc"]), 2),
        vol_ratio=round(float(row["vol_ratio"]), 2),
        ema_fast=round(float(row["ema_fast"]), 4),
        ema_mid=round(float(row["ema_mid"]), 4),
        ema_slow=round(float(row["ema_slow"]), 4),
        exit_plan=exit_plan,
    )


def scan(symbol_data: dict[str, pd.DataFrame], cfg, portfolio,
         regime_ok: bool = True) -> list[Signal]:
    """Scan a universe {symbol: ohlcv_df} and return ranked setups.

    Capped by both cfg.max_signals and the portfolio's available slots.
    ``regime_ok`` is the benchmark regime verdict for the current scan date
    (only used when cfg.use_regime_filter is set).
    """
    signals: list[Signal] = []
    for symbol, df in symbol_data.items():
        try:
            sig = build_signal(symbol, df, cfg, portfolio, regime_ok=regime_ok)
        except Exception:
            # One bad symbol shouldn't sink the whole scan.
            sig = None
        if sig is not None:
            signals.append(sig)

    signals.sort(key=lambda s: s.score, reverse=True)

    cap = min(cfg.max_signals, portfolio.max_concurrent_positions) \
        if portfolio.max_concurrent_positions > 0 else cfg.max_signals
    return signals[:cap]
