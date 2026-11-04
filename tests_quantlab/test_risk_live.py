import pytest

from conftest import synthetic
from test_paper import PAIR, Scripted, TF, version
from quantlab.config import Settings
from quantlab.evaluation import approval
from quantlab.live import engine as le
from quantlab.live.crypto import decrypt, encrypt
from quantlab.live.exchange import ALLOWED_SIGNED, BinanceSpot, ExchangeError, ExchangeUnknown, verify_key_is_safe
from quantlab.market.store import CandleStore
from quantlab.models import EvaluationReport, EvaluationRun, ExchangeConnection, LiveOrder, LiveTrade, RiskEvent
from quantlab.risk.engine import RiskLimits, entry_violations, portfolio_breaches

ON = Settings(live_enabled=True, secret_key="x" * 40)
OFF = Settings(live_enabled=False, secret_key="x" * 40)


class FakeExchange:
    def __init__(self, usdt=100.0):
        self.usdt, self.base = usdt, 0.0
        self.calls, self.fail, self.exists = [], None, {}

    def account(self):
        return {"balances": [{"asset": "USDT", "free": str(self.usdt)}, {"asset": "BTC", "free": str(self.base)}]}

    def _res(self, cid, qty, price):
        r = {"orderId": 1, "status": "FILLED", "executedQty": str(qty), "cummulativeQuoteQty": str(qty * price), "fills": [{"commission": str(qty * price * 0.001), "commissionAsset": "USDT"}], "clientOrderId": cid}
        self.exists[cid] = r
        return r

    def market_buy(self, symbol, quote, cid):
        self.calls.append(("BUY", quote, cid))
        if self.fail:
            if self.fail is ExchangeUnknown:
                self._res(cid, quote / 100, 100)  # placed, but the response was lost
            raise self.fail("simulated")
        return self._res(cid, quote / 100, 100)

    def market_sell(self, symbol, qty, cid):
        self.calls.append(("SELL", qty, cid))
        if self.fail:
            raise self.fail("simulated")
        return self._res(cid, qty, 110)

    def query_order(self, symbol, cid):
        return self.exists.get(cid)

    def open_orders(self, symbol):
        return []

    def cancel_all(self, symbol):
        self.calls.append(("CANCEL", symbol))


def limits(**kw):
    return RiskLimits(**kw)


def entry(**kw):
    base = dict(quote=50.0, equity=100.0, free_usdt=100.0, open_positions=0, orders_last_hour=0, min_notional=5.0, stoploss_pct=0.03)
    return [v.rule for v in entry_violations(limits(max_position_usdt=60), **{**base, **kw})]


def test_clean_entry_passes():
    assert entry() == []


@pytest.mark.parametrize("kw,rule", [
    ({"quote": 70.0}, "max_position"), ({"free_usdt": 10.0}, "insufficient_balance"), ({"quote": 4.0}, "min_order"), ({"open_positions": 1}, "max_positions"),
    ({"orders_last_hour": 6}, "order_frequency"), ({"stoploss_pct": 0.2}, "trade_risk"), ({"duplicate": True}, "duplicate_order"), ({"stoploss_pct": 0.0}, "no_stoploss"),
])
def test_each_entry_rule_fires(kw, rule):
    assert rule in entry(**kw)


def test_portfolio_breaches():
    l = limits(max_drawdown_pct=10, max_daily_loss_pct=5)
    assert [v.rule for v in portfolio_breaches(l, 89, 100, 89)] == ["max_drawdown"]
    assert [v.rule for v in portfolio_breaches(l, 94, 100, 100)] == ["daily_loss"]
    assert portfolio_breaches(l, 99, 100, 100) == []


def test_secret_roundtrip_is_not_plaintext():
    tok = encrypt("k" * 40, "my-secret")
    assert "my-secret" not in tok and decrypt("k" * 40, tok) == "my-secret"
    with pytest.raises(ValueError):
        encrypt("short", "x")


def test_exchange_client_has_no_dangerous_surface():
    assert not any("withdraw" in p or "margin" in p or "futures" in p or "/fapi" in p or "transfer" in p for _, p in ALLOWED_SIGNED)
    ex = BinanceSpot("http://x", "k", "s")
    with pytest.raises(ExchangeError):
        ex._signed("POST", "/sapi/v1/capital/withdraw/apply")
    assert "k" not in repr(ex).replace("BinanceSpot", "") and "s" not in repr(ex).split("(")[1].replace("http://x", "")


