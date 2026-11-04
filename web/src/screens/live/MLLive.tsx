// @ts-nocheck
'use client';
import React from 'react';
import MLLab from '../generated/MLLab';
import { act, api } from '@/lib/api';
import { Btn, Card, Field, Grid, Input, Notice, Select } from '../ui';

const ALGOS = [['lightgbm', 'LightGBM'], ['xgboost', 'XGBoost'], ['random_forest', 'Random Forest (baseline)'], ['lstm', 'LSTM (tajribaviy)'], ['rl', 'RL Q-learning (tajribaviy)']];
const ENGINE = { lightgbm: 'ml_lightgbm', xgboost: 'ml_xgboost', random_forest: 'ml_random_forest', lstm: 'ml_lstm', rl: 'ml_rl' };

function Controls({ toast, sel, selectModel }: any) {
  const Q = window.QL;
  const [f, setF] = React.useState({ algo: 'lightgbm', pair: 'BTC/USDT', timeframe: '4h', horizon: 6 });
  const m = Q.MODELS.find((x) => x.id === sel) || Q.MODELS[0];
  const engine = m && Q.STRATS.find((s) => s.engine === ENGINE[m.algo]);
  return (
    <Card title="Modelni o'qitish va boshqarish" sub="Yangi model faqat nomzod bo'ladi. U hech qachon faol strategiyani o'zi almashtirmaydi.">
      <Grid min={150}>
        <Field label="Algoritm"><Select value={f.algo} options={ALGOS} onChange={(e) => setF({ ...f, algo: e.target.value })} /></Field>
        <Field label="Juftlik"><Select value={f.pair} options={Q.MARKETS.map((x) => x.sym)} onChange={(e) => setF({ ...f, pair: e.target.value })} /></Field>
        <Field label="Taymfreym"><Select value={f.timeframe} options={['15m', '30m', '1h', '4h', '1d']} onChange={(e) => setF({ ...f, timeframe: e.target.value })} /></Field>
        <Field label="Gorizont (sham)"><Input type="number" min="1" max="100" value={f.horizon} onChange={(e) => setF({ ...f, horizon: e.target.value })} /></Field>
        <div style={{ display: 'flex', alignItems: 'flex-end' }}><Btn tone="primary" style={{ width: '100%' }} onClick={() => act(toast, "O'qitish navbatga qo'shildi", () => api('/ml/train', { body: { ...f, horizon: Number(f.horizon) } }))}>O'qitishni boshlash</Btn></div>
      </Grid>
      {m ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginTop: 14, fontSize: 13, color: '#CBD5E1' }}>
          <span>Tanlangan: <b>{m.name} {m.ver}</b> · OOS savdo {m.trading?.total_return != null ? Q.fmt.pct(m.trading.total_return) : '—'} · buy&amp;hold {m.buyHold != null ? Q.fmt.pct(m.buyHold) : '—'}</span>
          <Select value={m.id} style={{ width: 240 }} options={Q.MODELS.map((x) => [x.id, x.name + ' ' + x.ver])} onChange={(e) => selectModel(e.target.value)} />
          {m.status !== 'prod' ? <Btn onClick={() => act(toast, 'Model tasdiqlandi', () => api(`/ml/versions/${m.dbId}/promote`, { method: 'POST' }))}>Tasdiqlash (promote)</Btn> : null}
          {m.status === 'prod' && engine ? <Btn onClick={() => act(toast, `${engine.name} yangi versiyasi shu modelga bog'landi`, () => api(`/ml/versions/${m.dbId}/attach/${engine.id}`, { method: 'POST' }))}>{engine.name} strategiyasiga bog'lash</Btn> : null}
        </div>
      ) : <div style={{ marginTop: 14 }}><Notice tone="info">Hali model yo'q. Birinchi modelni o'qiting.</Notice></div>}
    </Card>
  );
}

export default class MLLive extends MLLab {
  componentDidMount() {
    super.componentDidMount();
    clearInterval(this._p);
    this.onData = () => { this.setState({ jobs: window.QL.JOBS.map((j) => ({ ...j })) }); };
    window.addEventListener('ql-data', this.onData);
  }
  componentWillUnmount() {
    super.componentWillUnmount();
    window.removeEventListener('ql-data', this.onData);
  }
  renderVals() {
    if (!window.QL.MODELS.length) return { v: { loading: false, ok: false, error: false, empty: true }, newJob: () => {}, retry: () => {} };
    const s = this.state, Q = window.QL;
    if (!Q.MODELS.some((m) => m.id === s.sel)) this.state.sel = Q.MODELS[0].id;
    const v = super.renderVals();
    if (v.jobs) v.jobs = v.jobs.map((j, i) => ({ ...j, cancel: () => act(this.props.toast, "O'qitish bekor qilindi", () => api(`/jobs/${s.jobs[i].dbId}/cancel`, { method: 'POST' })) }));
    return v;
  }
  render() {
    return (
      <>
        <div style={{ marginBottom: 16 }}><Controls toast={this.props.toast} sel={this.state.sel} selectModel={(sel) => this.setState({ sel })} /></div>
        {window.QL.MODELS.length ? super.render() : null}
      </>
    );
  }
}
