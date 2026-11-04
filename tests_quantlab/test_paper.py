import pandas as pd
import pytest
from sqlalchemy.exc import IntegrityError

from conftest import synthetic
from quantlab.backtest.engine import run_on_signals
from quantlab.backtest.core import ExecConfig
from quantlab.db import Database
from quantlab.market.store import CandleStore
from quantlab.models import EquitySnapshot, PaperSession, PaperTrade, Strategy, StrategyParameter, StrategyVersion, VirtualBalance
from quantlab.paper import engine as pe
from quantlab.strategies.base import REGISTRY, RiskDefaults, Strategy as Strat

PAIR, TF, STEP = "BTC/USDT", "1h", 3600


class Scripted(Strat):
    """Test strategy: enters and exits on the candle timestamps in class attributes."""
    key, name = "scripted", "Scripted"
    enters: set = set()
    exits: set = set()

    def compute(self, df, p):
        return df["ts"].isin(self.enters), df["ts"].isin(self.exits)


class Exploding(Strat):
    """Test strategy that always raises."""
    key, name = "exploding", "Exploding"

    def compute(self, df, p):
        raise RuntimeError("boom")


def version(s, engine="scripted", name=None, risk=None):
    st = Strategy(name=name or engine, engine=engine)
    s.add(st)
    s.flush()
    v = StrategyVersion(strategy_id=st.id, version=1, pairs=[PAIR], timeframe=TF, risk=risk if risk is not None else {"stoploss_pct": 0.5, "stake_pct": 1.0, "max_drawdown_pct": 90, "max_daily_loss_pct": 90})
    s.add(v)
    s.flush()
    st.current_version_id = v.id
    return v


@pytest.fixture
def world(db, tmp_path):
    store = CandleStore(tmp_path)
    df = synthetic(300)
    store.save(PAIR, TF, df)
    return db, store, df


def start(world, capital=100.0, engine="scripted", at=100, risk=None, name=None):
    db, store, df = world
    now = int(df["ts"].iloc[at])
    with db.session() as s:
        v = version(s, engine, name, risk)
        return pe.create_session(s, v, PAIR, TF, capital, now=now).id, now


def walk(db, store, sid, df, end):
    """Tick once per candle, as the running worker does, up to the close of candle `end - 1`."""
    with db.session() as s:
        last = s.get(PaperSession, sid).last_candle_ts
    n = 0
    for ts in df["ts"].to_numpy():
        if ts > last and ts <= df["ts"].iloc[end]:
            n += pe.tick_session(db, store, sid, now=int(ts) + 1)
    return n


def test_entry_fills_at_next_open_then_exit_realises_pnl(world):
    db, store, df = world
    sid, now = start(world)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[100])}, {int(t[105])}
    assert walk(db, store, sid, df, 110) == 10
    with db.session() as s:
        tr = s.query(PaperTrade).filter_by(session_id=sid).one()
        assert tr.entry_ts == int(t[101]) and tr.entry_price == pytest.approx(df["open"].iloc[101] * 1.0005)
        assert tr.exit_ts == int(t[106]) and tr.exit_reason == "signal"
        ps = s.get(PaperSession, sid)
        assert ps.portfolio.balance("USDT").free == pytest.approx(100 + tr.pnl)
        assert ps.portfolio.balance("BTC").free == pytest.approx(0, abs=1e-12)


def test_matches_backtest_accounting(world):
    """Paper and backtest share one core, so identical signals give identical results."""
    db, store, df = world
    sid, _ = start(world)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[110]), int(t[150])}, {int(t[130]), int(t[170])}
    walk(db, store, sid, df, 200)
    window = df[(df["ts"] > df["ts"].iloc[99]) & (df["ts"] <= t[198])].reset_index(drop=True)
    out = run_on_signals(window, window["ts"].isin(Scripted.enters).to_numpy(), window["ts"].isin(Scripted.exits).to_numpy(), TF, 100.0, ExecConfig(stake_pct=1.0, stoploss_pct=0.5))
    with db.session() as s:
        ps = s.get(PaperSession, sid)
        assert ps.portfolio.balance("USDT").free == pytest.approx(out.equity[-1][1])
        assert s.query(PaperTrade).filter_by(session_id=sid).count() == 2


def test_only_closed_candles_are_used(world):
    db, store, df = world
    sid, now = start(world)
    Scripted.enters, Scripted.exits = set(), set()
    last_ts = int(df["ts"].iloc[150])
    assert pe.tick_session(db, store, sid, now=last_ts + 10) == 150 - 100  # candle 150 still forming
    with db.session() as s:
        assert s.get(PaperSession, sid).last_candle_ts == int(df["ts"].iloc[149])


