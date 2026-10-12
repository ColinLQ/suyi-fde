#!/usr/bin/env node
// ingest.mjs — raw JSONL → 标准化快照（state/db.json 按日期分区）。只读本地文件，零网络。
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i++) {
  const t = argv[i].replace(/^--/, '');
  if (t.includes('=')) { const [k, v] = t.split('='); args[k] = v; }
  else if (argv[i + 1] && !argv[i + 1].startsWith('--')) { args[t] = argv[i + 1]; i++; }
  else args[t] = true;
}
const date = args.date || new Date().toISOString().slice(0, 10);
// 早晚快照分槽：slot=am(默认，08:30采集) / pm(18:30采集)。同日二次采集互不覆盖，db.days[date][slot]
const hour = new Date().getHours();
const slot = args.slot || (hour >= 14 ? 'pm' : 'am');
const rawDir = path.join(root, 'data', 'raw', date, slot);
const stateDir = path.join(root, 'state');
fs.mkdirSync(stateDir, { recursive: true });
const dbPath = path.join(stateDir, 'db.json');
const db = fs.existsSync(dbPath) ? JSON.parse(fs.readFileSync(dbPath, 'utf8')) : { days: {} };

const readJsonl = f => fs.existsSync(path.join(rawDir, f)) ? fs.readFileSync(path.join(rawDir, f), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : null;
const readJson = f => fs.existsSync(path.join(rawDir, f)) ? JSON.parse(fs.readFileSync(path.join(rawDir, f), 'utf8')) : null;

const yHeader = readJson('yizhe_header.json');
const yWarn = readJson('yizhe_warn.json');
const yFollow = readJsonl('yizhe_follow_orders.jsonl') || [];
const yFinance = readJson('yizhe_finance_sum.json');
const yTemplates = readJsonl('yizhe_template_list.jsonl') || [];
const dConsole = readJson('duoke_console_summary.json');
const dOrders = readJsonl('duoke_orders.jsonl') || [];
const dPayments = readJsonl('duoke_payments.jsonl') || [];

// —— snapshot层端点（早间批次不采）回落：当前槽 → 当日另一槽 → 往前逐日最近快照（早间日报复用最近晚间快照，SKILL口径） ——
// 返回 {data, from}；from='当日' 或 '2026-09-27 pm' 式回溯标记，用于日报披露数据时效
function readWithFallback(f) {
  if (fs.existsSync(path.join(rawDir, f))) return { data: fs.existsSync(path.join(rawDir, f)) && f.endsWith('.jsonl') ? readJsonl(f) : readJson(f), from: null };
  // 当前槽没有 → 找 fallback 目录（只解析一次，缓存）
  if (!readWithFallback._dir) {
    let dir = null;
    const cand = [];
    // 当日另一槽
    const other = slot === 'am' ? 'pm' : 'am';
    cand.push([date, other]);
    // 往前30天逐日（pm优先——晚间全量快照更完整）
    const dt = new Date(date + 'T00:00:00');
    for (let i = 1; i <= 30 && !dir; i++) {
      const d = new Date(dt); d.setDate(d.getDate() - i);
      const ds = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      cand.push([ds, 'pm'], [ds, 'am']);
    }
    for (const [d, s] of cand) {
      if (fs.existsSync(path.join(root, 'data', 'raw', d, s, f))) { dir = `${d}/${s}`; break; }
    }
    readWithFallback._dir = dir || false;
  }
  if (!readWithFallback._dir) return { data: null, from: null };
  const p2 = path.join(root, 'data', 'raw', readWithFallback._dir, f);
  const data = f.endsWith('.jsonl')
    ? fs.readFileSync(p2, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse)
    : JSON.parse(fs.readFileSync(p2, 'utf8'));
  return { data, from: readWithFallback._dir };
}

const goodsFB = readWithFallback('duoke_goods.jsonl');
const trendFB = readWithFallback('duoke_sale_trend.json');
const dGoods = goodsFB.data || [];
const dTrend = trendFB.data;
const snapshotFrom = goodsFB.from; // null=当日现采；否则如 '2026-09-27/pm'（回溯源，日报披露用）
if (snapshotFrom) console.log(`[ingest] 快照回落：duoke_goods/sale_trend 来自 ${snapshotFrom}（${date}/${slot} 未采snapshot层——早间批次正常行为）`);
if (!yHeader || !dGoods.length) { console.error('缺少原始数据，请先执行采集'); process.exit(1); }

// —— 通用兜底落库：注册表其余端点的产物整体入 extra（禁止静默丢弃，铁律⑦）；解析失败记录错误不中断 ——
const KNOWN = ['yizhe_header.json', 'yizhe_warn.json', 'yizhe_follow_orders.jsonl', 'yizhe_finance_sum.json', 'yizhe_template_list.jsonl', 'duoke_console_summary.json', 'duoke_goods.jsonl', 'duoke_sale_trend.json', 'duoke_orders.jsonl', 'duoke_payments.jsonl', '_source_demo'];
const extra = {};
fs.readdirSync(rawDir).filter(f => !KNOWN.includes(f) && !f.startsWith('.')).forEach(f => {
  try {
    extra[f] = f.endsWith('.jsonl')
      ? fs.readFileSync(path.join(rawDir, f), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse)
      : JSON.parse(fs.readFileSync(path.join(rawDir, f), 'utf8'));
  } catch (e) { extra[f] = { _error: '解析失败：' + e.message }; }
});
const isDemo = fs.existsSync(path.join(rawDir, '_source_demo'));

// —— 多客商品SKU展开 + 30日动销关联 ——
const skuFlat = [];
dGoods.forEach(g => {
  Object.entries(g.sku || {}).forEach(([skuId, s]) => {
    const t = (dTrend?.goods?.[g.id]?.trend) || {};
    const last7 = Object.entries(t).sort((a, b) => b[0].localeCompare(a[0])).slice(0, 7).reduce((a, [, v]) => a + v, 0);
    const total30 = dTrend?.goods?.[g.id]?.total || 0;
    const stock = Number(s.warehouse_0 || 0);
    skuFlat.push({
      goods_id: g.id, item_ref: g.item_ref,
      goods_name: (g.name && String(g.name).trim()) || g.item_ref || `#${g.id}`, // 源数据name空串兜底（168款，2026-09-28）
      cate: g.cate_info?.name,
      sku_id: skuId, color: s.color?.name, size: s.size?.name,
      cost_price: Number(s.price_in), sale_price: Number(s.price_1),
      stock, onway: s.onway_stock_0 || 0, presell: s.pre_sell_stock_0 || 0,
      oversold: stock < 0 ? Math.abs(stock) : 0, // 超卖欠货件数（源系统真实状态：已接单未回货）
      sold_last7: last7, sold_30: total30
    });
  });
});

const day = {
  yizhe: {
    production: yHeader.data,
    warn: yWarn.data,
    finance: yFinance.data,
    follow_orders: yFollow,
    templates: yTemplates
  },
  duoke: {
    console: (({ err, ...rest }) => rest)(dConsole),
    skus: skuFlat,
    orders: dOrders,
    payments: dPayments
  },
  extra,
  meta: {
    date, captured_at: new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString(), // 本地时间（原toISOString为UTC，日报落款差8h，2026-09-28修复）
    source: isDemo ? 'demo' : 'real',
    source_desc: isDemo ? 'Demo模拟数据' : '直连API采集', // 原'浏览器采集'文案不准（2026-09-28直连化后）
    snapshot_from: snapshotFrom, // null=当日现采；'YYYY-MM-DD/pm'=库存快照回溯源（早间复用晚间快照时披露）
    goods_count: dGoods.length
  }
};
db.days[date] = db.days[date] || {};
db.days[date][slot] = day;
fs.writeFileSync(dbPath, JSON.stringify(db, null, 1));

// —— 水位记录 ——
const waterPath = path.join(stateDir, 'watermark.json');
fs.writeFileSync(waterPath, JSON.stringify({ last_success_date: date, updated_at: new Date().toISOString() }, null, 2));

// —— 数据质量披露（铁律⑦：异常显式化，禁止静默） ——
const oversoldRefs = [...new Set(skuFlat.filter(s => s.oversold > 0).map(s => s.item_ref))];
if (oversoldRefs.length) console.log(`[ingest] ⚠️ 超卖欠贷数据披露：${oversoldRefs.length} 款库存为负（已接单未回货，源系统真实状态，非采集错误）；累计缺口 ${skuFlat.reduce((a, s) => a + s.oversold, 0)} 件`);
const noNameRefs = dGoods.filter(g => !(g.name && String(g.name).trim())).length;
if (noNameRefs) console.log(`[ingest] ⚠️ 源数据空品名 ${noNameRefs} 款，已用款号兜底显示`);

console.log(`[ingest] ${date} 入库完成：SKU明细 ${skuFlat.length} 条；样板 ${yTemplates.length} 款；跟单 ${yFollow.length} 单`);
console.log(`[ingest] 销售汇总：${dOrders.length} 单（退货 ${dOrders.filter(o => Number(o.goods_quantity) < 0).length}）；流水 ${dPayments.length} 笔`);
console.log(`[ingest] 兜底落库 ${Object.keys(extra).length} 个扩展端点文件；数据来源=${isDemo ? 'demo' : 'real'}`);
