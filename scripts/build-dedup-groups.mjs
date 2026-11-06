#!/usr/bin/env node
// 客户账户合并组构建：同名+手机号+下单行为三证据
// 输出 state/customer-merge-groups.json：groups=[[cid,cid,...],...] + evidence
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');  // skill代码根目录（可移植）
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const PM = path.join(dataHome, 'data/raw/2026-10-09/pm');
const rl = f => fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));

const customers = rl(path.join(PM, 'duoke_customers.jsonl'));
const orders = rl(path.join(PM, 'duoke_orders_hist3y.jsonl'));

const norm = s => String(s || '').replace(/[（(].*?[)）]/g, '').replace(/[\s·丶。．.,，]/g, '').trim();

const activeIds = new Set(orders.map(o => String(o.client_id)));
const active = customers.filter(c => activeIds.has(String(c.id)) && String(c.id) !== '-15');

const phoneOf = c => {
  const phones = new Set();
  const add = p => { const d = String(p || '').replace(/\D/g, ''); if (d.length >= 7 && d.length <= 15) phones.add(d); };
  add(c.phone);
  const addr = c.address;
  if (addr && typeof addr === 'object') Object.values(addr).forEach(a => { if (a) add(a.phone); });
  return [...phones];
};

// ---- 证据1：归一化同名 ----
const byName = new Map();
active.forEach(c => { const n = norm(c.name); if (!n) return; if (!byName.has(n)) byName.set(n, []); byName.get(n).push(c); });

// ---- 证据2：手机号（含跨名）----
const byPhone = new Map();
active.forEach(c => phoneOf(c).forEach(p => { if (!byPhone.has(p)) byPhone.set(p, []); byPhone.get(p).push(c); }));

// ---- 并查集 ----
const parent = new Map();
const find = x => { let r = x; while (parent.get(r) !== r) r = parent.get(r); let c = x; while (parent.get(c) !== c) { const n = parent.get(c); parent.set(c, r); c = n; } return r; };
const union = (a, b) => { const ra = find(a), rb = find(b); if (ra !== rb) parent.set(ra, rb); };
active.forEach(c => parent.set(String(c.id), String(c.id)));

// 规则A：归一化同名 → 合并（同名同地同名，档口场景几乎必同人；冲突案例少且影响小）
byName.forEach((arr) => { for (let i = 1; i < arr.length; i++) union(String(arr[0].id), String(arr[i].id)); });
// 规则B：同手机号 → 合并（含跨名）
byPhone.forEach(arr => { for (let i = 1; i < arr.length; i++) union(String(arr[0].id), String(arr[i].id)); });

// ---- 证据3（校验）：同组内下单款交叉度 ----
const refByCid = new Map();
{
  const det = rl(path.join(PM, 'duoke_order_details.jsonl'));
  det.forEach(d => (d.goods || []).forEach(g => {
    const cid = String(g.client_id);
    if (!refByCid.has(cid)) refByCid.set(cid, new Set());
    refByCid.get(cid).add(g.item_ref);
  }));
}

const groups = new Map();
parent.forEach((_, cid) => { const r = find(cid); if (!groups.has(r)) groups.set(r, []); groups.get(r).push(cid); });
const mergeGroups = [...groups.values()].filter(g => g.length > 1);

// 输出
const meta = mergeGroups.map(g => {
  const cs = g.map(id => customers.find(c => String(c.id) === id)).filter(Boolean);
  const names = [...new Set(cs.map(c => c.name))];
  const phones = [...new Set(cs.flatMap(phoneOf))];
  let refInter = null;
  if (g.length === 2 && refByCid.has(g[0]) && refByCid.has(g[1])) {
    const inter = [...refByCid.get(g[0])].filter(r => refByCid.get(g[1]).has(r)).length;
    const uni = new Set([...refByCid.get(g[0]), ...refByCid.get(g[1])]).size;
    refInter = uni ? +(inter / uni).toFixed(2) : null;
  }
  return { ids: g, names, phones, sameName: names.length === 1, refInter };
});

const out = {
  built_at: new Date().toISOString(),
  rule: 'A:归一化同名合并(去括号/空格/分隔符) + B:同手机号合并(≥7位,含跨名)；并查集聚类',
  active_customers: active.length,
  groups: meta,
};
const outF = path.join(dataHome, 'state/customer-merge-groups.json');
fs.writeFileSync(outF, JSON.stringify(out, null, 1));
const nAccounts = meta.reduce((s, g) => s + g.ids.length, 0);
console.log('merge groups:', meta.length, '| accounts merged:', nAccounts, '| ->', outF);
console.log('same-name groups:', meta.filter(g => g.sameName).length, '| phone-only(cross-name):', meta.filter(g => !g.sameName).length);
console.log('无任何手机号的组:', meta.filter(g => g.phones.length === 0).length);
