"""Background processes. Each role runs separately so one can restart without the others:

    python -m quantlab.worker market|paper|jobs|notify|live|trainer
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import threading
import time

from quantlab.config import TIMEFRAMES, Settings, get_settings
from quantlab.db import Database
from quantlab.market.binance import BinancePublic
from quantlab.market.store import CandleStore
from quantlab.market.stream import PriceStream
from quantlab.models import ExchangeConnection, LivePortfolio, PaperSession, StrategyVersion, SystemSetting, TradingPair, utcnow
from quantlab.notify.service import dispatch_telegram, notify, syslog
from quantlab.paper import engine as paper
from quantlab.services import JobRunner, heartbeat, refresh_universe, seed, sync_dataset

log = logging.getLogger("quantlab.worker")
RUN = threading.Event()
RUN.set()


def _stop(*_):
    RUN.clear()


def _wait(seconds: float) -> None:
    end = time.time() + seconds
    while RUN.is_set() and time.time() < end:
        time.sleep(min(0.5, seconds))


def _guard(fn, name: str):
    """A failure in one cycle is logged and retried. It never kills the process loop."""
    try:
        return fn()
    except Exception as exc:
        log.exception("%s cycle failed", name)
        return exc


def active_datasets(db: Database, base_tf: str = "1h") -> set[tuple[str, str]]:
    with db.session() as s:
        out = {(p.symbol, base_tf) for p in s.query(TradingPair).filter_by(enabled=True)}
        for ps in s.query(PaperSession).filter(PaperSession.status.in_(paper.ACTIVE)):
            out.add((ps.pair, ps.timeframe))
        from quantlab.evaluation.approval import active_authorization

        for env in ("live", "testnet"):
            if (a := active_authorization(s, env)):
                v = s.get(StrategyVersion, a.strategy_version_id)
                out.add((a.pairs[0], v.timeframe))
    return out


def run_market(db: Database, settings: Settings) -> None:
    client = BinancePublic(settings.binance_public_url)
    store = CandleStore(settings.data_dir, client)
    stream = PriceStream(settings.binance_ws_url, list(settings.watchlist))
    stop = asyncio.Event()
    loop = asyncio.new_event_loop()
    threading.Thread(target=lambda: loop.run_until_complete(stream.run(stop)), daemon=True).start()
    last_sync: dict[tuple[str, str], int] = {}
    last_universe = last_tick = 0.0
    while RUN.is_set():
        now = time.time()
        if now - last_universe > 3600:
            if not isinstance(_guard(lambda: refresh_universe(db, client), "universe"), Exception):
                last_universe = now
        if now - last_tick > 10:
            def tick():
                with db.session() as s:
                    pairs = [p.symbol for p in s.query(TradingPair).filter_by(enabled=True)]
                rows = client.tickers(pairs)
                with db.session() as s:
                    row = s.get(SystemSetting, "tickers") or SystemSetting(key="tickers")
                    row.value = {"at": int(time.time()), "rows": rows}
                    s.merge(row)
            _guard(tick, "tickers")
            last_tick = now
        for pair, tf in active_datasets(db):
            step = TIMEFRAMES[tf]
            boundary = int(now // step) * step
            if last_sync.get((pair, tf), 0) < boundary:
                def sync():
                    # First sync fetches about 8000 candles; afterwards only the new ones.
                    sync_dataset(db, store, pair, tf, since=boundary - step * 8000)
                if not isinstance(_guard(sync, f"sync {pair} {tf}"), Exception):
                    last_sync[(pair, tf)] = boundary
        heartbeat(db, "market", {"ws_connected": stream.connected, "ws_reconnects": stream.reconnects, "datasets": len(last_sync)})
        _wait(5)
    loop.call_soon_threadsafe(stop.set)


def run_paper(db: Database, settings: Settings) -> None:
    from quantlab.analysis import paper_digest

    store = CandleStore(settings.data_dir)
    while RUN.is_set():
        applied = _guard(lambda: paper.tick_all(db, store), "paper")
        _guard(lambda: paper_digest(db), "paper digest")
        heartbeat(db, "paper", {"applied": applied if isinstance(applied, int) else 0})
        _wait(10)


def run_jobs(db: Database, settings: Settings) -> None:
    client = BinancePublic(settings.binance_public_url)
    runner = JobRunner(db, settings, CandleStore(settings.data_dir, client))
    if (n := runner.recover()):
        log.info("requeued %s interrupted jobs", n)
    while RUN.is_set():
        busy = _guard(runner.run_one, "jobs")
        heartbeat(db, "jobs", {"busy": busy is True})
        if busy is not True:
            _wait(2)


def run_trainer(db: Database, settings: Settings) -> None:
    """Scheduled learning loop: retrain, try the best new models in virtual challenger sessions, review
    results daily, and keep the evaluation report current. New versions stay candidates, and nothing
    here touches real trading. The 30-day report can finish a run; only the owner can authorize."""
    import os

    from quantlab.analysis import generate, run_challengers
    from quantlab.evaluation.report import generate_report
    from quantlab.ml.plan import enqueue_training
    from quantlab.models import EvaluationRun, TrainingJob

    days = float(os.environ.get("QL_RETRAIN_DAYS", "7"))
    store = CandleStore(settings.data_dir)
    while RUN.is_set():
        with db.session() as s:
            row = s.get(SystemSetting, "trainer")
            last = (row.value or {}).get("last", 0) if row else 0
        if time.time() - last >= days * 86400:
            n = _guard(lambda: enqueue_training(db, list(settings.watchlist)), "trainer")
            if isinstance(n, int):
                with db.session() as s:
                    s.merge(SystemSetting(key="trainer", value={"last": int(time.time()), "queued": n}))
                    syslog(s, "INFO", "trainer", f"queued {n} training jobs")
        with db.session() as s:
            pending = s.query(TrainingJob).filter(TrainingJob.status.in_(("queued", "running"))).count()
        if not pending:
            _guard(lambda: run_challengers(db, store), "challengers")
        with db.session() as s:
            row = s.get(SystemSetting, "review")
            last_review = (row.value or {}).get("last", 0) if row else 0
        if time.time() - last_review >= 86400:
            def review():
                generate(db, store, list(settings.watchlist))
                with db.session() as s:
                    runs = [r.id for r in s.query(EvaluationRun).filter_by(status="running")]
                for rid in runs:
                    generate_report(db, store, rid)
            if not isinstance(_guard(review, "daily review"), Exception):
                with db.session() as s:
                    s.merge(SystemSetting(key="review", value={"last": int(time.time())}))
        heartbeat(db, "trainer", {"every_days": days, "pending_training": pending})
        _wait(600)


def run_notify(db: Database, settings: Settings) -> None:
    from quantlab.watchdog import check

    while RUN.is_set():
        _guard(lambda: check(db, settings.data_dir), "watchdog")
        _guard(lambda: dispatch_telegram(db, settings.telegram_token, settings.telegram_chat_id), "telegram")
        heartbeat(db, "notify", {"telegram": bool(settings.telegram_token)})
        _wait(15)


def build_exchange(db: Database, settings: Settings, environment: str):
    from quantlab.live.crypto import decrypt
    from quantlab.live.exchange import BinanceSpot

    with db.session() as s:
        row = s.query(ExchangeConnection).filter_by(environment=environment).one_or_none()
        if row is None:
            return None
        key, secret = decrypt(settings.secret_key, row.api_key_enc), decrypt(settings.secret_key, row.api_secret_enc)
    return BinanceSpot(settings.binance_live_url if environment == "live" else settings.binance_testnet_url, key, secret)


def run_live(db: Database, settings: Settings) -> None:
    """One process drives testnet and live independently. If it is down, nothing is sent."""
    from quantlab.live.engine import LiveEngine
    from quantlab.live.exchange import verify_key_is_safe

    client = BinancePublic(settings.binance_public_url)
    store = CandleStore(settings.data_dir)
    verified: set[str] = set()
    while RUN.is_set():
        with db.session() as s:
            running = [p.environment for p in s.query(LivePortfolio).filter(LivePortfolio.status != "stopped")]
        for env in running:
            def cycle(env=env):
                ex = build_exchange(db, settings, env)
                if ex is None:
                    return
                if env == "live" and env not in verified:
                    problems = verify_key_is_safe(ex)
                    if problems:
                        from quantlab.live.engine import get_portfolio
                        with db.session() as s:
                            pf = get_portfolio(s, env)
                            pf.status, pf.halt_reason = "halted", "unsafe key: " + "; ".join(problems)
                            notify(s, "live", "API kalit xavfsiz emas", "; ".join(problems), "err", "live")
                        return
                    verified.add(env)
                eng = LiveEngine(db, settings, store, ex, env)
                with db.session() as s:
                    from quantlab.evaluation.approval import active_authorization
                    a = active_authorization(s, env)
                    pair = a.pairs[0] if a else None
                price = None
                if pair:
                    price = float(client.tickers([pair])[0]["lastPrice"])
                eng.tick(last_price=price)
            _guard(cycle, f"live {env}")
        heartbeat(db, "live", {"environments": running})
        _wait(10)


ROLES = {"market": run_market, "paper": run_paper, "jobs": run_jobs, "notify": run_notify, "live": run_live, "trainer": run_trainer}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx logs request URLs at INFO, and Telegram URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    if role not in ROLES:
        sys.exit(f"usage: python -m quantlab.worker {'|'.join(ROLES)}")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    settings = get_settings()
    db = Database(settings.database_url)
    seed(db, settings)
    with db.session() as s:
        syslog(s, "INFO", role, f"{role} worker started")
    ROLES[role](db, settings)


if __name__ == "__main__":
    main()
