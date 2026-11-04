// @ts-nocheck
/**
 * Fills the design's QL data object with real rows from the API, replacing every seeded
 * value. The screens read QL synchronously, so this is the single seam between them and the
 * backend. Nothing renders until the first hydrate, so demo values are never on screen.
 */
import QL from './ql';
import { api } from './api';

const Q: any = QL;
let current: any = null;
const lastRes: { value: any } = { value: null };
const candleCache = new Map<string, any[]>();

function replace(arr: any[], items: any[]) {
  arr.length = 0;
  arr.push(...items);
}

function monthLabels(list: any[]) {
  return list.map((m) => ({ ...m, label: Q.MON[m.m] }));
}

export const EMPTY_RES = {
  ret: 0, net: 0, cap: 100, final: 100, trades: 0, wins: 0, losses: 0, win: 0, pf: 0, mdd: 0, sharpe: 0, sortino: 0, avgDur: 0, avgTrade: 0, dailyEq: [], from: 0, to: 0, bars: 0,
  eq: [], dd: [], segs: [{ name: "O'qitish", from: 0, to: 0, ret: 0, pct: 60, color: '#3B82F6' }, { name: 'Validatsiya', from: 0, to: 0, ret: 0, pct: 20, color: '#9747FF' }, { name: 'Namunadan tashqari (OOS)', from: 0, to: 0, ret: 0, pct: 20, color: '#FFA841' }],
  monthly: [], dist: Array.from({ length: 14 }, (_, i) => ({ lo: i - 6, n: 0 })), candles: [], markers: [], list: [], open: null, empty: true,
};

/** Converts a saved backtest from the API into the result shape the Backtest Lab renders. */
export function toResult(d: any, split: number[] = [60, 20, 20]) {
  const m = d.metrics;
  const eqRaw = d.equity.map(([time, value]: number[]) => ({ time, value }));
  const stride = Math.max(1, Math.ceil(eqRaw.length / 1500));
  let pk = -Infinity;
  const eq: any[] = [], dd: any[] = [];
  eqRaw.forEach((p: any, i: number) => {
    pk = Math.max(pk, p.value);
    if (i % stride === 0 || i === eqRaw.length - 1) {
      eq.push(p);
      dd.push({ time: p.time, value: (p.value / pk - 1) * 100 });
    }
  });
  const n = eqRaw.length, a = Math.floor((n * split[0]) / 100), b = Math.floor((n * (split[0] + split[1])) / 100);
  const seg = (name: string, i: number, j: number, pct: number, color: string) => ({ name, from: eqRaw[i]?.time, to: eqRaw[j]?.time, ret: eqRaw[i] && eqRaw[j] ? (eqRaw[j].value / eqRaw[i].value - 1) * 100 : 0, pct, color });
  const list = d.trades.map((t: any, i: number) => ({ id: i, entryT: t.entry_ts, exitT: t.exit_ts, entry: t.entry_price, exit: t.exit_price, qty: t.qty, fees: t.fees, pnl: t.pnl, pnlPct: t.pnl_pct, why: { signal: 'Signal', stoploss: 'Stop-loss', takeprofit: 'Take-profit' }[t.reason] || t.reason, cost: t.qty * t.entry_price, dur: t.exit_ts - t.entry_ts }));
  const bins = Array.from({ length: 14 }, (_, i) => ({ lo: i - 6, n: 0 }));
  list.forEach((t: any) => { bins[Math.max(0, Math.min(13, Math.floor(t.pnlPct) + 6))].n++; });
  const markers: any[] = [];
  list.forEach((t: any) => {
    markers.push({ time: t.entryT, position: 'belowBar', color: '#16C784', shape: 'arrowUp', text: 'B' });
    markers.push({ time: t.exitT, position: 'aboveBar', color: t.pnl >= 0 ? '#16C784' : '#EA3943', shape: 'arrowDown', text: 'S' });
  });
  const daily: number[] = [];
  let lastDay = -1;
  eqRaw.forEach((p: any) => { const day = Math.floor(p.time / 86400); if (day !== lastDay) { daily.push(p.value); lastDay = day; } else daily[daily.length - 1] = p.value; });
  return {
    ret: m.total_return ?? 0, net: m.net_profit, cap: m.initial_balance, final: m.final_balance, trades: m.total_trades, wins: m.winning_trades, losses: m.losing_trades, win: m.win_rate ?? 0, pf: m.profit_factor ?? 0, mdd: m.max_drawdown ?? 0, sharpe: m.sharpe ?? 0, sortino: m.sortino ?? 0, avgDur: m.avg_holding_seconds ?? 0, avgTrade: m.avg_trade_return ?? 0, dailyEq: daily, from: eqRaw[0]?.time, to: eqRaw[n - 1]?.time, bars: n,
    eq, dd, segs: [seg("O'qitish", 0, a, split[0], '#3B82F6'), seg('Validatsiya', a, b, split[1], '#9747FF'), seg('Namunadan tashqari (OOS)', b, n - 1, split[2], '#FFA841')],
    monthly: monthLabels(d.monthly), dist: bins, candles: d.candles, markers: markers.sort((x, y) => x.time - y.time), list, open: null, metrics: m,
  };
}

