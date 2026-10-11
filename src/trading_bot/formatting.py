"""Render signals into a human-readable WhatsApp message."""
from __future__ import annotations

from datetime import datetime

from .strategy import Signal


DISCLAIMER = (
    "Candidate setups for a *simulated* competition - not financial advice, not "
    "guaranteed winners. Always use the stop. This trend-riding style wins only "
    "~40% of the time ON PURPOSE: a few big winners outweigh many small losers. "
    "Expect losing trades; the edge is in the right tail over many trades."
)


def format_signal(sig: Signal, rank: int) -> str:
    plan = sig.exit_plan or (
        f"target {sig.target:,.2f} (1:{sig.reward_risk:g}), stop {sig.stop:,.2f}"
    )
    return (
        f"{rank}. *{sig.symbol}* (LONG)\n"
        f"   Entry ~{sig.entry:,.2f}  |  Shares {sig.shares:,}  "
        f"(${sig.notional:,.0f} notional, ${sig.dollar_risk:,.0f} at risk)\n"
        f"   Plan: {plan}\n"
        f"   RSI {sig.rsi:g}  ROC {sig.roc:g}%  Vol x{sig.vol_ratio:g}  "
        f"ATR {sig.atr:,.2f}  Score {sig.score:.2f}"
    )


def format_momentum_book(picks: list[dict], equity: float, weight_scheme: str,
                         as_of: str | None = None) -> str:
    """Render the momentum book as a clean, aligned monospace table (reads well
    on phones in Telegram/Discord)."""
    from datetime import datetime
    stamp = as_of or datetime.now().strftime("%a %b %d")
    wtxt = "inverse-vol weighted" if weight_scheme == "invvol" else "equal weighted"

    rows = []
    deployed = 0.0
    for p in picks:
        w = p.get("weight") or (1.0 / max(1, len(picks)))
        price = p.get("price") or 0.0
        sh = int((w * equity) // price) if price > 0 else 0
        val = sh * price
        deployed += val
        rows.append((p["symbol"], sh, price, w, p.get("momentum", 0.0)))

    hdr = f"{'TICKER':<7}{'SHARES':>7}{'PRICE':>10}{'WT':>6}"
    body = [hdr, "-" * len(hdr)]
    for sym, sh, price, w, _m in rows:
        body.append(f"{sym:<7}{sh:>7,}{('$' + format(price, ',.2f')):>10}{w * 100:>5.1f}%")
    table = "```\n" + "\n".join(body) + "\n```"

    return "\n".join([
        f"🏆 *Momentum Book* — {stamp}",
        f"_Top {len(picks)} by 12-1 momentum · {wtxt} · ${deployed:,.0f} of "
        f"${equity:,.0f} deployed_",
        "",
        table,
        "📋 Hold these names; *sell* anything no longer on the list. "
        "Rebalances ~monthly.",
        "⚠️ _Simulated competition, not advice. This style wins <half the time "
        "by design — a few big winners carry it. Rebalance on schedule._",
    ])


def format_message(signals: list[Signal], as_of: str | None = None,
                   allocations=None) -> str:
    stamp = as_of or datetime.now().strftime("%Y-%m-%d")
    header = (f"📊 *Momentum + EMA setups* — {stamp}\n"
              f"Ride winners (trail stop), cut losers fast.\n")

    if not signals:
        body = (
            "No qualifying setups today. That's normal — the screen stays flat "
            "when trend + momentum + volume don't line up. No trade is a position."
        )
        return f"{header}\n{body}\n\n_{DISCLAIMER}_"

    lines = [format_signal(s, i + 1) for i, s in enumerate(signals)]
    body = "\n\n".join(lines)

    book = ""
    if allocations:
        picks = "  ".join(f"{a.symbol} {a.weight*100:.0f}%" for a in allocations)
        deployed = sum(a.dollars for a in allocations)
        book = (f"\n\n*Suggested concentrated book* (conviction-weighted, "
                f"≤20%/name, ~${deployed:,.0f} deployed):\n{picks}")

    return f"{header}\n{body}{book}\n\n_{DISCLAIMER}_"
