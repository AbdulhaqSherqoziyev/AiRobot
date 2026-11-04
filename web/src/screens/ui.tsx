// @ts-nocheck
'use client';
/** Small kit in the design's visual language, for screens added after the design. */
import React from 'react';
import QL from '@/lib/ql';

export const T = { card: '#151C2C', border: '#263244', elev: '#1B2435', text: '#F1F5F9', muted: '#94A3B8', dim: '#64748B', accent: '#3B82F6', pos: '#16C784', neg: '#EA3943', warn: '#F0B90B', input: '#0F1522' };

export function Page({ title, sub, actions, children }: any) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap', justifyContent: 'space-between', minWidth: 0 }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, letterSpacing: '-.01em' }}>{title}</h1>
          {sub ? <p style={{ margin: '4px 0 0', fontSize: 13, color: T.muted }}>{sub}</p> : null}
        </div>
        {actions}
      </div>
      {children}
    </div>
  );
}

export function Card({ title, sub, right, children, style, pad = true }: any) {
  return (
    <section style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, minWidth: 0, ...style }}>
      {title ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '14px 16px', borderBottom: `1px solid ${T.border}` }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 600 }}>{title}</div>
            {sub ? <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>{sub}</div> : null}
          </div>
          {right}
        </div>
      ) : null}
      <div style={pad ? { padding: 16 } : undefined}>{children}</div>
    </section>
  );
}

export function Btn({ tone = 'neutral', children, style, ...p }: any) {
  const bg = { neutral: T.elev, primary: T.accent, danger: '#DC2F3A', ok: '#0E9F6E' }[tone];
  return <button {...p} style={{ height: 36, padding: '0 14px', borderRadius: 8, border: tone === 'neutral' ? `1px solid ${T.border}` : 0, background: p.disabled ? '#334155' : bg, color: T.text, fontSize: 13, fontWeight: 600, cursor: p.disabled ? 'not-allowed' : 'pointer', opacity: p.disabled ? 0.7 : 1, whiteSpace: 'nowrap', ...style }}>{children}</button>;
}

const fieldStyle = { height: 36, padding: '0 10px', background: T.input, border: `1px solid ${T.border}`, borderRadius: 8, color: T.text, fontSize: 13, outline: 'none', width: '100%' };

export function Field({ label, hint, children }: any) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, fontWeight: 500, color: T.muted, minWidth: 0 }}>
      {label}
      {children}
      {hint ? <span style={{ fontSize: 11, color: T.dim, fontWeight: 400 }}>{hint}</span> : null}
    </label>
  );
}
export const Input = (p: any) => <input {...p} style={{ ...fieldStyle, ...p.style }} />;
export const Select = ({ options, ...p }: any) => (
  <select {...p} style={{ ...fieldStyle, ...p.style }}>
    {options.map((o: any) => (Array.isArray(o) ? <option key={o[0]} value={o[0]}>{o[1]}</option> : <option key={o} value={o}>{o}</option>))}
  </select>
);

export function Pill({ color = T.muted, children }: any) {
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 700, color, background: color + '22', whiteSpace: 'nowrap' }}>{children}</span>;
}

export function Grid({ min = 240, gap = 12, children }: any) {
  return <div style={{ display: 'grid', gridTemplateColumns: `repeat(auto-fit,minmax(min(${min}px,100%),1fr))`, gap }}>{children}</div>;
}

export function Stat({ label, value, color, sub }: any) {
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '14px 16px', minWidth: 0 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.04em', color: T.muted, textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, marginTop: 6, color: color || T.text, overflow: 'hidden', textOverflow: 'ellipsis' }}>{value}</div>
      {sub ? <div style={{ fontSize: 12, color: T.muted, marginTop: 4 }}>{sub}</div> : null}
    </div>
  );
}

export function Table({ heads, rows, empty = "Ma'lumot yo'q" }: any) {
  if (!rows.length) return <div style={{ padding: '32px 16px', textAlign: 'center', color: T.muted, fontSize: 13 }}>{empty}</div>;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead><tr>{heads.map((h: string, i: number) => <th key={i} style={{ textAlign: 'left', padding: '9px 12px', color: T.muted, fontWeight: 600, borderBottom: `1px solid ${T.border}`, whiteSpace: 'nowrap' }}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r: any[], i: number) => <tr key={i}>{r.map((c, j) => <td key={j} style={{ padding: '9px 12px', borderBottom: '1px solid #1E2738', whiteSpace: 'nowrap', color: '#CBD5E1' }}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

export function Notice({ tone = 'warn', children }: any) {
  const c = { warn: T.warn, err: T.neg, info: '#60A5FA', ok: T.pos }[tone];
  return <div style={{ padding: '10px 12px', borderRadius: 8, background: c + '1F', border: `1px solid ${c}55`, color: c, fontSize: 13, lineHeight: '19px' }}>{children}</div>;
}

export const Icon = (p: any) => <QL.Icon {...p} />;

/** Poll an endpoint while the screen is mounted. */
export function usePoll(fn: () => Promise<any>, ms: number, deps: any[] = []) {
  const [data, setData] = React.useState<any>(null);
  const [error, setError] = React.useState<string>('');
  const fails = React.useRef(0);
  const load = React.useCallback(async () => {
    try {
      setData(await fn());
      fails.current = 0;
      setError('');
    } catch (e: any) {
      // One failed poll is usually a restart. Keep showing the last good data; report it only
      // if it continues, and a refused request (4xx) straight away.
      fails.current += 1;
      if (fails.current >= 3 || (e.status >= 400 && e.status < 500)) setError(e.message || 'Xato');
    }
  }, deps);
  React.useEffect(() => {
    load();
    const t = setInterval(load, ms);
    return () => clearInterval(t);
  }, [load, ms]);
  return { data, error, reload: load };
}

export const fmtTs = (t: number | null | undefined) => (t ? QL.fmt.dt(t) : '—');
