#!/usr/bin/env node
// stock-diff.mjs — 衣者(成品库存) × 多客(商品SKU库存) 双系统库存差异比对。只读本地文件，零网络。
// 用法：node scripts/stock-diff.mjs [--from 2026-09-28] [--to 2026-10-09] [--top N]
// 数据源：data/raw/<日期>/<槽>/{yizhe_stock_list.jsonl, duoke_goods.jsonl, duoke_sale_trend.json}
// 口径：
//   衣者库存 = 成品库存接口 total_num（款级，only_has_stock=1，只返回有库存款）
//   多客库存 = 商品SKU warehouse_0 合计（可为负=超卖欠货），另计 onway_stock_0(在途)/pre_sell_stock_0(预售占用)
//   款级匹配：款号完全一致优先 → 回落 state/mapping.json pairs（含人工确认对）
// 产出：out/库存差异-<from>_<to>.md 与 .json
import fs from 'node:fs';
import crypto from 'node:crypto';
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
const TOP = Number(args.top || 20);
const readJsonl = f => fs.existsSync(f) ? fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : null;
const readJson = f => fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')) : null;

// —— 枚举所有含库存快照的日期/槽位 ——
const rawRoot = path.join(root, 'data', 'raw');
const snaps = [];
for (const d of fs.readdirSync(rawRoot).filter(x => /^\d{4}-\d{2}-\d{2}$/.test(x)).sort()) {
  for (const s of fs.readdirSync(path.join(rawRoot, d)).sort()) {
    const dir = path.join(rawRoot, d, s);
    const yz = path.join(dir, 'yizhe_stock_list.jsonl');
    const dk = path.join(dir, 'duoke_goods.jsonl');
    if (fs.existsSync(yz) || fs.existsSync(dk)) {
      snaps.push({ date: d, slot: s, yz: fs.existsSync(yz) ? yz : null, dk: fs.existsSync(dk) ? dk : null });
    }
  }
}
if (!snaps.length) { console.error('[stock-diff] 未找到任何库存快照，请先采集 yizhe_stock_list / duoke_goods'); process.exit(1); }
const from = args.from || snaps[0].date;
const to = args.to || snaps[snaps.length - 1].date;
const pick = want => snaps.filter(x => x.date === want).sort((a, b) => (b.yz ? 1 : 0) - (a.yz ? 1 : 0))[0];
const A = pick(from), B = pick(to);
if (!A || !B) { console.error(`[stock-diff] 缺少 ${from} 或 ${to} 的快照`); process.exit(1); }

const mapping = JSON.parse(fs.readFileSync(path.join(root, 'state', 'mapping.json'), 'utf8'));
const tpl2ref = Object.fromEntries(mapping.pairs.map(p => [p.template_no, p.item_ref]));

// —— 多客：按款聚合 SKU 库存 ——
function dkAgg(file, trendFile) {
  const goods = readJsonl(file) || [];
  const trend = trendFile && fs.existsSync(trendFile) ? readJson(trendFile) : null;
  const m = new Map();
  for (const g of goods) {
    const ref = g.item_ref || `#${g.id}`;
    let stock = 0, onway = 0, presell = 0, neg = 0, skuN = 0;
    const skuArr = Array.isArray(g.sku) ? g.sku : Object.entries(g.sku || {});
    for (const [, s] of skuArr) {
      const w = Number(s.warehouse_0 || 0);
      stock += w; if (w < 0) neg += -w;
      onway += Number(s.onway_stock_0 || 0);
      presell += Number(s.pre_sell_stock_0 || 0);
      skuN++;
    }
    const t = trend?.goods?.[g.id];
    const trend30 = Object.values(t?.trend || {}).reduce((a, v) => a + Number(v || 0), 0);
    m.set(ref, {
      ref, name: (g.name && String(g.name).trim()) || '', cate: g.cate_info?.name || '',
      season: g.season?.name || '', year: g.year?.name || '', wave: g.wave?.name || '',
      stock, onway, presell, oversold: neg, skuN,
      sold30: t?.total ?? trend30,
      goods_id: g.id, disable: String(g.disable ?? 0),
    });
  }
  return m;
}
// —— 衣者：款级成品库存 ——
function yzAgg(file, tplFile) {
  const rows = readJsonl(file) || [];
  const tplName = new Map(), tplCat = new Map(), tplBand = new Map();
  if (tplFile && fs.existsSync(tplFile)) for (const t of readJsonl(tplFile)) {
    tplName.set(t.template_no, t.template_name); tplCat.set(t.template_no, t.cat_name); tplBand.set(t.template_no, t.band_name);
  }
  const m = new Map();
  for (const r of rows) {
    m.set(r.template_no, {
      no: r.template_no, name: (r.template_name && String(r.template_name).trim()) || tplName.get(r.template_no) || '',
      num: Number(r.total_num || 0), created_at: r.created_at, band: r.band_name || tplBand.get(r.template_no) || '',
      design: r.design_user || '',
    });
  }
  return m;
}
const trendOf = s => s.dk ? s.dk.replace('duoke_goods.jsonl', 'duoke_sale_trend.json') : null;
const tplOf = s => s.yz ? s.yz.replace('yizhe_stock_list.jsonl', 'yizhe_template_list.jsonl') : null;

