"""Everything the web screens read, computed from real rows. Strategies with no backtest
report nulls rather than numbers, so an empty system looks empty."""

from __future__ import annotations

import time
from datetime import timezone

import numpy as np
import pandas as pd

from quantlab.models import BacktestResult, BacktestSession, EquitySnapshot, Job, LiveTrade, ModelVersion, Notification, OptimizationJob, PaperSession, PaperTrade, Strategy, StrategyVersion, SystemSetting, TrainingJob
from quantlab.paper.engine import session_view

ICONS = {"backtest": "flask-conical", "risk": "triangle-alert", "system": "database", "paper": "circle-play", "ml": "brain", "optimizer": "sliders-horizontal", "live": "siren", "trade": "repeat", "daily": "calendar", "evaluation": "clipboard-check"}
TONES = {"ok": "#16C784", "info": "#60A5FA", "warn": "#F0B90B", "err": "#EA3943"}
PALETTE_ALLOC = ["#FFA841", "#9747FF", "#16B5CA", "#EC4899", "#3B82F6", "#16C784", "#F0B90B", "#60A5FA", "#EA3943"]


def ts(dt) -> int | None:
    return int(dt.replace(tzinfo=timezone.utc).timestamp()) if dt else None


def prices(s) -> dict[str, dict]:
    row = s.get(SystemSetting, "tickers")
    out = {}
    if row:
        for r in row.value.get("rows", []):
            sym = r["symbol"]
            if sym.endswith("USDT"):
                out[sym[:-4] + "/USDT"] = r
    return out


def last_price(tick: dict, pair: str) -> float | None:
    r = tick.get(pair)
    return float(r["lastPrice"]) if r else None


def daily_series(eq: list) -> list[dict]:
    if not eq:
        return []
    df = pd.Series([e for _, e in eq], index=pd.to_datetime([t for t, _ in eq], unit="s")).resample("1D").last().dropna()
    return [{"time": int(i.timestamp()), "value": float(v)} for i, v in df.items()]


def strategy_row(s, st: Strategy) -> dict:
    ver = s.get(StrategyVersion, st.current_version_id)
    b = None
    for v in sorted(st.versions, key=lambda v: -v.version):
        b = s.query(BacktestSession).filter_by(strategy_version_id=v.id, status="done").order_by(BacktestSession.id.desc()).first()
        if b:
            break
    m = b.result.metrics if b and b.result else {}
    daily = daily_series(b.result.equity) if b and b.result else []
    init = m.get("initial_balance") or 100.0
    values = [d["value"] for d in daily]
    peak = np.maximum.accumulate(values) if values else []
    risk = ver.risk or {}
    has_model = st.kind != "ml" or bool(ver.params().get("model_path"))
    return {
        "id": str(st.id), "dbId": st.id, "versionId": ver.id, "version": ver.version, "engine": st.engine, "kind": st.kind, "name": st.name, "pair": (ver.pairs or ["BTC/USDT"])[0], "pairs": ver.pairs, "tf": ver.timeframe,
        "type": "ML" if st.kind == "ml" else "Texnik", "sl": float(risk.get("stoploss_pct", 0)) * 100, "tp": float(risk.get("takeprofit_pct", 0)) * 100,
        "status": "draft" if not has_model else ("active" if st.enabled else "inactive"), "bt": ts(b.finished_at) if b else None, "created": ts(st.created_at), "desc": st.description, "color": st.color, "params": ver.params(), "risk": risk,
        "ret": m.get("total_return") or 0.0, "win": m.get("win_rate") or 0.0, "trades": m.get("total_trades") or 0, "mdd": m.get("max_drawdown") or 0.0, "sharpe": m.get("sharpe") or 0.0, "sortino": m.get("sortino") or 0.0, "pf": m.get("profit_factor") or 0.0,
        "avgDur": m.get("avg_holding_seconds") or 0.0, "avgTrade": m.get("avg_trade_return") or 0.0, "net": m.get("net_profit") or 0.0, "wins": m.get("winning_trades") or 0, "losses": m.get("losing_trades") or 0, "hasBacktest": bool(m),
        "curve": [{"time": d["time"], "value": (d["value"] / init - 1) * 100} for d in daily],
        "dd": [{"time": d["time"], "value": float(v / p - 1) * 100} for d, v, p in zip(daily, values, peak)],
        "dailyEq": values, "monthly": [{**x, "label": ""} for x in (b.result.monthly if b and b.result else [])], "spark": values[::5] or [init, init],
    }


