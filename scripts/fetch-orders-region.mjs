#!/usr/bin/env node
// fetch-orders-region.mjs — 一次性分析脚本：拉取近30日全量销售订单（含收件信息），用于地区×品类补货分析。
// 复用 fetch-endpoints.mjs 的凭据收割与请求构造逻辑（只读查询接口 order/new_view_all，遵守只读红线）。
// 用法：node scripts/fetch-orders-region.mjs [--days 30] [--out data/raw/2026-09-28/am/duoke_orders_30d.jsonl]
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';
import { harvestAuth } from './harvest-auth.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i++) {
  const t = argv[i].replace(/^--/, '');
  if (t.includes('=')) { const [k, v] = t.split('='); args[k] = v; }
  else if (argv[i + 1] && !argv[i + 1].startsWith('--')) { args[t] = argv[i + 1]; i++; }
  else args[t] = true;
}
const days = Number(args.days || 30);
const today = new Date();
const fmt = dt => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
const dayOff = n => { const dt = new Date(today); dt.setDate(dt.getDate() + n); return fmt(dt); };
const sday = dayOff(-(days - 1));
const eday = dayOff(0);
const outPath = args.out || path.join(dataHome, 'data', 'raw', '2026-09-28', 'am', `duoke_orders_${days}d.jsonl`);
const timeoutMs = 30000;

// —— 凭据：实时收割优先，回落缓存（12h内有效） ——
const rules = JSON.parse(fs.readFileSync(path.join(root, 'config', 'rules.json'), 'utf8'));
const cacheHours = rules['直连采集']?.['凭据缓存有效期小时'] ?? 12;
let auth = null;
const h = await harvestAuth({}).catch(() => ({}));
if (h.duoke?.ok) auth = { creds: h.duoke.creds, from: '实时收割' };
if (!auth) {
  try {
    const cache = JSON.parse(fs.readFileSync(path.join(dataHome, 'state', 'auth.json'), 'utf8'));
    const fresh = (Date.now() - new Date(cache.harvested_at).getTime()) < cacheHours * 3600e3;
    if (fresh && cache.duoke?.ok) auth = { creds: cache.duoke.creds, from: `缓存(${cache.harvested_at})` };
  } catch {}
}
if (!auth) { console.error('[region] 多客凭据不可得（未登录且缓存失效）→ 转登录阻断流程（硬停）'); process.exit(1); }
console.log(`[region] 多客凭据：${auth.from}`);

const c = auth.creds;
const base = 'https://api.duoke.net/index.php';
const params = {
  lang: 'chs', key: c.key, bi_key: 'documentList', type: 'custom',
  sday, eday,
  order_type: '{"options":["sale_order"],"allSelected":0}',
  keyword: '',
  page: 1, page_size: 20,
};

// 第1页探明总量，后续并发翻页
async function fetchPage(page) {
  const url = new URL(base + '/order/new_view_all');
  const q = { ...params, page };
  for (const [k, v] of Object.entries(q)) url.searchParams.set(k, String(v));
  const res = await fetch(url, { headers: { origin: 'https://air.duoke.net', referer: 'https://air.duoke.net/' }, signal: AbortSignal.timeout(timeoutMs) });
  const text = await res.text();
  let j; try { j = JSON.parse(text); } catch { throw new Error('响应非JSON'); }
  if (j.err !== undefined && Number(j.err) !== 0) throw new Error(`err=${j.err} ${j.msg || ''}`);
  return j;
}

const p1 = await fetchPage(1);
const total = Number(p1.list_num ?? p1.total ?? (p1.list || []).length);
console.log(`[region] 窗口 ${sday}~${eday} 共 ${total} 单`);
if (!total) { console.log('[region] 无订单，退出'); process.exit(0); }

const rows = [...(p1.list || [])];
const pages = Math.ceil(total / 20);
console.log(`[region] 翻页 ${pages} 页（20/页），并发3、间隔300ms …`);
const sem = (() => { let a = 0; const w = []; return { acq: () => a < 3 ? (a++, Promise.resolve()) : new Promise(r => w.push(r)), rel: () => { const x = w.shift(); if (x) x(); else a--; } }; })();
let nextFire = Date.now();
const out = [];
const results = await Promise.allSettled(Array.from({ length: pages - 1 }, (_, i) => i + 2).map(async pg => {
  const at = Math.max(nextFire, Date.now()); nextFire = at + 100;
  const wait = at - Date.now(); if (wait > 0) await new Promise(r => setTimeout(r, wait));
  await sem.acq();
  try { return { pg, j: await fetchPage(pg) }; } finally { sem.rel(); }
}));
for (const r of results) {
  if (r.status === 'fulfilled') out[r.value.pg - 1] = r.value.j.list || [];
  else console.error(`[region] 第?页失败: ${r.reason?.message || r.reason}`);
}
const all = [...rows, ...out.filter(Boolean).flat()];
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, all.map(r => JSON.stringify(r)).join('\n') + '\n');
console.log(`[region] 落盘 ${all.length}/${total} 单 → ${outPath}`);
if (all.length < total) { console.error(`[region] ⚠️ 缺 ${total - all.length} 单（失败页）`); process.exit(2); }

// 首单字段结构披露
console.log('[region] 订单字段:', Object.keys(all[0] || {}).join(', '));
