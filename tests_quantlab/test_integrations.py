"""Microstructure, Jesse interop, sweep discipline, AI boundaries and the API routes."""

import ast
import json
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from conftest import synthetic
from quantlab.ai_analysis import backends, service
from quantlab.ai_analysis.evidence import build_pack
from quantlab.ai_analysis.schema import InvalidRecommendation, Recommendation, check_against_pack
from quantlab.api.app import create_app
from quantlab.backtest.core import ExecConfig, Filters
from quantlab.backtest.engine import run_on_signals
from quantlab.config import Settings
from quantlab.market.binance import BinancePublic
from quantlab.market.microstructure import MicrostructureMonitor, Thresholds, analyze
from quantlab.market.store import CandleStore
from quantlab.models import AiReport, Experiment, ExperimentResult, Job
from quantlab.research import robustness, sweep
from quantlab.research.sweep import SweepConfig, expand_grid, run_sweep, split_indices, wf_windows
from quantlab.services import JobRunner
from quantlab.strategies import indicators as ind
from quantlab.strategies import interop
from quantlab.strategies.base import get_strategy

FIX = Path(__file__).parent / "fixtures" / "jesse"
PW = "correct horse battery"
BOOK = {"lastUpdateId": 9, "bids": [["100", "2"], ["99.9", "5"], ["99", "100"], ["90", "1000"]], "asks": [["100.2", "1"], ["100.3", "4"], ["101", "100"], ["110", "1000"]]}


# ---- microstructure ----
def test_book_metrics_match_hand_calculation():
    m = analyze(BOOK, bands_bps=(50,), notional=300.0, fee=0.001)
    assert m["best_bid"] == 100 and m["best_ask"] == 100.2 and m["mid"] == pytest.approx(100.1)
    assert m["spread"] == pytest.approx(0.2)
    assert m["spread_bps"] == pytest.approx(0.2 / 100.1 * 1e4)
    d = m["depth"][0]  # band 99.5995 .. 100.6005
    assert d["bid_quote"] == pytest.approx(100 * 2 + 99.9 * 5)
    assert d["ask_quote"] == pytest.approx(100.2 + 100.3 * 4)
    assert d["imbalance"] == pytest.approx((699.5 - 501.4) / (699.5 + 501.4), abs=1e-3)
    assert d["complete"] is True
    # Buying 300 USDT: 100.2 from the first level, 199.8 from the second.
    vwap = 300 / (1 + 199.8 / 100.3)
    assert m["liquidity"]["buy"]["vwap"] == pytest.approx(vwap)
    assert m["liquidity"]["buy"]["slippage_bps"] == pytest.approx((vwap / 100.1 - 1) * 1e4)


def test_maker_edge_is_negative_when_spread_is_below_fees():
    m = analyze(BOOK, fee=0.001)
    assert m["maker_round_trip"]["edge_bps"] == pytest.approx(m["spread_bps"] - 20)
    assert m["maker_round_trip"]["viable"] is False


def test_short_book_is_flagged_not_understated():
    book = {"bids": [["100", "1"]], "asks": [["100.01", "1"]]}
    m = analyze(book, bands_bps=(50,), notional=1000.0)
    assert m["depth"][0]["complete"] is False
    assert m["liquidity"]["buy"]["filled"] is False
    assert {"thin_depth", "book_too_short"} <= {w["code"] for w in m["warnings"]}


def test_abnormal_books_raise_warnings():
    assert "wide_spread" in {w["code"] for w in analyze({"bids": [["100", "99"]], "asks": [["102", "99"]]})["warnings"]}
    assert "crossed_book" in {w["code"] for w in analyze({"bids": [["101", "99"]], "asks": [["100", "99"]]})["warnings"]}
    with pytest.raises(ValueError):
        analyze({"bids": [], "asks": []})


