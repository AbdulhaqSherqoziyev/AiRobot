// @ts-nocheck
'use client';
import React from 'react';
import { api } from '@/lib/api';
import { Btn, Field, Input, Notice, T } from './ui';

export default function Login({ onEnter }: any) {
  const [username, setU] = React.useState('owner');
  const [password, setP] = React.useState('');
  const [err, setErr] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const submit = async (e: any) => {
    e.preventDefault();
    setBusy(true);
    setErr('');
    try {
      await api('/auth/login', { body: { username, password } });
      onEnter();
    } catch (x: any) {
      setErr(x.message);
      setBusy(false);
    }
  };
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0B0F19', padding: 16, fontFamily: 'var(--font-ui)' }}>
      <form onSubmit={submit} style={{ width: 'min(380px,100%)', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 34, height: 34, borderRadius: 9, background: T.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, color: '#fff', fontSize: 13 }}>QL</div>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, color: T.text }}>Quant Lab</div>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.04em', color: T.muted }}>AI TRADING</div>
          </div>
        </div>
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: T.text }}>Hisobga kirish</div>
          {err ? <Notice tone="err">{err}</Notice> : null}
          <Field label="Login"><Input value={username} autoComplete="username" onChange={(e) => setU(e.target.value)} /></Field>
          <Field label="Parol"><Input type="password" value={password} autoComplete="current-password" autoFocus onChange={(e) => setP(e.target.value)} /></Field>
          <Btn tone="primary" type="submit" disabled={busy || !password} style={{ width: '100%' }}>{busy ? 'Tekshirilmoqda…' : 'Kirish'}</Btn>
        </div>
      </form>
    </div>
  );
}
