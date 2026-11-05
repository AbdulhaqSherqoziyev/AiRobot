"""Read-only order-book metrics from public Binance Spot depth snapshots. Places no orders.

Concepts (spread, depth bands, VWAP cost of a size) follow Hummingbot's OrderBook API
(get_price, get_vwap_for_volume); no Hummingbot code is used. Binance REST depth carries no
exchange timestamp, so freshness means the age of our last successful fetch.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

DEFAULT_BANDS_BPS = (10, 50, 100)
BOOK_LIMIT = 500  # request weight 25; a smaller book would not reach the wider bands on BTC


@dataclass(frozen=True)
class Thresholds:
    wide_spread_bps: float = 10.0
    thin_depth_quote: float = 1000.0  # within the narrowest band, either side
    imbalance: float = 0.7
    stale_seconds: float = 30.0


def _levels(rows: list) -> list[tuple[float, float]]:
    return [(float(p), float(q)) for p, q in rows if float(q) > 0]


def _fill_cost(levels: list[tuple[float, float]], notional: float, reference: float, side: int) -> dict:
    """Average price of a market order of `notional` quote against the visible book."""
    left, qty, spent = notional, 0.0, 0.0
    for price, avail in levels:
        take = min(left, price * avail)
        spent += take
        qty += take / price
        left -= take
        if left <= 1e-9:
            break
    if qty <= 0:
        return {"filled": False, "vwap": None, "slippage_bps": None}
    vwap = spent / qty
    return {"filled": left <= 1e-9, "vwap": vwap, "slippage_bps": side * (vwap / reference - 1) * 1e4}


def analyze(depth: dict, bands_bps: tuple[int, ...] = DEFAULT_BANDS_BPS, notional: float = 100.0, fee: float = 0.001, th: Thresholds = Thresholds()) -> dict:
    """Metrics for one snapshot. Raises ValueError on an empty book, which has no spread."""
    bids, asks = _levels(depth.get("bids") or []), _levels(depth.get("asks") or [])
    if not bids or not asks:
        raise ValueError("bo'sh order book")
    bid, ask = bids[0][0], asks[0][0]
    mid = (bid + ask) / 2
    spread = ask - bid
    spread_bps = spread / mid * 1e4
    rows = []
    for bps in sorted(bands_bps):
        lo, hi = mid * (1 - bps / 1e4), mid * (1 + bps / 1e4)
        b = sum(p * q for p, q in bids if p >= lo)
        a = sum(p * q for p, q in asks if p <= hi)
        # If the fetched book ends inside the band, the sum is only a lower bound.
        rows.append({
            "bps": bps, "bid_quote": round(b, 2), "ask_quote": round(a, 2),
            "imbalance": round((b - a) / (b + a), 4) if b + a else None,
            "complete": bids[-1][0] < lo and asks[-1][0] > hi,
        })
    buy, sell = _fill_cost(asks, notional, mid, 1), _fill_cost(bids, notional, mid, -1)
    # A maker pays the fee twice and at best captures the spread: the test any market-making
    # idea has to pass before inventory risk and competition are even considered.
    maker_edge = spread_bps - 2 * fee * 1e4
    warnings = []
    if bid >= ask:
        warnings.append({"code": "crossed_book", "level": "err", "text": "Bid ask'dan yuqori: ma'lumot xato bo'lishi mumkin"})
    if spread_bps > th.wide_spread_bps:
        warnings.append({"code": "wide_spread", "level": "warn", "text": f"Spread keng: {spread_bps:.1f} bps"})
    if rows and min(rows[0]["bid_quote"], rows[0]["ask_quote"]) < th.thin_depth_quote:
        warnings.append({"code": "thin_depth", "level": "warn", "text": f"±{rows[0]['bps']} bps ichida likvidlik kam"})
    if rows and rows[0]["imbalance"] is not None and abs(rows[0]["imbalance"]) > th.imbalance:
        warnings.append({"code": "imbalance", "level": "info", "text": f"Kuchli nomutanosiblik: {rows[0]['imbalance']:+.2f}"})
    if not buy["filled"] or not sell["filled"]:
        warnings.append({"code": "book_too_short", "level": "warn", "text": f"Ko'rinadigan kitob {notional:g} USDT uchun yetarli emas"})
    return {
        "best_bid": bid, "best_ask": ask, "mid": mid, "spread": spread, "spread_pct": spread / mid * 100, "spread_bps": spread_bps,
        "depth": rows, "levels": {"bids": len(bids), "asks": len(asks)}, "last_update_id": depth.get("lastUpdateId"),
        "liquidity": {"notional": notional, "buy": buy, "sell": sell},
        "maker_round_trip": {"fee_bps": 2 * fee * 1e4, "edge_bps": maker_edge, "viable": maker_edge > 0},
        "warnings": warnings,
    }


@dataclass
class _Entry:
    fetched_at: float = 0.0  # last attempt
    success_at: float = 0.0
    latency_ms: float | None = None
    metrics: dict | None = None
    error: str = ""
    failures: int = 0


@dataclass
class MicrostructureMonitor:
    """Serves snapshots, keeps the last good one, and makes failures and staleness explicit."""

    fetch: Callable[[str, int], dict]
    ttl: float = 5.0
    thresholds: Thresholds = Thresholds()
    clock: Callable[[], float] = time.time
    _entries: dict[str, _Entry] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, pair: str, notional: float = 100.0, fee: float = 0.001) -> dict:
        with self._lock:
            e = self._entries.setdefault(pair, _Entry())
            now = self.clock()
            if now - e.fetched_at >= self.ttl or (e.metrics and e.metrics["liquidity"]["notional"] != notional):
                self._refresh(pair, e, now, notional, fee)
            return self._view(pair, e)

    def _refresh(self, pair: str, e: _Entry, now: float, notional: float, fee: float) -> None:
        e.fetched_at = now
        started = time.monotonic()
        try:
            e.metrics = analyze(self.fetch(pair, BOOK_LIMIT), notional=notional, fee=fee, th=self.thresholds)
        except Exception as exc:  # noqa: BLE001  the failure itself is what the page has to show
            e.error, e.failures = str(exc)[:300], e.failures + 1
            return
        e.success_at, e.latency_ms, e.error, e.failures = self.clock(), (time.monotonic() - started) * 1000, "", 0

    def _view(self, pair: str, e: _Entry) -> dict:
        age = self.clock() - e.success_at if e.success_at else None
        if e.metrics is None:
            status = "error"
        elif e.failures or (age is not None and age > self.thresholds.stale_seconds):
            status = "stale"
        else:
            status = "ok"
        return {
            "pair": pair, "status": status, "source": "binance-spot-public REST /depth", "as_of": e.success_at or None, "age_seconds": age,
            "latency_ms": e.latency_ms, "error": e.error, "consecutive_failures": e.failures, "metrics": e.metrics,
        }