def test_monitor_makes_failure_and_staleness_visible():
    now = [1000.0]
    calls = {"fail": True}

    def fetch(pair, limit):
        if calls["fail"]:
            raise RuntimeError("connection refused")
        return BOOK

    mon = MicrostructureMonitor(fetch, ttl=5, thresholds=Thresholds(stale_seconds=30), clock=lambda: now[0])
    v = mon.get("BTC/USDT")
    assert v["status"] == "error" and "refused" in v["error"] and v["metrics"] is None and v["consecutive_failures"] == 1
    calls["fail"] = False
    now[0] += 6
    v = mon.get("BTC/USDT")
    assert v["status"] == "ok" and v["age_seconds"] == 0 and v["metrics"]["best_bid"] == 100
    calls["fail"] = True
    now[0] += 6
    v = mon.get("BTC/USDT")
    assert v["status"] == "stale" and v["metrics"]["best_bid"] == 100 and v["error"]  # keeps last good, says so


# ---- Jesse: against real Jesse output produced by fixtures/jesse/run_jesse_parity.py ----
@pytest.fixture(scope="module")
def jesse():
    d = json.loads((FIX / "jesse_results.json").read_text())
    df = pd.DataFrame(d["hourly_candles"], columns=["ts", "open", "high", "low", "close", "volume"])
    d["df"] = df
    d["start_ts"] = int(pd.Timestamp(d["start"], tz="UTC").timestamp())
    return d


def _ours(j, key, slippage=0.0):
    sig = get_strategy(key).signals(j["df"])
    cfg = ExecConfig(fee=j["fee"], slippage=slippage, stake_pct=0.95, filters=Filters(min_notional=0.0))
    return run_on_signals(j["df"], sig["enter"].to_numpy(), sig["exit"].to_numpy(), j["timeframe"], j["initial"], cfg, start_ts=j["start_ts"])


@pytest.mark.parametrize("key,cls", [("jesse_ema_cross", "QlEmaCross"), ("jesse_rsi_trend", "QlRsiTrend")])
def test_same_signals_as_real_jesse(jesse, key, cls):
    """Signal parity is exact; a Jesse fill stamped in candle T is our signal candle T."""
    out = _ours(jesse, key)
    fills = jesse["results"][cls]["fills"]
    j_buys = [f[1] for f in fills if f[0] == "buy"]
    j_sells = [f[1] for f in fills if f[0] == "sell"]
    step = 3600
    assert [t["entry_ts"] - step for t in out.trades] == j_buys[: len(out.trades)]
    assert [t["exit_ts"] - step for t in out.trades] == j_sells[: len(out.trades)]
    assert len(j_buys) - len(out.trades) <= 1  # a signal on the last candle fills only in Jesse


@pytest.mark.parametrize("key,cls", [("jesse_ema_cross", "QlEmaCross"), ("jesse_rsi_trend", "QlRsiTrend")])
def test_returns_differ_only_by_the_documented_fill_rule(jesse, key, cls):
    """Same data, fee and sizing, no slippage. BTC next-open is within cents of the previous close,
    and Jesse takes the spot fee from the coin, so close but not equal: 7.29 vs 7.28, 7.99 vs 7.96."""
    ours = _ours(jesse, key).metrics
    theirs = jesse["results"][cls]
    assert abs(ours["total_return"] - theirs["net_profit_percentage"]) < 0.1
    assert ours["total_return"] != theirs["net_profit_percentage"]
    assert ours["fees_paid"] == pytest.approx(theirs["fee"], rel=0.01)
    # Our slippage is a cost Jesse does not model, so it can only lower the result.
    assert _ours(jesse, key, slippage=0.0005).metrics["total_return"] < ours["total_return"]


