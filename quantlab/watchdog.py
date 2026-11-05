"""Tells the owner when the unattended system stops doing its job. A crashed container restarts by
itself; this is for what a restart does not catch: a stuck worker, stalled candles, a full disk.
It runs in the notify worker, so it cannot report its own death or a dead server."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from quantlab.config import TIMEFRAMES
from quantlab.models import ComponentHeartbeat, PaperSession, SystemSetting, utcnow
from quantlab.notify.service import notify

# Seconds of silence before alerting. Generous enough for normal work: one training job can run for
# minutes between jobs-worker heartbeats, and the trainer only wakes every ten minutes.
SILENCE = {"market": 600, "paper": 600, "jobs": 3600, "trainer": 2400}
NAMES = {"market": "Bozor ma'lumoti", "paper": "Paper savdo", "jobs": "Vazifalar (backtest, AI)", "trainer": "AI o'qitish"}
REPEAT_SECONDS = 6 * 3600
CANDLE_GRACE = 900
DISK_LIMIT_PCT = 90.0


def find_problems(s, data_dir: Path, now: float | None = None) -> dict[str, str]:
    now = time.time() if now is None else now
    wall = utcnow().timestamp()
    skew = now - time.time()
    out: dict[str, str] = {}
    for h in s.query(ComponentHeartbeat):
        limit = SILENCE.get(h.name)
        if limit is None:
            continue
        silent = wall + skew - h.at.timestamp()
        if silent > limit:
            out[f"worker:{h.name}"] = f"{NAMES[h.name]} {int(silent // 60)} daqiqadan beri javob bermayapti"
    latest: dict[str, int] = {}
    for tf, ts in s.query(PaperSession.timeframe, PaperSession.last_candle_ts).filter(PaperSession.status == "running"):
        latest[tf] = max(latest.get(tf, 0), ts)
    for tf, ts in latest.items():
        step = TIMEFRAMES.get(tf)
        if step and ts + 2 * step + CANDLE_GRACE < now:
            out[f"candles:{tf}"] = f"{tf} sessiyalar yangi sham olmayapti, oxirgisidan {int((now - ts - step) // 3600)} soat o'tdi"
    path = Path(data_dir)
    disk = shutil.disk_usage(path if path.exists() else "/")
    used = disk.used / disk.total * 100
    if used >= DISK_LIMIT_PCT:
        out["disk"] = f"Serverda disk {used:.0f}% to'lgan"
    return out


def check(db, data_dir: Path, now: float | None = None) -> int:
    """Sends new problems, repeats unresolved ones rarely, and reports recovery. Returns messages made."""
    now = time.time() if now is None else now
    made = 0
    with db.session() as s:
        row = s.get(SystemSetting, "watchdog")
        seen: dict = dict(row.value) if row and row.value else {}
        problems = find_problems(s, data_dir, now)
        due = {k: v for k, v in problems.items() if now - seen.get(k, 0) >= REPEAT_SECONDS}
        if due:
            notify(s, "system", "Tizimda muammo", "\n".join(due.values()) + "\nReal savdo o'chiq. Tekshirish uchun menga yozing.", "err", "monitoring")
            made += 1
        recovered = [k for k in seen if k not in problems]
        if recovered:
            notify(s, "system", "Muammo tuzaldi", "Tizim yana normal ishlayapti.", "ok", "monitoring")
            made += 1
        kept = {k: t for k, t in seen.items() if k in problems}
        kept.update({k: now for k in due})
        s.merge(SystemSetting(key="watchdog", value=kept))
    return made
