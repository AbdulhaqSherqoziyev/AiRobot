// @ts-nocheck
'use client';
import PaperTrading from '../generated/PaperTrading';
import { act, api } from '@/lib/api';
import { Btn, Notice } from '../ui';

/** Design terminal over the real paper engine. Every control calls the API. */
export default class PaperLive extends PaperTrading {
  constructor(props) {
    super(props);
    const Q = window.QL, first = Q.SESS.find((x) => x.status !== 'stopped') || Q.SESS[0], strat = Q.STRATS.find((x) => x.status === 'active') || Q.STRATS[0];
    this.state.sel = props.params?.id ? String(props.params.id) : first ? first.id : '';
    this.state.nf = { strat: props.params?.strat ? String(props.params.strat) : strat.id, pair: strat.pair, capital: 100 };
  }
  componentDidMount() {
    super.componentDidMount();
    this.onData = () => {
      if (!this.state.sessions) return;
      const Q = window.QL;
      this.setState({ sessions: Q.SESS.map((s) => ({ ...s, closed: Q.sessTrades(s) })) }, () => {
        const cur = this.sess();
        if (cur) this.loadEquity(cur.id, cur.dbId);
      });
    };
    window.addEventListener('ql-data', this.onData);
    this.onCandles = () => { const s = this.sess(); if (s) this.select(s.id); };
    window.addEventListener('ql-candles', this.onCandles);
  }
  componentWillUnmount() {
    super.componentWillUnmount();
    window.removeEventListener('ql-data', this.onData);
    window.removeEventListener('ql-candles', this.onCandles);
  }
  async loadEquity(id, dbId) {
    try {
      const eq = await api(`/paper/sessions/${dbId}/equity`);
      if (this.state.sel === id) this.setState({ eq });
    } catch { /* keeps the previous curve */ }
  }
  select(id) {
    const Q = window.QL, s = this.sess(id);
    if (!s) return;
    const cs = Q.candles(s.pair, s.tf, 180);
    // `cs` stays null until candles arrive: the design reads cs[0] whenever it is set.
    this.setState({ sel: id, cs: cs.length ? cs : null, log: Q.sessEvents(s), key: s.id + '|' + cs.length, eq: this.state.sel === id ? this.state.eq : [] });
    this.loadEquity(id, s.dbId);
  }
  /** Real data only: prices from the snapshot; closed candles are fetched, never invented. */
  sub() {
    if (this._u) this._u();
    this._u = window.QL.stream.subscribe((px) => this.setState({ px: { ...px } }));
  }
  equityOf(s) {
    return s.equity ?? s.start + s.realized;
  }
  renderVals() {
    const st = this.state, toast = this.props.toast, confirm = this.props.confirm;
    if (st.sessions && !st.sessions.length) {
      const v = super.renderVals();
      return { ...v, v: { loading: false, ok: false, error: false, empty: true }, startNew: this.startFn(), openNew: () => this.setState({ newOpen: true }) };
    }
    const v = super.renderVals();
    if (!st.sessions) return v;
    const s = this.sess() || st.sessions[0];
    const out = { ...v, startNew: this.startFn() };
    if (s) {
      // Markers must land on the session's own candles, not on one-minute buckets.
      const step = window.QL.TF[s.tf] || 3600, snap = (t) => Math.floor(t / step) * step;
      const first = st.cs?.[0]?.time ?? 0;
      const marks = [];
      (s.closed || []).forEach((t) => {
        if (t.entryT >= first) marks.push({ time: snap(t.entryT), position: 'belowBar', color: '#16C784', shape: 'arrowUp', text: 'B' });
        if (t.exitT >= first) marks.push({ time: snap(t.exitT), position: 'aboveBar', color: t.pnl >= 0 ? '#16C784' : '#EA3943', shape: 'arrowDown', text: 'S' });
      });
      if (s.pos && s.pos.t >= first) marks.push({ time: snap(s.pos.t), position: 'belowBar', color: '#16C784', shape: 'arrowUp', text: 'B' });
      out.markers = marks.sort((a, b) => a.time - b.time);
    }
    if (v.pause && s) {
      const run = (action, text) => act(toast, text, () => api(`/paper/sessions/${s.dbId}/${action}`, { method: 'POST' }));
      out.pause = () => run('pause', 'Sessiya pauzada: yangi kirishlar toʻxtatildi');
      out.resume = () => run('resume', 'Sessiya davom etmoqda');
      out.stop = () => confirm({ danger: true, title: "Sessiyani to'xtatasizmi?", okLabel: "To'xtatish", text: "Ochiq pozitsiya oxirgi yopilgan sham narxida virtual yopiladi. Sessiya tarixga o'tadi.", onOk: () => run('stop', "Sessiya to'xtatildi") });
      out.reset = () => confirm({ danger: true, title: 'Sessiyani qayta boshlaysizmi?', okLabel: 'Qayta boshlash', text: "Balans boshlang'ich holatga qaytadi, savdolar tarixi o'chiriladi.", onOk: () => run('reset', 'Sessiya qayta boshlandi') });
    }
    return out;
  }
  startFn() {
    return () => {
      const nf = this.state.nf;
      act(this.props.toast, 'Paper sessiya boshlandi', async () => {
        const { id } = await api('/paper/sessions', { body: { strategy_id: Number(nf.strat), pair: nf.pair, capital: Number(nf.capital) } });
        this.setState({ newOpen: false, sel: String(id), tab: 'log' });
      });
    };
  }
  render() {
    const s = this.state.sessions && this.sess();
    return (
      <>
        {s && s.rawStatus === 'halted' ? <div style={{ marginBottom: 12 }}><Notice tone="err">Risk chegarasi ishladi: {s.note}. Yangi kirishlar to'xtatilgan; davom ettirish sizning tasdig'ingizni talab qiladi.</Notice></div> : null}
        {super.render()}
      </>
    );
  }
}
