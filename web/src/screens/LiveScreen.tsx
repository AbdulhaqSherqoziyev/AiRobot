// @ts-nocheck
'use client';
import React from 'react';
import { act, api } from '@/lib/api';
import { Btn, Card, Field, Grid, Input, Notice, Page, Pill, Select, Stat, T, Table, fmtTs, usePoll } from './ui';

const ENVS = { live: { label: 'REAL PUL', color: '#DC2F3A' }, testnet: { label: 'TESTNET · soxta pul', color: '#C084FC' } };

function TestnetAuth({ toast, reload }) {
  const Q = window.QL;
  const list = Q.STRATS.filter((s) => s.status === 'active');
  const [f, setF] = React.useState({ id: list[0]?.id, max_capital: 100, max_position: 50, daily_loss_limit: 5, max_drawdown_pct: 10, password: '' });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const st = list.find((s) => s.id === String(f.id));
  return (
    <Card title="Testnet ruxsati" sub="Testnet soxta pul ishlatadi va faqat buyurtma oqimini sinash uchun. Baholash talab qilinmaydi.">
      <Grid min={160}>
        <Field label="Strategiya"><Select value={f.id} options={list.map((s) => [s.id, `${s.name} · ${s.pair}`])} onChange={set('id')} /></Field>
        <Field label="Maks. kapital"><Input type="number" value={f.max_capital} onChange={set('max_capital')} /></Field>
        <Field label="Maks. pozitsiya"><Input type="number" value={f.max_position} onChange={set('max_position')} /></Field>
        <Field label="Kunlik zarar chegarasi"><Input type="number" value={f.daily_loss_limit} onChange={set('daily_loss_limit')} /></Field>
        <Field label="Maks. pasayish, %"><Input type="number" value={f.max_drawdown_pct} onChange={set('max_drawdown_pct')} /></Field>
        <Field label="Parol"><Input type="password" value={f.password} onChange={set('password')} /></Field>
      </Grid>
      <Btn tone="primary" style={{ marginTop: 12 }} disabled={!st || !f.password} onClick={() => act(toast, 'Testnet ruxsati saqlandi', async () => { await api('/live/authorize', { body: { environment: 'testnet', strategy_version_id: st.versionId, pairs: [st.pair], max_capital: Number(f.max_capital), max_position: Number(f.max_position), daily_loss_limit: Number(f.daily_loss_limit), max_drawdown_pct: Number(f.max_drawdown_pct), confirmation: 'TESTNET', password: f.password } }); reload(); })}>Testnetga ruxsat berish</Btn>
    </Card>
  );
}

