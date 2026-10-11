"""Render signals into a human-readable WhatsApp message."""
from __future__ import annotations

from datetime import datetime

from .strategy import Signal


DISCLAIMER = (
    "These are candidate setups for a *simulated* competition, not financial "
    "advice and not guaranteed winners. Always use the stop. Expected win rate "
    "for this style is ~45-60%; the edge is winners > losers over many trades."
)


def format_signal(sig: Signal, rank: int) -> str:
    return (
        f"{rank}. *{sig.symbol}* (LONG)\n"
        f"   Entry ~{sig.entry:,.2f}  |  Stop {sig.stop:,.2f}  |  Target {sig.target:,.2f}\n"
        f"   Risk/Reward 1:{sig.reward_risk:g}  |  Shares {sig.shares:,}  "
        f"(${sig.notional:,.0f} notional, ${sig.dollar_risk:,.0f} at risk)\n"
        f"   RSI {sig.rsi:g}  ROC {sig.roc:g}%  Vol x{sig.vol_ratio:g}  "
        f"ATR {sig.atr:,.2f}  Score {sig.score:.2f}"
    )


def format_message(signals: list[Signal], as_of: str | None = None) -> str:
    stamp = as_of or datetime.now().strftime("%Y-%m-%d")
    header = f"📊 *Momentum + EMA setups* — {stamp}\nHold: 1-2 days.  $100k/trade.\n"

    if not signals:
        body = (
            "No qualifying setups today. That's normal — the screen stays flat "
            "when trend + momentum + volume don't line up. No trade is a position."
        )
        return f"{header}\n{body}\n\n_{DISCLAIMER}_"

    lines = [format_signal(s, i + 1) for i, s in enumerate(signals)]
    body = "\n\n".join(lines)
    return f"{header}\n{body}\n\n_{DISCLAIMER}_"
