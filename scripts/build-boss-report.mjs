#!/usr/bin/env node
// 老板经营日报聚合脚本（PRD V1.0 MVP · build-boss-report）
// 数据源：state/db.json（汇总库）+ out/（预警/补货深度）+ data/raw/<日期>/（明细）
// 用法：node scripts/build-boss-report.mjs --date 2026-10-09
// 输出：out/老板日报-<日期>.md
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const argDate = (process.argv.find(a => a.startsWith('--date')) || '').split('=')[1]
  || process.argv[process.argv.indexOf('--date') + 1] || '2026-10-09';
const OUT = path.join(ROOT, 'out', `老板日报-${argDate}.md`);

// ---------- 工具 ----------
const j = (p) => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return null; } };
const jsonl = (p) => { try { return fs.readFileSync(p, 'utf8').split('\n').filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean); } catch { return []; } };
const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
const fmt = (n) => Math.round(n).toLocaleString('en-US');
const wan = (n) => Math.abs(n) >= 10000 ? `¥${(n / 10000).toFixed(1)}万` : `¥${fmt(n)}`;
const ts2d = (t) => new Date(num(t) * 1000).toISOString().slice(0, 10);
const daysBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 86400000);
const DATA_DATE = argDate;
const TODAY = new Date(DATA_DATE);

// ---------- 数据装载（缺项容错） ----------
const db = j(path.join(ROOT, 'state/db.json'));
const day = db?.days?.[DATA_DATE]?.am || null;
if (!day) { console.error(`[硬停] db.json 中无 ${DATA_DATE} 数据槽`); process.exit(1); }

const D = day.duoke || {}, Y = day.yizhe || {};
const orders = D.orders || [];          // 当日订单
const payments = D.payments || [];      // 当日流水
const skus = D.skus || [];              // SKU 级库存快照
const console_ = D.console || {};
const finance = Y.finance || {};
const production = Y.production || {};

const orders30 = jsonl(path.join(ROOT, `data/raw/${DATA_DATE}/am/duoke_orders_30d.jsonl`));
const prodList = jsonl(path.join(ROOT, `data/raw/${DATA_DATE}/am/yizhe_production_list.jsonl`))
  .concat(jsonl(path.join(ROOT, `data/raw/${DATA_DATE}/pm/yizhe_production_list.jsonl`)));
const goodsRaw = jsonl(path.join(ROOT, `data/raw/${DATA_DATE}/pm/duoke_goods.jsonl`));
const details = jsonl(path.join(ROOT, `data/raw/${DATA_DATE}/pm/duoke_order_details.jsonl`));
const alerts = j(path.join(ROOT, 'out', `alerts-${DATA_DATE}.json`)) || {};
const restock = j(path.join(ROOT, 'out', `restock-deep-${DATA_DATE}.json`)) || {};

