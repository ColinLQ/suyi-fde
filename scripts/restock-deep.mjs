#!/usr/bin/env node
// restock-deep.mjs — 补货深度分析（V1.3 2026-09-28）：补货预警 × 在产订单交叉净缺口 + 季节修正 + 订单地区分析。零网络（只读已采数据）。
// 方法论（与 SKILL.md「第2.5步」一致）：
//   ① 净缺口 = max(0, 建议补货量 − 该款在产订单计划量合计)；建议 ≤ 在产 → 只需催货
//   ② 季节修正：season 字段 × 动销趋势（近7日 vs 前23日）分三类——
//      秋季上行（ratio≥1.5，建议量上调30-50%，脚本给出区间）/ 档口预占（近7日0销量+负库存，先核实再补）/ 冬季慢热（前23日有量+近7日0，缓）
//   ③ 地区分布：duoke_orders_30d.jsonl 三级地域解析（province字段→address文本→客户名前缀，识别率约80%）+ 气候大区 + 周度趋势
// 依赖：alerts-<date>.json（第2步 alert-rules 产物）、state/db.json、duoke_goods.jsonl、duoke_sale_trend.json
//      可选：duoke_orders_30d.jsonl（缺失时地区板块跳过并提示先跑 scripts/fetch-orders-region.mjs --days 30）
// 用法：node scripts/restock-deep.mjs [--date YYYY-MM-DD]
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const argv = process.argv.slice(2);
const argDate = argv.includes('--date') ? argv[argv.indexOf('--date') + 1] : null;

const db = JSON.parse(fs.readFileSync(path.join(dataHome, 'state', 'db.json'), 'utf8'));
const dates = Object.keys(db.days).sort();
const date = argDate || dates[dates.length - 1];
const slots = db.days[date] || {};
const day = slots.am || slots.pm;
if (!day) { console.error(`[deep] 无 ${date} 数据`); process.exit(1); }
const slot = slots.am ? 'am' : 'pm';

const alerts = JSON.parse(fs.readFileSync(path.join(dataHome, 'out', `alerts-${date}.json`), 'utf8'));
const ra = alerts.restock_alerts || [];
if (!ra.length) { console.error('[deep] 无补货预警（先跑 alert-rules.mjs）'); process.exit(1); }

// —— 原始文件读取（当日槽 → 另一槽回落） ——
const rawBase = path.join(dataHome, 'data', 'raw', date);
function readRaw(file) {
  for (const s of [slot, slot === 'am' ? 'pm' : 'am']) {
    const p = path.join(rawBase, s, file);
    if (fs.existsSync(p)) {
      return file.endsWith('.jsonl')
        ? fs.readFileSync(p, 'utf8').trim().split('\n').filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean)
        : JSON.parse(fs.readFileSync(p, 'utf8'));
    }
  }
  return null;
}
const dGoods = readRaw('duoke_goods.jsonl') || [];
const dTrend = readRaw('duoke_sale_trend.json');
const dOrders30 = readRaw('duoke_orders_30d.jsonl');

// —— 季节/趋势 ——
const seasonByRef = {}; const gid2ref = {};
for (const g of dGoods) {
  seasonByRef[g.item_ref] = g.season?.name || '?';
  gid2ref[String(g.id)] = g.item_ref;
}
const trendByRef = {};
for (const [gid, td] of Object.entries(dTrend?.goods || {})) {
  const ref = gid2ref[gid]; if (!ref) continue;
  const days = Object.entries(td.trend || {}).sort((a, b) => a[0].localeCompare(b[0]));
  if (!days.length) continue;
  const last7 = days.slice(-7); const prev23 = days.slice(0, -7).slice(-23);
  const avg7 = last7.reduce((a, [, v]) => a + v, 0) / 7;
  const avg23 = prev23.length ? prev23.reduce((a, [, v]) => a + v, 0) / prev23.length : 0;
  trendByRef[ref] = { avg7, avg23, ratio: avg23 >= 0.1 ? avg7 / avg23 : (avg7 > 0 ? Infinity : 0) };
}

