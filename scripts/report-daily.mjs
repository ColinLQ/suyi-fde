#!/usr/bin/env node
// report-daily.mjs — 生成经营日报(markdown) + 五部门分版 + 看板H5。零网络，纯落盘产出（不负责推送）。
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const db = JSON.parse(fs.readFileSync(path.join(root, 'state', 'db.json'), 'utf8'));
const dates = Object.keys(db.days).sort();
const a = process.argv.find(x => x.startsWith('--date='));
const date = a ? a.split('=')[1] : dates[dates.length - 1];
const slots = db.days[date] || {};
const day = slots.am || slots.pm;
const alerts = JSON.parse(fs.readFileSync(path.join(root, 'out', `alerts-${date}.json`), 'utf8'));
const recon = JSON.parse(fs.readFileSync(path.join(root, 'out', `reconcile-${date}.json`), 'utf8'));
const mapping = JSON.parse(fs.readFileSync(path.join(root, 'state', 'mapping.json'), 'utf8'));

const f = n => Number(n || 0).toLocaleString('zh-CN');
const money = n => '¥' + Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 });

// —— 销售汇总 ——
const orders = day.duoke.orders || [];
const sales = orders.filter(o => Number(o.goods_quantity) > 0);
const returns = orders.filter(o => Number(o.goods_quantity) < 0);
const salesAmt = sales.reduce((a, o) => a + Number(o.calc_price), 0);
const salesQty = sales.reduce((a, o) => a + Number(o.goods_quantity), 0);
const returnAmt = returns.reduce((a, o) => a + Math.abs(Number(o.calc_price)), 0);

// —— 品类结构（款级库存货值×销量） ——
const byCate = {};
day.duoke.skus.forEach(s => {
  const c = byCate[s.cate] = byCate[s.cate] || { stock: 0, value: 0, sold7: 0 };
  c.stock += s.stock; c.value += s.cost_price * s.stock; c.sold7 += s.sold_last7;
});
const cateRows = Object.entries(byCate).sort((a, b) => b[1].sold7 - a[1].sold7);

// —— 销量Top10款 ——
const byRef = {};
day.duoke.skus.forEach(s => {
  const g = byRef[s.item_ref] = byRef[s.item_ref] || { name: s.goods_name, cate: s.cate, stock: 0, sold7: 0 };
  g.stock += s.stock; g.sold7 += s.sold_last7;
});
const top10 = Object.entries(byRef).sort((a, b) => b[1].sold7 - a[1].sold7).slice(0, 10);

// —— 销售业绩 ——
const bySeller = {};
(day.duoke.payments || []).forEach(p => { bySeller[p.seller_name] = (bySeller[p.seller_name] || 0) + Number(p.price); });

const p = day.yizhe.production, w = day.yizhe.warn, fin = day.yizhe.finance;
const urgent = alerts.restock_alerts.filter(x => x.level.includes('紧急') || x.level.includes('超卖'));
const oversold = alerts.restock_alerts.filter(x => x.level.includes('超卖'));
const srcDesc = day.meta.source_desc || (day.meta.source === 'mock' || day.meta.source === 'demo' ? '⚠️ Demo模拟数据' : '直连API采集');
const stockNote = day.meta.snapshot_from ? `⚠️ 库存快照回溯自 ${day.meta.snapshot_from}（早间批次不采snapshot层，复用最近晚间快照）` : '';

