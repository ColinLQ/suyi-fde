#!/usr/bin/env node
// 春季畅销滞销与利润复盘 —— 核心计算（参数化：--year 2025|2026）
// 数据源：duoke_goods(商品快照2026-10-09) + duoke_order_details(3年明细) + yizhe_production_<year>spring(生产单)
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');  // skill代码根目录（可移植）
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const RAW09 = path.join(dataHome, 'data/raw/2026-10-09/pm');
const RAW10 = path.join(dataHome, 'data/raw/2026-10-10/pm');
const OUT = path.join(dataHome, 'out');

const YEAR = process.argv.includes('--year') ? process.argv[process.argv.indexOf('--year') + 1] : '2025';
const OUTJSON = path.join(OUT, `spring${YEAR.slice(2)}-review-data.json`);

const read = f => fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
const goods = read(path.join(RAW09, 'duoke_goods.jsonl'));
const ods = read(path.join(RAW09, 'duoke_order_details.jsonl'));
const prod = read(path.join(RAW10, `yizhe_production_${YEAR}spring.jsonl`));
const prodDetails = read(path.join(RAW10, `yizhe_production_${YEAR}spring_details.jsonl`));

// 颜色归一化：卡其/卡其色→卡其，米杏/米杏色→米杏 等
const normColor = c => {
  if (!c) return '未知';
  let x = String(c).trim();
  x = x.replace(/色$/, m => ['杂色', '卡其色', '杏色', '米色'].includes(x) ? m : '');
  const map = { '卡其色': '卡其', '米杏色': '米杏', '藏青色': '藏青', '墨绿色': '墨绿', '酒红色': '酒红', '粉红色': '粉红', '橘黄色': '橘黄', '乳白色': '乳白', '天蓝色': '天蓝', '深蓝色': '深蓝', '浅蓝色': '浅蓝', '浅灰色': '浅灰', '深灰色': '深灰', '黑底白线': '黑底印花', '白底黑线': '白底印花' };
  return map[x] || x;
};

// ---------- 基础表 ----------
const goodsByRef = new Map(goods.map(g => [g.item_ref, g]));
const imgBase = 'http://cn-cdn-oss.duoke.net/user_19228/';
function firstImg(g) {
  for (const s of Object.values(g.sku || {})) {
    const im = (s.img || []).find(x => x);
    if (im) return imgBase + im;
  }
  return '';
}
function stockOf(g) {
  let t = 0;
  for (const s of Object.values(g.sku || {})) {
    for (const [k, v] of Object.entries(s)) {
      if (/^warehouse_\d+$/.test(k) || /^store_stock_\d+$/.test(k)) t += (+v || 0);
    }
  }
  return t;
}

// ---------- 1. 销售明细聚合（全盘 + 2025春） ----------
// salesByRef: 全生命周期净销量/净金额(3年窗)  daySales: 款×日 净量  colorSales: 款×色  refCustomerDocs: 款×客户×单据
const salesByRef = new Map();   // ref -> {qty, amt, firstDay, lastDay}
const daySales = new Map();     // ref|day -> qty
const colorSales = new Map();   // ref|color -> qty
const custDocs = new Map();     // ref|client -> [{doc, day, qty}]
for (const o of ods) {
  const day = new Date(o.goods[0].ctime * 1000).toISOString().slice(0, 10);
  for (const g of o.goods) {
    const ref = g.item_ref;
    const e = salesByRef.get(ref) || { qty: 0, amt: 0 };
    e.qty += g.quantity; e.amt += g.quantity * (g.price || 0);
    salesByRef.set(ref, e);
    daySales.set(ref + '|' + day, (daySales.get(ref + '|' + day) || 0) + g.quantity);
    colorSales.set(ref + '|' + g.color, (colorSales.get(ref + '|' + g.color) || 0) + g.quantity);
    const ck = ref + '|' + g.client_id;
    if (!custDocs.has(ck)) custDocs.set(ck, []);
    const dl = custDocs.get(ck);
    let d = dl.find(x => x.doc === o.doc_id);
    if (!d) { d = { doc: o.doc_id, day, qty: 0 }; dl.push(d); }
    d.qty += g.quantity;
  }
}
// 退货（负行）按款聚合
const returnByRef = new Map();
const returnRows = [];
for (const o of ods) for (const g of o.goods) {
  if (g.quantity < 0) {
    returnByRef.set(g.item_ref, (returnByRef.get(g.item_ref) || 0) + g.quantity);
    if (!returnRows.some(r => r.ref === g.item_ref)) returnRows.push({ ref: g.item_ref, name: g.name, cat: g.category, year: g.year, season: g.season });
  }
}

