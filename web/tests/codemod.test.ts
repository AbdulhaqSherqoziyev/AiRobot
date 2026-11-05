import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const gen = (n: string) => readFileSync(`src/screens/generated/${n}.tsx`, 'utf8');

describe('generated screens', () => {
  it('shows no demo labels', () => {
    for (const n of ['Dashboard', 'BacktestLab', 'MarketExplorer', 'Portfolio', 'Comparison', 'Reports', 'TradeHistory']) {
      const src = gen(n).replace(/demoState|demo-state/g, '');
      expect(src, n).not.toMatch(/DEMO MA'LUMOT|demo tarixiy|demo shamlar|demo narxlar|namunaviy \(demo\)/);
    }
  });
  it('uses no hard-coded dashboard figures', () => {
    expect(gen('Dashboard')).not.toContain("value: '142'");
  });
  it('contains no invented history or figures', () => {
    expect(gen('Strategies')).not.toContain('CooldownPeriod');
    expect(gen('Strategies')).not.toContain("'v1.2'");
    expect(gen('Reports')).not.toContain('01.05.2026');
    expect(gen('Reports')).not.toContain('Oylik hisobot · Okt 2026');
    expect(gen('MLLab')).not.toContain('Har 24 soatda');
    expect(gen('MLLab')).not.toContain('LGBM-Trend ehtimol');
    expect(gen('StrategyBuilder')).not.toContain('up_prob"]\\u0027');
    for (const n of ['Dashboard', 'Strategies', 'Reports', 'WhatIf', 'Comparison']) expect(gen(n), n).not.toContain('$50');
  });
  it('labels real trades as real', () => {
    expect(gen('TradeHistory')).toContain("t.kind === 'live' ? 'REAL'");
  });
  it('removed the demo login', () => {
    expect(existsSync('src/screens/generated/Auth.tsx')).toBe(false);
    expect(gen('QuantLab')).not.toContain('Demo hisob');
  });
  it('adds the control screens to the shell', () => {
    const q = gen('QuantLab');
    for (const s of ['DC_Evaluation', 'DC_LiveCenter', 'DC_Monitoring', 'DC_ExperimentLab', 'DC_StrategyEval', 'DC_Microstructure', 'DC_AiReports', 'DC_IntegrationsHub']) expect(q).toContain(s);
  });
});
