"""Daily review of what the running virtual sessions and models actually did. It observes and
recommends. It never changes a strategy, promotes a model or touches real trading."""

from __future__ import annotations

import math
from datetime import timezone

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import func

from quantlab.market.store import CandleStore
from quantlab.ml.features import build_features, build_labels
from quantlab.ml.training import classification
from quantlab.models import AnalysisReport, EquitySnapshot, ModelVersion, PaperSession, PaperTrade, Strategy, StrategyVersion, SystemSetting, utcnow
from quantlab.notify.service import notify
from quantlab.paper.engine import ACTIVE, base_asset, create_session, set_status
from quantlab.research.filters import uptrend
from quantlab.strategies import indicators as ind

MIN_TRADES = 30
# Hundreds of configurations run at once, so a single good one proves little. A plain 2-sigma
# bar would pass about 1 in 40 by luck alone; this one is deliberately harder.
CONFIDENT_T = 3.5
CHALLENGERS_KEPT = 3


def _epoch(dt) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def verdict(trades: int, t_stat: float | None, profit_factor: float | None) -> str:
    if trades < MIN_TRADES:
        return "namuna_kam"
    if t_stat is not None and t_stat >= CONFIDENT_T and (profit_factor or 0) > 1.3:
        return "umidli"
    if t_stat is not None and t_stat <= -2:
        return "zararli"
    return "noaniq"


def _session_row(s, store: CandleStore, ps: PaperSession, cache: dict) -> dict:
    ver = s.get(StrategyVersion, ps.strategy_version_id)
    trades = s.query(PaperTrade).filter(PaperTrade.session_id == ps.id, PaperTrade.exit_ts.isnot(None)).all()
    eq = [r.equity for r in s.query(EquitySnapshot).filter_by(scope="paper", scope_id=ps.id).order_by(EquitySnapshot.ts)]
    init = ps.portfolio.initial_balance
    last = eq[-1] if eq else init
    peak = np.maximum.accumulate(eq) if eq else np.array([init])
    dd = float(((np.array(eq) / peak) - 1).min() * 100) if eq else 0.0
    key = (ps.pair, ps.timeframe)
    if key not in cache:
        cache[key] = store.load(*key)
    df = cache[key]
    bh = None
    since = df[df["ts"] >= _epoch(ps.started_at)] if len(df) else df
    if len(since) > 1:
        bh = float((since["close"].iloc[-1] / since["open"].iloc[0] - 1) * 100)
    return {
        "strategy": ver.strategy.name, "kind": ver.strategy.kind, "timeframe": ps.timeframe, "pair": ps.pair, "session_id": ps.id,
        "return": (last / init - 1) * 100, "dd": dd, "bh": bh, "pnls": [t.pnl for t in trades], "pcts": [t.pnl_pct for t in trades],
        "fees": sum(t.entry_fee + t.exit_fee for t in trades), "days": (utcnow() - ps.started_at).total_seconds() / 86400,
    }


def strategy_table(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["strategy"], r["kind"], r["timeframe"]), []).append(r)
    out = []
    for (name, kind, tf), rs in groups.items():
        pcts = [p for r in rs for p in r["pcts"]]
        pnls = [p for r in rs for p in r["pnls"]]
        win, loss = sum(p for p in pnls if p > 0), -sum(p for p in pnls if p <= 0)
        pf = win / loss if loss > 0 else None
        t = None
        if len(pcts) > 2 and np.std(pcts) > 0:
            t = float(np.mean(pcts) / np.std(pcts, ddof=1) * math.sqrt(len(pcts)))
        bhs = [r["bh"] for r in rs if r["bh"] is not None]
        ret = float(np.median([r["return"] for r in rs]))
        out.append({
            "strategy": name, "kind": kind, "timeframe": tf, "sessions": len(rs), "trades": len(pcts), "median_return": round(ret, 3), "median_buy_hold": round(float(np.median(bhs)), 3) if bhs else None,
            "worst_drawdown": round(min(r["dd"] for r in rs), 3), "profit_factor": round(pf, 3) if pf is not None else None, "win_rate": round(sum(p > 0 for p in pnls) / len(pnls) * 100, 1) if pnls else None,
            "t_stat": round(t, 2) if t is not None else None, "fees": round(sum(r["fees"] for r in rs), 3), "days": round(max(r["days"] for r in rs), 1), "verdict": verdict(len(pcts), t, pf),
        })
    return sorted(out, key=lambda x: (x["trades"] < MIN_TRADES, -(x["t_stat"] if x["t_stat"] is not None else -99)))


