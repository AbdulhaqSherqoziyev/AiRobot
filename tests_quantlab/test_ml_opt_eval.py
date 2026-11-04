import json
from datetime import timedelta

import numpy as np
import pytest

from conftest import synthetic
from quantlab.market.store import CandleStore
from quantlab.ml.features import build_features, build_labels, walk_forward_folds
from quantlab.ml.models import make_model
from quantlab.ml.strategy import LightgbmStrategy
from quantlab.ml.training import promote, train_version
from quantlab.models import EvaluationReport, EvaluationRun, ModelVersion, PaperSession, PaperTrade, Strategy
from quantlab.config import Settings
from quantlab.evaluation.report import generate_report, start_run
from quantlab.market.stream import PriceStream
from quantlab.optimize.search import optimize, oos_passes
from quantlab.paper.engine import base_asset
from quantlab.services import JobRunner, enqueue, seed
from quantlab.models import BacktestSession, Job, utcnow
from quantlab.strategies.base import get_strategy

PAIR, TF = "BTC/USDT", "1h"
S = Settings(watchlist=(PAIR,), secret_key="x" * 40)


def test_features_do_not_look_ahead():
    df = synthetic(600)
    full = build_features(df)
    part = build_features(df.iloc[:400].copy())
    np.testing.assert_allclose(full.iloc[:400].to_numpy(dtype=float), part.to_numpy(dtype=float), equal_nan=True)


def test_labels_end_before_unknown_future():
    df = synthetic(100)
    assert build_labels(df, 6).iloc[-6:].isna().all() and build_labels(df, 6).iloc[:-6].notna().all()


def test_walk_forward_is_chronological_and_purged():
    for tr, te in walk_forward_folds(1000, 4, purge=6):
        assert tr.max() + 6 < te.min()


@pytest.mark.parametrize("algo", ["lightgbm", "xgboost", "random_forest", "rl"])
def test_model_fits_and_predicts_probabilities(algo):
    r = np.random.default_rng(0)
    X = r.normal(size=(400, 4))
    y = (X[:, 0] > 0).astype(float)
    m = make_model(algo, n_estimators=20) if algo != "rl" else make_model(algo)
    m.fit(X, y)
    p = m.predict_proba(X)
    assert p.shape == (400,) and ((0 <= p) & (p <= 1)).all()


def test_lstm_learns_a_simple_rule():
    r = np.random.default_rng(0)
    X = r.normal(size=(500, 3))
    y = (X[:, 0] > 0).astype(float)
    m = make_model("lstm", seq=4, epochs=200, hidden=16).fit(X, y)
    p = m.predict_proba(X)
    assert p.shape == (500,) and ((p[3:] >= 0.5) == (y[3:] == 1)).mean() > 0.7


def test_rl_has_no_short_action():
    r = np.random.default_rng(1)
    X = r.normal(size=(300, 4))
    m = make_model("rl").fit(X, (X[:, 0] > 0).astype(float))
    assert all(len(q) == 2 for q in m.q.values())  # flat and long only


@pytest.fixture
def trained(db, tmp_path):
    store = CandleStore(tmp_path)
    store.save(PAIR, TF, synthetic(2000))
    vid = train_version(db, tmp_path, store, "lightgbm", PAIR, TF, hyper={"n_estimators": 20}, folds=2)
    return db, store, vid


@pytest.mark.parametrize("algo,hyper", [("xgboost", {"n_estimators": 10}), ("random_forest", {"n_estimators": 10}), ("rl", {}), ("lstm", {"epochs": 1, "seq": 8})])
def test_every_algo_trains_saves_and_trades_through_the_strategy(db, tmp_path, algo, hyper):
    import joblib

    store = CandleStore(tmp_path)
    store.save(PAIR, TF, synthetic(1600))
    vid = train_version(db, tmp_path, store, algo, PAIR, TF, hyper=hyper, folds=2)
    with db.session() as s:
        path = s.get(ModelVersion, vid).artifact_path
    assert joblib.load(path)["algo"] == algo  # a saved model reloads in another process
    sig = LightgbmStrategy().signals(store.load(PAIR, TF).tail(500).reset_index(drop=True), {"model_path": path})
    assert len(sig) == 500


