# Bloomberg Trading Challenge — Momentum + EMA Signal Bot

A **signals-only** assistant for the (simulated) Bloomberg Global Trading
Challenge. It scans the competition's allowed universe for short-term
(1–2 day hold) long setups that combine an **EMA trend stack** with
**momentum confirmation**, sizes them for a **$1M paper portfolio**
($100k per trade), and posts the ranked setups to WhatsApp.

Humans review the setups and enter the trades in the Bloomberg terminal.
**The bot does not place trades.**

---

## ⚠️ Read this first: about "99% win rate"

You asked for "solid, 99% win rate picks." That number is not achievable by
any EMA/momentum strategy — or any strategy — on 1–2 day holds. This project
is built to be **honest** about that, because a bot that *claims* near-certain
wins to a group of people is how people lose money.

What a good short-term momentum system actually looks like:

| Metric | Realistic target | Fantasy |
|---|---|---|
| Win rate | **~45–60%** | 99% |
| How it profits | winners **bigger** than losers (positive expectancy) | "always right" |
| Risk control | hard stop on every trade | "it'll come back" |

The honest backtester in this repo reports the **true** win rate and
expectancy. After tuning (see "Tuning the strategy" below), a 5-year large-cap
sample shows roughly **54% win rate** with a small **positive** expectancy and
a profit factor near 1.3 — a modest, real edge. Not 99%. **The edge is small
and must be validated on your universe, never assumed.**

A key finding from the built-in sensitivity probe: as you raise the profit
target, the win rate *falls* (e.g. a 2.5:1 reward/risk target won only ~47% of
the time). That inverse relationship is the mathematical reason 99% is
impossible — you can only get a very high hit rate with a microscopic target,
which destroys expectancy and hides catastrophic tail risk.

**Use this as a disciplined screener and a backtesting lab, not a crystal ball.**

---

## The strategy

A candidate **long** setup fires on a daily bar when ALL of these hold:

1. **EMA trend stack** — `EMA(8) > EMA(21) > EMA(50)` and price above `EMA(21)`
   (trade with the short-term uptrend).
2. **Momentum** — positive rate-of-change over 10 bars, and RSI(14) in a
   constructive **50–75** band (strong, but not an overbought blow-off).
3. **Participation** — volume at/above its 20-day average.
4. **Not overextended** — price no more than 3×ATR above the fast EMA
   (don't chase parabolic moves).

Risk management, defined **before** entry:

- **Stop:** `entry − 1.5 × ATR(14)`.
- **Exit — two modes (`EXIT_MODE`):**
  - **`trend` (default):** no fixed target. Ride the move with a **3×ATR
    trailing stop** that ratchets up under the highs, exit on a close below the
    mid EMA or after `MAX_TREND_DAYS` (30). Winners can run to many multiples of
    risk. This is the **"place well" profile** — see below.
  - **`swing`:** fixed `1.5:1` target + ATR stop + a `MAX_HOLD_DAYS` (2) time
    stop. Higher win rate, but every win is capped at 1.5R.
- **Sizing:** **$100k notional** per trade → `shares = floor(100000 / entry)`.
  With $1M that's up to **10 concurrent positions** (10% each, within the 20%
  rule). When more than 10 setups qualify, the strongest-scoring are kept.
  *(Conviction-weighted concentration is a planned next step — see below.)*

All thresholds live in `src/trading_bot/config.py` and are overridable via env
vars / `.env` — see `.env.example`.

---

## Setup

```bash
pip install -e ".[dev]"      # or: pip install -r requirements.txt
cp .env.example .env         # optional; defaults work for a console dry-run
```

### 1. The universe (this is "WLS")

The competition allows any member of the **Bloomberg World Large, Mid & Small
Cap Index (WLS)** — single-name equities only, long-only, no ETFs, no leverage,
and no single position above 20% of notional. That full index is **~10,000+
global names and lives only in the Bloomberg Terminal (`MEMB`)**, so it can't be
scraped or pulled from a public API.

`config/universe.csv` therefore ships a practical, liquid, **US large/mid-cap
subset** of WLS: the **S&P 500 + S&P MidCap 400** constituents (~900 names, all
WLS members), tickers normalised for Yahoo Finance. Regenerate it any time with:

```bash
python scripts/build_universe.py
```

