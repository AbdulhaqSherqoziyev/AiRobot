// @ts-nocheck
'use client';
import React from 'react';
import { act, api } from '@/lib/api';
import { pctCell } from './ExperimentLab';
import { Btn, Card, Field, Grid, Input, Notice, Page, Pill, Select, Stat, T, Table, fmtTs, usePoll } from './ui';

const STANCE = { consider_long: ["Long ko'rib chiqish", T.pos], stay_flat: ['Bozordan tashqarida', T.warn], no_view: ["Fikr yo'q", T.muted] };
const stance = (s) => (s ? <Pill color={(STANCE[s] || [])[1]}>{(STANCE[s] || [s])[0]}</Pill> : '—');
const List = ({ title, items }: any) => (items?.length ? <div><b style={{ fontSize: 13 }}>{title}</b><ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 13 }}>{items.map((x, i) => <li key={i}>{x}</li>)}</ul></div> : null);

export default function AiReportsScreen({ toast }: any) {
  const st = usePoll(() => api('/ai/status'), 20000);
  const list = usePoll(() => api('/ai/reports'), 10000);
  const [f, setF] = React.useState({ pair: 'BTC/USDT', timeframe: '4h', engine: 'rule_baseline' });
  const [sel, setSel] = React.useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const head = { title: 'AI tadqiqot hisobotlari', sub: "Ixtiyoriy fikr, saqlanadi va keyin bozor natijasi bilan solishtiriladi. Buyurtma yubormaydi, risk chegaralarini o'zgartirmaydi." };
  if (st.error) return <Page {...head}><Notice tone="err">{st.error}</Notice></Page>;
  const s = st.data;
  if (!s) return <Page {...head}><div style={{ color: T.muted }}>Yuklanmoqda…</div></Page>;
  const run = () => act(toast, 'Hisobot navbatga qo\'shildi', () => api('/ai/reports', { body: f }));
  const paid = f.engine !== 'rule_baseline';
  return (
    <Page {...head}>
      {!s.enabled ? <Notice tone="warn">AI moduli o'chiq. Uni "Tadqiqot integratsiyalari" sahifasida yoqish mumkin. Savdo va backtest bunga bog'liq emas.</Notice> : null}
      <Grid min={170}>
        <Stat label="24 soatlik chaqiruvlar" value={`${s.usage_24h.calls} / ${s.limits.calls}`} />
        <Stat label="24 soatlik xarajat" value={`$${s.usage_24h.usd} / $${s.limits.usd}`} />
        <Stat label="Model" value={s.engines.includes('claude') ? s.model : 'Sozlanmagan'} sub={`${s.limits.max_tokens} token, ${s.limits.timeout_s} s chegarasi`} />
      </Grid>
      <Card title="Yangi hisobot">
        <Grid min={190}>
          <Field label="Juftlik"><Input value={f.pair} onChange={set('pair')} /></Field>
          <Field label="Taymfreym"><Select value={f.timeframe} onChange={set('timeframe')} options={[['1h', '1h'], ['4h', '4h'], ['1d', '1d']]} /></Field>
          <Field label="Tahlilchi" hint={paid ? 'Bu pullik LLM chaqiruvi' : "LLM'siz qat'iy qoida, taqqoslash uchun"}><Select value={f.engine} onChange={set('engine')} options={s.engines.map((x) => [x, x])} /></Field>
        </Grid>
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <Btn tone="primary" disabled={!s.enabled} onClick={run}>Hisobot yaratish</Btn>
          <Btn onClick={() => act(toast, 'Natijalarni baholash navbatga qo\'shildi', () => api('/ai/outcomes', { method: 'POST' }))}>Natijalarni baholash</Btn>
        </div>
      </Card>
      <Card title="Tavsiyalar keyin nima bo'ldi" sub="Narx shunchaki necha marta ko'tarilgani yonida: tavsiya shundan yaxshi bo'lishi kerak. 30 ta namunadan kam natija ishonchli emas." pad={false}>
        <Table empty="Hali baholangan hisobot yo'q" heads={['Tahlilchi', 'Baholangan', 'To\'g\'ri', 'Aniqlik', "Narx ko'tarilgan", "Fikrsiz", 'Namuna']} rows={s.scoreboard.map((g) => [g.engine, g.scored, g.hits, g.hit_rate == null ? '—' : g.hit_rate + '%', g.price_rose_rate == null ? '—' : g.price_rose_rate + '%', g.no_view, g.enough_samples ? 'Yetarli' : <Pill color={T.warn}>Kam</Pill>])} />
      </Card>
      <Card title="Hisobotlar tarixi" pad={false}>
        <Table empty="Hali hisobot yo'q" heads={['#', 'Vaqt', 'Juftlik', 'TF', 'Tahlilchi', 'Holat', 'Pozitsiya', 'Ishonch', 'Xarajat', 'Natija', 'To\'g\'ri', '']} rows={(list.data || []).map((r) => [r.id, fmtTs(r.created), r.pair, r.timeframe, r.engine, <Pill color={r.status === 'ok' ? T.pos : T.neg}>{r.status}</Pill>, stance(r.stance), r.confidence || '—', r.usage?.usd != null ? '$' + r.usage.usd : '—', r.outcome ? pctCell(r.outcome.forward_return_pct) : 'Kutilmoqda', r.outcome?.hit == null ? '—' : r.outcome.hit ? 'Ha' : "Yo'q", <Btn onClick={() => setSel(r.id)}>Ochish</Btn>])} />
      </Card>
      {sel ? <Report id={sel} /> : null}
    </Page>
  );
}

function Report({ id }: any) {
  const { data: r, error } = usePoll(() => api('/ai/reports/' + id), 60000, [id]);
  if (error) return <Notice tone="err">{error}</Notice>;
  if (!r) return null;
  if (r.status !== 'ok') return <Card title={`Hisobot #${id}`}><Notice tone="err">{r.error}</Notice></Card>;
  const x = r.recommendation;
  return (
    <Card title={`Hisobot #${id}: ${x.symbol} ${x.timeframe}`} sub={`${r.engine}${r.model ? ' · ' + r.model : ''} · ${r.latency_s} s · oxirgi sham ${fmtTs(r.last_candle_ts)}`} right={stance(x.stance)}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 13 }}><b>Bozor rejimi farazi:</b> {x.market_regime_hypothesis}</div>
        <div style={{ fontSize: 13 }}><b>Ishonch ({x.confidence.level}):</b> {x.confidence.explanation}</div>
        <Table heads={['Dalil', 'Qiymat', 'Vaqt', 'Manba']} rows={x.evidence.map((e) => [e.name, e.value, fmtTs(e.timestamp), e.source])} />
        <List title="Kirish shartlari" items={x.entry_conditions} />
        <List title="Chiqish shartlari" items={x.exit_conditions} />
        <List title="Bekor qilish shartlari" items={x.invalidation_conditions} />
        <List title="Risklar" items={x.risks} />
        <List title="Yetishmayotgan ma'lumot" items={x.missing_data} />
        <div style={{ fontSize: 12, color: T.dim }}>Baholash ufqi: {x.horizon_candles} sham. Manbalar: {r.data_pack.sources.join(', ')}.</div>
      </div>
    </Card>
  );
}