def test_new_model_is_candidate_with_full_lineage(trained):
    db, store, vid = trained
    with db.session() as s:
        v = s.get(ModelVersion, vid)
        assert v.status == "candidate" and v.dataset_hash and v.features and v.hyperparameters["seed"] == 42
        assert v.validation_metrics["accuracy"] > 0 and "trading" in v.oos_metrics and v.feature_importance
        assert v.train_end_ts < store.load(PAIR, TF)["ts"].iloc[-1]


def test_retrain_never_replaces_promoted_model(trained, tmp_path):
    db, store, v1 = trained
    promote(db, v1)
    v2 = train_version(db, tmp_path, store, "lightgbm", PAIR, TF, hyper={"n_estimators": 20}, folds=2)
    with db.session() as s:
        assert s.get(ModelVersion, v1).status == "promoted" and s.get(ModelVersion, v2).status == "candidate"
    promote(db, v2)
    with db.session() as s:
        assert s.get(ModelVersion, v1).status == "archived" and s.get(ModelVersion, v2).status == "promoted"


def test_ml_strategy_without_model_never_trades(candles):
    sig = LightgbmStrategy().signals(candles, {})
    assert not sig["enter"].any() and not sig["exit"].any()


def test_ml_strategy_uses_pinned_model_without_lookahead(trained):
    db, store, vid = trained
    with db.session() as s:
        path = s.get(ModelVersion, vid).artifact_path
    df = store.load(PAIR, TF)
    st = LightgbmStrategy()
    a = st.signals(df, {"model_path": path})
    b = st.signals(df.iloc[:1500].copy(), {"model_path": path})
    assert a.iloc[:1500].equals(b) and a["enter"].any()


def test_optimizer_keeps_oos_separate_and_reports_top(candles):
    res = optimize(get_strategy("ema_crossover"), candles, TF, trials=8, top_k=3, min_trades=1, fixed={"stoploss_pct": 0.03})
    assert res["trials"] == 8 and 1 <= len(res["top"]) <= 3
    t = res["top"][0]
    assert t["out_of_sample"] != t["in_sample"]
    assert t["eligible"] == (oos_passes(t["out_of_sample"]) and t["in_sample"]["total_return"] > 0)
    assert res["oos_start"] == int(candles["ts"].iloc[int(len(candles) * 0.7)])


def test_optimizer_refuses_too_little_data(candles):
    with pytest.raises(ValueError):
        optimize(get_strategy("ema_crossover"), candles.iloc[:200], TF, trials=2)


@pytest.fixture
def seeded(db, tmp_path):
    seed(db, S)
    store = CandleStore(tmp_path)
    store.save(PAIR, TF, synthetic(1500))
    return db, store


def test_seed_is_idempotent(seeded):
    db, _ = seeded
    seed(db, S)
    with db.session() as s:
        assert s.query(Strategy).filter_by(engine="rsi_reversal").count() == 1
        assert s.query(Strategy).count() >= 15


def test_evaluation_skips_ml_without_model_and_isolates_sessions(seeded):
    db, store = seeded
    run = start_run(db)
    with db.session() as s:
        ps = s.query(PaperSession).filter_by(eval_run_id=run).all()
        assert len(ps) == 10 and all(p.portfolio.initial_balance == 100 for p in ps)
        assert len({p.portfolio.id for p in ps}) == 10
    with pytest.raises(ValueError):
        start_run(db)


def test_report_before_30_days_is_not_final_and_says_extend(seeded):
    db, store = seeded
    run = start_run(db)
    rid = generate_report(db, store, run)
    with db.session() as s:
        rep = s.get(EvaluationReport, rid)
        assert not rep.is_final and s.get(EvaluationRun, run).status == "running"
        assert rep.recommendation["action"] == "extend" and rep.recommendation["limitations"]
        assert all(not r["eligible"] for r in rep.rows)


