#!/usr/bin/env node
// fetch-endpoints.mjs — 直连采集器（默认采集路径。2026-09-24用户批准解除"脚本禁止直连源系统API"禁令）。
// 流程：先经CDP收割专用浏览器实时登录凭据（harvest-auth.mjs：Runtime.evaluate直读localStorage快路径，
// 网络被动监听回落；浏览器仍是唯一登录态持有者，本脚本不登录、不存账号密码）→ 按批次映射 endpoints.json 端点 →
// 机器速度直调两系统**只读查询**接口 → 按页落盘 data/raw/<date>/<slot>/（.json=响应原文 / .jsonl=list_path行数组），
// 落盘契约与浏览器采集完全一致，下游 ingest 链路零改动。
// 用法：node scripts/fetch-endpoints.mjs [--date YYYY-MM-DD] [--slot am|pm] [--batch morning|noon|evening|poll|weekly|first]
//        [--only 文件名,…] [--dry-run] [--interval 毫秒] [--max-pages N] [--workers N] [--port 9222]
// 提速设计：① 大列表 page_size 调大（衣者500/页，终止以响应total驱动，服务端cap每页条数也能正确续页）；
// ② 端点内并发翻页——第1页探明total与实际每页条数后按波并发发页、按页序落盘（终止语义与串行版一致：
//    空页=尾页/无total短页=尾页/rows≥total=尾页/达最大页数截断；波内失败页之后的页丢弃不写，文件保持成功前缀）；
// ③ 全端点并发推进 + 请求级全局信号量（并发数默认3）+ 全局出枪节奏器（相邻请求出枪间隔≥请求间隔毫秒/并发数，
//    节奏等待不占并发槽——与原「持槽静默」饱和时的均值节奏一致，槽位只承载真实I/O）。
// 输出：每端点一行结果；末行JSON总摘要。某系统凭据不可得（未登录/浏览器未启动）→ 该系统停止并退出码1（转登录阻断流程，见SKILL.md；智能体须硬停后续步骤）
import fs from 'node:fs';
import path from 'node:path';
import { harvestAuth } from './harvest-auth.mjs';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i++) {
  const t = argv[i].replace(/^--/, '');
  if (t.includes('=')) { const [k, v] = t.split('='); args[k] = v; }
  else if (argv[i + 1] && !argv[i + 1].startsWith('--')) { args[t] = argv[i + 1]; i++; }
  else args[t] = true;
}
const date = args.date || new Date().toISOString().slice(0, 10);
const hour = new Date().getHours();
const slot = args.slot || (hour >= 14 ? 'pm' : 'am'); // 与 ingest.mjs 槽位口径一致
const batch = args.batch || (slot === 'am' ? 'morning' : 'evening');
const dryRun = !!args['dry-run'];
const T0 = Date.now();
const only = args.only ? String(args.only).split(',').map(s => s.trim()) : null;

const cfg = JSON.parse(fs.readFileSync(path.join(root, 'config', 'endpoints.json'), 'utf8'));
const rules = JSON.parse(fs.readFileSync(path.join(root, 'config', 'rules.json'), 'utf8'));
const DIRECT = rules['直连采集'] || {};
const interval = Number(args.interval ?? DIRECT['请求间隔毫秒'] ?? 300);
const maxPages = Number(args['max-pages'] ?? DIRECT['单端点最大页数'] ?? 300);
const timeoutMs = Number(DIRECT['请求超时毫秒'] ?? 30000);
const cacheHours = Number(DIRECT['凭据缓存有效期小时'] ?? 12);
const cdpPort = Number(args.port ?? DIRECT['调试端口'] ?? 9222);
const workers = Math.max(1, Number(args.workers ?? DIRECT['并发数'] ?? 3));

// —— 批次→端点映射（与SKILL.md「批次与采集范围」一致） ——
const NOON_FILES = ['yizhe_follow_orders.jsonl', 'yizhe_production_list.jsonl', 'yizhe_purchase_list.jsonl', 'yizhe_instock_list.jsonl'];
const BATCH = {
  morning: { tiers: ['poll', 'morning', 'increment'] },
  noon: { files: NOON_FILES },
  evening: { tiers: ['poll', 'morning', 'increment', 'snapshot', 'detail'] },
  poll: { tiers: ['poll'] },
  weekly: { tiers: ['weekly'], files: ['yizhe_template_list.jsonl'] },
  first: { tiers: ['poll', 'morning', 'increment', 'snapshot', 'detail', 'weekly', 'onetime'] },
};
if (!BATCH[batch]) { console.error(`[fetch] 未知批次 --batch ${batch}（可选：${Object.keys(BATCH).join('|')}）`); process.exit(2); }

