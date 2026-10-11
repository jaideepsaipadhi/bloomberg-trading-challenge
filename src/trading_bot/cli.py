"""Command-line entrypoint.

Usage:
    python -m trading_bot.cli signals        # scan universe, post today's setups
    python -m trading_bot.cli backtest       # replay history, print honest stats
    python -m trading_bot.cli signals --dry-run   # force console output

Run `python -m trading_bot.cli --help` for all options.
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .universe import load_universe
from . import data as data_mod
from .strategy import scan
from .backtest import backtest
from .portfolio import allocate
from .formatting import format_message
from .whatsapp import build_notifier, ConsoleNotifier


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--universe", default=None, help="Path to universe CSV (default config/universe.csv)")
    p.add_argument("--period", default="1y", help="History window for data fetch (e.g. 6mo, 1y, 2y)")
    p.add_argument("--limit", type=int, default=None, help="Only scan the first N symbols (debug)")


def cmd_signals(args) -> int:
    cfg = load_config()
    symbols = load_universe(args.universe)
    if args.limit:
        symbols = symbols[: args.limit]
    if not symbols:
        print("Universe is empty — add tickers to config/universe.csv.", file=sys.stderr)
        return 2

    print(f"Fetching data for {len(symbols)} symbols...", file=sys.stderr)
    symbol_data = data_mod.fetch_universe(symbols, period=args.period)
    print(f"Got data for {len(symbol_data)}/{len(symbols)} symbols.", file=sys.stderr)

    regime_ok = True
    if cfg.strategy.use_regime_filter:
        series, reason = data_mod.fetch_regime_series(cfg.strategy, period="2y")
        if series is None:
            print(f"WARNING: regime filter on but {reason}; treating as risk-off.",
                  file=sys.stderr)
            regime_ok = False
        else:
            regime_ok = bool(series.iloc[-1])
            print(f"Market regime ({cfg.strategy.benchmark_symbol} vs EMA"
                  f"{cfg.strategy.regime_ema}): {'RISK-ON' if regime_ok else 'RISK-OFF'}.",
                  file=sys.stderr)

    signals = scan(symbol_data, cfg.strategy, cfg.portfolio, regime_ok=regime_ok)
    allocations = allocate(signals, cfg.portfolio.total_capital, cfg.portfolio)
    message = format_message(signals, allocations=allocations)

    notifier = ConsoleNotifier() if args.dry_run else build_notifier(cfg.whatsapp)
    result = notifier.send(message)

    if args.json:
        print(json.dumps({
            "signals": [s.to_dict() for s in signals],
            "allocations": [a.__dict__ for a in allocations],
            "delivery": result,
        }, indent=2))
    return 0


def cmd_backtest(args) -> int:
    cfg = load_config()
    symbols = load_universe(args.universe)
    if args.limit:
        symbols = symbols[: args.limit]
    if not symbols:
        print("Universe is empty — add tickers to config/universe.csv.", file=sys.stderr)
        return 2

    print(f"Fetching {args.period} of data for {len(symbols)} symbols...", file=sys.stderr)
    symbol_data = data_mod.fetch_universe(symbols, period=args.period)
    print(f"Got data for {len(symbol_data)}/{len(symbols)} symbols.", file=sys.stderr)

    regime = None
    if cfg.strategy.use_regime_filter:
        regime, reason = data_mod.fetch_regime_series(cfg.strategy, period=args.period)
        if regime is None:
            print(f"WARNING: regime filter on but {reason}; proceeding without it.",
                  file=sys.stderr)

    result = backtest(symbol_data, cfg.strategy, regime=regime)
    summary = result.summary()

    print("\n==== BACKTEST (honest stats) ====")
    for k, v in summary.items():
        print(f"  {k:>16}: {v}")
    print("\nReminder: expectancy_r > 0 with profit_factor > 1 is the edge.")
    print("A win_rate near 1.0 would signal an over-fit / no-stop setup, not skill.\n")

    if args.json:
        print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading_bot", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("signals", help="Scan universe and post today's setups")
    _add_common(s)
    s.add_argument("--dry-run", action="store_true", help="Force console output (no WhatsApp send)")
    s.add_argument("--json", action="store_true", help="Also print machine-readable JSON")
    s.set_defaults(func=cmd_signals)

    b = sub.add_parser("backtest", help="Replay history and print honest performance stats")
    _add_common(b)
    b.add_argument("--json", action="store_true", help="Also print machine-readable JSON")
    b.set_defaults(func=cmd_backtest)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
