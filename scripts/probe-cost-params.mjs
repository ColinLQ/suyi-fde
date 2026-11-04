#!/usr/bin/env node
// probe-cost-params.mjs — 探测「财务对账-按订单核对」成本接口的日期参数与总条数（只读）
// 目标：取 2026-09 下单订单的 预计单件成本(template_price) / 实际单件成本(cuted_price, stock_in_price)
import fs from 'node:fs';
import path from 'node:path';
import { harvestAuth } from './harvest-auth.mjs';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
let auth = null;
const h = await harvestAuth({}).catch(() => ({}));
if (h.yizhe?.ok) auth = h.yizhe.creds;
if (!auth) {
  try { const c = JSON.parse(fs.readFileSync(path.join(root, 'state', 'auth.json'), 'utf8')); if (c.yizhe?.ok) auth = c.yizhe.creds; } catch {}
}
if (!auth) { console.error('凭据不可得'); process.exit(1); }

const base = 'https://api.yizheyun.com';
const api = '/backend/finance/get_production_process_list';
async function call(params) {
  const body = { token: auth.token, cid: auth.cid, uid: auth.uid, plate_type: 'backend', v: auth.v, cv: auth.cv, page: 1, page_size: 5, current: 1, pageSize: 5, ...params };
  const res = await fetch(base + api, {
    method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://scm.yizheyun.com', referer: 'https://scm.yizheyun.com/' },
    body: JSON.stringify(body), signal: AbortSignal.timeout(30000),
  });
  const j = await res.json().catch(() => null);
  return j;
}

const cases = [
  ['空参数', {}],
  ['created_at数组@last365', { created_at: ['@last365', '@today'] }],
  ['created_at数组9月', { created_at: ['2026-09-01', '2026-09-30'] }],
  ['created_at字符串9月', { created_at: '2026-09-01,2026-09-30' }],
  ['created_at_start_end', { created_at_start: '2026-09-01', created_at_end: '2026-09-30' }],
  ['paid_status全', { created_at: ['2026-09-01', '2026-09-30'], paid_status_list: [1, 2, 3] }],
];
for (const [name, p] of cases) {
  try {
    const j = await call(p);
    const d = j?.data || {};
    const list = d.list || [];
    const first = list[0];
    console.log(`\n【${name}】code=${j?.code} total=${d.total ?? '?'} 首行条数=${list.length}`);
    if (first) {
      const pick = {};
      for (const k of ['production_sn', 'template_no', 'created_at', 'template_price', 'cuted_price', 'stock_in_price', 'cuted_purchase_price', 'stock_purchase_price', 'price', 'cost_price', 'plan_total_num', 'stock_in_num', 'cuted_num', 'paid_status_desc']) pick[k] = first[k];
      console.log('  样本:', JSON.stringify(pick, null, 0));
    }
  } catch (e) { console.log(`\n【${name}】失败 ${e.message}`); }
  await new Promise(r => setTimeout(r, 300));
}
