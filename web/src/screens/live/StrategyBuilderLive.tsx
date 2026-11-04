// @ts-nocheck
'use client';
import StrategyBuilder from '../generated/StrategyBuilder';
import { api } from '@/lib/api';
import { refresh } from '@/lib/backend';

const clean = (rows) => rows.map(({ ind, op, kind, val }) => ({ ind, op, kind, val }));

export default class StrategyBuilderLive extends StrategyBuilder {
  /** Each save is an immutable version: past results stay tied to the old rules. */
  async persist() {
    const s = this.state, Q = window.QL;
    const params = { rules: { join: s.join, entry: clean(s.entry), exit: clean(s.exit), prm: s.prm } };
    const risk = { stake_pct: s.sizing === 'pct' ? Math.min(1, s.size / 100) : 0.95, stoploss_pct: s.sl / 100, takeprofit_pct: s.tp / 100 };
    const existing = Q.STRATS.find((x) => x.name === s.name);
    let id;
    if (existing) {
      if (existing.engine !== 'rule_builder') throw new Error("Bu nom band: boshqa nom tanlang");
      await api(`/strategies/${existing.id}/versions`, { body: { params, pairs: [s.pair], timeframe: s.tf, risk, note: 'builder' } });
      id = existing.id;
    } else {
      id = String((await api('/strategies', { body: { name: s.name, engine: 'rule_builder', params, pairs: [s.pair], timeframe: s.tf, risk } })).id);
    }
    await refresh();
    return id;
  }
  renderVals() {
    const v = super.renderVals(), s = this.state, toast = this.props.toast;
    if (!v.save) return v;
    return {
      ...v,
      save: () => this.persist().then(() => toast('“' + s.name + '” yangi versiya sifatida saqlandi', 'ok')).catch((e) => toast(e.message, 'err')),
      runBacktest: () => this.persist().then((id) => this.props.nav('backtest', { strat: id, pair: s.pair, tf: s.tf, capital: s.capital, sl: s.sl, tp: s.tp, fee: s.fee, slip: s.slip, name: s.name })).catch((e) => toast(e.message, 'err')),
    };
  }
}