def test_finished_run_with_no_results_recommends_nothing_and_starts_no_live(seeded):
    from quantlab.models import LiveAuthorization, LivePortfolio

    db, store = seeded
    run = start_run(db)
    rid = generate_report(db, store, run, now_dt=utcnow() + timedelta(days=31))
    with db.session() as s:
        rep = s.get(EvaluationReport, rid)
        assert rep.is_final and s.get(EvaluationRun, run).status == "finished"
        assert rep.recommendation["action"] in ("extend", "none")
        assert s.query(LiveAuthorization).count() == 0 and s.query(LivePortfolio).count() == 0


def test_good_session_passes_screening(seeded):
    db, store = seeded
    run = start_run(db, criteria={"min_trades": 2, "min_oos_return": -100})
    df = store.load(PAIR, TF)
    with db.session() as s:
        ps = s.query(PaperSession).filter_by(eval_run_id=run).first()
        sid = ps.id
        ps.started_at = utcnow() - timedelta(days=31)
        for i, (pnl, pct) in enumerate([(5.0, 5.0), (4.0, 4.0), (-1.0, -1.0)]):
            s.add(PaperTrade(session_id=sid, entry_signal_ts=i, entry_ts=i * 1000 + 1, entry_price=1, qty=1, entry_fee=0.01, exit_ts=i * 1000 + 500, exit_price=1, exit_fee=0.01, pnl=pnl, pnl_pct=pct))
        from quantlab.models import EquitySnapshot

        for i, e in enumerate([100.0, 105.0, 109.0, 108.0]):
            s.add(EquitySnapshot(scope="paper", scope_id=sid, ts=int(df["ts"].iloc[-10 + i]), equity=e))
    rid = generate_report(db, store, run, now_dt=utcnow() + timedelta(days=31))
    with db.session() as s:
        row = next(r for r in s.get(EvaluationReport, rid).rows if r["session_id"] == sid)
        assert row["metrics"]["profit_factor"] == 9.0 and row["fee_impact_pct"] is not None
        assert row["days"] >= 30 and "out_of_sample" in row and row["regimes"]
        # OOS on synthetic data may or may not pass; every other criterion must be satisfied.
        assert not [f for f in row["fails"] if "out-of-sample" not in f]


def test_job_runner_backtest_saves_reproducible_result(seeded):
    db, store = seeded
    runner = JobRunner(db, S, store)
    df = store.load(PAIR, TF)
    with db.session() as s:
        st = s.query(Strategy).filter_by(engine="ema_crossover").one()
        b = BacktestSession(strategy_version_id=st.current_version_id, pair=PAIR, timeframe=TF, start_ts=int(df["ts"].iloc[300]), end_ts=int(df["ts"].iloc[-1]), config={"initial": 100.0})
        s.add(b)
        s.flush()
        enqueue(s, "backtest", {"session_id": b.id})
        bid = b.id
    assert runner.run_one() is True
    with db.session() as s:
        b = s.get(BacktestSession, bid)
        assert b.status == "done" and b.data_hash and b.result.metrics["total_trades"] > 0
        assert s.query(Job).one().status == "done"


def test_job_failure_is_recorded_not_raised(seeded):
    db, store = seeded
    with db.session() as s:
        st = s.query(Strategy).first()
        b = BacktestSession(strategy_version_id=st.current_version_id, pair="NOPE/USDT", timeframe=TF, start_ts=1, end_ts=2)
        s.add(b)
        s.flush()
        enqueue(s, "backtest", {"session_id": b.id})
        bid = b.id
    assert JobRunner(db, S, store).run_one() is True
    with db.session() as s:
        assert s.get(BacktestSession, bid).status == "error" and s.query(Job).one().status == "error"


