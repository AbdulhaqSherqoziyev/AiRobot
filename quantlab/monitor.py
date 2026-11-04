"""System health for the Monitoring page."""

from __future__ import annotations

import shutil
from datetime import timedelta

import psutil
from sqlalchemy import text

from quantlab.models import ComponentHeartbeat, MarketDataset, utcnow

STALE = {"market": 180, "paper": 90, "jobs": 90, "notify": 180, "live": 90}


def snapshot(db, data_dir, client=None) -> dict:
    vm = psutil.virtual_memory()
    disk = shutil.disk_usage(str(data_dir) if data_dir.exists() else "/")
    db_ok, db_err = True, ""
    try:
        with db.session() as s:
            s.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok, db_err = False, type(exc).__name__
    workers, datasets = [], []
    if db_ok:
        with db.session() as s:
            now = utcnow()
            for h in s.query(ComponentHeartbeat):
                age = (now - h.at).total_seconds()
                workers.append({"name": h.name, "age_seconds": round(age), "ok": age < STALE.get(h.name, 120), "detail": h.detail})
            for d in s.query(MarketDataset).order_by(MarketDataset.symbol, MarketDataset.timeframe):
                datasets.append({"symbol": d.symbol, "timeframe": d.timeframe, "source": d.source, "rows": d.rows, "gaps": d.gaps, "first_ts": d.first_ts, "last_ts": d.last_ts, "last_sync_at": d.last_sync_at.isoformat() + "Z" if d.last_sync_at else None, "last_error": d.last_error})
    latency, binance_ok = None, False
    if client is not None:
        try:
            latency, binance_ok = round(client.ping(), 1), True
        except Exception:
            binance_ok = False
    ws = next((w["detail"] for w in workers if w["name"] == "market"), {})
    return {
        "cpu_pct": psutil.cpu_percent(interval=0.1), "ram_pct": vm.percent, "ram_used_gb": round(vm.used / 2**30, 2), "ram_total_gb": round(vm.total / 2**30, 2),
        "disk_pct": round(disk.used / disk.total * 100, 1), "disk_free_gb": round(disk.free / 2**30, 1),
        "database": {"ok": db_ok, "error": db_err}, "backend": {"ok": True}, "workers": workers, "datasets": datasets,
        "binance": {"ok": binance_ok, "latency_ms": latency}, "websocket": {"connected": bool(ws.get("ws_connected")), "reconnects": ws.get("ws_reconnects", 0)},
    }