def test_restart_resumes_state_without_duplicates(world, tmp_path):
    db, store, df = world
    sid, _ = start(world)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[110])}, {int(t[140])}
    walk(db, store, sid, df, 120)
    with db.session() as s:
        before = (s.get(PaperSession, sid).last_candle_ts, s.query(EquitySnapshot).filter_by(scope_id=sid).count())
        open_trade = s.query(PaperTrade).filter(PaperTrade.exit_ts.is_(None)).one()
        qty = open_trade.qty
    # A new Database object over the same file stands in for a process restart.
    db2 = Database(str(db.engine.url))
    assert pe.tick_session(db2, store, sid, now=int(t[120]) + 1) == 0  # same time: nothing to redo
    with db2.session() as s:
        assert (s.get(PaperSession, sid).last_candle_ts, s.query(EquitySnapshot).filter_by(scope_id=sid).count()) == before
        assert s.query(PaperTrade).filter(PaperTrade.exit_ts.is_(None)).one().qty == qty
    pe.tick_session(db2, store, sid, now=int(t[121]) + 1)
    with db2.session() as s:
        assert s.query(PaperTrade).count() == 1


def test_downtime_runs_exits_but_opens_nothing(world):
    db, store, df = world
    sid, _ = start(world)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[110])}, set()
    pe.tick_session(db, store, sid, now=int(t[200]))  # 100 candles late
    with db.session() as s:
        assert s.query(PaperTrade).filter_by(session_id=sid).count() == 0


def test_duplicate_entry_is_impossible(world):
    db, _, _ = world
    sid, _ = start(world)
    with pytest.raises(IntegrityError):
        with db.session() as s:
            for _i in range(2):
                s.add(PaperTrade(session_id=sid, entry_signal_ts=5, entry_ts=6, entry_price=1, qty=1, entry_fee=0))
                s.flush()


def test_sessions_are_isolated(world):
    db, store, df = world
    a, _ = start(world, name="a")
    b, _ = start(world, capital=250.0, name="b")
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[110])}, {int(t[120])}
    walk(db, store, a, df, 130)
    with db.session() as s:
        assert s.get(PaperSession, b).portfolio.balance("USDT").free == 250.0
        assert s.query(PaperTrade).filter_by(session_id=b).count() == 0
        assert s.query(VirtualBalance).count() == 4


def test_failing_strategy_halts_only_its_session(world):
    db, store, df = world
    bad, _ = start(world, engine="exploding", name="bad")
    good, _ = start(world, name="good")
    Scripted.enters, Scripted.exits = set(), set()
    pe.tick_all(db, store, now=int(df["ts"].iloc[110]))
    with db.session() as s:
        assert s.get(PaperSession, bad).status == "halted" and "boom" in s.get(PaperSession, bad).halt_reason
        assert s.get(PaperSession, good).status == "running" and s.get(PaperSession, good).last_candle_ts > 0


def test_drawdown_halts_entries_until_owner_resumes(tmp_path, db):
    store = CandleStore(tmp_path)
    df = synthetic(200)
    # A 30% crash on one candle while the stop is too wide to trigger.
    df.loc[120:, ["open", "high", "low", "close"]] *= 0.7
    store.save(PAIR, TF, df)
    w = (db, store, df)
    sid, _ = start(w, risk={"stoploss_pct": 0.9, "stake_pct": 1.0, "max_drawdown_pct": 20, "max_daily_loss_pct": 90})
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[110]), int(t[135])}, set()
    walk(db, store, sid, df, 125)
    with db.session() as s:
        ps = s.get(PaperSession, sid)
        assert ps.status == "halted" and "max_drawdown" in ps.halt_reason
    assert pe.set_status(db, sid, "resume") == "running"
    with db.session() as s:
        assert s.get(PaperSession, sid).status == "running"


def test_pause_blocks_entries_and_keeps_exits(world):
    db, store, df = world
    sid, _ = start(world)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[105])}, {int(t[115])}
    walk(db, store, sid, df, 108)
    pe.set_status(db, sid, "pause")
    walk(db, store, sid, df, 118)
    with db.session() as s:
        assert s.query(PaperTrade).filter(PaperTrade.session_id == sid, PaperTrade.exit_ts.isnot(None)).count() == 1


def test_stop_closes_position_and_reset_restores_capital(world):
    db, store, df = world
    sid, _ = start(world)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[105])}, set()
    walk(db, store, sid, df, 108)
    assert pe.set_status(db, sid, "stop", store) == "stopped"
    with db.session() as s:
        ps = s.get(PaperSession, sid)
        assert s.query(PaperTrade).filter_by(session_id=sid).one().exit_reason == "manual_stop"
        assert ps.portfolio.balance("BTC").free == 0.0
    pe.set_status(db, sid, "reset")
    with db.session() as s:
        ps = s.get(PaperSession, sid)
        assert ps.status == "running" and ps.portfolio.balance("USDT").free == 100.0 and s.query(PaperTrade).filter_by(session_id=sid).count() == 0
