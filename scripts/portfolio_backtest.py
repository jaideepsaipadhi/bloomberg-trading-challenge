#!/usr/bin/env python3
"""Portfolio-level backtest: the metric the competition actually scores.

Runs the concentrated, trend-riding portfolio over history and reports:
  * a full-history run (total return, vs benchmark, max drawdown), and
  * a walk-forward over competition-length windows (~6 trading weeks),
    summarising how often and by how much it beats the benchmark.

Benchmark: pass --benchmark ACWI (global, ~= the WLS index the competition
scores against) or SPY (US large-cap, a much tougher bar). WLS itself is
Terminal-only; ACWI (iShares MSCI ACWI) is the closest free proxy.

Usage:
  python scripts/portfolio_backtest.py --period 5y --benchmark ACWI
  python scripts/portfolio_backtest.py --period 5y --window 30 --limit 400
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
from trading_bot.portfolio import simulate, walk_forward  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="5y")
    ap.add_argument("--benchmark", default="ACWI", help="ticker proxy for WLS (ACWI or SPY)")
    ap.add_argument("--window", type=int, default=30, help="walk-forward window in trading days (~6wk)")
    ap.add_argument("--step", type=int, default=30)
    ap.add_argument("--limit", type=int, default=None, help="cap universe size (speed)")
    args = ap.parse_args()

    cfg = load_config()
    symbols = load_universe()
    if args.limit:
        symbols = symbols[: args.limit]

    print(f"Fetching {args.period} for {len(symbols)} symbols + {args.benchmark}...", file=sys.stderr)
    symbol_data = data_mod.fetch_universe(symbols, period=args.period)
    bench = data_mod.fetch_one(args.benchmark, period=args.period)
    bench_close = bench["close"] if bench is not None else None
    print(f"Got {len(symbol_data)} symbols; benchmark "
          f"{'ok' if bench_close is not None else 'MISSING'}.", file=sys.stderr)

    full = simulate(symbol_data, cfg.strategy, cfg.portfolio, benchmark_close=bench_close)
    print("\n==== FULL-HISTORY PORTFOLIO RUN ====")
    for k, v in full.summary().items():
        print(f"  {k:>20}: {v}")

    res = walk_forward(symbol_data, cfg.strategy, cfg.portfolio,
                       benchmark_close=bench_close,
                       window_days=args.window, step_days=args.step)
    if not res:
        print("\n(no walk-forward windows)")
        return
    rel = np.array([r.relative_return for r in res])
    tot = np.array([r.total_return for r in res])
    dd = np.array([r.max_drawdown for r in res])
    beat = int((rel > 0).sum())
    print(f"\n==== WALK-FORWARD: {len(res)} windows of ~{args.window} trading days "
          f"vs {args.benchmark} ====")
    print(f"  beat benchmark : {beat}/{len(res)} ({beat/len(res)*100:.0f}%)")
    print(f"  relative return: median {np.median(rel)*100:+.2f}%  mean {rel.mean()*100:+.2f}%")
    print(f"  relative best/worst: {rel.max()*100:+.1f}% / {rel.min()*100:+.1f}%")
    print(f"  top-decile relative (p90): {np.percentile(rel,90)*100:+.1f}%")
    print(f"  abs return median: {np.median(tot)*100:+.2f}%   median maxDD: {np.median(dd)*100:.1f}%")
    print("\nNote: placing well needs the right tail (p90), not the median. ACWI ~= WLS;")
    print("SPY is a much tougher bar (US large-cap outran global equities this era).")


if __name__ == "__main__":
    main()
