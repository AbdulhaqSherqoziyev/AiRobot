"""Jesse form of `jesse_ema_cross`: runs only inside the isolated Jesse venv."""
import jesse.indicators as ta
from jesse import utils
from jesse.strategies import Strategy

LOG = []


class QlEmaCross(Strategy):
    def _cross(self):
        f = ta.ema(self.candles, 20, sequential=True)
        s = ta.ema(self.candles, 50, sequential=True)
        return f[-1], s[-1], f[-2], s[-2]

    def should_long(self):
        f, s, pf, ps = self._cross()
        return f > s and pf <= ps

    def should_short(self):
        return False

    def go_long(self):
        self.buy = utils.size_to_qty(self.balance * 0.95, self.price, fee_rate=self.fee_rate, precision=8), self.price

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return True

    def update_position(self):
        f, s, pf, ps = self._cross()
        if f < s and pf >= ps:
            self.liquidate()

    def on_open_position(self, order):
        LOG.append(("buy", int(self.current_candle[0] // 1000), float(self.position.entry_price), float(self.position.qty)))

    def on_close_position(self, order, closed_trade=None):
        LOG.append(("sell", int(self.current_candle[0] // 1000), float(order.price), float(order.qty)))
