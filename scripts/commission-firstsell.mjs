#!/usr/bin/env node
// commission-firstsell.mjs — 首单30天卖完统计（提成口径）
// 规则（2026-10-16 与用户确认）：
//   1) 每月计算上月提成：统计30天窗口结束月落在上月（默认2026-09）的款
//   2) 开始卖时间 T = min(多客商品备注日期, 多客首销日期)，两者取早
//   3) 窗口 [T, T+30天]（含端点），结束月=统计月的款纳入
//   4) 首单数量 = 衣者首单（production_type=1）实际入库SKU汇总；无入库明细降级计划数；无首单记录标注跳过
//   5) 卖完判定：30天内该颜色/尺码累计销量（含退货负数冲减）>= 首单对应数量
//   6) 颜色归一化：去尾"色"字匹配（米白色↔米白），未匹配销售色单列披露
// 数据源：data/raw/2026-10-09/pm/duoke_order_details.jsonl（3年订单明细）
//        data/raw/2026-10-09/pm/duoke_goods.jsonl（商品名/类目）
//        data/raw/2026-10-10/pm/perf_purchase_all.jsonl（衣者全量采购）
//        data/raw/2026-10-10/pm/perf_instock_done.jsonl（入库SKU明细）
//        state/goods-remarks.json（多客商品备注日期缓存）
// 产出：out/commission-<月>.json（供 build-commission-excel.py）
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const MONTH = process.argv.includes('--month') ? process.argv[process.argv.indexOf('--month') + 1] :
  new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }).slice(0, 7); // 默认当月，定时任务传上月
// 数据源自动发现：data/raw/<任意日期>/<槽>/ 下按 mtime 取最新
const findLatest = name => {
  const hits = [];
  const walk = d => fs.readdirSync(d, { withFileTypes: true }).forEach(e => {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name === name) hits.push(p);
  });
  walk(path.join(dataHome, 'data/raw'));
  if (!hits.length) throw new Error('未找到数据文件: ' + name);
  hits.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  return hits[0];
};
const SRC_DETAILS = findLatest('duoke_order_details.jsonl');
const SRC_GOODS = findLatest('duoke_goods.jsonl');
const SRC_PURCHASE = findLatest('perf_purchase_all.jsonl');
const SRC_INSTOCK = findLatest('perf_instock_done.jsonl');
const SRC_REMARKS = path.join(dataHome, 'state/goods-remarks.json');
const OUT = path.join(dataHome, 'out', `commission-${MONTH}.json`);

const read = f => fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse);
// 时区修正：多客ctime为unix秒，按 Asia/Shanghai 转日期（避免UTC偏移一天）
const dstr = ts => new Date(Number(ts) * 1000).toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' });
const addDays = (ds, n) => new Date(new Date(ds + 'T00:00:00+08:00').getTime() + n * 864e5)
  .toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' });
const normColor = c => String(c || '').trim().replace(/色$/, '');

console.log(`[提成-首单30天] 统计月=${MONTH}`);
console.log(`数据源：\n  明细 ${SRC_DETAILS}\n  商品 ${SRC_GOODS}\n  采购 ${SRC_PURCHASE}\n  入库 ${SRC_INSTOCK}`);

// ── 1. 多客销售明细：每款首销 + 全量行 ──
const details = read(SRC_DETAILS);
const firstSale = {}; const salesRows = {};
for (const d of details) {
  for (const g of d.goods || []) {
    const ref = g.item_ref; if (!ref) continue;
    const ds = dstr(g.ctime);
    if (!firstSale[ref] || ds < firstSale[ref]) firstSale[ref] = ds;
    (salesRows[ref] ??= []).push({ ds, color: g.color, size: g.size, qty: Number(g.quantity) || 0 });
  }
}
console.log(`多客明细载入：${details.length} 单，款数 ${Object.keys(firstSale).length}`);