def test_interrupted_job_is_requeued(seeded):
    db, store = seeded
    with db.session() as s:
        s.add(Job(kind="sync", status="running"))
    assert JobRunner(db, S, store).recover() == 1
    with db.session() as s:
        assert s.query(Job).one().status == "queued"


@pytest.mark.parametrize("drops", [1, 3])
def test_price_stream_reconnects_with_backoff(drops):
    import asyncio
    import json

    delays, attempts = [], []
    stop = asyncio.Event()
    msg = json.dumps({"data": {"s": "BTCUSDT", "c": "123.5"}})

    class Conn:
        async def __aenter__(self):
            attempts.append(1)
            if len(attempts) <= drops:
                raise OSError("down")
            return self

        async def __aexit__(self, *a):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if getattr(self, "done", False):
                stop.set()
                raise StopAsyncIteration
            self.done = True
            return msg

    async def nosleep(d):
        delays.append(d)

    st = PriceStream("wss://x", [PAIR], connect=lambda url: Conn())
    asyncio.run(st.run(stop, sleep=nosleep))
    assert st.prices[PAIR] == 123.5 and st.reconnects == drops
    assert delays == [2.0 ** i for i in range(drops)]


def test_paper_watch_creates_sized_sessions_once(db):
    from quantlab.cli import paper_watch

    st = Settings(watchlist=("BTC/USDT", "ETH/USDT"), secret_key="x" * 40)
    assert paper_watch(db, st) == 2
    assert paper_watch(db, st) == 0
    with db.session() as s:
        ps = s.query(PaperSession).all()
        assert {p.pair for p in ps} == {"BTC/USDT", "ETH/USDT"} and all(p.timeframe == "4h" for p in ps)
        assert all(p.risk["sizing"]["mode"] == "vol_target" and p.portfolio.initial_balance == 100 for p in ps)


def test_seeded_strategies_default_to_study_settings(seeded):
    from quantlab.models import StrategyVersion

    db, _ = seeded
    with db.session() as s:
        v = s.get(StrategyVersion, s.query(Strategy).filter_by(engine="ema_crossover").one().current_version_id)
        assert v.timeframe == "4h" and v.risk["sizing"]["mode"] == "vol_target"


def test_concurrent_seed_on_empty_database_all_succeed(db):
    from concurrent.futures import ThreadPoolExecutor

    from quantlab.models import TradingPair

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda _: seed(db, S), range(6)))
    with db.session() as s:
        assert s.query(TradingPair).filter_by(symbol=PAIR).count() == 1
        assert s.query(Strategy).filter_by(engine="ema_crossover").count() == 1


def test_training_plan_queues_each_combination_once_and_skips_1h(db):
    from quantlab.ml.models import ALGOS
    from quantlab.ml.plan import enqueue_training
    from quantlab.models import TrainingJob

    assert enqueue_training(db, ["BTC/USDT", "ETH/USDT"]) == 2 * 2 * len(ALGOS)
    assert enqueue_training(db, ["BTC/USDT", "ETH/USDT"]) == 0  # nothing piles up
    with db.session() as s:
        assert {t.timeframe for t in s.query(TrainingJob)} == {"4h", "1d"}


# ---- daily review and challengers ----

def test_verdict_needs_a_large_sample_and_a_hard_bar():
    from quantlab.analysis import verdict

    assert verdict(10, 9.0, 3.0) == "namuna_kam"
    assert verdict(50, 2.5, 2.0) == "noaniq"  # 2.5 sigma is common when hundreds run together
    assert verdict(50, 3.6, 1.5) == "umidli"
    assert verdict(50, 3.6, 1.1) == "noaniq"
    assert verdict(50, -2.5, 0.7) == "zararli"


