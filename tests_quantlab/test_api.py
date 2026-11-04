import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import synthetic
from quantlab.api.app import create_app
from quantlab.api.auth import make_token, read_token
from quantlab.config import Settings
from quantlab.evaluation.approval import CONFIRMATION
from quantlab.market.binance import BinanceError, BinancePublic
from quantlab.market.store import CandleStore
from quantlab.models import ExchangeConnection, Strategy, SystemSetting
from quantlab.services import JobRunner

PW = "correct horse battery"


@pytest.fixture
def ctx(db, tmp_path):
    st = Settings(secret_key="k" * 40, owner_password=PW, data_dir=tmp_path, watchlist=("BTC/USDT", "ETH/USDT"), secure_cookies=False, live_enabled=True)
    client = BinancePublic("http://nowhere.invalid", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))), retries=1, sleep=lambda x: None)
    app = create_app(st, db, client)
    c = TestClient(app, headers={"x-ql": "1"})
    return c, db, st, tmp_path


def login(c):
    r = c.post("/auth/login", json={"username": "owner", "password": PW})
    assert r.status_code == 200
    return c


def sid(db, engine="ema_crossover"):
    with db.session() as s:
        return s.query(Strategy).filter_by(engine=engine).one().id


def test_refuses_to_start_without_secret(db):
    with pytest.raises(RuntimeError):
        create_app(Settings(secret_key="short"), db)


@pytest.mark.parametrize("path", ["/snapshot", "/engines", "/live/status", "/system/monitor", "/settings/credentials", "/evaluation"])
def test_everything_needs_login(ctx, path):
    assert ctx[0].get(path).status_code == 401


def test_health_is_public_and_bare(ctx):
    assert ctx[0].get("/health").json() == {"ok": True}


def test_login_rate_limit_locks(ctx):
    c, *_ = ctx
    for _ in range(5):
        assert c.post("/auth/login", json={"username": "owner", "password": "wrong"}).status_code == 401
    assert c.post("/auth/login", json={"username": "owner", "password": PW}).status_code == 429


def test_session_cookie_flags(ctx):
    r = ctx[0].post("/auth/login", json={"username": "owner", "password": PW})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_token_tamper_and_expiry():
    t = make_token("s" * 40, "owner", now=1000)
    assert read_token("s" * 40, t, now=1001) == "owner"
    assert read_token("s" * 40, t, now=10**10) is None
    assert read_token("z" * 40, t, now=1001) is None
    assert read_token("s" * 40, "x" + t, now=1001) is None


def test_mutation_needs_custom_header(ctx):
    c, db, *_ = ctx
    login(c)
    r = c.post(f"/strategies/{sid(db)}/clone", headers={"x-ql": ""})
    assert r.status_code == 403


def test_snapshot_on_empty_system_invents_nothing(ctx):
    c, *_ = ctx
    d = login(c).get("/snapshot").json()
    assert d["sessions"] == [] and d["trades"] == [] and d["models"] == [] and d["notifications"] == []
    assert len(d["strategies"]) >= 15 and all(not x["hasBacktest"] and x["ret"] == 0 for x in d["strategies"])
    assert d["portfolio"]["equity"] == []


def test_strategy_lifecycle_and_immutable_versions(ctx):
    c, db, *_ = ctx
    login(c)
    r = c.post("/strategies", json={"name": "Mine", "engine": "rsi_reversal", "params": {"period": 10}})
    assert r.status_code == 200
    new = r.json()["id"]
    assert c.post("/strategies", json={"name": "Mine", "engine": "rsi_reversal"}).status_code == 409
    assert c.post("/strategies", json={"name": "Bad", "engine": "rsi_reversal", "params": {"period": 500}}).status_code == 400
    assert c.post(f"/strategies/{new}/versions", json={"params": {"period": 20}, "pairs": ["ETH/USDT"], "timeframe": "4h"}).status_code == 200
    vs = c.get(f"/strategies/{new}/versions").json()
    assert [v["params"]["period"] for v in vs] == [10, 20] and vs[1]["current"]
    assert c.patch(f"/strategies/{new}", json={"enabled": False}).status_code == 200
    clone = c.post(f"/strategies/{new}/clone").json()
    assert "nusxa" in clone["name"]
    assert c.delete(f"/strategies/{clone['id']}").status_code == 200


def test_used_strategy_cannot_be_deleted(ctx):
    c, db, *_ = ctx
    login(c)
    i = sid(db)
    assert c.post("/paper/sessions", json={"strategy_id": i, "pair": "BTC/USDT"}).status_code == 200
    assert c.delete(f"/strategies/{i}").status_code == 409


