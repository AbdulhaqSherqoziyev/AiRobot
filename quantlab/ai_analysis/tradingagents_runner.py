"""Runs in the separate TradingAgents venv, never in the application: <venv>/bin/python -I this.py BTC-USD <unix-ts>
Prints one JSON line. Uses the market analyst only, since each extra analyst adds LLM calls and data vendors."""

import json
import sys
from datetime import datetime, timezone

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

KEYS = ("market_report", "investment_plan", "trader_investment_plan", "final_trade_decision")


def main() -> None:
    ticker, ts = sys.argv[1], int(sys.argv[2])
    cfg = {**DEFAULT_CONFIG, "max_debate_rounds": 1, "max_risk_discuss_rounds": 1, "checkpoint_enabled": False}
    graph = TradingAgentsGraph(selected_analysts=("market",), config=cfg)
    day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
    state, signal = graph.propagate(ticker, day, asset_type="crypto")
    print(json.dumps({"signal": signal, "model": cfg.get("deep_think_llm"), "state": {k: state.get(k, "") for k in KEYS}}))


if __name__ == "__main__":
    main()