def closed_trade(t: PaperTrade) -> dict:
    return {"id": f"p{t.id}", "entryT": t.entry_ts, "exitT": t.exit_ts, "entry": t.entry_price, "exit": t.exit_price, "qty": t.qty, "fees": t.entry_fee + t.exit_fee, "pnl": t.pnl, "pnlPct": t.pnl_pct, "why": {"signal": "Signal", "stoploss": "Stop-loss", "takeprofit": "Take-profit", "manual_stop": "Qo'lda"}.get(t.exit_reason, t.exit_reason), "cost": t.qty * t.entry_price}


def session_row(s, ps: PaperSession, tick: dict) -> dict:
    v = session_view(s, ps, last_price(tick, ps.pair))
    return {
        "id": str(ps.id), "dbId": ps.id, "strat": str(v["strategy_id"]), "pair": ps.pair, "tf": ps.timeframe, "start": v["initial"], "realized": v["realized"], "usdt": v["usdt"], "equity": v["equity"], "unrealized": v["unrealized"], "drawdown": v["drawdown"],
        "pos": {"qty": v["position"]["qty"], "entry": v["position"]["entry"], "t": v["position"]["entry_ts"]} if v["position"] else None,
        "status": {"halted": "paused"}.get(ps.status, ps.status), "rawStatus": ps.status, "started": v["started_at"], "ended": ts(ps.stopped_at), "trades": v["trades"], "note": ps.halt_reason or None, "fees": v["fees"], "lastCandle": ps.last_candle_ts, "evalRun": ps.eval_run_id,
        "closed": [closed_trade(t) for t in s.query(PaperTrade).filter(PaperTrade.session_id == ps.id, PaperTrade.exit_ts.isnot(None)).order_by(PaperTrade.exit_ts.desc()).limit(300)],
    }


def all_trades(s, tick: dict) -> list[dict]:
    out = []
    for ps in s.query(PaperSession):
        ver = s.get(StrategyVersion, ps.strategy_version_id)
        st = ver.strategy
        for t in s.query(PaperTrade).filter_by(session_id=ps.id):
            base = {"id": f"p{t.id}", "strat": str(st.id), "stratName": st.name, "pair": ps.pair, "kind": "paper", "entryT": t.entry_ts, "exitT": t.exit_ts, "entry": t.entry_price, "exit": t.exit_price, "qty": t.qty}
            if t.exit_ts:
                out.append({**base, "status": "closed", "fees": t.entry_fee + t.exit_fee, "pnl": t.pnl, "pnlPct": t.pnl_pct})
            else:
                p = last_price(tick, ps.pair) or t.entry_price
                cost = t.qty * t.entry_price
                pnl = t.qty * p - cost - t.entry_fee
                out.append({**base, "status": "open", "fees": t.entry_fee, "pnl": pnl, "pnlPct": pnl / cost * 100 if cost else 0.0})
    for t in s.query(LiveTrade):
        pair = t.symbol[:-4] + "/USDT"
        p = t.exit_price or last_price(tick, pair) or t.entry_price
        pnl = t.pnl if t.exit_ts else t.qty * p - t.qty * t.entry_price - t.entry_fee
        cost = t.qty * t.entry_price
        out.append({"id": f"l{t.id}", "strat": "live", "stratName": "REAL", "pair": pair, "kind": "live", "status": "closed" if t.exit_ts else "open", "entryT": t.entry_ts, "exitT": t.exit_ts, "entry": t.entry_price, "exit": t.exit_price, "qty": t.qty, "fees": t.entry_fee + t.exit_fee, "pnl": pnl, "pnlPct": pnl / cost * 100 if cost else 0.0})
    out.sort(key=lambda t: -(t["exitT"] or t["entryT"] + 10**9))
    return out