// —— 日期token（本地时区安全） ——
const fmt = dt => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
const dayOff = n => { const dt = new Date(date + 'T00:00:00'); dt.setDate(dt.getDate() + n); return fmt(dt); };
const TOKENS = {
  '@today': () => dayOff(0), '@yesterday': () => dayOff(-1), '@last7': () => dayOff(-6),
  '@last365': () => dayOff(-364), '@wide': () => '2015-01-01',
  '@window_s': () => (slot === 'am' ? dayOff(-1) : dayOff(0)), // 增量时间窗：早间=昨日 / 晚间=当日
  '@window_e': () => (slot === 'am' ? dayOff(-1) : dayOff(0)),
};
const resolve = v => Array.isArray(v) ? v.map(resolve)
  : (v && typeof v === 'object') ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, resolve(x)]))
  : (typeof v === 'string' && TOKENS[v]) ? TOKENS[v]() : v;
const dig = (o, p) => (p || '').split('.').filter(Boolean).reduce((a, k) => (a == null ? a : a[k]), o);
const sleep = ms => new Promise(r => setTimeout(r, ms));

// —— 端点选择（保持注册表顺序：衣者在前、多客在后；sale_trend 依赖 goods 先采） ——
const selected = [];
for (const sys of ['yizhe', 'duoke']) {
  for (const ep of cfg[sys].endpoints) {
    const b = BATCH[batch];
    const hit = b.tiers ? b.tiers.includes(ep.tier) : (b.files || []).includes(ep.file);
    const extra = (b.tiers && (b.files || []).includes(ep.file));
    if (hit || extra) selected.push({ sys, ep });
  }
}
const picked = only ? selected.filter(({ ep }) => only.includes(ep.file)) : selected;
if (picked.length === 0) { console.error(`[fetch] 批次 ${batch} 未匹配到任何端点${only ? '（--only 过滤为空？）' : ''}`); process.exit(2); }

// —— 凭据：实时收割优先，CDP不可用时回落 state/auth.json 缓存（限缓存有效期） ——
let auth = { yizhe: null, duoke: null };
if (!dryRun) {
  console.log(`[fetch] ${date}/${slot} 批次=${batch}，端点${picked.length}个；先收割浏览器凭据（DevTools端口自动发现，优先${cdpPort}）…`);
  const h = await harvestAuth({ port: cdpPort }).catch(e => ({ yizhe: { ok: false, reason: e.message }, duoke: { ok: false, reason: e.message } }));
  for (const k of ['yizhe', 'duoke']) {
    if (h[k]?.ok) auth[k] = { creds: h[k].creds, from: '实时收割' };
  }
  if (!auth.yizhe || !auth.duoke) {
    try {
      const cache = JSON.parse(fs.readFileSync(path.join(root, 'state', 'auth.json'), 'utf8'));
      const fresh = (Date.now() - new Date(cache.harvested_at).getTime()) < cacheHours * 3600e3;
      for (const k of ['yizhe', 'duoke']) {
        if (!auth[k] && fresh && cache[k]?.ok) {
          auth[k] = { creds: cache[k].creds, from: `缓存(${cache.harvested_at})` };
          console.log(`  ${k}：实时收割失败（${h[k]?.reason || '未知'}），回落${auth[k].from}`);
        }
      }
    } catch {}
  }
  for (const k of ['yizhe', 'duoke']) if (auth[k]) console.log(`  ${k === 'yizhe' ? '衣者' : '多客'}凭据：${auth[k].from}`);
}
const authDead = {}; // 运行中判定登录态失效（首个请求即auth语义错误）→ 停该系统剩余端点
const AUTH_ERR = /登录|登陆|token|过期|失效|授权|auth|key/i;

