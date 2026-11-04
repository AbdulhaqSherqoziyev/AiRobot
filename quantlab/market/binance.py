"""Public Binance Spot REST client: retries, backoff and rate-limit handling. No keys."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

log = logging.getLogger(__name__)
KLINES_MAX = 1000


class BinanceError(RuntimeError):
    pass


def to_symbol(pair: str) -> str:
    return pair.replace("/", "")


class BinancePublic:
    def __init__(self, base_url: str, client: httpx.Client | None = None, retries: int = 5, sleep: Callable[[float], None] = time.sleep):
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=15)
        self.retries = retries
        self.sleep = sleep

    def _get(self, path: str, params: dict | None = None) -> Any:
        delay = 1.0
        last = ""
        for attempt in range(self.retries):
            try:
                res = self.client.get(f"{self.base}/api/v3/{path}", params=params)
            except httpx.HTTPError as exc:
                last = f"network: {exc}"
            else:
                if res.status_code in (418, 429):
                    # Binance states how long to back off; ignoring it risks an IP ban.
                    wait = float(res.headers.get("Retry-After", delay))
                    last = f"rate limited {res.status_code}"
                    self.sleep(wait)
                    continue
                if res.status_code >= 500:
                    last = f"HTTP {res.status_code}"
                elif res.status_code >= 400:
                    raise BinanceError(f"{path}: HTTP {res.status_code}: {res.text[:200]}")
                else:
                    return res.json()
            if attempt < self.retries - 1:
                self.sleep(delay)
                delay = min(delay * 2, 30)
        raise BinanceError(f"{path}: gave up after {self.retries} attempts: {last}")

    def ping(self) -> float:
        started = time.monotonic()
        self._get("ping")
        return (time.monotonic() - started) * 1000

    def klines(self, pair: str, timeframe: str, start_ms: int | None = None, end_ms: int | None = None, limit: int = KLINES_MAX) -> list[list]:
        params: dict = {"symbol": to_symbol(pair), "interval": timeframe, "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        return self._get("klines", params)

    def tickers(self, pairs: list[str]) -> list[dict]:
        import json

        return self._get("ticker/24hr", {"symbols": json.dumps([to_symbol(p) for p in pairs], separators=(",", ":"))})

    def book_tickers(self, pairs: list[str]) -> list[dict]:
        import json

        return self._get("ticker/bookTicker", {"symbols": json.dumps([to_symbol(p) for p in pairs], separators=(",", ":"))})

    def depth(self, pair: str, limit: int = 20) -> dict:
        return self._get("depth", {"symbol": to_symbol(pair), "limit": limit})

    def trades(self, pair: str, limit: int = 500) -> list[dict]:
        return self._get("trades", {"symbol": to_symbol(pair), "limit": limit})

    def exchange_info(self, pairs: list[str] | None = None) -> dict:
        import json

        params = {"symbols": json.dumps([to_symbol(p) for p in pairs], separators=(",", ":"))} if pairs else None
        return self._get("exchangeInfo", params)


def parse_filters(symbol_info: dict) -> dict:
    """Trading filters the backtester, paper engine and live engine all respect."""
    out = {"min_notional": 5.0, "step_size": 0.0, "tick_size": 0.0, "min_qty": 0.0, "status": symbol_info.get("status", "")}
    for f in symbol_info.get("filters", []):
        t = f.get("filterType")
        if t == "LOT_SIZE":
            out["step_size"] = float(f["stepSize"])
            out["min_qty"] = float(f["minQty"])
        elif t == "PRICE_FILTER":
            out["tick_size"] = float(f["tickSize"])
        elif t in ("NOTIONAL", "MIN_NOTIONAL"):
            out["min_notional"] = float(f.get("minNotional", out["min_notional"]))
    return out