def test_backtest_through_worker_and_export(ctx):
    c, db, st, tmp = ctx
    store = CandleStore(tmp)
    df = synthetic(800)
    store.save("BTC/USDT", "1h", df)
    login(c)
    r = c.post("/backtests", json={"strategy_id": sid(db), "pair": "BTC/USDT", "timeframe": "1h", "start_ts": int(df["ts"].iloc[300]), "end_ts": int(df["ts"].iloc[-1])}).json()
    assert c.get(f"/backtests/{r['id']}").json()["status"] == "queued"
    assert JobRunner(db, st, store).run_one()
    d = c.get(f"/backtests/{r['id']}").json()
    assert d["status"] == "done" and d["metrics"]["total_trades"] > 0 and d["equity"] and d["candles"] and d["data_hash"]
    assert "entry_ts" in c.get(f"/backtests/{r['id']}/export.csv").text
    snap = c.get("/snapshot").json()
    row = next(x for x in snap["strategies"] if x["engine"] == "ema_crossover")
    assert row["hasBacktest"] and row["trades"] == d["metrics"]["total_trades"]


def test_paper_session_controls(ctx):
    c, db, *_ = ctx
    login(c)
    i = c.post("/paper/sessions", json={"strategy_id": sid(db), "pair": "BTC/USDT", "capital": 250}).json()["id"]
    assert c.post(f"/paper/sessions/{i}/pause").json()["status"] == "paused"
    assert c.post(f"/paper/sessions/{i}/resume").json()["status"] == "running"
    assert c.post(f"/paper/sessions/{i}/stop").json()["status"] == "stopped"
    assert c.post(f"/paper/sessions/{i}/pause").status_code == 400
    assert c.post(f"/paper/sessions/{i}/explode").status_code == 404
    s = c.get("/snapshot").json()["sessions"][0]
    assert s["start"] == 250 and s["equity"] == 250


def test_leveraged_token_session_refused(ctx):
    c, db, *_ = ctx
    assert login(c).post("/paper/sessions", json={"strategy_id": sid(db), "pair": "BTCUP/USDT"}).status_code == 400


def test_ml_session_needs_model(ctx):
    c, db, *_ = ctx
    assert login(c).post("/paper/sessions", json={"strategy_id": sid(db, "ml_lightgbm"), "pair": "BTC/USDT"}).status_code == 400


def test_credentials_are_encrypted_and_never_returned(ctx):
    c, db, *_ = ctx
    login(c)
    key, secret = "PLAINKEYabcd1234", "PLAINSECRETxyz789"
    assert c.put("/settings/credentials", json={"environment": "live", "api_key": key, "api_secret": secret}).status_code == 200
    with db.session() as s:
        row = s.query(ExchangeConnection).one()
        assert key not in row.api_key_enc and secret not in row.api_secret_enc
    for path in ("/settings/credentials", "/snapshot", "/live/status", "/system/logs"):
        body = c.get(path).text
        assert key not in body and secret not in body
    assert c.get("/settings/credentials").json()[0]["hint"] == "1234"


def test_live_cannot_start_without_authorization(ctx):
    c, db, *_ = ctx
    login(c)
    r = c.post("/live/start", json={"environment": "live", "password": PW})
    assert r.status_code == 403


def test_live_start_needs_password(ctx):
    c, *_ = ctx
    assert login(c).post("/live/start", json={"environment": "live", "password": "nope"}).status_code == 403


def test_authorization_needs_password_and_final_report(ctx):
    c, db, *_ = ctx
    login(c)
    body = {"strategy_version_id": 1, "pairs": ["BTC/USDT"], "max_capital": 100, "max_position": 50, "daily_loss_limit": 5, "max_drawdown_pct": 10, "confirmation": CONFIRMATION}
    assert c.post("/live/authorize", json={**body, "password": "bad"}).status_code == 403
    r = c.post("/live/authorize", json={**body, "password": PW})
    assert r.status_code == 400 and "final" in r.json()["detail"]


def test_kill_works_with_nothing_configured_and_persists(ctx):
    c, *_ = ctx
    login(c)
    assert c.post("/live/kill", json={"environment": "live"}).json()["halted"]
    assert c.get("/live/status").json()["status"] == "halted"


def test_settings_allowlist_and_monitor(ctx):
    c, *_ = ctx
    login(c)
    assert c.put("/settings/risk", json={"value": {"x": 1}}).status_code == 200
    assert c.get("/settings/risk").json()["x"] == 1
    assert c.put("/settings/evil", json={"value": {}}).status_code == 404
    m = c.get("/system/monitor").json()
    assert m["database"]["ok"] and "cpu_pct" in m and m["binance"]["ok"] is False  # upstream mocked down


