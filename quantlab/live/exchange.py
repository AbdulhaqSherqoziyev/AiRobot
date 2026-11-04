"""Signed Binance Spot client. Spot only by construction: it exposes no margin, futures,
transfer or withdrawal method, and the request helper refuses any path outside its list."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Protocol
from urllib.parse import urlencode

import httpx

ALLOWED_SIGNED = {("GET", "/api/v3/account"), ("POST", "/api/v3/order"), ("GET", "/api/v3/order"), ("DELETE", "/api/v3/openOrders"), ("GET", "/api/v3/openOrders"), ("GET", "/sapi/v1/account/apiRestrictions")}


class ExchangeError(RuntimeError):
    """The exchange rejected the request; the order definitely did not execute."""


class ExchangeUnknown(RuntimeError):
    """Timeout or 5xx: the order may or may not exist, so it must be reconciled."""


class Exchange(Protocol):
    def account(self) -> dict: ...
    def market_buy(self, symbol: str, quote_qty: float, client_id: str) -> dict: ...
    def market_sell(self, symbol: str, base_qty: float, client_id: str) -> dict: ...
    def query_order(self, symbol: str, client_id: str) -> dict | None: ...
    def open_orders(self, symbol: str) -> list[dict]: ...
    def cancel_all(self, symbol: str) -> None: ...


class BinanceSpot:
    def __init__(self, base_url: str, api_key: str, api_secret: str, client: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self._key, self._secret = api_key, api_secret
        self.client = client or httpx.Client(timeout=10)

    def __repr__(self) -> str:  # never let a key reach a log line
        return f"BinanceSpot({self.base})"

    def _signed(self, method: str, path: str, params: dict | None = None):
        if (method, path) not in ALLOWED_SIGNED:
            raise ExchangeError(f"endpoint not permitted: {method} {path}")
        q = {**(params or {}), "timestamp": int(time.time() * 1000), "recvWindow": 5000}
        qs = urlencode(q)
        sig = hmac.new(self._secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
        try:
            res = self.client.request(method, f"{self.base}{path}?{qs}&signature={sig}", headers={"X-MBX-APIKEY": self._key})
        except httpx.HTTPError as exc:
            raise ExchangeUnknown(type(exc).__name__) from exc
        if res.status_code >= 500 or res.status_code in (418, 429):
            raise ExchangeUnknown(f"HTTP {res.status_code}")
        if res.status_code >= 400:
            raise ExchangeError(f"HTTP {res.status_code}: {res.text[:300]}")
        return res.json()

    def key_restrictions(self) -> dict:
        return self._signed("GET", "/sapi/v1/account/apiRestrictions")

    def account(self) -> dict:
        return self._signed("GET", "/api/v3/account")

    def market_buy(self, symbol: str, quote_qty: float, client_id: str) -> dict:
        return self._signed("POST", "/api/v3/order", {"symbol": symbol, "side": "BUY", "type": "MARKET", "quoteOrderQty": f"{quote_qty:.2f}", "newClientOrderId": client_id, "newOrderRespType": "FULL"})

    def market_sell(self, symbol: str, base_qty: float, client_id: str) -> dict:
        return self._signed("POST", "/api/v3/order", {"symbol": symbol, "side": "SELL", "type": "MARKET", "quantity": f"{base_qty:.8f}".rstrip("0").rstrip("."), "newClientOrderId": client_id, "newOrderRespType": "FULL"})

    def query_order(self, symbol: str, client_id: str) -> dict | None:
        try:
            return self._signed("GET", "/api/v3/order", {"symbol": symbol, "origClientOrderId": client_id})
        except ExchangeError as exc:
            if "-2013" in str(exc):  # Order does not exist
                return None
            raise

    def open_orders(self, symbol: str) -> list[dict]:
        return self._signed("GET", "/api/v3/openOrders", {"symbol": symbol})

    def cancel_all(self, symbol: str) -> None:
        try:
            self._signed("DELETE", "/api/v3/openOrders", {"symbol": symbol})
        except ExchangeError as exc:
            if "-2011" not in str(exc):  # nothing to cancel
                raise


def verify_key_is_safe(ex: BinanceSpot) -> list[str]:
    """Problems with the live key. Withdrawal, margin and futures rights all refuse start."""
    r = ex.key_restrictions()
    problems = []
    if r.get("enableWithdrawals"):
        problems.append("API key has withdrawal permission")
    if r.get("enableMargin") or r.get("enableFutures") or r.get("enableVanillaOptions"):
        problems.append("API key has margin or derivatives permission")
    if not r.get("ipRestrict"):
        problems.append("API key is not IP restricted")
    if not r.get("enableSpotAndMarginTrading"):
        problems.append("API key cannot trade spot")
    return problems
