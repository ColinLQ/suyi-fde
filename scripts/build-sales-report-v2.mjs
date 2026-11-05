#!/usr/bin/env node
// 销售需求14项指标计算 V2（销售负责人修正版 2026-10-10）
// 输入=多客订单列表(3年)+明细+客户+商品实时库存+衣者当前库存
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');  // skill代码根目录（可移植）
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const PM = path.join(dataHome, 'data/raw/2026-10-09/pm');
const OUT = path.join(dataHome, 'out');
const rl = f => fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));

// ---------- 数据加载 ----------
const orders = rl(path.join(PM, 'duoke_orders_hist3y.jsonl'));
const details = rl(path.join(PM, 'duoke_order_details.jsonl'));
const customers = rl(path.join(PM, 'duoke_customers.jsonl'));
const goods = rl(path.join(PM, 'duoke_goods.jsonl'));
const stockYizhe = rl(path.join(PM, 'yizhe_stock_list.jsonl'));

const NOW = Date.now() / 1000;
const beijing = ts => { const dt = new Date(ts * 1000 + 8 * 3600 * 1000); return dt.toISOString().slice(0, 10); };
const money = n => (n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 });
const f1 = n => (n || 0).toFixed(1);
const esc = s => String(s ?? '').replace(/\|/g, '/');

const valid = orders.filter(o => o.show !== '0' && o.show !== 0);
console.log(`orders=${orders.length} valid=${valid.length} details=${details.length}`);

// ---------- 客户账户合并（同人多个账户归并为一户） ----------
let MERGE_GROUPS = [];
try { MERGE_GROUPS = JSON.parse(fs.readFileSync(path.join(dataHome, 'state/customer-merge-groups.json'), 'utf8')).groups || []; } catch {}
const cid2g = new Map();
MERGE_GROUPS.forEach((g, i) => g.ids.forEach(id => cid2g.set(String(id), 'G' + i)));
const gidOf = cid => cid2g.get(String(cid)) || 'S' + cid;
console.log(`merge groups: ${MERGE_GROUPS.length}`);

// ---------- 客户档案 ----------
const custMap = new Map();
customers.forEach(c => custMap.set(String(c.id), c));
const VIP_NAME = { '1': '普通', '2': 'B类', '3': 'A类', '4': 'C类' };
const VIP_RANK = { '2': 2, '3': 3, '4': 4 };
const vipOf = gid => {
  if (gid[0] !== 'G') { const c = custMap.get(String(gid.slice(1))); return c ? (VIP_NAME[c.vip] || `vip${c.vip}`) : '未建档'; }
  const g = MERGE_GROUPS[+gid.slice(1)];
  let best = '1';
  g.ids.forEach(id => { const c = custMap.get(String(id)); if (!c) return; const r = VIP_RANK[c.vip] || 0; const br = VIP_RANK[best] || 0; if (r > 0 && (br === 0 || r > br)) best = c.vip; });
  return VIP_NAME[best] || `vip${best}`;
};
const vipRawOf = gid => {
  if (gid[0] !== 'G') { const c = custMap.get(String(gid.slice(1))); return c ? c.vip : null; }
  const g = MERGE_GROUPS[+gid.slice(1)];
  let best = '1';
  g.ids.forEach(id => { const c = custMap.get(String(id)); if (!c) return; const r = VIP_RANK[c.vip] || 0; const br = VIP_RANK[best] || 0; if (r > 0 && (br === 0 || r > br)) best = c.vip; });
  return best;
};

// ---------- 客户聚合（3年全量，按合并后 gid）：下单/退单分开、金额分开 ----------
const custAgg = new Map();
valid.forEach(o => {
  const cid = String(o.client_id);
  const gid = gidOf(cid);
  const amt = +o.calc_price || 0, qty = +o.goods_quantity || 0, t = +o.ctime;
  const isRet = qty < 0;
  let a = custAgg.get(gid);
  if (!a) { a = { first: t, last: t, buyN: 0, retN: 0, buyQty: 0, retQty: 0, buyAmt: 0, retAmt: 0, cids: new Set(), shops: new Map() }; custAgg.set(gid, a); }
  a.first = Math.min(a.first, t); a.last = Math.max(a.last, t);
  a.cids.add(cid);
  const sn = o.shop_name || '未知店';
  a.shops.set(sn, (a.shops.get(sn) || 0) + 1); // 归属店铺=下单次数最多
  if (isRet) { a.retN++; a.retQty += Math.abs(qty); a.retAmt += Math.abs(amt); }
  else { a.buyN++; a.buyQty += qty; a.buyAmt += amt; }
});
// 合并组主显示名：组内最早下单的账户名（保留最常用叫法）
const gidMainName = new Map();
custAgg.forEach((a, gid) => {
  if (gid[0] !== 'G') { gidMainName.set(gid, null); return; } // 独立户走 custName
  let best = null, bestT = Infinity;
  valid.forEach(o => { if (a.cids.has(String(o.client_id)) && +o.ctime < bestT) { bestT = +o.ctime; best = o.customer_name; } });
  gidMainName.set(gid, best);
});
const custName = gid => { if (gidMainName.has(gid) && gidMainName.get(gid)) return gidMainName.get(gid);
  const c = custMap.get(String(gid.slice(1))); return c ? c.name : (valid.find(o => gidOf(String(o.client_id)) === gid)?.customer_name || gid); };
// 手机号（合并组取组内任一账户手机号；2026-10-12 需求#9）
const phoneOfCid = c => { const p = String(c.phone || '').replace(/[^\d+]/g, ''); const d = p.replace(/\D/g, ''); return (d.length >= 7 && d.length <= 15) ? p : ''; };
const custPhone = new Map();
customers.forEach(c => { const p = phoneOfCid(c); if (p) custPhone.set(String(c.id), p); });
const phoneOf = gid => {
  if (gid[0] !== 'G') return custPhone.get(gid.slice(1)) || '';
  const g = MERGE_GROUPS[+gid.slice(1)];
  for (const id of g.ids) { const p = custPhone.get(String(id)); if (p) return p; }
  return '';
};
// 客户归属店铺（2026-10-12：所有客户统计表加归属店铺）
const shopOf = gid => { const a = custAgg.get(gid); if (!a || !a.shops.size) return ''; let best = '', n = 0; a.shops.forEach((c, sn) => { if (c > n) { n = c; best = sn; } }); return best; };
// 单品销售价 + 上市时间（V2.4 口径：多客备注日期优先 → 无备注用首次销售时间 → 兜底建档日）
const goodsPrice = new Map(); const goodsListDate = new Map(); const goodsRemarkDate = new Map();
let REMARKS = {};
try { REMARKS = JSON.parse(fs.readFileSync(path.join(dataHome, 'state/goods-remarks.json'), 'utf8')); } catch {}
goods.forEach(g => {
  const pr = g.price_range && g.price_range.range && g.price_range.range[0] ? +g.price_range.range[0] : 0;
  if (pr > 0) goodsPrice.set(g.item_ref, pr);
  const rem = REMARKS[g.item_ref];
  if (rem && rem.date) { goodsListDate.set(g.item_ref, rem.date); goodsRemarkDate.set(g.item_ref, true); }
  else goodsListDate.set(g.item_ref, beijing(+g.ctime)); // 先兜底建档日；首销时间在 rows 构建后回填
});
// 客单价 = 购买总金额 ÷ 购买单数；件单价 = 净额÷净件
const aov = a => a.buyN > 0 ? a.buyAmt / a.buyN : 0;

