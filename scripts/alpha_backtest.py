#!/usr/bin/env python3
"""Backtest the cross-sectional momentum alpha (the strongest explored).

Holds an equal-weight top-K book of the highest trailing-return names,
rebalanced monthly, measured vs an ACWI (~WLS) benchmark, with a train/test
walk-forward over ~6-week (competition-length) windows.

Usage:
  python scripts/alpha_backtest.py --period 6y --benchmark ACWI --top-k 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trading_bot.config import load_config          # noqa: E402
from trading_bot.universe import load_universe       # noqa: E402
from trading_bot import data as data_mod             # noqa: E402
from trading_bot.alpha import close_panel, momentum_backtest  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="6y")
    ap.add_argument("--benchmark", default="ACWI")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--window", type=int, default=30)
    args = ap.parse_args()

    cfg = load_config().strategy
    top_k = args.top_k or cfg.mom_top_k
    symbols = load_universe()
    print(f"Fetching {args.period} for {len(symbols)} symbols + {args.benchmark}...", file=sys.stderr)
    symbol_data = data_mod.fetch_universe(symbols, period=args.period)
    b = data_mod.fetch_one(args.benchmark, period=args.period)
    bench = b["close"] if b is not None else None

    closes = close_panel(symbol_data)
    n = len(closes.index)
    warmup = cfg.mom_lookback + cfg.mom_skip + 5
    split = warmup + int((n - warmup) * 0.60)

    full = momentum_backtest(closes, bench, cfg, top_k=top_k, start=warmup)
    print(f"\n==== CROSS-SECTIONAL MOMENTUM (top {top_k}, rebalance {cfg.mom_rebalance_days}d, "
          f"lookback {cfg.mom_lookback}/skip {cfg.mom_skip}) ====")
    for k, v in full.summary().items():
        print(f"  {k:>20}: {v}")
    print("  NOTE: total return is inflated by survivorship bias; trust the "
          "walk-forward hit-rate below.")

    def windows(a, bnd):
        rel = []
        i = a
        while i + args.window <= bnd:
            rel.append(momentum_backtest(closes, bench, cfg, top_k, start=i,
                                         end=i + args.window).relative_return)
            i += args.window
        rel = np.array(rel)
        return (rel > 0).mean(), np.median(rel), len(rel)

    for label, (a, bnd) in {"TRAIN": (warmup, split), "TEST (held-out)": (split, n)}.items():
        beat, med, nw = windows(a, bnd)
        print(f"  {label:<16}: beat {beat*100:4.0f}%  median_rel {med*100:+.2f}%  ({nw} windows)")


if __name__ == "__main__":
    main()
