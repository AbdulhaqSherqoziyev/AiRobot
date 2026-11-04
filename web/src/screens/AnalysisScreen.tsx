// @ts-nocheck
'use client';
import React from 'react';
import { act, api } from '@/lib/api';
import { Btn, Card, Grid, Notice, Page, Pill, Stat, T, Table, fmtTs, usePoll } from './ui';

const VERDICT = { umidli: ['Umidli', T.pos], zararli: ['Zararli', T.neg], noaniq: ['Noaniq', T.warn], namuna_kam: ['Namuna kam', T.muted] };

export default function AnalysisScreen({ toast }: any) {
  const { data, error, reload } = usePoll(() => api('/analysis'), 30000);
  const f = window.QL.fmt;
  const pct = (x) => (x == null ? '—' : <span style={{ color: f.tone(x) }}>{f.pct(x)}</span>);
  const run = () => act(toast, 'Tahlil navbatga qo\'shildi', () => api('/analysis/run', { method: 'POST' }));
  const head = { title: 'Kunlik tahlil', sub: "Virtual sessiyalar real narxda nima qilayotganini kuzatadi. Tizim faqat tavsiya beradi: hech narsani o'zi o'zgartirmaydi.", actions: <Btn onClick={run}>Hozir tahlil qilish</Btn> };
  if (error) return <Page {...head}><Notice tone="err">{error}</Notice></Page>;
  if (!data) return <Page {...head}><div style={{ color: T.muted }}>Yuklanmoqda…</div></Page>;
  const r = data.report;
  if (!r) return <Page {...head}><Notice tone="info">Hali tahlil yo'q. U kuniga bir marta avtomatik yaratiladi.</Notice></Page>;
  return (
    <Page {...head}>
      <Notice>{r.summary.live_recommendation}</Notice>
      <Grid min={170}>
        <Stat label="Sessiyalar" value={r.summary.sessions} sub={`${r.summary.active} faol · ${r.summary.halted} risk to'xtatgan`} />
        <Stat label="Yopiq savdolar" value={r.summary.closed_trades} />
        <Stat label="Umidli guruhlar" value={r.summary.promising} sub="Ishonch chegarasidan o'tganlar" color={r.summary.promising ? T.pos : undefined} />
        <Stat label="Hisobot vaqti" value={fmtTs(r.created)} />
      </Grid>
      <Card title="Xulosalar">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{r.findings.map((x, i) => <Notice key={i} tone={x.tone}>{x.text}</Notice>)}</div>
      </Card>
      <Card title="Strategiyalar real natijasi" sub="Guruh: strategiya va taymfreym, barcha juftliklar bo'yicha" pad={false}>
        <Table empty="Hali natija yo'q" heads={['Strategiya', 'TF', 'Sessiya', 'Savdo', 'Median daromad', 'Buy&Hold', 'Eng katta DD', 'PF', "G'alaba", 't', 'Komissiya', 'Xulosa']} rows={r.strategies.map((x) => [x.strategy, x.timeframe, x.sessions, x.trades, pct(x.median_return), pct(x.median_buy_hold), pct(x.worst_drawdown), x.profit_factor ?? '—', x.win_rate != null ? x.win_rate + '%' : '—', x.t_stat ?? '—', f.usd(x.fees), <Pill color={VERDICT[x.verdict][1]}>{VERDICT[x.verdict][0]}</Pill>])} />
      </Card>
      <Card title="ML modellar sifati" sub="Model o'qitilgandan keyin kelgan real ma'lumotdagi natija. 50 ta namunadan oldin baho chiqmaydi." pad={false}>
        <Table empty="Sinovda model yo'q" heads={['Model', 'Versiya', 'Holat', 'Validatsiya AUC', "O'qitish OOS AUC", 'Yangi namuna', 'Yangi AUC', 'Izoh']} rows={r.models.map((m) => [m.model, 'v' + m.version, m.status, m.validation_auc ?? '—', m.training_oos_auc ?? '—', m.forward_samples, m.forward_auc ?? '—', m.note || '—'])} />
      </Card>
      <Card title="Bozor holati" pad={false}>
        <Table heads={['Juftlik', 'Rejim', '30 kun', 'Kunlik volatillik']} rows={r.market.map((m) => [m.pair, m.regime, pct(m.return_30d), m.daily_vol + '%'])} />
      </Card>
    </Page>
  );
}
