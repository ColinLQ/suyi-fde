#!/usr/bin/env node
// verify-stockout-202609.mjs — 对账脚本：重拉出货记录+跟单单，用多口径核对9月数字（只读）。
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';
import { harvestAuth } from './harvest-auth.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
let auth = null;
const h = await harvestAuth({}).catch(() => ({}));
if (h.yizhe?.ok) auth = h.yizhe.creds;
if (!auth) {
  try {
    const cache = JSON.parse(fs.readFileSync(path.join(dataHome, 'state', 'auth.json'), 'utf8'));
    if (cache.yizhe?.ok) auth = cache.yizhe.creds;
  } catch {}
}
if (!auth) { console.error('[verify] 衣者凭据不可得 → 登录阻断'); process.exit(1); }

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
  if (!j || String(j.code) !== '200') throw new Error(`${api} code=${j?.code} ${j?.msg || ''}`);
  return j;
}
async function fetchAll(api, baseParams, pageSize = 100) {
  const rows = []; let page = 1, total = null;
  while (page <= 300) {
    const j = await call(api, { page, page_size: pageSize, current: page, pageSize, ...baseParams });
    const list = j?.data?.list || [];
    total = j?.data?.total ?? total;
    rows.push(...list);
    if (!list.length || (total != null && rows.length >= Number(total)) || list.length < pageSize) break;
    page++;
  }
  return rows;
}

// ① 最新出货记录全量
const stockout = await fetchAll('/common/stockout_panel/record_list', { status_list: 2 });
// ② 已完成+在产跟单单（口径对照：订单数）
const followDone = await fetchAll('/common/follow_order/get_follow_order_list', { status_list: [3] });
const followActive = await fetchAll('/common/follow_order/get_follow_order_list', { status_list: [1, 2] });
const follows = [...followDone, ...followActive];

const out = {
  拉取时间: new Date().toISOString(),
  stockout_total: stockout.length, follow_total: follows.length,
  stockout: stockout.map(r => ({ record_id: r.record_id, production_id: r.production_id, template_no: r.template_no, stockout_at: r.stockout_at, created_at: r.created_at, total_num: r.total_num, is_revoke: r.is_revoke, follower_user_name: r.follower_user_name, factory_name: r.factory_name })),
  follows: follows.map(r => ({ follow_order_id: r.follow_order_id, production_id: r.production_id, template_no: r.template_no, created_at: r.created_at, finish_time: r.finish_time, last_stockout_time: r.last_stockout_time, status: r.status, status_desc: r.status_desc, plan_total_num: r.plan_total_num, stock_out_num: r.stock_out_num?.value ?? r.stock_out_num, follower_user_name: r.follower_user_name, factory_name: r.factory_name })),
};
fs.writeFileSync(path.join(dataHome, 'data', 'raw', '2026-10-22', 'verify-202609.json'), JSON.stringify(out));
console.log(`[verify] 出货记录 ${stockout.length} 条（10-10 快照为 4467）；跟单单 ${follows.length}`);

// —— 多口径对账（9月） ——
const old = fs.readFileSync(path.join(dataHome, 'data', 'raw', '2026-10-10', 'pm', 'perf_stockout_all.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
const oldIds = new Set(old.map(r => r.record_id));
const newIds = new Set(stockout.map(r => r.record_id));
const added = stockout.filter(r => !oldIds.has(r.record_id));
const removed = old.filter(r => !newIds.has(r.record_id));

const s09 = stockout.filter(r => (r.stockout_at || '').startsWith('2026-09'));
const o09 = old.filter(r => (r.stockout_at || '').startsWith('2026-09'));
console.log('\n===== 9月出货口径对比 =====');
console.log(`A. 按出货时间落9月：新 ${s09.length} 批 / ${s09.reduce((a, r) => a + Number(r.total_num || 0), 0)} 件 ｜ 10-10快照 ${o09.length} 批 / ${o09.reduce((a, r) => a + Number(r.total_num || 0), 0)} 件`);
const prod09 = new Set(s09.map(r => r.production_id));
console.log(`B. 9月出货涉及生产单（订单）数：${prod09.size} 个（一单多批是常态）`);
const fCreated09 = follows.filter(r => (r.created_at || '').startsWith('2026-09'));
console.log(`C. 9月创建的生产单（跟单单）：${fCreated09.length} 单 / 计划 ${fCreated09.reduce((a, r) => a + Number(r.plan_total_num || 0), 0)} 件`);
const fFinish09 = follows.filter(r => (r.finish_time || '').startsWith('2026-09'));
const soNum = r => Number((r.stock_out_num && r.stock_out_num.value) !== undefined ? r.stock_out_num.value : (r.stock_out_num || 0));
console.log(`D. 9月完成（finish_time）的跟单单：${fFinish09.length} 单 / 计划 ${fFinish09.reduce((a, r) => a + Number(r.plan_total_num || 0), 0)} 件 / 已出 ${fFinish09.reduce((a, r) => a + soNum(r), 0)} 件`);
const inProd = follows.filter(r => [1, 2].includes(r.status));
console.log(`E. 当前在产单：${inProd.length}（其中9月创建 ${inProd.filter(r => (r.created_at || '').startsWith('2026-09')).length}）`);

console.log('\n===== 快照差异（10-10 → 10-22） =====');
console.log(`新增出货记录 ${added.length} 条；消失 ${removed.length} 条`);
const added09 = added.filter(r => (r.stockout_at || '').startsWith('2026-09'));
if (added09.length) console.log(`其中落9月的补录：${added09.length} 条 →`, added09.slice(0, 8).map(r => `${r.template_no}@${(r.stockout_at || '').slice(0, 10)}×${r.total_num}`).join('、'));
if (removed.length) console.log('消失样本：', removed.slice(0, 5).map(r => `${r.template_no}@${(r.stockout_at || '').slice(0, 10)}`).join('、'));
