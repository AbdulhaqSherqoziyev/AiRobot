// @ts-nocheck
'use client';
import React from 'react';
import { act, api } from '@/lib/api';
import { Btn, Card, Grid, Notice, Page, Pill, T, Table, fmtTs, usePoll } from './ui';

const HEALTH = { ok: ['Ishlaydi', T.pos], degraded: ['Qisman', T.warn], missing: ["O'rnatilmagan", T.warn] };

export default function IntegrationsHub({ toast }: any) {
  const { data, error, reload } = usePoll(() => api('/integrations'), 20000);
  const [open, setOpen] = React.useState(null);
  const head = { title: 'Tadqiqot integratsiyalari', sub: "Tashqi loyihalardan nima olingani va hozirgi holati. Birortasi ham buyurtma yubora olmaydi." };
  if (error) return <Page {...head}><Notice tone="err">{error}</Notice></Page>;
  if (!data) return <Page {...head}><div style={{ color: T.muted }}>Yuklanmoqda…</div></Page>;
  const flip = async (r) => { await act(toast, r.enabled ? "O'chirildi" : 'Yoqildi', () => api('/integrations/' + r.key, { body: { enabled: !r.enabled } })); reload(); };
  return (
    <Page {...head}>
      <Grid min={320}>
        {data.map((r) => {
          const [label, color] = HEALTH[r.health.state] || [r.health.state, T.muted];
          return (
            <Card key={r.key} title={r.name} sub={r.upstream} right={<Pill color={r.enabled ? color : T.dim}>{r.enabled ? label : "O'chiq"}</Pill>}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13 }}>
                <div>{r.provides}</div>
                <Row k="Tekshirilgan versiya" v={r.audited} />
                <Row k="O'rnatilgan" v={r.health.installed || 'Kutubxona sifatida emas'} />
                <Row k="Litsenziya" v={r.license} />
                <Row k="Ulanish usuli" v={r.mode} />
                <Row k="Oxirgi muvaffaqiyatli ish" v={fmtTs(r.last_success)} />
                <div style={{ color: T.muted }}>{r.health.text}</div>
                <div style={{ color: T.dim, fontSize: 12 }}>{r.obligation}</div>
                {r.last_error ? <Notice tone="err">{fmtTs(r.last_error.at)}: {r.last_error.text}</Notice> : null}
                <div style={{ display: 'flex', gap: 8 }}>
                  <Btn onClick={() => flip(r)}>{r.enabled ? "O'chirish" : 'Yoqish'}</Btn>
                  <Btn onClick={() => setOpen(open === r.key ? null : r.key)}>Loglar ({r.logs.length})</Btn>
                </div>
              </div>
            </Card>
          );
        })}
      </Grid>
      {open ? <Card title={'Loglar: ' + open} pad={false}><Table empty="Log yo'q" heads={['Vaqt', 'Daraja', 'Xabar']} rows={data.find((r) => r.key === open).logs.map((l) => [fmtTs(l.at), l.level, l.message])} /></Card> : null}
      <JesseCompat />
    </Page>
  );
}

function Row({ k, v }: any) {
  return <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span style={{ color: T.muted }}>{k}</span><span style={{ textAlign: 'right' }}>{v}</span></div>;
}

function JesseCompat() {
  const { data, error } = usePoll(() => api('/jesse/compatibility'), 300000);
  if (error || !data) return null;
  return (
    <Card title="Jesse moslik hisoboti" sub={`Jesse ${data.jesse_version}, ${data.mode}`}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontSize: 13 }}>
        <div>Indikatorlar: {data.indicators.supported_count} / {data.indicators.jesse_total} ({Object.keys(data.indicators.supported).join(', ')}). Taymfreymlar: {data.timeframes.supported.join(', ')}.</div>
        <Table heads={['Mavzu', 'Jesse', 'Quant Lab']} rows={data.execution_differences.map((d) => [d.topic, d.jesse, d.quantlab])} />
        <div><b>Buyurtma turlari:</b> {Object.entries(data.order_types).map(([k, v]) => `${k}: ${v}`).join('; ')}</div>
        <div style={{ color: T.muted }}><b>Ko'chmaydigan xususiyatlar:</b> {data.unsupported_features.join('; ')}</div>
      </div>
    </Card>
  );
}
