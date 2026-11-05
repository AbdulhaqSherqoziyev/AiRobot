"""Routes for external-integration features: experiments, order-book metrics, AI reports and
integration status. All are read-only towards trading: nothing here can create an order, start a
session, change a limit or reach the live engine."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

from quantlab import integrations as integ
from quantlab.ai_analysis import service as ai
from quantlab.api import snapshot as snap
from quantlab.config import TIMEFRAMES, Settings
from quantlab.db import Database
from quantlab.market.binance import BinanceError, BinancePublic
from quantlab.market.microstructure import MicrostructureMonitor
from quantlab.market.store import CandleStore
from quantlab.models import AiReport, EvaluationReport, Experiment, ExperimentResult
from quantlab.research import sweep as sw
from quantlab.research import vbt_adapter
from quantlab.services import enqueue
from quantlab.strategies import interop
from quantlab.strategies.base import get_strategy

MAX_PAIRS = 9


class ExperimentCreate(BaseModel):
    name: str = Field("", max_length=128)
    strategy: str
    pairs: list[str] = Field(min_length=1, max_length=MAX_PAIRS)
    timeframe: str = "4h"
    start_ts: int
    end_ts: int
    grid: dict[str, list[float]] = {}
    backend: str = "vectorbt"
    fee: float = Field(0.001, ge=0, le=0.05)
    slippage: float = Field(0.0005, ge=0, le=0.05)
    stake_pct: float = Field(0.95, gt=0, le=1)
    stoploss_pct: float = Field(0.0, ge=0, lt=1)
    train: float = Field(0.6, gt=0, lt=1)
    validation: float = Field(0.2, gt=0, lt=1)
    folds: int = Field(4, ge=2, le=12)
    min_trades: int = Field(5, ge=1, le=500)


class SwitchBody(BaseModel):
    enabled: bool


class AiCreate(BaseModel):
    pair: str
    timeframe: str = "4h"
    engine: str = "rule_baseline"


def _exp_row(e: Experiment) -> dict:
    s = e.summary or {}
    return {
        "id": e.id, "job_id": e.job_id, "name": e.name, "strategy": e.strategy_key, "version": e.strategy_version, "pairs": e.pairs, "timeframe": e.timeframe,
        "start_ts": e.start_ts, "end_ts": e.end_ts, "backend": e.backend, "status": e.status, "error": e.error, "n_combos": e.n_combos, "runtime_s": e.runtime_s,
        "created": snap.ts(e.created_at), "config": e.config, "selected": s.get("selected"), "test": s.get("test_pooled"),
        "eligibility": (s.get("eligibility") or {}).get("status"), "wf_positive_share": (s.get("walk_forward") or {}).get("positive_share"),
        "stability": (s.get("sensitivity") or {}).get("stability"), "engine_gap": s.get("engine_gap_max_pct"),
    }


def _ai_row(r: AiReport, full: bool = False) -> dict:
    row = {
        "id": r.id, "created": snap.ts(r.created_at), "pair": r.pair, "timeframe": r.timeframe, "engine": r.engine, "model": r.model, "status": r.status, "error": r.error,
        "stance": (r.recommendation or {}).get("stance"), "confidence": ((r.recommendation or {}).get("confidence") or {}).get("level"), "usage": r.usage, "latency_s": r.latency_s,
        "last_candle_ts": r.last_candle_ts, "reference_price": r.reference_price, "outcome": r.outcome, "outcome_at": snap.ts(r.outcome_at),
    }
    if full:
        row.update(recommendation=r.recommendation, data_pack=r.data_pack)
    return row


def register(app: FastAPI, db: Database, settings: Settings, store: CandleStore, client: BinancePublic, owner) -> None:
    monitor = MicrostructureMonitor(lambda pair, limit: client.depth(pair, limit))

    def require(key: str) -> None:
        with db.session() as s:
            if not integ.is_enabled(s, key):
                raise HTTPException(409, f"{integ.MANIFEST[key]['name']} integratsiyasi o'chirilgan")

    # ---- status and switches ----
    @app.get("/integrations")
    def list_integrations(_: str = Depends(owner)):
        with db.session() as s:
            return integ.status(s, settings, snap.ts)

    @app.post("/integrations/{key}")
    def switch(key: str, body: SwitchBody, _: str = Depends(owner)):
        if key not in integ.MANIFEST:
            raise HTTPException(404)
        with db.session() as s:
            integ.set_enabled(s, key, body.enabled)
        return {"ok": True}

    @app.get("/jesse/compatibility")
    def jesse_compat(_: str = Depends(owner)):
        require("jesse")
        return {**interop.compatibility_report(), "specs": interop.JESSE_SPECS}

    # ---- microstructure ----
    @app.get("/market/microstructure")
    def microstructure(pair: str, notional: float = Query(100.0, gt=0, le=1_000_000), _: str = Depends(owner)):
        require("hummingbot")
        return monitor.get(pair, round(notional, 2), settings.default_fee)

    # ---- experiments ----
    @app.get("/experiments/presets")
    def presets(_: str = Depends(owner)):
        return {"presets": sw.PRESETS, "backends": {"vectorbt": bool(vbt_adapter.available()), "native": True}, "limits": sw.MAX_COMBOS, "gates": sw.GATES}

    @app.post("/experiments")
    def create_experiment(body: ExperimentCreate, _: str = Depends(owner)):
        if body.timeframe not in TIMEFRAMES:
            raise HTTPException(400, "unsupported timeframe")
        if body.end_ts <= body.start_ts:
            raise HTTPException(400, "tugash vaqti boshlanishdan keyin bo'lishi kerak")
        try:
            strat = get_strategy(body.strategy)
            cfg = sw.SweepConfig(fee=body.fee, slippage=body.slippage, stake_pct=body.stake_pct, stoploss_pct=body.stoploss_pct, train=body.train, validation=body.validation, folds=body.folds, min_trades=body.min_trades, backend=body.backend)
            combos = sw.expand_grid(strat, body.grid)
        except KeyError:
            raise HTTPException(404, "strategiya topilmadi") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        if strat.kind == "ml":
            raise HTTPException(400, "ML strategiyalar uchun sweep yo'q")
        if len(combos) > sw.MAX_COMBOS[body.backend]:
            raise HTTPException(400, f"{len(combos)} ta kombinatsiya: {body.backend} uchun chegara {sw.MAX_COMBOS[body.backend]}")
        if body.backend == "vectorbt":
            require("vectorbt")
            if not vbt_adapter.available():
                raise HTTPException(409, "vectorbt o'rnatilmagan: native dvigatelni tanlang")
        if body.strategy.startswith("jesse_"):
            require("jesse")
        with db.session() as s:
            j = enqueue(s, "sweep", {})
            e = Experiment(job_id=j.id, name=body.name, strategy_key=body.strategy, strategy_version=strat.version, pairs=body.pairs, timeframe=body.timeframe, start_ts=body.start_ts, end_ts=body.end_ts, backend=body.backend, grid=body.grid, config=asdict(cfg), n_combos=len(combos))
            s.add(e)
            s.flush()
            j.payload = {"experiment_id": e.id}
            return {"id": e.id, "job_id": j.id, "n_combos": len(combos)}

    @app.get("/experiments")
    def list_experiments(limit: int = Query(100, le=500), _: str = Depends(owner)):
        with db.session() as s:
            return [_exp_row(e) for e in s.query(Experiment).order_by(Experiment.id.desc()).limit(limit)]

    def _get_exp(s, eid: int) -> Experiment:
        e = s.get(Experiment, eid)
        if e is None:
            raise HTTPException(404, "tajriba topilmadi")
        return e

    @app.get("/experiments/{eid}")
    def get_experiment(eid: int, _: str = Depends(owner)):
        with db.session() as s:
            e = _get_exp(s, eid)
            return {**_exp_row(e), "grid": e.grid, "summary": e.summary, "repro": e.repro}

    @app.get("/experiments/{eid}/results")
    def experiment_results(eid: int, limit: int = Query(200, ge=1, le=3000), offset: int = Query(0, ge=0), _: str = Depends(owner)):
        with db.session() as s:
            _get_exp(s, eid)
            q = s.query(ExperimentResult).filter_by(experiment_id=eid).order_by(ExperimentResult.rank)
            return {"total": q.count(), "rows": [{"rank": r.rank, "selected": r.selected, "params": r.params, "train": r.train, "validation": r.validation} for r in q.offset(offset).limit(limit)]}

    @app.get("/experiments/{eid}/export.csv")
    def export_experiment(eid: int, _: str = Depends(owner)):
        with db.session() as s:
            e = _get_exp(s, eid)
            rows = s.query(ExperimentResult).filter_by(experiment_id=eid).order_by(ExperimentResult.rank).all()
            keys = sorted({k for r in rows for k in r.params})
            buf = io.StringIO()
            w = csv.writer(buf)
            metrics = sw.METRICS
            w.writerow(["experiment_id", "strategy", "version", "rank", "selected", *keys, *[f"train_{m}" for m in metrics], *[f"validation_{m}" for m in metrics]])
            for r in rows:
                w.writerow([e.id, e.strategy_key, e.strategy_version, r.rank, r.selected, *[r.params.get(k) for k in keys], *[r.train.get(m) for m in metrics], *[r.validation.get(m) for m in metrics]])
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="experiment-{eid}.csv"'})

    # ---- unified evaluation ----
    @app.get("/strategy-evaluation")
    def strategy_evaluation(_: str = Depends(owner)):
        """Latest finished experiment per strategy and timeframe, next to the paper report. Sorted
        by id only, so no column silently becomes the ranking."""
        with db.session() as s:
            latest: dict[tuple, Experiment] = {}
            for e in s.query(Experiment).filter(Experiment.status == "done").order_by(Experiment.id):
                latest[(e.strategy_key, e.timeframe)] = e
            rows = [{**_exp_row(e), "checks": ((e.summary or {}).get("eligibility") or {}).get("checks", []), "regimes": (e.summary or {}).get("regimes_covered", []), "monte_carlo": (e.summary or {}).get("monte_carlo"), "test_by_pair": (e.summary or {}).get("test_by_pair")} for e in latest.values()]
            rep = s.query(EvaluationReport).order_by(EvaluationReport.id.desc()).first()
            paper = {"id": rep.id, "created": snap.ts(rep.created_at), "is_final": rep.is_final, "rows": rep.rows, "recommendation": rep.recommendation} if rep else None
            counts = {st: s.query(Experiment).filter(Experiment.status == st).count() for st in ("done", "error", "cancelled", "running", "queued")}
        return {"experiments": rows, "paper_report": paper, "counts": counts, "gates": sw.GATES, "live": "qulflangan: 30 kunlik hisobot va egasining tasdig'i kerak"}

    # ---- AI research ----
    @app.get("/ai/status")
    def ai_status(_: str = Depends(owner)):
        with db.session() as s:
            health = integ.health("tradingagents", True, settings)
            return {"enabled": integ.is_enabled(s, "tradingagents"), "engines": health["engines"], "usage_24h": ai.usage_today(s), "limits": {"calls": settings.ai_daily_calls, "usd": settings.ai_daily_usd, "max_tokens": settings.ai_max_tokens, "timeout_s": settings.ai_timeout_s}, "model": settings.ai_model, "scoreboard": ai.scoreboard(s)}

    @app.post("/ai/reports")
    def create_ai_report(body: AiCreate, _: str = Depends(owner)):
        require("tradingagents")
        if body.timeframe not in TIMEFRAMES:
            raise HTTPException(400, "unsupported timeframe")
        allowed = integ.health("tradingagents", True, settings)["engines"]
        if body.engine not in allowed:
            raise HTTPException(409, f"{body.engine} sozlanmagan")
        micro = None
        try:
            with db.session() as s:
                if integ.is_enabled(s, "hummingbot"):
                    micro = monitor.get(body.pair, 100.0, settings.default_fee)
                if body.engine in ai.PAID_ENGINES:
                    ai.check_limits(s, settings)
                return {"job_id": enqueue(s, "ai_report", {"pair": body.pair, "timeframe": body.timeframe, "engine": body.engine, "micro": micro}).id}
        except ai.LimitExceeded as exc:
            raise HTTPException(429, str(exc)) from None
        except BinanceError as exc:  # pragma: no cover  the monitor already catches these
            raise HTTPException(502, str(exc)) from None

    @app.get("/ai/reports")
    def list_ai_reports(limit: int = Query(100, le=500), _: str = Depends(owner)):
        with db.session() as s:
            return [_ai_row(r) for r in s.query(AiReport).order_by(AiReport.id.desc()).limit(limit)]

    @app.get("/ai/reports/{rid}")
    def get_ai_report(rid: int, _: str = Depends(owner)):
        with db.session() as s:
            r = s.get(AiReport, rid)
            if r is None:
                raise HTTPException(404, "hisobot topilmadi")
            return _ai_row(r, full=True)

    @app.post("/ai/outcomes")
    def run_outcomes(_: str = Depends(owner)):
        with db.session() as s:
            return {"job_id": enqueue(s, "ai_outcomes", {}).id}
