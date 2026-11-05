"""Interchangeable analysts. None of them can reach the risk, paper or live modules; a test
checks the imports. An LLM call happens only when the owner presses a button, never per candle."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantlab.ai_analysis.schema import Confidence, Evidence, Recommendation
from quantlab.config import Settings

# USD per million tokens for the default model; anything else is reported as unknown cost.
PRICES = {"claude-opus-5-5": (4.0, 20.0)}
SYSTEM_PROMPT = """You are a research analyst for a personal Binance Spot research system. Your output is stored and later scored against what the market did. It places no orders and changes no settings.

Use only the JSON data pack in the user message. Copy each evidence item's name, value, timestamp and source from the pack. Anything listed under "unavailable" is not available to you: name it in missing_data and draw no conclusions about it. Do not bring in remembered prices, news or events.

The market is spot only, so the choices are consider_long, stay_flat or no_view. There is no short side. Pick no_view when the evidence does not support a view, and keep confidence low unless several independent indicators agree. Write in Uzbek, keeping indicator names as they are."""


@dataclass
class Analysis:
    recommendation: Recommendation
    engine: str
    model: str | None = None
    usage: dict | None = None
    latency_s: float | None = None
    raw: str = ""


class AnalystError(RuntimeError):
    pass


class RuleBaseline:
    """No LLM. A fixed reading of the indicators, stored the same way, so anything smarter has a
    baseline to beat on the outcomes page."""

    name = "rule_baseline"

    def analyze(self, pack: dict) -> Analysis:
        i = {k: v["value"] for k, v in pack["indicators"].items()}
        ts, src = pack["last_closed_candle_ts"], pack["indicators"]["close"]["source"]
        ev = lambda k: Evidence(name=k, value=str(i[k]), timestamp=ts, source=src)  # noqa: E731
        up = i["close"] > i["ema_200"] and i["ema_20"] > i["ema_50"]
        down = i["close"] < i["ema_200"] and i["ema_20"] < i["ema_50"]
        trending = (i["adx_14"] or 0) >= 20
        regime = ("o'suvchi" if up else "pasayuvchi" if down else "aralash") + (" trend" if trending else ", trend kuchsiz")
        stance = "consider_long" if up and trending else "stay_flat" if down else "no_view"
        rec = Recommendation(
            symbol=pack["symbol"], timeframe=pack["timeframe"], stance=stance, horizon_candles=20, market_regime_hypothesis=regime,
            evidence=[ev(k) for k in ("close", "ema_20", "ema_50", "ema_200", "adx_14", "rsi_14")],
            entry_conditions=["EMA20 > EMA50, narx EMA200 ustida, ADX >= 20"] if stance == "consider_long" else [],
            exit_conditions=["EMA20 EMA50 ostiga tushsa"] if stance == "consider_long" else [],
            invalidation_conditions=["Narx EMA200 ostida yopilsa"] if up else ["Narx EMA200 ustida yopilsa va EMA20 > EMA50 bo'lsa"],
            confidence=Confidence(level="low", explanation="Qat'iy qoida, LLM emas. Bu faqat taqqoslash uchun bazaviy chiziq."),
            risks=[f"ATR {i['atr_14_pct']}%: to'satdan harakat stopni o'tkazib yuborishi mumkin", "Qoida bozor rejimi almashishini kech sezadi"],
            missing_data=[k for k, v in pack["unavailable"].items() if v],
        )
        return Analysis(rec, self.name)


class ClaudeAnalyst:
    """One structured-output call with hard token, time and retry limits."""

    name = "claude"

    def __init__(self, settings: Settings, client: Any = None):
        self.settings = settings
        self.client = client

    def _client(self):
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic(api_key=self.settings.ai_api_key or None, timeout=self.settings.ai_timeout_s, max_retries=1)
        return self.client

    def analyze(self, pack: dict) -> Analysis:
        m = self.settings.ai_model
        r = self._client().beta.messages.parse(
            model=m, max_tokens=self.settings.ai_max_tokens, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            output_config={"effort": "medium"}, system=SYSTEM_PROMPT, output_format=Recommendation,
            messages=[{"role": "user", "content": json.dumps(pack, ensure_ascii=False, sort_keys=True)}],
        )
        usage = {"input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens, "request_id": getattr(r, "_request_id", None)}
        price = PRICES.get(m)
        usage["usd"] = round((usage["input_tokens"] * price[0] + usage["output_tokens"] * price[1]) / 1e6, 5) if price else None
        if r.stop_reason == "refusal":
            raise AnalystError(f"model rad etdi: {getattr(r.stop_details, 'category', None)}")
        if r.stop_reason == "max_tokens":
            raise AnalystError(f"javob {self.settings.ai_max_tokens} token chegarasida kesildi")
        if r.parsed_output is None:
            raise AnalystError(f"tuzilgan javob yo'q (stop_reason={r.stop_reason})")
        return Analysis(r.parsed_output, self.name, m, usage)


def map_tradingagents(state: dict, signal: str, pack: dict) -> Recommendation:
    """Maps TradingAgents' free-text result to the schema. Its data comes from Yahoo `BTC-USD`, not
    from Binance Spot and not from the pack, so its prose cannot be tied to pack timestamps. It is
    stored at low confidence with that gap stated."""
    stance = {"Buy": "consider_long", "Overweight": "consider_long", "Hold": "no_view", "Underweight": "stay_flat", "Sell": "stay_flat"}.get(signal, "no_view")
    close = pack["indicators"]["close"]
    return Recommendation(
        symbol=pack["symbol"], timeframe=pack["timeframe"], stance=stance, horizon_candles=20,
        market_regime_hypothesis=(state.get("investment_plan") or "")[:800] or "TradingAgents rejim bermadi",
        evidence=[Evidence(name="close", value=str(close["value"]), timestamp=close["timestamp"], source=close["source"])],
        entry_conditions=[(state.get("trader_investment_plan") or "")[:800]] if state.get("trader_investment_plan") else [],
        exit_conditions=[], invalidation_conditions=[],
        confidence=Confidence(level="low", explanation=f"TradingAgents reytingi: {signal}. Matnli xulosa; dalillari tekshirilmagan."),
        risks=[(state.get("final_trade_decision") or "")[:800]] if state.get("final_trade_decision") else [],
        missing_data=["TradingAgents Yahoo Finance BTC-USD ishlatadi, Binance Spot narxi emas", "Agent matnidagi dalillar vaqt belgisi bilan tekshirilmagan"],
    )


class TradingAgentsAnalyst:
    """Runs upstream in its own interpreter (QL_TRADINGAGENTS_PYTHON): its dependencies stay out of
    this process, and it holds its own LLM keys and data vendors."""

    name = "tradingagents"
    RUNNER = Path(__file__).with_name("tradingagents_runner.py")

    def __init__(self, settings: Settings, run=subprocess.run):
        self.settings, self.run = settings, run

    def analyze(self, pack: dict) -> Analysis:
        if not self.settings.tradingagents_python:
            raise AnalystError("QL_TRADINGAGENTS_PYTHON sozlanmagan")
        base = pack["symbol"].split("/")[0]
        p = self.run([self.settings.tradingagents_python, "-I", str(self.RUNNER), f"{base}-USD", str(pack["built_at"])], capture_output=True, text=True, timeout=self.settings.tradingagents_timeout_s)
        if p.returncode != 0:
            raise AnalystError(f"TradingAgents xatosi: {p.stderr[-500:]}")
        out = json.loads(p.stdout.strip().splitlines()[-1])
        return Analysis(map_tradingagents(out["state"], out["signal"], pack), self.name, out.get("model"), None, raw=json.dumps(out["state"], ensure_ascii=False)[:20000])


def make(name: str, settings: Settings, client: Any = None):
    if name == RuleBaseline.name:
        return RuleBaseline()
    if name == ClaudeAnalyst.name:
        return ClaudeAnalyst(settings, client)
    if name == TradingAgentsAnalyst.name:
        return TradingAgentsAnalyst(settings)
    raise ValueError(f"noma'lum tahlilchi: {name}")