// ---------- 明细行（款级事实表） ----------
const rows = [];
details.forEach(dd => (dd.goods || []).forEach(g => {
  rows.push({ doc_id: g.doc_id, date: beijing(+g.ctime), ts: +g.ctime, cid: gidOf(g.client_id), seller: g.seller, shop_id: g.shop_id,
    ref: g.item_ref, name: g.name, cat: g.category, season: g.season, year: g.year,
    qty: g.quantity, price: g.price, amount: g.quantity * g.price });
}));
console.log('detail rows:', rows.length);

// 上市时间回填：无备注日期的款 → 用首次销售时间（V2.4 口径）
{
  const firstSaleTs = new Map();
  rows.forEach(r => { const cur = firstSaleTs.get(r.ref); if (!cur || r.ts < cur) firstSaleTs.set(r.ref, r.ts); });
  goods.forEach(g => {
    if (goodsRemarkDate.has(g.item_ref)) return;
    if (firstSaleTs.has(g.item_ref)) goodsListDate.set(g.item_ref, beijing(firstSaleTs.get(g.item_ref)));
  });
}

// ---------- 1&5. 周期统计（连带率/补单金额/新老客金额） ----------
function periodStats(days) {
  const cut = NOW - days * 86400;
  const os = valid.filter(o => +o.ctime >= cut);
  let amt = 0, qty = 0, buyN = 0;
  let newBuyN = 0, oldBuyN = 0, newAmt = 0, oldAmt = 0, newQty = 0, oldQty = 0, reorderAmt = 0, firstAmt = 0;
  os.forEach(o => {
    const oAmt = +o.calc_price || 0, oQty = +o.goods_quantity || 0;
    amt += oAmt; qty += oQty;
    if (oQty > 0) buyN++;
    const a = custAgg.get(gidOf(o.client_id));
    const isNew = a && a.first === +o.ctime; // 该客户全历史首单恰为本单
    if (isNew) { newBuyN += oQty > 0 ? 1 : 0; newAmt += oAmt; newQty += oQty; firstAmt += oAmt; }
    else { oldBuyN += oQty > 0 ? 1 : 0; oldAmt += oAmt; oldQty += oQty; reorderAmt += oAmt; } // reorderAmt=老客金额（兼容字段）
  });
  return {
    label: days, orders: os.length, amt, qty, buyN,
    attach: buyN > 0 ? qty / buyN : 0, // 平均每单连带（件/单，含退货冲减）
    newBuyN, oldBuyN, newAmt, oldAmt,
    newAttach: newBuyN > 0 ? newQty / newBuyN : 0,
    oldAttach: oldBuyN > 0 ? oldQty / oldBuyN : 0,
    reorderAmt, firstAmt,
  };
}
const p7 = periodStats(7), p15 = periodStats(15), p30 = periodStats(30);

// ---------- 流失名单（三档：30-60天 / 60天-1年 / 1-2年；超2年不要） ----------
function dormantRec(a, cid) {
  const gap = Math.floor((NOW - a.last) / 86400);
  const netQty = a.buyQty - a.retQty, netAmt = a.buyAmt - a.retAmt;
  return { cid, name: custName(cid), phone: phoneOf(cid), shop: shopOf(cid), vip: vipOf(cid), first: beijing(a.first), last: beijing(a.last), gapDays: gap,
    buyN: a.buyN, retN: a.retN, buyQty: a.buyQty, retQty: a.retQty, buyAmt: a.buyAmt, retAmt: a.retAmt,
    netQty, netAmt, aov: aov(a), unitPrice: netQty > 0 ? netAmt / netQty : 0 };
}
const tier1 = [], tier2 = [], tier3 = [];
custAgg.forEach((a, cid) => {
  const gap = Math.floor((NOW - a.last) / 86400);
  if (gap < 30 || gap >= 730) return; // 只留 30天~2年
  const rec = dormantRec(a, cid); // cid 参数已是 gid
  if (gap < 60) tier1.push(rec);
  else if (gap < 365) tier2.push(rec);
  else tier3.push(rec);
});
tier1.sort((x, y) => y.netAmt - x.netAmt); tier2.sort((x, y) => y.netAmt - x.netAmt); tier3.sort((x, y) => y.netAmt - x.netAmt);
// 盘活名单（超3个月，含首单时间）＝ tier2∩(>=90) + tier3
const revive = [...tier2.filter(r => r.gapDays >= 90), ...tier3].sort((a, b) => b.netAmt - a.netAmt);

// ---------- 月未下单（2026-10-12 #2 新口径：近3个月有下单，但本月自然月还没有单） ----------
const nowBj = new Date((NOW + 8 * 3600) * 1000);
const monthStartBj = new Date(nowBj.getFullYear(), nowBj.getMonth(), 1).getTime() / 1000 - 8 * 3600; // 北京时间本月1日0点(近似：取本地)
const monthStart = new Date(new Date().getFullYear(), new Date().getMonth(), 1).getTime() / 1000;
const threeMonthsAgo = NOW - 90 * 86400;
const monthMissing = [];
custAgg.forEach((a, gid) => {
  if (a.last < threeMonthsAgo) return;      // 近3个月（90天）内没有任何单→不属于（那是流失名单的事）
  if (a.last >= monthStart) return;         // 本月已有单→正常
  monthMissing.push({ name: custName(gid), phone: phoneOf(gid), shop: shopOf(gid), vip: vipOf(gid), last: beijing(a.last), gapDays: Math.floor((NOW - a.last) / 86400),
    buyN: a.buyN, retN: a.retN, buyAmt: a.buyAmt, retAmt: a.retAmt, aov: aov(a) });
});
monthMissing.sort((x, y) => y.buyAmt - x.buyAmt);

