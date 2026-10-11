"""Bloomberg Trading Challenge — momentum + EMA signal bot.

A signals-only trading assistant for the (simulated) Bloomberg Global Trading
Challenge. It screens the competition's allowed universe for short-term
(1-2 day hold) long setups that combine an EMA trend stack with momentum
confirmation, sizes them for a $1M paper portfolio, and posts the ranked
setups to a WhatsApp channel.

It does NOT place trades. Humans review the setups and enter them in the
Bloomberg terminal.
"""

__version__ = "0.1.0"