def test_notifications_read_and_delete(ctx):
    from quantlab.notify.service import notify

    c, db, *_ = ctx
    login(c)
    with db.session() as s:
        notify(s, "system", "t")
    n = c.get("/snapshot").json()["notifications"][0]
    assert not n["read"]
    c.post("/notifications/read", json=None)
    assert c.get("/snapshot").json()["notifications"][0]["read"]
    c.delete(f"/notifications/{n['dbId']}")
    assert c.get("/snapshot").json()["notifications"] == []


def test_public_client_retries_then_raises_and_honours_rate_limit():
    calls, waits = [], []

    def handler(r):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "7"}) if len(calls) == 1 else httpx.Response(200, json=[])

    c = BinancePublic("http://x", client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=waits.append)
    assert c.klines("BTC/USDT", "1h") == [] and waits == [7.0]
    bad = BinancePublic("http://x", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))), retries=2, sleep=lambda x: None)
    with pytest.raises(BinanceError):
        bad.ping()
    four = BinancePublic("http://x", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad"))), sleep=lambda x: None)
    with pytest.raises(BinanceError):
        four.ping()


def test_store_sync_is_incremental_and_excludes_forming_candle(tmp_path):
    rows_by_call = []

    def kl(start):
        return [[(start + i * 3600) * 1000, "1", "2", "0.5", "1.5", "10", 0, "0", 0, "0", "0", "0"] for i in range(3)]

    class C:
        def klines(self, pair, tf, start_ms=None, end_ms=None, limit=1000):
            rows_by_call.append(start_ms)
            s = start_ms // 1000
            return [r for r in kl(s) if r[0] <= end_ms]

    store = CandleStore(tmp_path, C())
    now = 3600 * 1000 + 1800
    store.sync("BTC/USDT", "1h", since_ts=3600 * 995, now=now)
    df = store.load("BTC/USDT", "1h")
    assert df["ts"].iloc[-1] == 3600 * 999  # candle 1000 is still forming
    n = len(rows_by_call)
    store.sync("BTC/USDT", "1h", now=now)
    assert len(rows_by_call) == n  # nothing new to fetch
    store.sync("BTC/USDT", "1h", now=3600 * 1001 + 5)
    assert store.load("BTC/USDT", "1h")["ts"].iloc[-1] == 3600 * 1000
    assert store.load("BTC/USDT", "1h")["ts"].is_unique


def test_rule_builder_strategy_roundtrip(ctx):
    c, db, st, tmp = ctx
    store = CandleStore(tmp)
    df = synthetic(800)
    store.save("BTC/USDT", "1h", df)
    login(c)
    rules = {"join": {"entry": "AND", "exit": "OR"}, "entry": [{"ind": "rsi", "op": "lt", "kind": "num", "val": "40"}, {"ind": "emaF", "op": "gt", "kind": "ind", "val": "emaS"}], "exit": [{"ind": "rsi", "op": "gt", "kind": "num", "val": "65"}], "prm": {"rsiP": 14}}
    r = c.post("/strategies", json={"name": "Built", "engine": "rule_builder", "params": {"rules": rules}})
    assert r.status_code == 200, r.text
    bad = {**rules, "entry": [{"ind": "__import__", "op": "lt", "kind": "num", "val": "1"}]}
    assert c.post("/strategies", json={"name": "Evil", "engine": "rule_builder", "params": {"rules": bad}}).status_code == 400
    assert c.post("/strategies", json={"name": "Empty", "engine": "rule_builder", "params": {"rules": {"entry": []}}}).status_code == 400
    b = c.post("/backtests", json={"strategy_id": r.json()["id"], "pair": "BTC/USDT", "timeframe": "1h", "start_ts": int(df["ts"].iloc[300]), "end_ts": int(df["ts"].iloc[-1])}).json()
    assert JobRunner(db, st, store).run_one()
    d = c.get(f"/backtests/{b['id']}").json()
    assert d["status"] == "done" and d["metrics"]["total_trades"] > 0


def test_rule_signals_have_no_lookahead(candles):
    from quantlab.strategies.rules import RuleBuilder

    rules = {"entry": [{"ind": "macdLine", "op": "xa", "kind": "ind", "val": "macdSig"}], "exit": [{"ind": "close", "op": "lt", "kind": "ind", "val": "bbl"}]}
    s = RuleBuilder()
    full, part = s.signals(candles, {"rules": rules}), s.signals(candles.iloc[:900].copy(), {"rules": rules})
    assert (full.iloc[:900].to_numpy() == part.to_numpy()).all()


def test_rule_indicators_match_the_builder_labels(candles):
    from quantlab.strategies import indicators as ind
    from quantlab.strategies.rules import _series

    hist = ind.macd(candles["close"])[2]
    assert _series(candles, "macd", {}).equals(hist)
    atr = _series(candles, "atr", {}).dropna()
    assert atr.between(0, 100).all() and atr.median() < 20  # a percentage, not a price distance