// ---------- 新客未复购（2026-10-12 #3：档位15-30天 / 30-60天） ----------
const nc1530 = [], nc3060 = [];
custAgg.forEach((a, gid) => {
  if (a.buyN + a.retN > 1) return;
  const ageDays = (NOW - a.first) / 86400;
  const rec = { name: custName(gid), phone: phoneOf(gid), shop: shopOf(gid), first: beijing(a.first), gapDays: Math.floor(ageDays), amt: a.buyAmt, qty: a.buyQty,
    aov: aov(a), unitPrice: a.buyQty > 0 ? a.buyAmt / a.buyQty : 0 };
  if (ageDays >= 15 && ageDays < 30) nc1530.push(rec);
  else if (ageDays >= 30 && ageDays < 60) nc3060.push(rec);
});
nc1530.sort((a, b) => b.gapDays - a.gapDays); nc3060.sort((a, b) => b.gapDays - a.gapDays);

// ---------- 新客未复购 / 老客断档（旧逻辑保留给兼容，不再输出老客断档 sheet） ----------
const newClient15 = [], newClient30 = [];
custAgg.forEach((a, cid) => {
  const ageDays = (NOW - a.first) / 86400;
  const sinceLast = (NOW - a.last) / 86400;
  const rec = { name: custName(cid), first: beijing(a.first), gapDays: Math.floor(sinceLast), amt: a.buyAmt, qty: a.buyQty, buyN: a.buyN };
  if (ageDays >= 15 && ageDays <= 45 && a.buyN + a.retN <= 1) newClient15.push(rec);
  if (ageDays >= 30 && ageDays <= 60 && a.buyN + a.retN <= 1) newClient30.push(rec);
});
newClient15.sort((a, b) => b.gapDays - a.gapDays); newClient30.sort((a, b) => b.gapDays - a.gapDays);

const oldClientGap = [];
custAgg.forEach((a, cid) => {
  if (a.buyN < 2) return;
  const sinceLast = (NOW - a.last) / 86400;
  if (sinceLast > 30) oldClientGap.push({ name: custName(cid), vip: vipOf(cid), times: a.buyN + a.retN, last: beijing(a.last), gapDays: Math.floor(sinceLast), amt: a.buyAmt });
});
oldClientGap.sort((a, b) => b.gapDays - a.gapDays);

// ---------- 款级（周/半月/月三窗 + 全品类top30 + 单品类top10 + 实时库存） ----------
const dkStock = new Map(), goodsYear = new Map(), goodsSeason = new Map(), goodsCat = new Map(), goodsName = new Map();
goods.forEach(g => {
  let total = 0;
  const skus = g.sku || [];
  if (Array.isArray(skus)) skus.forEach(s => total += +s.warehouse_0 || 0);
  else if (skus && typeof skus === 'object') Object.values(skus).forEach(s => { const w = +(s.warehouse_0 ?? 0) || 0; total += w; });
  dkStock.set(g.item_ref, total);
  goodsYear.set(g.item_ref, (g.year && g.year.name) || '');
  goodsSeason.set(g.item_ref, (g.season && g.season.name) || '');
  goodsCat.set(g.item_ref, (g.k_category && g.k_category.name) || '');
  goodsName.set(g.item_ref, g.name || '');
});
// 明细行品类兜底
const catOf = ref => goodsCat.get(ref) || rows.find(r => r.ref === ref)?.cat || '';

function goodsAggBy(days) {
  const cut = NOW - days * 86400;
  const m = new Map();
  rows.filter(r => r.ts >= cut).forEach(r => {
    let g = m.get(r.ref);
    if (!g) { g = { ref: r.ref, qty: 0, amt: 0, clients: new Set() }; m.set(r.ref, g); }
    g.qty += r.qty; g.amt += r.amount; r.cid && g.clients.add(r.cid);
  });
  return m;
}
const gW = goodsAggBy(7), gH = goodsAggBy(15), gM = goodsAggBy(30);
const moveRow = (g) => ({ ref: g.ref, name: goodsName.get(g.ref) || '', cat: catOf(g.ref), qty: g.qty, amt: g.amt,
  clients: g.clients.size, stock: dkStock.get(g.ref) ?? '-', listDate: goodsListDate.get(g.ref) || '', price: goodsPrice.get(g.ref) || 0 });
const topN = (m, n, minClients = 0) => [...m.values()].filter(g => g.clients.size >= Math.max(1, minClients)).sort((a, b) => b.qty - a.qty).slice(0, n).map(g => moveRow(g));

// 单品类 top10（近30日，主要品类）
const cat30 = new Map();
gM.forEach((g, ref) => { const c = catOf(ref); if (!c) return; let a = cat30.get(c); if (!a) { a = { qty: 0 }; cat30.set(c, a); } a.qty += g.qty; });
const mainCats = [...cat30.entries()].sort((a, b) => b[1].qty - a[1].qty).slice(0, 6).map(e => e[0]);
const catTop = {};
mainCats.forEach(c => {
  const m = new Map();
  gM.forEach((g, ref) => { if (catOf(ref) !== c) return; let x = m.get(ref); if (!x) { x = { ...g }; m.set(ref, x); } });
  catTop[c] = [...m.values()].sort((a, b) => b.qty - a.qty).slice(0, 10).map(g => moveRow(g));
  catTop[c + '·剔除专属'] = [...m.values()].filter(g => g.clients.size >= 2).sort((a, b) => b.qty - a.qty).slice(0, 10).map(g => moveRow(g));
});

// 动销率（近30日窗）
const totalStyles30 = gM.size || 1;
const active30 = [...gM.values()].filter(g => g.qty > 100).length;

// 售罄率（窗口内销量 ÷ 衣者当前库存，标题按销售负责人要求叫"售罄率"）
const yizheStock = new Map();
stockYizhe.forEach(s => yizheStock.set(s.template_no, +s.total_num || 0));
const sellThrough = [...gM.values()].map(g => ({ ref: g.ref, name: goodsName.get(g.ref) || '', sold30: g.qty, stock: yizheStock.get(g.ref) || 0,
  rate: yizheStock.get(g.ref) ? g.qty / yizheStock.get(g.ref) : null, clients: g.clients.size }))
  .filter(s => s.stock > 0).sort((a, b) => (b.rate || 0) - (a.rate || 0));

