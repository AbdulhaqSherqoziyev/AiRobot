"""REST API of the control centre. Everything except health and login needs the session
cookie, and every mutation also needs the X-QL header. No route ever returns a secret."""

from __future__ import annotations

import csv
import io
import time

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from quantlab import monitor
from quantlab.api import auth as A
from quantlab.api import snapshot as snap
from quantlab.backtest.core import ExecConfig
from quantlab.config import TIMEFRAMES, Settings, get_settings
from quantlab.db import Database
from quantlab.evaluation import approval
from quantlab.evaluation.report import DEFAULT_CRITERIA, generate_report, start_run
from quantlab.live import engine as live
from quantlab.live.crypto import encrypt
from quantlab.market.binance import BinancePublic
from quantlab.market.store import CandleStore
from quantlab.market.universe import UniverseRules, scan
from quantlab.ml.models import ALGOS
from quantlab.ml.training import promote
from quantlab.models import (BacktestSession, EvaluationReport, EvaluationRun, ExchangeConnection, Job, LiveOrder, LiveTrade, MarketDataset, ModelVersion, Notification, OptimizationJob, PaperSession, RiskEvent, Strategy, StrategyVersion, SystemLog, SystemSetting, TradingPair, TrainingJob, User)
from quantlab.notify.service import DEFAULT_PREFS, syslog
from quantlab.paper import engine as paper
from quantlab.services import enqueue, new_version, seed
from quantlab.strategies.base import get_strategy

COOKIE = "ql_session"


