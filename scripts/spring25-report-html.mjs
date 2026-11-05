#!/usr/bin/env node
// 2025春季复盘 —— HTML报告生成（含商品图片）
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');  // skill代码根目录（可移植）
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const R = JSON.parse(fs.readFileSync(path.join(dataHome, 'out/spring25-review-data.json'), 'utf8'));

const fmt = n => (n || 0).toLocaleString('zh-CN');
const pct = s => `${s}%`;

// 款卡片行（图+字段）
function itemRow(x, opts = {}) {
  const extra = opts.extra || '';
  const badge = opts.badge || '';
  return `<tr class="item-row">
  <td class="rank">${badge || opts.rank}</td>
  <td class="imgcell"><img loading="lazy" src="${x.img}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2260%22 height=%2260%22%3E%3Crect width=%2260%22 height=%2260%22 fill=%22%23f0f0f0%22/%3E%3Ctext x=%2230%22 y=%2236%22 font-size=%2210%22 fill=%22%23999%22 text-anchor=%22middle%22%3E无图%3C/text%3E%3C/svg%3E'" alt=""></td>
  <td class="ref">${x.ref}</td>
  <td class="name">${x.name}</td>
  <td class="cat">${x.cat || ''}</td>
  ${extra}
</tr>`;
}

const th = arr => `<tr>${arr.map(t => `<th>${t}</th>`).join('')}</tr>`;
const table = (head, rows, cls = '') => `<table class="tbl ${cls}">${th(head)}</table>${rows ? `<table class="tbl ${cls}"><tbody>${rows}</tbody></table>` : ''}`;

// ============ 各板块 ============
function ranking(list, title, id, headCells, rowFn, note) {
  return `<section id="${id}">
  <h2>${title}</h2>
  ${note ? `<p class="note">${note}</p>` : ''}
  <table class="tbl"><thead>${th(headCells)}</thead><tbody>
  ${list.map((x, i) => rowFn(x, i + 1)).join('\n')}
  </tbody></table>
</section>`;
}

const head6 = ['排名', '图片', '款号', '品名', '品类'];