def test_key_with_withdrawal_rights_is_refused():
    class E(BinanceSpot):
        def key_restrictions(self):
            return {"enableWithdrawals": True, "ipRestrict": False, "enableSpotAndMarginTrading": True}

    p = verify_key_is_safe(E("http://x", "k", "s"))
    assert any("withdrawal" in x for x in p) and any("IP" in x for x in p)


# ---- world with a finished evaluation ----

@pytest.fixture
def world(db, tmp_path):
    store = CandleStore(tmp_path)
    df = synthetic(300)
    store.save(PAIR, TF, df)
    with db.session() as s:
        v = version(s, risk={"stoploss_pct": 0.03})
        run = EvaluationRun(duration_days=30, status="finished")
        s.add(run)
        s.flush()
        rep = EvaluationReport(run_id=run.id, is_final=True, rows=[{"strategy_version_id": v.id, "eligible": True, "fails": []}])
        s.add(rep)
        s.add(ExchangeConnection(environment="live", api_key_enc="x", api_secret_enc="y"))
        s.flush()
        ids = (v.id, rep.id)
    return db, store, df, *ids


def auth_args(vid, rep, **kw):
    return {**dict(report_id=rep, strategy_version_id=vid, pairs=[PAIR], max_capital=100.0, max_position=50.0, daily_loss_limit=5.0, max_drawdown_pct=10.0, fee_assumption=0.001, stop_conditions={}, confirmation=approval.CONFIRMATION), **kw}


def test_time_alone_never_authorizes(world):
    db, *_ = world
    with db.session() as s:
        assert "egasining tasdig'i yo'q" in approval.gate_reasons(s, ON, "live")
    with pytest.raises(PermissionError):
        le.start(db, ON, "live")


def test_master_switch_blocks_even_with_authorization(world):
    db, _, _, vid, rep = world
    approval.authorize(db, **auth_args(vid, rep))
    with pytest.raises(PermissionError, match="QL_LIVE_ENABLED"):
        le.start(db, OFF, "live")


@pytest.mark.parametrize("kw", [{"confirmation": "ok"}, {"max_capital": 101.0}, {"max_capital": 40.0}, {"pairs": ["BTC/USDT", "ETH/USDT"]}, {"pairs": ["BTCUP/USDT"]}, {"max_drawdown_pct": 80.0}, {"daily_loss_limit": 0.0}])
def test_bad_authorizations_refused(world, kw):
    db, _, _, vid, rep = world
    with pytest.raises(ValueError):
        approval.authorize(db, **auth_args(vid, rep, **kw))


def test_failed_strategy_cannot_be_authorized(db):
    with db.session() as s:
        v = version(s)
        run = EvaluationRun(duration_days=30, status="finished")
        s.add(run)
        s.flush()
        rep = EvaluationReport(run_id=run.id, is_final=True, rows=[{"strategy_version_id": v.id, "eligible": False, "fails": ["pf"]}])
        s.add(rep)
        s.flush()
        vid, rid = v.id, rep.id
    with pytest.raises(ValueError, match="did not pass"):
        approval.authorize(db, **auth_args(vid, rid))


def engine(world, ex, settings=ON):
    db, store, *_ = world
    return le.LiveEngine(db, settings, store, ex)


def live_ready(world, **kw):
    db, _, _, vid, rep = world
    approval.authorize(db, **auth_args(vid, rep, **kw))
    le.start(db, ON, "live")


def test_entry_exit_cycle_and_no_duplicate_on_retick(world):
    db, _, df, *_ = world
    live_ready(world)
    ex = FakeExchange()
    e = engine(world, ex)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[299])}, set()
    now = int(t[299]) + 3600 + 5
    assert e.tick(now=now, last_price=100) == "entry"
    assert e.tick(now=now, last_price=100) == "no_new_candle"
    assert [c[0] for c in ex.calls] == ["BUY"] and ex.calls[0][1] == pytest.approx(49.95)  # capped by max_position
    with db.session() as s:
        assert s.query(LiveTrade).filter(LiveTrade.exit_ts.is_(None)).count() == 1


def test_engine_stopped_by_default_sends_nothing(world):
    ex = FakeExchange()
    assert engine(world, ex).tick() == "stopped" and ex.calls == []


def test_unknown_order_outcome_halts_then_reconciles_without_resending(world):
    db, _, df, *_ = world
    live_ready(world)
    ex = FakeExchange()
    ex.fail = ExchangeUnknown
    e = engine(world, ex)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[299])}, set()
    now = int(t[299]) + 3605
    e.tick(now=now, last_price=100)
    with db.session() as s:
        assert le.get_portfolio(s, "live").status == "halted"
        assert s.query(LiveOrder).one().status == "unknown"
    ex.fail = None
    e.tick(now=now, last_price=100)
    with db.session() as s:
        assert s.query(LiveOrder).one().status == "filled"
        assert s.query(LiveTrade).count() == 1  # booked from the reconciliation
    assert len(ex.calls) == 1  # never sent a second time


