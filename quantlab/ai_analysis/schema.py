"""Structured research output. A recommendation is a stored opinion: nothing reads it to trade."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="Indicator or fact, exactly as named in the data pack")
    value: str
    timestamp: int = Field(description="Unix seconds of the data point, copied from the data pack")
    source: str = Field(description="Source id, copied from the data pack")


class Confidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal["low", "medium", "high"]
    explanation: str


class Recommendation(BaseModel):
    """The spec's required fields. `stance` has no short side: Binance Spot, long or flat."""

    model_config = ConfigDict(extra="forbid")
    symbol: str
    timeframe: str
    stance: Literal["consider_long", "stay_flat", "no_view"]
    horizon_candles: int = Field(description="Candles after which this view should be judged, between 1 and 200")
    market_regime_hypothesis: str
    evidence: list[Evidence]
    entry_conditions: list[str]
    exit_conditions: list[str]
    invalidation_conditions: list[str]
    confidence: Confidence
    risks: list[str]
    missing_data: list[str]


class InvalidRecommendation(ValueError):
    pass


def check_against_pack(rec: Recommendation, pack: dict) -> None:
    """Refuses output that names data the pack did not contain."""
    if rec.symbol != pack["symbol"] or rec.timeframe != pack["timeframe"]:
        raise InvalidRecommendation(f"boshqa aktiv haqida: {rec.symbol} {rec.timeframe}")
    if not 1 <= rec.horizon_candles <= 200:
        raise InvalidRecommendation(f"horizon_candles chegaradan tashqari: {rec.horizon_candles}")
    if rec.stance != "no_view" and not rec.evidence:
        raise InvalidRecommendation("dalilsiz tavsiya")
    for e in rec.evidence:
        if e.source not in pack["sources"]:
            raise InvalidRecommendation(f"to'plamda yo'q manba: {e.source}")
        if e.timestamp not in pack["timestamps"]:
            raise InvalidRecommendation(f"to'plamda yo'q vaqt belgisi: {e.timestamp}")
    needed = [k for k, v in pack["unavailable"].items() if v]
    if needed and not rec.missing_data:
        raise InvalidRecommendation(f"yo'q ma'lumot aytilmagan: {needed}")