export default function LiveScreen({ toast, confirm, nav }: any) {
  const [env, setEnv] = React.useState('live');
  const { data: d, error, reload } = usePoll(() => api('/live/status?environment=' + env), 5000, [env]);
  const { data: bal } = usePoll(() => api('/live/balance?environment=' + env), 30000, [env]);
  const [password, setPassword] = React.useState('');
  if (error) return <Page title="Live savdo markazi"><Notice tone="err">{error}</Notice></Page>;
  if (!d || d.environment !== env) return <Page title="Live savdo markazi"><div style={{ color: T.muted }}>Yuklanmoqda…</div></Page>;
  const Q = window.QL, f = Q.fmt, E = ENVS[env], usdt = bal?.balances?.find((b) => b.asset === 'USDT');
  const open = d.gate_reasons.length === 0;
  const kill = () => confirm({ danger: true, title: 'FAVQULODDA TOʻXTATISH', okLabel: "To'xtatish va pozitsiyani yopish", text: "Yangi buyurtmalar darhol bloklanadi va ochiq pozitsiya bozor narxida sotiladi.", onOk: () => act(toast, null, async () => { const r = await api('/live/kill', { body: { environment: env } }); toast(r.closed ? "To'xtatildi, pozitsiya yopildi" : r.error ? 'Bloklandi, lekin pozitsiyani yopib bo\'lmadi: Binance\'ni tekshiring' : "To'xtatildi", r.error ? 'err' : 'warn'); reload(); }) });
  const start = () => confirm({ danger: env === 'live', title: env === 'live' ? 'REAL PUL bilan savdoni boshlaysizmi?' : 'Testnetni boshlaysizmi?', okLabel: 'Boshlash', text: env === 'live' ? `Strategiya haqiqiy buyurtmalar yuboradi. Kapital chegarasi ${d.authorization?.max_capital} USDT. Yo'qotish mumkin.` : 'Binance Testnetga buyurtma yuboriladi.', onOk: () => act(toast, 'Boshlandi', async () => { await api('/live/start', { body: { environment: env, password } }); setPassword(''); reload(); }) });
  return (
    <Page title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>Live savdo markazi <span style={{ background: E.color, color: '#fff', fontSize: 12, padding: '3px 10px', borderRadius: 6 }}>{E.label}</span></span>} sub="Paper tizimidan to'liq ajratilgan. Har bir buyurtma risk qoidalaridan o'tadi."
      actions={<div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Select value={env} style={{ width: 150 }} options={[['live', 'Real pul'], ['testnet', 'Testnet']]} onChange={(e) => setEnv(e.target.value)} /><Btn tone="danger" onClick={kill} style={{ height: 40, fontSize: 14, padding: '0 18px' }}>FAVQULODDA TO'XTATISH</Btn></div>}>
      {d.status === 'halted' ? <Notice tone="err"><b>To'xtatilgan:</b> {d.halt_reason}. Yangi buyurtmalar bloklangan; davom ettirish tasdig'ingizni talab qiladi.</Notice> : null}
      {!open ? <Notice tone="warn"><b>Savdo yopiq.</b> Sabablar: {d.gate_reasons.join('; ')}.</Notice> : null}
      <Grid min={170}>
        <Stat label="Holat" value={d.status === 'running' ? 'Ishlamoqda' : d.status === 'halted' ? "To'xtatilgan" : "O'chiq"} color={d.status === 'running' ? T.pos : d.status === 'halted' ? T.neg : T.muted} />
        <Stat label="Mavjud USDT" value={usdt ? f.usd(Number(usdt.free)) : bal?.connected === false ? 'Ulanmagan' : '…'} sub={bal?.error} />
        <Stat label="Realizatsiya PnL" value={f.susd(d.realized)} color={f.tone(d.realized)} />
        <Stat label="Ochiq PnL" value={d.unrealized != null ? f.susd(d.unrealized) : '—'} />
        <Stat label="Kapital chegarasi" value={d.authorization ? f.usd(d.authorization.max_capital) : '—'} sub={d.authorization ? `Pozitsiya ${d.authorization.max_position} · kunlik ${d.authorization.daily_loss_limit} · DD ${d.authorization.max_drawdown_pct}%` : null} />
      </Grid>
      {env === 'testnet' && !d.authorization ? <TestnetAuth toast={toast} reload={reload} /> : null}
      {env === 'live' && !d.authorization ? <Notice tone="info">Real savdo 30 kunlik baholashdan va sizning tasdig'ingizdan keyingina ochiladi. <a onClick={() => nav('evaluation')} style={{ cursor: 'pointer' }}>Baholash markazi</a></Notice> : null}
      {d.authorization ? (
        <Card title="Boshqaruv" sub={`Juftlik ${d.authorization.pairs.join(', ')} · tasdiq ${fmtTs(d.authorization.created)}`}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
            {env === 'live' ? <div style={{ width: 220 }}><Field label="Parol (boshlash uchun)"><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field></div> : null}
            {d.status !== 'running' ? <Btn tone={env === 'live' ? 'danger' : 'primary'} disabled={!open || (env === 'live' && !password)} onClick={start}>{d.status === 'halted' ? 'Davom ettirish' : 'Boshlash'}</Btn> : null}
            {d.status === 'running' ? <Btn onClick={() => act(toast, "To'xtatildi. Ochiq pozitsiya saqlanadi", async () => { await api('/live/stop', { body: { environment: env } }); reload(); })}>Yumshoq to'xtatish</Btn> : null}
            <Btn onClick={() => act(toast, 'Tasdiq bekor qilindi', async () => { await api('/live/revoke', { body: { environment: env } }); reload(); })}>Tasdiqni bekor qilish</Btn>
          </div>
        </Card>
      ) : null}
      <Grid min={380}>
        <Card title="Ochiq pozitsiya" pad={false}><Table empty="Ochiq pozitsiya yo'q" heads={['Juftlik', 'Miqdor', 'Kirish', 'Vaqt']} rows={d.position ? [[d.position.symbol, d.position.qty, f.price(d.position.entry), fmtTs(d.position.t)]] : []} /></Card>
        <Card title="Buyurtmalar" pad={false}><Table empty="Buyurtma yo'q" heads={['Vaqt', 'Juftlik', 'Tomon', 'Holat', 'Xato']} rows={d.orders.map((o) => [fmtTs(o.created), o.symbol, o.side, o.status, o.error || '—'])} /></Card>
        <Card title="Savdolar" pad={false}><Table empty="Savdo yo'q" heads={['Kirish', 'Chiqish', 'Juftlik', 'PnL', 'Sabab']} rows={d.trades.map((t) => [fmtTs(t.entry_ts), fmtTs(t.exit_ts), t.symbol, f.susd(t.pnl), t.reason || '—'])} /></Card>
        <Card title="Risk hodisalari" pad={false}><Table empty="Hodisa yo'q" heads={['Vaqt', 'Qoida', 'Tafsilot']} rows={d.risk_events.map((e) => [fmtTs(e.at), e.rule, e.detail])} /></Card>
      </Grid>
    </Page>
  );
}
