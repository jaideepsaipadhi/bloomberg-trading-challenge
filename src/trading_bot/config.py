"""Configuration for the trading signal bot.

All tunables live here so the strategy's behaviour is explicit and auditable.
Values can be overridden via environment variables (loaded from a .env file
if python-dotenv is installed).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Optional

try:  # optional, nice-to-have
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class PortfolioConfig:
    """Capital and position-sizing rules for the paper portfolio."""

    total_capital: float = field(default_factory=lambda: _env_float("TOTAL_CAPITAL", 1_000_000.0))
    notional_per_trade: float = field(default_factory=lambda: _env_float("NOTIONAL_PER_TRADE", 100_000.0))

    @property
    def max_concurrent_positions(self) -> int:
        """How many $notional trades the capital supports at once."""
        if self.notional_per_trade <= 0:
            return 0
        return int(self.total_capital // self.notional_per_trade)


@dataclass
class StrategyConfig:
    """Parameters for the EMA + momentum setup screen and risk management.

    Defaults are deliberately conservative and chosen to produce a positive
    EXPECTANCY, not a high hit rate. A realistic win rate for this style of
    short-term trade is roughly 45-60%; the edge comes from winners being
    larger than losers (see README).
    """

    # EMA trend stack (fast > mid > slow confirms an uptrend)
    ema_fast: int = field(default_factory=lambda: _env_int("EMA_FAST", 8))
    ema_mid: int = field(default_factory=lambda: _env_int("EMA_MID", 21))
    ema_slow: int = field(default_factory=lambda: _env_int("EMA_SLOW", 50))

    # Momentum. The RSI band + ROC floor define a "momentum sweet spot":
    # strong enough to trend (not a weak fakeout), not so hot it's exhausted.
    # These tuned defaults improved win rate AND expectancy in both halves of
    # an out-of-sample split (see README "Tuning the strategy").
    roc_lookback: int = field(default_factory=lambda: _env_int("ROC_LOOKBACK", 10))
    roc_min: float = field(default_factory=lambda: _env_float("ROC_MIN", 2.0))  # percent
    rsi_period: int = field(default_factory=lambda: _env_int("RSI_PERIOD", 14))
    rsi_min: float = field(default_factory=lambda: _env_float("RSI_MIN", 55.0))
    rsi_max: float = field(default_factory=lambda: _env_float("RSI_MAX", 70.0))

    # Volume confirmation
    volume_avg_period: int = field(default_factory=lambda: _env_int("VOLUME_AVG_PERIOD", 20))
    volume_ratio_min: float = field(default_factory=lambda: _env_float("VOLUME_RATIO_MIN", 1.2))

    # Anti-chasing: reject entries too far above the fast EMA (parabolic blow-offs)
    max_atr_extension: float = field(default_factory=lambda: _env_float("MAX_ATR_EXTENSION", 3.0))

    # --- Optional win-rate filters (default OFF = baseline). See README. ---

    # Market-regime filter: only go long when the benchmark is above its EMA.
    use_regime_filter: bool = field(default_factory=lambda: _env_bool("USE_REGIME_FILTER", False))
    benchmark_symbol: str = field(default_factory=lambda: os.getenv("BENCHMARK_SYMBOL", "SPY"))
    regime_ema: int = field(default_factory=lambda: _env_int("REGIME_EMA", 100))

    # Trend-strength filter: skip chop, require a real trend (ADX).
    use_adx_filter: bool = field(default_factory=lambda: _env_bool("USE_ADX_FILTER", False))
    adx_period: int = field(default_factory=lambda: _env_int("ADX_PERIOD", 14))
    adx_min: float = field(default_factory=lambda: _env_float("ADX_MIN", 20.0))

    # Rising-trend filter: require the slow EMA itself to be sloping up.
    use_slope_filter: bool = field(default_factory=lambda: _env_bool("USE_SLOPE_FILTER", False))
    slope_min: float = field(default_factory=lambda: _env_float("SLOPE_MIN", 0.0))

    # Pullback entry: only buy when price is NEAR the fast EMA (not extended),
    # i.e. buy the dip in an uptrend rather than chasing a stretched bar.
    use_pullback_entry: bool = field(default_factory=lambda: _env_bool("USE_PULLBACK_ENTRY", False))
    pullback_max_extension: float = field(default_factory=lambda: _env_float("PULLBACK_MAX_EXTENSION", 1.0))

    # Risk management (ATR-based)
    atr_period: int = field(default_factory=lambda: _env_int("ATR_PERIOD", 14))
    stop_atr_mult: float = field(default_factory=lambda: _env_float("STOP_ATR_MULT", 1.5))
    reward_risk_ratio: float = field(default_factory=lambda: _env_float("REWARD_RISK_RATIO", 1.5))
    max_hold_days: int = field(default_factory=lambda: _env_int("MAX_HOLD_DAYS", 2))

    # How many setups to surface per scan (also capped by portfolio slots)
    max_signals: int = field(default_factory=lambda: _env_int("MAX_SIGNALS", 10))

    @property
    def min_bars_required(self) -> int:
        """Minimum history needed before indicators are valid."""
        return max(self.ema_slow, self.roc_lookback, self.rsi_period,
                   self.atr_period, self.volume_avg_period) + 5


@dataclass
class WhatsAppConfig:
    """WhatsApp delivery settings.

    provider:
      - "console": print to stdout (default, zero setup, safe for testing)
      - "twilio":  broadcast 1:1 to each recipient via Twilio's WhatsApp API

    NOTE: The official WhatsApp Business API (Twilio/Meta) cannot post into a
    WhatsApp *group*. "recipients" is therefore a broadcast list of individual
    numbers that have opted in. See README for the group caveat.
    """

    provider: str = field(default_factory=lambda: os.getenv("WHATSAPP_PROVIDER", "console"))

    # Twilio
    twilio_account_sid: Optional[str] = field(default_factory=lambda: os.getenv("TWILIO_ACCOUNT_SID"))
    twilio_auth_token: Optional[str] = field(default_factory=lambda: os.getenv("TWILIO_AUTH_TOKEN"))
    # e.g. "whatsapp:+14155238886" (Twilio sandbox number)
    twilio_from: Optional[str] = field(default_factory=lambda: os.getenv("TWILIO_WHATSAPP_FROM"))
    # comma-separated e.g. "whatsapp:+1555...,whatsapp:+1444..."
    recipients_raw: Optional[str] = field(default_factory=lambda: os.getenv("WHATSAPP_RECIPIENTS"))

    @property
    def recipients(self) -> list[str]:
        if not self.recipients_raw:
            return []
        return [r.strip() for r in self.recipients_raw.split(",") if r.strip()]


@dataclass
class Config:
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    whatsapp: WhatsAppConfig = field(default_factory=WhatsAppConfig)

    def to_dict(self) -> dict:
        return asdict(self)


def load_config() -> Config:
    return Config()