@pytest.mark.parametrize("name,fn", [
    ("rsi14", lambda df: ind.rsi(df["close"], 14)), ("ema20", lambda df: ind.ema(df["close"], 20)), ("sma20", lambda df: ind.sma(df["close"], 20)),
    ("atr14", lambda df: ind.atr(df, 14)), ("adx14", lambda df: ind.adx(df, 14)[0]), ("macd", lambda df: ind.macd(df["close"], 12, 26, 9)[0]),
    ("macd_signal", lambda df: ind.macd(df["close"], 12, 26, 9)[1]), ("bb_upper", lambda df: ind.bollinger(df["close"], 20, 2)[2]), ("bb_lower", lambda df: ind.bollinger(df["close"], 20, 2)[0]),
])
def test_indicators_equal_jesse_after_warmup(jesse, name, fn):
    theirs = np.array([np.nan if x is None else x for x in json.loads((FIX / "jesse_indicators.json").read_text())[name]], dtype=float)
    ours = fn(jesse["df"]).to_numpy(dtype=float)
    assert np.nanmax(np.abs(ours[-500:] - theirs[-500:]) / np.abs(theirs[-500:])) < 1e-5


def test_new_strategies_do_not_disturb_the_registry_or_seeding(db, tmp_path):
    """The deployed paper test depends on exactly the seeded set staying the same."""
    from quantlab.models import Strategy as Row
    from quantlab.services import seed
    from quantlab.strategies.base import REGISTRY, all_strategies
    from quantlab.strategies.rules import RuleBuilder

    all_strategies()
    assert REGISTRY["rule_builder"] is RuleBuilder and "" not in REGISTRY
    seed(db, _settings(tmp_path))
    with db.session() as s:
        engines = {r.engine for r in s.query(Row).all()}
    assert not engines & {"jesse_ema_cross", "jesse_rsi_trend", "rsi_ema_trend", "rule_builder"}


def test_spec_conversion_refuses_what_it_cannot_honour():
    base = interop.JESSE_SPECS["jesse_ema_cross"]
    for bad in ({**base, "order_type": "limit"}, {**base, "should_short": [{"x": 1}]}, {**base, "take_profit_ladder": [1, 2]},
                {**base, "should_long": [{"left": {"indicator": "cci", "period": 20}, "op": ">", "right": 0}]},
                {**base, "should_long": [{"left": "close", "op": "~", "right": 1}]}, {**base, "should_long": []}):
        with pytest.raises(interop.UnsupportedSpec):
            interop.spec_to_rules(bad)


def test_compatibility_report_is_complete_and_honest():
    r = interop.compatibility_report()
    assert r["indicators"]["supported_count"] == 7 and r["indicators"]["jesse_total"] > 150
    assert set(r["indicators"]["supported"]).isdisjoint(r["indicators"]["unsupported"])
    assert "4h" in r["timeframes"]["supported"] and "1D" in r["timeframes"]["supported"]
    assert "1M" in r["timeframes"]["unsupported"] and "1m" in r["timeframes"]["supported"]  # a month is not a minute
    assert any(d["topic"] == "Slippage" for d in r["execution_differences"])


# ---- sweep discipline ----
def test_segments_never_overlap_and_stay_ordered():
    seg = split_indices(1000, 100, 0.6, 0.2)
    assert seg["train"] == (100, 640) and seg["validation"] == (640, 820) and seg["test"] == (820, 1000)
    for start, oos, end in wf_windows(100, 820, 4):
        assert start < oos < end <= 820  # walk-forward never reaches the test segment


def test_grid_is_validated_against_strategy_bounds():
    s = get_strategy("rsi_ema_trend")
    assert len(expand_grid(s, sweep.PRESETS["rsi_ema_example"]["grid"])) == 576
    with pytest.raises(ValueError):
        expand_grid(s, {"rsi_period": [1000]})
    with pytest.raises(ValueError):
        expand_grid(s, {"nonsense": [1]})
    assert expand_grid(s, {"ema_fast": [20, 50], "ema_slow": [20, 50]}) == [{"ema_fast": 20, "ema_slow": 50}]