// ---------- 2. 2025春款基础表 ----------
const springItems = goods.filter(g => g.year?.name === YEAR + '年' && g.season?.name === '春季');
const s25Refs = new Set(springItems.map(g => g.item_ref));
const s25ByRef = new Map(springItems.map(g => [g.item_ref, g]));

// 生产聚合（按款）：计划件数、实际入库、生产单数、首张生产日期
const prodByRef = new Map();
for (const p of prod) {
  const ref = p.template_no;
  if (!s25Refs.has(ref)) continue;
  const e = prodByRef.get(ref) || { plan: 0, inNum: 0, orders: 0, firstDate: p.created_at, remarks: [] };
  e.plan += (+p.plan_total_num || 0);
  e.inNum += (p.stock_in_num?.value ?? 0);
  e.orders += 1;
  if (p.created_at < e.firstDate) e.firstDate = p.created_at;
  if (p.order_remark) e.remarks.push(p.order_remark);
  prodByRef.set(ref, e);
}

// ---------- 3. 指标计算 ----------
const R = {};
const decorate = ref => {
  const g = s25ByRef.get(ref) || goodsByRef.get(ref);
  const s = salesByRef.get(ref) || { qty: 0, amt: 0 };
  return {
    ref, name: g?.name || '', cat: g?.cate_info?.name || '', img: g ? firstImg(g) : '',
    qty: s.qty, amt: Math.round(s.amt), stock: g ? stockOf(g) : 0,
    price: g?.price_range?.range?.[0] || '',
    ctime: g ? new Date(g.ctime * 1000).toISOString().slice(0, 10) : ''
  };
};

// ⑨(先算) 颜色生产占比：基于生产单详情 sku_detail 精确统计
const colorProdAgg = new Map(); let colorProdTotal = 0;
for (const d of prodDetails) for (const co of d.sku || []) {
  const cn = normColor(co.co_val);
  colorProdAgg.set(cn, (colorProdAgg.get(cn) || 0) + (+co.total_num || 0));
  colorProdTotal += (+co.total_num || 0);
}

// ① 2025春 畅销TOP20 / ② 滞销TOP20（净销量升序）
const s25Sales = [...s25Refs].map(ref => {
  const d = decorate(ref);
  const p = prodByRef.get(ref);
  return { ...d, plan: p?.plan || 0, inNum: p?.inNum || 0 };
});
R.hot20 = [...s25Sales].sort((a, b) => b.qty - a.qty).slice(0, 20);
R.cold20 = [...s25Sales].sort((a, b) => a.qty - b.qty).slice(0, 20);

