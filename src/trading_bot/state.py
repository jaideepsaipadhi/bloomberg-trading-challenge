"""Persisted book state (so posts happen only on change, not every day).

The state is a small JSON file committed to the repo by the scheduled workflow,
recording the last rebalance date and the book held since then. Between
rebalances the book is FIXED — matching the strategy's ~monthly rebalance — so
the team holds it and only gets a short weekly "no change" heartbeat.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, datetime

STATE_PATH = pathlib.Path(__file__).resolve().parents[2] / "state" / "book_state.json"


def load_state(path: pathlib.Path = STATE_PATH) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save_state(data: dict, path: pathlib.Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def needs_rebalance(state: dict | None, today: date, interval_days: int) -> bool:
    """True if there's no book yet, or the holding period has elapsed."""
    if not state or "last_rebalance" not in state:
        return True
    last = datetime.strptime(state["last_rebalance"], "%Y-%m-%d").date()
    return (today - last).days >= interval_days
