# Phase 8 — Baseline strategy (simple rule-based, long-only spot)

Status: done
Started: 2026-07-26   Finished: 2026-07-26

> Re-scoped from the roadmap's FreqAI strategy to a simple rule-based strategy per
> owner decision (ADR-0006). Stage C (FreqAI) deferred.

## Goal
A transparent, conservative, long-only spot strategy to serve as the first
live-path candidate, validated by backtest and lookahead-bias analysis.

## Reason
Constitution: capital preservation, fewer/safer trades. Owner chose a simple
rule-based approach for the first live pilot (ADR-0006).

## Compliance / safety
Long only (`can_short=False`), no leverage. Platform guards (spot-only, screening,
order gate, loss limits, circuit breaker) apply independently of the strategy.

## Design
`user_data/strategies/IslamicSpotStrategy.py` (resolver-loaded, no core edits):
- Timeframe 1h (less noise, deliberate trades).
- Regime: EMA50 > EMA200 and close > EMA50.
- Entry: RSI crossing up through 50 (momentum turn, not chasing), RSI < 70,
  ADX > 20 (trend strength), volume > 20-period average.
- Exit: conservative `minimal_roi` (5%→0.5% over time), hard stoploss −5%,
  trailing stop (2% once +3% offset reached), and a trend-break / overbought exit
  signal.
- Named constants (no magic numbers); startup_candle_count 250.

## Files affected
- new: `user_data/strategies/IslamicSpotStrategy.py`
- new: `tests/strategy/test_islamic_spot_strategy.py`
- edited: `.gitignore` (track the strategy file)

## Validation — DONE
- Loads via `StrategyResolver`; 2 smoke tests (long-only, indicators + 0/1 signals).
- **Backtest** (Binance spot, 4 pairs, 1h, ~6 months to 2026-07-25): 61 trades,
  final 992.83 / 1000 = **−0.72%** while **market fell −40.81%** — strong capital
  preservation in a bear regime, but **not profitable**. Profit factor 0.65,
  max consecutive losses 9 (our ConsecutiveLossGuard would trip at 4).
- **Lookahead-analysis: no bias detected** (0 biased entry/exit signals, 0 biased
  indicators) — backtest is trustworthy.

## Honest assessment / risk
The strategy preserves capital but does not yet show positive expectancy. The test
window was heavily bearish; trend-following should fare better in uptrends, but this
is unproven. **Not ready for live on profitability grounds** — needs multi-regime
backtesting and tuning first. It is, however, a safe, bias-free, mechanically-correct
baseline that exercises the whole platform end-to-end.

## Testing — DONE
2 strategy tests; backtest + lookahead run clean. Full regression pending commit.

## Documentation — DONE
ADR-0006; ROADMAP (Stage C deferred, this phase added); this record.

## Outcome
Delivered a validated (bias-free) conservative baseline strategy. Next before live:
multi-regime backtests + parameter review (hyperopt optional), then the security
pass (Phase 11) and deployment. AI advisor (Stage C) is a later increment.