def model_quality(s, store: CandleStore) -> list[dict]:
    """How models in virtual sessions predict on candles after their own training ended."""
    out = []
    seen = set()
    for ps in s.query(PaperSession).filter(PaperSession.status.in_(ACTIVE)):
        ver = s.get(StrategyVersion, ps.strategy_version_id)
        path = ver.params().get("model_path")
        if not path or path in seen:
            continue
        seen.add(path)
        mv = s.query(ModelVersion).filter_by(artifact_path=path).one_or_none()
        if mv is None:
            continue
        row = {"model": mv.model.name, "version": mv.version, "algo": mv.model.algo, "pair": mv.pair, "timeframe": mv.timeframe, "status": mv.status, "training_oos_auc": (mv.oos_metrics or {}).get("auc"), "validation_auc": (mv.validation_metrics or {}).get("auc"), "forward_samples": 0, "forward_auc": None, "note": ""}
        try:
            bundle = joblib.load(path)
            df = store.load(mv.pair, mv.timeframe)
            X = build_features(df)[bundle["features"]]
            y = build_labels(df, bundle.get("horizon", 6))
            created = _epoch(mv.created_at)
            mask = (df["ts"] > created) & X.notna().all(axis=1) & y.notna()
            row["forward_samples"] = int(mask.sum())
            if mask.sum() >= 50:
                m = classification(y[mask].to_numpy(), bundle["model"].predict_proba(X.to_numpy()[mask.to_numpy()]))
                row["forward_auc"] = m.get("auc")
                base = row["training_oos_auc"]
                if base is not None and m.get("auc") is not None and m["auc"] < base - 0.05:
                    row["note"] = "sifat pasaygan"
        except Exception as exc:  # one unreadable model must not stop the daily review
            row["note"] = f"tekshirib bo'lmadi: {type(exc).__name__}"
        out.append(row)
    return out


def market_state(store: CandleStore, pairs: list[str]) -> list[dict]:
    out = []
    for pair in pairs:
        df = store.load(pair, "1d")
        if len(df) < 60:
            continue
        adx = ind.adx(df, 14)[0].iloc[-1]
        up = bool(uptrend(df)[-1]) if len(df) > 210 else None
        rets = df["close"].pct_change()
        regime = "yonlama" if adx < 20 else ("o'sish" if up else "pasayish")
        out.append({"pair": pair, "regime": regime, "return_30d": round(float((df["close"].iloc[-1] / df["close"].iloc[-31] - 1) * 100), 2), "daily_vol": round(float(rets.tail(30).std() * 100), 2), "above_ema200": up})
    return out


def findings(table: list[dict], models: list[dict], market: list[dict], total: int) -> list[dict]:
    out = []
    enough = [r for r in table if r["trades"] >= MIN_TRADES]
    if not enough:
        most = max((r["trades"] for r in table), default=0)
        out.append({"tone": "info", "text": f"Namuna hali kam: eng ko'p savdoli guruhda {most} ta savdo, xulosa uchun kamida {MIN_TRADES} ta kerak."})
    good = [r for r in table if r["verdict"] == "umidli"]
    for r in good[:3]:
        out.append({"tone": "ok", "text": f"{r['strategy']} {r['timeframe']}: t={r['t_stat']}, PF={r['profit_factor']}. Kuzatishni davom ettirishga arziydi, bu foyda isboti emas."})
    for r in [x for x in table if x["verdict"] == "zararli"][:3]:
        out.append({"tone": "warn", "text": f"{r['strategy']} {r['timeframe']}: real narxlarda aniq zarar (t={r['t_stat']})."})
    beat = [r for r in enough if r["median_buy_hold"] is not None and r["median_return"] > r["median_buy_hold"]]
    if enough:
        out.append({"tone": "info", "text": f"Yetarli savdoli {len(enough)} guruhdan {len(beat)} tasi buy&hold'dan yuqori. Bu risk emas, faqat daromad taqqoslovi."})
    for m in [x for x in models if x["note"] == "sifat pasaygan"][:3]:
        out.append({"tone": "warn", "text": f"{m['model']} v{m['version']}: yangi ma'lumotda AUC {m['forward_auc']}, o'qitishda {m['training_oos_auc']}. Qayta o'qitish natijasini kuting."})
    if market:
        down = sum(1 for m in market if m["regime"] == "pasayish")
        out.append({"tone": "info", "text": f"Bozor: {len(market)} juftlikdan {down} tasi pasayish rejimida. Faqat long strategiyalar uchun bu noqulay."})
    out.append({"tone": "info", "text": f"{total} ta sessiya birga kuzatilmoqda: ular ko'p bo'lgani uchun eng yaxshisi tasodifan ham yaxshi ko'rinishi mumkin. Shu sababli ishonch chegarasi t ≥ {CONFIDENT_T}."})
    return out


def generate(db, store: CandleStore, pairs: list[str]) -> int:
    with db.session() as s:
        cache: dict = {}
        sessions = s.query(PaperSession).all()
        rows = [_session_row(s, store, ps, cache) for ps in sessions]
        table = strategy_table(rows)
        models = model_quality(s, store)
        market = market_state(store, pairs)
        found = findings(table, models, market, len(sessions))
        summary = {"sessions": len(sessions), "active": sum(1 for p in sessions if p.status in ACTIVE), "halted": sum(1 for p in sessions if p.status == "halted"), "closed_trades": sum(len(r["pnls"]) for r in rows), "promising": sum(1 for r in table if r["verdict"] == "umidli"), "live_recommendation": "Real savdo tavsiya etilmaydi: bu faqat 30 kunlik baholash va sizning tasdig'ingiz bilan ochiladi."}
        rep = AnalysisReport(summary=summary, strategies=table, models=models, market=market, findings=found)
        s.add(rep)
        s.flush()
        notify(s, "evaluation", "Kunlik tahlil tayyor", f"{summary['closed_trades']} ta yopiq savdo, {summary['promising']} ta umidli guruh", "info", "analysis")
        return rep.id