def _sweep(seed=7, n=3000, **kw):
    frames = {"AAA/USDT": synthetic(n, seed=seed, step=14400), "BBB/USDT": synthetic(n, seed=seed + 1, step=14400)}
    start = int(frames["AAA/USDT"]["ts"].iloc[200])
    grid = {"rsi_period": [7, 14], "rsi_entry": [30, 35], "rsi_exit": [65, 70], "ema_fast": [5], "ema_slow": [30]}
    return frames, start, grid, run_sweep(frames, get_strategy("rsi_ema_trend"), grid, "4h", start, SweepConfig(backend="native", **kw))


def test_sweep_is_reproducible_and_keeps_every_set():
    *_, a = _sweep()
    *_, b = _sweep()
    assert len(a["rows"]) == 8
    assert a["rows"] == b["rows"]
    assert a["summary"] == b["summary"]
    assert a["repro"]["data_hash"] == b["repro"]["data_hash"] and a["repro"]["backend"] == "native"


def test_test_segment_cannot_influence_the_choice():
    """Corrupting candles inside the test segment leaves train/validation results and the choice alone."""
    frames = {"AAA/USDT": synthetic(3000, seed=7, step=14400), "BBB/USDT": synthetic(3000, seed=8, step=14400)}
    start = int(frames["AAA/USDT"]["ts"].iloc[200])
    grid = {"rsi_period": [7, 14], "rsi_entry": [45, 50], "rsi_exit": [55, 60], "ema_fast": [5], "ema_slow": [30]}
    strat = get_strategy("rsi_ema_trend")
    base = run_sweep(frames, strat, grid, "4h", start, SweepConfig(backend="native"))
    assert base["summary"]["selected"] is not None  # otherwise this test proves nothing
    changed = {}
    for pair, df in frames.items():
        cut = split_indices(len(df), int(np.searchsorted(df["ts"], start)), 0.6, 0.2)["test"][0]
        d = df.copy()
        for col in ("open", "high", "low", "close"):
            d.loc[d.index[cut + 1 :], col] = d[col].iloc[cut + 1 :] * np.linspace(1, 5, len(d) - cut - 1)
        changed[pair] = d
    out = run_sweep(changed, strat, grid, "4h", start, SweepConfig(backend="native"))
    assert out["summary"]["selected"] == base["summary"]["selected"]
    assert [r["validation"] for r in out["rows"]] == [r["validation"] for r in base["rows"]]
    assert [r["train"] for r in out["rows"]] == [r["train"] for r in base["rows"]]
    assert out["summary"]["walk_forward"] == base["summary"]["walk_forward"]
    assert out["summary"]["test_pooled"] != base["summary"]["test_pooled"]


def test_sharpe_is_hidden_when_trades_are_too_few():
    assert sweep.slim({"total_trades": 3, "sharpe": 9.0, "sortino": 9.0})["sharpe"] is None
    assert sweep.slim({"total_trades": 30, "sharpe": 1.5, "sortino": 2.0})["sharpe"] == 1.5


def _passing():
    return {"selected": {"a": 1}, "test_pooled": {"total_return": 5.0, "profit_factor": 1.5, "max_drawdown": -10.0}, "test_trades_by_pair": {"A": 30}, "walk_forward": {"positive_share": 0.75}, "sensitivity": {"stability": 0.8}, "pair_positive_share": 1.0, "engine_gap_max_pct": 0.1, "regimes_covered": ["bear", "bull"]}


def test_eligibility_never_grants_live_and_each_gate_bites():
    e = sweep.eligibility(_passing())
    assert e["status"] == "paper_candidate" and "qulflangan" in e["live"]
    for change in ({"selected": None}, {"test_trades_by_pair": {"A": 19}}, {"test_pooled": {**_passing()["test_pooled"], "total_return": -0.1}}, {"test_pooled": {**_passing()["test_pooled"], "profit_factor": 1.0}},
                   {"test_pooled": {**_passing()["test_pooled"], "max_drawdown": -26.0}}, {"walk_forward": {"positive_share": 0.5}}, {"sensitivity": {"stability": 0.4}}, {"pair_positive_share": 0.0}, {"engine_gap_max_pct": 9.0}, {"regimes_covered": ["bull"]}):
        assert sweep.eligibility({**_passing(), **change})["status"] == "rejected", change


