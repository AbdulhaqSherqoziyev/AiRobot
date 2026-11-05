"""Regenerates jesse_results.json by running real Jesse on real Binance Spot candles.

Never imported by the application or the test suite: Jesse's pins conflict with Quant Lab,
so it runs in its own venv and only its output is committed.

    <jesse-venv>/bin/python -I run_jesse_parity.py <fixture-dir> [start-iso] [end-iso]
"""
import importlib
import json
import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(sys.argv[1]).resolve()
START = sys.argv[2] if len(sys.argv) > 2 else "2026-08-01"
END = sys.argv[3] if len(sys.argv) > 3 else "2026-11-01"
SYMBOL, PAIR, TF, FEE, BALANCE = "BTCUSDT", "BTC-USDT", "1h", 0.001, 100.0
WARMUP_HOURS = 240
BASE = "https://data-api.binance.vision/api/v3/klines"


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


def klines(interval: str, start: int, end: int) -> list[list]:
    out: list[list] = []
    while start < end:
        url = f"{BASE}?symbol={SYMBOL}&interval={interval}&startTime={start}&endTime={end - 1}&limit=1000"
        with urllib.request.urlopen(url, timeout=30) as r:
            rows = json.load(r)
        if not rows:
            break
        out += rows
        start = rows[-1][0] + 1
        time.sleep(0.05)
    return out


def jesse_rows(rows: list[list]) -> np.ndarray:
    # Jesse column order: timestamp, open, close, high, low, volume.
    return np.array([[r[0], float(r[1]), float(r[4]), float(r[2]), float(r[3]), float(r[5])] for r in rows], dtype=float)


def main() -> None:
    sys.path.insert(0, str(HERE))
    # Jesse resolves strategies from ./strategies, which also makes it demand its PostgreSQL
    # for closed-trade history. A temp cwd keeps its output out of the repo; DB writes are off.
    work = Path(tempfile.mkdtemp())
    (work / "strategies").symlink_to(HERE / "strategies")
    os.chdir(work)
    start, end = ms(START), ms(END)
    warm = start - WARMUP_HOURS * 3600_000
    cache = Path(tempfile.gettempdir()) / f"ql_jesse_1m_{START}_{END}.npy"
    if cache.exists():
        one = np.load(cache)
    else:
        one = jesse_rows(klines("1m", warm, end))
        np.save(cache, one)
    hourly = klines(TF, warm, end)
    from jesse.research import backtest
    from jesse.services.db import Database

    Database.open_connection = lambda self: None

    key = f"Binance Spot-{PAIR}"
    candles = {key: {"exchange": "Binance Spot", "symbol": PAIR, "candles": one[one[:, 0] >= start]}}
    warmup = {key: {"exchange": "Binance Spot", "symbol": PAIR, "candles": one[one[:, 0] < start]}}
    results = {}
    for name in ("QlEmaCross", "QlRsiTrend"):
        mod = importlib.import_module(f"strategies.{name}")
        mod.LOG.clear()
        cfg = {"starting_balance": BALANCE, "fee": FEE, "type": "spot", "simulation_model": "spot", "exchange": "Binance Spot", "warm_up_candles": WARMUP_HOURS, "annualization": 365}
        routes = [{"exchange": "Binance Spot", "strategy": name, "symbol": PAIR, "timeframe": TF}]
        res = backtest(cfg, routes, [], candles, warmup)
        m = res.get("metrics", {})
        results[name] = {
            "fills": list(mod.LOG),
            "total_trades": m.get("total"),
            "net_profit": m.get("net_profit"),
            "net_profit_percentage": m.get("net_profit_percentage"),
            "max_drawdown": m.get("max_drawdown"),
            "win_rate": m.get("win_rate"),
            "finishing_balance": m.get("finishing_balance"),
            "fee": m.get("fee"),
        }
    import jesse.version

    payload = {
        "jesse_version": jesse.version.__version__,
        "symbol": PAIR, "timeframe": TF, "fee": FEE, "initial": BALANCE, "start": START, "end": END, "warmup_hours": WARMUP_HOURS,
        "hourly_candles": [[r[0] // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in hourly],
        "results": results,
    }
    (HERE / "jesse_results.json").write_text(json.dumps(payload))
    print(json.dumps({k: {a: b for a, b in v.items() if a != "fills"} | {"n_fills": len(v["fills"])} for k, v in results.items()}, indent=1))


if __name__ == "__main__":
    main()