export function hydrate(snap: any) {
  current = snap;
  const placeholder = (sym: string) => ({ sym, base: sym.split('/')[0], price: 0, ch: 0, vol: 0, dv: 0, rank: 0, spark: [0, 0], high: 0, low: 0 });

  const rows = Object.entries(snap.tickers).sort((a: any, b: any) => b[1].vol - a[1].vol);
  if (rows.length) {
    replace(Q.MARKETS, rows.map(([sym, t]: any, i) => {
      const prev = Q.MK[sym];
      const spark = prev && prev.price === t.price ? prev.spark : [...((prev?.real && prev.spark) || []), t.price].slice(-48);
      return { sym, base: sym.split('/')[0], price: t.price, ch: t.ch, vol: t.vol, dv: 0, rank: i + 1, spark: spark.length > 1 ? spark : [t.price, t.price], high: t.high, low: t.low, real: true };
    }));
  } else {
    replace(Q.MARKETS, []);
  }
  Object.keys(Q.MK).forEach((k) => delete Q.MK[k]);
  Q.MARKETS.forEach((m: any) => { Q.MK[m.sym] = m; });
  const px = Q.stream.px;
  Object.keys(px).forEach((k) => delete px[k]);
  Q.MARKETS.forEach((m: any) => { px[m.sym] = m.price; });
  [...snap.sessions.map((s: any) => s.pair), ...snap.strategies.map((s: any) => s.pair)].forEach((p: string) => { if (!Q.MK[p]) Q.MK[p] = placeholder(p); });

  replace(Q.STRATS, snap.strategies.map((s: any) => ({
    ...s, monthly: monthLabels(s.monthly), curve: s.curve.length ? s.curve : [{ time: Q.NOW(), value: 0 }], dd: s.dd.length ? s.dd : [{ time: Q.NOW(), value: 0 }], dailyEq: s.dailyEq.length ? s.dailyEq : [100, 100],
  })));
  replace(Q.SESS, snap.sessions);
  replace(Q.MODELS, snap.models);
  replace(Q.FEATURES, snap.features);
  replace(Q.JOBS, snap.jobs);
  replace(Q.BACKTESTS, snap.backtests);
  replace(Q.NOTIFS, snap.notifications);
  const P = Q.portfolio, now = Q.NOW(), pf = snap.portfolio;
  Object.keys(P).forEach((k) => delete P[k]);
  // Before the first closed candle the only true data point is the opening capital.
  const point = (v: number) => [{ time: now, value: v }];
  Object.assign(P, pf, {
    monthly: monthLabels(pf.monthly), values: pf.values.length ? pf.values : [pf.start], equity: pf.equity.length ? pf.equity : point(pf.start),
    dd: pf.dd.length ? pf.dd : point(0), pnlPct: pf.pnlPct.length ? pf.pnlPct : point(0), bench: pf.bench.length ? pf.bench : point(0),
  });
  Q.END = Q.NOW();
  Q.optimizations = snap.optimizations;
  Q.backend = true;
  window.dispatchEvent(new Event('ql-data'));
}

