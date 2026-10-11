import numpy as np
import pandas as pd

from trading_bot.config import StrategyConfig
from trading_bot.alpha import (close_panel, momentum_score, momentum_backtest,
                               momentum_walk_forward, momentum_picks)


def _panel(n=400, k=12, seed=0):
    """A panel where symbols have different, persistent drifts, so momentum
    ranking should favour the strong-drift names."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-02", periods=n, freq="B")
    data = {}
    drifts = np.linspace(-0.05, 0.25, k)  # S0 worst ... S{k-1} best
    for i in range(k):
        close = 100 + drifts[i] * np.arange(n) + rng.normal(0, 0.5, n)
        close = np.maximum(close, 1.0)
        data[f"S{i}"] = pd.DataFrame({"close": close}, index=idx)
    return data


def test_momentum_score_shape_and_values():
    closes = close_panel(_panel())
    sc = momentum_score(closes, lookback=252, skip=21)
    assert sc.shape == closes.shape
    # Strong-drift symbol should outrank weak-drift symbol late in the sample.
    last = sc.iloc[-1]
    assert last["S11"] > last["S0"]


def test_momentum_backtest_beats_weak_equal_mix():
    cfg = StrategyConfig()
    cfg.mom_lookback, cfg.mom_skip, cfg.mom_rebalance_days = 252, 21, 21
    cfg.mom_weight = "equal"  # isolate SELECTION; weighting tested separately
    closes = close_panel(_panel(n=500))
    # benchmark = equal-weight all names (buy & hold)
    bench = (closes / closes.iloc[0]).mean(axis=1)
    res = momentum_backtest(closes, bench, cfg, top_k=3, start=300)
    assert res is not None
    # Holding the top-3 momentum names should beat the equal-weight average.
    assert res.relative_return > 0


def test_momentum_picks_returns_ranked_names():
    cfg = StrategyConfig()
    picks = momentum_picks(_panel(n=400), cfg, top_k=3)
    assert len(picks) == 3
    assert picks[0]["momentum"] >= picks[-1]["momentum"]
    assert all("price" in p for p in picks)


def test_walk_forward_windows():
    cfg = StrategyConfig()
    closes = close_panel(_panel(n=600))
    bench = (closes / closes.iloc[0]).mean(axis=1)
    res = momentum_walk_forward(closes, bench, cfg, top_k=3,
                                window_days=30, step_days=30)
    assert len(res) >= 3


def test_risk_adjusted_momentum_differs_from_raw():
    """vol_window>0 should change the ranking vs raw momentum."""
    closes = close_panel(_panel(n=500, seed=3))
    raw = momentum_score(closes, 252, 21, vol_window=0)
    radj = momentum_score(closes, 252, 21, vol_window=126)
    # Same shape, but values differ where vol is defined.
    assert raw.shape == radj.shape
    last_raw = raw.iloc[-1].dropna()
    last_radj = radj.iloc[-1].dropna()
    assert not np.allclose(last_raw.values, last_radj.values)


def test_book_weights_invvol_caps_and_sums_to_one():
    from trading_bot.alpha import book_weights
    names = ["A", "B", "C", "D"]
    vol = pd.Series({"A": 0.01, "B": 0.02, "C": 0.04, "D": 0.08})
    w = book_weights(names, vol, mode="invvol", cap=0.40)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(v <= 0.40 + 1e-9 for v in w.values())
    # lower-vol name gets more weight than higher-vol name
    assert w["A"] > w["D"]


def test_book_weights_equal():
    from trading_bot.alpha import book_weights
    w = book_weights(["A", "B", "C", "D"], pd.Series(dtype=float), mode="equal")
    assert all(abs(v - 0.25) < 1e-9 for v in w.values())
