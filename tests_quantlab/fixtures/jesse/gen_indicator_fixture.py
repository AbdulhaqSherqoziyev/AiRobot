"""Regenerates jesse_indicators.json from Jesse's own indicator code (run in the Jesse venv with -I)."""
import json
import sys
from pathlib import Path

import numpy as np
import jesse.indicators as ta

here = Path(sys.argv[1])
d = json.loads((here / "jesse_results.json").read_text())
rows = d["hourly_candles"]
# Jesse column order: timestamp, open, close, high, low, volume.
c = np.array([[r[0] * 1000, r[1], r[4], r[2], r[3], r[5]] for r in rows], dtype=float)
out = {
    "rsi14": ta.rsi(c, 14, sequential=True), "ema20": ta.ema(c, 20, sequential=True), "sma20": ta.sma(c, 20, sequential=True),
    "atr14": ta.atr(c, 14, sequential=True), "adx14": ta.adx(c, 14, sequential=True),
    "macd": ta.macd(c, 12, 26, 9, sequential=True).macd, "macd_signal": ta.macd(c, 12, 26, 9, sequential=True).signal,
    "bb_upper": ta.bollinger_bands(c, 20, 2, sequential=True).upperband, "bb_lower": ta.bollinger_bands(c, 20, 2, sequential=True).lowerband,
}
(here / "jesse_indicators.json").write_text(json.dumps({k: [None if np.isnan(x) else round(float(x), 8) for x in v] for k, v in out.items()}))
print({k: float(v[-1]) for k, v in out.items()})