// ③ 2025春 售罄率 TOP10/Bottom10（口径收紧：仅2025年春季款；净销量/(净销量+当前库存)；过滤负库存超卖与负净销款，另列超卖榜）
const allItems = springItems.map(g => {
  const s = salesByRef.get(g.item_ref) || { qty: 0, amt: 0 };
  const stock = stockOf(g);
  return { ref: g.item_ref, name: g.name, cat: g.cate_info?.name, img: firstImg(g), qty: s.qty, stock, rate: (s.qty + stock) > 0 ? s.qty / (s.qty + stock) : null, year: g.year?.name, season: g.season?.name };
}).filter(x => x.rate !== null && (x.qty > 0 || x.stock > 0));
const normalRate = allItems.filter(x => x.qty > 20 && x.stock >= 0 && (x.qty + x.stock) >= 50);
R.selloutTop10 = [...normalRate].sort((a, b) => b.rate - a.rate || b.qty - a.qty).slice(0, 10).map(x => ({ ...x, rate: (x.rate * 100).toFixed(1) }));
R.selloutLow10 = [...normalRate].sort((a, b) => a.rate - b.rate || b.stock - a.stock).slice(0, 10).map(x => ({ ...x, rate: (x.rate * 100).toFixed(1) }));
R.oversellTop = allItems.filter(x => x.stock < 0).sort((a, b) => a.stock - b.stock).slice(0, 10).map(x => ({ ref: x.ref, name: x.name, cat: x.cat, img: x.img, qty: x.qty, stock: x.stock }));

// ④ 品类售罄率 TOP5/Bottom5（仅2025春款聚合）
const catAgg = new Map();
for (const x of allItems) {
  const c = catAgg.get(x.cat) || { qty: 0, stock: 0, styles: 0 };
  c.qty += x.qty; c.stock += x.stock; c.styles++;
  catAgg.set(x.cat, c);
}
const catRates = [...catAgg.entries()].filter(([, v]) => v.styles >= 3).map(([cat, v]) => ({ cat, ...v, rate: v.qty / (v.qty + v.stock) * 100 })).sort((a, b) => b.rate - a.rate);
R.catTop5 = catRates.slice(0, 5).map(x => ({ ...x, rate: x.rate.toFixed(1) }));
R.catLow5 = [...catRates].reverse().slice(0, 5).map(x => ({ ...x, rate: x.rate.toFixed(1) }));

// ⑤ 库存最大TOP20（仅2025春款）
R.stockTop20 = [...allItems].sort((a, b) => b.stock - a.stock).slice(0, 20);

// ⑥⑦ 上市1个月/2个月动销率（2025春，上市日=商品建档日；动销率=窗口净销量/生产计划件数）
const winRate = (ref, days) => {
  const g = s25ByRef.get(ref);
  const start = new Date(g.ctime * 1000);
  const end = new Date(start.getTime() + days * 86400000);
  const sd = start.toISOString().slice(0, 10), ed = end.toISOString().slice(0, 10);
  let qty = 0;
  for (const [k, v] of daySales) {
    const [r, d] = k.split('|');
    if (r === ref && d >= sd && d <= ed) qty += v;
  }
  return qty;
};
const launchStats = s25Sales.map(x => {
  const plan = x.plan || x.qty || 1;
  return { ...x, q30: winRate(x.ref, 30), q60: winRate(x.ref, 60), r30: winRate(x.ref, 30) / plan, r60: winRate(x.ref, 60) / plan };
});
R.month1Top10 = [...launchStats].sort((a, b) => b.r30 - a.r30).slice(0, 10);
R.month1Low10 = [...launchStats].sort((a, b) => a.r30 - b.r30).slice(0, 10);
R.month2Top10 = [...launchStats].sort((a, b) => b.r60 - a.r60).slice(0, 10);
R.month2Low10 = [...launchStats].sort((a, b) => a.r60 - b.r60).slice(0, 10);