// ============ Markdown 日报 ============
const md = `# 📊 经营日报 ${date}

## 一、今日速览
| 指标 | 数值 |
|---|---|
| 销售金额（净） | ${money(salesAmt - returnAmt)} |
| 销售件数 / 单数 | ${f(salesQty)} 件 / ${f(sales.length)} 单（退货 ${returns.length} 单 ${money(returnAmt)}） |
| 收款流水 | ${money((day.duoke.payments || []).reduce((a, x) => a + Number(x.price), 0))} |
| 30天门店Top | ${day.duoke.console.transaction_top10?.[0]?.shop_name || '-'} ${money(day.duoke.console.transaction_top10?.[0]?.transaction_money)} |

## 二、生产进度（衣者）
- 在产订单 **${f(p.production_num)}** 单（首单${f(p.first_order)} / 返单${f(p.back_order)} / 订单${f(p.normal_order)}），下单件数 ${f(p.order_num)}
- 裁货 ${f(p.cuted_num)} → 出货 ${f(p.stock_out_num)} → 入库 ${f(p.stock_in_num)}；**欠货 ${f(p.owed_num)} 件**
- ⚠️ 异常：全部 ${w.total_error}（货期 ${w.date_error} / 进度 ${w.time_error} / 件数 ${w.num_error}）；未分厂 ${w.no_factory_count}、未指派采购 ${w.no_buyer_count}

## 三、补货预警（${alerts.restock_alerts.length} 款：⛔超卖 ${oversold.length}｜🔴紧急 ${alerts.restock_alerts.filter(x => x.level === '🔴紧急').length}｜🟡关注 ${alerts.restock_alerts.filter(x => x.level === '🟡关注').length}）
${oversold.length ? `> ⛔ **超卖欠货 ${oversold.length} 款**（库存为负=已接单未回货，须最优先处理）：\n${oversold.slice(0, 5).map(x => `> - ${x.item_ref} ${x.name}｜库存 ${f(x.stock)}｜日均销 ${x.daily_avg}｜建议补 ${f(x.suggest_qty)}\n`).join('')}` : ''}
| 级别 | 款号 | 品名 | 库存 | 日均销 | 可售天数 | 建议补货 |
|---|---|---|---|---|---|---|
${alerts.restock_alerts.slice(0, 10).map(x => `| ${x.level} | ${x.item_ref} | ${x.name} | ${f(x.stock)} | ${x.daily_avg} | ${x.days_left} | ${f(x.suggest_qty)} |`).join('\n')}

## 四、超期红号（${alerts.overdue_orders.length} 单）
- 分布：${Object.entries(alerts.overdue_summary).map(([k, v]) => `${k} ${v}单`).join('、') || '无'}
${alerts.overdue_orders.slice(0, 5).map(o => `- ${o.template_no} ${o.type}｜${o.step}｜${o.over}｜${o.factory}｜跟单:${o.follower}`).join('\n')}

## 五、品类结构（按近7日动销排序）
| 品类 | 库存(件) | 库存货值 | 近7日销量 |
|---|---|---|---|
${cateRows.map(([c, v]) => `| ${c} | ${f(v.stock)} | ${money(v.value)} | ${f(v.sold7)} |`).join('\n')}

## 六、销量Top10款
| # | 款号 | 品名 | 近7日销量 | 当前库存 |
|---|---|---|---|---|
${top10.map(([ref, g], i) => `| ${i + 1} | ${ref} | ${g.name} | ${f(g.sold7)} | ${f(g.stock)} |`).join('\n')}

## 七、销售业绩（流水归属）
${Object.entries(bySeller).sort((a, b) => b[1] - a[1]).map(([n, v]) => `- ${n}：${money(v)}`).join('\n')}

## 八、财务与数据质量
- 待核对金额 ${money(fin.sum_wait_paid_price)}（衣者财务口径）
- 成本对账：核对 ${recon.summary.cost_checked} 款，超差 ${recon.summary.cost_violations} 款 → **${recon.summary.quality_flag}**
- 款号匹配率：${(mapping.pairs.length / (mapping.pairs.length + mapping.manual_queue.length) * 100).toFixed(1)}%（人工队列 ${mapping.manual_queue.filter(q => q.status === '待确认').length} 款待确认）
${oversold.length ? `- ⛔ 超卖欠货：${oversold.length} 款库存为负（源系统真实状态：已接单未回货），累计缺口 ${f(oversold.reduce((a, x) => a + Math.abs(x.stock), 0))} 件，已列最高优先级预警\n` : ''}${alerts.stale_oversold?.length ? `- 🧊 呆滞超卖：另有 ${alerts.stale_oversold.length} 款负库存但30日零动销（历史遗留缺口 ${f(alerts.stale_oversold.reduce((a, x) => a + x.gap, 0))} 件），不建议补货，建议安排盘点核销\n` : ''}- 数据截至：${(day.meta.captured_at || '').replace('T', ' ').slice(0, 16)}（来源：${srcDesc}${stockNote ? '；' + stockNote : ''}）
`;

const outDir = path.join(root, 'out'); fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, `日报-${date}.md`), md);

