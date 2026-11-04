// @ts-nocheck
'use client';
import React from 'react';
import { act, api } from '@/lib/api';
import { Btn, Card, Field, Grid, Input, Notice, Page, Pill, Select, T, Table, usePoll } from './ui';

const CATS = [['trade', 'Savdolar'], ['daily', 'Kunlik hisobot'], ['backtest', 'Backtest'], ['paper', 'Paper'], ['live', 'Live'], ['risk', 'Risk'], ['system', 'Tizim xatolari'], ['ml', 'ML'], ['evaluation', 'Baholash']];

function Credentials({ toast }) {
  const { data, reload } = usePoll(() => api('/settings/credentials'), 60000);
  const [f, setF] = React.useState({ environment: 'testnet', api_key: '', api_secret: '' });
  const save = () => act(toast, 'Kalitlar shifrlab saqlandi', async () => { await api('/settings/credentials', { method: 'PUT', body: f }); setF({ ...f, api_key: '', api_secret: '' }); reload(); });
  return (
    <Card title="Binance API kalitlari" sub="Serverda shifrlangan holda saqlanadi va brauzerga hech qachon qaytarilmaydi.">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Notice>Real kalit uchun: faqat Spot savdo ruxsati, yechib olish (withdrawal) o'chiq, IP cheklovi yoqilgan, alohida sub-hisob. Aks holda live engine ishga tushmaydi.</Notice>
        <Grid min={200}>
          <Field label="Muhit"><Select value={f.environment} options={[['testnet', 'Testnet'], ['live', 'Real (live)']]} onChange={(e) => setF({ ...f, environment: e.target.value })} /></Field>
          <Field label="API kalit"><Input autoComplete="off" value={f.api_key} onChange={(e) => setF({ ...f, api_key: e.target.value })} /></Field>
          <Field label="Maxfiy kalit"><Input type="password" autoComplete="new-password" value={f.api_secret} onChange={(e) => setF({ ...f, api_secret: e.target.value })} /></Field>
        </Grid>
        <div><Btn tone="primary" disabled={f.api_key.length < 8 || f.api_secret.length < 8} onClick={save}>Saqlash</Btn></div>
        <Table empty="Kalitlar kiritilmagan" heads={['Muhit', 'Kalit oxiri', '']} rows={(data || []).map((c) => [c.environment, '••••' + c.hint, <Btn style={{ height: 26 }} onClick={() => act(toast, "O'chirildi", async () => { await api('/settings/credentials/' + c.environment, { method: 'DELETE' }); reload(); })}>O'chirish</Btn>])} />
      </div>
    </Card>
  );
}

function Prefs({ toast }) {
  const { data } = usePoll(() => api('/settings/notifications'), 600000);
  const { data: tg } = usePoll(() => api('/telegram/status'), 600000);
  const [p, setP] = React.useState(null);
  const v = p || data;
  return (
    <Card title="Bildirishnomalar va Telegram" sub="Telegram ixtiyoriy: uzilgan bo'lsa ham web ilova to'liq ishlaydi." right={<Pill color={tg?.configured ? T.pos : T.muted}>{tg?.configured ? 'Telegram ulangan' : 'Telegram ulanmagan'}</Pill>}>
      {!tg?.configured ? <p style={{ margin: '0 0 12px', fontSize: 13, color: T.muted }}>Ulash uchun serverda <code>QL_TELEGRAM_TOKEN</code> va <code>QL_TELEGRAM_CHAT_ID</code> o'zgaruvchilarini o'rnating. Token ataylab brauzer orqali kiritilmaydi.</p> : null}
      {v ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14 }}>
          {CATS.map(([k, label]) => <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#CBD5E1' }}><input type="checkbox" checked={!!v[k]} onChange={(e) => setP({ ...v, [k]: e.target.checked })} />{label}</label>)}
        </div>
      ) : null}
      <Btn style={{ marginTop: 12 }} disabled={!p} onClick={() => act(toast, 'Saqlandi', async () => { await api('/settings/notifications', { method: 'PUT', body: { value: p } }); setP(null); })}>Saqlash</Btn>
    </Card>
  );
}

function Password({ toast }) {
  const [f, setF] = React.useState({ current: '', new: '' });
  return (
    <Card title="Xavfsizlik" sub="5 ta noto'g'ri urinishdan keyin kirish 15 daqiqaga bloklanadi.">
      <Grid min={200}>
        <Field label="Joriy parol"><Input type="password" value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} autoComplete="current-password" /></Field>
        <Field label="Yangi parol" hint="Kamida 12 belgi"><Input type="password" value={f.new} onChange={(e) => setF({ ...f, new: e.target.value })} autoComplete="new-password" /></Field>
      </Grid>
      <Btn style={{ marginTop: 12 }} disabled={!f.current || f.new.length < 12} onClick={() => act(toast, "Parol o'zgartirildi", async () => { await api('/auth/password', { body: f }); setF({ current: '', new: '' }); })}>Parolni o'zgartirish</Btn>
    </Card>
  );
}

function Pairs({ toast }) {
  const { data, reload } = usePoll(() => api('/market/pairs'), 60000);
  const [sym, setSym] = React.useState('');
  const [scan, setScan] = React.useState(null);
  const runScan = async () => {
    try { setScan(await api('/market/universe')); } catch (e) { toast(e.message, 'err'); }
  };
  const toggle = (p) => act(toast, null, async () => { await api('/market/pairs', { body: { symbol: p.symbol, enabled: !p.enabled } }); reload(); });
  return (
    <Card title="Kuzatuv ro'yxati" sub="Bozor ma'lumoti faqat yoqilgan juftliklar uchun sinxronlanadi. Leveraged tokenlar rad etiladi." pad={false}>
      <div style={{ display: 'flex', gap: 8, padding: 12 }}><Input placeholder="ATOM/USDT" value={sym} onChange={(e) => setSym(e.target.value.toUpperCase())} style={{ maxWidth: 200 }} /><Btn disabled={!sym} onClick={() => act(toast, "Qo'shildi", async () => { await api('/market/pairs', { body: { symbol: sym, enabled: true } }); setSym(''); reload(); })}>Qo'shish</Btn><Btn onClick={runScan}>Hajm, spread va filtrlar bo'yicha skanerlash</Btn></div>
      {scan ? <div style={{ padding: '0 12px 12px' }}><Table heads={['Juftlik', 'Natija', 'Sabab', '24s hajm', 'Spread', 'Volatillik']} rows={scan.map((r) => [r.pair, <Pill color={r.eligible ? T.pos : T.neg}>{r.eligible ? 'Mos' : 'Mos emas'}</Pill>, r.reasons.join(', ') || '—', window.QL.fmt.compact(r.quote_volume), r.spread_bps + ' bps', r.volatility_pct + '%'])} /></div> : null}
      <Table heads={['Juftlik', 'Holat', '24s hajm', 'Spread', 'Volatillik', 'Min. buyurtma', '']} rows={(data || []).map((p) => [p.symbol, <Pill color={p.enabled ? T.pos : T.muted}>{p.enabled ? 'Yoqilgan' : "O'chiq"}</Pill>, window.QL.fmt.compact(p.volume), p.spread_bps + ' bps', p.volatility + '%', p.min_notional, <Btn style={{ height: 26 }} onClick={() => toggle(p)}>{p.enabled ? "O'chirish" : 'Yoqish'}</Btn>])} />
    </Card>
  );
}

export default function SettingsLive({ toast }: any) {
  return (
    <Page title="Sozlamalar" sub="Kalitlar, kuzatuv ro'yxati, bildirishnomalar va xavfsizlik.">
      <Credentials toast={toast} />
      <Pairs toast={toast} />
      <Prefs toast={toast} />
      <Password toast={toast} />
    </Page>
  );
}