// —— 在产订单（extra 或 yizhe 层；按款汇总多订单） ——
const prodRows = day.extra?.['yizhe_production_list.jsonl'] || day.yizhe?.production_list || [];
const prods = {};
for (const p of prodRows) {
  const g = prods[p.template_no] = prods[p.template_no] || { plan: 0, out: 0 };
  g.plan += Number(p.plan_total_num) || 0;
  const so = p.stock_out_num;
  g.out += (typeof so === 'object' && so ? Number(so.value) : Number(so)) || 0;
}
const steps = {};
for (const o of day.yizhe?.follow_orders || []) if (o.current_step) steps[o.template_no] = o.current_step;

// —— 逐款深度分析 ——
const RISING = 1.5;
const rows = ra.map(a => {
  const ref = a.item_ref;
  const p = prods[ref] || { plan: 0, out: 0 };
  const suggest = a.suggest_qty || 0;
  const net = Math.max(0, suggest - p.plan);
  const season = seasonByRef[ref] || '?';
  const t = trendByRef[ref];
  let trendTag = '无数据', ratio = null;
  if (t) {
    ratio = t.ratio;
    if (!isFinite(ratio) && t.avg7 > 0) trendTag = '新起';
    else if (t.avg7 === 0 && t.avg23 > 0) trendTag = '停滞';
    else if (ratio >= RISING) trendTag = `上行x${ratio.toFixed(1)}`;
    else if (ratio <= 0.5) trendTag = '回落';
    else trendTag = '平';
  }
  // 动作分类
  let action, adjNet = null;
  const oversold = a.level === '⛔超卖';
  if (net <= 0 && suggest > 0) action = '催货（在产已覆盖）';
  else if (oversold && t && t.avg23 === 0) action = `核实档口（预占存疑，净补${net}先挂起）`;
  else if (oversold && t && t.avg7 === 0) action = '缓（入冬未启动）';
  else if (season === '冬季' && t && t.avg7 === 0) action = '缓（入冬未启动）';
  else if (season === '秋季' && ratio !== null && (ratio >= RISING || !isFinite(ratio))) {
    adjNet = [net, Math.ceil(net * 1.5)];
    action = `追加下单（上行期建议 ${adjNet[0]}~${adjNet[1]}）`;
  } else action = '追加下单';
  return { ...a, season, ratio: ratio && isFinite(ratio) ? Math.round(ratio * 10) / 10 : (ratio === Infinity ? '∞' : null), trend: trendTag, inprod: p.plan, inprod_out: p.out, net, action, adj_low: adjNet?.[0], adj_high: adjNet?.[1], step: steps[ref] || '' };
});