// —— 全局限流：请求级信号量（并发数=workers个请求同时在途）+ 出枪节奏器
//    （相邻请求出枪间隔≥请求间隔毫秒/workers，节奏等待不占并发槽；与原「持槽静默请求间隔毫秒」饱和时的均值节奏一致）——
const sem = (() => {
  let active = 0; const waiters = [];
  return {
    acq: () => active < workers ? (active++, Promise.resolve()) : new Promise(r => waiters.push(r)),
    rel: () => { const w = waiters.shift(); if (w) w(); else active--; },
  };
})();
let nextFire = Date.now();
const paceReserve = () => { const at = Math.max(nextFire, Date.now()); nextFire = at + Math.max(1, Math.round(interval / workers)); return at; };

// —— 请求构造（衣者=POST JSON+通用参数；多客=GET查询串或POST form） ——
async function callApi(sys, ep, extraParams) {
  const c = auth[sys].creds;
  const base = cfg[sys].base_api;
  const params = { ...(resolve(ep.params) || {}), ...resolve(extraParams) };
  const fireAt = paceReserve();
  const waitMs = fireAt - Date.now();
  if (waitMs > 0) await sleep(waitMs); // 出枪节奏：等待不占并发槽
  await sem.acq();
  try {
    if (sys === 'yizhe') {
      const body = { token: c.token, cid: c.cid, uid: c.uid, plate_type: c.plate_type || 'backend', v: c.v, cv: c.cv, ...params };
      const res = await fetch(base + ep.api, {
        method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://scm.yizheyun.com', referer: 'https://scm.yizheyun.com/' },
        body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs),
      });
      return res.text();
    }
    const url = new URL(base + ep.api);
    // no_version: 该端点GET请求携带version会报9999 "bi key not exist"（2026-09-28实测payment/view_all；浏览器GET也不带version）
    const q = { lang: c.lang || 'chs', ...((c.version && !ep.no_version) ? { version: c.version } : {}), key: c.key, ...params };
    const headers = { origin: 'https://air.duoke.net', referer: 'https://air.duoke.net/' };
    if ((ep.method || 'GET').toUpperCase() === 'POST') {
      const fd = new FormData();
      for (const [k, v] of Object.entries(q)) fd.append(k, String(v));
      const res = await fetch(url, { method: 'POST', headers, body: fd, signal: AbortSignal.timeout(timeoutMs) });
      return res.text();
    }
    for (const [k, v] of Object.entries(q)) url.searchParams.set(k, String(v));
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(timeoutMs) });
    return res.text();
  } finally {
    sem.rel();
  }
}
const parseOk = (sys, text) => {
  let j = null; try { j = JSON.parse(text); } catch { return { j: null, ok: false, msg: '响应非JSON' }; }
  const ok = sys === 'yizhe' ? String(j.code) === '200' : (j.err === undefined ? true : Number(j.err) === 0);
  return { j, ok, msg: ok ? '' : `code=${j.code ?? j.err} ${j.msg || ''}` };
};

const issues = [];
const logIssue = (file, type, detail) => { issues.push({ ts: new Date().toISOString(), date, slot, batch, file, type, detail }); };
const results = [];
const rawDir = path.join(root, 'data', 'raw', date, slot);
if (!dryRun) fs.mkdirSync(rawDir, { recursive: true });

// —— 特例：多客30日动销依赖当日商品列表的goods id（分批并发拉取后按序合并落盘） ——
async function runSaleTrend(ep) {
  const goodsFile = path.join(rawDir, 'duoke_goods.jsonl');
  if (!fs.existsSync(goodsFile)) return { status: 'fail', reason: '缺依赖 duoke_goods.jsonl（先采商品列表）' };
  const ids = fs.readFileSync(goodsFile, 'utf8').trim().split('\n').filter(Boolean).map(l => { try { return JSON.parse(l).id; } catch { return null; } }).filter(Boolean).map(Number);
  const merged = {}; const batchSize = 50; let failReason = null;
  const chunks = [];
  for (let i = 0; i < ids.length; i += batchSize) chunks.push(ids.slice(i, i + batchSize));
  const settled = await Promise.allSettled(chunks.map(chunk => callApi('duoke', ep, { goods_ids: JSON.stringify(chunk) }).then(text => {
    const { j, ok, msg } = parseOk('duoke', text);
    if (!ok) throw new Error(msg);
    return j.goods || {};
  })));
  for (const r of settled) {
    if (r.status === 'fulfilled') Object.assign(merged, r.value);
    else failReason ??= String(r.reason?.message || r.reason);
  }
  if (failReason) return { status: 'fail', reason: failReason, rows: Object.keys(merged).length };
  const out = { days: 30, goods: merged };
  fs.writeFileSync(path.join(rawDir, ep.file), JSON.stringify(out, null, 1));
  return { status: 'ok', rows: Object.keys(merged).length, goods: ids.length };
}

