"""Technical indicators used by the strategy.

Pure functions over pandas Series/DataFrames. No network, no state — so they
are trivial to unit-test with synthetic data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def roc(series: pd.Series, lookback: int) -> pd.Series:
    """Rate of change (momentum), in percent, over ``lookback`` bars."""
    return (series / series.shift(lookback) - 1.0) * 100.0


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder's smoothing == EMA with alpha = 1/period
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When there have been no losses at all, RSI is defined as 100.
    out = out.where(avg_loss != 0.0, 100.0)
    return out


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range (Wilder's smoothing)."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index (Wilder) — trend STRENGTH, regardless of
    direction. High ADX (>~20-25) = a real trend; low ADX = chop to avoid."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)

    tr = true_range(high, low, close)
    alpha = 1.0 / period
    atr_ = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False).mean() / atr_.replace(0.0, np.nan)
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False).mean() / atr_.replace(0.0, np.nan)

    di_sum = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    return dx.ewm(alpha=alpha, adjust=False).mean()


def regime_ok_series(benchmark_close: pd.Series, ema_span: int) -> pd.Series:
    """Boolean Series: is the benchmark above its own EMA (risk-on uptrend)?"""
    return benchmark_close > ema(benchmark_close, ema_span)


def add_indicators(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Return a copy of ``df`` with all strategy indicators attached.

    ``df`` must have columns: open, high, low, close, volume (lower-case).
    ``cfg`` is a StrategyConfig.
    """
    out = df.copy()
    close = out["close"]

    out["ema_fast"] = ema(close, cfg.ema_fast)
    out["ema_mid"] = ema(close, cfg.ema_mid)
    out["ema_slow"] = ema(close, cfg.ema_slow)
    out["roc"] = roc(close, cfg.roc_lookback)
    out["rsi"] = rsi(close, cfg.rsi_period)
    out["atr"] = atr(out["high"], out["low"], close, cfg.atr_period)
    out["adx"] = adx(out["high"], out["low"], close, cfg.adx_period)
    out["vol_avg"] = out["volume"].rolling(cfg.volume_avg_period).mean()
    out["vol_ratio"] = out["volume"] / out["vol_avg"]
    # How far price has extended above the fast EMA, measured in ATRs.
    out["atr_extension"] = (close - out["ema_fast"]) / out["atr"]
    # Slope of the slow EMA (is the longer trend actually rising?), normalised
    # to percent-per-bar so it's comparable across price levels.
    out["ema_slow_slope"] = out["ema_slow"].pct_change() * 100.0
    return out