def test_monte_carlo_is_seeded_and_refuses_small_samples():
    r = [2.0, -1.0, 3.0, -2.0, 1.5, 0.5, -0.5]
    assert robustness.monte_carlo_trades(r) == robustness.monte_carlo_trades(r)
    m = robustness.monte_carlo_trades(r)
    assert m["return_p5"] <= m["return_p50"] <= m["return_p95"] and 0 <= m["prob_loss"] <= 1
    assert robustness.monte_carlo_trades(r[:3])["sims"] == 0
    assert robustness.monte_carlo_trades([1.0] * 10)["max_dd_p50"] == 0


def test_sensitivity_flags_a_lone_peak():
    grid = {"a": [1, 2, 3]}
    rows = {robustness.params_key({"a": i}): {"v": v} for i, v in ((1, -5.0), (2, 30.0), (3, -4.0))}
    r = robustness.sensitivity({"a": 2}, rows, grid, lambda x: x["v"])
    assert r["stability"] == 0.0 and r["neighbors"] == 2


# ---- AI boundaries ----
def _pack(now=None):
    df = synthetic(600, step=14400)
    return df, build_pack(df, "BTC/USDT", "4h", now=now or float(df["ts"].iloc[-1] + 14400))


def test_pack_uses_closed_candles_only_and_states_what_is_missing():
    df = synthetic(600, step=14400)
    last = int(df["ts"].iloc[-1])
    p = build_pack(df, "BTC/USDT", "4h", now=last + 100)  # last candle still open
    assert p["last_closed_candle_ts"] == int(df["ts"].iloc[-2])
    assert p["unavailable"]["news"] and p["unavailable"]["sentiment"] and p["unavailable"]["order_book"]
    tampered = df.copy()
    tampered.loc[tampered.index[-1], "close"] = 1e9
    assert build_pack(tampered, "BTC/USDT", "4h", now=last + 100)["indicators"] == p["indicators"]


def test_baseline_output_passes_its_own_validation():
    _, p = _pack()
    a = backends.RuleBaseline().analyze(p)
    check_against_pack(a.recommendation, p)
    assert a.recommendation.confidence.level == "low" and "news" in a.recommendation.missing_data


def _rec(p, **over):
    base = backends.RuleBaseline().analyze(p).recommendation.model_dump()
    return Recommendation(**{**base, **over})


def test_invented_sources_and_silent_gaps_are_rejected():
    _, p = _pack()
    ev = _rec(p).evidence[0].model_dump()
    for bad in ({"evidence": [{**ev, "source": "twitter"}]}, {"evidence": [{**ev, "timestamp": 123}]}, {"evidence": [], "stance": "consider_long"}, {"missing_data": []}, {"symbol": "ETH/USDT"}, {"horizon_candles": 0}):
        with pytest.raises(InvalidRecommendation):
            check_against_pack(_rec(p, **bad), p)


def test_ai_package_cannot_reach_trading_modules():
    root = Path(__file__).parents[1] / "quantlab" / "ai_analysis"
    forbidden = ("quantlab.live", "quantlab.paper", "quantlab.risk", "quantlab.backtest", "quantlab.services")
    for f in root.glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not [n for n in names if n.startswith(forbidden)], f


def test_trading_modules_do_not_read_ai_or_experiments():
    root = Path(__file__).parents[1] / "quantlab"
    for sub in ("live", "paper", "risk"):
        for f in (root / sub).glob("*.py"):
            text = f.read_text()
            for word in ("ai_analysis", "AiReport", "Experiment", "vectorbt", "research"):
                assert word not in text, (f, word)


