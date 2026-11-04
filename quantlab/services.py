"""Application services shared by API and workers."""

from __future__ import annotations

import logging
import time
import traceback

from quantlab.backtest.engine import run_backtest
from quantlab.config import TIMEFRAMES, Settings
from quantlab.db import Database
from quantlab.market.binance import BinancePublic, parse_filters
from quantlab.market.store import CandleStore
from quantlab.market.universe import UniverseRules, scan
from quantlab.ml.training import train_version
from quantlab.models import BacktestResult, BacktestSession, ComponentHeartbeat, Job, MarketDataset, OptimizationJob, Strategy, StrategyParameter, StrategyVersion, TradingPair, TrainingJob, utcnow
from quantlab.notify.service import notify, syslog
from quantlab.optimize.search import optimize
from quantlab.risk.sizing import HISTORY_DAYS
from quantlab.strategies.base import all_strategies, get_strategy

log = logging.getLogger(__name__)
SEED_PAIR = "BTC/USDT"
# From .ai/research/2026-11-strategy-optimization.md: 1h lost heavily to costs, and volatility
# sizing helped on every timeframe. This reduces damage; it is not evidence of profit.
SEED_TF = "4h"
SEED_SIZING = {"mode": "vol_target", "target": 0.015}


def seed(db: Database, settings: Settings) -> None:
    """Idempotent: creates the watchlist and one row per registered strategy."""
    with db.session() as s:
        for p in settings.watchlist:
            if not s.query(TradingPair).filter_by(symbol=p).count():
                s.add(TradingPair(symbol=p))
        for st in all_strategies():
            if not st.seedable or s.query(Strategy).filter_by(engine=st.key).count():
                continue
            row = Strategy(name=st.name, engine=st.key, kind=st.kind, description=st.description, color=st.color, enabled=st.kind == "technical")
            s.add(row)
            s.flush()
            v = new_version(s, row, {k: p.default for k, p in st.params.items()}, [SEED_PAIR], SEED_TF, {"stake_pct": st.risk.stake_pct, "stoploss_pct": st.risk.stoploss_pct, "takeprofit_pct": st.risk.takeprofit_pct, "max_drawdown_pct": st.risk.max_drawdown_pct, "max_daily_loss_pct": st.risk.daily_loss_pct, "max_orders_per_hour": st.risk.max_orders_per_hour, "sizing": SEED_SIZING}, "initial")
            row.current_version_id = v.id


