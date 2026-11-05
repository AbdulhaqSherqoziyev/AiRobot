// @ts-nocheck
'use client';
import React from 'react';
import { act, api } from '@/lib/api';
import { Btn, Card, Field, Grid, Input, Notice, Page, Pill, Select, Stat, T, Table, fmtTs, usePoll } from './ui';

const ELIG = { paper_candidate: ['Paper nomzodi', T.warn], rejected: ['Rad etildi', T.neg] };
const STATUS = { done: T.pos, error: T.neg, running: T.accent, queued: T.muted, cancelled: T.muted };
export const eligPill = (s) => (s ? <Pill color={(ELIG[s] || [])[1] || T.muted}>{(ELIG[s] || [s])[0]}</Pill> : '—');
const num = (x, d = 2) => (x == null ? '—' : Number(x).toFixed(d));
export const pctCell = (x) => (x == null ? '—' : <span style={{ color: window.QL.fmt.tone(x) }}>{window.QL.fmt.pct(x)}</span>);
const day = (t) => new Date(t * 1000).toISOString().slice(0, 10);
const toTs = (s) => Math.floor(Date.parse(s + 'T00:00:00Z') / 1000);

export default function ExperimentLab({ toast }: any) {
  const list = usePoll(() => api('/experiments'), 5000);
  const meta = usePoll(() => api('/experiments/presets'), 300000);
  const [f, setF] = React.useState({ preset: 'rsi_ema_example', pairs: 'BTC/USDT,ETH/USDT,SOL/USDT', timeframe: '4h', start: day(Date.now() / 1000 - 86400 * 365 * 4), end: day(Date.now() / 1000), backend: 'native', fee: 0.001, slippage: 0.0005, grid: '' });
  const [sel, setSel] = React.useState(null);
  const [cmp, setCmp] = React.useState([]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const preset = meta.data?.presets?.[f.preset];
  const grid = () => (f.grid.trim() ? JSON.parse(f.grid) : preset.grid);
  const start = () => act(toast, 'Tajriba navbatga qo\'shildi', async () => {
    const r = await api('/experiments', { body: { name: preset.label, strategy: preset.strategy, pairs: f.pairs.split(',').map((p) => p.trim()).filter(Boolean), timeframe: f.timeframe, start_ts: toTs(f.start), end_ts: toTs(f.end), grid: grid(), backend: f.backend, fee: Number(f.fee), slippage: Number(f.slippage) } });
    list.reload();
    return r;
  });
  const rows = list.data || [];
  const toggle = (id) => setCmp(cmp.includes(id) ? cmp.filter((x) => x !== id) : [...cmp, id]);
  return (
    <Page title="Tajriba laboratoriyasi" sub="Parametr sweep. Tanlov train va validation'da, test faqat tanlangan to'plamga, yakuniy natija asosiy dvigatelda. Bu sahifa buyurtma yubormaydi.">
      <Card title="Yangi tajriba">
        {!meta.data ? <div style={{ color: T.muted }}>Yuklanmoqda…</div> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Grid min={190}>
              <Field label="Andoza"><Select value={f.preset} onChange={set('preset')} options={Object.entries(meta.data.presets).map(([k, p]) => [k, p.label])} /></Field>
              <Field label="Juftliklar (vergul bilan)"><Input value={f.pairs} onChange={set('pairs')} /></Field>
              <Field label="Taymfreym"><Select value={f.timeframe} onChange={set('timeframe')} options={[['1h', '1h'], ['4h', '4h'], ['1d', '1d']]} /></Field>
              <Field label="Boshlanish"><Input type="date" value={f.start} onChange={set('start')} /></Field>
              <Field label="Tugash"><Input type="date" value={f.end} onChange={set('end')} /></Field>
              <Field label="Dvigatel" hint={meta.data.backends.vectorbt ? '' : "VectorBT o'rnatilmagan"}><Select value={f.backend} onChange={set('backend')} options={[['native', `Asosiy dvigatel (≤${meta.data.limits.native})`], ...(meta.data.backends.vectorbt ? [['vectorbt', `VectorBT, tezroq, ko'p xotira (≤${meta.data.limits.vectorbt})`]] : [])]} /></Field>
              <Field label="Komissiya"><Input type="number" step="0.0001" value={f.fee} onChange={set('fee')} /></Field>
              <Field label="Slippage"><Input type="number" step="0.0001" value={f.slippage} onChange={set('slippage')} /></Field>
            </Grid>
            <Field label="Parametr panjarasi (JSON, bo'sh qolsa andozadagi)"><Input value={f.grid} onChange={set('grid')} placeholder={JSON.stringify(preset?.grid || {})} /></Field>
            <div><Btn tone="primary" onClick={start}>Ishga tushirish</Btn></div>
          </div>
        )}
      </Card>
      <Card title="Barcha tajribalar" sub="Rad etilgan va xato bilan tugaganlar ham saqlanadi. Tartib: yangisi yuqorida, daromad bo'yicha emas." pad={false}>
        <Table empty="Hali tajriba yo'q" heads={['', '#', 'Strategiya', 'Juftlik', 'TF', 'Dvigatel', 'Holat', 'To\'plam', 'Vaqt', 'Test daromadi', 'Test DD', 'PF', 'Savdo', 'WF +', 'Baho', '']} rows={rows.map((e) => [
          <input type="checkbox" checked={cmp.includes(e.id)} onChange={() => toggle(e.id)} aria-label={`Taqqoslash ${e.id}`} />, e.id, e.strategy, e.pairs.length, e.timeframe, e.backend, <Pill color={STATUS[e.status] || T.muted}>{e.status}</Pill>, e.n_combos, e.runtime_s == null ? '—' : e.runtime_s.toFixed(1) + 's',
          pctCell(e.test?.total_return), pctCell(e.test?.max_drawdown), num(e.test?.profit_factor), e.test?.total_trades ?? '—', e.wf_positive_share == null ? '—' : Math.round(e.wf_positive_share * 100) + '%', eligPill(e.eligibility), <Btn onClick={() => setSel(e.id)}>Ochish</Btn>,
        ])} />
      </Card>
      {cmp.length > 1 ? <Compare rows={rows.filter((e) => cmp.includes(e.id))} /> : null}
      {sel ? <Detail id={sel} /> : null}
    </Page>
  );
}