def test_rejection_halts_and_books_nothing(world):
    db, _, df, *_ = world
    live_ready(world)
    ex = FakeExchange()
    ex.fail = ExchangeError
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[299])}, set()
    engine(world, ex).tick(now=int(t[299]) + 3605, last_price=100)
    with db.session() as s:
        assert le.get_portfolio(s, "live").status == "halted" and s.query(LiveTrade).count() == 0


def test_halted_engine_blocks_entries_but_keeps_stop(world):
    db, _, df, *_ = world
    live_ready(world)
    ex = FakeExchange()
    e = engine(world, ex)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[299])}, set()
    now = int(t[299]) + 3605
    e.tick(now=now, last_price=100)
    with db.session() as s:
        le.get_portfolio(s, "live").status = "halted"
    assert e.tick(now=now + 60, last_price=90) == "stoploss"
    assert ex.calls[-1][0] == "SELL"


def test_stale_market_data_opens_nothing(world):
    db, _, df, *_ = world
    live_ready(world)
    ex = FakeExchange()
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[299])}, set()
    assert engine(world, ex).tick(now=int(t[299]) + 3600 * 5, last_price=100) == "stale_data" and ex.calls == []


def test_revoked_authorization_stops_new_orders(world):
    db, _, df, *_ = world
    live_ready(world)
    approval.revoke(db, "live")
    ex = FakeExchange()
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[299])}, set()
    assert engine(world, ex).tick(now=int(t[299]) + 3605, last_price=100) == "no_authorization"
    assert ex.calls == []
    with db.session() as s:
        assert le.get_portfolio(s, "live").status == "halted"


def test_kill_switch_persists_halt_and_closes(world):
    db, _, df, *_ = world
    live_ready(world)
    ex = FakeExchange()
    e = engine(world, ex)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[299])}, set()
    e.tick(now=int(t[299]) + 3605, last_price=100)
    out = le.kill_switch(db, "live", ex)
    assert out["closed"] and ex.calls[-1][0] == "SELL"
    with db.session() as s:
        assert le.get_portfolio(s, "live").status == "halted"
        assert s.query(LiveTrade).one().exit_reason == "kill_switch"
        assert s.query(RiskEvent).filter_by(rule="kill_switch").count() == 1


def test_kill_switch_halts_even_when_exchange_is_down(world):
    db, _, df, *_ = world
    live_ready(world)
    ex = FakeExchange()
    e = engine(world, ex)
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[299])}, set()
    e.tick(now=int(t[299]) + 3605, last_price=100)
    ex.fail = ExchangeUnknown
    out = le.kill_switch(db, "live", ex)
    assert out["halted"] and not out["closed"] and out["error"]
    with db.session() as s:
        assert le.get_portfolio(s, "live").status == "halted"


def test_live_entry_uses_volatility_stake_within_limits(db, tmp_path):
    from quantlab.risk.sizing import stake_series

    store = CandleStore(tmp_path)
    df = synthetic(24 * 70)
    store.save(PAIR, TF, df)
    risk = {"stoploss_pct": 0.03, "sizing": {"mode": "vol_target", "target": 0.005}}
    with db.session() as s:
        v = version(s, risk=risk)
        run = EvaluationRun(duration_days=30, status="finished")
        s.add(run)
        s.flush()
        rep = EvaluationReport(run_id=run.id, is_final=True, rows=[{"strategy_version_id": v.id, "eligible": True, "fails": []}])
        s.add(rep)
        s.add(ExchangeConnection(environment="live", api_key_enc="x", api_secret_enc="y"))
        s.flush()
        vid, rid = v.id, rep.id
    approval.authorize(db, **auth_args(vid, rid, max_position=90.0))
    le.start(db, ON, "live")
    ex = FakeExchange()
    t = df["ts"].to_numpy()
    Scripted.enters, Scripted.exits = {int(t[-1])}, set()
    assert le.LiveEngine(db, ON, store, ex).tick(now=int(t[-1]) + 3605, last_price=100) == "entry"
    stake = stake_series(df[df["ts"] >= int(t[-1]) + 3605 - 40 * 86400].reset_index(drop=True), risk)[-1]
    assert stake < 0.9 and ex.calls[0][1] == pytest.approx(100 * stake * 0.999, abs=0.02)