// —— 地区分析（可选） ——
const PROV = ['广东','浙江','江苏','福建','湖南','湖北','四川','贵州','云南','广西','江西','安徽','河南','山东','山西','陕西','河北','辽宁','吉林','黑龙江','甘肃','青海','新疆','西藏','宁夏','海南','内蒙古','北京','上海','天津','重庆','香港','澳门','台湾'];
const CITY2PROV = {'深圳':'广东','东莞':'广东','佛山':'广东','中山':'广东','珠海':'广东','惠州':'广东','汕头':'广东','湛江':'广东','虎门':'广东','普宁':'广东','潮汕':'广东','海珠':'广东','天河':'广东','越秀':'广东','荔湾':'广东','番禺':'广东','白云':'广东','花都':'广东','增城':'广东','南沙':'广东','义乌':'浙江','温州':'浙江','宁波':'浙江','杭州':'浙江','嘉兴':'浙江','金华':'浙江','绍兴':'浙江','台州':'浙江','厦门':'福建','福州':'福建','泉州':'福建','漳州':'福建','莆田':'福建','石狮':'福建','郑州':'河南','洛阳':'河南','武汉':'湖北','宜昌':'湖北','襄阳':'湖北','长沙':'湖南','株洲':'湖南','衡阳':'湖南','常德':'湖南','成都':'四川','绵阳':'四川','宜宾':'四川','南充':'四川','贵阳':'贵州','遵义':'贵州','昆明':'云南','大理':'云南','丽江':'云南','曲靖':'云南','南宁':'广西','柳州':'广西','桂林':'广西','玉林':'广西','南昌':'江西','赣州':'江西','九江':'江西','上饶':'江西','合肥':'安徽','芜湖':'安徽','蚌埠':'安徽','阜阳':'安徽','安庆':'安徽','青岛':'山东','济南':'山东','烟台':'山东','潍坊':'山东','临沂':'山东','济宁':'山东','威海':'山东','西安':'陕西','咸阳':'陕西','宝鸡':'陕西','太原':'山西','临汾':'山西','运城':'山西','石家庄':'河北','唐山':'河北','保定':'河北','沧州':'河北','邯郸':'河北','沈阳':'辽宁','大连':'辽宁','鞍山':'辽宁','锦州':'辽宁','长春':'吉林','哈尔滨':'黑龙江','大庆':'黑龙江','兰州':'甘肃','乌鲁木齐':'新疆','库尔勒':'新疆','伊犁':'新疆','西宁':'青海','银川':'宁夏','拉萨':'西藏','海口':'海南','三亚':'海南'};
const CLIMATE = {'广东':'华南','福建':'华南','海南':'华南','广西':'华南','香港':'华南','澳门':'华南','台湾':'华南','浙江':'华东','江苏':'华东','上海':'华东','安徽':'华东','江西':'华东','湖南':'华中','湖北':'华中','河南':'华中','云南':'西南','贵州':'西南','四川':'西南','重庆':'西南','西藏':'西南','山东':'华北','河北':'华北','北京':'华北','天津':'华北','山西':'华北','内蒙古':'华北','辽宁':'东北','吉林':'东北','黑龙江':'东北','陕西':'西北','甘肃':'西北','新疆':'西北','青海':'西北','宁夏':'西北'};
const OVERSEAS = /马来西亚|新加坡|迪拜|越南|泰国|Mohammed|Dubai|Russia|俄/i;
function parseRegion(o) {
  const ai = o.client_address_info || {};
  for (const p of PROV) if (ai.province && ai.province.includes(p)) return p;
  const addr = String(ai.address || '');
  for (const p of PROV) if (addr.includes(p)) return p;
  for (const [c, pv] of Object.entries(CITY2PROV)) if (addr.includes(c)) return pv;
  const name = ai.client_name || o.customer_name || '';
  if (OVERSEAS.test(name)) return '海外';
  for (const p of PROV) if (name.startsWith(p)) return p;
  for (const [c, pv] of Object.entries(CITY2PROV)) if (name.startsWith(c)) return pv;
  return null;
}

let regionBlock = null;
if (dOrders30 && dOrders30.length) {
  const provCnt = {}; const cliCnt = {}; const wkCli = {}; let unknown = 0, totalQty = 0;
  const dayMs = 86400e3; const today = new Date(date + 'T00:00:00').getTime();
  for (const o of dOrders30) {
    const r = parseRegion(o);
    if (!r) { unknown++; continue; }
    provCnt[r] = (provCnt[r] || 0) + 1;
    const cli = CLIMATE[r] || '海外';
    cliCnt[cli] = (cliCnt[cli] || 0) + 1;
    const ctime = Number(o.ctime) * 1000;
    const w = ctime >= today - 7 * dayMs ? 'W4' : ctime >= today - 14 * dayMs ? 'W3' : ctime >= today - 21 * dayMs ? 'W2' : 'W1';
    (wkCli[w] = wkCli[w] || {})[cli] = (wkCli[w][cli] || 0) + 1;
    totalQty += Number(o.goods_quantity) || 0;
  }
  regionBlock = { orders: dOrders30.length, unknown, provCnt, cliCnt, wkCli, totalQty };
} else {
  console.log('[deep] ⚠️ 缺 duoke_orders_30d.jsonl，地区板块跳过（可跑 node scripts/fetch-orders-region.mjs --days 30 后重跑）');
}

