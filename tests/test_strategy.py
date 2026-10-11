import numpy as np
import pandas as pd

from trading_bot.config import StrategyConfig, PortfolioConfig
from trading_bot.strategy import build_signal, scan
from trading_bot.backtest import backtest_symbol, BacktestResult


def _uptrend_df(seed=0):
    """A realistic setup on the FINAL bar that clears the (stricter) default
    screen: an established uptrend (EMA stack), a pullback that cools RSI into
    the 55-70 sweet spot, a 3-bar surge that lifts ROC above its floor, an
    oscillating consolidation (keeps RSI moderate), and elevated recent volume.
    """
    rng = np.random.default_rng(seed)
    base = 100 + 0.12 * np.arange(180) + rng.normal(0, 0.15, 180)
    dip = np.array([base[-1] - 0.6 * (i + 1) for i in range(5)])
    surge = np.array([dip[-1] + 1.7 * (i + 1) for i in range(3)])
    deltas = [0.3, -0.6, 0.4, -0.7, 0.3, -0.4]  # net ~flat; mixes down bars
    cons = [surge[-1] + deltas[0]]
    for dv in deltas[1:]:
        cons.append(cons[-1] + dv)
    close = np.concatenate([base, dip, surge, np.array(cons)])
    n = len(close)
    vol = np.full(n, 1_000_000.0)
    vol[-9:] = np.linspace(1.3, 1.6, 9) * 1_000_000.0
    idx = pd.date_range("2021-01-04", periods=n, freq="B")
    return pd.DataFrame(
        {"open": close - 0.1, "high": close + 0.8, "low": close - 0.8,
         "close": close, "volume": vol},
        index=idx,
    )


def _trending_df(n=500, seed=0):
    """A long drift+swing series with variable volume, so the screen fires
    repeatedly over history (used by the backtest test)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = 100 + 0.18 * t + 6.0 * np.sin(t / 11.0) + rng.normal(0, 0.6, n)
    vol = rng.uniform(0.8, 2.2, n) * 1_000_000.0
    idx = pd.date_range("2015-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"open": close - 0.1, "high": close + 1.0, "low": close - 1.0,
         "close": close, "volume": vol},
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
    # Signal fields are rounded to 4dp, so allow a small tolerance.
    assert np.isclose(sig.reward_per_share / sig.risk_per_share, cfg.reward_risk_ratio, atol=1e-3)


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
    trades = backtest_symbol("TEST", _trending_df(n=500), cfg)
    res = BacktestResult(trades=trades)
    assert res.n >= 1
    # Win rate is a real fraction, never the fantasy 99-100%.
    assert 0.0 <= res.win_rate <= 1.0
    # Every trade's R is finite.
    assert all(np.isfinite(t.r_multiple) for t in trades)


def test_optional_filters_are_stricter():
    """Enabling an optional filter should never ADD trades vs baseline."""
    base = StrategyConfig()
    stricter = StrategyConfig()
    stricter.use_adx_filter = True
    stricter.adx_min = 25
    df = _trending_df(n=500)
    n_base = len(backtest_symbol("TEST", df, base))
    n_strict = len(backtest_symbol("TEST", df, stricter))
    assert n_strict <= n_base


def test_trend_exit_lets_winners_run_past_swing_cap():
    """In a sustained uptrend, trend mode should capture more than the swing
    target cap (1.5R), i.e. produce at least one trade with R clearly > 1.5."""
    swing = StrategyConfig(); swing.exit_mode = "swing"
    trend = StrategyConfig(); trend.exit_mode = "trend"; trend.use_ema_trend_exit = False
    df = _trending_df(n=500, seed=3)
    swing_r = [t.r_multiple for t in backtest_symbol("T", df, swing)]
    trend_r = [t.r_multiple for t in backtest_symbol("T", df, trend)]
    assert swing_r and trend_r
    # Swing caps wins at the reward/risk ratio; trend has no such cap.
    assert max(swing_r) <= swing.reward_risk_ratio + 0.05
    assert max(trend_r) > swing.reward_risk_ratio


def test_trend_signal_has_trailing_exit_plan():
    cfg = StrategyConfig(); cfg.exit_mode = "trend"
    sig = build_signal("TEST", _uptrend_df(), cfg, PortfolioConfig())
    assert sig is not None
    assert "TREND" in sig.exit_plan and "trail" in sig.exit_plan.lower()


def test_regime_filter_blocks_when_risk_off():
    """With the regime filter on and benchmark risk-off, no signal fires."""
    cfg = StrategyConfig()
    cfg.use_regime_filter = True
    port = PortfolioConfig()
    sig = build_signal("TEST", _uptrend_df(), cfg, port, regime_ok=False)
    assert sig is None
    # Same setup, risk-on -> signal returns.
    sig2 = build_signal("TEST", _uptrend_df(), cfg, port, regime_ok=True)
    assert sig2 is not None