/** Function overrides, installed once. */
export function install() {
  const missing = { id: '', name: "O'chirilgan strategiya", color: '#64748B', pair: 'BTC/USDT', tf: '1h', sl: 0, tp: 0, ret: 0, sharpe: 0, mdd: 0, trades: 0, win: 0, curve: [], dd: [], monthly: [], dailyEq: [], spark: [0, 0] };
  Q.strat = (id: string) => Q.STRATS.find((s: any) => s.id === String(id)) || Q.STRATS[0] || missing;
  Q.trades = () => current?.trades || [];
  Q.sessTrades = (s: any) => s.closed || [];
  Q.sessEvents = (s: any) => {
    const st = Q.strat(s.strat);
    const ev: any[] = [{ t: s.started, kind: 'start', text: "Sessiya boshlandi · boshlang'ich balans " + Q.fmt.usd(s.start), sub: 'Paper rejim · real buyurtma yuborilmaydi' }];
    (s.closed || []).forEach((t: any) => {
      ev.push({ t: t.entryT, kind: 'buy', text: 'Virtual SOTIB OLISH @ ' + Q.fmt.price(t.entry), sub: Q.fmt.num(t.qty, 6) + ' ' + s.pair.split('/')[0] });
      ev.push({ t: t.exitT, kind: 'sell', text: 'Virtual SOTISH @ ' + Q.fmt.price(t.exit) + ' · ' + t.why, sub: 'PnL ' + Q.fmt.susd(t.pnl, 3) });
    });
    if (s.pos) ev.push({ t: s.pos.t, kind: 'buy', text: 'Virtual SOTIB OLISH @ ' + Q.fmt.price(s.pos.entry), sub: Q.fmt.num(s.pos.qty, 6) + ' ' + s.pair.split('/')[0] + ' · ochiq' });
    if (s.note) ev.push({ t: Q.NOW(), kind: 'warn', text: s.note, sub: st.name });
    return ev.sort((a, b) => b.t - a.t);
  };
  Q.btDefaults = (s: any) => ({ strat: s.id, pair: s.pair, tf: s.tf, days: 180, capital: 100, fee: 0.1, slip: 0.05, sl: s.sl, tp: s.tp, size: 95, rsiP: 14, os: 30, ob: 70, fast: 20, slow: 50, split: [60, 20, 20] });
  Q.runBT = () => lastRes.value || EMPTY_RES;
  Q.setLastRes = (r: any) => { lastRes.value = r; };
  Q.candles = (sym: string, tf: string, n: number) => {
    const key = sym + '|' + tf;
    if (!candleCache.has(key)) {
      candleCache.set(key, []);
      api(`/market/klines?pair=${encodeURIComponent(sym)}&timeframe=${tf}&limit=${Math.min(n, 1000)}`).then((rows: any[]) => {
        candleCache.set(key, rows);
        window.dispatchEvent(new CustomEvent('ql-candles', { detail: key }));
      }).catch(() => candleCache.delete(key));
    }
    return candleCache.get(key)!;
  };
  // Prices come from the snapshot; there is no simulated tick anymore.
  const subs = new Set<any>();
  Q.stream.subscribe = (f: any) => { subs.add(f); return () => subs.delete(f); };
  window.addEventListener('ql-data', () => subs.forEach((f: any) => { try { f(Q.stream.px); } catch { /* one screen must not stop others */ } }));
  // New status words from the real engines.
  const status = Q.status;
  Q.status = (k: string) => (k === 'halted' ? { label: "Risk to'xtatdi", color: '#EA3943', bg: 'rgba(234,57,67,.13)' } : k === 'cancelled' ? { label: 'Bekor qilindi', color: '#94A3B8', bg: 'rgba(148,163,184,.13)' } : status(k));
}

export async function refresh() {
  hydrate(await api('/snapshot'));
}
