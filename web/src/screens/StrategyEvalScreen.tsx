// @ts-nocheck
'use client';
import React from 'react';
import { api } from '@/lib/api';
import { eligPill, pctCell } from './ExperimentLab';
import { Card, Grid, Notice, Page, Pill, Stat, T, Table, fmtTs, usePoll } from './ui';

const num = (x, d = 2) => (x == null ? '—' : Number(x).toFixed(d));
const share = (x) => (x == null ? '—' : Math.round(x * 100) + '%');

export default function StrategyEvalScreen() {
  const { data, error } = usePoll(() => api('/strategy-evaluation'), 30000);
  const head = { title: 'Strategiya baholash', sub: "Barcha manbalardagi strategiyalar bir xil mezon bilan. Hech qaysi ustun tartibni belgilamaydi va hech narsa 'foydali' deb yorliqlanmaydi." };
  if (error) return <Page {...head}><Notice tone="err">{error}</Notice></Page>;
  if (!data) return <Page {...head}><div style={{ color: T.muted }}>Yuklanmoqda…</div></Page>;
  const paper = data.paper_report;
  return (
    <Page {...head}>
      <Notice tone="info">Live savdo holati: {data.live}. Quyidagi "Paper nomzodi" faqat paper sinovga kirish shartidir.</Notice>
      <Grid min={170}>
        <Stat label="Yakunlangan tajribalar" value={data.counts.done} />
        <Stat label="Xato bilan tugaganlar" value={data.counts.error} sub="Saqlanadi, yashirilmaydi" />
        <Stat label="Navbatda / ishlayapti" value={data.counts.queued + data.counts.running} />
      </Grid>
      <Card title="Ko'rilmagan davrdagi natijalar" sub="Har strategiya va taymfreym uchun oxirgi tajriba. Asosiy dvigatel, juftliklar medianasi." pad={false}>
        <Table empty="Hali yakunlangan tajriba yo'q" heads={['Strategiya', 'V', 'TF', 'Daromad', 'Pasayish', 'Sharpe', 'PF', 'Savdo', 'WF +', 'Barqarorlik', "Zarar ehtimoli", 'Rejimlar', 'Baho']} rows={data.experiments.map((e) => [e.strategy, e.version, e.timeframe, pctCell(e.test?.total_return), pctCell(e.test?.max_drawdown), num(e.test?.sharpe), num(e.test?.profit_factor), e.test?.total_trades ?? '—', share(e.wf_positive_share), share(e.stability), share(e.monte_carlo?.prob_loss), (e.regimes || []).join(', ') || '—', eligPill(e.eligibility)])} />
      </Card>
      {data.experiments.map((e) => (
        <Card key={e.id} title={`${e.strategy} ${e.timeframe}: mezonlar`} right={eligPill(e.eligibility)} pad={false}>
          <Table heads={['Mezon', 'Qiymat', 'Talab', '']} rows={e.checks.map((c) => [c.name, c.value == null ? '—' : String(c.value), c.need, <Pill color={c.ok ? T.pos : T.neg}>{c.ok ? "O'tdi" : "O'tmadi"}</Pill>])} />
        </Card>
      ))}
      <Card title="30 kunlik paper baholash" sub={paper ? `Hisobot ${fmtTs(paper.created)}${paper.is_final ? ', yakuniy' : ', oraliq'}. "Baholash markazi"dan olingan, bu yerda o'zgartirilmaydi.` : undefined}>
        {paper ? <div style={{ fontSize: 13 }}>{typeof paper.recommendation?.text === 'string' ? paper.recommendation.text : JSON.stringify(paper.recommendation)}</div> : <div style={{ color: T.muted, fontSize: 13 }}>Hali paper hisoboti yo'q.</div>}
      </Card>
    </Page>
  );
}
