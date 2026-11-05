"""Jesse form of `jesse_rsi_trend`: runs only inside the isolated Jesse venv."""
import jesse.indicators as ta
from jesse import utils
from jesse.strategies import Strategy

LOG = []


class QlRsiTrend(Strategy):
    def should_long(self):
        r = ta.rsi(self.candles, 14, sequential=True)
        e = ta.ema(self.candles, 100)
        return r[-1] > 40 and r[-2] <= 40 and self.close > e

    def should_short(self):
        return False

    def go_long(self):
        self.buy = utils.size_to_qty(self.balance * 0.95, self.price, fee_rate=self.fee_rate, precision=8), self.price

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return True

    def update_position(self):
        if ta.rsi(self.candles, 14) >= 65:
            self.liquidate()

    def on_open_position(self, order):
        LOG.append(("buy", int(self.current_candle[0] // 1000), float(self.position.entry_price), float(self.position.qty)))

    def on_close_position(self, order, closed_trade=None):
        LOG.append(("sell", int(self.current_candle[0] // 1000), float(order.price), float(order.qty)))
