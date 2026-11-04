"""Isolated real-order engine. Runs as its own process and imports nothing from the paper
engine. It is off unless every gate passes, and any doubt results in no new order:

* QL_LIVE_ENABLED, an active owner authorization, stored credentials, no persisted halt.
* Each order is written to the database before it is sent, under a deterministic client id,
  so a restart can reconcile instead of re-sending.
* An order with an unknown outcome halts the engine until it is reconciled.
"""

from __future__ import annotations

import logging
import time

from quantlab.config import TIMEFRAMES, Settings
from quantlab.evaluation.approval import active_authorization, gate_reasons
from quantlab.live.exchange import BinanceSpot, Exchange, ExchangeError, ExchangeUnknown
from quantlab.market.binance import to_symbol
from quantlab.market.store import CandleStore
from quantlab.models import EquitySnapshot, LiveAuthorization, LiveOrder, LivePortfolio, LiveTrade, RiskEvent, StrategyVersion, TradingPair, utcnow
from quantlab.notify.service import notify, syslog
from quantlab.risk.engine import RiskLimits, entry_violations, portfolio_breaches
from quantlab.risk.sizing import HISTORY_DAYS, stake_series
from quantlab.strategies.base import get_strategy

log = logging.getLogger(__name__)
WINDOW = 600


def get_portfolio(s, environment: str) -> LivePortfolio:
    pf = s.query(LivePortfolio).filter_by(environment=environment).one_or_none()
    if pf is None:
        pf = LivePortfolio(environment=environment)
        s.add(pf)
        s.flush()
    return pf


def _fill_price(res: dict) -> tuple[float, float, float]:
    """(average price, executed base qty, fee in USDT terms) from an order response."""
    qty = float(res.get("executedQty", 0))
    quote = float(res.get("cummulativeQuoteQty", 0))
    avg = quote / qty if qty else 0.0
    fee = 0.0
    fee_base = 0.0
    for f in res.get("fills", []):
        c = float(f.get("commission", 0))
        if f.get("commissionAsset") == "USDT":
            fee += c
        elif f.get("commissionAsset") == res.get("symbol", "").replace("USDT", ""):
            fee += c * avg
            fee_base += c
    return avg, qty - fee_base, fee


