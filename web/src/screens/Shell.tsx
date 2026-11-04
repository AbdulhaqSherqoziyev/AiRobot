// @ts-nocheck
'use client';
import QuantLab from './generated/QuantLab';
import Login from './Login';
import { api } from '@/lib/api';
import { hydrate, install, refresh } from '@/lib/backend';
import React from 'react';

const SNAPSHOT_MS = 10000;
const MODE = {
  backtest: { label: 'TARIXIY BACKTEST', title: "Tarixiy ma'lumotda simulyatsiya. Hech qanday buyurtma yuborilmaydi", fg: '#60A5FA', bg: 'rgba(59,130,246,.14)', border: 'rgba(59,130,246,.35)' },
  paper: { label: 'PAPER TRADING', title: "Real narx, virtual balans. Hech qanday real buyurtma yo'q", fg: '#F0B90B', bg: 'rgba(240,185,11,.12)', border: 'rgba(240,185,11,.3)' },
  testnet: { label: 'TESTNET', title: 'Binance Testnet: soxta pul, haqiqiy buyurtma oqimi', fg: '#C084FC', bg: 'rgba(192,132,252,.14)', border: 'rgba(192,132,252,.4)' },
  live: { label: 'REAL PUL · LIVE', title: 'Haqiqiy pul bilan savdo', fg: '#FFFFFF', bg: '#DC2F3A', border: '#DC2F3A' },
  research: { label: 'TADQIQOT', title: "Tadqiqot muhiti. Bu sahifa buyurtma yubormaydi", fg: '#94A3B8', bg: 'rgba(148,163,184,.12)', border: 'rgba(148,163,184,.3)' },
};
const ROUTE_MODE = { backtest: 'backtest', builder: 'backtest', optimizer: 'backtest', compare: 'backtest', paper: 'paper', evaluation: 'paper', trades: 'paper', portfolio: 'paper', live: 'live' };

class App extends QuantLab {
  constructor(props) {
    super(props);
    const fromUrl = window.location.pathname.split('/')[1];
    if (fromUrl) this.state.route = fromUrl;
    if (this.state.route === 'auth') this.state.route = 'dashboard'; // left by the old demo login
    this.state.latency = undefined;
    this.state.liveRunning = null;
    const go = this.nav;
    this.nav = (route, params) => {
      if (route === 'integrations') route = 'monitoring';
      go(route, params);
      if (window.location.pathname !== '/' + route) window.history.pushState(null, '', '/' + route);
    };
    this.setRoute = go;
    const remove = this.removeNotif, read = this.markRead, all = this.markAll;
    this.markRead = (id) => { read(id); const n = window.QL.NOTIFS.find((x) => x.id === id); if (n) api('/notifications/read', { body: [n.dbId] }).catch(() => {}); };
    this.removeNotif = (id) => { remove(id); const n = window.QL.NOTIFS.find((x) => x.id === id); if (n) api('/notifications/' + n.dbId, { method: 'DELETE' }).catch(() => {}); };
    this.markAll = () => { all(); api('/notifications/read', { method: 'POST' }).catch(() => {}); };
  }
  componentDidMount() {
    super.componentDidMount();
    clearInterval(this._lat);
    const ping = async () => {
      try { this.setState({ latency: (await api('/system/ping')).latency_ms }); } catch { this.setState({ latency: null }); }
      try {
        const [l, t] = await Promise.all([api('/live/status?environment=live'), api('/live/status?environment=testnet')]);
        this.setState({ liveRunning: l.status === 'running' ? 'live' : t.status === 'running' ? 'testnet' : null });
      } catch { /* banner state is unchanged on a failed poll */ }
    };
    ping();
    this._lat = setInterval(ping, 15000);
    this.onPop = () => this.setRoute(window.location.pathname.split('/')[1] || 'dashboard');
    window.addEventListener('popstate', this.onPop);
    this.onData = () => this.setState({ notifs: window.QL.NOTIFS.map((n) => ({ ...n })) });
    window.addEventListener('ql-data', this.onData);
  }
  componentWillUnmount() {
    super.componentWillUnmount();
    window.removeEventListener('popstate', this.onPop);
    window.removeEventListener('ql-data', this.onData);
  }
  renderVals() {
    const l = this.state.latency, base = super.renderVals(), route = this.state.route;
    const mode = this.state.liveRunning === 'live' ? 'live' : route === 'live' ? (this.state.liveRunning === 'testnet' ? 'testnet' : 'live') : ROUTE_MODE[route] || 'research';
    return {
      ...base, markRead: this.markRead, removeNotif: this.removeNotif, markAll: this.markAll, nav: this.nav, toast: this.toast, confirm: this.confirm,
      demoState: new URLSearchParams(window.location.search).get('demoState') || 'normal',
      badge: MODE[mode],
      latencyColor: l == null ? '#EA3943' : '#16C784',
      latencyText: l == null ? (l === null ? 'ulanmagan' : '…') : l + ' ms',
      logout: () => api('/auth/logout', { method: 'POST' }).finally(() => { this.props.onLogout(); }),
    };
  }
  render() {
    const running = this.state.liveRunning;
    return (
      <>
        {running === 'live' ? <div role="alert" style={{ position: 'fixed', top: 0, left: 0, right: 0, height: 4, background: '#DC2F3A', zIndex: 200 }} /> : null}
        {super.render()}
      </>
    );
  }
}

/** Gate: nothing from the app renders before login and the first real data load. */
export default function Shell() {
  const [state, setState] = React.useState<'checking' | 'login' | 'down' | 'ready'>('checking');

  const boot = React.useCallback(async () => {
    setState('checking');
    try {
      install();
      await api('/auth/me');
      await refresh();
      setState('ready');
    } catch (e: any) {
      setState(e.status === 401 ? 'login' : 'down');
    }
  }, []);

  React.useEffect(() => {
    boot();
  }, [boot]);

  React.useEffect(() => {
    if (state !== 'ready') return;
    const t = setInterval(() => refresh().catch((e) => { if (e.status === 401) setState('login'); }), SNAPSHOT_MS);
    return () => clearInterval(t);
  }, [state]);

  const center = { minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, background: '#0B0F19', color: '#94A3B8', fontSize: 14, padding: 16, textAlign: 'center' } as const;
  if (state === 'checking') return <div style={center}>Yuklanmoqda…</div>;
  if (state === 'login') return <Login onEnter={boot} />;
  if (state === 'down') {
    return (
      <div style={center}>
        <div style={{ fontSize: 16, fontWeight: 600, color: '#F1F5F9' }}>Backend ulanmagan</div>
        <div>API javob bermayapti. Hech qanday ma'lumot ko'rsatilmaydi va hech narsa o'zgartirilmaydi.</div>
        <button onClick={boot} style={{ height: 36, padding: '0 14px', borderRadius: 8, border: 0, background: '#3B82F6', color: '#F1F5F9', fontWeight: 600, cursor: 'pointer' }}>Qayta urinish</button>
      </div>
    );
  }
  return <App onLogout={() => setState('login')} />;
}
