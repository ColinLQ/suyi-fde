#!/usr/bin/env node
// probe-status-params.mjs — 一次性探测脚本：确认出货/采购/跟单/入库接口的状态参数与日期过滤正确形态。
// 只读查询，遵守只读红线。探测结果打印，不落盘业务数据。
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { harvestAuth } from './harvest-auth.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const timeoutMs = 30000;

let auth = null;
const h = await harvestAuth({}).catch(() => ({}));
if (h.yizhe?.ok) auth = h.yizhe.creds;
if (!auth) {
  try {
    const cache = JSON.parse((await import('node:fs')).readFileSync(path.join(dataHome, 'state', 'auth.json'), 'utf8'));
    if (cache.yizhe?.ok) auth = cache.yizhe.creds;
  } catch {}
}
if (!auth) { console.error('[probe] 衣者凭据不可得'); process.exit(1); }

const base = 'https://api.yizheyun.com';
async function call(api, params) {
  const body = { token: auth.token, cid: auth.cid, uid: auth.uid, plate_type: 'backend', v: auth.v, cv: auth.cv, ...params };
  const res = await fetch(base + api, {
    method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://scm.yizheyun.com', referer: 'https://scm.yizheyun.com/' },
    body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs),
  });
  const text = await res.text();
  try { return JSON.parse(text); } catch { return { code: 'non-json', raw: text.slice(0, 200) }; }
}

async function probe(name, api, params, listPath = 'data.list') {
  const j = await call(api, { page: 1, page_size: 5, current: 1, pageSize: 5, ...params });
  const code = String(j.code);
  const list = listPath.split('.').reduce((a, k) => (a == null ? a : a[k]), j);
  const total = j?.data?.total;
  console.log(`\n== ${name} == code=${code} total=${total ?? '-'} rows=${Array.isArray(list) ? list.length : 'N/A'}`);
  if (code === '200' && Array.isArray(list) && list.length) {
    const s = list[0];
    // 打印状态相关字段帮助判断完成态
    const keys = ['purchase_sn', 'follow_order_sn', 'template_no', 'status', 'status_desc', 'purchase_status', 'purchase_status_desc', 'buy_status', 'buy_status_desc', 'reach_status', 'reach_status_desc', 'stockin_status', 'stockout_at', 'created_at', 'finish_time', 'estimated_finish_time', 'last_stockout_time', 'last_instock_time'];
    const picked = {}; for (const k of keys) if (s[k] !== undefined) picked[k] = s[k];
    console.log(JSON.stringify(picked, null, 1));
  } else if (j.msg) console.log('msg:', j.msg);
}

// —— 1. 出货记录：原 created_at 参数导致 0 行，探测不同形态 ——
await probe('出货·无日期参数(全量)', '/common/stockout_panel/record_list', { status_list: 2 });
await probe('出货·日期为数组', '/common/stockout_panel/record_list', { status_list: 2, created_at: ['2026-09-01', '2026-09-30'] });
await probe('出货·日期为字符串区间', '/common/stockout_panel/record_list', { status_list: 2, created_at: '2026-09-01,2026-09-30' });
await probe('出货·status_list数组', '/common/stockout_panel/record_list', { status_list: [2] });

// —— 2. 采购单：找"已完成"状态值 ——
await probe('采购·buy_status=[1,2](在途)', '/common/purchase/get_purchase_list', { buy_status_list: [1, 2], reach_status_list: [1, 2] });
await probe('采购·buy_status=[3]', '/common/purchase/get_purchase_list', { buy_status_list: [3], reach_status_list: [1, 2, 3] });
await probe('采购·buy_status=[4]', '/common/purchase/get_purchase_list', { buy_status_list: [4], reach_status_list: [1, 2, 3, 4] });
await probe('采购·全状态', '/common/purchase/get_purchase_list', { buy_status_list: [], reach_status_list: [] });

// —— 3. 跟单：找"已完成"状态值 ——
await probe('跟单·status=[1,2](在产)', '/common/follow_order/get_follow_order_list', { status_list: [1, 2] });
await probe('跟单·status=[3]', '/common/follow_order/get_follow_order_list', { status_list: [3] });
await probe('跟单·status=[4]', '/common/follow_order/get_follow_order_list', { status_list: [4] });
await probe('跟单·全状态', '/common/follow_order/get_follow_order_list', { status_list: [] });

// —— 4. 成衣入库：完成态 ——
await probe('入库·status=[1,2]', '/common/instock/get_instock_list', { status_list: [1, 2] });
await probe('入库·status=[3]', '/common/instock/get_instock_list', { status_list: [3] });
await probe('入库·全状态', '/common/instock/get_instock_list', { status_list: [] });
console.log('\n[probe] 完成');