class LiveEngine:
    def __init__(self, db, settings: Settings, store: CandleStore, exchange: Exchange, environment: str = "live"):
        self.db, self.settings, self.store, self.ex, self.env = db, settings, store, exchange, environment

    def _halt(self, s, pf: LivePortfolio, rule: str, detail: str, tone: str = "err") -> None:
        pf.status, pf.halt_reason = "halted", f"{rule}: {detail}"
        s.add(RiskEvent(scope="live", scope_id=pf.id, rule=rule, detail=detail))
        notify(s, "live", f"REAL SAVDO TO'XTATILDI ({self.env})", detail, tone, "live")
        syslog(s, "ERROR", "live", f"{rule}: {detail}")

    def _write_order(self, pf_id: int, symbol: str, side: str, cid: str, quote: float | None, base: float | None) -> bool:
        """Write-ahead record. False if this client id exists, meaning do not send."""
        from sqlalchemy.exc import IntegrityError

        try:
            with self.db.session() as s:
                s.add(LiveOrder(portfolio_id=pf_id, client_order_id=cid, symbol=symbol, side=side, quote_qty=quote, base_qty=base, status="pending"))
            return True
        except IntegrityError:
            return False

    def _finish(self, cid: str, status: str, res: dict | None = None, error: str = "") -> None:
        with self.db.session() as s:
            o = s.query(LiveOrder).filter_by(client_order_id=cid).one()
            o.status, o.error, o.raw = status, error[:1000], res or {}
            o.exchange_order_id = str((res or {}).get("orderId", ""))

    def reconcile(self) -> int:
        """Resolve orders whose outcome is unknown, e.g. after a timeout or a crash mid-send."""
        with self.db.session() as s:
            pf = get_portfolio(s, self.env)
            todo = [(o.client_order_id, o.symbol, o.side) for o in s.query(LiveOrder).filter(LiveOrder.portfolio_id == pf.id, LiveOrder.status.in_(("pending", "unknown")))]
        n = 0
        for cid, symbol, side in todo:
            try:
                res = self.ex.query_order(symbol, cid)
            except (ExchangeUnknown, ExchangeError) as exc:
                log.warning("reconcile %s failed: %s", cid, exc)
                continue
            if res is None:
                self._finish(cid, "not_placed")
            else:
                self._finish(cid, res.get("status", "FILLED").lower(), res)
                if res.get("status") == "FILLED":
                    self._book(cid, symbol, side, res)
            n += 1
        return n

    def _book(self, cid: str, symbol: str, side: str, res: dict, reason: str = "signal", ts: int | None = None) -> None:
        ts = ts or int(time.time())
        avg, qty, fee = _fill_price({**res, "symbol": symbol})
        with self.db.session() as s:
            pf = get_portfolio(s, self.env)
            t = s.query(LiveTrade).filter(LiveTrade.portfolio_id == pf.id, LiveTrade.exit_ts.is_(None)).one_or_none()
            if side == "BUY" and t is None:
                s.add(LiveTrade(portfolio_id=pf.id, symbol=symbol, entry_ts=ts, entry_price=avg, qty=qty, entry_fee=fee))
                notify(s, "trade", f"REAL SOTIB OLISH {symbol}", f"{qty} @ {avg}", "info", "live")
            elif side == "SELL" and t is not None:
                t.exit_ts, t.exit_price, t.exit_fee, t.exit_reason = ts, avg, fee, reason
                t.pnl = t.qty * avg - t.qty * t.entry_price - t.entry_fee - fee
                notify(s, "trade", f"REAL SOTISH {symbol}", f"PnL {t.pnl:.4f} USDT ({reason})", "ok" if t.pnl >= 0 else "warn", "live")

    def _send(self, pf_id: int, symbol: str, side: str, cid: str, *, quote: float | None = None, base: float | None = None, reason: str = "signal", ts: int | None = None) -> bool:
        if not self._write_order(pf_id, symbol, side, cid, quote, base):
            return False
        try:
            res = self.ex.market_buy(symbol, quote, cid) if side == "BUY" else self.ex.market_sell(symbol, base, cid)
        except ExchangeUnknown as exc:
            self._finish(cid, "unknown", error=str(exc))
            with self.db.session() as s:
                self._halt(s, get_portfolio(s, self.env), "unknown_order_state", f"{cid}: {exc}")
            return False
        except ExchangeError as exc:
            self._finish(cid, "rejected", error=str(exc))
            with self.db.session() as s:
                self._halt(s, get_portfolio(s, self.env), "exchange_rejected", f"{cid}: {exc}")
            return False
        self._finish(cid, res.get("status", "FILLED").lower(), res)
        self._book(cid, symbol, side, res, reason, ts)
        return True

    def _balances(self) -> dict[str, float]:
        return {b["asset"]: float(b["free"]) for b in self.ex.account().get("balances", [])}

    def tick(self, now: int | None = None, last_price: float | None = None) -> str:
        """One engine cycle. Returns a short status for logs and tests."""
        now = int(time.time()) if now is None else now
        with self.db.session() as s:
            pf = get_portfolio(s, self.env)
            status = pf.status
            if status == "stopped":
                return "stopped"
            reasons = gate_reasons(s, self.settings, self.env)
            auth = active_authorization(s, self.env)
            if reasons:
                # Permission was withdrawn while running: stop opening, keep managing exits.
                if status == "running":
                    self._halt(s, pf, "gate_closed", "; ".join(reasons))
                status = "halted"
            pf_id, last_ts = pf.id, pf.last_candle_ts
        self.reconcile()
        with self.db.session() as s:
            pf = s.get(LivePortfolio, pf_id)
            if s.query(LiveOrder).filter(LiveOrder.portfolio_id == pf_id, LiveOrder.status.in_(("pending", "unknown"))).count():
                return "waiting_reconcile"
            if auth is None:
                return "no_authorization"
            auth = s.merge(auth)
            ver = s.get(StrategyVersion, auth.strategy_version_id)
            engine_key, params, tf, risk = ver.strategy.engine, ver.params(), ver.timeframe, ver.risk or {}
            pair = auth.pairs[0]
            limits = RiskLimits(max_position_usdt=auth.max_position, max_drawdown_pct=auth.max_drawdown_pct, max_daily_loss_pct=auth.daily_loss_limit / max(auth.max_capital, 1e-9) * 100, max_orders_per_hour=int((auth.stop_conditions or {}).get("max_orders_per_hour", 6)), max_trade_risk_pct=float((auth.stop_conditions or {}).get("max_trade_risk_pct", 5.0)))
            max_capital = auth.max_capital
            open_trade = s.query(LiveTrade).filter(LiveTrade.portfolio_id == pf_id, LiveTrade.exit_ts.is_(None)).one_or_none()
            entry_price, open_qty = (open_trade.entry_price, open_trade.qty) if open_trade else (0.0, 0.0)
            tp = s.query(TradingPair).filter_by(symbol=pair).one_or_none()
            min_notional = tp.min_notional if tp else 5.0
            hour_ago = utcnow().timestamp() - 3600
            orders_hour = sum(1 for o in s.query(LiveOrder).filter(LiveOrder.portfolio_id == pf_id, LiveOrder.status.in_(("filled", "unknown", "pending"))) if o.created_at.timestamp() >= hour_ago)
        symbol = to_symbol(pair)
        step = TIMEFRAMES[tf]
        df = self.store.load(pair, tf, start_ts=now - max(step * WINDOW, HISTORY_DAYS * 86400))
        stop_pct = float(risk.get("stoploss_pct", 0.03))
        price = last_price if last_price is not None else (float(df["close"].iloc[-1]) if len(df) else 0.0)
        # Stops are evaluated every cycle on the latest price, not only on closed candles.
        if open_qty and price and price <= entry_price * (1 - stop_pct):
            self._send(pf_id, symbol, "SELL", f"ql{pf_id}s{now // 60}", base=open_qty, reason="stoploss", ts=now)
            return "stoploss"
        if df.empty or int(df["ts"].iloc[-1]) + step > now or int(df["ts"].iloc[-1]) <= last_ts:
            return "no_new_candle"
        candle_ts = int(df["ts"].iloc[-1])
        if candle_ts + step * 2 < now:
            return "stale_data"  # never act on old market data
        try:
            sig = get_strategy(engine_key).signals(df, params)
        except Exception as exc:
            with self.db.session() as s:
                self._halt(s, s.get(LivePortfolio, pf_id), "strategy_error", str(exc)[:300])
            return "strategy_error"
        enter, exit_ = bool(sig["enter"].iloc[-1]), bool(sig["exit"].iloc[-1])
        with self.db.session() as s:
            s.get(LivePortfolio, pf_id).last_candle_ts = candle_ts
        balances = self._balances()
        free = balances.get("USDT", 0.0)
        equity = free + open_qty * price
        with self.db.session() as s:
            pf = s.get(LivePortfolio, pf_id)
            pf.peak_equity = max(pf.peak_equity, min(equity, max_capital * 10))
            midnight = candle_ts - candle_ts % 86400
            first = s.query(EquitySnapshot).filter(EquitySnapshot.scope == "live", EquitySnapshot.scope_id == pf_id, EquitySnapshot.ts >= midnight).order_by(EquitySnapshot.ts).first()
            s.merge(EquitySnapshot(scope="live", scope_id=pf_id, ts=candle_ts, equity=equity)) if not s.query(EquitySnapshot).filter_by(scope="live", scope_id=pf_id, ts=candle_ts).count() else None
            if pf.status == "running":
                for v in portfolio_breaches(limits, equity, pf.peak_equity, first.equity if first else equity):
                    self._halt(s, pf, v.rule, v.detail, "warn")
                    break
            status = pf.status
        if open_qty and exit_:
            self._send(pf_id, symbol, "SELL", f"ql{pf_id}x{candle_ts}", base=open_qty, ts=now)
            return "exit"
        if enter and not open_qty:
            if status != "running":
                return "entry_blocked"
            # Same sizing as paper and backtest, always inside the authorized limits.
            stakes = stake_series(df, risk)
            sized = min(equity, max_capital) * float(stakes[-1]) if stakes is not None else limits.max_position_usdt
            quote = round(min(sized, limits.max_position_usdt, max_capital, free) * 0.999, 2)
            vio = entry_violations(limits, quote=quote, equity=min(equity, max_capital), free_usdt=free, open_positions=0, orders_last_hour=orders_hour, min_notional=min_notional, stoploss_pct=stop_pct)
            if vio:
                with self.db.session() as s:
                    for v in vio:
                        s.add(RiskEvent(scope="live", scope_id=pf_id, rule=v.rule, detail=v.detail))
                    notify(s, "risk", "Buyurtma risk qoidasi bilan rad etildi", "; ".join(v.detail for v in vio), "warn", "live")
                return "entry_rejected"
            self._send(pf_id, symbol, "BUY", f"ql{pf_id}e{candle_ts}", quote=quote, ts=now)
            return "entry"
        return "idle"