function Compare({ rows }: any) {
  const metric = [['Test daromadi', (e) => pctCell(e.test?.total_return)], ['Test pasayishi', (e) => pctCell(e.test?.max_drawdown)], ['Sharpe', (e) => num(e.test?.sharpe)], ['Profit factor', (e) => num(e.test?.profit_factor)], ['Savdolar (median)', (e) => e.test?.total_trades ?? '—'], ['Walk-forward +', (e) => (e.wf_positive_share == null ? '—' : Math.round(e.wf_positive_share * 100) + '%')], ['Barqarorlik', (e) => (e.stability == null ? '—' : Math.round(e.stability * 100) + '%')], ['Dvigatel farqi', (e) => num(e.engine_gap, 3)], ['Baho', (e) => eligPill(e.eligibility)]];
  return <Card title="Taqqoslash" pad={false}><Table heads={['Ko\'rsatkich', ...rows.map((e) => `#${e.id} ${e.strategy}`)]} rows={metric.map(([k, fn]) => [k, ...rows.map(fn)])} /></Card>;
}

function Detail({ id }: any) {
  const { data: e, error } = usePoll(() => api('/experiments/' + id), 10000, [id]);
  const res = usePoll(() => api(`/experiments/${id}/results?limit=30`), 60000, [id]);
  if (error) return <Notice tone="err">{error}</Notice>;
  if (!e) return null;
  if (e.status === 'error') return <Card title={`Tajriba #${id}`}><Notice tone="err">{e.error}</Notice></Card>;
  const s = e.summary || {};
  if (!s.eligibility) return <Card title={`Tajriba #${id}`}><div style={{ color: T.muted }}>Holat: {e.status}</div></Card>;
  const Chart = window.QL.Chart;
  const series = Object.entries(s.equity_test || {}).map(([pair, pts], i) => ({ name: pair, color: ['#3B82F6', '#F59E0B', '#22C55E', '#A855F7', '#EF4444', '#14B8A6', '#EC4899', '#84CC16', '#F97316'][i % 9], data: pts.map(([t, v]) => ({ time: t, value: v })) }));
  return (
    <Card title={`Tajriba #${id}: ${e.strategy} v${e.version}`} right={<a href={`/api/q/experiments/${id}/export.csv`} style={{ color: T.accent, fontSize: 13 }}>CSV eksport</a>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Notice tone="info">{s.multiple_testing_note} {s.eligibility.note}</Notice>
        <Grid min={170}>
          <Stat label="Tanlangan parametrlar" value={s.selected ? '' : 'Yo\'q'} sub={s.selected ? JSON.stringify(s.selected) : "Mezonga yetadigan to'plam chiqmadi, test ochilmadi"} />
          <Stat label="Test daromadi (median)" value={pctCell(s.test_pooled?.total_return)} sub="Asosiy dvigatel" />
          <Stat label="Test pasayishi" value={pctCell(s.test_pooled?.max_drawdown)} />
          <Stat label="Walk-forward +" value={s.walk_forward?.positive_share == null ? '—' : Math.round(s.walk_forward.positive_share * 100) + '%'} sub={`Median OOS ${num(s.walk_forward?.median_oos_return)}%`} />
          <Stat label="Monte Carlo: zarar ehtimoli" value={s.monte_carlo?.prob_loss == null ? '—' : Math.round(s.monte_carlo.prob_loss * 100) + '%'} sub={s.monte_carlo?.note || `5-95%: ${num(s.monte_carlo?.return_p5)} .. ${num(s.monte_carlo?.return_p95)}%`} />
          <Stat label="Barqarorlik" value={s.sensitivity?.stability == null ? '—' : Math.round(s.sensitivity.stability * 100) + '%'} sub="Qo'shni to'plamlardan foydali ulushi" />
        </Grid>
        {series.length ? <div><div style={{ fontSize: 13, color: T.muted, marginBottom: 6 }}>Test davri kapitali, asosiy dvigatel</div><Chart series={series} height={240} /></div> : null}
        <Table heads={['Mezon', 'Qiymat', 'Talab', '']} rows={s.eligibility.checks.map((c) => [c.name, c.value == null ? '—' : String(c.value), c.need, <Pill color={c.ok ? T.pos : T.neg}>{c.ok ? "O'tdi" : "O'tmadi"}</Pill>])} />
        {s.engine_comparison ? <Table heads={['Juftlik', 'Dvigatel', 'Dvigatel daromadi', 'Asosiy daromad', 'Savdo', 'Asosiy savdo', 'Farq']} rows={s.engine_comparison.map((c) => [c.pair, c.backend, pctCell(c.backend_return), pctCell(c.authoritative_return), c.backend_trades, c.authoritative_trades, num(c.gap_pct_points, 4)])} /> : null}
        <Table heads={['Juftlik', 'Segment', 'Davr', 'Sham', 'Buy&Hold', 'Rejim']} rows={Object.entries(s.segments).flatMap(([pair, seg]) => Object.entries(seg).map(([k, v]) => [pair, k, `${day(v.start)} .. ${day(v.end)}`, v.candles, pctCell(v.buy_hold), v.regime]))} />
        <div><div style={{ fontSize: 13, color: T.muted, marginBottom: 6 }}>Validation Sharpe bo'yicha birinchi 30 ta ({res.data?.total ?? '—'} tadan)</div>
          <Table heads={['#', 'Parametrlar', 'Train', 'Train DD', 'Val', 'Val DD', 'Val Sharpe', 'Val PF', 'Val savdo']} rows={(res.data?.rows || []).map((r) => [r.selected ? <b>{r.rank} ✓</b> : r.rank, <code style={{ fontSize: 11 }}>{JSON.stringify(r.params)}</code>, pctCell(r.train.total_return), pctCell(r.train.max_drawdown), pctCell(r.validation.total_return), pctCell(r.validation.max_drawdown), num(r.validation.sharpe), num(r.validation.profit_factor), r.validation.total_trades ?? '—'])} /></div>
        <div style={{ fontSize: 12, color: T.dim }}>Takrorlash: {Object.entries(e.repro || {}).filter(([k]) => !['data_hash', 'rows'].includes(k)).map(([k, v]) => `${k}=${v}`).join(' · ')} · yaratilgan {fmtTs(e.created)} · xesh {Object.values(e.repro?.data_hash || {}).map((h) => String(h).slice(0, 8)).join(', ')}</div>
      </div>
    </Card>
  );
}
