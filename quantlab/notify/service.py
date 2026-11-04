"""Notifications live in the database; Telegram is an optional extra delivery channel.
A Telegram failure can never affect trading or the web application."""

from __future__ import annotations

import logging

import httpx

from quantlab.models import Notification, SystemLog, SystemSetting

log = logging.getLogger(__name__)
# Defaults for what is forwarded to Telegram; the owner edits this in Settings.
DEFAULT_PREFS = {"trade": True, "daily": True, "backtest": True, "paper": True, "live": True, "risk": True, "system": True, "ml": False, "evaluation": True}


def notify(s, category: str, title: str, text: str = "", tone: str = "info", route: str = "dashboard") -> None:
    s.add(Notification(category=category, title=title, text=text, tone=tone, route=route))


def syslog(s, level: str, component: str, message: str) -> None:
    s.add(SystemLog(level=level, component=component, message=message[:4000]))


def dispatch_telegram(db, token: str, chat_id: str, client: httpx.Client | None = None, limit: int = 20) -> int:
    if not token or not chat_id:
        return 0
    client = client or httpx.Client(timeout=10)
    sent = 0
    with db.session() as s:
        row = s.get(SystemSetting, "notifications")
        prefs = {**DEFAULT_PREFS, **(row.value if row else {})}
        for n in s.query(Notification).filter_by(telegram_sent=False).order_by(Notification.id).limit(limit):
            if not prefs.get(n.category, True):
                n.telegram_sent = True
                continue
            try:
                res = client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": f"{n.title}\n{n.text}"[:4000]})
                if res.status_code == 200:
                    n.telegram_sent = True
                    sent += 1
                else:
                    # The URL contains the token, so only the status code is logged.
                    log.warning("telegram send failed: HTTP %s", res.status_code)
                    break
            except httpx.HTTPError as exc:
                log.warning("telegram unreachable: %s", type(exc).__name__)
                break
    return sent