// ⑧ 品类 生产占比 vs 销售占比（2025春）
const catProd = new Map(), catSale = new Map();
let totPlan = 0, totQty = 0, totAmt = 0, totStyles = 0;
for (const x of s25Sales) {
  const c = x.cat || '未分类';
  const p = prodByRef.get(x.ref);
  const plan = p?.plan || 0;
  const cp = catProd.get(c) || { styles: 0, plan: 0 };
  cp.styles++; cp.plan += plan; catProd.set(c, cp);
  const cs = catSale.get(c) || { qty: 0, amt: 0 };
  cs.qty += x.qty; cs.amt += x.amt; catSale.set(c, cs);
  totPlan += plan; totQty += x.qty; totAmt += x.amt; totStyles++;
}
R.catCompare = [...catProd.keys()].map(c => ({
  cat: c, styles: catProd.get(c).styles, plan: catProd.get(c).plan,
  qty: catSale.get(c)?.qty || 0, amt: Math.round(catSale.get(c)?.amt || 0),
  styleShare: (catProd.get(c).styles / totStyles * 100).toFixed(1),
  prodShare: totPlan ? (catProd.get(c).plan / totPlan * 100).toFixed(1) : '0.0',
  qtyShare: totQty ? ((catSale.get(c)?.qty || 0) / totQty * 100).toFixed(1) : '0.0',
  amtShare: totAmt ? ((catSale.get(c)?.amt || 0) / totAmt * 100).toFixed(1) : '0.0'
})).sort((a, b) => b.plan - a.plan);
R.totals = { totPlan, totQty, totAmt: Math.round(totAmt), totStyles };

// ⑨ 颜色 销售：基于明细行的 color 字段（归一化后聚合）
const colorSale = new Map(); let colorSaleTotal = 0;
for (const o of ods) for (const g of o.goods) {
  if (!s25Refs.has(g.item_ref) || g.quantity <= 0) continue;
  const cn = normColor(g.color);
  colorSale.set(cn, (colorSale.get(cn) || 0) + g.quantity);
  colorSaleTotal += g.quantity;
}
R.colorCompare = {
  prod: [...colorProdAgg.entries()].sort((a, b) => b[1] - a[1]).slice(0, 15).map(([c, n]) => ({ c, n, share: (n / colorProdTotal * 100).toFixed(1) })),
  sale: [...colorSale.entries()].sort((a, b) => b[1] - a[1]).slice(0, 15).map(([c, n]) => ({ c, n, share: (n / colorSaleTotal * 100).toFixed(1) })),
  prodTotal: colorProdTotal, saleTotal: colorSaleTotal
};

// ⑩ 价格段(10元档) 生产vs销售（生产=款price_1×plan；销售=明细成交价×qty）
const priceBand = p => p <= 0 ? null : Math.floor(p / 10) * 10;
const bandProd = new Map(), bandSale = new Map();
let bandProdTot = 0, bandSaleQty = 0;
for (const x of s25Sales) {
  const g = s25ByRef.get(x.ref);
  const pv = parseFloat(g?.price_range?.range?.[0] || '0');
  const b = priceBand(pv); if (b === null) continue;
  const p = prodByRef.get(x.ref);
  const plan = p?.plan || 0;
  const e = bandProd.get(b) || { styles: 0, plan: 0 };
  e.styles++; e.plan += plan; bandProd.set(b, e); bandProdTot += plan;
}
for (const o of ods) for (const g of o.goods) {
  if (!s25Refs.has(g.item_ref) || g.quantity <= 0) continue;
  if (g.price < 15 || g.price > 400) continue; // 过滤异常价（赠品/内部处理/录错价）
  const b = priceBand(g.price); if (b === null) continue;
  const e = bandSale.get(b) || { qty: 0, amt: 0 };
  e.qty += g.quantity; e.amt += g.quantity * g.price;
  bandSale.set(b, e); bandSaleQty += g.quantity;
}
const bands = [...new Set([...bandProd.keys(), ...bandSale.keys()])].filter(b => (bandProd.get(b)?.plan || 0) > 0 || (bandSale.get(b)?.qty || 0) > 0).sort((a, b) => a - b);
R.priceBands = bands.map(b => ({
  band: `${b}-${b + 10}元`,
  styles: bandProd.get(b)?.styles || 0, plan: bandProd.get(b)?.plan || 0,
  prodShare: bandProdTot ? ((bandProd.get(b)?.plan || 0) / bandProdTot * 100).toFixed(1) : '0.0',
  qty: bandSale.get(b)?.qty || 0, amt: Math.round(bandSale.get(b)?.amt || 0),
  qtyShare: bandSaleQty ? ((bandSale.get(b)?.qty || 0) / bandSaleQty * 100).toFixed(1) : '0.0'
}));