You can edit the file freely (one ticker per line, `#` for comments). To trade
the exact index instead, export WLS constituents from the Terminal and drop them
in — just keep Yahoo ticker conventions (`BRK-B`, not `BRK.B`).

> **Note on the benchmark:** your P&L is scored against the *global* WLS index,
> but this working universe is US-only — a deliberate regional tilt. Fine to
> start; revisit if you want to track the global benchmark more closely.

### 2. Run a backtest (do this before trusting any signal)

```bash
trading-bot backtest --period 2y
# or without installing:
PYTHONPATH=src python -m trading_bot.cli backtest --period 2y
```

Look at **expectancy_r** (average R per trade) and **profit_factor**. You want
expectancy > 0 and profit factor > 1 *on your real universe*, ideally on data
the parameters weren't tuned on. A `win_rate` near 1.0 would be a red flag, not
a success — it means the setup has no real stop.

### 3. Generate today's setups

```bash
trading-bot signals --dry-run            # prints to console, no WhatsApp
trading-bot signals                      # sends via configured WhatsApp provider
trading-bot signals --json               # also emit machine-readable JSON
```

---

## Tuning the strategy (how the defaults were chosen)

The defaults were set by an **ablation study** on 5 years of data, keeping only
changes with sound rationale that improved results — and then confirming them
**out-of-sample**. Honest findings:

- **The win-rate lever that works is the momentum "sweet spot":** RSI 55–70
  **and** ROC ≥ 2% **and** volume ≥ 1.2× average. Too-weak momentum = fakeouts;
  too-hot = exhaustion. This raised win rate ~51% → ~54%, roughly **4×'d**
  expectancy, and **halved** max drawdown — and it held up in *both* halves of
  an out-of-sample time split. These are now the defaults.
- **The classic regime/ADX/slope filters barely moved the needle** on a
  large-cap universe that trended up for years (there was little chop or
  risk-off to filter out). They are included but **off by default** — on a
  broader or weaker real universe they may matter much more, so test them.
- **Win rate tops out in the low-to-mid 50s%.** That is what a real edge looks
  like. Anything claiming far more is either overfit or using a no-stop,
  tiny-target trick that hides catastrophic risk.

Run your own ablation on *your* competition universe before trusting any of it.

### Riding winners vs. scalping them (why the default is `trend`)

The competition is a short, winner-skewed tournament scored on *relative return*
vs the WLS index. Past winners posted enormous numbers (+167%, +400% in a few
weeks) by **concentrating and letting volatile positions run** — not by racking
up a high win rate on tiny trades. To *place well* you need the same instinct in
measured form: **ride winners, cut losers fast.**

The backtest makes the trade-off concrete (15y, large-cap sample):

| Exit | Win rate | Expectancy | Avg win | Best single win | Trades ≥3R |
|---|---|---|---|---|---|
| `swing` (1.5R, 2-day) | **53%** | +0.05R | 1.5R | 1.5R | 0% |
| `trend` (trail 3×ATR) | **39%** | **+0.33R** | 2.0R | **~12R** | ~9% |

Trend-riding **wins less than half the time yet earns ~6–7× the expectancy**,
because a handful of trades run to 10×+ their risk and carry all the small
losers. This is why "maximize win rate" is the wrong goal — and it's a robust,
decades-documented effect, not a curve-fit. `trend` is the default; set
`EXIT_MODE=swing` to revert.

### Placing well: concentration, volatility tilt, portfolio backtest

Three pieces now target the "place well" goal:

- **Conviction-weighted concentration** (`trading_bot.portfolio.allocate`):
  spreads the $1M across the top `TARGET_POSITIONS` (default 10) names,
  conviction-weighted by score via water-filling, capped at `MAX_POSITION_PCT`
  (20%, the rule), aiming for ~full deployment. The daily signal message prints
  the suggested concentrated book.
- **Volatility tilt** (`USE_VOL_TILT`, default on): the ranking score rewards
  higher-ATR% movers, so the book leans toward names that can actually run.
- **High-volatility universe** (`config/high_vol_supplement.csv`): adds ~37
  liquid high-beta/biotech/crypto-proxy/catalyst names on top of the S&P
  500+400 (regenerate with `python scripts/build_universe.py`).

**Portfolio backtester** — the metric that actually sets your ranking:

```bash
python scripts/portfolio_backtest.py --period 5y --benchmark ACWI
```