def portfolio(s, sessions: list[dict], tick: dict) -> dict:
    """Virtual portfolio only: the sum of isolated paper sessions. Real money is never in it."""
    frames = []
    start = 0.0
    for ps in s.query(PaperSession):
        rows = s.query(EquitySnapshot).filter_by(scope="paper", scope_id=ps.id).order_by(EquitySnapshot.ts).all()
        start += ps.portfolio.initial_balance
        if rows:
            frames.append(pd.Series([r.equity for r in rows], index=pd.to_datetime([r.ts for r in rows], unit="s")).resample("1D").last().ffill())
    empty = {"start": start, "final": start, "mdd": 0.0, "values": [], "equity": [], "dd": [], "pnlPct": [], "bench": [], "daily": [], "monthly": [], "alloc": [], "vol": 0.0, "sharpe": 0.0, "sortino": 0.0, "ret": 0.0, "calmar": 0.0, "winDays": 0.0}
    alloc: dict[str, float] = {}
    total = 0.0
    for r in sessions:
        if r["rawStatus"] == "stopped":
            continue
        total += r["equity"]
        alloc["USDT (bo'sh)"] = alloc.get("USDT (bo'sh)", 0.0) + r["usdt"]
        if r["pos"]:
            base = r["pair"].split("/")[0]
            alloc[base] = alloc.get(base, 0.0) + r["equity"] - r["usdt"]
    empty["alloc"] = [{"name": k, "v": round(v / total * 100, 2), "color": PALETTE_ALLOC[i % len(PALETTE_ALLOC)]} for i, (k, v) in enumerate(sorted(alloc.items(), key=lambda x: -x[1]))] if total else []
    if not frames:
        return empty
    all_df = pd.concat(frames, axis=1).sort_index()
    # Sessions not yet started count at their opening capital; a later start is not a gain.
    inits = [ps.portfolio.initial_balance for ps in s.query(PaperSession) if s.query(EquitySnapshot).filter_by(scope="paper", scope_id=ps.id).count()]
    for col, init in zip(all_df.columns, inits):
        all_df[col] = all_df[col].ffill().fillna(init)
    base = float(sum(inits)) or 1.0
    eq = all_df.sum(axis=1)
    values = eq.to_numpy()
    times = [int(i.timestamp()) for i in eq.index]
    peak = np.maximum.accumulate(values)
    dd = (values / peak - 1) * 100
    r = np.diff(values) / values[:-1] if len(values) > 1 else np.array([])
    out = {**empty, "start": base, "final": float(values[-1]), "mdd": float(dd.min()), "values": values.tolist(), "ret": float((values[-1] / base - 1) * 100)}
    out["equity"] = [{"time": t, "value": float(v)} for t, v in zip(times, values)]
    out["dd"] = [{"time": t, "value": float(v)} for t, v in zip(times, dd)]
    out["pnlPct"] = [{"time": t, "value": float((v / base - 1) * 100)} for t, v in zip(times, values)]
    out["daily"] = [{"time": t, "value": float(d), "color": "rgba(22,199,132,.85)" if d >= 0 else "rgba(234,57,67,.85)"} for t, d in zip(times[1:], np.diff(values))]
    from quantlab.backtest.metrics import monthly_returns

    out["monthly"] = [{**m, "label": ""} for m in monthly_returns(list(zip(times, values.tolist())))]
    if len(r) > 1 and r.std() > 0:
        out["vol"], out["sharpe"] = float(r.std() * np.sqrt(365) * 100), float(r.mean() / r.std() * np.sqrt(365))
        neg = np.minimum(r, 0)
        if (neg ** 2).mean() > 0:
            out["sortino"] = float(r.mean() / np.sqrt((neg ** 2).mean()) * np.sqrt(365))
        out["winDays"] = float((r > 0).mean() * 100)
    out["calmar"] = out["ret"] / abs(out["mdd"]) if out["mdd"] else 0.0
    return out


def models(s) -> tuple[list[dict], list[list], list[dict]]:
    rows = []
    latest = None
    status_map = {"promoted": "prod", "candidate": "staging", "archived": "archived"}
    for v in s.query(ModelVersion).order_by(ModelVersion.id.desc()):
        val, oos = v.validation_metrics or {}, v.oos_metrics or {}
        pct = lambda x: None if x is None else round(x * 100, 2)  # noqa: E731
        rows.append({"id": str(v.id), "dbId": v.id, "name": v.model.name, "algo": v.model.algo, "ver": f"v{v.version}", "acc": pct(oos.get("accuracy")), "prec": pct(oos.get("precision")), "rec": pct(oos.get("recall")), "f1": pct(oos.get("f1")), "val": pct(val.get("f1")), "oos": pct(oos.get("f1")), "auc": oos.get("auc"), "baseRate": pct(oos.get("base_rate")), "trading": oos.get("trading"), "buyHold": oos.get("buy_hold_return"), "dur": "—", "status": status_map.get(v.status, v.status), "pair": v.pair, "tf": v.timeframe, "trained": ts(v.created_at), "features": len(v.features or []), "samples": oos.get("samples", 0), "importance": v.feature_importance, "dataset": v.dataset_hash, "trainStart": v.train_start_ts, "trainEnd": v.train_end_ts, "path": v.artifact_path})
        if latest is None and v.feature_importance:
            latest = v.feature_importance
    feats = [[k, val] for k, val in list((latest or {}).items())[:10]]
    jobs = []
    for t in s.query(TrainingJob).order_by(TrainingJob.id.desc()).limit(20):
        j = s.get(Job, t.job_id)
        if j and j.status in ("queued", "running", "error"):
            jobs.append({"id": str(j.id), "dbId": j.id, "model": f"{t.algo} · {t.pair} {t.timeframe}", "algo": t.algo, "progress": round((j.progress or 0) * 100), "status": {"running": "training"}.get(j.status, j.status), "note": j.error or j.note or "Navbatda", "eta": "—"})
    return rows, feats, jobs


