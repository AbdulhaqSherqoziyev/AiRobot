"""Performance metrics. Same functions for backtests, paper sessions and live."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np


def _safe(x: float) -> float | None:
    return None if x is None or math.isnan(x) or math.isinf(x) else round(float(x), 6)


def max_streak(values: list[bool]) -> int:
    best = cur = 0
    for v in values:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def compute(equity: list[tuple[int, float]], trades: list[dict], initial: float, bar_seconds: int) -> dict:
    """`trades` are closed round trips with pnl, pnl_pct, fees, entry_ts, exit_ts."""
    eq = np.array([e for _, e in equity], dtype=float) if equity else np.array([initial], dtype=float)
    final = float(eq[-1])
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    peak = np.maximum.accumulate(eq)
    dd = (eq / peak - 1) * 100
    rets = np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([])
    per_year = 365 * 86400 / bar_seconds
    sharpe = sortino = None
    if len(rets) > 1 and rets.std() > 0:
        sharpe = rets.mean() / rets.std() * math.sqrt(per_year)
        downside = rets[rets < 0]
        if len(downside) > 1 and downside.std() > 0:
            sortino = rets.mean() / downside.std() * math.sqrt(per_year)
    holds = [t["exit_ts"] - t["entry_ts"] for t in trades if t.get("exit_ts")]
    total_span = (equity[-1][0] - equity[0][0]) if len(equity) > 1 else 0
    return {
        "initial_balance": round(initial, 4),
        "final_balance": round(final, 4),
        "net_profit": round(final - initial, 4),
        "total_return": _safe((final / initial - 1) * 100) if initial else None,
        "win_rate": _safe(len(wins) / len(trades) * 100) if trades else None,
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        # Null, not infinity, when nothing lost: too few trades to claim a ratio.
        "profit_factor": _safe(gross_win / gross_loss) if gross_loss > 0 else None,
        "max_drawdown": _safe(float(dd.min())),
        "sharpe": _safe(sharpe) if sharpe is not None else None,
        "sortino": _safe(sortino) if sortino is not None else None,
        "avg_trade_return": _safe(float(np.mean([t["pnl_pct"] for t in trades]))) if trades else None,
        "avg_holding_seconds": _safe(float(np.mean(holds))) if holds else None,
        "fees_paid": round(sum(t.get("fees", 0.0) for t in trades), 6),
        "exposure": _safe(sum(holds) / total_span * 100) if total_span and holds else 0.0,
        "consecutive_wins": max_streak([t["pnl"] > 0 for t in trades]),
        "consecutive_losses": max_streak([t["pnl"] <= 0 for t in trades]),
    }


def monthly_returns(equity: list[tuple[int, float]]) -> list[dict]:
    out: list[dict] = []
    if not equity:
        return out
    prev = equity[0][1]
    key = None
    last = prev
    for ts, e in equity:
        d = datetime.fromtimestamp(ts, timezone.utc)
        k = (d.year, d.month)
        if key is not None and k != key:
            out.append({"y": key[0], "m": key[1] - 1, "ret": round((last / prev - 1) * 100, 4)})
            prev = last
        key, last = k, e
    out.append({"y": key[0], "m": key[1] - 1, "ret": round((last / prev - 1) * 100, 4)})
    return out