// ── 2. 开始=min(备注,首销)；结束=上架(备注)+30天（无备注用首销近似）；筛窗口结束月=统计月 ──
const remarks = JSON.parse(fs.readFileSync(SRC_REMARKS, 'utf8'));
const cands = []; const excluded = [];
const dnum = ds => Math.floor(new Date(ds + 'T00:00:00+08:00').getTime() / 864e5);
for (const [ref, fsDate] of Object.entries(firstSale)) {
  const rd = remarks[ref]?.date || null;
  // 老款保护：首销早于上架备注>60天 → 视为老款重新上架/备注补写，剔除（避免3年窗口噪音）
  if (rd && dnum(fsDate) < dnum(rd) - 60) { excluded.push({ ref, firstSale: fsDate, remarkDate: rd }); continue; }
  const T = rd && rd < fsDate ? rd : fsDate;          // 开始：哪个早算哪个
  const shelf = rd || fsDate;                          // 上架基准：备注日期；无备注降级首销
  const end = addDays(shelf, 29);                      // 结束：上架日起共30个自然日（上架当天=第1天），即上架+29天（自然日，含大小月）
  if (end.slice(0, 7) === MONTH) cands.push({ ref, T, end, remarkDate: rd, firstSale: fsDate, tBasis: rd && rd < fsDate ? '备注日期' : '首销日期', endBasis: rd ? '上架+30天' : '首销+30天(无备注)' });
}
cands.sort((a, b) => a.T < b.T ? -1 : 1);
console.log(`窗口结束月=${MONTH} 的款：${cands.length}`);

// ── 3. 商品信息 ──
const goodsInfo = {};
for (const g of read(SRC_GOODS)) goodsInfo[g.item_ref] = {
  name: g.name || '', category: g.cate_info?.name || '',
  price: (g.price_range?.range || [])[0] || '',
};

// ── 4. 衣者首单（production_type=1，取最早下单）+ 入库SKU明细 ──
const purchase = read(SRC_PURCHASE);
const firstOrder = {};
for (const r of purchase) {
  if (!cands.some(c => c.ref === r.template_no)) continue;
  if (Number(r.production_type) !== 1) continue;
  if (!firstOrder[r.template_no] || r.created_at < firstOrder[r.template_no].created_at) firstOrder[r.template_no] = r;
}
// 无type=1则回落最早任意类型采购单（如"订单"），标注
const anyOrder = {};
for (const r of purchase) {
  if (!firstOrder[r.template_no]) {
    if (!anyOrder[r.template_no] || r.created_at < anyOrder[r.template_no].created_at) anyOrder[r.template_no] = r;
  }
}
const instock = read(SRC_INSTOCK);
const instockByProd = {}; const instockByRef = {};
for (const r of instock) {
  (instockByProd[r.production_id] ??= []).push(r);
  (instockByRef[r.template_no] ??= []).push(r);
}

