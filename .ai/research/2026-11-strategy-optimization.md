# Strategy optimization study, November 2026

## Pre-registration (written before the holdout was run)

Holdout: 2025-11-04 to 2026-11-03, 9 watchlist pairs, 4h candles, fee 0.1%, slippage 0.05%.
It is run once, and nothing is changed or re-selected afterwards.

Candidates, chosen on the development period only (2021-06-15 to 2025-11-04), all with default
parameters, 3% stop and volatility-target sizing (1.5% daily, 30-day lookback):

1. `atr_breakout` 4h
2. `ema_crossover` 4h
3. `multi_indicator` 4h

Baselines: buy and hold; `TREND_HOLD` 4h with trend+vol (no indicator strategy).

A candidate counts as confirmed only if, on the holdout, all of these hold:

- median return across pairs is positive
- median Sharpe beats both baselines
- at least 6 of 9 pairs are positive

Also reported, not part of the rule: results at double costs, an equal-weight portfolio, and
the platform's live screening criteria (profit factor above 1.3, drawdown under 5%).

## Result: no candidate confirmed

The holdout was a falling market: buy and hold had a median of -44% across the pairs.

| Holdout, median across 9 pairs | Return | Max drawdown | Sharpe | Profit factor | Positive pairs |
| --- | --- | --- | --- | --- | --- |
| Buy and hold | -44.22% | -61.06% | -0.59 | n/a | 0 |
| TREND_HOLD (baseline) | -3.92% | -9.25% | -0.35 | 0.00 | 3 |
| `atr_breakout` | -2.49% | -18.47% | -0.07 | 0.90 | 3 |
| `ema_crossover` | -12.45% | -22.51% | -0.46 | 0.68 | 1 |
| `multi_indicator` | -18.09% | -23.53% | -0.91 | 0.53 | 0 |

`atr_breakout` was closest: it beat both baselines on Sharpe but failed on return and on positive
pairs. At double costs its median return was -5.64%. As an equal-weight portfolio: -3.18%,
drawdown -16.32%, profit factor 0.89. All candidates fail the live screen (profit factor 1.3,
drawdown 5%).

## What the development period showed (2021-06 to 2025-11)

Median of all 10 strategies across 9 pairs:

| Timeframe | Base return | Base drawdown | Vol-sized return | Vol-sized drawdown |
| --- | --- | --- | --- | --- |
| 1h | -80.85% | -87.50% | -39.44% | -53.62% |
| 4h | -5.76% | -57.51% | +14.66% | -28.78% |
| 1d | -12.97% | -35.91% | +0.94% | -21.56% |

- 1h is not viable at these costs: none of its 40 strategy configurations beat buy and hold's
  median Sharpe (0.57), though a few had a positive median return.
- Volatility sizing helped on all timeframes.
- The 200-day trend filter cut drawdown but also return and usually Sharpe, against expectation.
- Walk-forward tuning (25 trials, 4 test windows) did not reliably beat defaults, and chosen
  parameters changed sharply between windows. Do not adopt tuned parameters from this optimizer.

## Conclusions

1. No strategy here has shown an edge that survives an unseen period.
2. Volatility sizing and 4h or slower candles reduce damage. In the falling holdout year they limited
   losses far below buy and hold. That is risk reduction, not evidence of profit.
3. The holdout is now used. Anything derived from looking at it needs fresh data to be tested on.

## Limits

- One holdout year, in one market regime. It says little about rising markets.
- Survivorship bias: the 9 pairs are today's large coins, which flatters earlier years.
- 120 configurations were compared on the development period, so its top results are inflated.
- Single position per pair. Stop-loss fills assume the modelled price and slippage.
- Volatility sizing has since been added to the backtest, paper and live engines. The backtest path
  reproduces the holdout figures exactly on 9 of 9 pairs (`atr_breakout`); paper and live are covered by tests.

Reproduce: `python -m quantlab.research.compare --start 1623715200 --dev-end 1762214400`, then
`run_wf` with the same flags, then `holdout --start 1762214400`. Needs `quantlab.cli download
--days 2500` for 1d, 4h and 1h first.
