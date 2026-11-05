// @ts-nocheck
'use client';
import Strategies from '../generated/Strategies';
import React from 'react';
import { act, api } from '@/lib/api';
import { Btn, Card, Field, Grid, Input, Notice, Select, Table, fmtTs, usePoll } from '../ui';

/** Parameters, pairs and timeframe of a strategy. Saving creates a new immutable version. */
function Editor({ toast }: any) {
  const Q = window.QL;
  const [id, setId] = React.useState(Q.STRATS[0]?.id);
  const st = Q.STRATS.find((x) => x.id === id) || Q.STRATS[0];
  const { data: engines } = usePoll(() => api('/engines'), 600000);
  const { data: versions, reload } = usePoll(() => api(`/strategies/${st.id}/versions`), 30000, [st.id]);
  const [f, setF] = React.useState(null);
  React.useEffect(() => {
    setF({ params: { ...st.params }, pair: st.pair, tf: st.tf, sl: st.sl, tp: st.tp, stake: (st.risk?.stake_pct ?? 0.95) * 100, sizing: st.risk?.sizing?.mode === 'vol_target' ? 'vol' : 'fixed', target: (st.risk?.sizing?.target ?? 0.015) * 100, note: '' });
  }, [st.id, st.versionId]);
  if (!f) return null;
  const eng = engines?.find((e) => e.key === st.engine);
  const save = () => act(toast, 'Yangi versiya saqlandi. Eski natijalar eski versiyaga bog\'liq qoladi.', async () => {
    await api(`/strategies/${st.id}/versions`, { body: { params: f.params, pairs: [f.pair], timeframe: f.tf, note: f.note, risk: { ...st.risk, stoploss_pct: Number(f.sl) / 100, takeprofit_pct: Number(f.tp) / 100, stake_pct: Number(f.stake) / 100, sizing: f.sizing === 'vol' ? { mode: 'vol_target', target: Number(f.target) / 100 } : null } } });
    reload();
  });
  return (
    <div style={{ marginTop: 16 }}>
      <Card title="Strategiyani tahrirlash va versiyalar" sub="Har bir saqlash yangi versiya yaratadi: faol sessiyalar o'z versiyasida qoladi.">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Grid min={160}>
            <Field label="Strategiya"><Select value={st.id} options={Q.STRATS.map((x) => [x.id, x.name])} onChange={(e) => setId(e.target.value)} /></Field>
            <Field label="Juftlik"><Select value={f.pair} options={Q.MARKETS.map((m) => m.sym)} onChange={(e) => setF({ ...f, pair: e.target.value })} /></Field>
            <Field label="Taymfreym"><Select value={f.tf} options={['1m', '5m', '15m', '30m', '1h', '4h', '1d']} onChange={(e) => setF({ ...f, tf: e.target.value })} /></Field>
            <Field label="Stop-loss, %"><Input type="number" step="0.1" value={f.sl} onChange={(e) => setF({ ...f, sl: e.target.value })} /></Field>
            <Field label="Take-profit, %"><Input type="number" step="0.1" value={f.tp} onChange={(e) => setF({ ...f, tp: e.target.value })} /></Field>
            <Field label="Hajm usuli"><Select value={f.sizing} options={[['vol', "Volatillik bo'yicha"], ['fixed', "Qat'iy foiz"]]} onChange={(e) => setF({ ...f, sizing: e.target.value })} /></Field>
            {f.sizing === 'vol' ? <Field label="Kunlik volatillik maqsadi, %" hint="Tadqiqotda 1,5%"><Input type="number" step="0.1" value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} /></Field> : null}
            <Field label={f.sizing === 'vol' ? 'Maks. pozitsiya, % balans' : 'Pozitsiya, % balans'}><Input type="number" value={f.stake} onChange={(e) => setF({ ...f, stake: e.target.value })} /></Field>
            {eng ? Object.entries(eng.params).map(([k, p]) => (
              <Field key={k} label={k} hint={`${p.low} … ${p.high}`}><Input type="number" step={p.step} value={f.params[k] ?? p.default} onChange={(e) => setF({ ...f, params: { ...f.params, [k]: Number(e.target.value) } })} /></Field>
            )) : null}
          </Grid>
          {st.engine === 'rule_builder' ? <Notice tone="info">Qoidalar Strategiya konstruktorida tahrirlanadi.</Notice> : null}
          <div style={{ display: 'flex', gap: 8 }}><Input placeholder="Izoh (ixtiyoriy)" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /><Btn tone="primary" onClick={save}>Yangi versiya sifatida saqlash</Btn></div>
          <Table empty="Versiya yo'q" heads={['Versiya', 'Vaqt', 'Juftlik', 'TF', 'Parametrlar', 'Izoh', '']} rows={(versions || []).slice().reverse().map((v) => ['v' + v.version, fmtTs(v.created), (v.pairs || []).join(', '), v.timeframe, <code>{Object.entries(v.params).filter(([k]) => k !== 'rules' && k !== 'model_path').map(([k, x]) => `${k}=${x}`).join(' ')}</code>, v.note || '—', v.current ? 'Joriy' : ''])} />
        </div>
      </Card>
    </div>
  );
}

export default class StrategiesLive extends Strategies {
  componentDidMount() {
    super.componentDidMount();
    this.onData = () => { if (this.state.list) this.setState({ list: window.QL.STRATS.map((s) => ({ ...s })) }); };
    window.addEventListener('ql-data', this.onData);
  }
  componentWillUnmount() {
    super.componentWillUnmount();
    window.removeEventListener('ql-data', this.onData);
  }
  render() {
    return (
      <>
        {super.render()}
        {this.state.ready ? <Editor toast={this.props.toast} /> : null}
      </>
    );
  }
  setStatus(id, status) {
    if (status === 'paused') status = 'inactive';
    act(this.props.toast, null, () => api('/strategies/' + id, { method: 'PATCH', body: { enabled: status === 'active' } }));
  }
  duplicate(x) {
    act(this.props.toast, '“' + x.name + '” nusxalandi', () => api(`/strategies/${x.id}/clone`, { method: 'POST' }));
  }
  remove(x) {
    this.props.confirm({
      danger: true, title: "Strategiyani o'chirasizmi?", okLabel: "O'chirish",
      text: '“' + x.name + "” o'chiriladi. Tarixda ishlatilgan strategiyani o'chirib bo'lmaydi: uni nofaol qiling.",
      onOk: () => act(this.props.toast, '“' + x.name + "” o'chirildi", () => api('/strategies/' + x.id, { method: 'DELETE' })),
    });
  }
}