// ── 5. 逐款计算 ──
const results = []; const quality = [];
for (const c of cands) {
  const { ref, T, end } = c;
  const info = goodsInfo[ref] || {};
  const rec = { ...c, name: info.name, category: info.category, price: info.price, skus: [], unmatchedSales: [], qtyBasis: '', note: '' };

  // 首单记录
  let po = firstOrder[ref];
  if (po) { rec.firstOrderDate = po.created_at; rec.firstOrderType = '首单'; }
  else if (anyOrder[ref]) { po = anyOrder[ref]; rec.firstOrderDate = po.created_at; rec.firstOrderType = po.production_type_desc || '非首单'; rec.note = '无type=1首单记录，取最早采购单'; }
  else { rec.qtyBasis = '无首单记录'; rec.note = '衣者无任何采购/生产记录（疑似外购款），跳过卖完判定'; rec.conclusion = '无法判定'; quality.push({ ref, issue: '无首单记录', detail: `开始卖${T}，疑似外购款` }); results.push(rec); continue; }

  // 入库SKU明细：production_id → follow_order_id → 模板号早批次
  let batches = instockByProd[po.production_id] || [];
  let linkMethod = batches.length ? 'production_id' : '';
  if (!batches.length && po.follow_order_id) {
    batches = instock.filter(r => r.follow_order_id === po.follow_order_id);
    if (batches.length) linkMethod = 'follow_order_id';
  }
  if (!batches.length) {
    // 回落：该款所有入库批次中，录入时间 <= T+30 的（近似首单批次）
    const all = (instockByRef[ref] || []).filter(r => String(r.created_at).slice(0, 10) <= addDays(T, 30));
    if (all.length) { batches = all; linkMethod = '模板号+窗口内'; quality.push({ ref, issue: '首单批次间接关联', detail: `经${linkMethod}关联${all.length}批入库` }); }
  }

  const skuRows = batches.flatMap(b => (b.sku_detail || [])).filter(r => r.co_val !== '合计' && !r.is_sum);
  if (skuRows.length) {
    rec.qtyBasis = `入库SKU(${linkMethod})`;
    const bySku = new Map();
    for (const r of skuRows) {
      const key = normColor(r.co_val) + '|' + (r.si_val || 'F');
      bySku.set(key, (bySku.get(key) || 0) + (Number(r.instock_num) || 0));
    }
    rec.firstQtyTotal = [...bySku.values()].reduce((a, b) => a + b, 0);
    for (const [key, qty] of bySku) {
      const [color, size] = key.split('|');
      rec.skus.push({ color, size, firstQty: qty, soldQty: 0, totalQty: 0, rawColors: new Set() });
    }
  } else {
    rec.qtyBasis = '计划数(无入库明细)';
    rec.firstQtyTotal = Number(po.plan_total_num) || 0;
    rec.skus.push({ color: '(全部颜色尺码)', size: '-', firstQty: rec.firstQtyTotal, soldQty: 0, totalQty: 0, rawColors: new Set() });
    quality.push({ ref, issue: '无入库SKU明细', detail: `降级用计划数${rec.firstQtyTotal}` });
  }

  // 销量聚合：30天窗口 / 累计至统计月底（总额+按颜色）；退货跟踪=窗口后至月底
  const monthEnd = new Date(Date.UTC(Number(MONTH.slice(0, 4)), Number(MONTH.slice(5, 7)), 0)).toISOString().slice(0, 10);
  const win = salesRows[ref] || [];
  let winTotal = 0, monthEndTotal = 0;
  const skuMap = new Map(rec.skus.map(s => [s.color + '|' + (s.size === '-' ? '' : s.size), s]));
  const unmatchedWin = new Map(); const unmatchedAll = new Map();
  // 累计至月底按颜色汇总（所有售出颜色，含首单外）
  const monthEndByColor = new Map();
  // 窗口后至月底退货跟踪（按颜色/尺码，负数才记）
  const afterReturn = new Map();
  const agg = (s, inWin) => {
    if (inWin) winTotal += s.qty;
    if (s.ds <= monthEnd) {
      monthEndTotal += s.qty;
      const ck = normColor(s.color);
      monthEndByColor.set(ck, (monthEndByColor.get(ck) || 0) + s.qty);
    }
    if (!inWin && s.ds <= monthEnd && s.qty < 0) {
      const rk = normColor(s.color) + '|' + (s.size === 'F' || !s.size ? 'F' : s.size);
      afterReturn.set(rk, (afterReturn.get(rk) || 0) + s.qty);
    }
    const key = normColor(s.color) + '|' + (s.size === 'F' || !s.size ? 'F' : s.size);
    let hit = skuMap.get(key) || rec.skus.find(k => normColor(k.color) === normColor(s.color) && (k.size === '-' || k.size === s.size));
    if (!hit) hit = rec.skus.find(k => k.size === '-' && k.color === '(全部颜色尺码)'); // 计划数降级的款：全部计入
    if (hit) { if (inWin) hit.soldQty += s.qty; hit.rawColors.add(s.color); }
    else {
      const uk = normColor(s.color) + '|' + (s.size || 'F');
      if (inWin) unmatchedWin.set(uk, (unmatchedWin.get(uk) || 0) + s.qty);
      unmatchedAll.set(uk, (unmatchedAll.get(uk) || 0) + s.qty);
    }
  };
  for (const s of win) {
    const inWin = s.ds >= T && s.ds <= end;
    agg(s, inWin);
  }
  rec.winTotal = winTotal; rec.monthEndTotal = monthEndTotal; rec.monthEnd = monthEnd;
  rec.monthEndByColor = [...monthEndByColor.entries()].map(([color, qty]) => ({ color, qty }));
  // 差额总数（V3 符号规则）：任一颜色未达标→款未达标，= -Σ(未达标SKU缺口)（负数）；全部达标→ +Σ(超出量)（正数）
  let shortSum = 0, overSum = 0, anyUnmet = false;
  for (const s of rec.skus) {
    const d = s.firstQty - s.soldQty;
    if (d > 0) { anyUnmet = true; shortSum += d; } else overSum += -d;
  }
  rec.gapTotal = rec.firstQtyTotal != null ? (anyUnmet ? -shortSum : overSum) : null;
  rec.unmatched = [...unmatchedWin.entries()].map(([k, qty]) => { const [color, size] = k.split('|'); return { color, size, qty }; });
  rec.afterReturn = [...afterReturn.entries()].map(([k, qty]) => { const [color, size] = k.split('|'); return { color, size, qty }; });
  if (rec.unmatched.length) quality.push({ ref, issue: '窗口内有首单外颜色/尺码售出', detail: rec.unmatched.map(u => `${u.color}/${u.size}:${u.qty}`).join(', ') });

  // 颜色核对提示：多客累计售出颜色 vs 衣者首单颜色（含颜色相似度辅助判断）
  const yizheColors = new Set(rec.skus.filter(s => s.color !== '(全部颜色尺码)').map(s => s.color));
  const soldColors = new Set(rec.monthEndByColor.map(c => c.color));
  rec.colorIssues = [];
  for (const c of soldColors) {
    if (!yizheColors.has(c)) {
      // 相似度提示：一字包含（如"米白"∈"米白色"已被归一化处理；此处捕捉命名差异如"酱紫"vs"紫色"）
      const similar = [...yizheColors].filter(y => y.includes(c) || c.includes(y));
      rec.colorIssues.push({ color: c, similar: similar.join('/') || null });
    }
  }
  if (rec.qtyBasis === '计划数(无入库明细)' && soldColors.size) {
    rec.colorIssues.push({ color: '(无首单颜色明细，无法核对)', similar: null });
  }

  // SKU级判定
  let soldOut = 0;
  for (const s of rec.skus) { s.soldOut = s.soldQty >= s.firstQty; if (s.soldOut) soldOut++; s.gap = s.firstQty - s.soldQty; s.rawColors = [...s.rawColors]; }
  rec.skuCount = rec.skus.length; rec.soldOutCount = soldOut;
  rec.conclusion = rec.qtyBasis === '无首单记录' ? '无法判定' :
    (soldOut === rec.skus.length ? '全部卖完' : soldOut > 0 ? `部分卖完(${soldOut}/${rec.skus.length})` : '未卖完');
  results.push(rec);
}

fs.mkdirSync(path.join(dataHome, 'out'), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify({ month: MONTH, generatedAt: new Date().toISOString(), rule: '开始=min(备注,首销)；结束=上架(备注)+30天自然日(无备注用首销)；首销早于上架>60天按老款重上架剔除；结束月=' + MONTH + '；首单量=入库SKU(降级计划数)；卖完=窗口销量≥首单量', results, quality, excludedCount: excluded.length, excludedSample: excluded.slice(0, 10) }, null, 1));
console.log(`老款重上架剔除：${excluded.length} 款（首销早于上架备注>60天）`);
const done = results.filter(r => r.conclusion !== '无法判定');
console.log(`纳入判定 ${done.length} 款：全部卖完 ${done.filter(r => r.conclusion === '全部卖完').length}，部分 ${done.filter(r => r.conclusion.startsWith('部分')).length}，未卖完 ${done.filter(r => r.conclusion === '未卖完').length}，无法判定 ${results.length - done.length}`);
console.log('→', OUT);
