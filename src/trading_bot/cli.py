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


def cmd_momentum(args) -> int:
    """Live cross-sectional momentum book: today's top-K strongest names."""
    from .alpha import momentum_picks
    from datetime import datetime

    cfg = load_config()
    symbols = load_universe(args.universe)
    if args.limit:
        symbols = symbols[: args.limit]
    print(f"Fetching data for {len(symbols)} symbols...", file=sys.stderr)
    symbol_data = data_mod.fetch_universe(symbols, period=args.period)
    print(f"Got data for {len(symbol_data)}/{len(symbols)} symbols.", file=sys.stderr)

    picks = momentum_picks(symbol_data, cfg.strategy)
    equity = cfg.portfolio.total_capital
    wscheme = "inverse-vol" if cfg.strategy.mom_weight == "invvol" else "equal"

    stamp = datetime.now().strftime("%Y-%m-%d")
    lines = [f"🏆 *Momentum book* — {stamp}",
             f"Hold the {len(picks)} strongest names (12-1 momentum), {wscheme}-weighted, "
             f"rebalance ~monthly."]
    for i, p in enumerate(picks, 1):
        dollars = p.get("weight", 1.0 / max(1, len(picks))) * equity
        sh = int(dollars // p["price"]) if p["price"] > 0 else 0
        lines.append(f"{i}. *{p['symbol']}*  {p.get('weight', 0)*100:.0f}%  "
                     f"mom {p['momentum']*100:+.0f}%  ~{sh:,} sh @ {p['price']:,.2f}")
    lines.append("\n_Simulated competition; not advice. Momentum is pro-cyclical — "
                 "it gives back hard in market reversals. Rebalance on schedule._")
    message = "\n".join(lines)

    notifier = ConsoleNotifier() if args.dry_run else build_notifier(cfg.whatsapp)
    result = notifier.send(message)
    if args.json:
        print(json.dumps({"picks": picks, "delivery": result}, indent=2))
    return 0


def cmd_telegram_id(args) -> int:
    """List chat ids the bot can see (run after adding the bot to your group
    and sending a message there). Needs TELEGRAM_BOT_TOKEN in the environment."""
    import requests
    cfg = load_config()
    token = cfg.whatsapp.telegram_token
    if not token:
        print("Set TELEGRAM_BOT_TOKEN first (from @BotFather).", file=sys.stderr)
        return 2
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30)
    if not r.ok:
        print(f"getUpdates failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return 1
    seen = {}
    for upd in r.json().get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            seen[chat["id"]] = f"{chat.get('type')} — {chat.get('title') or chat.get('username') or chat.get('first_name','')}"
    if not seen:
        print("No chats yet. Add the bot to your group, SEND A MESSAGE in the "
              "group, then re-run this. (Telegram only shows chats with recent activity.)")
        return 0
    print("Chats the bot can see (use the id in TELEGRAM_CHAT_IDS):")
    for cid, desc in seen.items():
        print(f"  {cid}   [{desc}]")
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

    m = sub.add_parser("momentum", help="Post today's cross-sectional momentum book")
    _add_common(m)
    m.add_argument("--dry-run", action="store_true", help="Force console output (no send)")
    m.add_argument("--json", action="store_true", help="Also print machine-readable JSON")
    m.set_defaults(func=cmd_momentum)

    t = sub.add_parser("telegram-id", help="Discover Telegram chat/group ids for the bot")
    t.set_defaults(func=cmd_telegram_id)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
