// @ts-nocheck
'use client';
import React from 'react';
import { act, api } from '@/lib/api';
import { Btn, Card, Field, Grid, Input, Notice, Page, Pill, Select, T, Table } from './ui';

const OBJ = [['composite', 'Kompozit (risk bilan moslangan)'], ['sharpe', 'Sharpe'], ['profit_factor', 'Profit factor'], ['return', 'Daromad']];

export default function OptimizerLive({ toast, nav }: any) {
  const Q = window.QL, [, tick] = React.useReducer((x) => x + 1, 0);
  React.useEffect(() => { window.addEventListener('ql-data', tick); return () => window.removeEventListener('ql-data', tick); }, []);
  const strategies = Q.STRATS.filter((s) => s.kind === 'technical' && s.engine !== 'rule_builder');
  const [f, setF] = React.useState({ strategy_id: strategies[0]?.id, pair: 'BTC/USDT', timeframe: '4h', trials: 50, objective: 'composite', candles: 6000, oos_frac: 0.3, min_trades: 10, max_dd: 25 });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const st = Q.STRATS.find((s) => s.id === String(f.strategy_id));
  const list = Q.optimizations || [];
  const [sel, setSel] = React.useState(null);
  const cur = list.find((o) => o.id === sel) || list[0];
  const running = list.filter((o) => o.status === 'queued' || o.status === 'running');
  const start = () => act(toast, 'Optimizatsiya navbatga qo\'shildi', () => api('/optimizer', { body: { ...f, strategy_id: Number(f.strategy_id), trials: Number(f.trials), candles: Number(f.candles), oos_frac: Number(f.oos_frac), min_trades: Number(f.min_trades), max_dd: Number(f.max_dd) } }));
  const pct = (x) => (x == null ? '—' : <span style={{ color: Q.fmt.tone(x) }}>{Q.fmt.pct(x)}</span>);
  const name = (id) => Q.STRATS.find((s) => s.id === String(id))?.name || id;
  return (
    <Page title="Strategiya optimizatori" sub="Optuna TPE. Qidiruv faqat in-sample davrni ko'radi; eng yaxshi sozlamalar keyin ko'rilmagan davrda sinaladi.">
      <Grid min={320}>
        <Card title="Sozlamalar">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Grid min={140}>
              <Field label="Strategiya"><Select value={f.strategy_id} options={strategies.map((s) => [s.id, s.name])} onChange={set('strategy_id')} /></Field>
              <Field label="Juftlik"><Select value={f.pair} options={Q.MARKETS.map((m) => m.sym)} onChange={set('pair')} /></Field>
              <Field label="Taymfreym"><Select value={f.timeframe} options={['15m', '30m', '1h', '4h', '1d']} onChange={set('timeframe')} /></Field>
              <Field label="Sinovlar soni"><Input type="number" min="5" max="2000" value={f.trials} onChange={set('trials')} /></Field>
              <Field label="Maqsad"><Select value={f.objective} options={OBJ} onChange={set('objective')} /></Field>
              <Field label="Tarixiy shamlar"><Input type="number" min="600" value={f.candles} onChange={set('candles')} /></Field>
              <Field label="OOS ulushi"><Input type="number" step="0.05" min="0.1" max="0.6" value={f.oos_frac} onChange={set('oos_frac')} /></Field>
              <Field label="Min. savdolar"><Input type="number" min="1" value={f.min_trades} onChange={set('min_trades')} /></Field>
              <Field label="Maks. pasayish, %"><Input type="number" min="1" max="100" value={f.max_dd} onChange={set('max_dd')} /></Field>
            </Grid>
            {st ? <div style={{ fontSize: 12, color: T.muted }}>Parametrlar: {Object.keys(st.params).join(', ') || '—'}</div> : null}
            <Btn tone="primary" onClick={start}>Optimizatsiyani boshlash</Btn>
          </div>
        </Card>
        <Card title="Tarix" pad={false}>
          <Table empty="Hali optimizatsiya yo'q" heads={['#', 'Strategiya', 'Juftlik', 'Holat', '']} rows={list.map((o) => [o.id, name(o.strategyId), o.pair + ' ' + o.tf, o.status === 'running' ? `${Math.round(o.progress * 100)}%` : <Pill color={o.status === 'done' ? T.pos : o.status === 'error' ? T.neg : T.muted}>{o.status}</Pill>, <Btn style={{ height: 26 }} onClick={() => setSel(o.id)}>Ko'rish</Btn>])} />
        </Card>
      </Grid>
      {running.length ? <Notice tone="info">{running.length} ta optimizatsiya bajarilmoqda. Natijalar shu yerda paydo bo'ladi.</Notice> : null}
      {cur && cur.top?.length ? (
        <Card title={`Eng yaxshi konfiguratsiyalar · #${cur.id} ${name(cur.strategyId)}`} sub="In-sample natija yetarli emas: faqat OOS'dan o'tgani strategiyaga qo'llanadi." pad={false}>
          <Table heads={['#', 'Parametrlar', 'IS daromad', 'IS Sharpe', 'OOS daromad', 'OOS PF', 'OOS DD', 'OOS savdo', 'OOS holati', '']} rows={cur.top.map((t, i) => [i + 1, <code>{Object.entries(t.params).map(([k, v]) => `${k}=${typeof v === 'number' ? +v.toFixed(3) : v}`).join(' ')}</code>, pct(t.in_sample.total_return), (t.in_sample.sharpe ?? 0).toFixed(2), pct(t.out_of_sample.total_return), t.out_of_sample.profit_factor?.toFixed(2) ?? '—', pct(t.out_of_sample.max_drawdown), t.out_of_sample.total_trades, <Pill color={t.eligible ? T.pos : T.neg}>{t.eligible ? "O'tdi" : "O'tmadi"}</Pill>, t.eligible ? <Btn style={{ height: 26 }} onClick={() => act(toast, 'Yangi strategiya versiyasi yaratildi', () => api(`/optimizer/${cur.id}/apply/${i}`, { method: 'POST' }))}>Qo'llash</Btn> : null])} />
        </Card>
      ) : null}
      {cur && !cur.top?.length && cur.status === 'done' ? <Notice>Natija yo'q: cheklovlardan o'tgan konfiguratsiya topilmadi.</Notice> : null}
    </Page>
  );
}