// ---------- 新品上市（近35日上新：品类/金额/件单价 + 累计客户数Top10） ----------
const gctime = new Map(goods.map(g => [g.item_ref, +g.ctime]));
const newProduct = [];
{
  const byRef = new Map();
  rows.forEach(r => {
    if (r.ts < NOW - 35 * 86400) return;
    let x = byRef.get(r.ref);
    if (!x) { x = { qty: 0, amt: 0, clients: new Set() }; byRef.set(r.ref, x); }
    x.qty += r.qty; x.amt += r.amount; r.cid && x.clients.add(r.cid);
  });
  byRef.forEach((x, ref) => {
    const ct = gctime.get(ref);
    if (!ct) return;
    const listDate = beijing(ct);
    if ((NOW - ct) / 86400 > 35) return;
    const first7 = rows.filter(r => r.ref === ref && r.ts < ct + 7 * 86400);
    newProduct.push({ ref, name: goodsName.get(ref) || '', cat: catOf(ref), listDate, stock: dkStock.get(ref) ?? '-',
      weekQty: first7.reduce((s, r) => s + r.qty, 0), weekClients: new Set(first7.map(r => r.cid)).size,
      qty: x.qty, amt: x.amt, clients: x.clients.size, unitPrice: x.qty > 0 ? x.amt / x.qty : 0 });
  });
  newProduct.sort((a, b) => b.qty - a.qty);
}
const newProdClientTop = [...newProduct].sort((a, b) => b.clients - a.clients).slice(0, 10);
// 三档（2026-10-12 #11）：上市1-7天 / 7-15天 / 15-30天
const npTier = p => { const d = (NOW - (gctime.get(p.ref) || 0)) / 86400; return d < 7 ? '上市1-7天' : d < 15 ? '上市7-15天' : '上市15-30天'; };
newProduct.forEach(p => { p.tier = npTier(p); p.price = goodsPrice.get(p.ref) || 0; });


// ---------- 导购业绩（2026-10-12改：按日/周/月三周期 × 店铺分开） ----------
const sellerAgg = new Map(); // 30日汇总（兼容旧引用）
const sellerDaily = new Map(), sellerWeekly = new Map(), sellerMonthly = new Map();
const ymd = d => d.toISOString().slice(0, 10);
const bjNow = new Date((NOW + 8 * 3600) * 1000);
const bjYesterday = new Date(bjNow.getTime() - 86400 * 1000);
const yStr = ymd(bjYesterday);
const dow = (bjNow.getUTCDay() + 6) % 7 + 1;
const lastMon = new Date(bjNow.getTime() - (dow + 6) * 86400 * 1000);
const lastSun = new Date(lastMon.getTime() + 6 * 86400 * 1000);
const mon1 = new Date(Date.UTC(bjNow.getUTCFullYear(), bjNow.getUTCMonth(), 1));
const isoWeek = d => { const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())); const dayNum = (t.getUTCDay() + 6) % 7; t.setUTCDate(t.getUTCDate() - dayNum + 3); const ft = new Date(Date.UTC(t.getUTCFullYear(), 0, 4)); const fd = (ft.getUTCDay() + 6) % 7; ft.setUTCDate(ft.getUTCDate() - fd + 3); return t.getUTCFullYear() + '-W' + String(1 + Math.round((t - ft) / (7 * 86400 * 1000))).padStart(2, '0'); };
// ---------- 复购（V2.4 口径：客户再次购买同一款才算复购） ----------
// 按明细行时间序：客户×款 首次出现=首购，其后=复购
const custRefFirstTs = new Map(); // key: cid|ref -> first ts
const sortedRows = [...rows].sort((a, b) => a.ts - b.ts);
const repRows = sortedRows.map(r => {
  const k = r.cid + '|' + r.ref;
  const first = custRefFirstTs.get(k);
  if (first === undefined) { custRefFirstTs.set(k, r.ts); return { ...r, isRep: false }; }
  return { ...r, isRep: true };
});

// doc->复购金额/单行标记（由 repRows 明细推导；导购层 join）
const docRepAmt = new Map();
repRows.forEach(r => { if (!r.isRep) return; docRepAmt.set(String(r.doc_id), (docRepAmt.get(String(r.doc_id)) || 0) + r.amount); });
function aggSeller(map, key, o, oAmt, oQty, isNew) {
  let a = map.get(key);
  if (!a) { a = { shop: o.shop_name || '未知店', seller: o.seller_name || '未指定', qty: 0, amt: 0, buyN: 0, newBuyN: 0, oldBuyN: 0, newAmt: 0, oldAmt: 0, reorderAmt: 0, repAmt: 0, repBuyN: 0, times: 0 }; map.set(key, a); }
  a.qty += oQty; a.amt += oAmt; a.times++; if (oQty > 0) a.buyN++;
  const dRep = docRepAmt.get(String(o.id)) || 0;
  if (dRep > 0) { a.repAmt += dRep; a.repBuyN += oQty > 0 ? 1 : 0; }
  if (isNew) { a.newBuyN += oQty > 0 ? 1 : 0; a.newAmt += oAmt; } else { a.oldBuyN += oQty > 0 ? 1 : 0; a.oldAmt += oAmt; a.reorderAmt += oAmt; }
}
valid.filter(o => +o.ctime >= (mon1.getTime() / 1000 - 8 * 3600 - 8 * 86400)).forEach(o => {
  const oAmt = +o.calc_price || 0, oQty = +o.goods_quantity || 0;
  const ca = custAgg.get(gidOf(o.client_id));
  const isNew = !!(ca && ca.first === +o.ctime);
  const dt = new Date((+o.ctime + 8 * 3600) * 1000);
  const dStr = ymd(dt);
  if (+o.ctime >= NOW - 30 * 86400) aggSeller(sellerAgg, o.seller_name || '未指定', o, oAmt, oQty, isNew);
  if (dStr === yStr) aggSeller(sellerDaily, (o.shop_name || '未知店') + '|' + (o.seller_name || '未指定') + '|' + dStr, o, oAmt, oQty, isNew);
  if (dStr >= ymd(lastMon) && dStr <= ymd(lastSun)) aggSeller(sellerWeekly, (o.shop_name || '未知店') + '|' + (o.seller_name || '未指定') + '|' + isoWeek(dt), o, oAmt, oQty, isNew);
  if (dStr >= ymd(mon1) && dStr <= yStr) aggSeller(sellerMonthly, (o.shop_name || '未知店') + '|' + (o.seller_name || '未指定') + '|' + dStr.slice(0, 7), o, oAmt, oQty, isNew);
});
const sellerList = m => [...m.values()].sort((a, b) => a.shop.localeCompare(b.shop, 'zh') || b.amt - a.amt);

