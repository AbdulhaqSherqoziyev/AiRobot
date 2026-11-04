// @ts-nocheck
'use client';
import React from 'react';
import { act, api } from '@/lib/api';
import { Btn, Card, Field, Grid, Input, Notice, Page, Pill, Select, Stat, T, Table, fmtTs, usePoll } from './ui';

function Countdown({ run }) {
  const [now, setNow] = React.useState(Math.floor(Date.now() / 1000));
  React.useEffect(() => { const t = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000); return () => clearInterval(t); }, []);
  const left = run.ends - now, total = run.ends - run.started, done = Math.min(100, ((now - run.started) / total) * 100);
  return (
    <Card title={left > 0 ? `Qolgan vaqt: ${window.QL.fmt.clock(left)}` : 'Baholash muddati tugadi'} sub={`${fmtTs(run.started)} – ${fmtTs(run.ends)} · ${run.duration_days} kun`} right={<Pill color={run.status === 'running' ? T.warn : T.pos}>{run.status === 'running' ? 'Sinovda' : 'Yakunlangan'}</Pill>}>
      <div style={{ height: 8, background: '#0F1522', borderRadius: 99, overflow: 'hidden' }}><div style={{ width: done + '%', height: '100%', background: T.accent }} /></div>
    </Card>
  );
}

