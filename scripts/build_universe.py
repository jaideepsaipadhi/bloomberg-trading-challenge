#!/usr/bin/env python3
"""Regenerate config/universe.csv — a liquid US large/mid-cap subset of WLS.

The Bloomberg Trading Challenge allows any member of the Bloomberg World Large,
Mid & Small Cap Index (WLS). That full index is ~10,000+ global names and is
only available inside the Bloomberg Terminal (MEMB), so it cannot be scraped.

This builds a practical, liquid, US-listed working subset — the S&P 500 (large)
and S&P MidCap 400 (mid) constituents, all of which are WLS members — from
Wikipedia, and normalises the tickers for Yahoo Finance (e.g. BRK.B -> BRK-B).

Usage:  python scripts/build_universe.py
"""
from __future__ import annotations

import io
import pathlib

import pandas as pd
import requests

SOURCES = [
    ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "S&P 500 (large)"),
    ("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "S&P MidCap 400 (mid)"),
]
SYMBOL_COLS = ("Symbol", "Ticker symbol", "Ticker")
HEADERS = {"User-Agent": "Mozilla/5.0 (bloomberg-trading-challenge universe builder)"}
OUT = pathlib.Path(__file__).resolve().parents[1] / "config" / "universe.csv"


def _symbols_from(url: str) -> list[str]:
    html = requests.get(url, headers=HEADERS, timeout=60).text
    for table in pd.read_html(io.StringIO(html)):
        cols = {str(c).lower(): c for c in table.columns}
        for want in SYMBOL_COLS:
            if want.lower() in cols:
                raw = table[cols[want.lower()]]
                return [str(s).strip().upper().replace(".", "-")
                        for s in raw if str(s).strip() and str(s) != "nan"]
    raise SystemExit(f"No symbol column found at {url}")


def main() -> None:
    merged: list[str] = []
    seen: set[str] = set()
    for url, label in SOURCES:
        syms = _symbols_from(url)
        print(f"{label}: {len(syms)} symbols")
        for s in syms:
            if s not in seen:
                seen.add(s)
                merged.append(s)

    header = [
        "# WLS working universe for the Bloomberg Trading Challenge.",
        "# The competition allows any member of the Bloomberg World Large, Mid & Small",
        "# Cap Index (WLS). That full index is ~10,000+ global names and lives only in",
        "# the Bloomberg Terminal, so this is a liquid US large- + mid-cap SUBSET of it:",
        "# S&P 500 (large) + S&P MidCap 400 (mid). All are WLS members with clean data.",
        "# Tickers normalised for Yahoo Finance (e.g. BRK.B -> BRK-B).",
        "# Regenerate with scripts/build_universe.py.",
        "symbol",
    ]
    OUT.write_text("\n".join(header + merged) + "\n")
    print(f"Wrote {OUT} with {len(merged)} unique symbols")


if __name__ == "__main__":
    main()
