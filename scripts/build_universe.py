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

import argparse
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
CONFIG = pathlib.Path(__file__).resolve().parents[1] / "config"
OUT = CONFIG / "universe.csv"
SUPPLEMENT = CONFIG / "high_vol_supplement.csv"


def _read_local_symbols(path: pathlib.Path) -> list[str]:
    syms = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.lower() in {"symbol", "ticker"}:
            continue
        syms.append(s.upper().replace(".", "-"))
    return syms


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


def main(high_vol: bool = True) -> None:
    merged: list[str] = []
    seen: set[str] = set()

    def add(syms):
        n = 0
        for s in syms:
            if s and s not in seen:
                seen.add(s)
                merged.append(s)
                n += 1
        return n

    for url, label in SOURCES:
        syms = _symbols_from(url)
        print(f"{label}: {len(syms)} symbols")
        add(syms)

    supp_note = ""
    if high_vol and SUPPLEMENT.exists():
        added = add(_read_local_symbols(SUPPLEMENT))
        print(f"High-vol supplement: +{added} net-new names")
        supp_note = f"# Plus {added} net-new high-volatility/catalyst names from high_vol_supplement.csv.\n"

    header = [
        "# WLS working universe for the Bloomberg Trading Challenge.",
        "# The competition allows any member of the Bloomberg World Large, Mid & Small",
        "# Cap Index (WLS). That full index is ~10,000+ global names and lives only in",
        "# the Bloomberg Terminal, so this is a liquid US large- + mid-cap SUBSET of it:",
        "# S&P 500 (large) + S&P MidCap 400 (mid). All are WLS members with clean data.",
        supp_note.rstrip("\n") if supp_note else "#",
        "# Tickers normalised for Yahoo Finance (e.g. BRK.B -> BRK-B).",
        "# Regenerate with scripts/build_universe.py [--no-high-vol].",
        "symbol",
    ]
    OUT.write_text("\n".join(header + merged) + "\n")
    print(f"Wrote {OUT} with {len(merged)} unique symbols")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-high-vol", action="store_true",
                    help="Exclude the high-volatility/catalyst supplement.")
    args = ap.parse_args()
    main(high_vol=not args.no_high_vol)
