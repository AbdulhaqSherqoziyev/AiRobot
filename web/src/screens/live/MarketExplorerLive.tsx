// @ts-nocheck
'use client';
import MarketExplorer from '../generated/MarketExplorer';
import { api } from '@/lib/api';

/** Prices from the shared snapshot, chart from Binance. Nothing simulated. */
export default class MarketExplorerLive extends MarketExplorer {
  async load(sym, tf) {
    sym = sym || this.state.sym;
    tf = tf || this.state.tf;
    const key = sym + '|' + tf;
    this.want = key;
    try {
      const cs = await api(`/market/klines?pair=${encodeURIComponent(sym)}&timeframe=${tf}&limit=320`);
      if (this.want === key) this.setState({ sym, tf, cs, key, failed: false });
    } catch {
      if (this.want === key) this.setState({ sym, tf, cs: [], key, failed: true });
    }
  }
  sub() {
    if (this._u) this._u();
    this._u = window.QL.stream.subscribe((px) => {
      const s = this.state;
      this.setState({ px: { ...px } });
      if (s.cs && s.cs.length) {
        const step = window.QL.TF[s.tf], last = s.cs[s.cs.length - 1], bucket = Math.floor(Date.now() / 1000 / step) * step;
        if (bucket > last.time) this.load(s.sym, s.tf); // a candle closed: fetch it, do not invent it
      }
    });
  }
  renderVals() {
    const s = this.state;
    if (s.cs && !s.cs.length) return { ...super.renderVals(), v: { loading: false, ok: false, empty: false, error: true } };
    if (!window.QL.MK[s.sym] && window.QL.MARKETS[0]) this.state.sym = window.QL.MARKETS[0].sym;
    const v = super.renderVals();
    return v.cur ? { ...v, liveColor: '#16C784', liveLabel: 'Jonli · Binance' } : v;
  }
}