// ⑪ SKU总数与有效SKU（2025春，单款单色全周期净销>100件）
let skuTotal = 0;
const skuSales = new Map();
for (const g of springItems) {
  const colors = new Set();
  for (const s of Object.values(g.sku || {})) colors.add(normColor(s.color_info?.name_not_size || s.color?.name));
  skuTotal += colors.size;
}
for (const [k, v] of colorSales) {
  const [ref, color] = k.split('|');
  if (!s25Refs.has(ref)) continue;
  const cn = normColor(color);
  const nk = ref + '|' + cn;
  skuSales.set(nk, (skuSales.get(nk) || 0) + v);
}
const validSku = [...skuSales.entries()].filter(([, v]) => v > 100);
R.skuStats = { skuTotal, validSku: validSku.length, validList: validSku.sort((a, b) => b[1] - a[1]).slice(0, 30).map(([k, v]) => { const [ref, color] = k.split('|'); const g = s25ByRef.get(ref); return { ref, name: g?.name, color, qty: v, cat: g?.cate_info?.name }; }) };

// ⑫ 客户返单款TOP10（第2单起数量合计，按款）
const reorder = new Map();
for (const [k, docs] of custDocs) {
  const [ref] = k.split('|');
  if (!s25Refs.has(ref)) continue;
  const sorted = [...docs].sort((a, b) => a.day < b.day ? -1 : 1);
  for (let i = 1; i < sorted.length; i++) {
    reorder.set(ref, (reorder.get(ref) || 0) + sorted[i].qty);
  }
}
R.reorderTop10 = [...reorder.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).map(([ref, n]) => ({ ...decorate(ref), reorderQty: n }));

// ⑬ 退货款TOP10（限2025春，负数量合计）
const returnS25 = new Map();
for (const o of ods) for (const g of o.goods) {
  if (g.quantity < 0 && s25Refs.has(g.item_ref)) {
    returnS25.set(g.item_ref, (returnS25.get(g.item_ref) || 0) + g.quantity);
  }
}
R.returnTop10 = [...returnS25.entries()].map(([ref, n]) => ({ ...decorate(ref), retQty: n })).sort((a, b) => a.retQty - b.retQty).slice(0, 10);

// ---------- 输出 ----------
fs.writeFileSync(OUTJSON, JSON.stringify(R, null, 1));
console.log('=== 汇总 ===');
console.log(YEAR + '春款数:', springItems.length, '| SKU(单款单色)数:', R.skuStats.skuTotal, '| 有效SKU(>100件):', R.skuStats.validSku);
console.log('生产计划总量:', R.totals.totPlan, '| 净销量:', R.totals.totQty, '| 净销售额:', R.totals.totAmt);
console.log('\n畅销TOP5:', R.hot20.slice(0, 5).map(x => `${x.ref} ${x.name} ${x.qty}件`).join(' | '));
console.log('滞销TOP5:', R.cold20.slice(0, 5).map(x => `${x.ref} ${x.name} ${x.qty}件`).join(' | '));
console.log('\n售罄率最高TOP3:', R.selloutTop10.slice(0, 3).map(x => `${x.ref} ${x.rate}%`).join(' | '));
console.log('库存最大TOP3:', R.stockTop20.slice(0, 3).map(x => `${x.ref} ${x.stock}件`).join(' | '));
console.log('\n品类对比(前5):', R.catCompare.slice(0, 5).map(x => `${x.cat} 生产${x.prodShare}%/销售${x.qtyShare}%`).join(' | '));
console.log('\n颜色生产解析覆盖:', R.colorCompare.prodTotal, '件 | 颜色销售总量:', R.colorCompare.saleTotal);
console.log('价格段数:', R.priceBands.length);
console.log('返单TOP3:', R.reorderTop10.slice(0, 3).map(x => `${x.ref} ${x.reorderQty}件`).join(' | '));
console.log('退货TOP3:', R.returnTop10.slice(0, 3).map(x => `${x.ref} ${x.retQty}件`).join(' | '));