// ---------- 新客户月度分析（首单时间/客单/件单价，剔除退单） ----------
const monthNewRepeat = [];
custAgg.forEach((a, cid) => {
  if (a.buyN < 2) return;
  if ((NOW - a.first) / 86400 > 30) return;
  monthNewRepeat.push({ name: custName(cid), phone: phoneOf(cid), shop: shopOf(cid), first: beijing(a.first), times: a.buyN, qty: a.buyQty, amt: a.buyAmt, aov: aov(a), unitPrice: a.buyQty > 0 ? a.buyAmt / a.buyQty : 0 });
});
monthNewRepeat.sort((x, y) => y.times - x.times || y.amt - x.amt);

// ---------- 补单（2026-10-12 #5：改按款式统计） ----------
const reorderCust = new Map();
const reorderQty = new Map();
valid.forEach(o => {
  const a = custAgg.get(gidOf(o.client_id));
  if (!a) return;
  if (+o.ctime >= NOW - 30 * 86400 && a.first !== +o.ctime) {
    const gid = gidOf(o.client_id);
    reorderCust.set(gid, (reorderCust.get(gid) || 0) + (+o.calc_price || 0));
    reorderQty.set(gid, (reorderQty.get(gid) || 0) + (+o.goods_quantity || 0));
  }
});
// 补单款：明细行 join 客户首单时间——老客（下单时已非首单）拿的款计入补单量；分周/半月/月三窗
function reorderGoodsBy(days) {
  const cut = NOW - days * 86400;
  const m = new Map();
  rows.forEach(r => {
    if (r.ts < cut) return;
    const a = custAgg.get(r.cid);
    if (!a || a.first >= r.ts) return; // 新客首单行不算
    let g = m.get(r.ref);
    if (!g) { g = { ref: r.ref, qty: 0, amt: 0, clients: new Set() }; m.set(r.ref, g); }
    g.qty += r.qty; g.amt += r.amount; r.cid && g.clients.add(r.cid);
  });
  return m;
}
const rgW = reorderGoodsBy(7), rgH = reorderGoodsBy(15), rgM = reorderGoodsBy(30);

function repStatsBy(days) {
  const cut = NOW - days * 86400;
  let amt = 0, qty = 0, buyN = 0;
  const seen = new Map(); // doc 去重（复购单数按订单算）
  repRows.forEach(r => {
    if (r.ts < cut || !r.isRep) return;
    amt += r.amount; qty += r.qty;
    if (!seen.has(r.doc_id || (r.cid + r.date))) { seen.set(r.doc_id || (r.cid + r.date), 1); buyN++; }
  });
  return { amt, qty, buyN };
}
const rep7 = repStatsBy(7), rep15 = repStatsBy(15), rep30 = repStatsBy(30);
// 客户复购金额TOP（复购口径）
const repCustAgg = new Map();
repRows.forEach(r => { if (!r.isRep || r.ts < NOW - 30 * 86400) return; const k = r.cid; let a = repCustAgg.get(k); if (!a) { a = { amt: 0, qty: 0 }; repCustAgg.set(k, a); } a.amt += r.amount; a.qty += r.qty; });

// ---------- 库存告急与积压（当年当季：year=2026年 season=冬季；周/月销量+周转） ----------
const isCurrentSeason = ref => goodsYear.get(ref) === '2026年' && goodsSeason.get(ref) === '冬季';
const seasonStock = goods.filter(g => isCurrentSeason(g.item_ref))
  .map(g => ({ ref: g.item_ref, name: g.name || '', stock: dkStock.get(g.item_ref) || 0, w: (gW.get(g.item_ref)?.qty) || 0, m: (gM.get(g.item_ref)?.qty) || 0 }))
  .map(x => ({ ...x, turn: x.w > 0 ? (x.stock / x.w).toFixed(1) : '∞' }));
// 积压：库存最大
const stockMax = seasonStock.filter(x => x.stock > 0).sort((a, b) => b.stock - a.stock).slice(0, 15);
// 告急（2026-10-12 新定义）：总库存 < 近7日销量×2（卖不过两周即告急）
const stockWarn = seasonStock.filter(x => x.stock > 0 && x.w > 0 && x.stock < x.w * 2).sort((a, b) => (a.stock / Math.max(0.1, a.w)) - (b.stock / Math.max(0.1, b.w))).slice(0, 30);
// 预售欠货：负库存（卖超了，补货最紧急），按近30日销量排
const stockOwed = seasonStock.filter(x => x.stock < 0).sort((a, b) => b.m - a.m).slice(0, 20);

// ========== 输出 ==========
let md = '';
md += `# 销售数据报告 V2（销售部需求 v1.1 + 销售负责人修正意见）\n\n`;
md += `- **取数时间**：2026-10-10（数据截至当日 11:00，含 10-09/10-10 新单）\n- **数据源**：多客销售单据 ${valid.length} 单（2023-10 至今）、订单商品明细全量、客户档案 ${customers.length} 家、多客实时库存 ${goods.length} 款、衣者当前库存 ${stockYizhe.length} 款\n- **口径**：新客=客户首次下单（按 3 年全历史推导）；客单价=购买金额÷购买单数（退单不计入）；补单金额=老客（非首单）下单金额；连带=件数÷购买单数\n- **⚠️ 数据披露**：① 负库存=预售欠货（正常）；② 售罄率分母为衣者当前库存（非累计总进货），等系统方加字段后切换；③ 当年当季=多客 2026年+冬季；④ 内部账户剔除清单待销售负责人提供\n- **👤 客户账户合并（V2.1）**：多客存在同人多个账户（同名多户/同手机号多户，共 ${MERGE_GROUPS.length} 组涉及 ${MERGE_GROUPS.reduce((s2, g) => s2 + g.ids.length, 0)} 账户）。本报告已将同人账户合并为一户统计（客户数、新老客、流失名单、补单榜均按合并口径）。合并明细见《客户账户合并审计表-2026-10-10.md》，业务核对后如发现误合并（同名不同人）请告知组号，将拆开重算。\n\n---\n\n`;

