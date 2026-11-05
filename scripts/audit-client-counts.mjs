#!/usr/bin/env node
// 审计：合并账户对客户数指标的影响 + 生成完整证据表
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');  // skill代码根目录（可移植）
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const PM = path.join(dataHome, 'data/raw/2026-10-09/pm');
const rl = f => fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));

const customers = rl(path.join(PM, 'duoke_customers.jsonl'));
const orders = rl(path.join(PM, 'duoke_orders_hist3y.jsonl'));
const G = JSON.parse(fs.readFileSync(path.join(dataHome, 'state/customer-merge-groups.json'), 'utf8'));

const cid2g = new Map();
G.groups.forEach((g, i) => g.ids.forEach(id => cid2g.set(String(id), 'G' + i)));
const gidOf = cid => cid2g.get(String(cid)) || 'S' + cid; // 独立户自成一组
const canonicalName = gid => {
  if (gid[0] === 'S') { const c = customers.find(x => String(x.id) === gid.slice(1)); return c ? c.name : gid; }
  const g = G.groups[+gid.slice(1)];
  return g.names[0];
};

// ---- 影响面1：近30日动销榜客户数 ----
const det = rl(path.join(PM, 'duoke_order_details.jsonl'));
const NOW = Date.now() / 1000;
const byRef = new Map();
det.forEach(d => (d.goods || []).forEach(g2 => {
  if (+g2.ctime < NOW - 30 * 86400) return;
  if (!byRef.has(g2.item_ref)) byRef.set(g2.item_ref, new Set());
  byRef.get(g2.item_ref).add(gidOf(g2.client_id));
}));
const diffs = [];
byRef.forEach((set, ref) => {
  const raw = new Set();
  det.forEach(d => (d.goods || []).forEach(g2 => { if (g2.item_ref === ref && +g2.ctime >= NOW - 30 * 86400) raw.add(String(g2.client_id)); }));
  if (raw.size !== set.size) diffs.push({ ref, raw: raw.size, merged: set.size });
});
diffs.sort((a, b) => (b.raw - b.merged) - (a.raw - a.merged));
console.log('近30日动销款受影响数:', diffs.length);
diffs.slice(0, 15).forEach(d => console.log(`  ${d.ref}: ${d.raw} -> ${d.merged}`));

// ---- 影响面2：新老客口径（30日窗口）----
const custFirst = new Map();
orders.forEach(o => {
  const gid = gidOf(o.client_id);
  const t = +o.ctime;
  if (!custFirst.has(gid) || custFirst.get(gid) > t) custFirst.set(gid, t);
});
const cut = NOW - 30 * 86400;
const win = orders.filter(o => +o.ctime >= cut);
let newRaw = 0, newMerged = 0;
const rawFirst = new Map();
orders.forEach(o => { const c = String(o.client_id); if (!rawFirst.has(c) || rawFirst.get(c) > +o.ctime) rawFirst.set(c, +o.ctime); });
win.forEach(o => { if (rawFirst.get(String(o.client_id)) >= cut) newRaw++; if (custFirst.get(gidOf(o.client_id)) >= cut) newMerged++; });
console.log(`近30日新客单(原始): ${newRaw} -> 合并后: ${newMerged}（差 ${newRaw - newMerged}）`);
const totalActiveRaw = new Set(orders.map(o => String(o.client_id))).size;
const totalActiveMerged = new Set(orders.map(o => gidOf(o.client_id))).size;
console.log(`3年活跃客户(原始): ${totalActiveRaw} -> 合并后: ${totalActiveMerged}`);

// ---- 影响面3：流失名单 ----
const lastOf = new Map();
orders.forEach(o => { const gid = gidOf(o.client_id); if (!lastOf.has(gid) || lastOf.get(gid) < +o.ctime) lastOf.set(gid, +o.ctime); });
let dormantRaw = 0;
const lastRaw = new Map();
orders.forEach(o => { const c = String(o.client_id); if (!lastRaw.has(c) || lastRaw.get(c) < +o.ctime) lastRaw.set(c, +o.ctime); });
lastRaw.forEach((t, c) => { if ((NOW - t) / 86400 >= 30 && (NOW - t) / 86400 < 730) dormantRaw++; });
let dormantMerged = 0;
lastOf.forEach((t, g2) => { if ((NOW - t) / 86400 >= 30 && (NOW - t) / 86400 < 730) dormantMerged++; });
console.log(`流失名单(30天-2年): ${dormantRaw} -> ${dormantMerged}（差 ${dormantRaw - dormantMerged}）`);

// ---- 输出完整证据表 ----
const lines = ['# 客户账户合并审计表（供销售负责人核对）', '',
  `构建时间：${new Date().toISOString()}`, `规则：A 归一化同名合并（去括号/空格/分隔符）+ B 同手机号合并；并查集聚类`,
  `有效下单客户 ${totalActiveRaw} 户（原始账户）→ 合并后 ${totalActiveMerged} 户；合并组 ${G.groups.length} 组（涉及 ${G.groups.reduce((s, g) => s + g.ids.length, 0)} 个账户）`, '',
  '> 用法：业务同事按此表核对。确认同人的保留合并；确认不同人的（如两个同名档口不同老板），告诉我组号，我将其拆开重算。', '',
  '| 组号 | 账户ID | 客户名（各账户） | 手机号 | 同名 | 款交叉度 |', '|---|---|---|---|---|---|'];
G.groups.forEach((g, i) => {
  lines.push(`| G${i} | ${g.ids.join('、')} | ${g.names.join(' / ')} | ${g.phones.join('、') || '-'} | ${g.sameName ? '是' : '否'} | ${g.refInter ?? '-'} |`);
});
lines.push('');
fs.writeFileSync(path.join(dataHome, 'out/客户账户合并审计表-2026-10-10.md'), lines.join('\n'));
console.log('audit table -> out/客户账户合并审计表-2026-10-10.md');
