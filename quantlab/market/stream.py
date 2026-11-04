"""Binance public price WebSocket with reconnect and backoff. Prices are advisory (display
and engine-side stops); paper and strategy decisions use closed candles from the store."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


class PriceStream:
    def __init__(self, url: str, pairs: list[str], connect=None, max_backoff: float = 60.0):
        streams = "/".join(f"{p.replace('/', '').lower()}@miniTicker" for p in pairs)
        self.url = f"{url}?streams={streams}"
        self.prices: dict[str, float] = {}
        self.connected = False
        self.reconnects = 0
        self.last_message = 0.0
        self.max_backoff = max_backoff
        self._connect = connect
        self._names = {p.replace("/", ""): p for p in pairs}

    def handle(self, raw: str) -> None:
        d = json.loads(raw).get("data", {})
        pair = self._names.get(d.get("s", ""))
        if pair and "c" in d:
            self.prices[pair] = float(d["c"])
            self.last_message = time.time()

    async def run(self, stop: asyncio.Event, sleep: Callable[[float], Awaitable] = asyncio.sleep) -> None:
        connect = self._connect
        if connect is None:
            import websockets

            connect = websockets.connect
        backoff = 1.0
        while not stop.is_set():
            try:
                async with connect(self.url) as ws:
                    self.connected = True
                    backoff = 1.0
                    async for raw in ws:
                        self.handle(raw)
                        if stop.is_set():
                            break
            except Exception as exc:  # any network failure: reconnect, never crash the worker
                log.warning("price stream dropped: %s", type(exc).__name__)
            self.connected = False
            if stop.is_set():
                break
            self.reconnects += 1
            await sleep(backoff)
            backoff = min(backoff * 2, self.max_backoff)
