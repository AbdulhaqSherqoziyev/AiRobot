// @ts-nocheck
'use client';
import MarketExplorer from './generated/MarketExplorer';
import { fetchKlines, fetchTickers, reportSource } from '@/lib/live';

const POLL_MS = 5000;

/**
 * Design screen on real Binance data. Falls back to seeded demo data with a visible
 * label when Binance is unreachable. QL.MARKETS is shared with demo screens, whose
 * fake entry prices must never be valued at real prices, so it is restored on unmount.
 */
export default class MarketExplorerLive extends MarketExplorer {
  componentDidMount() {
    this.saved = window.QL.MARKETS.map((m) => ({ m, copy: { ...m } }));
    super.componentDidMount();
  }
  componentWillUnmount() {
    super.componentWillUnmount();
    clearInterval(this.poll);
    this.saved.forEach(({ m, copy }) => Object.assign(m, copy));
  }
  async load(sym, tf) {
    sym = sym || this.state.sym;
    tf = tf || this.state.tf;
    const key = sym + '|' + tf;
    this.want = key;
    try {
      const cs = await fetchKlines(sym, tf, 320);
      if (this.want !== key) return;
      if (!cs.length) throw new Error('no candles');
      this.setState({ sym, tf, cs, key, realCandles: true });
      reportSource('market');
    } catch {
      if (this.want !== key) return;
      this.setState({ sym, tf, cs: window.QL.candles(sym, tf, 320), key, realCandles: false });
      reportSource('demo');
    }
  }
  sub() {
    clearInterval(this.poll);
    if (this.props.live === false) return;
    const tick = async () => {
      try {
        const t = await fetchTickers(window.QL.MARKETS.map((m) => m.sym));
        const px = {};
        window.QL.MARKETS.forEach((m) => {
          const r = t[m.sym];
          if (!r) return;
          Object.assign(m, { price: r.price, ch: r.ch, vol: r.vol, high: r.high, low: r.low });
          px[m.sym] = r.price;
        });
        const s = this.state;
        const p = px[s.sym];
        let cs = s.cs;
        if (s.realCandles && cs && cs.length && p) {
          const step = window.QL.TF[s.tf], bucket = Math.floor(Date.now() / 1000 / step) * step, last = cs[cs.length - 1];
          if (bucket > last.time) {
            // A candle closed since the last load: refetch instead of inventing OHLC.
            this.load(s.sym, s.tf);
          } else {
            cs = cs.slice(0, -1).concat([{ ...last, close: p, high: Math.max(last.high, p), low: Math.min(last.low, p) }]);
          }
        }
        this.setState({ px, cs, realPrices: true });
      } catch {
        this.setState({ realPrices: false });
      }
    };
    tick();
    this.poll = setInterval(tick, POLL_MS);
  }
  renderVals() {
    const v = super.renderVals();
    if (!v.cur) return v;
    const real = this.state.realPrices && this.state.realCandles;
    return {
      ...v,
      liveColor: real ? '#16C784' : '#F0B90B',
      liveLabel: real ? 'Jonli · Binance · har 5 soniyada' : "DEMO · Binance'ga ulanib bo'lmadi",
    };
  }
}
