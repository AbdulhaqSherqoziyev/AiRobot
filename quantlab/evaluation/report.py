"""30-day evaluation: frozen criteria, a report per strategy, and a recommendation that can
only ever lead to an owner decision. Passing is a screening result, not a forecast."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from quantlab.backtest.metrics import compute
from quantlab.config import TIMEFRAMES
from quantlab.market.store import CandleStore
from quantlab.models import EquitySnapshot, EvaluationReport, EvaluationRun, PaperSession, PaperTrade, RiskEvent, Strategy, StrategyVersion, utcnow
from quantlab.notify.service import notify
from quantlab.paper.engine import create_session
from quantlab.strategies import indicators as ind
from quantlab.strategies.base import get_strategy
from quantlab.backtest.engine import run_backtest

DEFAULT_CRITERIA = {"min_days": 30, "min_trades": 20, "min_net_profit": 0.0, "min_profit_factor": 1.3, "max_drawdown_pct": 5.0, "min_oos_return": 0.0, "max_critical_events": 0}
LIMITATIONS = [
    "Paper fills use modelled fees and slippage; real fills can be worse.",
    "30 days cover few market regimes, so a good result can be luck.",
    "Many strategies were compared: the best of them is favoured by chance alone.",
    "Past performance does not predict future returns.",
]


def start_run(db, pairs_by_strategy: dict[int, tuple[str, str]] | None = None, capital: float = 100.0, criteria: dict | None = None, duration_days: int = 30, now: int | None = None) -> int:
    """Creates one isolated session per enabled strategy. ML strategies join only with a
    promoted model, since without one they would never trade and only pad the table."""
    with db.session() as s:
        if s.query(EvaluationRun).filter_by(status="running").count():
            raise ValueError("an evaluation run is already active")
        run = EvaluationRun(duration_days=duration_days, criteria={**DEFAULT_CRITERIA, **(criteria or {})})
        s.add(run)
        s.flush()
        n = 0
        for st in s.query(Strategy).filter_by(enabled=True):
            ver = s.get(StrategyVersion, st.current_version_id)
            if st.kind == "ml" and not ver.params().get("model_path"):
                continue
            pair, tf = (pairs_by_strategy or {}).get(st.id, ((ver.pairs or ["BTC/USDT"])[0], ver.timeframe))
            create_session(s, ver, pair, tf, capital, eval_run_id=run.id, now=now)
            n += 1
        if not n:
            raise ValueError("no enabled strategy to evaluate")
        notify(s, "evaluation", "30 kunlik baholash boshlandi", f"{n} ta strategiya, har biri {capital:g} USDT virtual kapital bilan", "info", "evaluation")
        return run.id


def _regime(store: CandleStore, pair: str, tf: str) -> pd.Series:
    df = store.load(pair, tf)
    if len(df) < 60:
        return pd.Series(dtype=object)
    c = df["close"]
    fast, slow = ind.ema(c, 20), ind.ema(c, 50)
    adx, _, _ = ind.adx(df, 14)
    reg = np.where(adx < 20, "range", np.where(fast > slow, "up", "down"))
    return pd.Series(reg, index=df["ts"].to_numpy())


def _consistency(equity: list[tuple[int, float]]) -> float | None:
    """Share of 7-day blocks with a positive return."""
    if len(equity) < 2:
        return None
    s = pd.Series([e for _, e in equity], index=pd.to_datetime([t for t, _ in equity], unit="s")).resample("7D").last().dropna()
    r = s.pct_change().dropna()
    return round(float((r > 0).mean() * 100), 1) if len(r) else None


def _oos(store: CandleStore, ver: StrategyVersion, pair: str, tf: str, started_ts: int) -> dict | None:
    """Backtest on the last 30% of the history that existed before paper trading began."""
    df = store.load(pair, tf, end_ts=started_ts)
    if len(df) < 500:
        return None
    start = int(df["ts"].iloc[int(len(df) * 0.7)])
    params = {**ver.params(), **{k: v for k, v in (ver.risk or {}).items() if k in ("stake_pct", "stoploss_pct", "takeprofit_pct", "sizing")}}
    m = run_backtest(get_strategy(ver.strategy.engine), df, params, tf, start_ts=start).metrics
    return {k: m[k] for k in ("total_return", "max_drawdown", "profit_factor", "total_trades", "sharpe")}


def build_rows(db, store: CandleStore, run_id: int, now_dt=None) -> tuple[list[dict], dict]:
    now_dt = now_dt or utcnow()
    rows = []
    with db.session() as s:
        run = s.get(EvaluationRun, run_id)
        c = run.criteria
        for ps in s.query(PaperSession).filter_by(eval_run_id=run_id):
            ver = s.get(StrategyVersion, ps.strategy_version_id)
            eq = [(r.ts, r.equity) for r in s.query(EquitySnapshot).filter_by(scope="paper", scope_id=ps.id).order_by(EquitySnapshot.ts)]
            trades = [{"pnl": t.pnl, "pnl_pct": t.pnl_pct, "fees": t.entry_fee + t.exit_fee, "entry_ts": t.entry_ts, "exit_ts": t.exit_ts} for t in s.query(PaperTrade).filter(PaperTrade.session_id == ps.id, PaperTrade.exit_ts.isnot(None)).order_by(PaperTrade.exit_ts)]
            m = compute(eq, trades, ps.portfolio.initial_balance, TIMEFRAMES[ps.timeframe])
            days = (now_dt - ps.started_at).total_seconds() / 86400
            gross = m["net_profit"] + m["fees_paid"]
            critical = s.query(RiskEvent).filter(RiskEvent.scope == "paper", RiskEvent.scope_id == ps.id, RiskEvent.rule.in_(("strategy_error", "max_drawdown", "daily_loss"))).count()
            regime = _regime(store, ps.pair, ps.timeframe)
            by_regime: dict = {}
            for t in trades:
                r = regime.get(t["entry_ts"], "unknown") if len(regime) else "unknown"
                b = by_regime.setdefault(str(r), {"trades": 0, "pnl": 0.0})
                b["trades"] += 1
                b["pnl"] = round(b["pnl"] + t["pnl"], 4)
            started_ts = int(ps.started_at.timestamp())
            oos = _oos(store, ver, ps.pair, ps.timeframe, started_ts)
            bench = None
            candles = store.load(ps.pair, ps.timeframe, start_ts=ps.last_candle_ts - 86400 * run.duration_days)
            if eq and len(candles):
                first = candles[candles["ts"] >= eq[0][0]]
                if len(first):
                    bench = round(float((first["close"].iloc[-1] / first["open"].iloc[0] - 1) * 100), 3)
            fails = []
            if days < c["min_days"]:
                fails.append(f"{days:.1f} kun < {c['min_days']} kun")
            if m["total_trades"] < c["min_trades"]:
                fails.append(f"{m['total_trades']} savdo < {c['min_trades']}")
            if m["net_profit"] <= c["min_net_profit"]:
                fails.append("sof foyda yo'q")
            if (m["profit_factor"] or 0) < c["min_profit_factor"]:
                fails.append(f"profit factor < {c['min_profit_factor']}")
            if abs(m["max_drawdown"] or 0) >= c["max_drawdown_pct"]:
                fails.append(f"pasayish >= {c['max_drawdown_pct']}%")
            if oos is None or (oos["total_return"] or 0) <= c["min_oos_return"]:
                fails.append("out-of-sample natija yetarli emas")
            if critical > c["max_critical_events"]:
                fails.append(f"{critical} ta kritik hodisa")
            sample_short = days < c["min_days"] or m["total_trades"] < c["min_trades"]
            rows.append({
                "session_id": ps.id, "strategy_id": ver.strategy_id, "strategy_version_id": ver.id, "strategy": ver.strategy.name, "pair": ps.pair, "timeframe": ps.timeframe, "days": round(days, 2),
                "metrics": m, "fee_impact_pct": round(m["fees_paid"] / gross * 100, 2) if gross > 0 else None, "consistency": _consistency(eq), "regimes": by_regime,
                "out_of_sample": oos, "benchmark_return": bench, "critical_events": critical, "eligible": not fails, "fails": fails, "insufficient_sample": sample_short,
            })
    eligible = [r for r in rows if r["eligible"]]
    eligible.sort(key=lambda r: -((r["metrics"]["sharpe"] or 0) + (r["metrics"]["profit_factor"] or 0)))
    if eligible:
        rec = {"action": "review", "strategy_version_id": eligible[0]["strategy_version_id"], "strategy": eligible[0]["strategy"], "pair": eligible[0]["pair"], "allocation": 100.0, "text": "Skrining mezonlaridan o'tdi. Bu kelajakdagi foydani kafolatlamaydi."}
    elif rows and all(r["insufficient_sample"] for r in rows):
        rec = {"action": "extend", "text": "Namuna yetarli emas: sinovni davom ettirish tavsiya etiladi."}
    else:
        rec = {"action": "none", "text": "Hech bir strategiya mezonlardan o'tmadi. Real savdo tavsiya etilmaydi."}
    rec["limitations"] = LIMITATIONS
    return rows, rec


def generate_report(db, store: CandleStore, run_id: int, now_dt=None) -> int:
    now_dt = now_dt or utcnow()
    with db.session() as s:
        run = s.get(EvaluationRun, run_id)
        if run is None:
            raise ValueError("unknown evaluation run")
        ends = run.started_at + timedelta(days=run.duration_days)
        duration_over = now_dt >= ends
    rows, rec = build_rows(db, store, run_id, now_dt)
    with db.session() as s:
        run = s.get(EvaluationRun, run_id)
        rep = EvaluationReport(run_id=run_id, is_final=duration_over, rows=rows, recommendation=rec)
        s.add(rep)
        # Finishing a run enables a report and an approval page. It never starts live trading.
        if duration_over and run.status == "running":
            run.status = "finished"
            notify(s, "evaluation", "30 kunlik baholash yakunlandi", rec["text"], "info", "evaluation")
        s.flush()
        return rep.id