def start_challengers(db, min_auc: float = 0.0) -> tuple[int, list[int]]:
    """For each algorithm and timeframe, a virtual session for the newest training round's best model
    by validation AUC. Out-of-sample results are not used, so they stay an honest check. Models stay
    candidates: promotion remains the owner's decision. Older challengers beyond a limit are stopped."""
    created = 0
    to_stop: list[int] = []
    with db.session() as s:
        row = s.get(SystemSetting, "challengers")
        done_upto = (row.value or {}).get("version_id", 0) if row else 0
        new = s.query(ModelVersion).filter(ModelVersion.id > done_upto).all()
        if not new:
            return 0, []
        best: dict[tuple, ModelVersion] = {}
        for v in new:
            auc = (v.validation_metrics or {}).get("auc") or 0
            key = (v.model.algo, v.timeframe)
            if auc >= min_auc and (key not in best or auc > ((best[key].validation_metrics or {}).get("auc") or 0)):
                best[key] = v
        engines = {"lightgbm": "ml_lightgbm", "xgboost": "ml_xgboost", "random_forest": "ml_random_forest", "lstm": "ml_lstm", "rl": "ml_rl"}
        from quantlab.services import new_version

        for (algo, tf), v in sorted(best.items()):
            st = s.query(Strategy).filter_by(engine=engines[algo]).first()
            if st is None:
                continue
            cur = s.get(StrategyVersion, st.current_version_id)
            risk = {**(cur.risk or {}), "stake_pct": 0.95, "stoploss_pct": 0.03, "sizing": {"mode": "vol_target", "target": 0.015}}
            # A new version, but not made current: seeded strategies stay model-free until promotion.
            ver = new_version(s, st, {**cur.params(), "model_path": v.artifact_path}, [v.pair], tf, risk, f"challenger {v.model.name} v{v.version}")
            create_session(s, ver, v.pair, tf, 100.0, name=f"{algo} {base_asset(v.pair)} {tf} v{v.version}")
            created += 1
            same = [p for p in s.query(PaperSession).filter(PaperSession.status.in_(ACTIVE), PaperSession.timeframe == tf, PaperSession.strategy_version_id.in_(s.query(StrategyVersion.id).filter_by(strategy_id=st.id))).order_by(PaperSession.id.desc())]
            to_stop += [p.id for p in same[CHALLENGERS_KEPT:]]
        top = max(v.id for v in new)
        s.merge(SystemSetting(key="challengers", value={"version_id": top}))
    return created, to_stop


def run_challengers(db, store: CandleStore) -> int:
    created, to_stop = start_challengers(db)
    for sid in to_stop:
        set_status(db, sid, "stop", store)
    return created


def paper_digest(db, max_lines: int = 15) -> int:
    """One message for all new virtual fills, labelled as test money. Per-fill messages from
    hundreds of sessions closing on the same candle would bury anything that matters."""
    with db.session() as s:
        row = s.get(SystemSetting, "paper_digest")
        if row is None:
            # First run: start from now, so old history is not re-announced.
            last_id = s.query(func.max(PaperTrade.id)).scalar() or 0
            last_exit = s.query(func.max(PaperTrade.exit_ts)).scalar() or 0
            s.add(SystemSetting(key="paper_digest", value={"id": last_id, "exit_ts": last_exit}))
            return 0
        last_id, last_exit = row.value.get("id", 0), row.value.get("exit_ts", 0)
        opened = s.query(PaperTrade).filter(PaperTrade.id > last_id).order_by(PaperTrade.id).all()
        closed = s.query(PaperTrade).filter(PaperTrade.exit_ts > last_exit).order_by(PaperTrade.exit_ts).all()
        if not opened and not closed:
            return 0
        name = {p.id: p.name for p in s.query(PaperSession)}
        lines = [f"+ {name.get(t.session_id, t.session_id)}: {t.entry_price:g}" for t in opened]
        lines += [f"- {name.get(t.session_id, t.session_id)}: {t.pnl:+.2f} USDT ({t.exit_reason})" for t in closed]
        more = len(lines) - max_lines
        text = "\n".join(lines[:max_lines]) + (f"\n...yana {more} ta" if more > 0 else "")
        title = f"TEST (virtual pul): {len(opened)} ta ochildi, {len(closed)} ta yopildi, jami {sum(t.pnl for t in closed):+.2f} USDT"
        notify(s, "paper", title, text, "info", "trades")
        row.value = {"id": max([last_id, *[t.id for t in opened]]), "exit_ts": max([last_exit, *[t.exit_ts for t in closed]])}
        return len(opened) + len(closed)
