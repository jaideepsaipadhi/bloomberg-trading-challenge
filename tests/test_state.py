from datetime import date

from trading_bot.state import needs_rebalance, save_state, load_state


def test_needs_rebalance_when_no_state():
    assert needs_rebalance(None, date(2026, 1, 1), 28) is True
    assert needs_rebalance({}, date(2026, 1, 1), 28) is True


def test_needs_rebalance_after_interval():
    state = {"last_rebalance": "2026-01-01"}
    assert needs_rebalance(state, date(2026, 1, 29), 28) is True   # exactly 28 days later
    assert needs_rebalance(state, date(2026, 2, 10), 28) is True   # past interval


def test_no_rebalance_within_interval():
    state = {"last_rebalance": "2026-01-01"}
    assert needs_rebalance(state, date(2026, 1, 15), 28) is False
    assert needs_rebalance(state, date(2026, 1, 28), 28) is False  # 27 days — not yet


def test_state_roundtrip(tmp_path):
    p = tmp_path / "book_state.json"
    data = {"last_rebalance": "2026-01-01", "book": [{"symbol": "AMD", "shares": 10}]}
    save_state(data, p)
    assert load_state(p) == data
    assert load_state(tmp_path / "missing.json") is None