let html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2025春季 复盘报告（畅销·滞销·利润结构）</title>
<style>
  :root { --line:#e5e7eb; --txt:#1f2937; --sub:#6b7280; --accent:#b45309; --bg:#fafaf9; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; color:var(--txt); background:var(--bg); padding:24px; }
  .wrap { max-width:1080px; margin:0 auto; }
  h1 { font-size:24px; margin-bottom:4px; }
  .meta { color:var(--sub); font-size:12px; margin-bottom:20px; }
  h2 { font-size:17px; margin:34px 0 10px; padding-left:10px; border-left:4px solid var(--accent); }
  h3 { font-size:14px; margin:18px 0 8px; }
  .note { font-size:12px; color:var(--sub); margin-bottom:8px; }
  .tbl { width:100%; border-collapse:collapse; font-size:12.5px; background:#fff; }
  .tbl th { background:#f5f5f4; font-weight:600; padding:6px 8px; text-align:left; border-bottom:2px solid var(--line); white-space:nowrap; }
  .tbl td { padding:5px 8px; border-bottom:1px solid var(--line); vertical-align:middle; }
  .rank { width:36px; text-align:center; font-weight:700; color:var(--sub); }
  .rank.top { color:#dc2626; }
  .imgcell { width:54px; } .imgcell img { width:48px; height:48px; object-fit:cover; border-radius:4px; border:1px solid var(--line); background:#fff; display:block; }
  .ref { font-family:ui-monospace,Menlo,monospace; font-size:11.5px; white-space:nowrap; }
  .name { min-width:120px; }
  .num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .num.strong { font-weight:700; }
  .pos { color:#dc2626; } .neg { color:#16a34a; }
  .hl { background:#fef3c7; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; margin:12px 0; }
  .card { background:#fff; border:1px solid var(--line); border-radius:8px; padding:12px 14px; }
  .card .k { font-size:12px; color:var(--sub); }
  .card .v { font-size:22px; font-weight:700; margin-top:2px; }
  .card .s { font-size:11px; color:var(--sub); margin-top:2px; }
  .bar { display:inline-block; height:10px; background:linear-gradient(90deg,#f59e0b,#d97706); border-radius:2px; vertical-align:middle; }
  .bar.b2 { background:linear-gradient(90deg,#93c5fd,#3b82f6); }
  .legend { font-size:11px; color:var(--sub); margin:6px 0; }
  .tag { display:inline-block; font-size:10.5px; padding:1px 6px; border-radius:3px; background:#fef3c7; color:#92400e; margin-right:4px; }
  .tag.red { background:#fee2e2; color:#991b1b; }
  .tag.green { background:#dcfce7; color:#166534; }
  footer { margin-top:40px; padding-top:12px; border-top:1px solid var(--line); font-size:11px; color:var(--sub); }
  @media print { body{padding:8px} .tbl{font-size:10px} }
</style>
</head>
<body>
<div class="wrap">
<h1>2025春季 复盘报告</h1>
<p class="meta">畅销 · 滞销 · 售罄率 · 生产vs销售结构 · SKU · 返单 · 退货 ｜ 数据截至 2026-10-10 ｜ 多客×衣者 双系统直连采集</p>

<div class="cards">
  <div class="card"><div class="k">2025春 款数</div><div class="v">${R.totals.totStyles}</div><div class="s">商品档案 2025年·春季</div></div>
  <div class="card"><div class="k">SKU（单款单色）</div><div class="v">${R.skuStats.skuTotal}</div><div class="s">有效SKU（动销>100件）${R.skuStats.validSku} 个</div></div>
  <div class="card"><div class="k">生产计划总量</div><div class="v">${fmt(R.totals.totPlan)}</div><div class="s">衣者 378 张生产单</div></div>
  <div class="card"><div class="k">全周期净销量</div><div class="v">${fmt(R.totals.totQty)}</div><div class="s">2023-10 ~ 2026-10 已扣退货</div></div>
  <div class="card"><div class="k">净销售额</div><div class="v">¥${fmt(R.totals.totAmt)}</div><div class="s">吊牌价×净量合计</div></div>
</div>

<!-- ① 畅销TOP20 -->
${ranking(R.hot20, '① 去年春季 畅销款 TOP20', 'hot', [...head6, '净销量(件)', '净销售额(¥)', '当前库存'], (x, i) => itemRow(x, { rank: i, badge: i <= 3 ? `<span class="rank top">${i}</span>` : i, extra: `<td class="num strong">${fmt(x.qty)}</td><td class="num">${fmt(x.amt)}</td><td class="num ${x.stock < 0 ? 'neg' : ''}">${fmt(x.stock)}</td>` }), '口径：全周期净销量（销量−退货），2025春 85 款内排名。')}

<!-- ② 滞销TOP20 -->
${ranking(R.cold20, '② 去年春季 滞销款 TOP20', 'cold', [...head6, '净销量(件)', '净销售额(¥)', '当前库存'], (x, i) => itemRow(x, { rank: i, extra: `<td class="num strong neg">${fmt(x.qty)}</td><td class="num">${fmt(x.amt)}</td><td class="num">${fmt(x.stock)}</td>` }), '口径：全周期净销量升序（销量最少者最滞销）。')}

<!-- ③ 全盘售罄率 -->
<section id="sellout">
<h2>③ 全盘货品 售罄率 最高 / 最低 TOP10</h2>
<p class="note">口径：售罄率 = 净销量 ÷（净销量 + 当前库存），全店 4248 款（过滤销量≤20件小单与负库存款）；另附超卖预警榜。</p>
<h3>售罄率最高 TOP10（补货候选）</h3>
<table class="tbl"><thead>${th([...head6, '净销量', '当前库存', '售罄率'])}</thead><tbody>
${R.selloutTop10.map((x, i) => itemRow(x, { rank: i + 1, extra: `<td class="num">${fmt(x.qty)}</td><td class="num">${fmt(x.stock)}</td><td class="num strong pos">${x.rate}%</td>` })).join('\n')}
</tbody></table>
<h3>售罄率最低 TOP10（清仓候选）</h3>
<table class="tbl"><thead>${th([...head6, '净销量', '当前库存', '售罄率'])}</thead><tbody>
${R.selloutLow10.map((x, i) => itemRow(x, { rank: i + 1, extra: `<td class="num">${fmt(x.qty)}</td><td class="num">${fmt(x.stock)}</td><td class="num strong neg">${x.rate}%</td>` })).join('\n')}
</tbody></table>
<h3>⚠️ 超卖预警（当前库存为负 = 有未发货订单）</h3>
<table class="tbl"><thead>${th(['款号', '品名', '净销量', '当前库存'])}</thead><tbody>
${R.oversellTop.map(x => `<tr><td class="ref">${x.ref}</td><td>${x.name}</td><td class="num">${fmt(x.qty)}</td><td class="num neg strong">${fmt(x.stock)}</td></tr>`).join('\n')}
</tbody></table>
</section>

<!-- ④ 品类售罄率 -->
<section id="catrate">
<h2>④ 单品类 售罄率 最高 / 最低 TOP5</h2>
<p class="note">口径：品类聚合 售罄率 = Σ净销量 ÷（Σ净销量 + Σ库存），仅列款数≥10 的品类。</p>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
<div><h3>最高 TOP5</h3><table class="tbl"><thead>${th(['品类', '款数', '净销量', '库存', '售罄率'])}</thead><tbody>
${R.catTop5.map(x => `<tr><td>${x.cat}</td><td class="num">${x.styles}</td><td class="num">${fmt(Math.round(x.qty))}</td><td class="num">${fmt(Math.round(x.stock))}</td><td class="num strong pos">${x.rate}%</td></tr>`).join('\n')}
</tbody></table></div>
<div><h3>最低 TOP5</h3><table class="tbl"><thead>${th(['品类', '款数', '净销量', '库存', '售罄率'])}</thead><tbody>
${R.catLow5.map(x => `<tr><td>${x.cat}</td><td class="num">${x.styles}</td><td class="num">${fmt(Math.round(x.qty))}</td><td class="num">${fmt(Math.round(x.stock))}</td><td class="num strong neg">${x.rate}%</td></tr>`).join('\n')}
</tbody></table></div>
</div>
</section>

<!-- ⑤ 库存最大TOP20 -->
${ranking(R.stockTop20, '⑤ 全盘 当前库存量 最大 TOP20', 'stock', [...head6, '当前库存', '净销量', '年份·季节'], (x, i) => itemRow(x, { rank: i + 1, extra: `<td class="num strong">${fmt(x.stock)}</td><td class="num">${fmt(x.qty)}</td><td>${x.year || ''}·${x.season || ''}</td>` }), '口径：多客全仓库存（warehouse+store 加总），快照 2026-10-09。')}

<!-- ⑥⑦ 上市1/2个月动销率 -->
<section id="launch">
<h2>⑥ 单品上市 1 个月 动销率 最高 / 最低 TOP10</h2>
<p class="note">口径：上市日=商品建档日；动销率 = 上市后30天净销量 ÷ 生产计划件数（2025春款）。</p>
<h3>最高 TOP10</h3>
<table class="tbl"><thead>${th([...head6, '30天净销', '计划产量', '动销率'])}</thead><tbody>
${R.month1Top10.map((x, i) => itemRow(x, { rank: i + 1, extra: `<td class="num">${fmt(x.q30)}</td><td class="num">${fmt(x.plan)}</td><td class="num strong pos">${(x.r30 * 100).toFixed(0)}%</td>` })).join('\n')}
</tbody></table>
<h3>最低 TOP10</h3>
<table class="tbl"><thead>${th([...head6, '30天净销', '计划产量', '动销率'])}</thead><tbody>
${R.month1Low10.map((x, i) => itemRow(x, { rank: i + 1, extra: `<td class="num">${fmt(x.q30)}</td><td class="num">${fmt(x.plan)}</td><td class="num strong neg">${(x.r30 * 100).toFixed(0)}%</td>` })).join('\n')}
</tbody></table>
<h2 style="margin-top:30px">⑦ 单品上市 2 个月 动销率 最高 / 最低 TOP10</h2>
<p class="note">口径：上市后60天净销量 ÷ 生产计划件数。</p>
<h3>最高 TOP10</h3>
<table class="tbl"><thead>${th([...head6, '60天净销', '计划产量', '动销率'])}</thead><tbody>
${R.month2Top10.map((x, i) => itemRow(x, { rank: i + 1, extra: `<td class="num">${fmt(x.q60)}</td><td class="num">${fmt(x.plan)}</td><td class="num strong pos">${(x.r60 * 100).toFixed(0)}%</td>` })).join('\n')}
</tbody></table>
<h3>最低 TOP10</h3>
<table class="tbl"><thead>${th([...head6, '60天净销', '计划产量', '动销率'])}</thead><tbody>
${R.month2Low10.map((x, i) => itemRow(x, { rank: i + 1, extra: `<td class="num">${fmt(x.q60)}</td><td class="num">${fmt(x.plan)}</td><td class="num strong neg">${(x.r60 * 100).toFixed(0)}%</td>` })).join('\n')}
</tbody></table>
</section>

<!-- ⑧ 品类生产vs销售 -->
<section id="catcmp">
<h2>⑧ 品类 生产占比 vs 实际销售占比（2025春）</h2>
<p class="note">口径：生产占比 = 品类计划产量 ÷ 总计划产量（款维度合并）；销售占比 = 品类净销量（件）÷ 总净销量；附回款金额占比。偏差列 = 产量占比 − 销量占比，负值=供不应求。</p>
<table class="tbl"><thead>${th(['品类', '款数', '计划产量(件)', '产量占比', '净销量(件)', '销量占比', '净销售额(¥)', '销售额占比', '产>销偏差'])}</thead><tbody>
${R.catCompare.map(x => {
  const d = (parseFloat(x.prodShare) - parseFloat(x.qtyShare)).toFixed(1);
  return `<tr class="${Math.abs(d) >= 1 ? 'hl' : ''}"><td>${x.cat}</td><td class="num">${x.styles}</td><td class="num">${fmt(x.plan)}</td><td class="num">${x.prodShare}%</td><td class="num">${fmt(x.qty)}</td><td class="num">${x.qtyShare}%</td><td class="num">${fmt(x.amt)}</td><td class="num">${x.amtShare}%</td><td class="num ${d > 0 ? 'pos' : 'neg'}">${d > 0 ? '+' : ''}${d}pct</td></tr>`;
}).join('\n')}
</tbody></table>
</section>

<!-- ⑨ 颜色生产vs销售 -->
<section id="colorcmp">
<h2>⑨ 颜色 生产占比 vs 实际销售占比（2025春）</h2>
<p class="note">口径：生产 = 378 张生产单颜色×件数（衣者精确数据，归一化后 ${fmt(R.colorCompare.prodTotal)} 件）；销售 = 明细行颜色聚合（${fmt(R.colorCompare.saleTotal)} 件）。</p>
<table class="tbl"><thead>${th(['颜色', '生产件数', '生产占比', '销售件数', '销售占比', '产-销偏差'])}</thead><tbody>
${(() => {
  const cats = [...new Set([...R.colorCompare.prod.map(x => x.c), ...R.colorCompare.sale.map(x => x.c)])];
  const rows = cats.map(c => {
    const p = R.colorCompare.prod.find(x => x.c === c), s = R.colorCompare.sale.find(x => x.c === c);
    const ps = p ? parseFloat(p.share) : 0, ss = s ? parseFloat(s.share) : 0;
    return { c, pn: p?.n || 0, ps, sn: s?.n || 0, ss, d: (ps - ss).toFixed(1) };
  }).sort((a, b) => b.pn - a.pn).slice(0, 15);
  return rows.map(x => `<tr class="${Math.abs(x.d) >= 1 ? 'hl' : ''}"><td>${x.c}</td><td class="num">${fmt(x.pn)}</td><td class="num">${x.ps.toFixed(1)}%</td><td class="num">${fmt(x.sn)}</td><td class="num">${x.ss.toFixed(1)}%</td><td class="num ${x.d > 0 ? 'pos' : 'neg'}">${x.d > 0 ? '+' : ''}${x.d}pct</td></tr>`).join('\n');
})()}
</tbody></table>
<p class="legend"><span class="bar" style="width:60px"></span> 生产占比 ｜ <span class="bar b2" style="width:60px"></span> 销售占比（红字=产>销积压倾向，绿字=产<供不应求）</p>
</section>

<!-- ⑩ 价格段 -->
<section id="price">
<h2>⑩ 价格段定位（10元间隔）：生产 vs 实际销售（2025春）</h2>
<p class="note">口径：生产 = 款吊牌价档 × 计划产量；销售 = 明细成交价 × 净量（已过滤 <15元 与 >400元 异常价行）。仅列有量的价格段。</p>
<table class="tbl"><thead>${th(['价格段', '款数', '计划产量', '产量占比', '净销量', '销量占比', '净销售额(¥)', '产-销偏差'])}</thead><tbody>
${R.priceBands.filter(b => b.styles > 0 || b.qty > 100).map(b => {
  const d = (parseFloat(b.prodShare) - parseFloat(b.qtyShare)).toFixed(1);
  return `<tr class="${Math.abs(d) >= 1 ? 'hl' : ''}"><td>${b.band}</td><td class="num">${b.styles}</td><td class="num">${fmt(b.plan)}</td><td class="num">${b.prodShare}%</td><td class="num">${fmt(b.qty)}</td><td class="num">${b.qtyShare}%</td><td class="num">${fmt(b.amt)}</td><td class="num ${d > 0 ? 'pos' : 'neg'}">${d > 0 ? '+' : ''}${d}pct</td></tr>`;
}).join('\n')}
</tbody></table>
</section>

<!-- ⑪ SKU -->
<section id="sku">
<h2>⑪ SKU 总数与 有效SKU（2025春）</h2>
<div class="cards">
  <div class="card"><div class="k">SKU 总数（单款单色）</div><div class="v">${R.skuStats.skuTotal}</div><div class="s">85 款 × 平均 2.5 色</div></div>
  <div class="card"><div class="k">有效 SKU（动销 >100 件）</div><div class="v">${R.skuStats.validSku}</div><div class="s">占比 ${(R.skuStats.validSku / R.skuStats.skuTotal * 100).toFixed(0)}%</div></div>
</div>
<h3>有效SKU 销量 TOP30（单款单色）</h3>
<table class="tbl"><thead>${th(['款号', '品名', '品类', '颜色', '净销量'])}</thead><tbody>
${R.skuStats.validList.map(x => `<tr><td class="ref">${x.ref}</td><td>${x.name}</td><td>${x.cat}</td><td>${x.color}</td><td class="num strong">${fmt(x.qty)}</td></tr>`).join('\n')}
</tbody></table>
</section>

<!-- ⑫ 返单款 -->
${ranking(R.reorderTop10, '⑫ 客户返单款 TOP10（按返单数量）', 'reorder', [...head6, '总净销量', '返单数量', '返单占比'], (x, i) => itemRow(x, { rank: i + 1, extra: `<td class="num">${fmt(x.qty)}</td><td class="num strong pos">${fmt(x.reorderQty)}</td><td class="num">${(x.reorderQty / x.qty * 100).toFixed(0)}%</td>` }), '口径：返单 = 同一客户对同款第2张及以后销售单据的净量合计（2025春款）。')}

<!-- ⑬ 退货款 -->
${ranking(R.returnTop10, '⑬ 退货款 TOP10（按退货数量，2025春）', 'ret', [...head6, '净销量', '退货量', '退货率'], (x, i) => itemRow(x, { rank: i + 1, extra: `<td class="num">${fmt(x.qty)}</td><td class="num strong neg">${fmt(x.retQty)}</td><td class="num">${(Math.abs(x.retQty) / (x.qty + Math.abs(x.retQty)) * 100).toFixed(1)}%</td>` }), '口径：明细中负数量行合计（含换货冲减），退货率 = 退货量 ÷ 毛销量。')}

<footer>
  数据源：多客 air.duoke.net（商品快照 2026-10-09 ｜ 3年销售明细 50,731 单 259,208 行）× 衣者 scm.yizheyun.com（2025春窗口生产单 378 张 + 颜色明细）<br>
  生成时间：${new Date().toISOString().slice(0, 19).replace('T', ' ')} ｜ scm-collector skill ｜ 只读采集，未做任何写操作
</footer>
</div>
</body>
</html>`;

fs.writeFileSync(path.join(dataHome, 'out/2025春季复盘-畅销滞销与利润.html'), html);
console.log('HTML 生成完成:', path.join(dataHome, 'out/2025春季复盘-畅销滞销与利润.html'), (html.length / 1024).toFixed(0) + 'KB');