def test_strategy_table_pools_sessions_and_keeps_groups_apart():
    from quantlab.analysis import strategy_table

    row = lambda name, tf, pnl: {"strategy": name, "kind": "technical", "timeframe": tf, "pair": "BTC/USDT", "session_id": 1, "return": 1.0, "dd": -2.0, "bh": -5.0, "pnls": pnl, "pcts": pnl, "fees": 0.1, "days": 3.0}
    t = strategy_table([row("A", "4h", [1.0, -0.5]), row("A", "4h", [2.0]), row("A", "1d", [1.0])])
    a = next(x for x in t if x["timeframe"] == "4h")
    assert a["sessions"] == 2 and a["trades"] == 3 and a["profit_factor"] == 6.0 and a["median_buy_hold"] == -5.0
    assert len(t) == 2


def test_generate_changes_nothing_but_writes_a_report(seeded):
    from quantlab.analysis import generate
    from quantlab.models import AnalysisReport, LiveAuthorization, LivePortfolio, StrategyVersion

    db, store = seeded
    run = start_run(db)
    with db.session() as s:
        before = (s.query(StrategyVersion).count(), s.query(PaperSession).count())
    rid = generate(db, store, [PAIR])
    with db.session() as s:
        r = s.get(AnalysisReport, rid)
        assert r.summary["sessions"] == 10 and "tavsiya etilmaydi" in r.summary["live_recommendation"] and r.findings
        assert (s.query(StrategyVersion).count(), s.query(PaperSession).count()) == before
        assert s.query(LiveAuthorization).count() == 0 and s.query(LivePortfolio).count() == 0


def test_challengers_pick_by_validation_stay_candidates_and_do_not_repeat(db, tmp_path):
    from quantlab.analysis import generate, run_challengers
    from quantlab.models import StrategyVersion

    seed(db, S)
    store = CandleStore(tmp_path)
    store.save(PAIR, "4h", synthetic(2000, step=14400))
    a = train_version(db, tmp_path, store, "lightgbm", PAIR, "4h", name="a", hyper={"n_estimators": 10}, folds=2)
    b = train_version(db, tmp_path, store, "lightgbm", PAIR, "4h", name="b", hyper={"n_estimators": 30}, folds=2, seed=1)
    with db.session() as s:
        cur_before = s.query(Strategy).filter_by(engine="ml_lightgbm").one().current_version_id
        va, vb = (s.get(ModelVersion, a).validation_metrics["auc"], s.get(ModelVersion, b).validation_metrics["auc"])
    assert run_challengers(db, store) == 1
    assert run_challengers(db, store) == 0
    best = a if va >= vb else b
    with db.session() as s:
        ps = s.query(PaperSession).one()
        ver = s.get(StrategyVersion, ps.strategy_version_id)
        assert ver.params()["model_path"] == s.get(ModelVersion, best).artifact_path
        assert ps.portfolio.initial_balance == 100 and ps.risk["sizing"]["mode"] == "vol_target"
        assert s.get(ModelVersion, best).status == "candidate"
        assert s.query(Strategy).filter_by(engine="ml_lightgbm").one().current_version_id == cur_before
    rid = generate(db, store, [PAIR])
    from quantlab.models import AnalysisReport

    with db.session() as s:
        m = s.get(AnalysisReport, rid).models
        assert m and m[0]["status"] == "candidate" and m[0]["forward_samples"] == 0


def test_paper_all_covers_every_combination_once(db):
    from quantlab.cli import paper_all

    st = Settings(watchlist=(PAIR, "ETH/USDT"), secret_key="x" * 40)
    assert paper_all(db, st) == 10 * 2 * 2
    assert paper_all(db, st) == 0
    with db.session() as s:
        assert all(p.risk["sizing"]["mode"] == "vol_target" for p in s.query(PaperSession))
        assert len({p.portfolio.id for p in s.query(PaperSession)}) == 40