// ============ 五部门分版（PRD US-01：研发/生产/销售/财务/仓库 各一份） ============
const pendingQ = mapping.manual_queue.filter(q => q.status === '待确认');
const deptReports = {
  '研发': `【研发日报 ${date}】
📐 近7日建版 ${(day.yizhe.templates || []).length} 款（Demo抽样）｜废版 ${(day.yizhe.templates || []).filter(t => t.template_status_name === '废版').length} 款
🏆 近7日动销Top品类：${cateRows.slice(0, 3).map(([c, v]) => `${c}(${f(v.sold7)}件)`).join('、')}
🎨 设计师样板占比：${[...new Set((day.yizhe.templates || []).map(t => t.design_user))].slice(0, 3).map(d => `${d}`).join('、')}
🔗 款号人工核对：待确认 ${pendingQ.length} 款${pendingQ.slice(0, 3).map(q => `\n  ? ${q.template_no} ${q.template_name}(${q.cat_name})·${q.design_user}`).join('')}`,
  '生产': `【生产日报 ${date}】
🏭 在产 ${f(p.production_num)} 单（首单${f(p.first_order)}/返单${f(p.back_order)}）｜下单件数 ${f(p.order_num)}
✂️ 裁货 ${f(p.cuted_num)} → 出货 ${f(p.stock_out_num)} → 入库 ${f(p.stock_in_num)}｜欠货 ${f(p.owed_num)} 件
⚠️ 超期 ${alerts.overdue_orders.length} 单：${Object.entries(alerts.overdue_summary).map(([k, v]) => `${k}${v}单`).join('、') || '无'}
🔧 未分厂 ${w.no_factory_count}｜未指派采购 ${w.no_buyer_count}｜未填加工费 ${w.no_price_count}`,
  '销售': `【销售日报 ${date}】
💰 销售(净) ${money(salesAmt - returnAmt)}｜${f(salesQty)}件/${sales.length}单（退货${returns.length}单）
🏆 Top3款：${top10.slice(0, 3).map(([ref, g]) => `${g.name}(${f(g.sold7)}件)`).join('、')}
📦 补货预警 ${alerts.restock_alerts.length} 款（🔴紧急${urgent.length}）${urgent.slice(0, 3).map(x => `\n  ${x.item_ref} ${x.name} 剩${x.days_left}天`).join('')}
🏬 门店Top：${(day.duoke.console.transaction_top10 || []).slice(0, 2).map(s => `${s.shop_name} ${money(s.transaction_money)}`).join('｜')}`,
  '财务': `【财务日报 ${date}】
💵 收款流水 ${money((day.duoke.payments || []).reduce((a, x) => a + Number(x.price), 0))}
📊 待核对 ${money(fin.sum_wait_paid_price)}（衣者口径）
⚖️ 成本对账：核对${recon.summary.cost_checked}款 超差${recon.summary.cost_violations}款 → ${recon.summary.quality_flag}
📦 库存货值 ${money(day.duoke.skus.reduce((a, s) => a + s.cost_price * s.stock, 0))}`,
  '仓库': `【仓库日报 ${date}】
📦 在库 ${f(day.duoke.skus.reduce((a, s) => a + s.stock, 0))} 件（多客口径）
📥 衣者入库累计 ${f(p.stock_in_num)} 件｜待入库见生产日报
⚖️ 入库一致性：衣者vs多客 ${recon.summary.quality_flag}
🔔 预警款缺货风险 ${urgent.length} 款，请优先配合补货入库`
};
for (const [dept, txt] of Object.entries(deptReports)) {
  fs.writeFileSync(path.join(outDir, `日报-${date}-${dept}版.txt`), txt);
}

// ============ 款号人工核对清单（PRD US-05） ============
if (pendingQ.length) {
  fs.writeFileSync(path.join(outDir, `款号核对清单-${date}.md`),
    `# 款号人工核对清单 ${date}\n\n> 以下款在衣者有样板、多客暂未自动匹配，请商品岗确认后告知智能体（逐条回复"款号=货号"即可回写映射）\n\n| # | 衣者款号 | 款名 | 品类 | 设计师 | 确认结果（待填） |\n|---|---|---|---|---|---|\n${pendingQ.map((q, i) => `| ${i + 1} | ${q.template_no} | ${q.template_name} | ${q.cat_name} | ${q.design_user} |  |`).join('\n')}\n`);
}

