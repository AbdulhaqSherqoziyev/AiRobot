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
  it('labels real trades as real', () => {
    expect(gen('TradeHistory')).toContain("t.kind === 'live' ? 'REAL'");
  });
  it('removed the demo login', () => {
    expect(existsSync('src/screens/generated/Auth.tsx')).toBe(false);
    expect(gen('QuantLab')).not.toContain('Demo hisob');
  });
  it('adds the control screens to the shell', () => {
    const q = gen('QuantLab');
    for (const s of ['DC_Evaluation', 'DC_LiveCenter', 'DC_Monitoring']) expect(q).toContain(s);
  });
});
