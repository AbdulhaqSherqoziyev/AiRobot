"""Configurable asset selection by liquidity, spread, volatility and exchange filters."""

from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass
from pathlib import Path

from quantlab.market.binance import BinancePublic, parse_filters

_spec = importlib.util.spec_from_file_location("ql_screening", Path(__file__).resolve().parents[2] / "freqtrade" / "islamic" / "screening.py")


def screen_pair(pair: str) -> str | None:
    """Reuses the Islamic pair screening (leveraged tokens, non-USDT quote, ...) without
    importing the whole Freqtrade package. Returns the rejection reason, or None."""
    assert _spec and _spec.loader
    mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(mod)
    return mod.screen_pair(pair)


@dataclass(frozen=True)
class UniverseRules:
    min_quote_volume: float = 20_000_000
    max_spread_bps: float = 10.0
    min_volatility_pct: float = 0.5
    max_volatility_pct: float = 25.0
    max_min_notional: float = 10.0


def evaluate(pair: str, ticker: dict, book: dict, filters: dict, rules: UniverseRules) -> dict:
    bid, ask = float(book["bidPrice"]), float(book["askPrice"])
    mid = (bid + ask) / 2
    spread = (ask - bid) / mid * 1e4 if mid else math.inf
    high, low = float(ticker["highPrice"]), float(ticker["lowPrice"])
    vola = (high - low) / low * 100 if low else 0.0
    vol = float(ticker["quoteVolume"])
    reasons = []
    if (r := screen_pair(pair)):
        reasons.append(f"compliance: {r}")
    if filters["status"] != "TRADING":
        reasons.append(f"status {filters['status']}")
    if vol < rules.min_quote_volume:
        reasons.append("low volume")
    if spread > rules.max_spread_bps:
        reasons.append("wide spread")
    if not rules.min_volatility_pct <= vola <= rules.max_volatility_pct:
        reasons.append("volatility out of range")
    if filters["min_notional"] > rules.max_min_notional:
        reasons.append("minimum order too large")
    return {"pair": pair, "quote_volume": vol, "spread_bps": round(spread, 3), "volatility_pct": round(vola, 2), **filters, "eligible": not reasons, "reasons": reasons}


def scan(client: BinancePublic, pairs: list[str], rules: UniverseRules | None = None) -> list[dict]:
    rules = rules or UniverseRules()
    tickers = {t["symbol"]: t for t in client.tickers(pairs)}
    books = {b["symbol"]: b for b in client.book_tickers(pairs)}
    info = {s["symbol"]: parse_filters(s) for s in client.exchange_info(pairs)["symbols"]}
    out = []
    for p in pairs:
        s = p.replace("/", "")
        if s in tickers and s in books and s in info:
            out.append(evaluate(p, tickers[s], books[s], info[s], rules))
    return out
