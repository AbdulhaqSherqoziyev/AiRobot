import React from 'react';

/** Base class of the design's page logic. */
export class DCLogic<P = any, S = any> extends React.Component<P, S> {
  renderVals(): Record<string, unknown> {
    return {};
  }
}

export const arr = (v: unknown): any[] => (Array.isArray(v) ? v : []);

const camel = (s: string) => s.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase());

/** Parse a CSS declaration string to a React style object. */
export function css(text: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (typeof text !== 'string') return out;
  for (const decl of text.split(';')) {
    const i = decl.indexOf(':');
    if (i < 0) continue;
    const prop = decl.slice(0, i).trim();
    out[prop.startsWith('--') ? prop : camel(prop)] = decl.slice(i + 1).trim();
  }
  return out;
}

const HOST = new Set(['position', 'left', 'right', 'top', 'bottom', 'inset', 'width', 'height', 'zIndex', 'transform']);

/** Imported components only inherit positional styles from their host, as in the design runtime. */
export function hostStyle(style: Record<string, unknown>) {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(style)) if (HOST.has(k)) out[k] = v;
  return Object.keys(out).length ? (out as React.CSSProperties) : undefined;
}

const seen = new Map<string, string>();
let sheet: HTMLStyleElement | null = null;

/** `style-hover` / `style-focus`: inline styles cannot express pseudo classes, so emit a rule. */
export function ps(pseudo: string, text: unknown): string {
  const key = pseudo + '|' + String(text);
  const hit = seen.get(key);
  if (hit) return hit;
  const cls = 'dcp' + seen.size.toString(36);
  seen.set(key, cls);
  if (typeof document !== 'undefined') {
    if (!sheet) {
      sheet = document.createElement('style');
      sheet.id = 'dc-pseudo';
      document.head.appendChild(sheet);
    }
    const body = String(text).split(';').filter((d) => d.includes(':')).map((d) => d.trim() + ' !important').join(';');
    sheet.appendChild(document.createTextNode(`.${cls}:${pseudo}{${body}}\n`));
  }
  return cls;
}

/** One broken screen shows an error in place. The shell, navigation and kill switch stay usable. */
export class ScreenBoundary extends React.Component<{ children: React.ReactNode }, { error: string }> {
  state = { error: '' };
  static getDerivedStateFromError(e: Error) {
    return { error: e.message || 'Xato' };
  }
  render() {
    if (!this.state.error) return this.props.children;
    return React.createElement('div', { role: 'alert', style: { padding: 24, border: '1px solid #EA3943', borderRadius: 12, color: '#F1F5F9', fontSize: 14, background: '#151C2C' } }, "Bu sahifani ko'rsatib bo'lmadi: " + this.state.error);
  }
}