// 一、总览
md += `## 一、总览（日/周/月下单回款）【需求9】\n\n`;
md += `| 周期 | 单数 | 购买单数 | 金额(¥) | 件数 | 平均每单连带(件) | 新客购买单数 | 新客金额 | 新客连带 | 老客购买单数 | 老客金额 | 老客连带 | 补单金额(老客) |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|\n`;
[[p7, '近7日'], [p15, '近半月'], [p30, '近30日']].forEach(([p, l]) => {
  md += `| ${l} | ${p.orders} | ${p.buyN} | ${money(p.amt)} | ${money(p.qty)} | ${f1(p.attach)} | ${p.newBuyN} | ${money(p.newAmt)} | ${f1(p.newAttach)} | ${p.oldBuyN} | ${money(p.oldAmt)} | ${f1(p.oldAttach)} | ${money(p.reorderAmt)} |\n`;
});
md += `\n> 补单金额口径：老客（非该客户历史首单）下单金额之和；新客首单金额=${money(p30.firstAmt)}（近30日）。退单为负数自然冲减。\n`;

// 二、新老客（含建单价，2026-10-12 #1）
const newAov = p30.newBuyN > 0 ? p30.newAmt / p30.newBuyN : 0;
const oldAov = p30.oldBuyN > 0 ? p30.oldAmt / p30.oldBuyN : 0;
md += `\n## 二、新老客户占比【需求5】（近30日）\n\n- 购买单数：新客 ${p30.newBuyN} / 老客 ${p30.oldBuyN}（${Math.round(p30.newBuyN / Math.max(1, p30.newBuyN + p30.oldBuyN) * 100)}% : ${Math.round(p30.oldBuyN / Math.max(1, p30.newBuyN + p30.oldBuyN) * 100)}%）\n- 金额贡献：新客 ${money(p30.newAmt)} / 老客 ${money(p30.oldAmt)}\n- 连带对比：新客 ${f1(p30.newAttach)} 件/单 vs 老客 ${f1(p30.oldAttach)} 件/单\n- 建单价：新客 ${money(newAov)} vs 老客 ${money(oldAov)}\n`;

// 三、流失名单
const tierTbl = (title, arr, note) => {
  let s = `### ${title}\n\n`;
  if (note) s += `${note}\n\n`;
  s += `| 客户 | 等级 | 最后下单 | 间隔(天) | 下单数 | 退单数 | 购买件数 | 退货件数 | 购买金额(¥) | 退货金额(¥) | 客单价 | 件单价 |\n|---|---|---|---|---|---|---|---|---|---|---|---|\n`;
  arr.slice(0, 30).forEach(r => { s += `| ${esc(r.name)} | ${r.vip} | ${r.last} | ${r.gapDays} | ${r.buyN} | ${r.retN} | ${money(r.buyQty)} | ${money(r.retQty)} | ${money(r.buyAmt)} | ${money(r.retAmt)} | ${money(r.aov)} | ${f1(r.unitPrice)} |\n`; });
  return s + '\n';
};
md += `\n## 三、客户流失预警名单【需求3附/6/10】\n\n`;
md += tierTbl(`3-1 超30-60天未下单（${tier1.length} 家，按净额排序，每日推业务跟进）`, tier1);
md += tierTbl(`3-2 超60天-1年未下单（${tier2.length} 家）`, tier2);
md += tierTbl(`3-3 超1年-2年未下单（${tier3.length} 家；超2年已剔除）`, tier3);
md += `### 3-4 新客未复购【需求6】\n\n**15天档** ${newClient15.length} 家（首单后未下第二单）Top20：\n\n| 客户 | 首单日 | 距首单(天) | 首单金额 | 首单件数 |\n|---|---|---|---|---|\n`;
newClient15.slice(0, 20).forEach(r => { md += `| ${esc(r.name)} | ${r.first} | ${r.gapDays} | ${money(r.amt)} | ${r.qty} |\n`; });
md += `\n**1个月档** ${newClient30.length} 家（完整见JSON）\n\n`;
md += `### 3-5 老客断档（间隔>1月）【需求6】共 ${oldClientGap.length} 家 Top20\n\n| 客户 | 等级 | 历史单数 | 最后下单 | 间隔(天) | 累计金额 |\n|---|---|---|---|---|---|\n`;
oldClientGap.slice(0, 20).forEach(r => { md += `| ${esc(r.name)} | ${r.vip} | ${r.times} | ${r.last} | ${r.gapDays} | ${money(r.amt)} |\n`; });
md += `\n### 3-6 老客盘活名单（超3个月~2年，含首单时间）【需求10】共 ${revive.length} 家，按历史净额 Top30\n\n`;
md += `| 客户 | 等级 | 首单时间 | 最后下单 | 间隔(天) | 下单数 | 退单数 | 净件数 | 净额(¥) | 客单价 | 件单价 |\n|---|---|---|---|---|---|---|---|---|---|---|\n`;
revive.slice(0, 30).forEach(r => { md += `| ${esc(r.name)} | ${r.vip} | ${r.first} | ${r.last} | ${r.gapDays} | ${r.buyN} | ${r.retN} | ${money(r.netQty)} | ${money(r.netAmt)} | ${money(r.aov)} | ${f1(r.unitPrice)} |\n`; });

// 四、ABCD
const vipStats = new Map();
valid.filter(o => +o.ctime >= NOW - 30 * 86400).forEach(o => {
  const vr = vipRawOf(gidOf(o.client_id)) || '0';
  const k = `vip${vr}`;
  let a = vipStats.get(k); if (!a) { a = { orders: 0, amt: 0, qty: 0 }; vipStats.set(k, a); }
  a.orders++; a.amt += +o.calc_price || 0; a.qty += +o.goods_quantity || 0;
});
md += `\n## 四、ABCD 客户（系统等级字段 vip）【需求8】\n\n`;
md += `| 等级 | 30日单数 | 30日金额(¥) | 30日件数 |\n|---|---|---|---|\n`;
[...vipStats.entries()].sort().forEach(([k, a]) => { md += `| ${k} | ${a.orders} | ${money(a.amt)} | ${money(a.qty)} |\n`; });
md += `\n> 名称对应（vip2=B/vip3=A/vip4=C 为暂标）待销售负责人确认。\n`;

// 五、导购
md += `\n## 五、导购业绩（近30日）【需求4】\n\n`;
md += `| 导购 | 单数 | 件数 | 金额(¥) | 新客购买单数 | 新客金额 | 老客购买单数 | 老客金额 | 补单金额 |\n|---|---|---|---|---|---|---|---|---|\n`;
[...sellerAgg.entries()].sort((a, b) => b[1].amt - a[1].amt).forEach(([s, a]) => {
  md += `| ${esc(s)} | ${a.times} | ${money(a.qty)} | ${money(a.amt)} | ${a.newBuyN} | ${money(a.newAmt)} | ${a.oldBuyN} | ${money(a.oldAmt)} | ${money(a.reorderAmt)} |\n`;
});