function Approval({ ev, toast, reload }) {
  const rec = ev.report.recommendation;
  const eligible = ev.report.rows.filter((r) => r.eligible);
  const [f, setF] = React.useState({ strategy_version_id: rec.strategy_version_id || eligible[0]?.strategy_version_id, pair: rec.pair || eligible[0]?.pair, max_capital: 100, max_position: 50, daily_loss_limit: 5, max_drawdown_pct: 10, fee_assumption: 0.001, max_orders_per_hour: 4, max_trade_risk_pct: 5, confirmation: '', password: '' });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const row = eligible.find((r) => r.strategy_version_id === Number(f.strategy_version_id));
  const submit = () => act(toast, 'Tasdiq saqlandi. Savdo hali boshlanmadi: Live markazidan alohida ishga tushiriladi.', async () => {
    await api('/live/authorize', { body: { environment: 'live', report_id: ev.report.id, strategy_version_id: Number(f.strategy_version_id), pairs: [row?.pair || f.pair], max_capital: Number(f.max_capital), max_position: Number(f.max_position), daily_loss_limit: Number(f.daily_loss_limit), max_drawdown_pct: Number(f.max_drawdown_pct), fee_assumption: Number(f.fee_assumption), stop_conditions: { max_orders_per_hour: Number(f.max_orders_per_hour), max_trade_risk_pct: Number(f.max_trade_risk_pct) }, confirmation: f.confirmation, password: f.password } });
    reload();
  });
  return (
    <Card title="Real savdoga ruxsat" sub="Faqat egasi tasdiqlaydi. Muddat o'tishi hech qachon real savdoni yoqmaydi." style={{ borderColor: '#DC2F3A' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Notice tone="err">Bu haqiqiy pul. Yo'qotishingiz mumkin. Mezonlardan o'tish kelajakdagi foydani kafolatlamaydi. Bu tavsiya moliyaviy maslahat emas.</Notice>
        <ul style={{ margin: 0, paddingLeft: 18, color: T.muted, fontSize: 13, lineHeight: '20px' }}>{(rec.limitations || []).map((l) => <li key={l}>{l}</li>)}</ul>
        <Grid min={170}>
          <Field label="Tasdiqlangan strategiya"><Select value={f.strategy_version_id} options={eligible.map((r) => [r.strategy_version_id, `${r.strategy} · ${r.pair}`])} onChange={set('strategy_version_id')} /></Field>
          <Field label="Maks. kapital, USDT" hint={`Yuqori chegara ${ev.hard_cap}`}><Input type="number" value={f.max_capital} onChange={set('max_capital')} /></Field>
          <Field label="Maks. pozitsiya, USDT"><Input type="number" value={f.max_position} onChange={set('max_position')} /></Field>
          <Field label="Kunlik zarar chegarasi, USDT"><Input type="number" value={f.daily_loss_limit} onChange={set('daily_loss_limit')} /></Field>
          <Field label="Maks. pasayish, %"><Input type="number" value={f.max_drawdown_pct} onChange={set('max_drawdown_pct')} /></Field>
          <Field label="Komissiya farazi"><Input type="number" step="0.0001" value={f.fee_assumption} onChange={set('fee_assumption')} /></Field>
          <Field label="Soatiga maks. buyurtma"><Input type="number" value={f.max_orders_per_hour} onChange={set('max_orders_per_hour')} /></Field>
          <Field label="Savdo boshiga risk, %"><Input type="number" value={f.max_trade_risk_pct} onChange={set('max_trade_risk_pct')} /></Field>
        </Grid>
        <Field label={`Tasdiqlash uchun aynan yozing: ${ev.confirmation}`}><Input value={f.confirmation} onChange={set('confirmation')} autoComplete="off" /></Field>
        <Field label="Parolingiz"><Input type="password" value={f.password} onChange={set('password')} autoComplete="current-password" /></Field>
        <Btn tone="danger" disabled={f.confirmation !== ev.confirmation || !f.password} onClick={submit}>Real savdoga ruxsat berish</Btn>
      </div>
    </Card>
  );
}

export default function EvaluationScreen({ toast, nav }: any) {
  const { data: ev, error, reload } = usePoll(() => api('/evaluation'), 20000);
  if (error) return <Page title="Baholash markazi"><Notice tone="err">{error}</Notice></Page>;
  if (!ev) return <Page title="Baholash markazi"><div style={{ color: T.muted }}>Yuklanmoqda…</div></Page>;
  const f = window.QL.fmt, c = ev.run?.criteria || ev.default_criteria, rep = ev.report;
  const pct = (x) => (x == null ? '—' : <span style={{ color: f.tone(x) }}>{f.pct(x)}</span>);
  const start = () => act(toast, 'Baholash boshlandi', async () => { await api('/evaluation/start', { body: {} }); reload(); });
  return (
    <Page title="Baholash markazi" sub="30 kunlik paper sinov. Mezonlar boshida qotiriladi va keyin o'zgarmaydi."
      actions={ev.run ? <Btn onClick={() => act(toast, 'Hisobot yaratildi', async () => { await api('/evaluation/report', { method: 'POST' }); reload(); })}>Hisobot yaratish</Btn> : <Btn tone="primary" onClick={start}>30 kunlik sinovni boshlash</Btn>}>
      {ev.run ? <Countdown run={ev.run} /> : <Notice tone="info">Sinov hali boshlanmagan. Boshlaganda har bir faol strategiya uchun 100 USDT virtual kapitalli alohida sessiya ochiladi. Modeli yo'q ML strategiyalar qo'shilmaydi.</Notice>}
      <Card title="Skrining mezonlari" sub="Bu boshlang'ich filtr, kelajakdagi foydaning isboti emas.">
        <Grid min={170}>
          <Stat label="Min. muddat" value={c.min_days + ' kun'} /><Stat label="Min. savdolar" value={c.min_trades} /><Stat label="Profit factor" value={'> ' + c.min_profit_factor} /><Stat label="Maks. pasayish" value={'< ' + c.max_drawdown_pct + '%'} /><Stat label="Kritik hodisalar" value={'≤ ' + c.max_critical_events} />
        </Grid>
      </Card>
      {rep ? (
        <>
          <Notice tone={rep.recommendation.action === 'review' ? 'ok' : 'warn'}><b>{rep.is_final ? 'Yakuniy hisobot' : 'Oraliq hisobot'} ({fmtTs(rep.created)}):</b> {rep.recommendation.text}</Notice>
          <Card title="Strategiyalar solishtiruvi" pad={false}>
            <Table heads={['Strategiya', 'Juftlik', 'Kun', 'Daromad', 'Buy&Hold', 'Sof foyda', 'PF', 'Max DD', 'Sharpe', 'Sortino', "G'alaba", 'Savdo', 'Komissiya ulushi', 'Barqarorlik', 'OOS', 'Natija']} rows={rep.rows.map((r) => [r.strategy, r.pair, r.days, pct(r.metrics.total_return), pct(r.benchmark_return), f.usd(r.metrics.net_profit), r.metrics.profit_factor?.toFixed(2) ?? '—', pct(r.metrics.max_drawdown), r.metrics.sharpe?.toFixed(2) ?? '—', r.metrics.sortino?.toFixed(2) ?? '—', r.metrics.win_rate != null ? r.metrics.win_rate.toFixed(1) + '%' : '—', r.metrics.total_trades, r.fee_impact_pct != null ? r.fee_impact_pct + '%' : '—', r.consistency != null ? r.consistency + '%' : '—', pct(r.out_of_sample?.total_return), <span title={r.fails.join('; ')}><Pill color={r.eligible ? T.pos : r.insufficient_sample ? T.warn : T.neg}>{r.eligible ? "O'tdi" : r.insufficient_sample ? 'Namuna kam' : "O'tmadi"}</Pill></span>])} />
          </Card>
          {rep.is_final && rep.rows.some((r) => r.eligible) && !ev.authorization ? <Approval ev={ev} toast={toast} reload={reload} /> : null}
          {rep.is_final && !rep.rows.some((r) => r.eligible) ? <Notice tone="err">Hech bir strategiya o'tmadi, shuning uchun real savdoga ruxsat berib bo'lmaydi.</Notice> : null}
          {!rep.is_final ? <Notice tone="info">Real savdo tasdig'i faqat yakuniy hisobotdan keyin ochiladi.</Notice> : null}
        </>
      ) : null}
      {ev.authorization ? <Notice tone="warn">Faol tasdiq mavjud (#{ev.authorization.id}). Boshqaruv Live markazida. <a onClick={() => nav('live')} style={{ cursor: 'pointer' }}>Ochish</a></Notice> : null}
    </Page>
  );
}
