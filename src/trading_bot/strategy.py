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

    def to_dict(self) -> dict:
        return asdict(self)


def _passes_filters(row: pd.Series, cfg) -> bool:
    """Boolean screen on a single (already-indicator-augmented) bar."""
    # Need valid indicator values.
    needed = ["ema_fast", "ema_mid", "ema_slow", "roc", "rsi", "atr",
              "vol_ratio", "atr_extension", "close", "high"]
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

    return bool(stacked and above_mid and momentum and volume_ok and not_overextended)


def _score(row: pd.Series, cfg) -> float:
    """Rank setups so the strongest float to the top when slots are scarce.

    Blend of: momentum (ROC), RSI distance above 50 (trend strength without
    overbought penalty), volume surge, and proximity to the fast EMA
    (prefer tighter, lower-risk entries). All normalised to rough 0-1-ish
    ranges before weighting.
    """
    roc_component = np.tanh(row["roc"] / 10.0)                 # saturates, ~0..1
    rsi_component = np.clip((row["rsi"] - 50.0) / 25.0, 0, 1)   # 50->0, 75->1
    vol_component = np.clip((row["vol_ratio"] - 1.0) / 2.0, 0, 1)
    # Lower extension is better (tighter stop): invert.
    tight_component = np.clip(1.0 - (row["atr_extension"] / cfg.max_atr_extension), 0, 1)

    return float(
        0.40 * roc_component
        + 0.25 * rsi_component
        + 0.20 * vol_component
        + 0.15 * tight_component
    )


def build_signal(symbol: str, df: pd.DataFrame, cfg, portfolio) -> Optional[Signal]:
    """Evaluate the MOST RECENT bar of ``df`` for a setup.

    Returns a Signal if the latest bar qualifies, else None.
    ``df`` columns: open, high, low, close, volume (lower-case), datetime index.
    """
    if df is None or len(df) < cfg.min_bars_required:
        return None

    data = add_indicators(df, cfg)
    row = data.iloc[-1]

    if not _passes_filters(row, cfg):
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
    )


def scan(symbol_data: dict[str, pd.DataFrame], cfg, portfolio) -> list[Signal]:
    """Scan a universe {symbol: ohlcv_df} and return ranked setups.

    Capped by both cfg.max_signals and the portfolio's available slots.
    """
    signals: list[Signal] = []
    for symbol, df in symbol_data.items():
        try:
            sig = build_signal(symbol, df, cfg, portfolio)
        except Exception:
            # One bad symbol shouldn't sink the whole scan.
            sig = None
        if sig is not None:
            signals.append(sig)

    signals.sort(key=lambda s: s.score, reverse=True)

    cap = min(cfg.max_signals, portfolio.max_concurrent_positions) \
        if portfolio.max_concurrent_positions > 0 else cfg.max_signals
    return signals[:cap]