const dkA = A.dk ? dkAgg(A.dk, trendOf(A)) : new Map();
const dkB = B.dk ? dkAgg(B.dk, trendOf(B)) : new Map();
const yzA = A.yz ? yzAgg(A.yz, tplOf(A)) : new Map();
const yzB = B.yz ? yzAgg(B.yz, tplOf(B)) : new Map();

const sum = (m, f) => [...m.values()].reduce((a, v) => a + f(v), 0);

// —— 款级比对（以 to 快照为准）——
const dkRefs = new Set(dkB.keys());
const rows = [];
const usedDk = new Set();
for (const [no, y] of yzB) {
  // 衣者款号常带后缀（客户名/套装/工厂标记，如 'LC263789—河南某客户'、'WT261397（套装）'），规范化后再比对
  const base = no.split(/[-—(（/]/)[0].trim();
  let ref = dkRefs.has(no) ? no : (dkRefs.has(base) ? base : (dkRefs.has(tpl2ref[no]) ? tpl2ref[no] : null));
  const matched = !!ref;
  if (ref) usedDk.add(ref);
  const d = ref ? dkB.get(ref) : null;
  rows.push({
    yz_no: no, dk_ref: ref || '', matched,
    name: y.name || d?.name || '', cate: d?.cate || '', season: d?.season || '', band: y.band || '',
    yz: y.num,
    dk: d ? d.stock : null,
    dk_onway: d ? d.onway : null, dk_presell: d ? d.presell : null, dk_oversold: d ? d.oversold : null,
    sold30: d ? d.sold30 : null,
    diff: d ? y.num - d.stock : null,
    // 期初（from）两侧
    yz0: yzA.get(no)?.num ?? null, dk0: ref && dkA.has(ref) ? dkA.get(ref).stock : null,
  });
}
// 多客有、衣者无（衣者成品库存列表不返回零库存款）
for (const [ref, d] of dkB) {
  if (usedDk.has(ref)) continue;
  const yzNum = yzB.get(ref)?.num ?? 0; // 正常不会命中
  rows.push({
    yz_no: '', dk_ref: ref, matched: true,
    name: d.name, cate: d.cate, season: d.season, band: '',
    yz: yzNum, dk: d.stock, dk_onway: d.onway, dk_presell: d.presell, dk_oversold: d.oversold,
    sold30: d.sold30, diff: yzNum - d.stock,
    yz0: yzA.get(ref)?.num ?? null, dk0: dkA.has(ref) ? dkA.get(ref).stock : null,
  });
}

const M = rows.filter(r => r.matched && r.dk !== null);
const unmatched = rows.filter(r => !r.matched);
const both = M.filter(r => r.yz > 0 && r.dk > 0);
const yzOnly = M.filter(r => r.yz > 0 && r.dk === 0);
const dkOnly = M.filter(r => r.yz === 0 && r.dk > 0);
const oversold = M.filter(r => r.dk < 0);
const equal = M.filter(r => r.yz > 0 && r.yz === r.dk);
const absDiff = M.reduce((a, r) => a + Math.abs(r.diff), 0);

const tot = {
  from, to,
  yz_from: sum(yzA, v => v.num), yz_to: sum(yzB, v => v.num),
  dk_from: sum(dkA, v => v.stock), dk_to: sum(dkB, v => v.stock),
  yz_cnt_from: yzA.size, yz_cnt_to: yzB.size, dk_cnt_from: dkA.size, dk_cnt_to: dkB.size,
  dk_oversold_to: sum(dkB, v => v.oversold), dk_onway_to: sum(dkB, v => v.onway), dk_presell_to: sum(dkB, v => v.presell),
  matched_cnt: M.length, unmatched_cnt: unmatched.length,
  equal_cnt: equal.length, both_cnt: both.length, yz_only_cnt: yzOnly.length, dk_only_cnt: dkOnly.length,
  oversold_cnt: oversold.length, abs_diff: absDiff,
  net_diff_to: sum(yzB, v => v.num) - sum(dkB, v => v.stock),
};

// 衣者在途/待入库（补货缺口视角）
const instockFile = B.yz ? B.yz.replace('yizhe_stock_list.jsonl','yizhe_instock_list.jsonl') : null;
let instock = null;
if (instockFile && fs.existsSync(instockFile)) {
  const rows = readJsonl(instockFile) || [];
  let waitOut = 0, doneIn = 0, cnt = 0;
  for (const r of rows) { if (/待入库/.test(r.status_desc || '')) { waitOut += Number(r.stockout_num || 0); cnt++; } doneIn += Number(r.instock_num || 0); }
  instock = { wait_orders: cnt, wait_pieces: waitOut, instocked_pieces: doneIn };
}
const topGapYz = M.filter(r => r.diff > 0).sort((a, b) => b.diff - a.diff).slice(0, TOP);   // 衣者多于多客
const topGapDk = M.filter(r => r.diff < 0).sort((a, b) => a.diff - b.diff).slice(0, TOP);   // 多客多于衣者
// 期间变化：两侧都有期初数据的款
const moved = M.filter(r => r.yz0 !== null && r.dk0 !== null);
const drift = moved.map(r => ({ ...r, yz_delta: r.yz - r.yz0, dk_delta: r.dk - r.dk0, gap_delta: r.diff - (r.yz0 - r.dk0) }))
  .sort((a, b) => Math.abs(b.gap_delta) - Math.abs(a.gap_delta)).slice(0, TOP);
const deadStock = M.filter(r => r.dk > 0 && (r.sold30 || 0) === 0).sort((a, b) => b.dk - a.dk).slice(0, TOP);

// —— 口径体检：衣者 total_num 到底是"当前库存"还是"累计入库" ——
const same = [...yzB.keys()].filter(k => yzA.has(k));
const movers = { up: 0, down: 0, flat: 0 };
for (const k of same) {
  const d = yzB.get(k).num - yzA.get(k).num;
  if (d > 0) movers.up++; else if (d < 0) movers.down++; else movers.flat++;
}
const newCnt = [...yzB.keys()].filter(k => !yzA.has(k)).length;
const goneCnt = [...yzA.keys()].filter(k => !yzB.has(k)).length;
const corr = (() => {
  const p = M.filter(r => r.yz != null && r.dk != null);
  const a = p.map(r => r.yz), b = p.map(r => r.dk), n = p.length;
  if (n < 3) return null;
  const sa = a.reduce((x, y) => x + y, 0), sb = b.reduce((x, y) => x + y, 0);
  const sab = a.reduce((s, v, i) => s + v * b[i], 0), saa = a.reduce((s, v) => s + v * v, 0), sbb = b.reduce((s, v) => s + v * v, 0);
  return (n * sab - sa * sb) / Math.sqrt((n * saa - sa * sa) * (n * sbb - sb * sb));
})();
const dkSold30 = sum(dkB, v => v.sold30 || 0);
const caliber = {
  yz_moved_up: movers.up, yz_moved_down: movers.down, yz_moved_flat: movers.flat, yz_new: newCnt, yz_gone: goneCnt,
  corr_yz_dk: corr == null ? null : Math.round(corr * 1000) / 1000,
  dk_sold30_total: dkSold30,
  yz_months_of_sales: dkSold30 ? Math.round(sum(yzB, v => v.num) / dkSold30 * 10) / 10 : null,
};
// 判定：同款11天零变动 + 与多客在库近零相关 + 量级远超多月销量 → 倾向"累计入库"
caliber.verdict = (movers.down === 0 && movers.up <= same.length * 0.02 && (corr == null || Math.abs(corr) < 0.3))
  ? '累计入库口径（疑似）' : '当前库存口径';

// —— 多客侧时间序列（所有可用快照）——
const seenHash = new Map();
const dkSeries = snaps.filter(s => s.dk).map(s => {
  const h = crypto.createHash('md5').update(fs.readFileSync(s.dk)).digest('hex').slice(0, 8);
  const m = dkAgg(s.dk, trendOf(s));
  let stock = 0, neg = 0, pos = 0, onway = 0;
  for (const v of m.values()) { stock += v.stock; neg += v.oversold; onway += v.onway; if (v.stock > 0) pos++; }
  const dup = seenHash.get(h);
  if (!dup) seenHash.set(h, `${s.date}/${s.slot}`);
  return { date: s.date, slot: s.slot, hash: h, dup_of: dup || null, stock, goods: m.size, in_stock_cnt: pos, oversold: neg, onway };
});
// 多客期间增减 Top（首末快照）
const dkMovers = [];
if (dkA.size && dkB.size) {
  for (const [ref, b] of dkB) {
    const a = dkA.get(ref);
    if (!a) continue;
    dkMovers.push({ ref, name: b.name, season: b.season, a: a.stock, b: b.stock, delta: b.stock - a.stock, sold30: b.sold30 });
  }
}
const dkDown = dkMovers.filter(r => r.delta < 0).sort((a, b) => a.delta - b.delta).slice(0, TOP);
const dkUp = dkMovers.filter(r => r.delta > 0).sort((a, b) => b.delta - a.delta).slice(0, TOP);

const outDir = path.join(root, 'out'); fs.mkdirSync(outDir, { recursive: true });
const jsonPath = path.join(outDir, `库存差异-${from}_${to}.json`);
fs.writeFileSync(jsonPath, JSON.stringify({ summary: tot, caliber, dk_series: dkSeries, rows, top_gap_yizhe: topGapYz, top_gap_duoke: topGapDk, drift, dead_stock: deadStock, unmatched, dk_down: dkDown, dk_up: dkUp }, null, 1));

const n = x => (x == null ? '—' : Number(x).toLocaleString('zh-CN'));
const md = [];
md.push(`# 衣者 × 多客 库存差异比对（${from} → ${to}）`);
md.push('');
md.push(`> 生成时间：${new Date(Date.now() - new Date().getTimezoneOffset() * 6e4).toISOString().slice(0, 19).replace('T', ' ')}　数据源：直连API快照（衣者成品库存 / 多客商品SKU库存）`);
md.push('');
md.push('## 一、总量对比');
md.push('');
md.push('| 指标 | ' + from + ' | ' + to + ' | 变化 |');
md.push('|---|---:|---:|---:|');
md.push(`| 衣者成品库存件数 | ${n(tot.yz_from)} | ${n(tot.yz_to)} | ${(tot.yz_to - tot.yz_from) >= 0 ? '+' : ''}${n(tot.yz_to - tot.yz_from)} |`);
md.push(`| 衣者有库存款数 | ${n(tot.yz_cnt_from)} | ${n(tot.yz_cnt_to)} | ${tot.yz_cnt_to - tot.yz_cnt_from >= 0 ? '+' : ''}${tot.yz_cnt_to - tot.yz_cnt_from} |`);
md.push(`| 多客在库件数 | ${n(tot.dk_from)} | ${n(tot.dk_to)} | ${(tot.dk_to - tot.dk_from) >= 0 ? '+' : ''}${n(tot.dk_to - tot.dk_from)} |`);
md.push(`| 多客在售款数 | ${n(tot.dk_cnt_from)} | ${n(tot.dk_cnt_to)} | ${tot.dk_cnt_to - tot.dk_cnt_from >= 0 ? '+' : ''}${tot.dk_cnt_to - tot.dk_cnt_from} |`);
md.push(`| **两侧净差（衣者−多客）** | ${n(tot.yz_from - tot.dk_from)} | **${n(tot.net_diff_to)}** | ${(tot.net_diff_to - (tot.yz_from - tot.dk_from)) >= 0 ? '+' : ''}${n(tot.net_diff_to - (tot.yz_from - tot.dk_from))} |`);
md.push(`| 款级绝对差异合计 | — | ${n(tot.abs_diff)} | — |`);
md.push('');
md.push(`多客侧附加状态（${to}）：超卖欠货 ${n(tot.dk_oversold_to)} 件 / ${tot.oversold_cnt} 款；在途 ${n(tot.dk_onway_to)} 件；预售占用 ${n(tot.dk_presell_to)} 件。`);
if (instock) md.push(`衣者在途（${to}）：待入库 ${instock.wait_orders} 单 / ${n(instock.wait_pieces)} 件；已入库 ${n(instock.instocked_pieces)} 件。`);
md.push('');
md.push('## 二、口径体检（决定上面这张表怎么读）');
md.push('');
md.push('| 检查项 | 结果 | 含义 |');
md.push('|---|---|---|');
md.push(`| 衣者同款期间变动 | 增 ${caliber.yz_moved_up} / 减 ${caliber.yz_moved_down} / 持平 ${caliber.yz_moved_flat} | ${caliber.yz_moved_down === 0 ? '**零减少**——当前库存不可能11天不减，倾向累计值' : '有增有减，符合实时库存'} |`);
md.push(`| 衣者款数进出 | 新增 ${caliber.yz_new} / 消失 ${caliber.yz_gone} | 消失=库存归零 |`);
md.push(`| 衣者×多客 款级相关系数 | ${caliber.corr_yz_dk} | ${Math.abs(caliber.corr_yz_dk) < 0.3 ? '**近零相关**——两侧不是同一口径' : '同向，可比' } |`);
md.push(`| 衣者量级 ÷ 多客30日动销 | ${n(caliber.yz_months_of_sales)} 个月销量 | ${caliber.yz_months_of_sales > 12 ? '**远超合理库龄**' : '合理'} |`);
md.push('');
md.push(`**判定：衣者 \`total_num\` = ${caliber.verdict}。**`);
md.push('');
if (caliber.verdict.includes('累计')) {
  md.push('> ⚠️ 因此「衣者 67.9 万件 vs 多客 4.3 万件」**不是**真实库存落差，而是「累计入库量 vs 当前在库量」的口径错位，不能直接用于补货/清仓决策。');
  md.push('> 若要拿到衣者**当前**成品库存，需在衣者 /stock-list 页面确认列字段名（本次浏览器SPA未渲染，未能核实），或改用「累计入库 − 累计出货」推算（出货记录接口当前返回0条，待修端点）。');
  md.push('> 下述第三~五节的**款级差异**仍按同源快照给出，仅供交叉核对与人工排查，不代表真实缺货量。');
} else {
  md.push('> 两侧均为当前库存口径，差异可直接用于补货/调拨决策。');
}
md.push('');
md.push('## 三、多客侧真实库存动态（可比，多时点）');
md.push('');
md.push('| 快照 | 在库件数 | 有库存款数 | 在售款数 | 超卖欠货 | 在途 |');
md.push('|---|---:|---:|---:|---:|---:|');
for (const s of dkSeries) md.push(`| ${s.date} ${s.slot}${s.dup_of ? `（= ${s.dup_of} 副本）` : ''} | ${n(s.stock)} | ${n(s.in_stock_cnt)} | ${n(s.goods)} | ${n(s.oversold)} | ${n(s.onway)} |`);
md.push('');
md.push(`期间（${from}→${to}）多客在库净变化 **${(tot.dk_to - tot.dk_from) >= 0 ? '+' : ''}${n(tot.dk_to - tot.dk_from)} 件**；同期30日动销 ${n(caliber.dk_sold30_total)} 件。`);
md.push('');
md.push(`### 库存下降最多（Top${TOP}）`);
md.push('');
md.push('| 款号 | 款名 | 季节 | 期初 | 期末 | 变化 | 30日动销 |');
md.push('|---|---|---|---:|---:|---:|---:|');
for (const r of dkDown) md.push(`| ${r.ref} | ${r.name || '—'} | ${r.season || '—'} | ${n(r.a)} | ${n(r.b)} | ${n(r.delta)} | ${n(r.sold30)} |`);
md.push('');
md.push(`### 库存上升最多（Top${TOP}，回货/退货入库）`);
md.push('');
md.push('| 款号 | 款名 | 季节 | 期初 | 期末 | 变化 | 30日动销 |');
md.push('|---|---|---|---:|---:|---:|---:|');
for (const r of dkUp) md.push(`| ${r.ref} | ${r.name || '—'} | ${r.season || '—'} | ${n(r.a)} | ${n(r.b)} | +${n(r.delta)} | ${n(r.sold30)} |`);
md.push('');
md.push('## 四、差异结构（款级，同源快照比对）');
md.push('');
md.push('| 分层 | 款数 | 衣者件数 | 多客件数 | 净差 |');
md.push('|---|---:|---:|---:|---:|');
const layer = (label, arr) => `| ${label} | ${arr.length} | ${n(sum(new Map(arr.map(r => [r.yz_no || r.dk_ref, { num: r.yz }])), v => v.num))} | ${n(arr.reduce((a, r) => a + r.dk, 0))} | ${n(arr.reduce((a, r) => a + r.diff, 0))} |`;
md.push(layer('两侧都有库存', both));
md.push(layer('仅衣者有库存（多客0/下架）', yzOnly));
md.push(layer('仅多客有库存（衣者0）', dkOnly));
md.push(layer('多客负库存（超卖）', oversold));
md.push(`| 款数完全一致 | ${equal.length} | — | — | 0 |`);
md.push(`| 款号未匹配（需人工核对） | ${unmatched.length} | ${n(unmatched.reduce((a, r) => a + r.yz, 0))} | — | — |`);
md.push('');
md.push(`匹配率：${(M.length / rows.length * 100).toFixed(1)}%（${M.length}/${rows.length} 款可比对）。`);
md.push('');
md.push(`## 五、衣者库存 > 多客库存（Top${TOP}，未回货/未上架/未同步）`);
md.push('');
md.push('| 款号 | 款名 | 品类 | 季节 | 衣者 | 多客 | 差 | 多客在途 | 30日动销 |');
md.push('|---|---|---|---|---:|---:|---:|---:|---:|');
for (const r of topGapYz) md.push(`| ${r.yz_no} | ${r.name || '—'} | ${r.cate || '—'} | ${r.season || '—'} | ${n(r.yz)} | ${n(r.dk)} | +${n(r.diff)} | ${n(r.dk_onway)} | ${n(r.sold30)} |`);
md.push('');
md.push(`## 六、多客库存 > 衣者库存（Top${TOP}，多客有货衣者无成品库存）`);
md.push('');
md.push('| 款号 | 款名 | 品类 | 季节 | 衣者 | 多客 | 差 | 30日动销 | 说明 |');
md.push('|---|---|---|---|---:|---:|---:|---:|---|');
for (const r of topGapDk) md.push(`| ${r.dk_ref} | ${r.name || '—'} | ${r.cate || '—'} | ${r.season || '—'} | ${n(r.yz)} | ${n(r.dk)} | ${n(r.diff)} | ${n(r.sold30)} | ${r.yz === 0 ? '衣者成品库无此款' : '衣者已出货未减/多客未销' } |`);
md.push('');
md.push(`## 七、期间差异变化最大（Top${TOP}，款级缺口漂移）`);
md.push('');
md.push('| 款号 | 款名 | 衣者期初→期末 | 多客期初→期末 | 缺口变化 |');
md.push('|---|---|---:|---:|---:|');
for (const r of drift) md.push(`| ${r.yz_no || r.dk_ref} | ${r.name || '—'} | ${n(r.yz0)} → ${n(r.yz)} | ${n(r.dk0)} → ${n(r.dk)} | ${r.gap_delta >= 0 ? '+' : ''}${n(r.gap_delta)} |`);
md.push('');
md.push(`## 八、多客有库存但30日零动销（呆滞，Top${TOP}）`);
md.push('');
md.push('| 款号 | 款名 | 季节 | 多客库存 | 衣者库存 | 成本占用* |');
md.push('|---|---|---|---:|---:|---:|');
for (const r of deadStock) md.push(`| ${r.dk_ref || r.yz_no} | ${r.name || '—'} | ${r.season || '—'} | ${n(r.dk)} | ${n(r.yz)} | — |`);
md.push('');
md.push('> *成本占用需结合SKU成本价，见 restock-deep 输出。');
md.push('');
md.push('## 九、款号未匹配清单（需人工确认对应关系）');
md.push('');
md.push('| 衣者款号 | 款名 | 衣者库存 |');
md.push('|---|---|---:|');
for (const r of unmatched) md.push(`| ${r.yz_no} | ${r.name || '—'} | ${n(r.yz)} |`);
md.push('');
md.push('## 十、口径与盲区（必读）');
md.push('');
md.push(`- 衣者成品库存接口 \`only_has_stock=1\`，**只返回有库存款**（${to} 返回 ${tot.yz_cnt_to} 款 / UI显示total 1452 含零库存款），故「仅多客有库存」里包含衣者已出完货的款，属正常。`);
md.push(`- 多客库存为 SKU 级 \`warehouse_0\` 合计，**负数=超卖欠货**（源系统真实状态，已接单未回货），不参与"库存不足"判定而应视为在途缺口。`);
md.push(`- 本比对为**同日快照差**，两侧入出库存在时间差（衣者出货→多客入库、多客开单→衣者减库存），单日差异含在途/在单部分，需结合衣者 \`yizhe_instock_list\`（待入库）与多客 \`onway_stock_0\` 解读。`);
md.push(`- 可比对窗口受限于采集起点：库存快照最早为 ${snaps[0].date}，两系统**同日双快照**只有 ${from} 与 ${to}；中间日期仅多客快照（无衣者成品库存），无法做逐日差异曲线。`);
md.push(`- 款号匹配：款号完全一致 ${rows.filter(r => r.yz_no && r.yz_no === r.dk_ref).length} 款，经 mapping.json 补 ${rows.filter(r => r.yz_no && r.dk_ref && r.yz_no !== r.dk_ref).length} 款，未匹配 ${unmatched.length} 款。`);
md.push('');
const mdPath = path.join(outDir, `库存差异-${from}_${to}.md`);
fs.writeFileSync(mdPath, md.join('\n'));

console.log(`[stock-diff] ${from} → ${to}`);
console.log(`  衣者成品库存 ${tot.yz_from} → ${tot.yz_to} 件（${tot.yz_cnt_from}→${tot.yz_cnt_to} 款）`);
console.log(`  多客在库     ${tot.dk_from} → ${tot.dk_to} 件（${tot.dk_cnt_from}→${tot.dk_cnt_to} 款，超卖 ${tot.dk_oversold_to} 件）`);
console.log(`  净差(衣者−多客) ${tot.yz_from - tot.dk_from} → ${tot.net_diff_to}；款级绝对差异合计 ${tot.abs_diff} 件`);
console.log(`  分层：两侧都有 ${both.length}｜仅衣者 ${yzOnly.length}｜仅多客 ${dkOnly.length}｜超卖 ${oversold.length}｜完全一致 ${equal.length}｜未匹配 ${unmatched.length}`);
console.log(`  产出：${path.relative(process.cwd(), mdPath)} / ${path.relative(process.cwd(), jsonPath)}`);
