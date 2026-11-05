"""Runs an analyst under the limits, stores every attempt and scores past views. Failures are
stored too. Writes only to ai_reports."""

from __future__ import annotations

import time
from datetime import timedelta

from quantlab.ai_analysis import backends
from quantlab.ai_analysis.evidence import build_pack
from quantlab.ai_analysis.schema import InvalidRecommendation, check_against_pack
from quantlab.config import TIMEFRAMES, Settings
from quantlab.db import Database
from quantlab.market.store import CandleStore
from quantlab.models import AiReport, utcnow

PAID_ENGINES = {"claude", "tradingagents"}


class LimitExceeded(RuntimeError):
    pass


def usage_today(s) -> dict:
    since = utcnow() - timedelta(days=1)
    rows = s.query(AiReport).filter(AiReport.created_at >= since, AiReport.engine.in_(PAID_ENGINES)).all()
    return {"calls": len(rows), "usd": round(sum((r.usage or {}).get("usd") or 0 for r in rows), 4)}


def check_limits(s, settings: Settings) -> None:
    u = usage_today(s)
    if u["calls"] >= settings.ai_daily_calls:
        raise LimitExceeded(f"24 soatlik chaqiruv chegarasi: {u['calls']}/{settings.ai_daily_calls}")
    if u["usd"] >= settings.ai_daily_usd:
        raise LimitExceeded(f"24 soatlik xarajat chegarasi: ${u['usd']}/${settings.ai_daily_usd}")


def run_report(db: Database, store: CandleStore, settings: Settings, pair: str, timeframe: str, engine: str, micro: dict | None = None, client=None) -> int:
    if engine in PAID_ENGINES:
        with db.session() as s:
            check_limits(s, settings)
    df = store.load(pair, timeframe)
    pack = build_pack(df, pair, timeframe, micro)
    row = AiReport(pair=pair, timeframe=timeframe, engine=engine, status="error", data_pack=pack, last_candle_ts=pack["last_closed_candle_ts"], reference_price=pack["indicators"]["close"]["value"])
    started = time.monotonic()
    try:
        result = backends.make(engine, settings, client).analyze(pack)
        check_against_pack(result.recommendation, pack)
        row.status, row.recommendation, row.model, row.usage, row.raw = "ok", result.recommendation.model_dump(), result.model, result.usage, result.raw
    except (backends.AnalystError, InvalidRecommendation, ValueError, OSError) as exc:
        row.error = str(exc)[:2000]
    except Exception as exc:  # noqa: BLE001  SDK and subprocess errors end here; they must not lose the record
        row.error = f"{type(exc).__name__}: {exc}"[:2000]
    row.latency_s = round(time.monotonic() - started, 3)
    with db.session() as s:
        s.add(row)
        s.flush()
        return row.id


def score(stance: str, forward_return: float, adverse: float) -> dict:
    """Consider_long is right when price rose; stay_flat when it did not. No_view is not scored."""
    hit = None if stance == "no_view" else (forward_return > 0 if stance == "consider_long" else forward_return <= 0)
    return {"forward_return_pct": round(forward_return, 4), "max_adverse_pct": round(adverse, 4), "hit": hit}


def evaluate_outcomes(db: Database, store: CandleStore) -> int:
    """Fills in the outcome once the horizon has fully passed, on closed candles only."""
    done = 0
    with db.session() as s:
        pending = s.query(AiReport).filter(AiReport.status == "ok", AiReport.outcome_at.is_(None)).all()
        for r in pending:
            h = int(r.recommendation.get("horizon_candles", 20))
            step = TIMEFRAMES[r.timeframe]
            end = r.last_candle_ts + step * h
            if end + step > time.time():
                continue
            df = store.load(r.pair, r.timeframe, r.last_candle_ts + step, end)
            if len(df) < h:
                continue  # a gap in the data: wait for the sync rather than score on partial data
            last = float(df["close"].iloc[-1])
            r.outcome = score(r.recommendation["stance"], (last / r.reference_price - 1) * 100, (float(df["low"].min()) / r.reference_price - 1) * 100)
            r.outcome["horizon_end_ts"] = int(df["ts"].iloc[-1])
            r.outcome_at = utcnow()
            done += 1
    return done


def scoreboard(s) -> list[dict]:
    """Hit rate per engine next to how often price simply rose, so a rate has something to beat."""
    groups: dict[str, dict] = {}
    for r in s.query(AiReport).filter(AiReport.outcome_at.is_not(None)).all():
        g = groups.setdefault(r.engine, {"engine": r.engine, "scored": 0, "hits": 0, "no_view": 0, "rose": 0, "total": 0})
        g["total"] += 1
        g["rose"] += r.outcome["forward_return_pct"] > 0
        if r.outcome["hit"] is None:
            g["no_view"] += 1
        else:
            g["scored"] += 1
            g["hits"] += bool(r.outcome["hit"])
    for g in groups.values():
        g["hit_rate"] = round(g["hits"] / g["scored"] * 100, 1) if g["scored"] else None
        g["price_rose_rate"] = round(g["rose"] / g["total"] * 100, 1) if g["total"] else None
        g["enough_samples"] = g["scored"] >= 30
    return list(groups.values())
