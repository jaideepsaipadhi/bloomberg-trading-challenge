import numpy as np
import pandas as pd

from trading_bot import indicators as ind


def test_ema_tracks_constant_series():
    s = pd.Series([5.0] * 50)
    assert np.isclose(ind.ema(s, 10).iloc[-1], 5.0)


def test_roc_simple():
    s = pd.Series([100.0, 110.0])
    out = ind.roc(s, 1)
    assert np.isclose(out.iloc[-1], 10.0)


def test_rsi_all_gains_is_100():
    s = pd.Series(np.arange(1, 60, dtype=float))  # strictly increasing
    r = ind.rsi(s, 14)
    assert r.iloc[-1] == 100.0


def test_rsi_bounded_0_100():
    rng = np.random.default_rng(0)
    s = pd.Series(100 + np.cumsum(rng.normal(0, 1, 500)))
    r = ind.rsi(s, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_atr_positive():
    rng = np.random.default_rng(1)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, 300)))
    high = close + 1.0
    low = close - 1.0
    a = ind.atr(high, low, close, 14).dropna()
    assert (a > 0).all()