async function runEndpoint(sys, ep) {
  const outPath = path.join(rawDir, ep.file);
  // 单对象端点（.json，无 list_path）：一次调用，响应原文落盘
  if (!ep.list_path) {
    const text = await callApi(sys, ep, {});
    const { ok, msg } = parseOk(sys, text);
    if (!ok) return { status: 'fail', reason: msg };
    fs.writeFileSync(outPath, text);
    return { status: 'ok' };
  }
  // 列表端点（.jsonl）：第1页探明 total 与实际每页条数（服务端cap如实反映）→ 端点内并发翻页：
  // 按波发页（同信号量限流）、按页序落盘（首页重写=同日重跑幂等）；终止语义与串行版一致——
  // 空页=尾页 / 无total短页=尾页 / rows≥total=尾页 / 达单端点最大页数截断；波内失败页之后的页丢弃不写
  const pageSize = Number(ep.page_size || (sys === 'yizhe' ? 100 : 20));
  const fetchPage = async page => {
    const extra = sys === 'yizhe'
      ? { page, page_size: pageSize, current: page, pageSize } // 部分老接口重复携带 antd 分页参数
      : { page, page_num: pageSize };
    const text = await callApi(sys, ep, extra);
    const { j, ok, msg } = parseOk(sys, text);
    if (!ok) throw new Error(msg);
    const arr = dig(j, ep.list_path);
    if (!Array.isArray(arr)) throw new Error(`list_path ${ep.list_path} 不是数组（接口结构变化？）`);
    return { j, arr };
  };
  let wroteFirst = false;
  const writeLines = lines => {
    const text = lines.length ? lines.join('\n') + '\n' : '';
    if (!wroteFirst) { fs.writeFileSync(outPath, text); wroteFirst = true; }
    else if (text) fs.appendFileSync(outPath, text);
  };
  let rows = 0, pages = 0, total = null, truncated = false, failReason = null, done = false;
  const accept = arr => { // 按页序收页；置done=尾页/截断，其后已取页一律丢弃不写
    writeLines(arr.map(r => JSON.stringify(r)));
    rows += arr.length; pages++;
    if (arr.length === 0) { done = true; return; } // 空页=尾页（total口径不一致时的兜底，如衣者库存total含零库存款）
    if (total != null && rows >= Number(total)) { done = true; return; } // total驱动：服务端cap每页条数也能正确续页不丢数据
    if (total == null && arr.length < pageSize) { done = true; return; } // 无total→短页=尾页（多客主要终止依据）
    if (pages >= maxPages) { truncated = true; done = true; return; }
  };
  const first = await fetchPage(1);
  total = sys === 'yizhe' ? dig(first.j, 'data.total') : (first.j.list_num ?? first.j.total_count ?? null);
  const perPage = first.arr.length; // 实际每页条数（被服务端cap时<pageSize；据此估页不漏页，行数不足下轮自动延波）
  const wave = Math.max(2, workers * 2); // 无total时的投机波宽度（短页/空页即截断，其后页丢弃）
  accept(first.arr);
  let next = 2;
  while (!done && !failReason) {
    // 有total：一次发完到total的估算剩余页（页偏小行数不足时，下轮按剩余行数自动延波）；
    // 无total：投机波推进，靠短页/空页/最大页数终止
    let waveEnd = total != null && perPage > 0 && Number.isFinite(Number(total))
      ? next - 1 + Math.ceil(Math.max(0, Number(total) - rows) / perPage)
      : next + wave - 1;
    if (!Number.isFinite(waveEnd)) break;
    if (waveEnd > maxPages) waveEnd = maxPages;
    if (waveEnd < next) break;
    const settled = await Promise.allSettled(Array.from({ length: waveEnd - next + 1 }, (_, i) => fetchPage(next + i)));
    for (const r of settled) { // allSettled保序：按页号处理，失败/尾页之后的页丢弃
      if (r.status === 'rejected') { failReason = String(r.reason?.message || r.reason); break; }
      accept(r.value.arr);
      if (done) break;
    }
    next = waveEnd + 1;
  }
  if (truncated) logIssue(ep.file, '达单端点最大页数', `已采${rows}行/${pages}页，剩余页未采（下轮续采）`);
  if (!failReason && total != null && !ep.total_relaxed && rows < Number(total)) logIssue(ep.file, '行数少于total', `落盘${rows}行 vs 响应total=${total}`);
  return failReason ? { status: 'fail', reason: failReason, rows, pages }
    : { status: 'ok', rows, pages, total: total == null ? undefined : Number(total) };
}

