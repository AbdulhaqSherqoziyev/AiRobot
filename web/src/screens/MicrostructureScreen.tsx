// @ts-nocheck
'use client';
import React from 'react';
import { api } from '@/lib/api';
import { Card, Field, Grid, Input, Notice, Page, Pill, Select, Stat, T, Table, usePoll } from './ui';

const STATE = { ok: ['Yangi', T.pos], stale: ['Eskirgan', T.warn], error: ['Ulanish yo\'q', T.neg] };
const n = (x, d = 2) => (x == null ? '—' : Number(x).toLocaleString('en-US', { maximumFractionDigits: d }));

export default function MicrostructureScreen() {
  const list = usePoll(() => api('/market/pairs'), 300000);
  const pairs = (list.data || []).filter((p) => p.enabled).map((p) => p.symbol);
  const [pair, setPair] = React.useState('BTC/USDT');
  const [notional, setNotional] = React.useState(100);
  const { data, error } = usePoll(() => api(`/market/microstructure?pair=${encodeURIComponent(pair)}&notional=${Number(notional) || 100}`), 5000, [pair, notional]);
  const m = data?.metrics;
  const [label, color] = data ? STATE[data.status] : ['—', T.muted];
  return (
    <Page title="Bozor mikrostrukturasi" sub="Binance Spot ochiq order book'i, faqat o'qish. Bu yerdan buyurtma yuborilmaydi." actions={<Pill color={color}>{label}</Pill>}>
      <Card>
        <Grid min={200}>
          <Field label="Juftlik">{pairs.length ? <Select value={pair} onChange={(e) => setPair(e.target.value)} options={pairs.map((p) => [p, p])} /> : <Input value={pair} onChange={(e) => setPair(e.target.value)} />}</Field>
          <Field label="Baholanadigan hajm, USDT"><Input type="number" min="1" value={notional} onChange={(e) => setNotional(e.target.value)} /></Field>
        </Grid>
      </Card>
      {error ? <Notice tone="err">{error}</Notice> : null}
      {data && data.status !== 'ok' ? <Notice tone={data.status === 'error' ? 'err' : 'warn'}>{data.status === 'error' ? "Ma'lumot olib bo'lmadi: " : "Oxirgi yaxshi ma'lumot ko'rsatilmoqda. Xato: "}{data.error || `ma'lumot ${n(data.age_seconds, 0)} s eski`} ({data.consecutive_failures} ta ketma-ket xato)</Notice> : null}
      {m ? <>
        {m.warnings.map((w) => <Notice key={w.code} tone={w.level}>{w.text}</Notice>)}
        <Grid min={170}>
          <Stat label="Eng yaxshi bid" value={n(m.best_bid, 8)} />
          <Stat label="Eng yaxshi ask" value={n(m.best_ask, 8)} />
          <Stat label="Spread" value={n(m.spread, 8)} sub={`${n(m.spread_pct, 5)}% · ${n(m.spread_bps, 3)} bps`} />
          <Stat label="Yangilik" value={`${n(data.age_seconds, 1)} s`} sub={`So'rov ${n(data.latency_ms, 0)} ms · ${data.source}`} />
          <Stat label={`${n(m.liquidity.notional, 0)} USDT sotib olish`} value={`${n(m.liquidity.buy.slippage_bps, 3)} bps`} sub={m.liquidity.buy.filled ? `O'rtacha ${n(m.liquidity.buy.vwap, 8)}` : "Kitob yetmaydi"} />
          <Stat label={`${n(m.liquidity.notional, 0)} USDT sotish`} value={`${n(m.liquidity.sell.slippage_bps, 3)} bps`} sub={m.liquidity.sell.filled ? `O'rtacha ${n(m.liquidity.sell.vwap, 8)}` : "Kitob yetmaydi"} />
        </Grid>
        <Card title="Chuqurlik" sub={`${m.levels.bids} bid, ${m.levels.asks} ask darajasi. Kitob band ichida tugasa, qiymat quyi chegara sifatida belgilanadi.`} pad={false}>
          <Table heads={['Band', 'Bid, USDT', 'Ask, USDT', 'Nomutanosiblik', "To'liq"]} rows={m.depth.map((d) => [`±${d.bps} bps`, n(d.bid_quote, 0), n(d.ask_quote, 0), n(d.imbalance, 3), d.complete ? 'Ha' : "Yo'q, quyi chegara"])} />
        </Card>
        <Card title="Market-making tekshiruvi" sub="Faqat hisob-kitob. Market-making savdosi tizimda yoqilmagan.">
          <div style={{ fontSize: 13 }}>Spread {n(m.spread_bps, 3)} bps, ikki tomonlama komissiya {n(m.maker_round_trip.fee_bps, 1)} bps: taxminiy natija <b style={{ color: m.maker_round_trip.viable ? T.pos : T.neg }}>{n(m.maker_round_trip.edge_bps, 2)} bps</b> har aylanishga, inventar riski va raqobatdan oldin.</div>
        </Card>
      </> : null}
    </Page>
  );
}
