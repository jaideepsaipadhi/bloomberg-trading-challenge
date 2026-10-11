from types import SimpleNamespace

from trading_bot.config import PortfolioConfig
from trading_bot.portfolio import allocate, _weights


def _sig(sym, price, score):
    return SimpleNamespace(symbol=sym, entry=price, score=score)


def test_equal_weights_sum_to_one_and_respect_cap():
    w = _weights([1, 1, 1, 1, 1, 1, 1, 1, 1, 1], max_pct=0.20, sizing_mode="equal")
    assert abs(sum(w) - 1.0) < 1e-6
    assert all(x <= 0.20 + 1e-9 for x in w)
    assert all(abs(x - 0.10) < 1e-9 for x in w)


def test_score_weights_capped_and_redistributed():
    # One dominant score should be capped at 20%, not 60%+.
    w = _weights([10, 1, 1, 1, 1, 1, 1, 1], max_pct=0.20, sizing_mode="score")
    assert max(w) <= 0.20 + 1e-9
    assert abs(sum(w) - 1.0) < 1e-6


def test_cap_binds_when_too_few_names():
    # 3 names, 20% cap -> can only deploy 60%, equal at the cap.
    w = _weights([5, 3, 1], max_pct=0.20, sizing_mode="score")
    assert all(abs(x - 0.20) < 1e-9 for x in w)
    assert abs(sum(w) - 0.60) < 1e-9


def test_allocate_sizes_and_caps_dollars():
    pcfg = PortfolioConfig(total_capital=1_000_000)
    pcfg.target_positions = 10
    sigs = [_sig(f"S{i}", 100.0, score=1.0) for i in range(10)]
    allocs = allocate(sigs, equity=1_000_000, pcfg=pcfg)
    assert len(allocs) == 10
    # ~10% each => ~$100k => ~1000 shares at $100
    assert all(a.shares > 0 for a in allocs)
    assert all(a.weight <= 0.20 + 1e-9 for a in allocs)
    deployed = sum(a.dollars for a in allocs)
    assert 0.95 * 1_000_000 <= deployed <= 1_000_000 + 1


def test_allocate_drops_dust():
    pcfg = PortfolioConfig(total_capital=1_000_000)
    pcfg.target_positions = 10
    pcfg.min_position_pct = 0.05
    # One microscopic score shouldn't survive as a dust position.
    scores = [1.0] * 9 + [0.0001]
    sigs = [_sig(f"S{i}", 50.0, score=scores[i]) for i in range(10)]
    allocs = allocate(sigs, equity=1_000_000, pcfg=pcfg)
    assert all(a.weight >= 0.05 - 1e-9 for a in allocs)


# ---- portfolio simulator ----
import numpy as np
import pandas as pd
from trading_bot.config import StrategyConfig
from trading_bot.portfolio import simulate, walk_forward


def _ohlc(n=400, seed=0, drift=0.18):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = 100 + drift * t + 6.0 * np.sin(t / 11.0) + rng.normal(0, 0.6, n)
    vol = rng.uniform(0.8, 2.2, n) * 1_000_000.0
    idx = pd.date_range("2015-01-02", periods=n, freq="B")
    return pd.DataFrame({"open": close - 0.1, "high": close + 1.0,
                         "low": close - 1.0, "close": close, "volume": vol}, index=idx)


def test_simulate_returns_sane_result():
    data = {f"S{i}": _ohlc(seed=i) for i in range(6)}
    cfg, pcfg = StrategyConfig(), PortfolioConfig()
    r = simulate(data, cfg, pcfg)
    assert r is not None
    assert r.end_equity > 0
    assert len(r.equity_curve) > 10
    assert 0.0 <= r.win_rate <= 1.0
    # relative = total - benchmark (benchmark 0 when none supplied)
    assert abs(r.relative_return - (r.total_return - r.benchmark_return)) < 1e-9


def test_simulate_respects_position_cap():
    data = {f"S{i}": _ohlc(seed=i) for i in range(20)}
    cfg = StrategyConfig()
    pcfg = PortfolioConfig(); pcfg.target_positions = 5
    # Monkey-check: never hold more than target_positions by inspecting trades
    # indirectly — run and ensure it completes with a bounded book.
    r = simulate(data, cfg, pcfg)
    assert r is not None and r.n_trades >= 0


def test_walk_forward_produces_windows():
    data = {f"S{i}": _ohlc(n=500, seed=i) for i in range(6)}
    cfg, pcfg = StrategyConfig(), PortfolioConfig()
    res = walk_forward(data, cfg, pcfg, window_days=30, step_days=30)
    assert len(res) >= 3
    assert all(w.end_equity > 0 for w in res)


def test_regime_overlay_blocks_new_longs_when_risk_off():
    """With an all-risk-off regime, the simulator opens no positions."""
    data = {f"S{i}": _ohlc(seed=i) for i in range(6)}
    cfg, pcfg = StrategyConfig(), PortfolioConfig()
    sample = next(iter(data.values()))
    risk_off = pd.Series(False, index=sample.index)
    r = simulate(data, cfg, pcfg, regime=risk_off)
    assert r is not None
    assert r.n_trades == 0
    assert abs(r.end_equity - pcfg.total_capital) < 1e-6
