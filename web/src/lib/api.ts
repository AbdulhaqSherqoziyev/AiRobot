/** Client for the control-plane API. */

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = opts.method || (opts.body !== undefined ? 'POST' : 'GET');
  const res = await fetch('/api/q' + path, {
    method,
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { ...(method === 'GET' ? {} : { 'x-ql': '1' }), ...(opts.body !== undefined ? { 'content-type': 'application/json' } : {}) },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

/** Run an action and report through the design's toast, then refresh the shared data. */
export async function act(toast: ((t: string, k?: string) => void) | undefined, okText: string | null, fn: () => Promise<unknown>) {
  const { refresh } = await import('./backend');
  try {
    const r = await fn();
    if (okText && toast) toast(okText, 'ok');
    await refresh();
    return r;
  } catch (e: any) {
    if (toast) toast(e.message || 'Xato', 'err');
    return undefined;
  }
}
