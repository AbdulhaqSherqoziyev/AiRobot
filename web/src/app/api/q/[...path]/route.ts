import { NextRequest, NextResponse } from 'next/server';

// Single-origin proxy to the FastAPI control plane, so the session cookie stays HttpOnly and
// SameSite=Strict. It adds no credentials of its own: the API authenticates each request.
const BASE = process.env.QL_API_URL || 'http://127.0.0.1:8100';
const FORWARD = ['cookie', 'content-type', 'x-ql'];
const RETRIES = 6;
const RETRY_MS = 2000;

async function handle(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const path = (await ctx.params).path.map(encodeURIComponent).join('/');
  const headers: Record<string, string> = {};
  for (const h of FORWARD) {
    const v = req.headers.get(h);
    if (v) headers[h] = v;
  }
  const hasBody = !['GET', 'HEAD'].includes(req.method);
  // The API is briefly down during a restart. Reads wait it out. Writes are never retried here:
  // a repeat could act twice, and the caller must see the real outcome.
  const attempts = hasBody ? 1 : RETRIES + 1;
  const body = hasBody ? await req.text() : undefined;
  for (let attempt = 1; ; attempt++) {
  try {
    const res = await fetch(`${BASE}/${path}${req.nextUrl.search}`, {
      method: req.method,
      headers,
      body,
      cache: 'no-store',
      signal: AbortSignal.timeout(30000),
    });
    const out = new NextResponse(res.status === 204 ? null : await res.arrayBuffer(), { status: res.status });
    for (const h of ['content-type', 'content-disposition', 'set-cookie']) {
      const v = res.headers.get(h);
      if (v) out.headers.set(h, v);
    }
    return out;
  } catch {
    if (attempt >= attempts) return NextResponse.json({ detail: 'backend ulanmagan' }, { status: 502 });
    await new Promise((r) => setTimeout(r, RETRY_MS));
  }
  }
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
