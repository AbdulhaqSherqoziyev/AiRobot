// @ts-nocheck
'use client';
import Dashboard from '../generated/Dashboard';
import React from 'react';
import { api } from '@/lib/api';
import { Grid, Stat, T, usePoll } from '../ui';

/** Real money is shown apart from every virtual number on this page. */
function RealAccount({ nav }: any) {
  const { data: d } = usePoll(() => api('/live/status?environment=live'), 15000);
  const f = window.QL.fmt;
  if (!d) return null;
  return (
    <section onClick={() => nav?.('live')} style={{ border: '1px solid #DC2F3A66', borderRadius: 12, padding: 12, marginBottom: 16, cursor: 'pointer' }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.05em', color: '#F87171', marginBottom: 10 }}>REAL HISOB · BINANCE SPOT</div>
      <Grid min={170}>
        <Stat label="Holat" value={d.status === 'running' ? 'Ishlamoqda' : d.status === 'halted' ? "To'xtatilgan" : "O'chiq"} color={d.status === 'running' ? T.pos : d.status === 'halted' ? T.neg : T.muted} sub={d.gate_reasons.length ? 'Yopiq: ' + d.gate_reasons[0] : 'Barcha shartlar bajarilgan'} />
        <Stat label="Kapital chegarasi" value={d.authorization ? f.usd(d.authorization.max_capital) : '—'} />
        <Stat label="Real PnL" value={f.susd(d.realized)} color={f.tone(d.realized)} />
      </Grid>
    </section>
  );
}

/** Design dashboard with its static health and insight text replaced by real values. */
export default class DashboardLive extends Dashboard {
  componentDidMount() {
    super.componentDidMount();
    this.onData = () => { this._c = null; this.forceUpdate(); };
    window.addEventListener('ql-data', this.onData);
    this.loadHealth();
    this._h = setInterval(() => this.loadHealth(), 30000);
  }
  componentWillUnmount() {
    super.componentWillUnmount();
    window.removeEventListener('ql-data', this.onData);
    clearInterval(this._h);
  }
  render() {
    return (
      <>
        <RealAccount nav={this.props.nav} />
        {super.render()}
      </>
    );
  }
  async loadHealth() {
    try {
      const m = await api('/system/monitor');
      this.setState({ mon: m });
      this._c = null;
    } catch { /* the card shows that the data is unavailable */ }
  }
  cache() {
    const was = this._c;
    const c = super.cache();
    if (was) return c;
    const Q = window.QL, f = Q.fmt, m = this.state.mon;
    const ok = (b) => Q.status(b ? 'ok' : 'error');
    c.health = m ? [
      { name: 'Binance ommaviy bozor API', detail: m.binance.ok ? m.binance.latency_ms + ' ms' : "Javob yo'q", st: ok(m.binance.ok) },
      { name: 'WebSocket narx oqimi', detail: m.websocket.reconnects + ' ta qayta ulanish', st: ok(m.websocket.connected) },
      { name: "Ma'lumotlar bazasi", detail: m.database.ok ? 'Ulangan' : m.database.error, st: ok(m.database.ok) },
      ...m.workers.map((w) => ({ name: 'Worker: ' + w.name, detail: w.age_seconds + ' soniya oldin', st: ok(w.ok) })),
      { name: 'Server', detail: `CPU ${m.cpu_pct}% · RAM ${m.ram_pct}% · Disk ${m.disk_pct}%`, st: ok(m.disk_pct < 90 && m.ram_pct < 95) },
    ] : [{ name: 'Tizim holati', detail: 'Yuklanmoqda…', st: Q.status('queued') }];
    const tested = Q.STRATS.filter((s) => s.hasBacktest).sort((a, b) => b.ret - a.ret);
    c.insights = [];
    if (tested.length) {
      const best = tested[0], worst = tested[tested.length - 1];
      c.insights.push({ icon: 'sparkles', color: '#60A5FA', title: best.name + ' yetakchi', text: `Oxirgi backtest: ${f.pct(best.ret)}, maksimal pasayish ${f.pct(best.mdd)}. Bu kelajak natijasini kafolatlamaydi.`, cta: 'Backtestda ochish', go: () => this.nav('backtest', { strat: best.id }) });
      c.insights.push({ icon: 'triangle-alert', color: '#EA3943', title: worst.name + ' eng past', text: `Oxirgi backtest: ${f.pct(worst.ret)}, ${worst.trades} ta savdo.`, cta: 'Backtestda ochish', go: () => this.nav('backtest', { strat: worst.id }) });
      const pos = tested.filter((s) => s.ret > 0).length;
      c.insights.push({ icon: 'git-compare', color: '#F0B90B', title: `${tested.length} tadan ${pos} tasi foydali`, text: "Natijalar komissiya va slippage'dan keyin hisoblangan.", cta: 'Solishtirish', go: () => this.nav('compare') });
    } else {
      c.insights.push({ icon: 'flask-conical', color: '#60A5FA', title: 'Hali backtest yo\'q', text: 'Natijalar paydo bo\'lishi uchun Backtest laboratoriyasida strategiyani sinang.', cta: 'Backtest', go: () => this.nav('backtest') });
    }
    return c;
  }
}