def notifications(s) -> list[dict]:
    now = int(time.time())
    return [{"id": str(n.id), "dbId": n.id, "type": n.category, "icon": ICONS.get(n.category, "bell"), "tone": TONES.get(n.tone, "#94A3B8"), "title": n.title, "text": n.text, "ago": max(0, now - ts(n.created_at)), "read": n.read, "route": n.route} for n in s.query(Notification).order_by(Notification.id.desc()).limit(100)]


def backtests(s) -> list[dict]:
    out = []
    for b in s.query(BacktestSession).order_by(BacktestSession.id.desc()).limit(30):
        v = s.get(StrategyVersion, b.strategy_version_id)
        m = b.result.metrics if b.result else {}
        out.append({"id": f"BT-{b.id}", "dbId": b.id, "strat": str(v.strategy_id), "name": v.strategy.name, "pair": b.pair, "tf": b.timeframe, "ts": ts(b.finished_at or b.created_at), "status": b.status, "err": b.error, "ret": m.get("total_return") or 0.0, "sharpe": m.get("sharpe") or 0.0, "mdd": m.get("max_drawdown") or 0.0, "trades": m.get("total_trades") or 0, "progress": b.progress})
    return out


def benchmark(store, series: list[dict]) -> list[dict]:
    """BTC buy and hold over the same days, for the portfolio chart."""
    if store is None or not series:
        return []
    df = store.load("BTC/USDT", "1h", start_ts=series[0]["time"] - 3600)
    if df.empty:
        return []
    closes = pd.Series(df["close"].to_numpy(), index=df["ts"].to_numpy())
    out = []
    first = None
    for p in series:
        idx = closes.index.searchsorted(p["time"] + 86400 - 3600, side="right") - 1
        if idx < 0:
            continue
        c = float(closes.iloc[idx])
        first = first or c
        out.append({"time": p["time"], "value": (c / first - 1) * 100})
    return out


def build(s, store=None) -> dict:
    tick = prices(s)
    sessions = [session_row(s, ps, tick) for ps in s.query(PaperSession).order_by(PaperSession.id.desc())]
    mods, feats, jobs = models(s)
    opt = [{"id": o.id, "strategyId": o.strategy_id, "pair": o.pair, "tf": o.timeframe, "status": o.status, "top": o.top, "config": {k: v for k, v in (o.config or {}).items() if k != "history"}, "history": (o.config or {}).get("history", []), "created": ts(o.created_at), "progress": (lambda j: j.progress if j else 0)(s.get(Job, o.job_id))} for o in s.query(OptimizationJob).order_by(OptimizationJob.id.desc()).limit(20)]
    pf = portfolio(s, sessions, tick)
    pf["bench"] = benchmark(store, pf["equity"])
    return {
        "backend": True, "tickers": {k: {"price": float(v["lastPrice"]), "ch": float(v["priceChangePercent"]), "vol": float(v["quoteVolume"]), "high": float(v["highPrice"]), "low": float(v["lowPrice"])} for k, v in tick.items()},
        "strategies": [strategy_row(s, st) for st in s.query(Strategy).order_by(Strategy.kind.desc(), Strategy.id)], "sessions": sessions, "trades": all_trades(s, tick), "portfolio": pf,
        "models": mods, "features": feats, "jobs": jobs, "backtests": backtests(s), "notifications": notifications(s), "optimizations": opt,
    }
