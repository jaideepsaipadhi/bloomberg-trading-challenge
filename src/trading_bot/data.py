"""Market-data access.

Uses Yahoo Finance (free) via ``yfinance`` for daily OHLCV. Results are
normalised to lower-case columns [open, high, low, close, volume] with a
DatetimeIndex, which is what the indicators/strategy expect.

The rest of the codebase only depends on that shape — so if you later switch
to a Bloomberg export or another provider, you only change this module.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def _normalise(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if df is None or len(df) == 0:
        return None
    df = df.copy()
    # yfinance sometimes returns a MultiIndex for a single ticker; flatten it.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    needed = ["open", "high", "low", "close", "volume"]
    if not all(c in df.columns for c in needed):
        return None
    df = df[needed].dropna()
    return df if len(df) else None


def fetch_one(symbol: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Fetch a single symbol's OHLCV. Returns None on failure/empty."""
    import yfinance as yf  # imported lazily so tests don't need the network

    try:
        raw = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception:
        return None
    return _normalise(raw)


def _fetch_batch(symbols: list[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
    """Download many tickers in one yfinance call (far faster than one-by-one)."""
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    try:
        raw = yf.download(
            symbols,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=True,
            group_by="ticker",
        )
    except Exception:
        return out

    if raw is None or len(raw) == 0:
        return out

    for sym in symbols:
        try:
            sub = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
        except (KeyError, TypeError):
            continue
        df = _normalise(sub)
        if df is not None:
            out[sym] = df
    return out


def fetch_universe(
    symbols: list[str], period: str = "1y", interval: str = "1d", batch_size: int = 100
) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV for many symbols. Batches the download for speed; falls back
    to per-symbol fetches for any ticker a batch didn't return. Skips failures."""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), batch_size):
        chunk = symbols[i:i + batch_size]
        got = _fetch_batch(chunk, period, interval)
        out.update(got)
        # Retry individually only the ones the batch missed.
        for sym in chunk:
            if sym not in out:
                df = fetch_one(sym, period=period, interval=interval)
                if df is not None:
                    out[sym] = df
    return out


def fetch_regime_series(cfg, period: str = "2y"):
    """Build the market-regime boolean Series for cfg.benchmark_symbol.

    Returns ``(series, None)`` on success or ``(None, reason)`` on failure.
    The series is True on dates where the benchmark closed above its EMA.
    """
    from .indicators import regime_ok_series

    df = fetch_one(cfg.benchmark_symbol, period=period)
    if df is None:
        return None, f"could not fetch benchmark {cfg.benchmark_symbol!r}"
    return regime_ok_series(df["close"], cfg.regime_ema), None
