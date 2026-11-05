#!/usr/bin/env node
// fetch-payments-year.mjs — 一次性分析脚本：拉取近N天全量收支流水（payment/view_all，只读查询接口，遵守只读红线）。
// 用于客户年回款分档（ABCD）分析。复用 harvest-auth.mjs 凭据收割与 fetch-orders-region.mjs 的请求构造模式。
// 用法：node scripts/fetch-payments-year.mjs [--days 365 | --sday 2025-01-01 --eday 2026-10-09]
//        [--out data/raw/<date>/<slot>/duoke_payments_365d.jsonl] [--workers 3] [--interval 300]
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
const days = Number(args.days || 0);
const today = new Date();
const fmt = dt => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
const dayOff = n => { const dt = new Date(today); dt.setDate(dt.getDate() + n); return fmt(dt); };
const sday = args.sday || (days ? dayOff(-(days - 1)) : dayOff(-364));
const eday = args.eday || dayOff(0);
const outPath = args.out || path.join(dataHome, 'data', 'raw', fmt(today), 'pm', `duoke_payments_${sday}_${eday}.jsonl`);
const timeoutMs = 30000;
const workers = Number(args.workers || 3);
const interval = Number(args.interval || 300);

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
if (!auth) { console.error('[pay365] 多客凭据不可得（未登录且缓存失效）→ 转登录阻断流程（硬停）'); process.exit(1); }
console.log(`[pay365] 多客凭据：${auth.from}`);

const c = auth.creds;
const base = 'https://api.duoke.net/index.php';
const params = {
  lang: 'chs', key: c.key, bi_key: 'billList', type: 'custom',
  sday, eday,
  keyword: '',
  page: 1, page_size: 20,
};
// 注：payment/view_all 为 no_version 端点（GET 带 version 会报 9999 bi key not exist，2026-09-28 实测）

// 第1页探明总量，后续并发翻页
async function fetchPage(page) {
  const url = new URL(base + '/payment/view_all');
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
console.log(`[pay365] 窗口 ${sday}~${eday} 共 ${total} 笔流水`);
if (!total) { console.log('[pay365] 无流水，退出'); process.exit(0); }

const rows = [...(p1.list || [])];
const pages = Math.ceil(total / 20);
console.log(`[pay365] 翻页 ${pages} 页（20/页），并发${workers}、间隔${interval}ms，预计 ~${Math.ceil(pages * 100 / workers / 1000 / 60)} 分钟 …`);
const sem = (() => { let a = 0; const w = []; return { acq: () => a < workers ? (a++, Promise.resolve()) : new Promise(r => w.push(r)), rel: () => { const x = w.shift(); if (x) x(); else a--; } }; })();
let nextFire = Date.now();
const out = [];
const results = await Promise.allSettled(Array.from({ length: pages - 1 }, (_, i) => i + 2).map(async pg => {
  const at = Math.max(nextFire, Date.now()); nextFire = at + Math.max(1, Math.round(interval / workers));
  const wait = at - Date.now(); if (wait > 0) await new Promise(r => setTimeout(r, wait));
  await sem.acq();
  try { return { pg, j: await fetchPage(pg) }; } finally { sem.rel(); }
}));
let failPages = 0;
for (const r of results) {
  if (r.status === 'fulfilled') out[r.value.pg - 1] = r.value.j.list || [];
  else { failPages++; console.error(`[pay365] 第?页失败: ${r.reason?.message || r.reason}`); }
}
const all = [...rows, ...out.filter(Boolean).flat()];
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, all.map(r => JSON.stringify(r)).join('\n') + '\n');
console.log(`[pay365] 落盘 ${all.length}/${total} 笔 → ${outPath}`);
if (all.length < total) { console.error(`[pay365] ⚠️ 缺 ${total - all.length} 笔（${failPages} 个失败页），可重跑补齐`); process.exit(2); }

// 结构披露：type 分布与金额合计
const stat = {};
let money = 0;
for (const r of all) {
  stat[r.type] = (stat[r.type] || 0) + 1;
  money += Number(r.price || 0);
}
console.log('[pay365] type 分布:', JSON.stringify(stat), '金额合计:', money.toFixed(2));
console.log('[pay365] 流水字段:', Object.keys(all[0] || {}).join(', '));