def start(db, settings: Settings, environment: str) -> None:
    with db.session() as s:
        reasons = gate_reasons(s, settings, environment)
        if reasons:
            raise PermissionError("; ".join(reasons))
        pf = get_portfolio(s, environment)
        auth = active_authorization(s, environment)
        pf.status, pf.halt_reason, pf.authorization_id = "running", "", auth.id
        if not pf.initial_capital:
            pf.initial_capital = pf.peak_equity = auth.max_capital
        syslog(s, "WARNING", "live", f"{environment} engine started by owner, authorization {auth.id}")
        notify(s, "live", f"REAL SAVDO BOSHLANDI ({environment})", f"Kapital chegarasi {auth.max_capital} USDT", "warn", "live")


def resume(db, settings: Settings, environment: str) -> None:
    """Owner approval after a halt. Same gates as a fresh start."""
    start(db, settings, environment)


def stop(db, environment: str) -> None:
    with db.session() as s:
        pf = get_portfolio(s, environment)
        pf.status = "stopped"
        syslog(s, "WARNING", "live", f"{environment} engine stopped by owner")


def kill_switch(db, environment: str, exchange: Exchange | None, close_positions: bool = True) -> dict:
    """Emergency stop. The persisted halt is committed first, so even if the exchange calls
    below fail, the engine will not open anything after a restart."""
    with db.session() as s:
        pf = get_portfolio(s, environment)
        pf.status, pf.halt_reason = "halted", "kill_switch: owner"
        s.add(RiskEvent(scope="live", scope_id=pf.id, rule="kill_switch", detail="owner"))
        notify(s, "live", f"FAVQULODDA TO'XTATISH ({environment})", "Yangi buyurtmalar bloklandi", "err", "live")
        pf_id = pf.id
        t = s.query(LiveTrade).filter(LiveTrade.portfolio_id == pf_id, LiveTrade.exit_ts.is_(None)).one_or_none()
        symbol, qty = (t.symbol, t.qty) if t else (None, 0.0)
    out = {"halted": True, "closed": False, "error": ""}
    if exchange is None or symbol is None or not close_positions:
        return out
    try:
        exchange.cancel_all(symbol)
        cid = f"ql{pf_id}k{int(time.time())}"
        res = exchange.market_sell(symbol, qty, cid)
        with db.session() as s:
            s.add(LiveOrder(portfolio_id=pf_id, client_order_id=cid, symbol=symbol, side="SELL", base_qty=qty, status=res.get("status", "FILLED").lower(), raw=res, exchange_order_id=str(res.get("orderId", ""))))
            avg, _, fee = _fill_price({**res, "symbol": symbol})
            t = s.query(LiveTrade).filter(LiveTrade.portfolio_id == pf_id, LiveTrade.exit_ts.is_(None)).one()
            t.exit_ts, t.exit_price, t.exit_fee, t.exit_reason = int(time.time()), avg, fee, "kill_switch"
            t.pnl = t.qty * avg - t.qty * t.entry_price - t.entry_fee - fee
        out["closed"] = True
    except (ExchangeError, ExchangeUnknown) as exc:
        out["error"] = str(exc)
        with db.session() as s:
            notify(s, "live", "Pozitsiyani yopib bo'lmadi", "Binance'da qo'lda tekshiring: " + str(exc)[:200], "err", "live")
            syslog(s, "ERROR", "live", f"kill switch close failed: {exc}")
    return out