It runs the concentrated, trend-riding portfolio day by day (no look-ahead:
close-signals execute at the next open), then reports a full-history run and a
**walk-forward over ~6-week windows** (the competition length): how often and
by how much it beats the benchmark, including the right-tail (p90) outcome that
placing well depends on. Use `--benchmark ACWI` (global, ≈ WLS) — `SPY` is a
much tougher US-large-cap bar. WLS itself is Terminal-only.

### ⚠️ A note on "tune it to beat October" / calendar windows

Tuning parameters until the backtest shows a high win rate on a **hand-picked
calendar window** (e.g. mid-Oct → mid-Nov) is **overfitting**, not a strategy.
A study on 15 years of data showed:

- The window has a mild *bullish index tilt* (SPY up in 13/15 years, ~+3% mean)
  — but with a big spread (−5% in 2012), and this is an **index drift over a
  month**, not an 80% hit rate on 1–2 day trades.
- Momentum+EMA actually performed **slightly worse** in that window than the
  rest of the year, and the per-year win rate swung from **17% to 92%** on
  tiny samples — i.e. noise. You could "prove" 80%+ by cherry-picking a good
  year, then watch it crater the next.

Optimising to a calendar window produces a number that evaporates the moment
you trade it live — which is *during* the competition. Don't.

## WhatsApp delivery

Set the provider in `.env`:

- `WHATSAPP_PROVIDER=console` *(default)* — prints the message. No credentials.
- `WHATSAPP_PROVIDER=twilio` — broadcasts each signal 1:1 to every number in
  `WHATSAPP_RECIPIENTS` via Twilio's WhatsApp API.

### ⚠️ The group limitation (important)

The **official** WhatsApp Business API (Twilio *and* Meta Cloud API) **cannot
post into a WhatsApp group.** It only supports 1:1 conversations with people
who opted in. So "post to the group" is implemented as a **broadcast**: each
team member gets the signal in their own 1:1 chat with the bot.

If you truly need it inside one group thread, the only way is an **unofficial
WhatsApp-Web automation library** (e.g. `whatsapp-web.js`, `Baileys`). Those
drive a real logged-in WhatsApp session and *can* post to a group — but they
violate WhatsApp's ToS and **risk your number getting banned.** This repo
deliberately does not implement that path; the adapter interface
(`src/trading_bot/whatsapp.py`) makes it easy to add if you accept that risk.

### Twilio quick start

1. Create a Twilio account and enable the WhatsApp sandbox (or get an approved
   sender).
2. Have each teammate message the sandbox join code so they're opted in.
3. Fill `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, and
   `WHATSAPP_RECIPIENTS` in `.env`, set `WHATSAPP_PROVIDER=twilio`, and run
   `trading-bot signals`.

---

## Scheduling (post before each session)

Run the scan on a cron (e.g. once each morning before the trading session):

```cron
30 13 * * 1-5  cd /path/to/repo && /usr/bin/env trading-bot signals >> bot.log 2>&1
```

---

## Project layout

```
config/universe.csv          # WLS — your tradeable tickers (edit this)
src/trading_bot/
  config.py                  # all tunables (env-overridable)
  universe.py                # loads the ticker list
  data.py                    # Yahoo Finance OHLCV (swap here for Bloomberg export)
  indicators.py              # EMA, ROC, RSI, ATR (pure, tested)
  strategy.py                # setup screen, scoring, sizing -> Signal objects
  backtest.py                # honest replay: win rate, expectancy, drawdown
  formatting.py              # WhatsApp message rendering
  whatsapp.py                # console / Twilio adapters
  cli.py                     # `trading-bot signals|backtest`
tests/                       # pytest suite (no network needed)
```

## Tests

```bash
pytest -q
```

---

## Honest limitations & next steps

- **Backtest realism:** uses daily bars; when a bar could have hit both stop
  and target it pessimistically assumes the stop. It does not model slippage,
  commissions, or intraday paths. Treat results as indicative, not exact.
- **No portfolio-level concurrency in the backtest:** it measures per-setup
  expectancy. The 10-slot cap is applied to *live* signals only.
- **Validate out-of-sample:** tune on one period, confirm on another. Do not
  trust in-sample numbers.
- **This is for a simulated competition.** Do not point it at a real brokerage
  without understanding the regulatory implications of sharing trade signals.

Not financial advice.
