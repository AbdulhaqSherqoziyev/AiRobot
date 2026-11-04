"""Parquet OHLCV store: incremental sync, duplicate removal, gap and sanity checks."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quantlab.config import TIMEFRAMES
from quantlab.market.binance import KLINES_MAX, BinancePublic

log = logging.getLogger(__name__)
COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


def klines_to_frame(rows: list[list]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=COLUMNS).astype({"ts": "int64"})
    df = pd.DataFrame([r[:6] for r in rows], columns=COLUMNS)
    df["ts"] = (df["ts"].astype("int64") // 1000).astype("int64")
    for c in COLUMNS[1:]:
        df[c] = df[c].astype("float64")
    return df


@dataclass
class ValidationReport:
    rows: int
    duplicates: int
    gaps: list[tuple[int, int]]
    invalid: int


def clean(df: pd.DataFrame, timeframe: str) -> tuple[pd.DataFrame, ValidationReport]:
    """Sort, drop duplicate timestamps and impossible candles, then report the gaps."""
    step = TIMEFRAMES[timeframe]
    n = len(df)
    df = df.sort_values("ts").drop_duplicates("ts", keep="last")
    dups = n - len(df)
    bad = (df["high"] < df[["open", "close", "low"]].max(axis=1)) | (df["low"] > df[["open", "close"]].min(axis=1)) | (df["low"] <= 0) | (df["volume"] < 0) | (df["ts"] % step != 0)
    invalid = int(bad.sum())
    df = df[~bad].reset_index(drop=True)
    gaps = []
    if len(df) > 1:
        ts = df["ts"].to_numpy()
        for i in (ts[1:] - ts[:-1] != step).nonzero()[0]:
            gaps.append((int(ts[i]) + step, int(ts[i + 1]) - step))
    return df, ValidationReport(len(df), dups, gaps, invalid)


class CandleStore:
    def __init__(self, data_dir: Path, client: BinancePublic | None = None, source: str = "binance-spot-public"):
        self.root = Path(data_dir) / "ohlcv"
        self.client = client
        self.source = source

    def path(self, pair: str, timeframe: str) -> Path:
        return self.root / timeframe / f"{pair.replace('/', '_')}.parquet"

    def load(self, pair: str, timeframe: str, start_ts: int | None = None, end_ts: int | None = None) -> pd.DataFrame:
        p = self.path(pair, timeframe)
        if not p.exists():
            return pd.DataFrame(columns=COLUMNS).astype({"ts": "int64"})
        df = pd.read_parquet(p)
        if start_ts is not None:
            df = df[df["ts"] >= start_ts]
        if end_ts is not None:
            df = df[df["ts"] <= end_ts]
        return df.reset_index(drop=True)

    def save(self, pair: str, timeframe: str, df: pd.DataFrame) -> None:
        p = self.path(pair, timeframe)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(p)  # atomic, so a crash never leaves a half-written dataset

    def sync(self, pair: str, timeframe: str, since_ts: int | None = None, now: int | None = None) -> ValidationReport:
        """Download everything after the last stored candle. Only closed candles are stored:
        keeping a forming candle would leak its final values into earlier decisions."""
        assert self.client is not None
        step = TIMEFRAMES[timeframe]
        now = int(time.time()) if now is None else now
        last_closed_open = (now // step) * step - step
        existing = self.load(pair, timeframe)
        cursor = int(existing["ts"].iloc[-1]) + step if len(existing) else (since_ts or last_closed_open - step * KLINES_MAX)
        frames = [existing] if len(existing) else []
        while cursor <= last_closed_open:
            rows = self.client.klines(pair, timeframe, start_ms=cursor * 1000, end_ms=last_closed_open * 1000 + 999)
            if not rows:
                break
            batch = klines_to_frame(rows)
            frames.append(batch)
            next_cursor = int(batch["ts"].iloc[-1]) + step
            if next_cursor <= cursor:
                break
            cursor = next_cursor
        if not frames:
            return ValidationReport(0, 0, [], 0)
        df, report = clean(pd.concat(frames, ignore_index=True), timeframe)
        df = df[df["ts"] <= last_closed_open].reset_index(drop=True)
        self.save(pair, timeframe, df)
        return report

    @staticmethod
    def data_hash(df: pd.DataFrame) -> str:
        return hashlib.sha256(pd.util.hash_pandas_object(df[COLUMNS], index=False).values.tobytes()).hexdigest()[:32]