// 六、款级
const moveTbl = (title, arr, withStock = true) => {
  let s = `### ${title}\n\n| 款号 | 款名 | 品类 | 销量 | 销售额(¥) | 下单客户数${withStock ? ' | 实时库存' : ''} |\n|---|---|---|---|---|---|${withStock ? '---|' : ''}\n`;
  arr.forEach(g => { s += `| ${g.ref} | ${esc(g.name)} | ${esc(g.cat)} | ${g.qty} | ${money(g.amt)} | ${g.clients}${withStock ? ` | ${g.stock}` : ''} |\n`; });
  return s + '\n';
};
md += `\n## 六、款级动销与售罄【需求1/2/11】\n\n`;
md += moveTbl('6-1 动销 TOP30·近7日（全品类）', topN(gW, 30));
md += moveTbl('6-2 动销 TOP30·近半月（全品类）', topN(gH, 30));
md += moveTbl('6-3 动销 TOP30·近30日（全品类）', topN(gM, 30));
md += `### 6-4 动销率（近30日，>100件为有效动销）\n\n- 统计款式数 ${totalStyles30}，超100件 ${active30}，**动销率 ${(active30 / totalStyles30 * 100).toFixed(1)}%**；销量≤100件 ${totalStyles30 - active30} 款（完整清单见JSON）\n`;
mainCats.forEach(c => { md += moveTbl(`6-5 单品类 TOP10·近30日｜${c}`, catTop[c]); });
md += `### 6-6 售罄率 TOP15（近30日销量 ÷ 衣者当前库存）\n\n| 款号 | 款名 | 近30日销量 | 当前库存(衣者) | 售罄率 | 客户数 |\n|---|---|---|---|---|---|\n`;
sellThrough.slice(0, 15).forEach(s => { md += `| ${s.ref} | ${esc(s.name)} | ${s.sold30} | ${s.stock} | ${(s.rate * 100).toFixed(0)}% | ${s.clients} |\n`; });
md += `\n> 售罄率=近30日销量÷衣者当前库存（会议口径的分母应为累计总进货数，待系统方新增字段后切换）。>100% 表示近期销量已超当前库存（补单/预售在途）。\n`;

// 新品
md += `### 6-7 新品上市一周/一月（近35日上新，按多客建档日≈上市）【需求1】\n\n`;
md += `| 款号 | 款名 | 品类 | 上市日 | 首周销量 | 首周客户数 | 累计销量 | 累计金额(¥) | 件单价 |\n|---|---|---|---|---|---|---|---|---|\n`;
newProduct.slice(0, 20).forEach(p => { md += `| ${p.ref} | ${esc(p.name)} | ${esc(p.cat)} | ${p.listDate} | ${p.weekQty} | ${p.weekClients} | ${p.qty} | ${money(p.amt)} | ${f1(p.unitPrice)} |\n`; });
md += `\n### 6-8 新品累计客户数 TOP10（普及面：对照 150 家标准）\n\n| 款号 | 款名 | 品类 | 上市日 | 累计客户数 | 累计销量 | 累计金额(¥) |\n|---|---|---|---|---|---|---|\n`;
newProdClientTop.forEach(p => { md += `| ${p.ref} | ${esc(p.name)} | ${esc(p.cat)} | ${p.listDate} | ${p.clients} | ${p.qty} | ${money(p.amt)} |\n`; });

// 七、补单
md += `\n## 七、补单分析【需求2】（客户行为口径：老客任意再下单=补单）近30日金额 Top10\n\n| 客户 | 近30日补单金额 | 近30日补单件数 | 等级 |\n|---|---|---|---|\n`;
[...reorderCust.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).forEach(([gid, amt]) => {
  md += `| ${esc(custName(gid))} | ${money(amt)} | ${money(reorderQty.get(gid) || 0)} | ${vipOf(gid)} |\n`;
});

// 八、新客月度
md += `\n## 八、新客户月度分析【需求7】（近30日首单且已复购，购买口径剔除退单）\n\n`;
md += `| 客户 | 首单时间 | 购买单数 | 购买件数 | 购买金额(¥) | 客单价 | 件单价 |\n|---|---|---|---|---|---|---|\n`;
monthNewRepeat.slice(0, 15).forEach(r => { md += `| ${esc(r.name)} | ${r.first} | ${r.times} | ${money(r.qty)} | ${money(r.amt)} | ${money(r.aov)} | ${f1(r.unitPrice)} |\n`; });

// 九、库存
md += `\n## 九、库存积压与告急【需求9附】（仅当年当季：2026年·冬季）\n\n`;
md += `### 9-1 实时库存最大 Top15（需消化）\n\n| 款号 | 款名 | 实时库存 | 近7日销量 | 近30日销量 | 预估周转(周) |\n|---|---|---|---|---|---|\n`;
stockMax.forEach(s => { md += `| ${s.ref} | ${esc(s.name)} | ${s.stock} | ${s.w} | ${s.m} | ${s.turn} |\n`; });
md += `\n### 9-2 库存告急（0<库存<50 且近30日有销量，按动销强度排）Top30\n\n| 款号 | 款名 | 实时库存 | 近7日销量 | 近30日销量 | 预估周转(周) |\n|---|---|---|---|---|---|\n`;
stockWarn.forEach(s => { md += `| ${s.ref} | ${esc(s.name)} | ${s.stock} | ${s.w} | ${s.m} | ${s.turn} |\n`; });
md += `\n### 9-3 预售欠货（负库存=卖超待补，按近30日销量排）Top20——补货最紧急\n\n| 款号 | 款名 | 实时库存(负) | 近7日销量 | 近30日销量 |\n|---|---|---|---|---|\n`;
stockOwed.forEach(s => { md += `| ${s.ref} | ${esc(s.name)} | ${s.stock} | ${s.w} | ${s.m} |\n`; });
md += `\n> 周转=库存÷近7日销量（∞=近7日无销量）；零库存且零销量的未上档案未列入告急；告急线 <50 件为暂定参数。负库存=预售欠货（属正常业务，多客先行销售）。近30日销量>0 但库存=0 的断货款已含在 9-3（库存0或负）。若需"断货即失单"清单可在 JSON 中筛 stock<=0 && m>0。\n`;