def test_paper_digest_is_plain_rare_and_never_repeats(seeded):
    from quantlab.analysis import paper_digest
    from quantlab.models import Notification

    db, store = seeded
    start_run(db)
    T0 = 1_800_000_000
    assert paper_digest(db, now=T0) == 0  # first run only sets the starting point
    with db.session() as s:
        sid = s.query(PaperSession).first().id
        s.add(PaperTrade(session_id=sid, entry_signal_ts=1, entry_ts=2, entry_price=10, qty=1, entry_fee=0))
        s.add(PaperTrade(session_id=sid, entry_signal_ts=3, entry_ts=4, entry_price=10, qty=1, entry_fee=0, exit_ts=9, exit_price=12, pnl=2.0, exit_reason="signal"))
    assert paper_digest(db, now=T0 + 10) == 3  # two entries, one exit
    assert paper_digest(db, now=T0 + 20) == 0  # nothing new
    with db.session() as s:
        s.add(PaperTrade(session_id=sid, entry_signal_ts=5, entry_ts=6, entry_price=10, qty=1, entry_fee=0, exit_ts=19, exit_price=9, pnl=-1.0, exit_reason="stoploss"))
    assert paper_digest(db, now=T0 + 30) == 0  # held back: at most every 12 hours
    assert paper_digest(db, now=T0 + 10 + 12 * 3600) == 2
    with db.session() as s:
        n = s.query(Notification).filter_by(category="paper").order_by(Notification.id).first()
        assert "virtual" in n.title and "Natija: +2.00 USDT" in n.text and "\n" in n.text


def test_training_a_batch_sends_one_message_not_one_per_model(db, tmp_path):
    from quantlab.analysis import run_challengers
    from quantlab.models import Notification

    seed(db, S)
    store = CandleStore(tmp_path)
    store.save(PAIR, "4h", synthetic(2000, step=14400))
    for name in ("a", "b", "c"):
        train_version(db, tmp_path, store, "lightgbm", PAIR, "4h", name=name, hyper={"n_estimators": 10}, folds=2)
    run_challengers(db, store)
    with db.session() as s:
        ml = s.query(Notification).filter_by(category="ml").all()
        assert len(ml) == 1 and "3 ta yangi model" in ml[0].text and "Real savdoga" in ml[0].text


def test_telegram_groups_virtual_stops_but_keeps_real_money_separate(db):
    import httpx

    from quantlab.notify.service import dispatch_telegram, notify

    sent = []
    client = httpx.Client(transport=httpx.MockTransport(lambda r: (sent.append(json.loads(r.content)["text"]), httpx.Response(200))[1]))
    with db.session() as s:
        for i in range(5):
            notify(s, "risk", f"Risk chegarasi: EMA {i}", "drawdown", "warn", "paper")
        notify(s, "live", "REAL SAVDO TO'XTATILDI (live)", "sabab", "err", "live")
        notify(s, "ml", "AI o'qitish tugadi", "x")
    assert dispatch_telegram(db, "t", "c", client) == 3
    assert "5 ta virtual sessiya" in sent[0] and "yana 2 ta" in sent[0] and sent[0].startswith("⚠️ TEST")
    assert sent[1].startswith("🔴 REAL SAVDO") and sent[2].startswith("🧠")
    assert dispatch_telegram(db, "t", "c", client) == 0


def test_telegram_outage_keeps_messages_for_later(db):
    import httpx

    from quantlab.notify.service import dispatch_telegram, notify

    with db.session() as s:
        notify(s, "live", "REAL", "x", "err", "live")
    down = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(502)))
    assert dispatch_telegram(db, "t", "c", down) == 0
    up = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert dispatch_telegram(db, "t", "c", up) == 1


def test_daily_text_is_short_and_says_real_trading_is_off():
    from quantlab.analysis import daily_text

    rows = [{"pnls": [1.0, -0.5]}]
    table = [{"strategy": "ATR", "timeframe": "4h", "trades": 2, "median_return": 0.5}]
    t = daily_text(rows, table, {"sessions": 3, "closed_trades": 2, "halted": 0, "promising": 0})
    assert "+0.50 USDT" in t and "hali erta" in t and "Real savdo: o'chiq" in t and len(t.splitlines()) <= 6
