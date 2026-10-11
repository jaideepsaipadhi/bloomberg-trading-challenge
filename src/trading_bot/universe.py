"""Load the tradeable universe (the competition's allowed symbols, "WLS").

The universe is just a newline/CSV list of tickers in ``config/universe.csv``.
Populate it with the exact symbols the Bloomberg Trading Challenge allows your
team to trade. Lines starting with ``#`` are comments; a header row named
``symbol``/``ticker`` is ignored.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "universe.csv"


def load_universe(path: str | os.PathLike | None = None) -> list[str]:
    p = Path(path) if path else _DEFAULT_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"Universe file not found at {p}. Create it with one ticker per line "
            f"(see config/universe.csv)."
        )

    symbols: list[str] = []
    with p.open(newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            cell = row[0].strip()
            if not cell or cell.startswith("#"):
                continue
            if cell.lower() in {"symbol", "ticker", "symbols", "tickers"}:
                continue
            symbols.append(cell.upper())

    # de-dupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out
