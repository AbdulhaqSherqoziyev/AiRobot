// @ts-nocheck
'use client';
import BacktestLab from '../generated/BacktestLab';
import { api } from '@/lib/api';
import { refresh, toResult } from '@/lib/backend';
import { Notice } from '../ui';

/** Design lab running on the server engine with real candles. Results are stored server-side. */
export default class BacktestLive extends BacktestLab {
  componentDidMount() {
    super.componentDidMount();
    window.QL.setLastRes(null);
    const want = this.props.params?.strat;
    const last = window.QL.BACKTESTS.find((b) => b.status === 'done' && (!want || b.strat === String(want)));
    if (last) setTimeout(() => this.show(last.dbId, false), 60); // after the base class builds cfg
  }
  componentWillUnmount() {
    super.componentWillUnmount();
    clearTimeout(this._poll);
  }
  async show(id, notify = true) {
    const d = await api('/backtests/' + id);
    const res = toResult(d, this.state.cfg?.split);
    window.QL.setLastRes(res);
    // The form must describe the result on screen, never another strategy.
    const c = d.config || {};
    const cfg = { ...this.state.cfg, strat: String(d.strategy_id), label: d.strategy + ' v' + d.version, pair: d.pair, tf: d.timeframe, from: d.start_ts, end: d.end_ts, capital: c.initial ?? 100, fee: (c.fee ?? 0.001) * 100, slip: (c.slippage ?? 0.0005) * 100, sl: c.stoploss_pct != null ? c.stoploss_pct * 100 : this.state.cfg?.sl, tp: c.takeprofit_pct != null ? c.takeprofit_pct * 100 : this.state.cfg?.tp };
    this.setState({ running: false, progress: 100, res, page: 0, runAt: window.QL.NOW(), lastId: id, runError: '', cfg });
    if (notify) this.props.toast?.('Backtest yakunlandi: ' + window.QL.fmt.pct(res.ret) + ' · ' + res.trades + ' ta savdo', 'ok');
  }
  async run() {
    if (this.state.running) return;
    const c = this.state.cfg;
    c.label = undefined;
    this.setState({ running: true, progress: 2, runError: '' });
    try {
      const { id, job_id } = await api('/backtests', { body: { strategy_id: Number(c.strat), pair: c.pair, timeframe: c.tf, start_ts: c.from, end_ts: c.end, initial: Number(c.capital), fee: Number(c.fee) / 100, slippage: Number(c.slip) / 100, stake_pct: Math.min(1, Number(c.size) / 100), stoploss_pct: Number(c.sl) / 100, takeprofit_pct: Number(c.tp) / 100 } });
      this.jobId = job_id;
      const tick = async () => {
        if (!this.state.running) return;
        const b = await api('/backtests/' + id);
        if (b.status === 'done') { await this.show(id); refresh(); return; }
        if (b.status === 'error' || b.status === 'cancelled') { this.setState({ running: false, progress: 0, runError: b.error || 'Bekor qilindi' }); this.props.toast?.(b.error || 'Bekor qilindi', 'err'); return; }
        const jobs = await api('/jobs');
        const j = jobs.find((x) => x.id === job_id);
        this.setState({ progress: Math.max(3, (j?.progress || 0) * 100) });
        this._poll = setTimeout(tick, 1000);
      };
      tick();
    } catch (e) {
      this.setState({ running: false, progress: 0, runError: e.message });
      this.props.toast?.(e.message, 'err');
    }
  }
  stop() {
    clearTimeout(this._poll);
    if (this.jobId) api(`/jobs/${this.jobId}/cancel`, { method: 'POST' }).catch(() => {});
    this.setState({ running: false, progress: 0 });
    this.props.toast?.("Backtest to'xtatildi", 'warn');
  }
  renderVals() {
    const v = super.renderVals(), s = this.state;
    if (!v.res) return v;
    const out = { ...v, save: () => this.props.toast?.('Har bir backtest serverda avtomatik saqlanadi', 'info') };
    if (s.lastId) out.exportCsv = () => { window.location.href = `/api/q/backtests/${s.lastId}/export.csv`; };
    return out;
  }
  render() {
    const s = this.state;
    return (
      <>
        {s.res?.empty && !s.running ? <div style={{ marginBottom: 12 }}><Notice tone="info">Hali natija yo'q: sozlamalarni tanlab backtestni ishga tushiring. Hozirgi nollar natija emas.</Notice></div> : null}
        {s.runError ? <div style={{ marginBottom: 12 }}><Notice tone="err">{s.runError}</Notice></div> : null}
        {super.render()}
      </>
    );
  }
}