// 十、待定
md += `\n## 十、待定参数（需销售负责人/系统方拍板）\n\n1. 售罄预警阈值（40%/30%/50%）、库存告急线（<50件）\n2. 多客「总进货数」字段（累计）——售罄率分母切换\n3. ABCD 与 vip 1/2/3/4 对应关系\n4. 内部账户剔除清单（工厂主体、清货、特卖账户等）\n5. 需求12（保本/亏本款）与 13（上市×气温）待后续\n`;

fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, '销售数据报告-2026-10-12.md'), md);

// JSON 完整名单（2026-10-12 V2.1 全新结构）
const dormantRecExport = r => ({ ...r, phone: r.phone || '' });
const tierRows = arr => arr.map(dormantRecExport);
const sellThroughExport = sellThrough.map(x => ({ ...x, listDate: goodsListDate.get(x.ref) || '', price: goodsPrice.get(x.ref) || 0 }));
const jsonOut = {
  generated_at: new Date().toISOString(),
  overview: { p7, p15, p30, newAov, oldAov },
  month_missing: monthMissing,
  new_ratio_30d: { newBuyN: p30.newBuyN, oldBuyN: p30.oldBuyN, newAmt: p30.newAmt, oldAmt: p30.oldAmt, newAttach: p30.newAttach, oldAttach: p30.oldAttach, newAov, oldAov },
  new_client_15_30: nc1530, new_client_30_60: nc3060,
  reorder_goods_week: topN(rgW, 30), reorder_goods_halfmonth: topN(rgH, 30), reorder_goods_month: topN(rgM, 30),
  reorder_customer_top: [...reorderCust.entries()].sort((a, b) => b[1] - a[1]).slice(0, 30).map(([gid, amt]) => ({ name: custName(gid), phone: phoneOf(gid), vip: vipOf(gid), reorderAmt: amt, reorderQty: reorderQty.get(gid) || 0 })),
  move_top_week: topN(gW, 30), move_top_halfmonth: topN(gH, 30), move_top_month: topN(gM, 30),
  move_top_week_ex: topN(gW, 30, 2), move_top_halfmonth_ex: topN(gH, 30, 2), move_top_month_ex: topN(gM, 30, 2),
  move_rate_30d: { total_styles: totalStyles30, active_over100: active30 },
  cat_top_month: catTop,
  sell_through_30d: sellThroughExport,
  new_product: newProduct, new_product_client_top: newProdClientTop.map(p => ({ ...p, tier: npTier(p), price: goodsPrice.get(p.ref) || 0 })),
  new_client_monthly: monthNewRepeat.map(r => ({ ...r, phone: phoneOf(custAgg.has(r.name) ? r.name : 'S' + r.name) || '' })),
  seller_30d: [...sellerAgg.values()].map(a => ({ ...a })),
  repurchase: { p7: rep7, p15: rep15, p30: rep30 },
  repurchase_goods_week: [...(function(){ const m = new Map(); repRows.forEach(r => { if (r.ts < NOW - 7 * 86400 || !r.isRep) return; let g = m.get(r.ref); if (!g) { g = { ref: r.ref, qty: 0, amt: 0, clients: new Set() }; m.set(r.ref, g); } g.qty += r.qty; g.amt += r.amount; g.clients.add(r.cid); }); return [...m.values()].sort((a, b) => b.amt - a.amt).slice(0, 30).map(g => ({ ...g, clients: g.clients.size, name: goodsName.get(g.ref) || '', cat: catOf(g.ref), listDate: goodsListDate.get(g.ref) || '', price: goodsPrice.get(g.ref) || 0 })); })()],
  repurchase_goods_halfmonth: [...(function(){ const m = new Map(); repRows.forEach(r => { if (r.ts < NOW - 15 * 86400 || !r.isRep) return; let g = m.get(r.ref); if (!g) { g = { ref: r.ref, qty: 0, amt: 0, clients: new Set() }; m.set(r.ref, g); } g.qty += r.qty; g.amt += r.amount; g.clients.add(r.cid); }); return [...m.values()].sort((a, b) => b.amt - a.amt).slice(0, 30).map(g => ({ ...g, clients: g.clients.size, name: goodsName.get(g.ref) || '', cat: catOf(g.ref), listDate: goodsListDate.get(g.ref) || '', price: goodsPrice.get(g.ref) || 0 })); })()],
  repurchase_goods_month: [...(function(){ const m = new Map(); repRows.forEach(r => { if (r.ts < NOW - 30 * 86400 || !r.isRep) return; let g = m.get(r.ref); if (!g) { g = { ref: r.ref, qty: 0, amt: 0, clients: new Set() }; m.set(r.ref, g); } g.qty += r.qty; g.amt += r.amount; g.clients.add(r.cid); }); return [...m.values()].sort((a, b) => b.amt - a.amt).slice(0, 30).map(g => ({ ...g, clients: g.clients.size, name: goodsName.get(g.ref) || '', cat: catOf(g.ref), listDate: goodsListDate.get(g.ref) || '', price: goodsPrice.get(g.ref) || 0 })); })()],
  seller_daily: sellerList(sellerDaily), seller_weekly: sellerList(sellerWeekly), seller_monthly: sellerList(sellerMonthly),
  seller_windows: { daily: yStr, weekly: ymd(lastMon) + '~' + ymd(lastSun), monthly: ymd(mon1) + '~' + yStr },
  vip_30d: Object.fromEntries(vipStats),
  stock_max_current_season: stockMax.map(x => ({ ...x, cat: catOf(x.ref), listDate: goodsListDate.get(x.ref) || '', price: goodsPrice.get(x.ref) || 0 })),
  stock_warn_current_season: stockWarn.map(x => ({ ...x, cat: catOf(x.ref), listDate: goodsListDate.get(x.ref) || '', price: goodsPrice.get(x.ref) || 0 })),
  dormant_30_60: tierRows(tier1), dormant_60_365: tierRows(tier2), dormant_365_730: tierRows(tier3),
  revive_90up: revive.map(r => ({ ...r, phone: phoneOf(r.cid) || '' })),
};
const TODAY = new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10);
fs.writeFileSync(path.join(OUT, `销售数据报告-${TODAY}.json`), JSON.stringify(jsonOut, null, 1));
console.log('REPORT json ->', `销售数据报告-${TODAY}.json`);
console.log('REPORT V2 ->', path.join(OUT, '销售数据报告-2026-10-10.md'), `(${md.length} chars)`);
console.log(`tiers: 30-60=${tier1.length} 60-365=${tier2.length} 365-730=${tier3.length} | revive=${revive.length} | newProd=${newProduct.length} | warn=${stockWarn.length}`);