class FakeClaude:
    def __init__(self, parsed=None, stop_reason="end_turn"):
        self.calls = []
        fake = self

        class Messages:
            def parse(self, **kw):
                fake.calls.append(kw)
                return SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason, stop_details=SimpleNamespace(category="cyber"), usage=SimpleNamespace(input_tokens=1000, output_tokens=500))

        self.beta = SimpleNamespace(messages=Messages())


def _settings(tmp_path, **kw):
    return Settings(secret_key="k" * 40, owner_password=PW, data_dir=tmp_path, watchlist=("BTC/USDT", "ETH/USDT"), secure_cookies=False, live_enabled=False, **kw)


@pytest.fixture
def world(db, tmp_path):
    st = _settings(tmp_path, ai_api_key="x", ai_daily_calls=2, ai_daily_usd=0.05)
    store = CandleStore(tmp_path)
    df = synthetic(900, step=14400, start=int(time.time()) - 900 * 14400)
    store.save("BTC/USDT", "4h", df)
    return db, store, st, df


def test_claude_call_has_limits_and_cost_is_recorded(world):
    db, store, st, df = world
    p = build_pack(df, "BTC/USDT", "4h")
    fake = FakeClaude(backends.RuleBaseline().analyze(p).recommendation)
    rid = service.run_report(db, store, st, "BTC/USDT", "4h", "claude", client=fake)
    kw = fake.calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["max_tokens"] == st.ai_max_tokens and kw["output_format"] is Recommendation
    assert "fallbacks" in kw and "temperature" not in kw and "thinking" not in kw
    assert "places no orders" in kw["system"]
    with db.session() as s:
        r = s.get(AiReport, rid)
        assert r.status == "ok" and r.usage["usd"] == pytest.approx((1000 * 4 + 500 * 20) / 1e6)