// 商品档案索引：款号 → {season, ctime}
const goodsMap = new Map();
for (const g of goodsRaw) {
  const ref = (g.item_ref || '').split(/[-—(/（]/)[0];
  if (!goodsMap.has(ref)) goodsMap.set(ref, { season: g.season?.name || '?', ctime: num(g.ctime), name: g.name || '' });
}
// 款级成交均价（3年商品行）
const styleAgg = new Map(); // ref -> [金额, 件数]
for (const d of details) for (const g of (d.goods || [])) {
  const q = num(g.quantity), pr = num(g.price);
  if (q > 0) { const a = styleAgg.get(g.item_ref) || [0, 0]; a[0] += q * pr; a[1] += q; styleAgg.set(g.item_ref, a); }
}
const avgPrice = (ref) => { const a = styleAgg.get(ref); return a && a[1] > 0 ? a[0] / a[1] : null; };

// 款级库存聚合
const styleStock = new Map(); // ref -> {stock, capital, s30, s7, onway, presell, name, cate}
for (const s of skus) {
  const k = s.item_ref; if (!k) continue;
  const o = styleStock.get(k) || { stock: 0, capital: 0, s30: 0, s7: 0, onway: 0, presell: 0, name: s.goods_name || '', cate: s.cate || '' };
  const st = num(s.stock), c = num(s.cost_price);
  o.stock += st; o.capital += st * c; o.s30 += num(s.sold_30); o.s7 += num(s.sold_last7);
  o.onway += num(s.onway); o.presell += num(s.presell);
  styleStock.set(k, o);
}

const L = [];
const sec = (t) => L.push(`\n## ${t}\n`);
const note = (t) => L.push(`> ${t}\n`);

// 30 日订单共享统计（模块一/四/拍板区共用）
let net30 = 0, ret30 = 0;
const shop30 = new Map(), retShop = new Map(), seller30 = new Map(), custCnt = new Map();
for (const r of orders30) {
  const p = num(r.calc_price);
  if (p >= 0) {
    net30 += p;
    shop30.set(r.shop_name, (shop30.get(r.shop_name) || 0) + p);
    const s = r.seller_name;
    if (s && s !== '空') seller30.set(s, (seller30.get(s) || 0) + p);
    custCnt.set(r.client_id, (custCnt.get(r.client_id) || 0) + 1);
  } else {
    ret30 += p;
    retShop.set(r.shop_name, (retShop.get(r.shop_name) || 0) + p);
  }
}
const flagShops = [];       // 模块二填充，拍板区引用
let fragItems = [];         // 模块三填充，拍板区引用

// ========== 模块一：经营速览 ==========
{
  sec('一、今日速览');
  const sales = orders.filter(o => num(o.calc_price) > 0);
  const rets = orders.filter(o => num(o.calc_price) < 0);
  const netSales = orders.reduce((s, o) => s + num(o.calc_price), 0);
  const pieces = sales.reduce((s, o) => s + num(o.goods_quantity), 0);
  const netPay = payments.reduce((s, p) => s + num(p.price), 0);
  const gap = netPay - netSales;

  // 30日基准（统计已在顶部完成）
  const avg30 = net30 / 30;
  const rep = [...custCnt.values()].filter(n => n >= 2).length;

  L.push(`| 指标 | 今日 | 对比 30 日日均（${wan(avg30)}） |`);
  L.push(`|---|---|---|`);
  L.push(`| 净销售额 | ${wan(netSales)} | ${netSales >= avg30 ? '↑ 高于均值' : '↓ 低于均值 ' + ((netSales / avg30 * 100).toFixed(0) + '%')} |`);
  L.push(`| 销售件数 / 单数 | ${fmt(pieces)} 件 / ${sales.length} 单（退货 ${rets.length} 单 ${wan(-rets.reduce((s, o) => s + num(o.calc_price), 0))}） | — |`);
  L.push(`| 收款流水 | ${wan(netPay)} | — |`);
  L.push(`| 收款−销售差额 | ${wan(gap)}${gap > avg30 * 0.5 ? ' ← 大额回款流入，留意挂账客户核销' : ''} | — |`);
  L.push(`| 新增客户 | ${console_.today_new_client_amount ?? '—'} | — |`);
  L.push(`| 应付供应商待付款（衣者） | **${wan(num(finance.sum_wait_paid_price))}** | 资金调度关注项 |`);

  // 月度趋势（console.trade_trend 自带历史）
  const tt = console_.trade_trend || [];
  const last2 = tt.slice(-2);
  if (last2.length >= 2) {
    const [prev, cur] = last2;
    L.push(`\n**月度进度**：${cur.date} 月累计成交 ${wan(num(cur.transaction_money))}（上月全月 ${wan(num(prev.transaction_money))}，达上月 ${(num(cur.transaction_money) / num(prev.transaction_money) * 100).toFixed(0)}%）；月销售目标未设定（可在 boss-params 中配置）。`);
  }

  L.push(`\n**30 日客户与门店**：成交客户 ${custCnt.size} 家，其中复购（≥2 单）${rep} 家（${(rep / custCnt.size * 100).toFixed(0)}%）；门店净销排名：`);
  [...shop30.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).forEach(([k, v], i) => {
    const rr = retShop.get(k) || 0;
    const rate = v > 0 ? `｜退货率 ${(Math.abs(rr) / v * 100).toFixed(1)}%` : '';
    L.push(`${i + 1}. ${k}：${wan(v)}${rate}`);
  });
}

// ========== 模块二：漏水清单 ==========
{
  sec('二、漏水清单（按损失额排序）');

  // ① 超卖丢单
  const ra = alerts.restock_alerts || [];
  const oversold = ra.filter(a => num(a.stock) < 0).map(a => ({ ...a, avg: avgPrice(a.item_ref) }));
  let totalDailyLoss = 0;
  const lossRows = oversold.map(a => {
    const price = a.avg ?? (() => { // 款级均价缺失回退：全局客单价
      const n30 = orders30.filter(r => num(r.calc_price) > 0);
      return n30.reduce((s, r) => s + num(r.calc_price), 0) / Math.max(n30.length, 1);
    })();
    const daily = num(a.daily_avg) * price;
    totalDailyLoss += daily;
    return { ref: a.item_ref, name: a.name, stock: num(a.stock), dailyAvg: num(a.daily_avg), price, daily };
  }).sort((a, b) => b.daily - a.daily);
  const staleO = (alerts.stale_oversold || []).slice().sort((a, b) => b.gap - a.gap);
  L.push(`### ① 超卖丢单（当期 ${oversold.length} 款 + 老超卖 ${staleO.length} 款）`);
  L.push(`**每日正在漏：约 ${wan(totalDailyLoss)}**（= Σ 日均销 × 款级成交均价）。Top5：`);
  L.push(`| 款号 | 品名 | 库存 | 日均销 | 成交均价 | 日损失额 |`);
  L.push(`|---|---|---|---|---|---|`);
  lossRows.slice(0, 5).forEach(r => L.push(`| ${r.ref} | ${r.name} | ${r.stock} | ${r.dailyAvg} | ¥${r.price.toFixed(0)} | **${wan(r.daily)}** |`));
  if (staleO.length) {
    L.push(`\n老超卖结构性缺货（gap≤5 优先处理）：共 ${staleO.filter(x => x.gap <= 5).length} 款；最大缺口 Top3：${staleO.slice(0, 3).map(x => `${x.item_ref}(缺${x.gap})`).join('、')}。`);
  }

  // ② 滞销占资
  const stale = [];
  for (const [ref, o] of styleStock) {
    if (o.stock >= 50 && o.s30 === 0 && o.presell === 0) {
      const gd = goodsMap.get(ref) || {};
      const age = gd.ctime ? daysBetween(ts2d(gd.ctime * 1000).replace(/-/g, '/'), DATA_DATE.replace(/-/g, '/')) : null;
      stale.push({ ref, ...o, season: gd.season || '?', age });
    }
  }
  stale.sort((a, b) => b.capital - a.capital);
  const staleCap = stale.reduce((s, x) => s + x.capital, 0);
  const staleOnway = stale.filter(x => x.onway > 0);
  L.push(`\n### ② 滞销占资（库存≥50件 且 30日零销 且 无预售）`);
  L.push(`共 **${stale.length} 款，占用资金 ${wan(staleCap)}**（成本价口径）；其中 **${staleOnway.length} 款仍在途补货**——最危险，建议立即核对是否叫停。`);
  L.push(`| 款号 | 品名 | 季节 | 库存 | 占用资金 | 在途 |`);
  L.push(`|---|---|---|---|---|---|`);
  stale.slice(0, 5).forEach(x => L.push(`| ${x.ref} | ${x.name} | ${x.season} | ${fmt(x.stock)} | ${wan(x.capital)} | ${x.onway > 0 ? `⚠${x.onway}` : '—'} |`));

  // ③ 退货损耗
  let retRateSum = 0, retN = 0;
  for (const [k, v] of shop30) {
    const rr = Math.abs(retShop.get(k) || 0) / v;
    retRateSum += rr; retN++;
  }
  const meanRR = retRateSum / Math.max(retN, 1);
  for (const [k, v] of shop30) {
    const rr = Math.abs(retShop.get(k) || 0) / v;
    if (rr > meanRR * 2 && v > 10000) flagShops.push([k, rr]);
  }
  L.push(`\n### ③ 退货损耗（30 日）`);
  L.push(`退货金额 ${wan(Math.abs(ret30))}，综合退货率 ${(Math.abs(ret30) / (net30 + Math.abs(ret30)) * 100).toFixed(1)}%。${flagShops.length ? `**异常店铺（超均值 2 倍）**：${flagShops.map(([k, r]) => `${k}（${(r * 100).toFixed(1)}%）`).join('、')} → 建议核查该档口销售行为。` : '各店退货率在正常区间。'}`);

  // ④ 生产异常
  const unassignedBuyer = prodList.filter(p => !p.buyer_user || p.buyer_user === '无').length;
  const unassignedFollower = prodList.filter(p => !p.follower_user || p.follower_user === '无').length;
  L.push(`\n### ④ 生产异常（衣者）`);
  L.push(`欠货 **${fmt(num(production.owed_num))} 件**｜裁后未入库 ${fmt(num(production.cuted_not_in_num))} 件（当前漏斗卡点）｜面料未到 ${fmt(num(production.not_reach_num))} 件。`);
  L.push(`在产 ${prodList.length} 单中：未指派采购 ${unassignedBuyer} 单、未指派跟单 ${unassignedFollower} 单 → 建议落实「谁下单谁负责」归属规则。`);
}

// ========== 模块三：决策建议 ==========
{
  sec('三、决策建议（明天押注什么）');

  // 补货动作汇总（restock-deep 引擎）
  const rows = restock.rows || [];
  const sm = restock.summary || {};
  L.push(`### 补货动作总览（净缺口引擎）`);
  L.push(`追单 ${sm.need_new_order ?? '—'} 款（净缺口 ${fmt(num(sm.net_total))} 件）｜仅催货 ${sm.chase_only ?? '—'} 款｜挂起核实 ${sm.verify_stall ?? 0} 款。Top 追单建议：`);
  const region = restock.region?.cliCnt || {};
  const regionKnown = Object.values(region).reduce((s, v) => s + v, 0);
  const southPct = regionKnown ? (region['华南'] || 0) / regionKnown * 100 : null;
  L.push(`| 款号 | 品名 | 动作 | 建议量 | 在产 | 季节趋势 |`);
  L.push(`|---|---|---|---|---|---|`);
  rows.filter(r => (r.inprod ?? 0) < num(r.suggest_qty)).sort((a, b) => num(b.suggest_qty) - num(a.suggest_qty)).slice(0, 5)
    .forEach(r => L.push(`| ${r.item_ref} | ${r.name} | 追单 | ${fmt(num(r.suggest_qty))} | ${fmt(num(r.inprod))} | ${r.trend || '—'} |`));
  if (southPct) L.push(`\n地区结构：华南占已识别订单的 **${southPct.toFixed(0)}%** → 追单量取建议区间上限。`);

  // 3.2.1 碎片化补单
  const frag = new Map(); // ref -> orders[]
  for (const p of prodList) {
    const ref = (p.template_no || '').split(/[-—(/（]/)[0];
    if (!ref) continue;
    if (!frag.has(ref)) frag.set(ref, []);
    frag.get(ref).push(p);
  }
  fragItems = [];
  for (const [ref, os] of frag) {
    const maxBo = Math.max(...os.map(o => num(o.back_order_times)));
    if (maxBo < 4) continue;
    const st = styleStock.get(ref) || {};
    const dailyAvg = (alerts.restock_alerts || []).find(a => a.item_ref === ref)?.daily_avg ?? (st.s7 ? st.s7 / 7 : null);
    const inprod = os.filter(o => (o.status_desc || '').includes('进行中')).reduce((s, o) => s + num(o.plan_total_num), 0);
    const oneshot = dailyAvg ? Math.max(0, 47 * dailyAvg - num(st.stock) - inprod) : null; // (10交期+30覆盖+7安全)×日均
    fragItems.push({ ref, maxBo, dailyAvg, stock: num(st.stock), inprod, oneshot, name: (st.name && st.name !== ref) ? st.name : (goodsMap.get(ref)?.name || '（多客侧未建档，衣者在产款）') });
  }
  fragItems.sort((a, b) => b.maxBo - a.maxBo);
  L.push(`\n### 补单碎片化预警（返单≥4 次：${fragItems.length} 款）`);  L.push(`每多一轮补单 = 多一个约 10 天交期窗口。本轮起执行「一次补到位」：`);
  L.push(`| 款号 | 品名 | 返单次数 | 日均销 | 当前库存 | 在产 | 一次到位建议 |`);
  L.push(`|---|---|---|---|---|---|---|`);
  fragItems.slice(0, 6).forEach(x => L.push(`| ${x.ref} | ${x.name} | ${x.maxBo} 次 | ${x.dailyAvg ?? '—'} | ${fmt(x.stock)} | ${fmt(x.inprod)} | ${x.oneshot === null ? '先催货' : (x.oneshot <= 0 ? `在产 ${x.inprod} 件到货即可覆盖，**勿再追加**` : `补 ${fmt(x.oneshot)} 件`)} |`));

  // 3.2.2 首单动销 × 季节窗口预测
  const seasonEnd = { '秋季': '2026-11-30', '冬季': '2027-01-15' }; // 华南窗口（演示参数，正式版由3年品类曲线生成）
  L.push(`\n### 补单量预测（首单动销 × 季节窗口 · 演示参数）`);
  L.push(`| 款号 | 季节 | 日均销 | 剩余窗口 | 窗口内预计可销 | 库存+在产 | 建议补 |`);
  L.push(`|---|---|---|---|---|---|---|`);
  const forecastPool = rows.filter(r => num(r.suggest_qty) > 0).map(r => {
    const season = r.season && r.season !== '?' ? r.season : goodsMap.get(r.item_ref)?.season;
    const end = seasonEnd[season];
    if (!end || !num(r.daily_avg)) return null;
    const daysLeft = daysBetween(DATA_DATE.replace(/-/g, '/'), end.replace(/-/g, '/'));
    if (daysLeft <= 10) return { r, season, daysLeft, forecast: 0, stop: true };
    const forecast = Math.round(num(r.daily_avg) * daysLeft * 0.9); // 0.9=冬季档口脉冲修正（演示参数）
    return { r, season, daysLeft, forecast, stop: false };
  }).filter(Boolean).sort((a, b) => b.forecast - a.forecast).slice(0, 4);
  forecastPool.forEach(f => {
    const suggest = Math.max(0, f.forecast - num(f.r.stock) - num(f.r.inprod));
    L.push(`| ${f.r.item_ref} | ${f.season} | ${f.r.daily_avg} | ${f.daysLeft} 天${f.stop ? '（⚠停补）' : ''} | ${fmt(f.forecast)} 件 | ${fmt(num(f.r.stock))}+${fmt(num(f.r.inprod))} | ${f.stop ? '**停补，转清仓观察**' : `补 ${fmt(suggest)} 件`} |`);
  });
  L.push(`\n> 窗口截止日为演示参数；正式版用 3 年品类曲线按华南/北方分别生成，并给出停补日期。`);
}

// ========== 模块四：组织人效 ==========
{
  sec('四、组织人效（30 日）');
  const sellers = [...seller30.entries()].sort((a, b) => b[1] - a[1]);
  L.push(`**导购（30 日成交额）**：Top3 ${sellers.slice(0, 3).map(([k, v]) => `${k} ${wan(v)}`).join('｜')}${sellers.length > 6 ? `；Bottom3 ${sellers.slice(-3).map(([k, v]) => `${k} ${wan(v)}`).join('｜')}` : ''}。`);
  L.push(`**客户资产**：30 日成交 ${custCnt30().size} 家、复购率见速览；月未下单客户与流失三档名单见销售报表 V2.5（按柳红口径）。`);
  L.push(`**9 月绩效结论（引用绩效月报）**：采购到厂超期率 63.4%（王锡池 76.8% vs 肖小平 38.6%，差一倍但出货周期接近——瓶颈在流程不在人）；52 个可归因延误单中 49 个为工厂段（恒生 13 批超 5 天+）→ 问责指向工厂管理，不问责跟单员；设计师下单转化：SOSO 133% / 黄蓓蕾 82% / 陈佩哲 48% → 低转化者定向辅导。`);
}
function custCnt30() { const m = new Map(); for (const r of orders30) if (num(r.calc_price) > 0) m.set(r.client_id, 1); return m; }

// ========== 模块五：数据可信度声明 ==========
{
  sec('五、数据可信度声明');
  L.push(`- 库存数据以**多客在库口径**为准（衣者成品库存的"库存数"实为累计入库件数，不作库存解读）；`);
  L.push(`- 动销为**出库口径**，不含月末未发货订单；`);
  L.push(`- 超卖损失为估算值（日均销 × 款级成交均价），部分款无成交记录时回退全局客单价；`);
  L.push(`- 滞销占用资金为**下限值**（约 11.5% 销量对应款无成本价记录）；`);
  L.push(`- 双系统款号已按截断规则匹配，未匹配款不参与交叉分析；`);
  L.push(`- 本期数据日期：**${DATA_DATE}**（演示版取最近完整快照，非当日数据）。`);
}

// ========== 需要老板拍板 ==========
L.push(`\n## 六、今天需要拍板的 3 件事\n`);
L.push(`1. **碎片化补单治理**：返单 ≥4 次的 ${fragItems.length} 款，是否按「一次补到位」执行（详见第三节）；`);
L.push(`2. **资金调度**：衣者待付款 ${wan(num(finance.sum_wait_paid_price))}，需安排付款节奏；`);
L.push(`3. **异常退货核查**：${flagShops.length ? flagShops.map(([k]) => k).join('、') : '（本期无异常店铺）'}退货率显著偏离，是否安排核查。`);

fs.writeFileSync(OUT, `# 🎯 老板经营日报 ${DATA_DATE}\n\n> 数据日期 ${DATA_DATE}｜演示版（build-boss-report V0.1）｜生成于 ${new Date().toISOString().slice(0, 16).replace('T', ' ')}\n${L.join('\n')}\n`);
console.log(`[OK] 已生成 ${OUT}`);
