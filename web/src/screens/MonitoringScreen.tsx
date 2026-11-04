// @ts-nocheck
'use client';
import React from 'react';
import { api } from '@/lib/api';
import { Card, Grid, Notice, Page, Pill, Select, Stat, T, Table, fmtTs, usePoll } from './ui';

export default function MonitoringScreen() {
  const { data: m, error } = usePoll(() => api('/system/monitor'), 10000);
  const [level, setLevel] = React.useState('');
  const { data: logs } = usePoll(() => api('/system/logs?limit=200' + (level ? '&level=' + level : '')), 15000, [level]);
  const ok = (b) => <Pill color={b ? T.pos : T.neg}>{b ? 'Ishlayapti' : 'Muammo'}</Pill>;
  if (error) return <Page title="Tizim monitoringi"><Notice tone="err">{error}</Notice></Page>;
  if (!m) return <Page title="Tizim monitoringi"><div style={{ color: T.muted }}>Yuklanmoqda…</div></Page>;
  return (
    <Page title="Tizim monitoringi" sub="Server, ishchi jarayonlar va ma'lumot oqimlarining haqiqiy holati.">
      <Grid min={170}>
        <Stat label="CPU" value={m.cpu_pct + '%'} /><Stat label="RAM" value={m.ram_pct + '%'} sub={`${m.ram_used_gb} / ${m.ram_total_gb} GB`} /><Stat label="Disk" value={m.disk_pct + '%'} sub={m.disk_free_gb + ' GB bo\'sh'} color={m.disk_pct > 90 ? T.neg : undefined} />
        <Stat label="Binance" value={m.binance.ok ? m.binance.latency_ms + ' ms' : 'Ulanmagan'} color={m.binance.ok ? T.pos : T.neg} /><Stat label="WebSocket" value={m.websocket.connected ? 'Ulangan' : 'Uzilgan'} color={m.websocket.connected ? T.pos : T.warn} sub={m.websocket.reconnects + ' ta qayta ulanish'} />
        <Stat label="Baza" value={m.database.ok ? 'Sog\'lom' : 'Xato'} color={m.database.ok ? T.pos : T.neg} />
      </Grid>
      <Card title="Ishchi jarayonlar" pad={false}>
        <Table empty="Hech bir worker heartbeat yubormagan: ishchilar ishga tushirilmagan" heads={['Nomi', 'Holat', 'Oxirgi signal', 'Tafsilot']} rows={m.workers.map((w) => [w.name, ok(w.ok), w.age_seconds + ' s oldin', <code>{JSON.stringify(w.detail)}</code>])} />
      </Card>
      <Card title="Ma'lumot to'plamlari" pad={false}>
        <Table empty="Hali ma'lumot yuklanmagan" heads={['Juftlik', 'TF', 'Shamlar', "Bo'shliqlar", 'Birinchi', 'Oxirgi', 'Sinxron', 'Xato']} rows={m.datasets.map((d) => [d.symbol, d.timeframe, d.rows, <span style={{ color: d.gaps ? T.warn : undefined }}>{d.gaps}</span>, fmtTs(d.first_ts), fmtTs(d.last_ts), d.last_sync_at ? window.QL.fmt.dt(Date.parse(d.last_sync_at) / 1000) : '—', d.last_error || '—'])} />
      </Card>
      <Card title="Loglar" right={<Select value={level} style={{ width: 130 }} options={[['', 'Hammasi'], ['ERROR', 'Xatolar'], ['WARNING', 'Ogohlantirish'], ['INFO', 'Info']]} onChange={(e) => setLevel(e.target.value)} />} pad={false}>
        <Table empty="Log yo'q" heads={['Vaqt', 'Daraja', 'Komponent', 'Xabar']} rows={(logs || []).map((l) => [fmtTs(l.at), <Pill color={l.level === 'ERROR' ? T.neg : l.level === 'WARNING' ? T.warn : T.muted}>{l.level}</Pill>, l.component, <span style={{ whiteSpace: 'normal' }}>{l.message}</span>])} />
      </Card>
    </Page>
  );
}