// —— 主循环（全端点并发推进，请求级全局信号量限流：并发数=workers，见 rules.json「直连采集」；两系统前端页面本身就并发数十XHR，3-4并发远低于正常页面负载） ——
const goodsGate = Promise.withResolvers(); // 动销依赖当日商品列表：等 goods 完成再跑
if (!picked.some(({ ep }) => ep.file === 'duoke_goods.jsonl')) goodsGate.resolve();

const runOne = async (sys, ep) => {
  const label = `${sys === 'yizhe' ? '衣者' : '多客'} ${ep.file}`;
  if (!auth[sys] || authDead[sys]) {
    const reason = authDead[sys] ? '登录态已失效（本轮停止该系统，转登录阻断流程）' : '凭据不可得（未登录或浏览器未启动）';
    console.log(`  ✗ ${label}：${reason}`);
    logIssue(ep.file, '凭据不可用', reason);
    results.push({ file: ep.file, status: 'fail', reason });
    return;
  }
  try {
    let r;
    if (ep.special === 'sale_trend') { await goodsGate.promise; r = await runSaleTrend(ep); }
    else r = await runEndpoint(sys, ep);
    if (ep.file === 'duoke_goods.jsonl') goodsGate.resolve();
    if (r.status === 'ok') {
      const cnt = r.rows != null ? ` ${r.rows}行/${r.pages || 1}页${r.total != null ? `（total=${r.total}）` : ''}` : '';
      console.log(`  ✓ ${label}${cnt}`);
    } else {
      console.log(`  ✗ ${label}：${r.reason}`);
      logIssue(ep.file, '采集失败', r.reason);
      if (AUTH_ERR.test(r.reason || '')) authDead[sys] = true; // 首个auth语义失败即停该系统，避免无效轰炸
    }
    results.push({ file: ep.file, ...r });
  } catch (e) {
    if (ep.file === 'duoke_goods.jsonl') goodsGate.resolve();
    console.log(`  ✗ ${label}：${e.message}`);
    logIssue(ep.file, '采集异常', e.message);
    results.push({ file: ep.file, status: 'fail', reason: e.message });
  }
};

if (dryRun) {
  for (const { sys, ep } of picked) {
    const params = { ...(resolve(ep.params) || {}), ...(ep.list_path ? (sys === 'yizhe' ? { page: 1, page_size: ep.page_size || 100 } : { page: 1, page_num: ep.page_size || 20 }) : {}) };
    console.log(`[dry-run] ${sys === 'yizhe' ? '衣者' : '多客'} ${ep.file} ← ${cfg[sys].base_api + ep.api} ${ep.method || (sys === 'yizhe' ? 'POST(json)' : 'GET')} ${JSON.stringify(params)} tier=${ep.tier}${ep.special ? ' special=' + ep.special : ''}`);
    results.push({ file: ep.file, status: 'planned' });
  }
} else {
  await Promise.all(picked.map(({ sys, ep }) => runOne(sys, ep))); // 全端点并发；请求由全局信号量排队，长链自动摊平
}

if (issues.length && !dryRun) {
  fs.mkdirSync(path.join(root, 'state'), { recursive: true });
  fs.appendFileSync(path.join(root, 'state', 'capture-issues.jsonl'), issues.map(i => JSON.stringify(i)).join('\n') + '\n');
}
const okCnt = results.filter(r => r.status === 'ok' || r.status === 'planned').length;
const failCnt = results.length - okCnt;
const summary = {
  ok: failCnt === 0, batch, date, slot, workers,
  elapsed_ms: dryRun ? undefined : Date.now() - T0,
  auth: { yizhe: !!auth.yizhe && !authDead.yizhe, duoke: !!auth.duoke && !authDead.duoke },
  fetched: okCnt, failed: failCnt, issues: issues.length,
  files: results.filter(r => r.status === 'ok').map(r => r.file),
};
console.log(JSON.stringify(summary));
process.exit(failCnt === results.length && results.length > 0 ? 1 : 0); // 全军覆没→1；部分失败靠issue披露
