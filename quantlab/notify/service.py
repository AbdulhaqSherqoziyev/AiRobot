"""Notifications live in the database; Telegram is an optional extra delivery channel.
A Telegram failure can never affect trading or the web application."""

from __future__ import annotations

import logging

import httpx

from quantlab.models import Notification, SystemLog, SystemSetting

log = logging.getLogger(__name__)
# Defaults for what is forwarded to Telegram; the owner edits this in Settings.
DEFAULT_PREFS = {"trade": True, "daily": True, "backtest": True, "paper": True, "live": True, "risk": True, "system": True, "ml": True, "evaluation": True}


def notify(s, category: str, title: str, text: str = "", tone: str = "info", route: str = "dashboard") -> None:
    s.add(Notification(category=category, title=title, text=text, tone=tone, route=route))


def syslog(s, level: str, component: str, message: str) -> None:
    s.add(SystemLog(level=level, component=component, message=message[:4000]))


ICONS = {"paper": "🧪", "evaluation": "📊", "daily": "📊", "ml": "🧠", "backtest": "🔬", "optimizer": "🔬", "risk": "⚠️", "system": "🛠", "live": "🔴", "trade": "🔴"}


def format_message(n) -> str:
    """Short and readable: what happened first, details below."""
    icon = ICONS.get(n.category, "ℹ️")
    return f"{icon} {n.title}\n{n.text}".strip()[:3900]


def _virtual_alert(n) -> bool:
    return n.category in ("risk", "system") and n.route == "paper"


def group_virtual_alerts(rows: list) -> str:
    """Many virtual sessions can stop on one candle. That is one piece of news, not many."""
    names = [r.title.split(": ", 1)[-1] for r in rows]
    shown = ", ".join(names[:3]) + (f" va yana {len(names) - 3} ta" if len(names) > 3 else "")
    return f"⚠️ TEST: {len(rows)} ta virtual sessiya to'xtadi\n{shown}\nReal pulga ta'siri yo'q. Davom ettirish panelda."[:3900]


def dispatch_telegram(db, token: str, chat_id: str, client: httpx.Client | None = None, limit: int = 100) -> int:
    if not token or not chat_id:
        return 0
    client = client or httpx.Client(timeout=10)
    sent = 0

    def send(text: str) -> bool:
        # The URL contains the token, so only the status code or error type is logged.
        try:
            res = client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text})
        except httpx.HTTPError as exc:
            log.warning("telegram unreachable: %s", type(exc).__name__)
            return False
        if res.status_code != 200:
            log.warning("telegram send failed: HTTP %s", res.status_code)
            return False
        return True

    with db.session() as s:
        row = s.get(SystemSetting, "notifications")
        prefs = {**DEFAULT_PREFS, **(row.value if row else {})}
        pending = []
        for n in s.query(Notification).filter_by(telegram_sent=False).order_by(Notification.id).limit(limit):
            if prefs.get(n.category, True):
                pending.append(n)
            else:
                n.telegram_sent = True
        alerts = [n for n in pending if _virtual_alert(n)]
        if alerts:
            if not send(group_virtual_alerts(alerts)):
                return sent
            sent += 1
            for n in alerts:
                n.telegram_sent = True
        for n in pending:
            if n.telegram_sent:
                continue
            if not send(format_message(n)):
                break
            n.telegram_sent = True
            sent += 1
    return sent
