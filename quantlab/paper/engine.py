"""Persistent paper trading. Virtual balances only: this module cannot reach an order API.

All state lives in the database and advances one closed candle per transaction, together
with `last_candle_ts`. After a crash or VPS restart a session resumes exactly where it was,
and a candle is never applied twice. The unique (session, signal candle) constraint is a
second guard against duplicate trades.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from quantlab.backtest.core import ExecConfig, Filters, Position, SimState, on_candle
from quantlab.config import TIMEFRAMES
from quantlab.market.store import CandleStore
from quantlab.models import EquitySnapshot, PaperSession, PaperTrade, RiskEvent, StrategyVersion, TradingPair, VirtualBalance, VirtualPortfolio, utcnow
from quantlab.notify.service import notify, syslog
from quantlab.risk.engine import RiskLimits, portfolio_breaches
from quantlab.risk.sizing import HISTORY_DAYS, stake_series
from quantlab.strategies.base import get_strategy

log = logging.getLogger(__name__)
WINDOW = 600  # candles of history handed to the strategy on each tick
ACTIVE = ("running", "paused", "halted")


def base_asset(pair: str) -> str:
    return pair.split("/")[0]


def create_session(s, version: StrategyVersion, pair: str, timeframe: str, capital: float = 100.0, name: str = "", fee: float = 0.001, slippage: float = 0.0005, risk: dict | None = None, eval_run_id: int | None = None, now: int | None = None) -> PaperSession:
    if capital <= 0:
        raise ValueError("capital must be positive")
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unsupported timeframe {timeframe}")
    now = int(time.time()) if now is None else now
    step = TIMEFRAMES[timeframe]
    merged = {**version.risk, **(risk or {})}
    ps = PaperSession(
        strategy_version_id=version.id, name=name or f"{version.strategy.name} {pair} {timeframe}", pair=pair, timeframe=timeframe, fee=fee, slippage=slippage, risk=merged,
        # Start from the candle now forming, so no decision is made on stale candles.
        last_candle_ts=(now // step) * step - step, eval_run_id=eval_run_id,
    )
    s.add(ps)
    s.flush()
    pf = VirtualPortfolio(session_id=ps.id, initial_balance=capital, peak_equity=capital)
    pf.balances = [VirtualBalance(asset="USDT", free=capital), VirtualBalance(asset=base_asset(pair), free=0.0)]
    s.add(pf)
    s.flush()
    return ps


def _exec_cfg(s, ps: PaperSession) -> ExecConfig:
    pair = s.query(TradingPair).filter_by(symbol=ps.pair).one_or_none()
    filters = Filters(pair.min_notional, pair.step_size) if pair else Filters()
    r = ps.risk or {}
    return ExecConfig(fee=ps.fee, slippage=ps.slippage, stake_pct=float(r.get("stake_pct", 0.95)), stoploss_pct=float(r.get("stoploss_pct", 0.03)), takeprofit_pct=float(r.get("takeprofit_pct", 0.0)), filters=filters)


def load_state(s, ps: PaperSession) -> tuple[SimState, PaperTrade | None]:
    usdt = ps.portfolio.balance("USDT")
    trade = s.query(PaperTrade).filter(PaperTrade.session_id == ps.id, PaperTrade.exit_ts.is_(None)).one_or_none()
    pos = Position(trade.entry_ts, trade.entry_price, trade.qty, trade.entry_fee, trade.entry_signal_ts) if trade else None
    pend = ps.pending_signal or {}
    return SimState(usdt=usdt.free, position=pos, pending=pend.get("side"), pending_ts=pend.get("ts", 0), pending_stake=pend.get("stake")), trade


def _day_start_equity(s, ps: PaperSession, ts: int) -> float:
    midnight = ts - ts % 86400
    row = s.query(EquitySnapshot).filter(EquitySnapshot.scope == "paper", EquitySnapshot.scope_id == ps.id, EquitySnapshot.ts >= midnight).order_by(EquitySnapshot.ts).first()
    return row.equity if row else 0.0


def _apply_candle(s, ps: PaperSession, cfg: ExecConfig, ts: int, o: float, h: float, l: float, c: float, enter: bool, exit_: bool, stale: bool, stake: float | None = None) -> None:
    state, trade = load_state(s, ps)
    allow = ps.status == "running" and not stale
    fills = on_candle(state, cfg, ts, o, h, l, c, enter and allow, exit_, allow_entries=allow, stake=stake)
    base = ps.portfolio.balance(base_asset(ps.pair))
    for f in fills:
        if f.side == "buy":
            s.add(PaperTrade(session_id=ps.id, entry_signal_ts=f.signal_ts, entry_ts=f.ts, entry_price=f.price, qty=f.qty, entry_fee=f.fee))
            base.free += f.qty
        else:
            assert trade is not None or state.position is None
            t = trade or s.query(PaperTrade).filter(PaperTrade.session_id == ps.id, PaperTrade.exit_ts.is_(None)).one()
            t.exit_ts, t.exit_price, t.exit_fee, t.pnl, t.pnl_pct, t.exit_reason = f.ts, f.price, f.fee, f.pnl, f.pnl_pct, f.reason
            base.free -= f.qty
            trade = None
        s.flush()
        if trade is None and f.side == "buy":
            trade = s.query(PaperTrade).filter(PaperTrade.session_id == ps.id, PaperTrade.exit_ts.is_(None)).one()
    ps.portfolio.balance("USDT").free = state.usdt
    # The stake is stored with the signal, so a restart executes the size that was decided.
    ps.pending_signal = {"side": state.pending, "ts": state.pending_ts, "stake": state.pending_stake} if state.pending else None
    ps.last_candle_ts = ts
    equity = state.equity(c)
    ps.portfolio.peak_equity = max(ps.portfolio.peak_equity, equity)
    day_start = _day_start_equity(s, ps, ts) or equity
    s.add(EquitySnapshot(scope="paper", scope_id=ps.id, ts=ts, equity=equity))
    if ps.status == "running":
        for v in portfolio_breaches(RiskLimits.from_dict(ps.risk), equity, ps.portfolio.peak_equity, day_start):
            ps.status, ps.halt_reason = "halted", f"{v.rule}: {v.detail}"
            s.add(RiskEvent(scope="paper", scope_id=ps.id, rule=v.rule, detail=v.detail))
            notify(s, "risk", f"Risk chegarasi: {ps.name}", v.detail, "warn", "paper")
            syslog(s, "WARNING", "paper", f"session {ps.id} halted: {v.detail}")
            break


def tick_session(db, store: CandleStore, session_id: int, now: int | None = None) -> int:
    """Apply every closed candle not yet seen. Returns the number of candles applied."""
    now = int(time.time()) if now is None else now
    with db.session() as s:
        ps = s.get(PaperSession, session_id)
        if ps is None or ps.status not in ACTIVE:
            return 0
        last, tf, pair = ps.last_candle_ts, ps.timeframe, ps.pair
        ver = s.get(StrategyVersion, ps.strategy_version_id)
        engine, params, risk = ver.strategy.engine, ver.params(), dict(ps.risk or {})
    step = TIMEFRAMES[tf]
    history = step * WINDOW
    if risk.get("sizing"):
        history = max(history, HISTORY_DAYS * 86400)
    df = store.load(pair, tf, start_ts=last - history)
    new = df[(df["ts"] > last) & (df["ts"] + step <= now)]
    if new.empty:
        return 0
    try:
        sig = get_strategy(engine).signals(df, params)
        stakes = stake_series(df, risk)
    except Exception as exc:
        # A broken strategy must not take other sessions down, and must not keep trading.
        log.exception("strategy failed in session %s", session_id)
        with db.session() as s:
            ps = s.get(PaperSession, session_id)
            ps.status, ps.halt_reason = "halted", f"strategy error: {exc}"
            s.add(RiskEvent(scope="paper", scope_id=session_id, rule="strategy_error", detail=str(exc)[:500]))
            notify(s, "system", f"Strategiya xatosi: {ps.name}", str(exc)[:300], "err", "paper")
            syslog(s, "ERROR", "paper", f"session {session_id}: {exc}")
        return 0
    applied = 0
    for i in new.index:
        row = df.loc[i]
        ts = int(row["ts"])
        # Candles missed while the system was down still run stops and exits, but open no
        # position: an entry cannot honestly be filled at a price from the past.
        stale = ts + step * 2 < now
        with db.session() as s:
            ps = s.get(PaperSession, session_id)
            if ps.last_candle_ts >= ts:
                continue  # another process applied it
            _apply_candle(s, ps, _exec_cfg(s, ps), ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), bool(sig["enter"].iloc[i - df.index[0]]), bool(sig["exit"].iloc[i - df.index[0]]), stale, None if stakes is None else float(stakes[i - df.index[0]]))
        applied += 1
    return applied


def tick_all(db, store: CandleStore, now: int | None = None) -> int:
    with db.session() as s:
        ids = [r.id for r in s.query(PaperSession).filter(PaperSession.status.in_(ACTIVE))]
    total = 0
    for sid in ids:
        try:
            total += tick_session(db, store, sid, now)
        except Exception:  # one session's failure must leave the others running
            log.exception("tick failed for session %s", sid)
    return total


def set_status(db, session_id: int, action: str, store: CandleStore | None = None) -> str:
    with db.session() as s:
        ps = s.get(PaperSession, session_id)
        if ps is None:
            raise ValueError("unknown session")
        if action == "pause" and ps.status == "running":
            ps.status = "paused"
        elif action == "resume" and ps.status in ("paused", "halted"):
            # Resuming a halted session is the owner's approval; it is logged, and the peak
            # is reset so the same old drawdown does not halt it again immediately.
            if ps.status == "halted":
                syslog(s, "INFO", "paper", f"owner resumed halted session {ps.id}: {ps.halt_reason}")
                last = s.query(EquitySnapshot).filter_by(scope="paper", scope_id=ps.id).order_by(EquitySnapshot.ts.desc()).first()
                if last:
                    ps.portfolio.peak_equity = last.equity
            ps.status, ps.halt_reason = "running", ""
        elif action == "stop" and ps.status in ACTIVE:
            _close_at_last_price(s, ps, store)
            ps.status, ps.stopped_at, ps.pending_signal = "stopped", utcnow(), None
        elif action == "reset":
            if ps.eval_run_id is not None:
                raise ValueError("this session belongs to an evaluation run and cannot be reset")
            s.query(PaperTrade).filter_by(session_id=ps.id).delete()
            s.query(EquitySnapshot).filter_by(scope="paper", scope_id=ps.id).delete()
            for b in ps.portfolio.balances:
                b.free = ps.portfolio.initial_balance if b.asset == "USDT" else 0.0
            ps.portfolio.peak_equity = ps.portfolio.initial_balance
            step = TIMEFRAMES[ps.timeframe]
            ps.last_candle_ts = (int(time.time()) // step) * step - step
            ps.pending_signal, ps.halt_reason, ps.stopped_at, ps.status = None, "", None, "running"
            ps.started_at = utcnow()
        else:
            raise ValueError(f"cannot {action} a {ps.status} session")
        return ps.status


def _close_at_last_price(s, ps: PaperSession, store: CandleStore | None) -> None:
    state, trade = load_state(s, ps)
    if trade is None or store is None:
        return
    df = store.load(ps.pair, ps.timeframe, start_ts=ps.last_candle_ts - TIMEFRAMES[ps.timeframe])
    if df.empty:
        return
    from quantlab.backtest.core import _sell

    last = df.iloc[-1]
    f = _sell(state, _exec_cfg(s, ps), int(last["ts"]), float(last["close"]), "manual_stop")
    trade.exit_ts, trade.exit_price, trade.exit_fee, trade.pnl, trade.pnl_pct, trade.exit_reason = f.ts, f.price, f.fee, f.pnl, f.pnl_pct, f.reason
    ps.portfolio.balance("USDT").free = state.usdt
    ps.portfolio.balance(base_asset(ps.pair)).free = 0.0


def session_view(s, ps: PaperSession, price: float | None = None) -> dict:
    state, trade = load_state(s, ps)
    mark = price if price is not None else (trade.entry_price if trade else 0.0)
    equity = state.equity(mark)
    closed = s.query(PaperTrade).filter(PaperTrade.session_id == ps.id, PaperTrade.exit_ts.isnot(None)).all()
    realized = sum(t.pnl for t in closed)
    unreal = (trade.qty * mark - trade.qty * trade.entry_price - trade.entry_fee) if trade else 0.0
    peak = max(ps.portfolio.peak_equity, equity)
    ver = s.get(StrategyVersion, ps.strategy_version_id)
    return {
        "id": ps.id, "name": ps.name, "strategy_id": ver.strategy_id, "strategy": ver.strategy.name, "version": ver.version, "color": ver.strategy.color,
        "pair": ps.pair, "timeframe": ps.timeframe, "status": ps.status, "halt_reason": ps.halt_reason,
        "started_at": int(ps.started_at.replace(tzinfo=timezone.utc).timestamp()), "initial": ps.portfolio.initial_balance, "usdt": state.usdt, "equity": equity,
        "realized": realized, "unrealized": unreal, "drawdown": (equity / peak - 1) * 100 if peak else 0.0, "trades": len(closed), "wins": sum(1 for t in closed if t.pnl > 0),
        "fees": sum(t.entry_fee + t.exit_fee for t in closed), "last_candle_ts": ps.last_candle_ts, "eval_run_id": ps.eval_run_id,
        "position": {"entry_ts": trade.entry_ts, "entry": trade.entry_price, "qty": trade.qty, "fee": trade.entry_fee} if trade else None,
    }
