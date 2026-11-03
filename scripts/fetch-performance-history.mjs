#!/usr/bin/env node
// fetch-performance-history.mjs — 一次性回捞脚本：绩效分析所需全量历史数据（只读查询，遵守只读红线）。
// 依据 probe-status-params.mjs 探测结论（2026-10-10）：
//   出货 created_at 数组有效（全量4467）；采购 buy_status 1=待采购 2=部分采购 3=采购完成（全2953）；
//   跟单 status 3=已完成（2779）；入库 stockin_status 3=全部入库（4285）
// 落盘 data/raw/2026-10-10/pm/perf_*.jsonl，供 build-performance-report.mjs 消费。
import fs from 'node:fs';
import path from 'node:path';
import { harvestAuth } from './harvest-auth.mjs';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
// 输出目录：固定沿用已有 perf 基础目录（存在则复用，否则按当天新建）——可移植
const legacy = path.join(root, 'data', 'raw', '2026-10-10', 'pm');
let outDir = legacy;
if (!fs.existsSync(path.join(legacy, 'perf_purchase_all.jsonl'))) {
  // 找已有 perf 目录，无则当天新建
  const hits = [];
  const walk = d => { try { fs.readdirSync(d, { withFileTypes: true }).forEach(e => { const p = path.join(d, e.name); if (e.isDirectory()) walk(p); else if (e.name === 'perf_purchase_all.jsonl') hits.push(path.dirname(p)); }); } catch {} };
  walk(path.join(root, 'data', 'raw'));
  if (hits.length) { hits.sort((a, b) => fs.statSync(path.join(b, 'perf_purchase_all.jsonl')).mtimeMs - fs.statSync(path.join(a, 'perf_purchase_all.jsonl')).mtimeMs); outDir = hits[0]; }
  else outDir = path.join(root, 'data', 'raw', new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }), 'pm');
}
fs.mkdirSync(outDir, { recursive: true });
const timeoutMs = 30000;
const pageMax = 300; // 单端点最大页数保护
const intervalMs = 250; // 相邻请求最小间隔

let auth = null;
const h = await harvestAuth({}).catch(() => ({}));
if (h.yizhe?.ok) auth = h.yizhe.creds;
if (!auth) {
  try {
    const cache = JSON.parse(fs.readFileSync(path.join(root, 'state', 'auth.json'), 'utf8'));
    if (cache.yizhe?.ok) auth = cache.yizhe.creds;
  } catch {}
}
if (!auth) { console.error('[perf] 衣者凭据不可得 → 转登录阻断流程'); process.exit(1); }

const base = 'https://api.yizheyun.com';
let nextFire = Date.now();
async function call(api, params) {
  const at = Math.max(nextFire, Date.now()); nextFire = at + intervalMs;
  const wait = at - Date.now(); if (wait > 0) await new Promise(r => setTimeout(r, wait));
  const body = { token: auth.token, cid: auth.cid, uid: auth.uid, plate_type: 'backend', v: auth.v, cv: auth.cv, ...params };
  const res = await fetch(base + api, {
    method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://scm.yizheyun.com', referer: 'https://scm.yizheyun.com/' },
    body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs),
  });
  const j = await res.json().catch(() => null);
  if (!j || String(j.code) !== '200') throw new Error(`${api} code=${j?.code} ${j?.msg || '非JSON'}`);
  return j;
}

// 通用全量拉取：探明 total 后按页顺序拉取（串行+节奏，避免风控）
async function fetchAll(name, api, baseParams, pageSize = 100) {
  const rows = [];
  let page = 1, total = null;
  while (page <= pageMax) {
    const j = await call(api, { page, page_size: pageSize, current: page, pageSize, ...baseParams });
    const list = j?.data?.list || [];
    total = j?.data?.total ?? total;
    rows.push(...list);
    if (list.length === 0) break;
    if (total != null && rows.length >= Number(total)) break;
    if (list.length < pageSize) break;
    page++;
  }
  const file = path.join(outDir, `perf_${name}.jsonl`);
  fs.writeFileSync(file, rows.map(r => JSON.stringify(r)).join('\n') + '\n');
  const truncated = total != null && rows.length < Number(total);
  console.log(`[perf] ${name}: ${rows.length} 行${total != null ? `/${total}` : ''}${truncated ? ' ⚠️截断' : ''} → ${path.basename(file)}`);
  return { name, rows: rows.length, total, truncated };
}

// —— 全量回捞（历史一次性，后续日增量即可） ——
const results = [];
results.push(await fetchAll('stockout_all', '/common/stockout_panel/record_list', { status_list: 2 }, 100));           // 全量出货 4467
results.push(await fetchAll('purchase_all', '/common/purchase/get_purchase_list', { buy_status_list: [], reach_status_list: [] }, 100)); // 全状态采购 2953
results.push(await fetchAll('follow_done', '/common/follow_order/get_follow_order_list', { status_list: [3] }, 100));     // 已完成跟单 2779
results.push(await fetchAll('follow_active', '/common/follow_order/get_follow_order_list', { status_list: [1, 2] }, 100));// 在产跟单 194
results.push(await fetchAll('instock_done', '/common/instock/get_instock_list', { status_list: [3] }, 100));              // 已入库 4285
results.push(await fetchAll('template_all', '/common/template/get_template_list', { empty_bom_warn: 2, current_step_ids: [], wait_step_ids: [], done_step_ids: [] }, 100)); // 样板全量

// —— 汇总校验：判断数据是否够 9 月月报 ——
const readRows = f => fs.readFileSync(path.join(outDir, f), 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
const stockout = readRows('perf_stockout_all.jsonl');
const months = {};
for (const r of stockout) {
  const m = (r.stockout_at || r.created_at || '').slice(0, 7);
  if (m) months[m] = (months[m] || 0) + 1;
}
const monthKeys = Object.keys(months).sort().reverse().slice(0, 4);
console.log('\n[perf] 出货记录月度分布(近4月):', JSON.stringify(Object.fromEntries(monthKeys.map(k => [k, months[k]]))));

const done = readRows('perf_follow_done.jsonl');
const doneMonths = {};
for (const r of done) {
  const m = (r.finish_time || '').slice(0, 7);
  if (m && m !== '0000-0') doneMonths[m] = (doneMonths[m] || 0) + 1;
}
console.log('[perf] 已完成跟单月度分布(近4月):', JSON.stringify(Object.fromEntries(Object.keys(doneMonths).sort().reverse().slice(0, 4).map(k => [k, doneMonths[k]]))));
console.log('[perf] 回捞完成');
