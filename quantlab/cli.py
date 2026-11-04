"""Operator commands: python -m quantlab.cli <command>"""

from __future__ import annotations

import argparse
import getpass
import time

from quantlab.api.auth import hash_password
from quantlab.config import TIMEFRAMES, get_settings
from quantlab.db import Database
from quantlab.market.binance import BinancePublic
from quantlab.market.store import CandleStore
from quantlab.models import User
from quantlab.services import refresh_universe, seed, sync_dataset


def main() -> None:
    ap = argparse.ArgumentParser(prog="quantlab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("set-owner-password")
    d = sub.add_parser("download")
    d.add_argument("--timeframe", default="1h")
    d.add_argument("--days", type=int, default=365)
    d.add_argument("--pairs", default="")
    a = ap.parse_args()
    st = get_settings()
    if a.cmd == "migrate":
        from pathlib import Path

        from alembic import command
        from alembic.config import Config

        cfg = Config(str(Path(__file__).parent / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", st.database_url.replace("%", "%%"))
        command.upgrade(cfg, "head")
        print("schema up to date")
        return
    db = Database(st.database_url)
    if a.cmd == "set-owner-password":
        pw = getpass.getpass("New owner password (min 12): ")
        if len(pw) < 12:
            raise SystemExit("too short")
        with db.session() as s:
            u = s.query(User).filter_by(username="owner").one_or_none()
            if u is None:
                s.add(User(username="owner", display_name="Owner", password_hash=hash_password(pw)))
            else:
                u.password_hash, u.failed_logins, u.locked_until = hash_password(pw), 0, None
        print("password set")
    elif a.cmd == "download":
        seed(db, st)
        client = BinancePublic(st.binance_public_url)
        store = CandleStore(st.data_dir, client)
        refresh_universe(db, client)
        since = int(time.time()) - a.days * 86400
        for p in (a.pairs.split(",") if a.pairs else st.watchlist):
            rep = sync_dataset(db, store, p, a.timeframe, since)
            print(f"{p} {a.timeframe}: {rep.rows} candles, {len(rep.gaps)} gaps, {rep.duplicates} duplicates, {rep.invalid} invalid")


if __name__ == "__main__":
    main()