// —— 落盘 JSON ——
const LV = { '⛔超卖': 0, '🔴紧急': 1, '🟡关注': 2 };
rows.sort((a, b) => (LV[a.level] - LV[b.level]) || (b.net - a.net));
const out = {
  date, generated_at: new Date().toISOString(),
  method: '净缺口=建议补货量−在产订单计划量；季节修正=season×动销趋势；地区=province/address/客户名前缀三级解析',
  rows, region: regionBlock,
  summary: {
    need_new_order: rows.filter(r => r.action.startsWith('追加')).length,
    chase_only: rows.filter(r => r.action.startsWith('催货')).length,
    verify_stall: rows.filter(r => r.action.startsWith('核实')).length,
    hold: rows.filter(r => r.action.startsWith('缓')).length,
    net_total: rows.reduce((a, r) => a + r.net, 0),
  },
};
fs.writeFileSync(path.join(dataHome, 'out', `restock-deep-${date}.json`), JSON.stringify(out, null, 1));

// —— Markdown 报告 ——
const L = [];
L.push(`# 补货深度分析 ${date}`, '');
L.push(`口径：净缺口 = 建议补货量 − 在产订单计划量；库存口径为采集时点快照。`, '');
L.push(`## 汇总：需追加下单 ${out.summary.need_new_order} 款（净缺口合计 ${out.summary.net_total} 件）｜催货 ${out.summary.chase_only} 款｜待核实 ${out.summary.verify_stall} 款｜缓 ${out.summary.hold} 款`, '');
L.push('## 明细（按级别/净缺口排序）', '');
L.push('| 级别 | 款号 | 品名 | 季节 | 库存 | 日均 | 趋势 | 建议 | 在产(已出) | 净补 | 动作 | 工序 |');
L.push('|---|---|---|---|---|---|---|---|---|---|---|---|');
for (const r of rows) {
  L.push(`| ${r.level} | ${r.item_ref} | ${r.name} | ${r.season} | ${r.stock} | ${r.daily_avg} | ${r.trend}${r.ratio && r.ratio !== '∞' && r.ratio !== null ? `(x${r.ratio})` : ''} | ${r.suggest_qty} | ${r.inprod}(${r.inprod_out}) | ${r.net} | ${r.action} | ${r.step} |`);
}
if (regionBlock) {
  const { cliCnt, wkCli, provCnt, unknown, orders } = regionBlock;
  const known = orders - unknown;
  L.push('', '## 订单地区分布（近30日）', '');
  L.push(`识别 ${known}/${orders} 单（${Math.round(known * 100 / orders)}%）。气候大区：` + Object.entries(cliCnt).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}单(${Math.round(v * 100 / known)}%)`).join('，'));
  L.push('', '| 周 | 华南 | 华东 | 华中 | 西南 | 华北 | 东北 | 西北 | 海外 |');
  L.push('|---|---|---|---|---|---|---|---|---|');
  for (const w of ['W1', 'W2', 'W3', 'W4']) {
    const c = wkCli[w] || {};
    L.push(`| ${w} | ${c['华南'] || 0} | ${c['华东'] || 0} | ${c['华中'] || 0} | ${c['西南'] || 0} | ${c['华北'] || 0} | ${c['东北'] || 0} | ${c['西北'] || 0} | ${c['海外'] || 0} |`);
  }
  const topProv = Object.entries(provCnt).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([k, v]) => `${k}${v}`).join('、');
  L.push('', `省份Top10：${topProv}`, '');
  L.push('解读要点：华南占比过半 → 秋款生命周期长（可穿至11月）、按上行系数上调；冬款看华南档口上冬装节奏（约10月中），不必赌北方降温（北方订单占比通常仅约10%）。');
}
L.push('', '---', '方法：净缺口=建议−在产；季节三分类（秋季上行/档口预占/冬季慢热）详见 SKILL.md 第2.5步。');
fs.writeFileSync(path.join(dataHome, 'out', `补货深度分析-${date}.md`), L.join('\n'));

console.log(`[deep] ${date}：${rows.length} 款 → out/restock-deep-${date}.json + out/补货深度分析-${date}.md`);
console.log(`[deep] 追加 ${out.summary.need_new_order} 款/净缺口 ${out.summary.net_total} 件；催货 ${out.summary.chase_only}；核实 ${out.summary.verify_stall}；缓 ${out.summary.hold}`);
if (regionBlock) console.log(`[deep] 地区：识别 ${regionBlock.orders - regionBlock.unknown}/${regionBlock.orders} 单，华南 ${regionBlock.cliCnt['华南'] || 0} 单`);
