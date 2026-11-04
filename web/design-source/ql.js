/* Quant Lab — shared demo data, mock API layer, formatters and chart/icon primitives.
   Every value here is seeded DEMO data. In production replace QL.api.* with calls to the
   backend REST API (freqtrade-based, /api/v1). API secrets never reach the frontend. */
(function () {
  if (window.QL) return;
  var C = { bg: '#0B0F19', bg2: '#111827', card: '#151C2C', elev: '#1B2435', accent: '#3B82F6', pos: '#16C784', neg: '#EA3943', warn: '#F0B90B', text: '#F1F5F9', muted: '#94A3B8', border: '#263244', grid: '#1A2333' };
  var DAY = 86400, HOUR = 3600;
  var END = Math.floor(Date.UTC(2026, 10, 4) / 1000);
  var NOW = function () { return Math.floor(Date.now() / 1000); };
  var PALETTE = ['#3B82F6', '#16B5CA', '#9747FF', '#EC4899', '#FFA841', '#A3B1C6'];
  var TF = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400, '1w': 604800 };

  function rng(seed) { var a = seed >>> 0; return function () { a = (a + 0x6D2B79F5) | 0; var t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  function gauss(r) { var u = 0, v = 0; while (!u) u = r(); while (!v) v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
  function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function hexA(hex, a) { var n = parseInt(hex.slice(1), 16); return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')'; }
  function pad(n) { return String(n).padStart(2, '0'); }
  function loc(v, d) { return Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }); }
  function avg(a) { return a.length ? a.reduce(function (s, x) { return s + x; }, 0) / a.length : 0; }
  function std(a) { var m = avg(a); return Math.sqrt(avg(a.map(function (x) { return (x - m) * (x - m); }))); }
  var MON = ['Yan', 'Fev', 'Mar', 'Apr', 'May', 'Iyn', 'Iyl', 'Avg', 'Sen', 'Okt', 'Noy', 'Dek'];

  var fmt = {
    usd: function (v, d) { if (v == null || isNaN(v)) return '—'; d = d == null ? 2 : d; return (v < 0 ? '−' : '') + '$' + loc(v, d); },
    susd: function (v, d) { if (v == null || isNaN(v)) return '—'; d = d == null ? 2 : d; return (v > 0 ? '+' : v < 0 ? '−' : '') + '$' + loc(v, d); },
    pct: function (v, d) { if (v == null || isNaN(v)) return '—'; d = d == null ? 2 : d; return (v > 0 ? '+' : v < 0 ? '−' : '') + loc(v, d) + '%'; },
    upct: function (v, d) { if (v == null || isNaN(v)) return '—'; return (v < 0 ? '−' : '') + loc(v, d == null ? 1 : d) + '%'; },
    num: function (v, d) { if (v == null || isNaN(v)) return '—'; return (v < 0 ? '−' : '') + loc(v, d || 0); },
    price: function (v) { if (v == null || isNaN(v)) return '—'; var d = v >= 10 ? 2 : v >= 1 ? 3 : 4; return loc(v, d); },
    compact: function (v) { var a = Math.abs(v); if (a >= 1e9) return (v / 1e9).toFixed(2) + 'B'; if (a >= 1e6) return (v / 1e6).toFixed(1) + 'M'; if (a >= 1e3) return (v / 1e3).toFixed(1) + 'K'; return v.toFixed(0); },
    tone: function (v) { return v > 0 ? C.pos : v < 0 ? C.neg : C.muted; },
    date: function (ts) { var d = new Date(ts * 1000); return pad(d.getUTCDate()) + '.' + pad(d.getUTCMonth() + 1) + '.' + d.getUTCFullYear(); },
    dt: function (ts) { var d = new Date(ts * 1000); return pad(d.getUTCDate()) + '.' + pad(d.getUTCMonth() + 1) + '.' + d.getUTCFullYear() + ' ' + pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()); },
    time: function (ts) { var d = new Date(ts * 1000); return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); },
    mon: function (y, m) { return MON[m] + ' ' + y; },
    dur: function (sec) { sec = Math.max(0, Math.round(sec)); var d = Math.floor(sec / DAY), h = Math.floor(sec % DAY / HOUR), m = Math.floor(sec % HOUR / 60); if (d) return d + ' kun ' + h + ' soat'; if (h) return h + ' soat ' + m + ' daq'; return m + ' daq'; },
    clock: function (sec) { sec = Math.max(0, Math.floor(sec)); var d = Math.floor(sec / DAY), h = Math.floor(sec % DAY / HOUR), m = Math.floor(sec % HOUR / 60), s = sec % 60; return (d ? d + ' kun ' : '') + pad(h) + ':' + pad(m) + ':' + pad(s); },
    ago: function (sec) { if (sec < 60) return 'hozirgina'; if (sec < HOUR) return Math.floor(sec / 60) + ' daq oldin'; if (sec < DAY) return Math.floor(sec / HOUR) + ' soat oldin'; if (sec < 2 * DAY) return 'kecha'; return Math.floor(sec / DAY) + ' kun oldin'; }
  };

  function series(vals, step, end) { var n = vals.length; return vals.map(function (v, i) { return { time: end - (n - 1 - i) * step, value: v }; }); }
  function ddOf(vals) { var pk = -Infinity; return vals.map(function (v) { pk = Math.max(pk, v); return (v / pk - 1) * 100; }); }
  function maxDD(vals) { var pk = -Infinity, m = 0; for (var i = 0; i < vals.length; i++) { pk = Math.max(pk, vals[i]); m = Math.min(m, (vals[i] / pk - 1) * 100); } return m; }
  function curve(seed, n, total, vol) { var r = rng(seed), L = 0, Ls = [0]; for (var i = 1; i < n; i++) { L += vol * gauss(r); Ls.push(L); } var adj = Math.log(1 + total / 100) - Ls[n - 1]; return Ls.map(function (l, i) { return Math.exp(l + adj * i / (n - 1)); }); }
  function monthlyOf(vals, end, base) {
    var n = vals.length, last = {}, order = [];
    for (var i = 0; i < n; i++) { var d = new Date((end - (n - 1 - i) * DAY) * 1000), k = d.getUTCFullYear() * 100 + d.getUTCMonth(); if (!(k in last)) order.push(k); last[k] = vals[i]; }
    var prev = base == null ? vals[0] : base;
    return order.map(function (k) { var v = last[k], r = (v / prev - 1) * 100; prev = v; return { y: Math.floor(k / 100), m: k % 100, ret: r, label: MON[k % 100] }; });
  }

  /* ---------- indicators ---------- */
  function ema(v, p) { var k = 2 / (p + 1), out = [], e = v[0]; for (var i = 0; i < v.length; i++) { e = i ? v[i] * k + e * (1 - k) : v[i]; out.push(e); } return out; }
  function sma(v, p) { var out = [], s = 0; for (var i = 0; i < v.length; i++) { s += v[i]; if (i >= p) s -= v[i - p]; out.push(s / Math.min(i + 1, p)); } return out; }
  function rsi(v, p) { p = p || 14; var out = [50], g = 0, l = 0; for (var i = 1; i < v.length; i++) { var d = v[i] - v[i - 1], up = d > 0 ? d : 0, dn = d < 0 ? -d : 0; if (i <= p) { g += up / p; l += dn / p; } else { g = (g * (p - 1) + up) / p; l = (l * (p - 1) + dn) / p; } out.push(i < p ? 50 : l === 0 ? 100 : 100 - 100 / (1 + g / l)); } return out; }
  function boll(v, p, k) { var mid = sma(v, p), up = [], lo = []; for (var i = 0; i < v.length; i++) { var a = Math.max(0, i - p + 1), s = 0; for (var j = a; j <= i; j++) s += (v[j] - mid[i]) * (v[j] - mid[i]); var sd = Math.sqrt(s / (i - a + 1)); up.push(mid[i] + k * sd); lo.push(mid[i] - k * sd); } return { mid: mid, upper: up, lower: lo }; }
  function macd(v) { var f = ema(v, 12), s = ema(v, 26), m = f.map(function (x, i) { return x - s[i]; }), sig = ema(m, 9); return { macd: m, signal: sig, hist: m.map(function (x, i) { return x - sig[i]; }) }; }
  function toSeries(cs, arr, from) { var out = []; for (var i = from || 0; i < cs.length; i++) out.push({ time: cs[i].time, value: arr[i] }); return out; }

  /* ---------- markets ---------- */
  var MK_RAW = [['BTC', 96420.5, 2.14, 1.82e9, 0.028], ['ETH', 3412.8, -1.06, 9.4e8, 0.036], ['BNB', 642.3, 0.48, 2.1e8, 0.03], ['SOL', 182.4, 4.82, 6.1e8, 0.05], ['XRP', 0.6214, -0.82, 3.3e8, 0.045], ['ADA', 0.4812, 1.12, 1.4e8, 0.05], ['DOGE', 0.1642, 6.31, 4.6e8, 0.06], ['AVAX', 38.62, -2.44, 1.2e8, 0.055], ['LINK', 17.84, 1.96, 1.1e8, 0.05], ['DOT', 6.92, -0.34, 7.2e7, 0.05], ['LTC', 84.15, 0.72, 9.0e7, 0.04], ['TRX', 0.1931, 0.21, 8.4e7, 0.03], ['ATOM', 8.41, -1.58, 5.6e7, 0.05], ['NEAR', 5.62, 3.05, 9.8e7, 0.06], ['APT', 10.84, -3.12, 7.7e7, 0.06], ['ARB', 0.8421, 1.44, 8.1e7, 0.06], ['OP', 1.982, -0.95, 6.4e7, 0.06], ['SUI', 2.214, 5.48, 2.4e8, 0.07]];
  var MARKETS = MK_RAW.map(function (a, i) {
    var r = rng(hash(a[0])), sp = [0], L = 0; for (var j = 1; j < 48; j++) { L += 0.004 * gauss(r); sp.push(L); }
    var start = a[1] / (1 + a[2] / 100), adj = Math.log(a[1] / start) - sp[47];
    var vals = sp.map(function (l, j) { return start * Math.exp(l + adj * j / 47); });
    return { sym: a[0] + '/USDT', base: a[0], price: a[1], ch: a[2], vol: a[3], dv: a[4], rank: i + 1, spark: vals, high: Math.max.apply(null, vals) * 1.003, low: Math.min.apply(null, vals) * 0.997 };
  });
  var MK = {}; MARKETS.forEach(function (m) { MK[m.sym] = m; });

  function genCandles(sym, step, n, end, seed) {
    var m = MK[sym] || MARKETS[0], r = rng(seed), vol = m.dv * Math.sqrt(step / DAY), Ls = [0], L = 0;
    for (var i = 1; i < n; i++) { L += vol * gauss(r); Ls.push(L); }
    var adj = -Ls[n - 1], out = [], prev = 0;
    for (i = 0; i < n; i++) {
      var c = m.price * Math.exp(Ls[i] + adj), o = i ? prev : c * (1 - vol * 0.3 * gauss(r));
      var hi = Math.max(o, c) * (1 + Math.abs(gauss(r)) * vol * 0.4), lo = Math.min(o, c) * (1 - Math.abs(gauss(r)) * vol * 0.4);
      var v = (m.vol / m.price) * (step / DAY) * (0.5 + r()) * (1 + Math.min(3, Math.abs(c / o - 1) / vol));
      out.push({ time: end - (n - 1 - i) * step, open: o, high: hi, low: lo, close: c, volume: v }); prev = c;
    }
    return out;
  }
  function candles(sym, tf, n) { var step = TF[tf] || HOUR; return genCandles(sym, step, n || 320, Math.floor(NOW() / step) * step, hash(sym + tf)); }

  /* ---------- backtest engine (runs in-browser on demo candles) ---------- */
  var SIG = {
    rsi: { en: function (k, i) { return k.rs[i] < k.os; }, ex: function (k, i) { return k.rs[i] > k.ob; } },
    ema: { en: function (k, i) { return k.ef[i] > k.es[i] && k.ef[i - 1] <= k.es[i - 1]; }, ex: function (k, i) { return k.ef[i] < k.es[i]; } },
    macd: { en: function (k, i) { return k.mh[i] > 0 && k.mh[i - 1] <= 0 && k.cl[i] > k.e200[i]; }, ex: function (k, i) { return k.mh[i] < 0; } },
    bb: { en: function (k, i) { return k.cl[i] < k.bl[i]; }, ex: function (k, i) { return k.cl[i] > k.bm[i]; } },
    multi: { en: function (k, i) { return k.rs[i] < 42 && k.ef[i] > k.es[i]; }, ex: function (k, i) { return k.rs[i] > 68 || k.ef[i] < k.es[i]; } },
    ai: { en: function (k, i) { return k.ai[i] > 0.62; }, ex: function (k, i) { return k.ai[i] < 0.45; } }
  };
  function runBT(cfg) {
    var step = TF[cfg.tf] || HOUR, n = Math.max(160, Math.min(8000, Math.round(cfg.days * DAY / step)));
    var cs = genCandles(cfg.pair, step, n, cfg.end || END, cfg.seed || 1), cl = cs.map(function (c) { return c.close; });
    var sid = SIG[cfg.strat] ? cfg.strat : 'rsi';
    var k = { cl: cl, os: cfg.os || 30, ob: cfg.ob || 70, rs: rsi(cl, cfg.rsiP || 14), ef: ema(cl, cfg.fast || 20), es: ema(cl, cfg.slow || 50) };
    if (sid === 'macd') { k.mh = macd(cl).hist; k.e200 = ema(cl, 200); }
    if (sid === 'bb') { var b = boll(cl, 20, 2); k.bl = b.lower; k.bm = b.mid; }
    if (sid === 'ai') { var r2 = rng((cfg.seed || 1) + 77); k.ai = cl.map(function (c, i) { return 1 / (1 + Math.exp(-((50 - k.rs[i]) / 9 + (k.ef[i] / k.es[i] - 1) * 60 + gauss(r2) * 0.9))); }); }
    var S = SIG[sid], fee = (cfg.fee || 0) / 100, slip = (cfg.slip || 0) / 100, sl = (cfg.sl || 0) / 100, tp = (cfg.tp || 0) / 100, size = Math.min(1, (cfg.size || 100) / 100), cap = cfg.capital || 50;
    var cash = cap, pos = null, trades = [], marks = [], eq = new Array(n), cool = 0, warm = 60;
    for (var i = 0; i < n; i++) {
      var c = cs[i];
      if (i >= warm) {
        if (pos) {
          var xp = 0, why = '';
          if (sl && c.low <= pos.entry * (1 - sl)) { xp = pos.entry * (1 - sl); why = 'Stop-loss'; }
          else if (tp && c.high >= pos.entry * (1 + tp)) { xp = pos.entry * (1 + tp); why = 'Take-profit'; }
          else if (S.ex(k, i)) { xp = c.close; why = 'Signal'; }
          if (xp) {
            var fill = xp * (1 - slip), gross = pos.qty * fill, f2 = gross * fee; cash += gross - f2;
            var pnl = gross - f2 - pos.cost;
            trades.push({ entryT: pos.t, exitT: c.time, entry: pos.entry, exit: fill, qty: pos.qty, fees: pos.fee + f2, pnl: pnl, pnlPct: pnl / pos.cost * 100, why: why, cost: pos.cost });
            if (!cfg.lite) marks.push({ time: c.time, position: 'aboveBar', color: C.neg, shape: 'arrowDown', text: 'S' });
            pos = null; cool = 2;
          }
        } else if (cool > 0) cool--;
        else if (S.en(k, i)) {
          var px = c.close * (1 + slip), stake = cash * size, f1 = stake * fee;
          if (stake > 1) { pos = { entry: px, qty: (stake - f1) / px, cost: stake, fee: f1, t: c.time, i: i }; cash -= stake; if (!cfg.lite) marks.push({ time: c.time, position: 'belowBar', color: C.pos, shape: 'arrowUp', text: 'B' }); }
        }
      }
      eq[i] = cash + (pos ? pos.qty * c.close : 0);
    }
    var final = eq[n - 1], wins = 0, gp = 0, gl = 0, dsum = 0;
    trades.forEach(function (t) { if (t.pnl > 0) { wins++; gp += t.pnl; } else gl -= t.pnl; dsum += t.exitT - t.entryT; });
    var per = Math.max(1, Math.round(DAY / step)), dv = [];
    for (i = 0; i < n; i += per) dv.push(eq[i]);
    if ((n - 1) % per) dv.push(final);
    var rr = []; for (i = 1; i < dv.length; i++) rr.push(dv[i] / dv[i - 1] - 1);
    var mean = avg(rr), sd = std(rr), dn = Math.sqrt(avg(rr.map(function (x) { return x < 0 ? x * x : 0; })));
    var res = { ret: (final / cap - 1) * 100, net: final - cap, cap: cap, final: final, trades: trades.length, wins: wins, losses: trades.length - wins, win: trades.length ? wins / trades.length * 100 : 0, pf: gl ? gp / gl : (gp ? 99 : 0), mdd: maxDD(eq), sharpe: sd ? mean / sd * Math.sqrt(365) : 0, sortino: dn ? mean / dn * Math.sqrt(365) : 0, avgDur: trades.length ? dsum / trades.length : 0, avgTrade: avg(trades.map(function (t) { return t.pnlPct; })), dailyEq: dv, from: cs[0].time, to: cs[n - 1].time, bars: n };
    if (cfg.lite) return res;
    var stride = Math.max(1, Math.ceil(n / 1500)), pk = -Infinity; res.eq = []; res.dd = [];
    for (i = 0; i < n; i++) { pk = Math.max(pk, eq[i]); if (i % stride === 0 || i === n - 1) { res.eq.push({ time: cs[i].time, value: eq[i] }); res.dd.push({ time: cs[i].time, value: (eq[i] / pk - 1) * 100 }); } }
    var sp = cfg.split || [60, 20, 20], a = Math.floor(n * sp[0] / 100), bb2 = Math.floor(n * (sp[0] + sp[1]) / 100);
    res.segs = [
      { name: "O'qitish", from: cs[0].time, to: cs[a].time, ret: (eq[a] / eq[0] - 1) * 100, pct: sp[0], color: '#3B82F6' },
      { name: 'Validatsiya', from: cs[a].time, to: cs[bb2].time, ret: (eq[bb2] / eq[a] - 1) * 100, pct: sp[1], color: '#9747FF' },
      { name: 'Namunadan tashqari (OOS)', from: cs[bb2].time, to: cs[n - 1].time, ret: (final / eq[bb2] - 1) * 100, pct: sp[2], color: '#FFA841' }
    ];
    res.monthly = monthlyOf(dv, cs[n - 1].time, cap);
    var bins = []; for (var bx = -6; bx < 8; bx++) bins.push({ lo: bx, n: 0 });
    trades.forEach(function (t) { var j = Math.max(0, Math.min(bins.length - 1, Math.floor(t.pnlPct) + 6)); bins[j].n++; });
    res.dist = bins; res.candles = cs; res.markers = marks; res.list = trades; res.open = pos;
    return res;
  }

  /* ---------- strategies ---------- */
  var STRATS = [
    { id: 'rsi', name: 'RSI Reversal', pair: 'BTC/USDT', tf: '1h', type: 'Qaytish', target: 12.4, sl: 3, tp: 6, status: 'active', bt: END - 10 * HOUR, created: END - 140 * DAY, desc: "RSI(14) 30 dan past bo'lganda sotib oladi; 70 dan oshganda yoki stop-loss ishlaganda sotadi." },
    { id: 'ema', name: 'EMA Crossover', pair: 'ETH/USDT', tf: '4h', type: 'Trend', target: 24.8, sl: 6, tp: 0, status: 'active', bt: END - 30 * HOUR, created: END - 122 * DAY, desc: "EMA(20) EMA(50) ni pastdan yuqoriga kesib o'tganda kiradi; teskari kesishuvda chiqadi." },
    { id: 'macd', name: 'MACD Momentum', pair: 'SOL/USDT', tf: '1h', type: 'Momentum', target: 9.6, sl: 4, tp: 8, status: 'paused', bt: END - 52 * HOUR, created: END - 96 * DAY, desc: "MACD gistogrammasi musbatga o'tganda va narx EMA(200) dan yuqori bo'lganda kiradi." },
    { id: 'bb', name: 'Bollinger Bands', pair: 'BNB/USDT', tf: '15m', type: 'Qaytish', target: -3.2, sl: 2, tp: 3, status: 'inactive', bt: END - 5 * DAY, created: END - 80 * DAY, desc: "Narx pastki Bollinger chizig'idan pastga tushganda kiradi; o'rta chiziqqa qaytganda chiqadi." },
    { id: 'multi', name: 'Multi-Indicator', pair: 'BTC/USDT', tf: '4h', type: 'Kompozit', target: 17.9, sl: 4, tp: 9, status: 'active', bt: END - 3 * HOUR, created: END - 61 * DAY, desc: "RSI(14) < 42 va EMA(20) > EMA(50) birgalikda tasdiqlaganda kiradi." },
    { id: 'ai', name: 'AI Prediction', pair: 'ETH/USDT', tf: '1h', type: 'ML · LightGBM', target: 6.1, sl: 3, tp: 5, status: 'draft', bt: END - 30 * HOUR, created: END - 24 * DAY, desc: "LGBM-Trend v1.4 tavsiyasi 0.62 ishonch chegarasidan oshganda, risk va Shariat tekshiruvidan so'ng kiradi." }
  ];
  function btDefaults(s) { return { strat: s.engine || s.id, pair: s.pair, tf: s.tf, days: s.tf === '15m' ? 75 : 300, capital: 50, fee: 0.1, slip: 0.05, sl: s.sl, tp: s.tp, size: 100, seed: s.seed, rsiP: 14, os: 30, ob: 70, fast: 20, slow: 50, split: [60, 20, 20] }; }
  STRATS.forEach(function (s, i) {
    s.color = PALETTE[i]; var best = null;
    for (var j = 1; j <= 28; j++) { var seed = (hash(s.id) + j * 7919) >>> 0; var r = runBT(Object.assign(btDefaults(s), { seed: seed, lite: true })); var d = Math.abs(r.ret - s.target) + Math.max(0, -r.mdd - 15) * 0.7 + (r.trades < 24 ? 4 : 0); if (!best || d < best.d) best = { d: d, seed: seed, r: r }; if (d < 1.5) break; }
    s.seed = best.seed; var R = best.r;
    ['ret', 'win', 'trades', 'mdd', 'sharpe', 'sortino', 'pf', 'avgDur', 'avgTrade', 'net', 'wins', 'losses'].forEach(function (key) { s[key] = R[key]; });
    s.curve = series(R.dailyEq.map(function (v) { return (v / 50 - 1) * 100; }), DAY, END);
    s.dd = series(ddOf(R.dailyEq), DAY, END);
    s.dailyEq = R.dailyEq;
    s.monthly = monthlyOf(R.dailyEq, END, 50);
    s.spark = R.dailyEq.filter(function (_, k) { return k % 5 === 0; });
  });
  var SMAP = {}; STRATS.forEach(function (s) { SMAP[s.id] = s; });

  var STATUS = {
    active: ['Faol', C.pos], paused: ['Pauza', C.warn], inactive: ['Nofaol', C.muted], draft: ['Qoralama', '#60A5FA'],
    running: ['Ishlamoqda', C.pos], stopped: ["To'xtatilgan", C.muted], error: ['Xatolik', C.neg], done: ['Yakunlandi', C.pos],
    training: ["O'qitilmoqda", '#60A5FA'], queued: ['Navbatda', C.muted], prod: ['Asosiy', C.pos], staging: ['Sinovda', C.warn], archived: ['Arxiv', C.muted],
    open: ['Ochiq', '#60A5FA'], closed: ['Yopiq', C.muted], ok: ['Ishlayapti', C.pos], warn: ['Ogohlantirish', C.warn]
  };
  function status(k) { var s = STATUS[k] || [k, C.muted]; return { label: s[0], color: s[1], bg: hexA(s[1], 0.13) }; }

  /* ---------- virtual portfolio (paper account) ---------- */
  var PSTART = 2000, PN = 188, pm = curve(7, PN, 13.57, 0.0062), pEq = pm.map(function (x) { return x * PSTART; });
  var bench = curve(11, PN, 18.2, 0.024);
  var portfolio = {
    start: PSTART, final: pEq[PN - 1], mdd: maxDD(pEq), values: pEq,
    equity: series(pEq, DAY, END), dd: series(ddOf(pEq), DAY, END),
    pnlPct: series(pEq.map(function (v) { return (v / PSTART - 1) * 100; }), DAY, END),
    bench: series(bench.map(function (v) { return (v - 1) * 100; }), DAY, END),
    daily: pEq.slice(1).map(function (v, i) { var d = v - pEq[i]; return { time: END - (PN - 2 - i) * DAY, value: d, color: d >= 0 ? hexA(C.pos, 0.85) : hexA(C.neg, 0.85) }; }),
    monthly: monthlyOf(pEq, END, PSTART),
    alloc: [{ name: 'BTC', v: 38.4, color: '#FFA841' }, { name: 'ETH', v: 31.2, color: '#9747FF' }, { name: 'SOL', v: 10.6, color: '#16B5CA' }, { name: 'BNB', v: 2.2, color: '#EC4899' }, { name: "USDT (bo'sh)", v: 17.6, color: '#64748B' }]
  };
  var dr = []; for (var q = 1; q < PN; q++) dr.push(pEq[q] / pEq[q - 1] - 1);
  portfolio.vol = std(dr) * Math.sqrt(365) * 100;
  portfolio.sharpe = avg(dr) / std(dr) * Math.sqrt(365);
  portfolio.sortino = avg(dr) / Math.sqrt(avg(dr.map(function (x) { return x < 0 ? x * x : 0; }))) * Math.sqrt(365);
  portfolio.ret = (portfolio.final / PSTART - 1) * 100;
  portfolio.calmar = portfolio.ret / Math.abs(portfolio.mdd);
  portfolio.winDays = dr.filter(function (x) { return x > 0; }).length / dr.length * 100;

  /* ---------- paper sessions ---------- */
  var t0 = NOW();
  var SESS = [
    { id: 's1', strat: 'rsi', pair: 'BTC/USDT', tf: '1h', start: 50, realized: 2.31, pos: { qty: 0.000318, entry: 95840.2, t: t0 - 3 * HOUR }, status: 'running', started: t0 - (2 * DAY + 6 * HOUR + 14 * 60), trades: 11 },
    { id: 's2', strat: 'ema', pair: 'ETH/USDT', tf: '4h', start: 100, realized: 3.05, pos: { qty: 0.0215, entry: 3388.4, t: t0 - 19 * HOUR }, status: 'running', started: t0 - (5 * DAY + 2 * HOUR), trades: 4 },
    { id: 's3', strat: 'multi', pair: 'BTC/USDT', tf: '4h', start: 500, realized: 12.92, pos: { qty: 0.00412, entry: 95210, t: t0 - 30 * HOUR }, status: 'running', started: t0 - (9 * DAY + 11 * HOUR), trades: 7 },
    { id: 's4', strat: 'macd', pair: 'SOL/USDT', tf: '1h', start: 250, realized: -8.9, pos: null, status: 'paused', started: t0 - 12 * DAY, trades: 19, note: 'MaxDrawdown himoyasi: sessiya −10% chegaraga yaqinlashdi' },
    { id: 's5', strat: 'bb', pair: 'BNB/USDT', tf: '15m', start: 50, realized: -1.4, pos: null, status: 'stopped', started: t0 - 31 * DAY, ended: t0 - 18 * DAY, trades: 42 },
    { id: 's6', strat: 'ai', pair: 'ETH/USDT', tf: '1h', start: 1000, realized: 31.2, pos: null, status: 'stopped', started: t0 - 46 * DAY, ended: t0 - 25 * DAY, trades: 36 }
  ];
  function sessTrades(s) {
    var r = rng(hash(s.id)), m = MK[s.pair], n = s.trades, stake = s.start * 0.6, raw = [], sum = 0;
    for (var i = 0; i < n; i++) { var p = gauss(r) * 1.4 + 0.15; raw.push(p); sum += stake * p / 100; }
    var shift = (s.realized - sum) / n, end = s.ended || (s.pos ? s.pos.t - HOUR : NOW() - HOUR), span = end - s.started, out = [];
    for (i = 0; i < n; i++) {
      var pnl = stake * raw[i] / 100 + shift, pct = pnl / stake * 100, exitT = s.started + span * (i + 1) / (n + 0.3), dur = (0.15 + r() * 0.7) * span / n;
      var entry = m.price * (0.95 + r() * 0.08), exit = entry * (1 + pct / 100);
      out.push({ id: s.id + '-' + i, entryT: exitT - dur, exitT: exitT, entry: entry, exit: exit, qty: stake / entry, fees: stake * 0.002, pnl: pnl, pnlPct: pct, why: pct > 0 ? (r() > 0.5 ? 'Signal' : 'Take-profit') : (r() > 0.5 ? 'Signal' : 'Stop-loss'), cost: stake });
    }
    return out.reverse();
  }
  function sessEvents(s) {
    var st = SMAP[s.strat], now = NOW();
    return [
      { t: now - 40, kind: 'info', text: 'Signal tekshiruvi: kirish sharti bajarilmadi', sub: st.name + ' · ' + s.pair },
      { t: now - 3 * 60 - 12, kind: 'info', text: "Yangi sham yopildi, indikatorlar qayta hisoblandi", sub: s.tf + ' · ' + s.pair },
      s.pos ? { t: s.pos.t, kind: 'buy', text: 'Virtual SOTIB OLISH bajarildi @ ' + fmt.price(s.pos.entry), sub: fmt.num(s.pos.qty, 6) + ' ' + s.pair.split('/')[0] + ' · komissiya 0.1%' } : null,
      s.pos ? { t: s.pos.t - 1, kind: 'ok', text: 'Tekshiruvlar o\'tdi: bozor ✓ risk ✓ Shariat (spot, leverage 1.0) ✓', sub: 'Buyurtma darvozasi (L4)' } : null,
      { t: s.started, kind: 'start', text: 'Sessiya boshlandi · boshlang\'ich balans ' + fmt.usd(s.start), sub: 'Paper rejim · real buyurtma yuborilmaydi' }
    ].filter(Boolean);
  }

  /* ---------- trade history (backtest + paper) ---------- */
  var _trades = null;
  function trades() {
    if (_trades) return _trades;
    var out = [];
    STRATS.forEach(function (s) {
      var r = runBT(btDefaults(s));
      r.list.slice(-45).forEach(function (t, i) { out.push(Object.assign({ id: 'bt-' + s.id + '-' + i, strat: s.id, stratName: s.name, pair: s.pair, kind: 'backtest', status: 'closed' }, t)); });
    });
    SESS.forEach(function (ss) {
      var s = SMAP[ss.strat];
      sessTrades(ss).forEach(function (t) { out.push(Object.assign({ strat: s.id, stratName: s.name, pair: ss.pair, kind: 'paper', status: 'closed' }, t)); });
      if (ss.pos) { var p = MK[ss.pair].price, cost = ss.pos.qty * ss.pos.entry, pnl = ss.pos.qty * p - cost; out.push({ id: ss.id + '-open', strat: s.id, stratName: s.name, pair: ss.pair, kind: 'paper', status: 'open', entryT: ss.pos.t, exitT: null, entry: ss.pos.entry, exit: null, qty: ss.pos.qty, fees: cost * 0.001, pnl: pnl, pnlPct: pnl / cost * 100, cost: cost }); }
    });
    out.sort(function (a, b) { return (b.exitT || b.entryT + 1e9) - (a.exitT || a.entryT + 1e9); });
    _trades = out; return out;
  }

  /* ---------- AI / ML ---------- */
  var MODELS = [
    { id: 'm1', name: 'LGBM-Trend', algo: 'LightGBM', ver: 'v1.4', acc: 56.8, prec: 58.1, rec: 52.4, f1: 55.1, val: 54.9, oos: 53.6, dur: '14 daq', status: 'prod', pair: 'ETH/USDT', tf: '1h', trained: END - 1 * DAY, features: 42, samples: 18400 },
    { id: 'm2', name: 'XGB-Reversal', algo: 'XGBoost', ver: 'v2.1', acc: 54.2, prec: 55.6, rec: 50.9, f1: 53.1, val: 52.7, oos: 51.8, dur: '22 daq', status: 'staging', pair: 'BTC/USDT', tf: '1h', trained: END - 3 * DAY, features: 38, samples: 21900 },
    { id: 'm3', name: 'LSTM-Seq64', algo: 'LSTM', ver: 'v0.9', acc: 52.9, prec: 53.4, rec: 56.2, f1: 54.8, val: 51.2, oos: 49.7, dur: '1 soat 48 daq', status: 'staging', pair: 'BTC/USDT', tf: '15m', trained: END - 6 * DAY, features: 24, samples: 64000 },
    { id: 'm4', name: 'PPO-LongOnly', algo: 'RL · PPO', ver: 'v0.3', acc: null, prec: null, rec: null, f1: null, val: null, oos: null, reward: 0.42, dur: '—', status: 'training', pair: 'ETH/USDT', tf: '1h', trained: null, features: 30, samples: 0 },
    { id: 'm5', name: 'LGBM-Trend', algo: 'LightGBM', ver: 'v1.3', acc: 55.4, prec: 56.0, rec: 51.8, f1: 53.8, val: 53.9, oos: 52.1, dur: '13 daq', status: 'archived', pair: 'ETH/USDT', tf: '1h', trained: END - 19 * DAY, features: 40, samples: 17200 }
  ];
  var FEATURES = [['rsi_14', 0.142], ['ema_ratio_20_50', 0.118], ['atr_pct_14', 0.097], ['volume_z_24', 0.088], ['macd_hist', 0.081], ['bb_width_20', 0.074], ['ret_lag_1', 0.066], ['ret_lag_3', 0.059], ['hour_of_day', 0.041], ['btc_corr_48', 0.038]];
  var JOBS = [
    { id: 'j1', model: 'PPO-LongOnly v0.3', algo: 'RL · PPO', progress: 64, status: 'training', note: 'Epizod 640 / 1000', eta: '18 daq' },
    { id: 'j2', model: 'LGBM-Trend v1.5', algo: 'LightGBM', progress: 22, status: 'training', note: 'Fold 2 / 5 (walk-forward)', eta: '9 daq' },
    { id: 'j3', model: 'XGB-Reversal v2.2', algo: 'XGBoost', progress: 0, status: 'queued', note: 'Navbatda: 1-o\'rin', eta: '—' }
  ];

  /* ---------- optimizer (demo search results) ---------- */
  var _opt = null;
  function optimizer() {
    if (_opt) return _opt;
    var r = rng(555), trials = [];
    function surf(p, o, sl) { return 1.62 - Math.pow((p - 13) / 6, 2) * 0.55 - Math.pow((o - 28) / 7, 2) * 0.5 - Math.pow((sl - 2.8) / 2, 2) * 0.3; }
    for (var i = 0; i < 500; i++) {
      var p = 7 + Math.floor(r() * 15), o = 20 + Math.floor(r() * 16), ob = 65 + Math.floor(r() * 16), sl = Math.round((1 + r() * 4) * 2) / 2, tp = Math.round((2 + r() * 8) * 2) / 2;
      var sh = surf(p, o, sl) + gauss(r) * 0.16, ret = sh * 7.2 + gauss(r) * 2.6 + tp * 0.35, mdd = -(3.5 + tp * 0.45 + Math.abs(gauss(r)) * 2.4 + (36 - o) * 0.12);
      trials.push({ n: i + 1, rsiP: p, os: o, ob: ob, sl: sl, tp: tp, sharpe: sh, ret: ret, mdd: mdd, trades: Math.round(60 + (o - 20) * 6 + r() * 40), pf: 1 + sh * 0.32 + gauss(r) * 0.05 });
    }
    trials.forEach(function (t) { t.pareto = !trials.some(function (u) { return u !== t && u.ret >= t.ret && u.mdd >= t.mdd && (u.ret > t.ret || u.mdd > t.mdd); }); });
    var grid = []; for (var oo = 34; oo >= 20; oo -= 2) { var row = []; for (var pp = 7; pp <= 21; pp += 2) row.push(surf(pp, oo, 2.5)); grid.push({ os: oo, cells: row }); }
    _opt = { trials: trials, grid: grid, gridCols: [7, 9, 11, 13, 15, 17, 19, 21] };
    return _opt;
  }

  /* ---------- recent backtests & notifications ---------- */
  var BACKTESTS = [
    { id: 'BT-142', strat: 'multi', ts: END - 3 * HOUR, status: 'done' }, { id: 'BT-141', strat: 'rsi', ts: END - 10 * HOUR, status: 'done' },
    { id: 'BT-140', strat: 'ema', ts: END - 30 * HOUR, status: 'done' }, { id: 'BT-139', strat: 'ai', ts: END - 31 * HOUR, status: 'done' },
    { id: 'BT-138', strat: 'macd', ts: END - 52 * HOUR, status: 'error', err: "SOL/USDT 1m: tarixiy ma'lumotda bo'shliq (12.10 – 14.10)" },
    { id: 'BT-137', strat: 'bb', ts: END - 5 * DAY, status: 'done' }
  ].map(function (b) { var s = SMAP[b.strat]; return Object.assign(b, { name: s.name, pair: s.pair, tf: s.tf, ret: s.ret, sharpe: s.sharpe, mdd: s.mdd, trades: s.trades }); });
  var NOTIFS = [
    { id: 'n1', type: 'backtest', icon: 'flask-conical', tone: C.pos, title: 'Backtest yakunlandi', text: 'Multi-Indicator · BTC/USDT 4h — ' + fmt.pct(SMAP.multi.ret) + ', Sharpe ' + SMAP.multi.sharpe.toFixed(2), ago: 12 * 60, read: false, route: 'backtest' },
    { id: 'n2', type: 'risk', icon: 'triangle-alert', tone: C.neg, title: 'Maksimal pasayish chegarasi oshdi', text: "MACD Momentum · SOL/USDT sessiyasi −10% chegaraga yetdi. Sessiya pauzaga qo'yildi.", ago: 2 * HOUR, read: false, route: 'paper' },
    { id: 'n3', type: 'system', icon: 'database', tone: C.warn, title: "Bozor ma'lumotlari sinxronizatsiyasi xato", text: 'SOL/USDT 1m — Binance 429 (so\'rovlar limiti). 60 soniyadan keyin qayta urinish.', ago: 3 * HOUR, read: false, route: 'integrations' },
    { id: 'n4', type: 'paper', icon: 'circle-play', tone: '#60A5FA', title: 'Paper trading sessiyasi boshlandi', text: 'RSI Reversal · BTC/USDT · boshlang\'ich balans $50.00', ago: 2 * DAY + 6 * HOUR, read: true, route: 'paper' },
    { id: 'n5', type: 'paper', icon: 'trending-up', tone: C.pos, title: 'Strategiya yangi cho\'qqiga chiqdi', text: 'EMA Crossover · ETH/USDT sessiyasi equity maksimumi: $104.12', ago: 5 * HOUR, read: true, route: 'paper' },
    { id: 'n6', type: 'ml', icon: 'brain', tone: '#60A5FA', title: "ML o'qitish yakunlandi", text: 'LGBM-Trend v1.4 — validatsiya F1 54.9%, OOS F1 53.6%', ago: DAY + 2 * HOUR, read: true, route: 'ml' },
    { id: 'n7', type: 'optimizer', icon: 'sliders-horizontal', tone: C.pos, title: 'Optimizatsiya yakunlandi', text: 'RSI Reversal · 500 iteratsiya · NSGA-II · Pareto to\'plamida 9 ta konfiguratsiya', ago: 2 * DAY, read: true, route: 'optimizer' },
    { id: 'n8', type: 'system', icon: 'shield-check', tone: C.muted, title: 'Shariat filtri yangilandi', text: 'IslamicComplianceFilter: juftliklar ro\'yxati qayta tekshirildi, leveraged tokenlar chiqarib tashlandi.', ago: 3 * DAY, read: true, route: 'settings' }
  ];

  var NAV = [
    { group: 'Umumiy', items: [['dashboard', 'Boshqaruv paneli', 'layout-dashboard'], ['market', 'Bozor tadqiqoti', 'chart-candlestick']] },
    { group: 'Strategiyalar', items: [['strategies', 'Mening strategiyalarim', 'layers'], ['builder', 'Strategiya konstruktori', 'blocks'], ['compare', 'Solishtirish', 'git-compare']] },
    { group: 'Tadqiqot', items: [['backtest', 'Backtest laboratoriyasi', 'flask-conical'], ['paper', 'Paper trading', 'circle-play'], ['ml', 'AI / ML laboratoriyasi', 'brain'], ['optimizer', 'Optimizator', 'sliders-horizontal']] },
    { group: 'Tahlil', items: [['portfolio', 'Portfel tahlili', 'chart-pie'], ['trades', 'Savdolar tarixi', 'history'], ['reports', 'Hisobotlar', 'file-text'], ['whatif', 'What-If kalkulyatori', 'calculator']] },
    { group: 'Tizim', items: [['notifications', 'Bildirishnomalar', 'bell'], ['integrations', 'Integratsiyalar', 'plug'], ['settings', 'Sozlamalar', 'settings']] }
  ];

  /* ---------- live demo price stream ---------- */
  var px = {}; MARKETS.forEach(function (m) { px[m.sym] = m.price; });
  var subs = [], timer = null, r9 = rng(4242);
  function tick() { MARKETS.forEach(function (m) { px[m.sym] *= Math.exp(m.dv / Math.sqrt(DAY) * 1.8 * gauss(r9)); }); subs.slice().forEach(function (f) { try { f(px); } catch (e) { } }); }
  var stream = { px: px, subscribe: function (f) { subs.push(f); if (!timer) timer = setInterval(tick, 1000); return function () { subs = subs.filter(function (g) { return g !== f; }); if (!subs.length && timer) { clearInterval(timer); timer = null; } }; } };

  /* ---------- mock API layer (swap for fetch() against the backend) ---------- */
  var endpoints = {
    dashboard: 'GET /api/v1/dashboard/summary', strategies: 'GET /api/v1/strategies', candles: 'GET /api/v1/pair_candles?pair=&timeframe=',
    backtest: 'POST /api/v1/backtest', sessions: 'GET /api/v1/paper/sessions', trades: 'GET /api/v1/trades', models: 'GET /api/v1/ml/models',
    optimizer: 'POST /api/v1/hyperopt', notifications: 'GET /api/v1/notifications', integrations: 'GET /api/v1/integrations'
  };
  var api = { endpoints: endpoints, mode: 'mock', get: function (key, producer, ms) { return new Promise(function (res) { setTimeout(function () { res(producer ? producer() : null); }, (ms || 380) + Math.random() * 240); }); } };

  function downloadCSV(name, rows) {
    var csv = rows.map(function (r) { return r.map(function (c) { var s = String(c == null ? '' : c); return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }).join(','); }).join('\n');
    var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })); a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 800);
  }
  function conic(parts) { var acc = 0, total = parts.reduce(function (s, p) { return s + p.v; }, 0), segs = parts.map(function (p) { var a = acc / total * 360; acc += p.v; return p.color + ' ' + a.toFixed(1) + 'deg ' + (acc / total * 360).toFixed(1) + 'deg'; }); return 'conic-gradient(' + segs.join(',') + ')'; }
  function heat(v, max) { var a = Math.min(1, Math.abs(v) / (max || 10)); return v >= 0 ? hexA(C.pos, 0.1 + a * 0.6) : hexA(C.neg, 0.1 + a * 0.6); }
  function ensureKF() { if (document.getElementById('ql-kf')) return; var s = document.createElement('style'); s.id = 'ql-kf'; s.textContent = '@keyframes qlping{0%{transform:scale(1);opacity:.55}80%,100%{transform:scale(2.4);opacity:0}}@keyframes qlshim{0%,100%{opacity:.5}50%{opacity:1}}'; document.head.appendChild(s); }

  /* ---------- React primitives ---------- */
  var lcP = null;
  function loadLucide() { if (window.lucide && window.lucide.icons) return Promise.resolve(window.lucide); if (!lcP) lcP = new Promise(function (res, rej) { var s = document.createElement('script'); s.src = 'https://unpkg.com/lucide@0.460.0/dist/umd/lucide.min.js'; s.onload = function () { res(window.lucide); }; s.onerror = function () { lcP = null; rej(); }; document.head.appendChild(s); }); return lcP; }
  var ALIAS = { 'chart-candlestick': ['CandlestickChart'], 'chart-pie': ['PieChart'], 'circle-play': ['PlayCircle'], 'triangle-alert': ['AlertTriangle'], 'ellipsis': ['MoreHorizontal'], 'circle-check': ['CheckCircle2', 'CheckCircle'], 'circle-x': ['XCircle'], 'circle-alert': ['AlertCircle'], 'chart-line': ['LineChart'], 'chart-column': ['BarChart3'], 'chart-scatter': ['ScatterChart'] };
  function pascal(n) { return n.split('-').map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); }).join(''); }
  function toSvg(node, size, stroke) {
    var NS = 'http://www.w3.org/2000/svg', svg = document.createElementNS(NS, 'svg');
    [['width', size], ['height', size], ['viewBox', '0 0 24 24'], ['fill', 'none'], ['stroke', 'currentColor'], ['stroke-width', stroke], ['stroke-linecap', 'round'], ['stroke-linejoin', 'round']].forEach(function (a) { svg.setAttribute(a[0], a[1]); });
    var kids = node; if (node && node[0] === 'svg') kids = node[2] || [];
    (kids || []).forEach(function (k) { var el = document.createElementNS(NS, k[0]); var at = k[1] || {}; Object.keys(at).forEach(function (key) { el.setAttribute(key, at[key]); }); svg.appendChild(el); });
    return svg;
  }
  function Icon(p) {
    var React = window.React, ref = React.useRef(null), size = +(p.size || 16), stroke = p.stroke || 1.75, name = p.icon || p.name || 'circle';
    React.useEffect(function () {
      var dead = false;
      loadLucide().then(function (L) {
        if (dead || !ref.current) return;
        var reg = L.icons || L, node = reg[pascal(name)] || L[pascal(name)];
        if (!node && ALIAS[name]) ALIAS[name].some(function (a) { node = reg[a] || L[a]; return !!node; });
        ref.current.innerHTML = ''; if (node) ref.current.appendChild(toSvg(node, size, stroke));
      }).catch(function () { });
      return function () { dead = true; };
    }, [name, size, stroke]);
    return React.createElement('span', { ref: ref, 'aria-hidden': true, style: Object.assign({ display: 'inline-flex', width: size, height: size, color: p.color || 'currentColor', flexShrink: 0, lineHeight: 0 }, p.style || {}) });
  }
  function Spark(p) {
    var h = window.React.createElement, v = p.values || [], H = +(p.height || 28);
    if (v.length < 2) return h('div', { style: { height: H } });
    var mn = Math.min.apply(null, v), mx = Math.max.apply(null, v);
    var pts = v.map(function (x, i) { return (i / (v.length - 1) * 100).toFixed(2) + ',' + (28 - (mx === mn ? 0.5 : (x - mn) / (mx - mn)) * 26).toFixed(2); });
    var col = p.color || (v[v.length - 1] >= v[0] ? C.pos : C.neg);
    return h('svg', { viewBox: '0 0 100 30', preserveAspectRatio: 'none', width: '100%', height: H, style: { display: 'block', overflow: 'visible' } },
      p.fill === false ? null : h('path', { d: 'M0,30 L' + pts.join(' L') + ' L100,30 Z', fill: hexA(col, 0.12), stroke: 'none' }),
      h('polyline', { points: pts.join(' '), fill: 'none', stroke: col, strokeWidth: 1.5, vectorEffect: 'non-scaling-stroke', strokeLinejoin: 'round' }));
  }
  function LiveDot(p) {
    ensureKF(); var h = window.React.createElement, c = p.color || C.pos, s = +(p.size || 8);
    return h('span', { style: { position: 'relative', display: 'inline-flex', width: s, height: s, flexShrink: 0 } },
      p.pulse === false ? null : h('span', { style: { position: 'absolute', inset: 0, borderRadius: 99, background: c, animation: 'qlping 1.6s cubic-bezier(0,0,.2,1) infinite' } }),
      h('span', { style: { position: 'relative', width: '100%', height: '100%', borderRadius: 99, background: c } }));
  }
  function Skel(p) { ensureKF(); return window.React.createElement('div', { style: { height: p.h || 14, width: p.w || '100%', borderRadius: p.r || 6, background: '#1B2435', animation: 'qlshim 1.4s ease-in-out infinite' } }); }

  var lwP = null;
  function loadLW() { if (window.LightweightCharts) return Promise.resolve(window.LightweightCharts); if (!lwP) lwP = new Promise(function (res, rej) { var s = document.createElement('script'); s.src = 'https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js'; s.onload = function () { res(window.LightweightCharts); }; s.onerror = function () { lwP = null; rej(); }; document.head.appendChild(s); }); return lwP; }
  function pfmt(kind, ref) {
    if (kind === 'usd') return { type: 'custom', minMove: 0.01, formatter: function (v) { return fmt.usd(v); } };
    if (kind === 'pct') return { type: 'custom', minMove: 0.01, formatter: function (v) { return v.toFixed(2) + '%'; } };
    if (kind === 'num') return { type: 'custom', minMove: 0.01, formatter: function (v) { return v.toFixed(2); } };
    var d = ref >= 10 ? 2 : ref >= 1 ? 3 : 4; return { type: 'price', precision: d, minMove: Math.pow(10, -d) };
  }
  function fmtVal(kind, v) { return kind === 'usd' ? fmt.usd(v) : kind === 'pct' ? fmt.pct(v) : kind === 'num' ? v.toFixed(2) : fmt.price(v); }
  var RANGES = [['1O', 30], ['3O', 90], ['6O', 180], ['Barchasi', 0]];

  function Chart(p) {
    var React = window.React, h = React.createElement;
    var box = React.useRef(null), S = React.useRef({ chart: null, list: [], sig: '' });
    var a = React.useState(false), ready = a[0], setReady = a[1];
    var b = React.useState(null), leg = b[0], setLeg = b[1];
    var c = React.useState(p.range || 'Barchasi'), range = c[0], setRange = c[1];
    var d = React.useState(false), err = d[0], setErr = d[1];
    var tk = React.useState(0), setTk = tk[1];
    var height = +(p.height || 260), kind = p.fmt || 'price';
    function specs() {
      var out = [];
      if (p.candles) {
        out.push({ kind: 'candles', data: p.candles, name: p.name || '' });
        if (p.volume) out.push({ kind: 'volume', name: 'Hajm', data: p.candles.map(function (k) { return { time: k.time, value: k.volume, color: k.close >= k.open ? 'rgba(22,199,132,.3)' : 'rgba(234,57,67,.3)' }; }) });
        (p.overlays || []).forEach(function (o) { out.push({ kind: 'line', name: o.name, color: o.color, data: o.data, width: 1, noLast: true }); });
      } else if (p.series) { p.series.forEach(function (s) { out.push({ kind: s.kind || p.kind || 'line', name: s.name, color: s.color, data: s.data || [], width: s.width, dashed: s.dashed }); }); }
      else if (p.data) out.push({ kind: p.kind || 'area', name: p.name || '', color: p.color || C.accent, data: p.data });
      return out;
    }
    function create(ch, sp) {
      var ref = sp.data && sp.data.length ? (sp.data[sp.data.length - 1].close || sp.data[sp.data.length - 1].value || 1) : 1, f = pfmt(kind, Math.abs(ref));
      if (sp.kind === 'candles') return ch.addCandlestickSeries({ upColor: C.pos, downColor: C.neg, borderVisible: false, wickUpColor: C.pos, wickDownColor: C.neg, priceFormat: f });
      if (sp.kind === 'volume') { var v = ch.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol', priceLineVisible: false, lastValueVisible: false }); v.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } }); return v; }
      if (sp.kind === 'area') return ch.addAreaSeries({ lineColor: sp.color, topColor: hexA(sp.color, 0.26), bottomColor: hexA(sp.color, 0.01), lineWidth: 2, priceLineVisible: false, priceFormat: f });
      if (sp.kind === 'hist') return ch.addHistogramSeries({ color: sp.color || C.accent, priceLineVisible: false, priceFormat: f });
      if (sp.kind === 'baseline') return ch.addBaselineSeries({ baseValue: { type: 'price', price: 0 }, topLineColor: C.pos, topFillColor1: hexA(C.pos, 0.22), topFillColor2: hexA(C.pos, 0.02), bottomLineColor: C.neg, bottomFillColor1: hexA(C.neg, 0.02), bottomFillColor2: hexA(C.neg, 0.25), lineWidth: 2, priceLineVisible: false, priceFormat: f });
      return ch.addLineSeries({ color: sp.color || C.accent, lineWidth: sp.width || 2, lineStyle: sp.dashed ? 2 : 0, priceLineVisible: false, lastValueVisible: !sp.noLast, crosshairMarkerRadius: 3, priceFormat: f });
    }
    function legendFrom(get) {
      return S.current.list.filter(function (it) { return it.spec.kind !== 'volume'; }).map(function (it) {
        var dd = get(it); if (!dd) return null;
        if (it.spec.kind === 'candles') { var up = dd.close >= dd.open; return { name: it.spec.name, text: 'O ' + fmt.price(dd.open) + '  H ' + fmt.price(dd.high) + '  L ' + fmt.price(dd.low) + '  C ' + fmt.price(dd.close), tone: up ? C.pos : C.neg }; }
        return { name: it.spec.name, color: it.spec.kind === 'hist' || it.spec.kind === 'baseline' ? null : it.spec.color, text: fmtVal(kind, dd.value), tone: it.spec.kind === 'hist' || it.spec.kind === 'baseline' ? fmt.tone(dd.value) : null };
      }).filter(Boolean);
    }
    function applyRange(lbl) {
      var ch = S.current.chart, main = S.current.list[0]; if (!ch || !main) return; var dd = main.spec.data; if (!dd || !dd.length) return;
      if (p.bars) { ch.timeScale().setVisibleLogicalRange({ from: dd.length - p.bars, to: dd.length + 2 }); return; }
      var r = RANGES.filter(function (x) { return x[0] === lbl; })[0], days = r ? r[1] : 0;
      if (!days || !p.ranges) { ch.timeScale().fitContent(); return; }
      var to = dd[dd.length - 1].time, from = to - days * DAY;
      if (from <= dd[0].time) { ch.timeScale().fitContent(); return; }
      try { ch.timeScale().setVisibleRange({ from: from, to: to }); } catch (e) { ch.timeScale().fitContent(); }
    }
    React.useEffect(function () {
      var dead = false;
      loadLW().then(function (LW) {
        if (dead || !box.current) return;
        var el = box.current, w0 = el.clientWidth || (el.parentNode && el.parentNode.clientWidth) || 600;
        var ch = LW.createChart(el, {
          width: w0, height: height,
          layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#94A3B8', fontFamily: 'Manrope, "Inter Tight", system-ui, sans-serif', fontSize: 11 },
          grid: { vertLines: { color: C.grid }, horzLines: { color: C.grid } },
          rightPriceScale: { borderColor: C.border, scaleMargins: { top: 0.14, bottom: p.volume ? 0.2 : 0.08 } },
          timeScale: { borderColor: C.border, timeVisible: !!p.intraday, secondsVisible: false, rightOffset: p.live ? 4 : 1 },
          crosshair: { mode: 0, vertLine: { color: '#475569', width: 1, style: 2, labelBackgroundColor: '#1B2435' }, horzLine: { color: '#475569', width: 1, style: 2, labelBackgroundColor: '#1B2435' } },
          localization: { locale: 'en-US', dateFormat: 'dd.MM.yyyy' },
          handleScroll: !p.static, handleScale: !p.static
        });
        S.current.chart = ch;
        var fit = function () { var ww = el.clientWidth; if (ww > 0 && S.current.chart) S.current.chart.resize(ww, height); };
        var ro = window.ResizeObserver ? new ResizeObserver(fit) : null; if (ro) ro.observe(el);
        window.addEventListener('resize', fit); var t1 = setTimeout(fit, 120), t2 = setTimeout(fit, 600);
        S.current.off = function () { if (ro) ro.disconnect(); window.removeEventListener('resize', fit); clearTimeout(t1); clearTimeout(t2); };
        ch.subscribeCrosshairMove(function (param) { if (!param || !param.time || !param.seriesData) { setLeg(null); return; } setLeg(legendFrom(function (it) { return param.seriesData.get(it.series); })); });
        setReady(true);
      }).catch(function () { if (!dead) setErr(true); });
      return function () { dead = true; if (S.current.off) S.current.off(); if (S.current.chart) S.current.chart.remove(); S.current = { chart: null, list: [], sig: '' }; };
    }, []);
    React.useEffect(function () {
      var ch = S.current.chart; if (!ready || !ch) return;
      var sp = specs(), sig = sp.map(function (s) { return s.kind + '|' + s.name + '|' + s.color; }).join(';'), inc = !!p.live && sig === S.current.sig && S.current.key === p.dataKey;
      S.current.key = p.dataKey;
      if (sig !== S.current.sig) { S.current.list.forEach(function (it) { ch.removeSeries(it.series); }); S.current.list = sp.map(function (s) { return { spec: s, series: create(ch, s), len: 0 }; }); S.current.sig = sig; inc = false; }
      S.current.list.forEach(function (it, i) {
        var dd = sp[i].data || []; it.spec = sp[i];
        if (inc && it.len && dd.length >= it.len && dd.length - it.len <= 1) it.series.update(dd[dd.length - 1]); else it.series.setData(dd);
        it.len = dd.length;
      });
      var main = S.current.list[0]; if (main && main.series.setMarkers) main.series.setMarkers((p.markers || []).slice().sort(function (x, y) { return x.time - y.time; }));
      if (!inc) { applyRange(range); setLeg(null); }
      setTk(function (x) { return x + 1; });
    }, [ready, p.data, p.series, p.candles, p.overlays, p.markers, p.volume, p.dataKey]);
    React.useEffect(function () { if (ready) applyRange(range); }, [range]);
    var items = leg || (ready ? legendFrom(function (it) { var dd = it.spec.data; return dd && dd[dd.length - 1]; }) : []);
    var btn = function (r) { var on = r[0] === range; return h('button', { key: r[0], onClick: function () { setRange(r[0]); }, style: { border: 0, cursor: 'pointer', fontFamily: 'Manrope, sans-serif', fontSize: 11, fontWeight: 600, padding: '3px 8px', borderRadius: 4, background: on ? '#263244' : 'transparent', color: on ? '#F1F5F9' : '#94A3B8' } }, r[0]); };
    return h('div', { style: { position: 'relative', width: '100%', height: height } },
      h('div', { ref: box, style: { position: 'absolute', inset: 0 } }),
      p.legend !== false && items.length ? h('div', { style: { position: 'absolute', top: 2, left: 2, zIndex: 3, display: 'flex', flexWrap: 'wrap', gap: '4px 6px', pointerEvents: 'none', fontFamily: 'Manrope, sans-serif', fontSize: 11, color: '#94A3B8', maxWidth: p.ranges ? 'calc(100% - 260px)' : 'calc(100% - 70px)' } },
        items.map(function (it, i) { return h('span', { key: i, style: { display: 'inline-flex', alignItems: 'center', gap: 6, background: 'rgba(11,15,25,.78)', padding: '2px 6px', borderRadius: 4, whiteSpace: 'nowrap' } }, it.color ? h('span', { style: { width: 8, height: 8, borderRadius: 2, background: it.color } }) : null, it.name ? h('span', null, it.name) : null, h('span', { style: { color: it.tone || '#F1F5F9', fontWeight: 600, fontVariantNumeric: 'tabular-nums' } }, it.text)); })) : null,
      p.ranges ? h('div', { style: { position: 'absolute', top: 0, right: 62, zIndex: 3, display: 'flex', gap: 2, background: '#111827', border: '1px solid #263244', borderRadius: 6, padding: 2 } }, RANGES.map(btn)) : null,
      !ready && !err ? h('div', { style: { position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94A3B8', fontSize: 12, fontFamily: 'Manrope, sans-serif' } }, 'Grafik yuklanmoqda…') : null,
      err ? h('div', { style: { position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#EA3943', fontSize: 12, fontFamily: 'Manrope, sans-serif' } }, 'Grafik kutubxonasi yuklanmadi. Internet aloqasini tekshiring.') : null);
  }

  window.QL = {
    C: C, PALETTE: PALETTE, DAY: DAY, HOUR: HOUR, END: END, NOW: NOW, TF: TF, MON: MON,
    fmt: fmt, rng: rng, gauss: gauss, hash: hash, hexA: hexA, avg: avg, std: std, series: series, ddOf: ddOf, maxDD: maxDD, monthlyOf: monthlyOf,
    ind: { ema: ema, sma: sma, rsi: rsi, boll: boll, macd: macd }, toSeries: toSeries,
    NAV: NAV, status: status, STRATS: STRATS, strat: function (id) { return SMAP[id] || STRATS[0]; }, MARKETS: MARKETS, MK: MK,
    candles: candles, runBT: runBT, btDefaults: btDefaults, portfolio: portfolio, SESS: SESS, sessTrades: sessTrades, sessEvents: sessEvents,
    trades: trades, MODELS: MODELS, FEATURES: FEATURES, JOBS: JOBS, optimizer: optimizer, BACKTESTS: BACKTESTS, NOTIFS: NOTIFS,
    stream: stream, api: api, downloadCSV: downloadCSV, conic: conic, heat: heat,
    Chart: Chart, Spark: Spark, Icon: Icon, LiveDot: LiveDot, Skel: Skel
  };
  loadLucide().catch(function () { }); loadLW().catch(function () { });
})();