class Login(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current: str
    new: str = Field(min_length=12)


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    engine: str
    description: str = ""
    params: dict = {}
    pairs: list[str] = ["BTC/USDT"]
    timeframe: str = "1h"
    risk: dict = {}


class VersionCreate(BaseModel):
    params: dict = {}
    pairs: list[str]
    timeframe: str
    risk: dict = {}
    note: str = ""


class StrategyPatch(BaseModel):
    enabled: bool | None = None
    name: str | None = None
    description: str | None = None


class BacktestCreate(BaseModel):
    strategy_id: int
    pair: str
    timeframe: str
    start_ts: int
    end_ts: int
    initial: float = Field(100.0, gt=0)
    fee: float = Field(0.001, ge=0, le=0.05)
    slippage: float = Field(0.0005, ge=0, le=0.05)
    stake_pct: float | None = Field(None, gt=0, le=1)
    stoploss_pct: float | None = Field(None, ge=0, lt=1)
    takeprofit_pct: float | None = Field(None, ge=0)


class SessionCreate(BaseModel):
    strategy_id: int
    pair: str
    timeframe: str | None = None
    capital: float = Field(100.0, gt=0, le=1_000_000)
    fee: float = Field(0.001, ge=0, le=0.05)
    slippage: float = Field(0.0005, ge=0, le=0.05)
    name: str = ""


class TrainCreate(BaseModel):
    algo: str
    pair: str
    timeframe: str = "1h"
    horizon: int = Field(6, ge=1, le=100)
    name: str | None = None
    hyper: dict = {}
    candles: int = Field(8000, ge=1000, le=60000)


class OptimizeCreate(BaseModel):
    strategy_id: int
    pair: str
    timeframe: str = "1h"
    trials: int = Field(50, ge=5, le=2000)
    objective: str = "composite"
    ranges: dict = {}
    candles: int = Field(6000, ge=600, le=60000)
    oos_frac: float = Field(0.3, ge=0.1, le=0.6)
    min_trades: int = Field(10, ge=1)
    max_dd: float = Field(25.0, gt=0, le=100)


class EvalStart(BaseModel):
    capital: float = Field(100.0, gt=0)
    criteria: dict = {}
    duration_days: int = Field(30, ge=1, le=365)


class Authorize(BaseModel):
    environment: str = "live"
    report_id: int | None = None
    strategy_version_id: int
    pairs: list[str]
    max_capital: float
    max_position: float
    daily_loss_limit: float
    max_drawdown_pct: float
    fee_assumption: float = 0.001
    stop_conditions: dict = {}
    confirmation: str
    password: str


class LiveAction(BaseModel):
    environment: str = "live"
    password: str | None = None
    close_positions: bool = True


class Credentials(BaseModel):
    environment: str
    api_key: str = Field(min_length=8)
    api_secret: str = Field(min_length=8)


class SettingBody(BaseModel):
    value: dict


class PairBody(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z0-9]{2,20}/USDT$")
    enabled: bool = True


def create_app(settings: Settings | None = None, db: Database | None = None, client: BinancePublic | None = None) -> FastAPI:
    settings = settings or get_settings()
    if len(settings.secret_key) < 32:
        raise RuntimeError("QL_SECRET_KEY must be set to at least 32 characters")
    db = db or Database(settings.database_url)
    client = client or BinancePublic(settings.binance_public_url, retries=2)
    store = CandleStore(settings.data_dir, client)
    app = FastAPI(title="Quant Lab API", docs_url=None, redoc_url=None, openapi_url=None)
    seed(db, settings)
    if settings.owner_password:
        with db.session() as s:
            if not s.query(User).count():
                s.add(User(username="owner", display_name="Owner", password_hash=A.hash_password(settings.owner_password)))

    def owner(request: Request) -> str:
        name = A.read_token(settings.secret_key, request.cookies.get(COOKIE))
        if not name:
            raise HTTPException(401, "not authenticated")
        if request.method not in ("GET", "HEAD") and request.headers.get("x-ql") != "1":
            raise HTTPException(403, "missing X-QL header")
        return name

    def check_password(s, name: str, password: str | None) -> None:
        """Re-authentication for actions involving real money."""
        user = s.query(User).filter_by(username=name).one()
        if not password or not A.verify_password(password, user.password_hash):
            raise HTTPException(403, "parol noto'g'ri")

    def bad(exc: Exception):
        return HTTPException(400, str(exc))

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/auth/login")
    def login(body: Login, response: Response):
        with db.session() as s:
            user, why = A.attempt_login(s, body.username, body.password)
            name = user.username if user else None
        if why == "locked":
            raise HTTPException(429, "juda ko'p urinish, keyinroq qayta urinib ko'ring")
        if not name:
            raise HTTPException(401, "login yoki parol noto'g'ri")
        response.set_cookie(COOKIE, A.make_token(settings.secret_key, name), httponly=True, samesite="strict", secure=settings.secure_cookies, max_age=A.SESSION_SECONDS, path="/")
        return {"username": name}

    @app.post("/auth/logout")
    def logout(response: Response, _: str = Depends(owner)):
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/auth/me")
    def me(name: str = Depends(owner)):
        return {"username": name}

    @app.post("/auth/password")
    def change_password(body: PasswordChange, name: str = Depends(owner)):
        with db.session() as s:
            check_password(s, name, body.current)
            s.query(User).filter_by(username=name).one().password_hash = A.hash_password(body.new)
        return {"ok": True}

    @app.get("/snapshot")
    def snapshot(_: str = Depends(owner)):
        with db.session() as s:
            return snap.build(s, store)

    # ---- market ----
    @app.get("/market/candles")
    def candles(pair: str, timeframe: str = "1h", limit: int = Query(500, le=5000), _: str = Depends(owner)):
        if timeframe not in TIMEFRAMES:
            raise HTTPException(400, "unsupported timeframe")
        df = store.load(pair, timeframe).tail(limit)
        return [{"time": int(r.ts), "open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in df.itertuples()]

    @app.get("/market/klines")
    def klines(pair: str, timeframe: str = "1h", limit: int = Query(320, le=1000), _: str = Depends(owner)):
        """Live chart data straight from Binance, including the candle still forming."""
        if timeframe not in {*TIMEFRAMES, "1w"}:
            raise HTTPException(400, "unsupported timeframe")
        try:
            rows = client.klines(pair, timeframe, limit=limit)
        except Exception as exc:
            raise HTTPException(502, "binance unreachable") from exc
        return [{"time": int(k[0]) // 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])} for k in rows]

    @app.get("/system/ping")
    def system_ping(_: str = Depends(owner)):
        try:
            return {"latency_ms": round(client.ping())}
        except Exception:
            return {"latency_ms": None}

    @app.get("/market/universe")
    def universe(min_quote_volume: float = 20_000_000, max_spread_bps: float = 10, _: str = Depends(owner)):
        with db.session() as s:
            pairs = [p.symbol for p in s.query(TradingPair)]
        try:
            return scan(client, pairs, UniverseRules(min_quote_volume=min_quote_volume, max_spread_bps=max_spread_bps))
        except Exception as exc:
            raise HTTPException(502, f"binance: {exc}") from exc

    @app.get("/market/pairs")
    def pairs(_: str = Depends(owner)):
        with db.session() as s:
            return [{"symbol": p.symbol, "enabled": p.enabled, "min_notional": p.min_notional, "step_size": p.step_size, "volume": p.quote_volume_24h, "spread_bps": p.spread_bps, "volatility": p.volatility} for p in s.query(TradingPair)]

    @app.post("/market/pairs")
    def set_pair(body: PairBody, _: str = Depends(owner)):
        from quantlab.market.universe import screen_pair

        if body.enabled and (r := screen_pair(body.symbol)):
            raise HTTPException(400, r)
        with db.session() as s:
            p = s.query(TradingPair).filter_by(symbol=body.symbol).one_or_none()
            if p is None:
                s.add(TradingPair(symbol=body.symbol, enabled=body.enabled))
            else:
                p.enabled = body.enabled
        return {"ok": True}

    @app.post("/market/sync")
    def market_sync(pair: str, timeframe: str = "1h", since: int | None = None, _: str = Depends(owner)):
        with db.session() as s:
            return {"job_id": enqueue(s, "sync", {"pair": pair, "timeframe": timeframe, "since": since}).id}

    # ---- strategies ----
    @app.get("/engines")
    def engines(_: str = Depends(owner)):
        from quantlab.strategies.base import all_strategies

        return [e.describe() for e in all_strategies()]

    @app.post("/strategies")
    def create_strategy(body: StrategyCreate, _: str = Depends(owner)):
        try:
            eng = get_strategy(body.engine)
        except KeyError as exc:
            raise HTTPException(400, "unknown engine") from exc
        with db.session() as s:
            if s.query(Strategy).filter_by(name=body.name).count():
                raise HTTPException(409, "bu nomli strategiya mavjud")
            st = Strategy(name=body.name, engine=body.engine, kind=eng.kind, description=body.description or eng.description, color=eng.color)
            s.add(st)
            s.flush()
            try:
                v = new_version(s, st, {**{k: p.default for k, p in eng.params.items()}, **body.params}, body.pairs, body.timeframe, body.risk or {"stake_pct": 0.95, "stoploss_pct": eng.risk.stoploss_pct}, "created")
            except ValueError as exc:
                raise bad(exc) from exc
            st.current_version_id = v.id
            return {"id": st.id, "version_id": v.id}

    @app.patch("/strategies/{sid}")
    def patch_strategy(sid: int, body: StrategyPatch, _: str = Depends(owner)):
        with db.session() as s:
            st = s.get(Strategy, sid) or _404()
            for k, v in body.model_dump(exclude_none=True).items():
                setattr(st, k, v)
        return {"ok": True}

    @app.post("/strategies/{sid}/versions")
    def add_version(sid: int, body: VersionCreate, _: str = Depends(owner)):
        with db.session() as s:
            st = s.get(Strategy, sid) or _404()
            try:
                v = new_version(s, st, body.params, body.pairs, body.timeframe, body.risk, body.note)
            except ValueError as exc:
                raise bad(exc) from exc
            st.current_version_id = v.id
            return {"version_id": v.id, "version": v.version}

    @app.get("/strategies/{sid}/versions")
    def list_versions(sid: int, _: str = Depends(owner)):
        with db.session() as s:
            st = s.get(Strategy, sid) or _404()
            return [{"id": v.id, "version": v.version, "params": v.params(), "pairs": v.pairs, "timeframe": v.timeframe, "risk": v.risk, "note": v.note, "created": snap.ts(v.created_at), "current": v.id == st.current_version_id} for v in st.versions]

    @app.post("/strategies/{sid}/clone")
    def clone_strategy(sid: int, _: str = Depends(owner)):
        with db.session() as s:
            st = s.get(Strategy, sid) or _404()
            cur = s.get(StrategyVersion, st.current_version_id)
            name, n = f"{st.name} (nusxa)", 2
            while s.query(Strategy).filter_by(name=name).count():
                name, n = f"{st.name} (nusxa {n})", n + 1
            c = Strategy(name=name, engine=st.engine, kind=st.kind, description=st.description, color=st.color, enabled=False)
            s.add(c)
            s.flush()
            v = new_version(s, c, cur.params(), cur.pairs, cur.timeframe, cur.risk, f"cloned from {st.name} v{cur.version}")
            c.current_version_id = v.id
            return {"id": c.id, "name": name}

    @app.delete("/strategies/{sid}")
    def delete_strategy(sid: int, _: str = Depends(owner)):
        with db.session() as s:
            st = s.get(Strategy, sid) or _404()
            vids = [v.id for v in st.versions]
            used = s.query(PaperSession).filter(PaperSession.strategy_version_id.in_(vids)).count() + s.query(BacktestSession).filter(BacktestSession.strategy_version_id.in_(vids)).count()
            if used:
                # History must stay reproducible, so a used strategy can only be disabled.
                raise HTTPException(409, "strategiya tarixda ishlatilgan: uni faqat nofaol qilish mumkin")
            s.delete(st)
        return {"ok": True}

    # ---- backtests ----
    @app.post("/backtests")
    def create_backtest(body: BacktestCreate, _: str = Depends(owner)):
        if body.timeframe not in TIMEFRAMES:
            raise HTTPException(400, "unsupported timeframe")
        if body.end_ts <= body.start_ts:
            raise HTTPException(400, "end must be after start")
        with db.session() as s:
            st = s.get(Strategy, body.strategy_id) or _404()
            cfg = {k: v for k, v in body.model_dump().items() if k in ("initial", "fee", "slippage", "stake_pct", "stoploss_pct", "takeprofit_pct") and v is not None}
            b = BacktestSession(strategy_version_id=st.current_version_id, pair=body.pair, timeframe=body.timeframe, start_ts=body.start_ts, end_ts=body.end_ts, config=cfg)
            s.add(b)
            s.flush()
            j = enqueue(s, "backtest", {"session_id": b.id})
            return {"id": b.id, "job_id": j.id}

    @app.get("/backtests/{bid}")
    def get_backtest(bid: int, _: str = Depends(owner)):
        with db.session() as s:
            b = s.get(BacktestSession, bid) or _404()
            v = s.get(StrategyVersion, b.strategy_version_id)
            r = b.result
            cs = store.load(b.pair, b.timeframe, b.start_ts, b.end_ts)
            return {"id": b.id, "status": b.status, "progress": b.progress, "error": b.error, "pair": b.pair, "timeframe": b.timeframe, "start_ts": b.start_ts, "end_ts": b.end_ts, "config": b.config, "data_hash": b.data_hash, "strategy": v.strategy.name, "strategy_id": v.strategy_id, "version": v.version, "params": v.params(), "metrics": r.metrics if r else None, "trades": r.trades if r else [], "equity": r.equity if r else [], "monthly": r.monthly if r else [],
                    "candles": [{"time": int(c.ts), "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume} for c in cs.tail(3000).itertuples()] if r else []}

    @app.get("/backtests/{bid}/export.csv")
    def export_backtest(bid: int, _: str = Depends(owner)):
        with db.session() as s:
            b = s.get(BacktestSession, bid) or _404()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["entry_ts", "exit_ts", "entry_price", "exit_price", "qty", "fees", "pnl", "pnl_pct", "reason"])
            for t in (b.result.trades if b.result else []):
                w.writerow([t["entry_ts"], t["exit_ts"], t["entry_price"], t["exit_price"], t["qty"], t["fees"], t["pnl"], t["pnl_pct"], t["reason"]])
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="backtest-{bid}.csv"'})

    # ---- jobs ----
    @app.post("/jobs/{jid}/cancel")
    def cancel_job(jid: int, _: str = Depends(owner)):
        with db.session() as s:
            j = s.get(Job, jid) or _404()
            j.cancel_requested = True
            if j.status == "queued":
                j.status = "cancelled"
        return {"ok": True}

    @app.get("/jobs")
    def jobs(_: str = Depends(owner)):
        with db.session() as s:
            return [{"id": j.id, "kind": j.kind, "status": j.status, "progress": j.progress, "note": j.note, "error": j.error, "created": snap.ts(j.created_at), "finished": snap.ts(j.finished_at), "payload": j.payload} for j in s.query(Job).order_by(Job.id.desc()).limit(50)]

    # ---- paper ----
    @app.post("/paper/sessions")
    def create_session(body: SessionCreate, _: str = Depends(owner)):
        from quantlab.market.universe import screen_pair

        if (r := screen_pair(body.pair)):
            raise HTTPException(400, r)
        with db.session() as s:
            st = s.get(Strategy, body.strategy_id) or _404()
            ver = s.get(StrategyVersion, st.current_version_id)
            if st.kind == "ml" and not ver.params().get("model_path"):
                raise HTTPException(400, "bu ML strategiya uchun avval model versiyasini tanlang")
            try:
                ps = paper.create_session(s, ver, body.pair, body.timeframe or ver.timeframe, body.capital, body.name, body.fee, body.slippage)
            except ValueError as exc:
                raise bad(exc) from exc
            return {"id": ps.id}

    @app.post("/paper/sessions/{sid}/{action}")
    def session_action(sid: int, action: str, _: str = Depends(owner)):
        if action not in ("pause", "resume", "stop", "reset"):
            raise HTTPException(404)
        try:
            return {"status": paper.set_status(db, sid, action, store)}
        except ValueError as exc:
            raise bad(exc) from exc

    @app.get("/paper/sessions/{sid}/equity")
    def session_equity(sid: int, _: str = Depends(owner)):
        from quantlab.models import EquitySnapshot

        with db.session() as s:
            return [{"time": r.ts, "value": r.equity} for r in s.query(EquitySnapshot).filter_by(scope="paper", scope_id=sid).order_by(EquitySnapshot.ts)]

    # ---- ML ----
    @app.post("/ml/train")
    def train(body: TrainCreate, _: str = Depends(owner)):
        if body.algo not in ALGOS:
            raise HTTPException(400, f"algo must be one of {ALGOS}")
        with db.session() as s:
            j = enqueue(s, "train", {})
            t = TrainingJob(job_id=j.id, algo=body.algo, pair=body.pair, timeframe=body.timeframe)
            s.add(t)
            s.flush()
            j.payload = {"training_id": t.id, "horizon": body.horizon, "name": body.name, "hyper": body.hyper, "candles": body.candles}
            return {"job_id": j.id}

    @app.post("/ml/versions/{vid}/promote")
    def promote_version(vid: int, _: str = Depends(owner)):
        try:
            promote(db, vid)
        except ValueError as exc:
            raise bad(exc) from exc
        return {"ok": True}

    @app.post("/ml/versions/{vid}/attach/{sid}")
    def attach_model(vid: int, sid: int, _: str = Depends(owner)):
        """Creates a new strategy version pinned to this model; running sessions keep theirs."""
        with db.session() as s:
            mv = s.get(ModelVersion, vid) or _404()
            st = s.get(Strategy, sid) or _404()
            if st.kind != "ml":
                raise HTTPException(400, "only ML strategies take a model")
            if mv.status != "promoted":
                raise HTTPException(400, "avval modelni tasdiqlang (promote)")
            cur = s.get(StrategyVersion, st.current_version_id)
            v = new_version(s, st, {**cur.params(), "model_path": mv.artifact_path}, [mv.pair], mv.timeframe, cur.risk, f"model {mv.model.name} v{mv.version}")
            st.current_version_id, st.enabled = v.id, True
            return {"version_id": v.id}

    # ---- optimizer ----
    @app.post("/optimizer")
    def start_optimizer(body: OptimizeCreate, _: str = Depends(owner)):
        with db.session() as s:
            st = s.get(Strategy, body.strategy_id) or _404()
            if st.kind == "ml":
                raise HTTPException(400, "ML strategiyalar optimizatori hali yo'q")
            j = enqueue(s, "optimize", {})
            o = OptimizationJob(job_id=j.id, strategy_id=st.id, pair=body.pair, timeframe=body.timeframe, config=body.model_dump(exclude={"strategy_id", "pair", "timeframe"}))
            s.add(o)
            s.flush()
            j.payload = {"optimization_id": o.id}
            return {"id": o.id, "job_id": j.id}

    @app.post("/optimizer/{oid}/apply/{rank}")
    def apply_optimized(oid: int, rank: int, _: str = Depends(owner)):
        """Only configurations that passed the unseen period can become a strategy version."""
        with db.session() as s:
            o = s.get(OptimizationJob, oid) or _404()
            if not 0 <= rank < len(o.top):
                raise HTTPException(404)
            item = o.top[rank]
            if not item["eligible"]:
                raise HTTPException(400, "bu konfiguratsiya out-of-sample sinovidan o'tmagan")
            st = s.get(Strategy, o.strategy_id)
            cur = s.get(StrategyVersion, st.current_version_id)
            v = new_version(s, st, {**cur.params(), **item["params"]}, cur.pairs, cur.timeframe, cur.risk, f"optimizer #{oid} rank {rank}")
            st.current_version_id = v.id
            return {"version_id": v.id}

    # ---- evaluation and approval ----
    @app.get("/evaluation")
    def evaluation(_: str = Depends(owner)):
        with db.session() as s:
            run = s.query(EvaluationRun).filter(EvaluationRun.duration_days > 0).order_by(EvaluationRun.id.desc()).first()
            rep = s.query(EvaluationReport).filter_by(run_id=run.id).order_by(EvaluationReport.id.desc()).first() if run else None
            from datetime import timedelta

            return {
                "default_criteria": DEFAULT_CRITERIA, "confirmation": approval.CONFIRMATION, "hard_cap": approval.HARD_CAPITAL_CAP_USDT,
                "run": {"id": run.id, "status": run.status, "started": snap.ts(run.started_at), "ends": snap.ts(run.started_at + timedelta(days=run.duration_days)), "duration_days": run.duration_days, "criteria": run.criteria} if run else None,
                "report": {"id": rep.id, "is_final": rep.is_final, "created": snap.ts(rep.created_at), "rows": rep.rows, "recommendation": rep.recommendation} if rep else None,
                "authorization": _auth_view(s, "live"),
            }

    @app.post("/evaluation/start")
    def evaluation_start(body: EvalStart, _: str = Depends(owner)):
        try:
            return {"run_id": start_run(db, capital=body.capital, criteria=body.criteria, duration_days=body.duration_days)}
        except ValueError as exc:
            raise bad(exc) from exc

    @app.post("/evaluation/report")
    def evaluation_report(_: str = Depends(owner)):
        with db.session() as s:
            run = s.query(EvaluationRun).filter(EvaluationRun.duration_days > 0).order_by(EvaluationRun.id.desc()).first()
            if run is None:
                raise HTTPException(400, "baholash boshlanmagan")
            rid = run.id
        return {"report_id": generate_report(db, store, rid)}

    def _auth_view(s, env: str):
        a = approval.active_authorization(s, env)
        return {"id": a.id, "strategy_version_id": a.strategy_version_id, "pairs": a.pairs, "max_capital": a.max_capital, "max_position": a.max_position, "daily_loss_limit": a.daily_loss_limit, "max_drawdown_pct": a.max_drawdown_pct, "fee_assumption": a.fee_assumption, "stop_conditions": a.stop_conditions, "created": snap.ts(a.created_at)} if a else None

    def _env(env: str) -> str:
        if env not in ("live", "testnet"):
            raise HTTPException(400, "environment must be live or testnet")
        return env

    @app.post("/live/authorize")
    def authorize(body: Authorize, name: str = Depends(owner)):
        _env(body.environment)
        with db.session() as s:
            check_password(s, name, body.password)
        try:
            return {"id": approval.authorize(db, report_id=body.report_id, strategy_version_id=body.strategy_version_id, pairs=body.pairs, max_capital=body.max_capital, max_position=body.max_position, daily_loss_limit=body.daily_loss_limit, max_drawdown_pct=body.max_drawdown_pct, fee_assumption=body.fee_assumption, stop_conditions=body.stop_conditions, confirmation=body.confirmation, environment=body.environment)}
        except ValueError as exc:
            raise bad(exc) from exc

    @app.get("/live/status")
    def live_status(environment: str = "live", _: str = Depends(owner)):
        _env(environment)
        with db.session() as s:
            pf = live.get_portfolio(s, environment)
            tick = snap.prices(s)
            orders = [{"id": o.id, "client_id": o.client_order_id, "symbol": o.symbol, "side": o.side, "status": o.status, "quote": o.quote_qty, "base": o.base_qty, "error": o.error, "created": snap.ts(o.created_at)} for o in s.query(LiveOrder).filter_by(portfolio_id=pf.id).order_by(LiveOrder.id.desc()).limit(50)]
            trades = s.query(LiveTrade).filter_by(portfolio_id=pf.id).order_by(LiveTrade.id.desc()).limit(50).all()
            realized = sum(t.pnl for t in trades if t.exit_ts)
            opened = next((t for t in trades if not t.exit_ts), None)
            unreal = None
            if opened:
                p = snap.last_price(tick, opened.symbol[:-4] + "/USDT")
                unreal = opened.qty * p - opened.qty * opened.entry_price - opened.entry_fee if p else None
            return {
                "environment": environment, "master_enabled": settings.live_enabled if environment == "live" else True, "status": pf.status, "halt_reason": pf.halt_reason, "gate_reasons": approval.gate_reasons(s, settings, environment),
                "authorization": _auth_view(s, environment), "orders": orders, "realized": realized, "unrealized": unreal, "initial_capital": pf.initial_capital, "peak_equity": pf.peak_equity,
                "position": {"symbol": opened.symbol, "qty": opened.qty, "entry": opened.entry_price, "t": opened.entry_ts} if opened else None,
                "trades": [{"symbol": t.symbol, "entry_ts": t.entry_ts, "entry": t.entry_price, "exit_ts": t.exit_ts, "exit": t.exit_price, "qty": t.qty, "pnl": t.pnl, "reason": t.exit_reason} for t in trades],
                "risk_events": [{"rule": e.rule, "detail": e.detail, "at": snap.ts(e.created_at)} for e in s.query(RiskEvent).filter_by(scope="live", scope_id=pf.id).order_by(RiskEvent.id.desc()).limit(20)],
                "confirmation": approval.CONFIRMATION if environment == "live" else approval.TESTNET_CONFIRMATION,
            }

    @app.get("/live/balance")
    def live_balance(environment: str = "live", _: str = Depends(owner)):
        """Asks the exchange. Failure is reported, never a stale or made-up number."""
        from quantlab.worker import build_exchange

        _env(environment)
        ex = build_exchange(db, settings, environment)
        if ex is None:
            return {"connected": False, "balances": []}
        try:
            rows = [b for b in ex.account().get("balances", []) if float(b["free"]) + float(b["locked"]) > 0]
            return {"connected": True, "balances": rows}
        except Exception as exc:
            return {"connected": False, "error": type(exc).__name__, "balances": []}

    @app.post("/live/start")
    def live_start(body: LiveAction, name: str = Depends(owner)):
        _env(body.environment)
        if body.environment == "live":
            with db.session() as s:
                check_password(s, name, body.password)
        try:
            live.start(db, settings, body.environment)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        return {"ok": True}

    @app.post("/live/stop")
    def live_stop(body: LiveAction, _: str = Depends(owner)):
        live.stop(db, _env(body.environment))
        return {"ok": True}

    @app.post("/live/kill")
    def live_kill(body: LiveAction, _: str = Depends(owner)):
        # Deliberately no password: stopping must always be faster than starting.
        from quantlab.worker import build_exchange

        return live.kill_switch(db, _env(body.environment), build_exchange(db, settings, body.environment), body.close_positions)

    @app.post("/live/revoke")
    def live_revoke(body: LiveAction, _: str = Depends(owner)):
        approval.revoke(db, _env(body.environment))
        return {"ok": True}

    # ---- settings ----
    @app.get("/settings/credentials")
    def credentials(_: str = Depends(owner)):
        with db.session() as s:
            return [{"environment": c.environment, "hint": c.key_hint, "created": snap.ts(c.created_at)} for c in s.query(ExchangeConnection)]

    @app.put("/settings/credentials")
    def set_credentials(body: Credentials, name: str = Depends(owner)):
        _env(body.environment)
        with db.session() as s:
            row = s.query(ExchangeConnection).filter_by(environment=body.environment).one_or_none() or ExchangeConnection(environment=body.environment)
            row.api_key_enc, row.api_secret_enc = encrypt(settings.secret_key, body.api_key), encrypt(settings.secret_key, body.api_secret)
            row.key_hint = body.api_key[-4:]
            s.add(row)
            syslog(s, "WARNING", "settings", f"{name} stored {body.environment} API credentials")
        return {"ok": True}

    @app.delete("/settings/credentials/{environment}")
    def del_credentials(environment: str, _: str = Depends(owner)):
        with db.session() as s:
            s.query(ExchangeConnection).filter_by(environment=_env(environment)).delete()
        return {"ok": True}

    @app.get("/settings/{key}")
    def get_setting(key: str, _: str = Depends(owner)):
        with db.session() as s:
            row = s.get(SystemSetting, key)
            defaults = {"notifications": DEFAULT_PREFS}.get(key, {})
            return {**defaults, **(row.value if row else {})}

    @app.put("/settings/{key}")
    def put_setting(key: str, body: SettingBody, _: str = Depends(owner)):
        if key not in ("notifications", "trading", "risk", "profile", "system"):
            raise HTTPException(404)
        with db.session() as s:
            s.merge(SystemSetting(key=key, value=body.value))
        return {"ok": True}

    @app.get("/telegram/status")
    def telegram_status(_: str = Depends(owner)):
        return {"configured": bool(settings.telegram_token and settings.telegram_chat_id)}

    # ---- notifications ----
    @app.post("/notifications/read")
    def notif_read(ids: list[int] | None = None, _: str = Depends(owner)):
        with db.session() as s:
            q = s.query(Notification)
            if ids is not None:
                q = q.filter(Notification.id.in_(ids))
            q.update({"read": True}, synchronize_session=False)
        return {"ok": True}

    @app.delete("/notifications/{nid}")
    def notif_delete(nid: int, _: str = Depends(owner)):
        with db.session() as s:
            s.query(Notification).filter_by(id=nid).delete()
        return {"ok": True}

    # ---- monitoring ----
    @app.get("/system/monitor")
    def system_monitor(_: str = Depends(owner)):
        return monitor.snapshot(db, settings.data_dir, client)

    @app.get("/system/logs")
    def system_logs(level: str | None = None, limit: int = Query(200, le=1000), _: str = Depends(owner)):
        with db.session() as s:
            q = s.query(SystemLog)
            if level:
                q = q.filter_by(level=level)
            return [{"at": snap.ts(l.created_at), "level": l.level, "component": l.component, "message": l.message} for l in q.order_by(SystemLog.id.desc()).limit(limit)]

    return app


def _404():
    raise HTTPException(404, "not found")


def app_factory() -> FastAPI:
    return create_app()
