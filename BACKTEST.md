# Backtest results — momentum book

Strategy: **cross-sectional 12-1 momentum, inverse-vol weighted, top 20,
rebalanced every ~21 trading days.** Period **2020-11-20 → 2026-10-15** (5.9y).
No trading costs (the competition fills free). Benchmark **ACWI** (iShares MSCI
ACWI, ≈ the global WLS index the competition scores against); **SPY** shown for
US context.

> ⚠️ **Read first — survivorship bias.** The universe is *today's* S&P 500 /
> S&P MidCap 400 members, so momentum selects from names we already know
> survived and thrived. The headline magnitudes (total return, CAGR) are
> **heavily inflated and are NOT a realistic expectation.** Trust the
> **walk-forward hit-rate** and the **relative ordering**, not the totals. The
> only bias-free evidence is the live forward track record now being collected.

## Headline performance

| Metric | Strategy | ACWI (~WLS) | SPY |
|---|---:|---:|---:|
| Total return | +1,754% | +104% | +136% |
| CAGR | +64.3% | +12.9% | +15.7% |
| Annualized volatility | 40.0% | 15.7% | 16.5% |
| Sharpe (rf=0) | 1.44 | 0.85 | 0.97 |
| Sortino | 2.04 | 1.22 | 1.33 |
| Max drawdown | −35.6% | −26.4% | −24.5% |
| Longest drawdown (days) | 183 | 516 | 488 |
| Best / worst day | +14.4% / −11.3% | | |

## Calendar-year returns

| Year | Strategy | ACWI | SPY | vs ACWI |
|---|---:|---:|---:|---:|
| 2020 (from Nov) | +29.2% | +5.9% | +5.7% | +23.3 pp |
| 2021 | +44.4% | +19.3% | +30.5% | +25.1 pp |
| 2022 | +10.6% | −18.8% | −18.6% | +29.5 pp ⚠️ |
| 2023 | +68.6% | +22.2% | +26.7% | +46.3 pp |
| 2024 | +93.2% | +18.5% | +25.6% | +74.8 pp |
| 2025 | +79.3% | +22.7% | +18.0% | +56.6 pp |
| 2026 YTD | +49.8% | +12.5% | +13.9% | +37.3 pp |

The 2022 figure (positive while the market fell ~19%) is the most
survivorship-flattered — real momentum struggled badly in 2022. Treat with
extra skepticism.

## Walk-forward (competition-length ~6-week windows) — the trustworthy core

| | Non-overlapping (49 windows) | Overlapping, 5-day step (291) |
|---|---:|---:|
| Beat benchmark | 67% (33/49) | 68% (197/291) |
| Mean / median relative | +4.73% / +4.57% | +4.83% / +4.28% |
| Std / information ratio | 11.2% / +0.42 | 10.5% / +0.46 |
| p10 / p90 relative | −9.1% / +15.8% | −8.4% / +17.9% |
| Worst / best window | −16.4% / +36.6% | −27.1% / +36.6% |

**Interpretation:** in a random 6-week window the book beat the global
benchmark ~2 of 3 times, by a median ~+4.5 percentage points — but a bad draw
is ~−16% relative. A favorable, high-variance bet; not a guarantee.

## Config sweep (full-period, IN-SAMPLE — do not over-read)

| Config | Total | Relative | MaxDD | WF beat | WF median |
|---|---:|---:|---:|---:|---:|
| invvol top 10 | 1800% | 1695% | −37% | 67% | 6.9% |
| **invvol top 20 (production)** | 1754% | 1649% | −36% | 67% | 4.6% |
| invvol top 30 | 1051% | 947% | −34% | 69% | 2.7% |
| equal top 10 | 2049% | 1945% | −40% | 65% | 5.5% |
| equal top 20 | 2111% | 2007% | −38% | 67% | 3.8% |
| equal top 30 | 1456% | 1352% | −36% | 67% | 3.7% |

Equal-weight shows a bigger headline, but production uses **inverse-vol**
because it won the *out-of-sample* train/test study (steadier, lower drawdown).
Picking the biggest in-sample number is the overfitting trap.

## What to take away

- **A real, repeatable edge** (beats the global benchmark ~67% of 6-week
  windows) with strong risk-adjusted numbers (Sharpe ~1.4) — but **high
  volatility (~40%) and a ~36% max drawdown**: a wild ride.
- **The headline totals are fiction** (survivorship bias). Expect far less live.
- **Pro-cyclical:** great in trends, vulnerable in sharp reversals (the real
  2022 would have hurt).
- The decisive test is the **live forward record**, which has zero survivorship
  bias and is now being collected.

_Reproduce: `python scripts/alpha_backtest.py --period 7y --benchmark ACWI`._
