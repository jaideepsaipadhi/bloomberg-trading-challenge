import numpy as np
import pandas as pd

from trading_bot.config import StrategyConfig, PortfolioConfig
from trading_bot.strategy import build_signal, scan
from trading_bot.backtest import backtest_symbol, BacktestResult


def _uptrend_df(n=201, start=100.0, drift=0.35, amp=3.0, seed=0):
    """A realistic uptrend: upward drift WITH periodic pullbacks, so RSI sits
    in a constructive band (not the parabolic RSI~100 of a monotonic line).
    n=201 lands the final bar mid-upswing, which triggers the long setup."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = start + drift * t + amp * np.sin(t / 9.0) + rng.normal(0, 0.4, n)
    idx = pd.date_range("2022-06-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": close - 0.1, "high": close + 1.2, "low": close - 1.2,
         "close": close, "volume": np.full(n, 1_200_000.0)},
        index=idx,
    )


def _downtrend_df(n=201, start=300.0, drift=0.35, amp=3.0, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = start - drift * t + amp * np.sin(t / 9.0) + rng.normal(0, 0.4, n)
    idx = pd.date_range("2022-06-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": close + 0.1, "high": close + 1.2, "low": close - 1.2,
         "close": close, "volume": np.full(n, 1_200_000.0)},
        index=idx,
    )


def test_uptrend_produces_long_signal():
    cfg, port = StrategyConfig(), PortfolioConfig()
    sig = build_signal("TEST", _uptrend_df(), cfg, port)
    assert sig is not None
    assert sig.direction == "long"
    assert sig.stop < sig.entry < sig.target
    assert sig.shares > 0
    # Fixed $100k notional sizing.
    assert abs(sig.notional - port.notional_per_trade) <= sig.entry


def test_downtrend_produces_no_signal():
    cfg, port = StrategyConfig(), PortfolioConfig()
    assert build_signal("TEST", _downtrend_df(), cfg, port) is None


def test_reward_risk_matches_config():
    cfg, port = StrategyConfig(), PortfolioConfig()
    sig = build_signal("TEST", _uptrend_df(), cfg, port)
    assert sig is not None
    assert np.isclose(sig.reward_per_share / sig.risk_per_share, cfg.reward_risk_ratio, atol=1e-6)


def test_scan_respects_slot_cap():
    cfg = StrategyConfig()
    cfg.max_signals = 100
    port = PortfolioConfig(total_capital=300_000, notional_per_trade=100_000)  # 3 slots
    universe = {f"S{i}": _uptrend_df(seed=i) for i in range(10)}
    sigs = scan(universe, cfg, port)
    assert len(sigs) <= 3


def test_scan_sorted_by_score_desc():
    cfg, port = StrategyConfig(), PortfolioConfig()
    universe = {f"S{i}": _uptrend_df(seed=i) for i in range(6)}
    sigs = scan(universe, cfg, port)
    scores = [s.score for s in sigs]
    assert scores == sorted(scores, reverse=True)


def test_backtest_produces_trades_and_sane_stats():
    cfg = StrategyConfig()
    trades = backtest_symbol("TEST", _uptrend_df(n=400), cfg)
    res = BacktestResult(trades=trades)
    assert res.n >= 1
    # Win rate is a real fraction, never the fantasy 99-100%.
    assert 0.0 <= res.win_rate <= 1.0
    # Every trade's R is finite.
    assert all(np.isfinite(t.r_multiple) for t in trades)