def test_real_sdk_builds_a_valid_request_and_parses_the_reply(world):
    """Real SDK against a mock transport: no network, no spend. Not proof the live API accepts it."""
    anthropic = pytest.importorskip("anthropic")
    httpx2 = pytest.importorskip("httpx2")
    db, store, st, df = world
    p = build_pack(df, "BTC/USDT", "4h")
    answer = backends.RuleBaseline().analyze(p).recommendation.model_dump_json()
    seen = {}

    def handler(req):
        seen["body"], seen["headers"] = json.loads(req.content), req.headers
        return httpx2.Response(200, json={"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "stop_reason": "end_turn", "stop_sequence": None, "content": [{"type": "text", "text": answer}], "usage": {"input_tokens": 10, "output_tokens": 20}})

    client = anthropic.Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    rid = service.run_report(db, store, st, "BTC/USDT", "4h", "claude", client=client)
    with db.session() as s:
        r = s.get(AiReport, rid)
        assert r.status == "ok", r.error
        assert r.recommendation["symbol"] == "BTC/USDT" and r.usage["input_tokens"] == 10
    b = seen["body"]
    assert b["model"] == "claude-opus-5-5" and b["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in seen["headers"]["anthropic-beta"]
    assert b["output_config"]["effort"] == "medium" and b["output_config"]["format"]["type"] == "json_schema"
    assert json.loads(b["messages"][0]["content"])["symbol"] == "BTC/USDT"


@pytest.mark.parametrize("parsed,stop,text", [(None, "refusal", "rad etdi"), (None, "max_tokens", "kesildi"), (None, "end_turn", "tuzilgan javob")])
def test_bad_llm_answers_are_stored_as_errors(world, parsed, stop, text):
    db, store, st, _ = world
    rid = service.run_report(db, store, st, "BTC/USDT", "4h", "claude", client=FakeClaude(parsed, stop))
    with db.session() as s:
        r = s.get(AiReport, rid)
        assert r.status == "error" and text in r.error and r.recommendation == {}


def test_daily_limits_stop_paid_calls_but_not_the_baseline(world):
    db, store, st, df = world
    fake = FakeClaude(backends.RuleBaseline().analyze(build_pack(df, "BTC/USDT", "4h")).recommendation)
    service.run_report(db, store, st, "BTC/USDT", "4h", "claude", client=fake)
    service.run_report(db, store, st, "BTC/USDT", "4h", "claude", client=fake)
    with pytest.raises(service.LimitExceeded):
        service.run_report(db, store, st, "BTC/USDT", "4h", "claude", client=fake)
    assert len(fake.calls) == 2
    assert service.run_report(db, store, st, "BTC/USDT", "4h", "rule_baseline")


def test_outcomes_wait_for_the_horizon_then_score(world):
    db, store, st, df = world
    rid = service.run_report(db, store, st, "BTC/USDT", "4h", "rule_baseline")
    assert service.evaluate_outcomes(db, store) == 0  # the future has not happened yet
    with db.session() as s:
        r = s.get(AiReport, rid)
        r.last_candle_ts = int(df["ts"].iloc[-60])
        r.reference_price = float(df["close"].iloc[-60])
        r.recommendation = {**r.recommendation, "stance": "consider_long", "horizon_candles": 20}
    assert service.evaluate_outcomes(db, store) == 1
    with db.session() as s:
        o = s.get(AiReport, rid).outcome
        ret = (float(df["close"].iloc[-40]) / float(df["close"].iloc[-60]) - 1) * 100
        assert o["forward_return_pct"] == pytest.approx(ret, abs=1e-3) and o["hit"] == (ret > 0)
        board = service.scoreboard(s)
        assert board[0]["engine"] == "rule_baseline" and board[0]["enough_samples"] is False


def test_tradingagents_maps_to_schema_and_declares_its_data_gap(tmp_path):
    _, p = _pack()
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({"signal": "Overweight", "model": "m", "state": {"investment_plan": "plan", "trader_investment_plan": "buy", "final_trade_decision": "ok"}}))

    a = backends.TradingAgentsAnalyst(_settings(tmp_path, tradingagents_python="/venv/bin/python"), run=run).analyze(p)
    check_against_pack(a.recommendation, p)
    assert calls[0][0][0] == "/venv/bin/python" and calls[0][0][1] == "-I" and "BTC-USD" in calls[0][0]
    assert a.recommendation.stance == "consider_long" and a.recommendation.confidence.level == "low"
    assert any("Yahoo" in m for m in a.recommendation.missing_data)
    with pytest.raises(backends.AnalystError):
        backends.TradingAgentsAnalyst(_settings(tmp_path)).analyze(p)


# ---- API ----
@pytest.fixture
def api(db, tmp_path):
    st = _settings(tmp_path)

    def handler(req):
        if req.url.path.endswith("/depth"):
            return httpx.Response(200, json=BOOK)
        return httpx.Response(503)

    client = BinancePublic("http://nowhere.invalid", client=httpx.Client(transport=httpx.MockTransport(handler)), retries=1, sleep=lambda _: None)
    app = create_app(st, db, client)
    c = TestClient(app, headers={"x-ql": "1"})
    assert c.post("/auth/login", json={"username": "owner", "password": PW}).status_code == 200
    store = CandleStore(tmp_path)
    for pair, seed in (("BTC/USDT", 1), ("ETH/USDT", 2)):
        store.save(pair, "4h", synthetic(2400, seed=seed, step=14400, start=int(time.time()) - 2400 * 14400))
    return c, db, st, store


def test_new_routes_need_login(db, tmp_path):
    c = TestClient(create_app(_settings(tmp_path), db, BinancePublic("http://x.invalid", retries=1, sleep=lambda _: None)), headers={"x-ql": "1"})
    for path in ("/integrations", "/experiments", "/experiments/presets", "/strategy-evaluation", "/ai/reports", "/ai/status", "/jesse/compatibility", "/market/microstructure?pair=BTC/USDT"):
        assert c.get(path).status_code == 401, path


def test_integrations_report_real_state_and_switches_gate_features(api):
    c, *_ = api
    rows = {r["key"]: r for r in c.get("/integrations").json()}
    assert set(rows) == {"vectorbt", "jesse", "hummingbot", "tradingagents"}
    assert rows["vectorbt"]["license"] == "Apache-2.0 + Commons Clause" and rows["tradingagents"]["enabled"] is False
    assert rows["tradingagents"]["health"]["state"] == "degraded"
    assert c.get("/market/microstructure?pair=BTC/USDT").json()["metrics"]["best_bid"] == 100
    assert c.post("/integrations/hummingbot", json={"enabled": False}).status_code == 200
    assert c.get("/market/microstructure?pair=BTC/USDT").status_code == 409
    assert c.post("/integrations/nope", json={"enabled": True}).status_code == 404
    assert c.post("/ai/reports", json={"pair": "BTC/USDT"}).status_code == 409  # AI is off by default
    assert c.get("/jesse/compatibility").json()["jesse_version"] == "3.6.0"


def test_ai_engine_without_key_is_refused(api):
    c, *_ = api
    c.post("/integrations/tradingagents", json={"enabled": True})
    assert c.post("/ai/reports", json={"pair": "BTC/USDT", "engine": "claude"}).status_code == 409
    assert c.post("/ai/reports", json={"pair": "BTC/USDT", "engine": "rule_baseline"}).status_code == 200


def test_experiment_flow_through_job_runner_to_export(api):
    c, db, st, store = api
    now = int(time.time())
    body = {"strategy": "rsi_ema_trend", "pairs": ["BTC/USDT", "ETH/USDT"], "timeframe": "4h", "start_ts": now - 2100 * 14400, "end_ts": now, "backend": "native",
            "grid": {"rsi_period": [7, 14], "rsi_entry": [30, 35], "ema_fast": [5], "ema_slow": [30]}}
    assert c.post("/experiments", json={**body, "backend": "bogus"}).status_code == 400
    assert c.post("/experiments", json={**body, "grid": {"rsi_period": [999]}}).status_code == 400
    assert c.post("/experiments", json={**body, "strategy": "nope"}).status_code == 404
    r = c.post("/experiments", json=body).json()
    assert r["n_combos"] == 4
    runner = JobRunner(db, st, store)
    assert runner.run_one()
    d = c.get(f"/experiments/{r['id']}").json()
    assert d["status"] == "done", d["error"]
    assert d["repro"]["backend"] == "native" and d["repro"]["data_hash"]["BTC/USDT"] and d["runtime_s"] >= 0
    assert d["summary"]["eligibility"]["status"] in ("rejected", "paper_candidate")
    rows = c.get(f"/experiments/{r['id']}/results").json()
    assert rows["total"] == 4 and rows["rows"][0]["rank"] == 1
    csv = c.get(f"/experiments/{r['id']}/export.csv")
    assert csv.status_code == 200 and "validation_total_return" in csv.text and len(csv.text.strip().splitlines()) == 5
    ev = c.get("/strategy-evaluation").json()
    assert ev["experiments"][0]["id"] == r["id"] and "qulflangan" in ev["live"] and ev["counts"]["done"] == 1


def test_failed_experiment_is_kept_with_its_error(api):
    c, db, st, store = api
    now = int(time.time())
    r = c.post("/experiments", json={"strategy": "rsi_ema_trend", "pairs": ["DOGE/USDT"], "timeframe": "4h", "start_ts": now - 86400 * 400, "end_ts": now, "backend": "native"}).json()
    JobRunner(db, st, store).run_one()
    d = c.get(f"/experiments/{r['id']}").json()
    assert d["status"] == "error" and d["error"]
    with db.session() as s:
        assert s.get(Job, d["job_id"]).status == "error"
        assert s.query(Experiment).count() == 1 and s.query(ExperimentResult).count() == 0
