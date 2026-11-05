#!/usr/bin/env node
// fetch-cost-month.mjs — 回捞指定月份的成本核算数据（财务对账-按订单核对）+ 采购单（含采购员归属）
// 用法：node scripts/fetch-cost-month.mjs [2026-09]
// 只读查询；落盘 data/raw/<today>/pm/perf_cost_<month>.jsonl + perf_purchase_<month>.jsonl
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const month = process.argv[2] || '2026-09';
const [y, m] = month.split('-').map(Number);
const lastDay = new Date(y, m, 0).getDate();
const start = `${month}-01`, end = `${month}-${String(lastDay).padStart(2, '0')}`;

const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' });
const outDir = path.join(dataHome, 'data', 'raw', today, 'pm');
fs.mkdirSync(outDir, { recursive: true });

const auth = JSON.parse(fs.readFileSync(path.join(dataHome, 'state', 'auth.json'), 'utf8')).yizhe.creds;
const base = 'https://api.yizheyun.com';
let nextFire = Date.now();
async function call(api, params) {
  const at = Math.max(nextFire, Date.now()); nextFire = at + 250;
  const wait = at - Date.now(); if (wait > 0) await new Promise(r => setTimeout(r, wait));
  const body = { token: auth.token, cid: auth.cid, uid: auth.uid, plate_type: 'backend', v: auth.v, cv: auth.cv, ...params };
  const res = await fetch(base + api, {
    method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://scm.yizheyun.com', referer: 'https://scm.yizheyun.com/' },
    body: JSON.stringify(body), signal: AbortSignal.timeout(30000),
  });
  const j = await res.json().catch(() => null);
  if (!j || String(j.code) !== '200') throw new Error(`${api} code=${j?.code} ${j?.msg || '非JSON'}`);
  return j;
}
async function fetchAll(tag, api, params, pageSize = 100) {
  const rows = []; let page = 1, total = null;
  while (page <= 60) {
    const j = await call(api, { page, page_size: pageSize, current: page, pageSize, ...params });
    const list = j?.data?.list || [];
    total = j?.data?.total ?? total;
    rows.push(...list);
    if (!list.length || list.length < pageSize) break;
    if (total != null && rows.length >= Number(total)) break;
    page++;
  }
  const file = path.join(outDir, `perf_${tag}_${month}.jsonl`);
  fs.writeFileSync(file, rows.map(r => JSON.stringify(r)).join('\n') + '\n');
  console.log(`[cost] ${tag}: ${rows.length} 行 / total=${total} → ${path.relative(root, file)}`);
  return rows;
}

// 1) 成本核算（按订单核对），按下单时间筛月
await fetchAll('cost', '/backend/finance/get_production_process_list', { created_at: [start, end] });
// 2) 采购单（全状态），同月
await fetchAll('purchase', '/common/purchase/get_purchase_list', { buy_status_list: [], reach_status_list: [], created_at: [start, end] }, 100);