// ============ 看板H5 ============
const bar = (v, max, color) => `<div style="display:inline-block;width:${Math.max(2, v / max * 100)}%;min-width:4px;height:10px;background:${color};border-radius:5px;vertical-align:middle"></div>`;
const maxSold = Math.max(...top10.map(([, g]) => g.sold7), 1);
const html = `<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>经营看板 ${date}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#f5f7fa;color:#1f2937;padding:20px;max-width:1100px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px} .sub{color:#6b7280;font-size:12px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px}
.card{background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.card .k{font-size:12px;color:#6b7280;margin-bottom:4px}
.card .v{font-size:22px;font-weight:700}
.card .v.red{color:#dc2626}.card .v.amber{color:#d97706}.card .v.green{color:#059669}
.panel{background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:16px}
.panel h2{font-size:14px;margin-bottom:10px;color:#374151}
table{width:100%;border-collapse:collapse;font-size:12px}
th{color:#6b7280;font-weight:500;text-align:left;padding:6px 8px;border-bottom:1px solid #e5e7eb}
td{padding:6px 8px;border-bottom:1px solid #f3f4f6}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px}
.tag.red{background:#fee2e2;color:#dc2626}.tag.amber{background:#fef3c7;color:#d97706}
footer{color:#9ca3af;font-size:11px;text-align:center;padding:8px}
</style></head><body>
<h1>🏭 服装企业经营看板</h1>
<div class="sub">${date}｜衣者 × 多客 数据打通｜数据截至 ${(day.meta.captured_at || '').replace('T', ' ').slice(0, 16)}${day.meta.source === 'mock' ? '（⚠️ 模拟数据）' : ''}${day.meta.snapshot_from ? `｜库存快照回溯自 ${day.meta.snapshot_from}` : ''}</div>

<div class="grid">
<div class="card"><div class="k">销售金额（净）</div><div class="v red">${money(salesAmt - returnAmt)}</div></div>
<div class="card"><div class="k">销售件数</div><div class="v">${f(salesQty)} 件</div></div>
<div class="card"><div class="k">在产订单</div><div class="v">${f(p.production_num)} 单</div></div>
<div class="card"><div class="k">欠货数</div><div class="v amber">${f(p.owed_num)} 件</div></div>
<div class="card"><div class="k">生产异常</div><div class="v red">${w.total_error}</div></div>
<div class="card"><div class="k">补货预警</div><div class="v red">${urgent.length} 🔴 / ${alerts.restock_alerts.length} 🟡</div></div>
<div class="card"><div class="k">库存总货值</div><div class="v green">${money(day.duoke.skus.reduce((a, s) => a + s.cost_price * s.stock, 0))}</div></div>
<div class="card"><div class="k">数据质量</div><div class="v ${recon.summary.quality_flag === 'PASS' ? 'green' : 'amber'}">${recon.summary.quality_flag}</div></div>
</div>

<div class="panel"><h2>📦 补货预警（按紧急度排序，共 ${alerts.restock_alerts.length} 款）</h2>
<table><tr><th>级别</th><th>款号</th><th>品名</th><th>库存</th><th>日均销</th><th>可售天数</th><th>建议补货</th></tr>
${alerts.restock_alerts.slice(0, 10).map(x => `<tr><td><span class="tag ${x.level.includes('紧急') || x.level.includes('超卖') ? 'red' : 'amber'}">${x.level}</span></td><td>${x.item_ref}</td><td>${x.name}</td><td>${f(x.stock)}</td><td>${x.daily_avg}</td><td><b style="color:${x.days_left === '已超卖' || (typeof x.days_left === 'number' && x.days_left < 10) ? '#dc2626' : '#d97706'}">${x.days_left}</b></td><td><b>${f(x.suggest_qty)}</b></td></tr>`).join('') || '<tr><td colspan="7">无预警</td></tr>'}
</table></div>

<div class="panel"><h2>🏆 近7日销量 Top10 款</h2>
<table><tr><th>#</th><th>款号</th><th>品名</th><th style="width:30%">销量</th><th>库存</th></tr>
${top10.map(([ref, g], i) => `<tr><td>${i + 1}</td><td>${ref}</td><td>${g.name}</td><td>${bar(g.sold7, maxSold, '#dc2626')} ${f(g.sold7)}</td><td>${f(g.stock)}</td></tr>`).join('')}
</table></div>

<div class="panel"><h2>🗂 品类结构</h2>
<table><tr><th>品类</th><th>库存(件)</th><th>库存货值</th><th style="width:30%">近7日动销</th></tr>
${cateRows.map(([c, v]) => { const m = Math.max(...cateRows.map(([, x]) => x.sold7), 1); return `<tr><td>${c}</td><td>${f(v.stock)}</td><td>${money(v.value)}</td><td>${bar(v.sold7, m, '#059669')} ${f(v.sold7)}</td></tr>`; }).join('')}
</table></div>

<div class="panel"><h2>⚠️ 生产异常（${alerts.overdue_orders.length} 单超期）</h2>
<table><tr><th>款号</th><th>类型</th><th>卡点环节</th><th>超期</th><th>工厂</th><th>跟单</th></tr>
${alerts.overdue_orders.slice(0, 8).map(o => `<tr><td>${o.template_no}</td><td>${o.type}</td><td>${o.step}</td><td style="color:#dc2626">${o.over}</td><td>${o.factory}</td><td>${o.follower}</td></tr>`).join('') || '<tr><td colspan="6">无超期</td></tr>'}
</table></div>

<footer>scm-collector｜链路：直连API采集 → ingest → 款号映射 → 预警/对账 → 日报+看板｜成本口径以多客为准${oversold.length ? `｜⛔${oversold.length}款超卖欠货（负库存=已接单未回货）` : ''}</footer>
</body></html>`;
fs.writeFileSync(path.join(outDir, `看板-${date}.html`), html);

console.log(`[report] 产出：out/日报-${date}.md ｜ 五部门分版txt ｜ out/看板-${date}.html`);