def new_version(s, strategy: Strategy, params: dict, pairs: list[str], timeframe: str, risk: dict, note: str = "") -> StrategyVersion:
    """Edits never mutate a version: results stay tied to the parameters that produced them."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unsupported timeframe {timeframe}")
    engine = get_strategy(strategy.engine)
    if timeframe not in engine.timeframes and timeframe not in ("1m", "5m"):
        raise ValueError(f"{engine.name} does not support {timeframe}")
    known = {k: v for k, v in params.items() if k not in ("model_path", "rules")}
    engine.resolve(known)  # raises on out-of-range values
    if strategy.engine == "rule_builder":
        from quantlab.strategies.rules import validate

        validate(params.get("rules") or {})
    n = (s.query(StrategyVersion).filter_by(strategy_id=strategy.id).count()) + 1
    v = StrategyVersion(strategy_id=strategy.id, version=n, pairs=pairs, timeframe=timeframe, risk=risk, note=note)
    s.add(v)
    s.flush()
    for k, val in params.items():
        s.add(StrategyParameter(version_id=v.id, name=k, value=val))
    s.flush()
    return v


def enqueue(s, kind: str, payload: dict) -> Job:
    j = Job(kind=kind, payload=payload)
    s.add(j)
    s.flush()
    return j


def heartbeat(db: Database, name: str, detail: dict | None = None) -> None:
    with db.session() as s:
        row = s.get(ComponentHeartbeat, name)
        if row is None:
            s.add(ComponentHeartbeat(name=name, detail=detail or {}))
        else:
            row.at, row.detail = utcnow(), detail or {}


class JobCancelled(Exception):
    pass


class JobRunner:
    def __init__(self, db: Database, settings: Settings, store: CandleStore):
        self.db, self.settings, self.store = db, settings, store

    def recover(self) -> int:
        """Jobs left `running` by a crash go back in the queue."""
        with self.db.session() as s:
            rows = s.query(Job).filter_by(status="running").all()
            for j in rows:
                j.status, j.progress, j.note = "queued", 0.0, "restarted after worker restart"
            return len(rows)

    def claim(self) -> int | None:
        with self.db.session() as s:
            j = s.query(Job).filter_by(status="queued").order_by(Job.id).first()
            if j is None:
                return None
            if j.cancel_requested:
                j.status = "cancelled"
                return None
            j.status, j.started_at = "running", utcnow()
            return j.id

    def _progress(self, job_id: int):
        def update(frac: float, note: str | None = None) -> None:
            with self.db.session() as s:
                j = s.get(Job, job_id)
                j.progress = round(float(frac), 4)
                if note:
                    j.note = note
                if j.cancel_requested:
                    raise JobCancelled()
        return update

    def run_one(self) -> bool:
        job_id = self.claim()
        if job_id is None:
            return False
        with self.db.session() as s:
            j = s.get(Job, job_id)
            kind, payload = j.kind, dict(j.payload)
        try:
            result = getattr(self, f"_do_{kind}")(job_id, payload, self._progress(job_id))
            with self.db.session() as s:
                j = s.get(Job, job_id)
                j.status, j.progress, j.result, j.finished_at = "done", 1.0, result or {}, utcnow()
        except JobCancelled:
            with self.db.session() as s:
                j = s.get(Job, job_id)
                j.status, j.finished_at = "cancelled", utcnow()
                self._mark_related(s, kind, payload, "cancelled", "")
        except Exception as exc:
            log.exception("job %s failed", job_id)
            with self.db.session() as s:
                j = s.get(Job, job_id)
                j.status, j.error, j.finished_at = "error", f"{exc}"[:2000], utcnow()
                self._mark_related(s, kind, payload, "error", str(exc))
                syslog(s, "ERROR", "jobs", f"{kind} #{job_id}: {traceback.format_exc()[-1500:]}")
                notify(s, "system", f"Vazifa xato bilan tugadi: {kind}", str(exc)[:300], "err", "monitoring")
        return True

    def _mark_related(self, s, kind: str, payload: dict, status: str, error: str) -> None:
        if kind == "backtest" and (b := s.get(BacktestSession, payload["session_id"])):
            b.status, b.error = status, error[:2000]
        if kind == "optimize" and (o := s.get(OptimizationJob, payload["optimization_id"])):
            o.status = status
        if kind == "train" and (t := s.get(TrainingJob, payload["training_id"])):
            t.status = status

    def _ensure_data(self, pair: str, tf: str, since: int | None, progress=None) -> None:
        if self.store.client is None:
            return
        if progress:
            progress(0.02, "bozor ma'lumoti sinxronlanmoqda")
        sync_dataset(self.db, self.store, pair, tf, since)

    def _do_sync(self, job_id: int, p: dict, progress) -> dict:
        rep = sync_dataset(self.db, self.store, p["pair"], p["timeframe"], p.get("since"))
        return {"rows": rep.rows, "gaps": len(rep.gaps), "duplicates": rep.duplicates}

    def _do_backtest(self, job_id: int, p: dict, progress) -> dict:
        with self.db.session() as s:
            b = s.get(BacktestSession, p["session_id"])
            b.status = "running"
            ver = s.get(StrategyVersion, b.strategy_version_id)
            engine, params, risk = ver.strategy.engine, ver.params(), ver.risk or {}
            pair, tf, start, end, cfg, name = b.pair, b.timeframe, b.start_ts, b.end_ts, b.config, ver.strategy.name
        strat = get_strategy(engine)
        warm = max(strat.warmup * TIMEFRAMES[tf], HISTORY_DAYS * 86400)
        self._ensure_data(pair, tf, start - warm, progress)
        df = self.store.load(pair, tf, start - warm, end)
        if (df["ts"] >= start).sum() < 2:
            raise ValueError(f"{pair} {tf}: bu davr uchun ma'lumot yo'q")
        merged = {**params, **{k: v for k, v in risk.items() if k in ("stake_pct", "stoploss_pct", "takeprofit_pct", "sizing")}, **cfg}
        with self.db.session() as s:
            tp = s.query(TradingPair).filter_by(symbol=pair).one_or_none()
            if tp:
                merged.setdefault("min_notional", tp.min_notional)
                merged.setdefault("step_size", tp.step_size)
        out = run_backtest(strat, df, merged, tf, float(cfg.get("initial", 100.0)), start_ts=start, on_progress=lambda f: progress(0.1 + 0.85 * f))
        with self.db.session() as s:
            b = s.get(BacktestSession, p["session_id"])
            b.status, b.progress, b.finished_at, b.data_hash = "done", 1.0, utcnow(), CandleStore.data_hash(df)
            s.add(BacktestResult(session_id=b.id, metrics=out.metrics, trades=out.trades, equity=[[t, round(e, 6)] for t, e in out.equity], monthly=out.monthly))
            notify(s, "backtest", "Backtest yakunlandi", f"{name} · {pair} {tf}: {out.metrics['total_return']:.2f}%, {out.metrics['total_trades']} savdo", "ok", "backtest")
        return {"session_id": p["session_id"], "total_return": out.metrics["total_return"]}

    def _do_train(self, job_id: int, p: dict, progress) -> dict:
        with self.db.session() as s:
            t = s.get(TrainingJob, p["training_id"])
            t.status = "running"
            algo, pair, tf = t.algo, t.pair, t.timeframe
        self._ensure_data(pair, tf, int(time.time()) - TIMEFRAMES[tf] * int(p.get("candles", 8000)), progress)
        mv = train_version(self.db, self.settings.data_dir, self.store, algo, pair, tf, name=p.get("name"), horizon=int(p.get("horizon", 6)), hyper=p.get("hyper") or {}, progress=progress)
        with self.db.session() as s:
            t = s.get(TrainingJob, p["training_id"])
            t.status, t.model_version_id = "done", mv
            notify(s, "ml", "ML o'qitish yakunlandi", f"{algo} · {pair} {tf}: yangi versiya nomzod sifatida saqlandi", "ok", "ml")
        return {"model_version_id": mv}

    def _do_optimize(self, job_id: int, p: dict, progress) -> dict:
        with self.db.session() as s:
            o = s.get(OptimizationJob, p["optimization_id"])
            o.status = "running"
            st = s.get(Strategy, o.strategy_id)
            ver = s.get(StrategyVersion, st.current_version_id)
            engine, risk, pair, tf, cfg = st.engine, ver.risk or {}, o.pair, o.timeframe, dict(o.config)
        start = cfg.get("start_ts") or int(time.time()) - TIMEFRAMES[tf] * int(cfg.get("candles", 6000))
        self._ensure_data(pair, tf, start, progress)
        df = self.store.load(pair, tf, start, cfg.get("end_ts"))
        fixed = {k: v for k, v in risk.items() if k in ("stake_pct", "stoploss_pct", "takeprofit_pct", "sizing")}
        res = optimize(get_strategy(engine), df, tf, ranges=cfg.get("ranges"), trials=int(cfg.get("trials", 50)), objective=cfg.get("objective", "composite"), fixed=fixed, min_trades=int(cfg.get("min_trades", 10)), max_dd=float(cfg.get("max_dd", 25.0)), oos_frac=float(cfg.get("oos_frac", 0.3)), progress=lambda f: progress(0.05 + 0.9 * f))
        with self.db.session() as s:
            o = s.get(OptimizationJob, p["optimization_id"])
            o.status, o.top = "done", res["top"]
            o.config = {**o.config, "history": res["history"], "oos_start": res["oos_start"]}
            notify(s, "optimizer", "Optimizatsiya yakunlandi", f"{pair} {tf}: {res['trials']} sinov, OOS'dan o'tganlar {sum(1 for t in res['top'] if t['eligible'])} ta", "ok", "optimizer")
        return {"trials": res["trials"]}


def sync_dataset(db: Database, store: CandleStore, pair: str, tf: str, since: int | None = None):
    # Older data than the file holds needs a rebuild from `since`, since sync only appends.
    existing = store.load(pair, tf)
    if since is not None and len(existing) and int(existing["ts"].iloc[0]) > since + TIMEFRAMES[tf]:
        from quantlab.market.store import clean, klines_to_frame
        import pandas as pd

        frames, cursor, first = [], since, int(existing["ts"].iloc[0])
        while cursor < first:
            rows = store.client.klines(pair, tf, start_ms=cursor * 1000, end_ms=(first - 1) * 1000)
            if not rows:
                break
            b = klines_to_frame(rows)
            frames.append(b)
            cursor = int(b["ts"].iloc[-1]) + TIMEFRAMES[tf]
        if frames:
            merged, _ = clean(pd.concat([*frames, existing], ignore_index=True), tf)
            store.save(pair, tf, merged)
    try:
        rep = store.sync(pair, tf, since_ts=since)
    except Exception as exc:
        with db.session() as s:
            ds = _dataset(s, store, pair, tf)
            ds.last_error = str(exc)[:500]
        raise
    df = store.load(pair, tf)
    with db.session() as s:
        ds = _dataset(s, store, pair, tf)
        ds.rows, ds.gaps, ds.last_sync_at, ds.last_error = rep.rows, len(rep.gaps), utcnow(), ""
        ds.duplicates_dropped += rep.duplicates
        if len(df):
            ds.first_ts, ds.last_ts = int(df["ts"].iloc[0]), int(df["ts"].iloc[-1])
    return rep


def _dataset(s, store: CandleStore, pair: str, tf: str) -> MarketDataset:
    ds = s.query(MarketDataset).filter_by(symbol=pair, timeframe=tf).one_or_none()
    if ds is None:
        ds = MarketDataset(symbol=pair, timeframe=tf, source=store.source, path=str(store.path(pair, tf)))
        s.add(ds)
        s.flush()
    return ds


def refresh_universe(db: Database, client: BinancePublic, rules: UniverseRules | None = None) -> list[dict]:
    with db.session() as s:
        pairs = [p.symbol for p in s.query(TradingPair)]
    rows = scan(client, pairs, rules)
    with db.session() as s:
        for r in rows:
            p = s.query(TradingPair).filter_by(symbol=r["pair"]).one()
            p.min_notional, p.step_size, p.tick_size, p.quote_volume_24h, p.spread_bps, p.volatility = r["min_notional"], r["step_size"], r["tick_size"], r["quote_volume"], r["spread_bps"], r["volatility_pct"]
    return rows
