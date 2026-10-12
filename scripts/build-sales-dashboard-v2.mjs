#!/usr/bin/env node
// 销售数据看板 V2：读报告JSON渲染
import fs from 'node:fs';
import path from 'node:path';
const SKILL = path.resolve(import.meta.dirname, '..');
const J = JSON.parse(fs.readFileSync(path.join(SKILL, 'out/销售数据报告-2026-10-10.json'), 'utf8'));
const money = n => Math.round(n || 0).toLocaleString('zh-CN');
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/\|/g, '/');
const f1 = n => (n || 0).toFixed(1);

const card = (label, val, sub, cls = '') => `<div class="card"><div class="lbl">${esc(label)}</div><div class="val ${cls}">${esc(val)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}</div>`;
const table = (headers, rows) => `<div class="tbl-wrap"><table><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;

const p30 = J.overview.p30, p7 = J.overview.p7;
const dormant = {
  t1: J.dormant_30_60.length, t2: J.dormant_60_365.length, t3: J.dormant_365_730.length,
};

const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>销售数据看板 V2 · 2026-10-10</title>
<style>
  :root { --pri:#1f6feb; --warn:#d97706; --danger:#dc2626; --bg:#f5f7fa; --card:#fff; --txt:#1f2937; --muted:#6b7280; --line:#e5e7eb; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif; background:var(--bg); color:var(--txt); padding:24px; }
  h1 { font-size:22px; margin-bottom:4px; }
  .meta { color:var(--muted); font-size:13px; margin-bottom:20px; line-height:1.8; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(165px,1fr)); gap:12px; margin-bottom:24px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
  .lbl { font-size:12px; color:var(--muted); margin-bottom:6px; }
  .val { font-size:23px; font-weight:700; }
  .warn { color:var(--warn); } .danger { color:var(--danger); } .pri { color:var(--pri); }
  .sub { font-size:12px; color:var(--muted); margin-top:4px; }
  section { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px 20px; margin-bottom:20px; }
  section h2 { font-size:16px; margin-bottom:12px; border-left:3px solid var(--pri); padding-left:8px; }
  .tbl-wrap { overflow-x:auto; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { background:#f0f4f8; text-align:left; padding:8px 10px; white-space:nowrap; border-bottom:2px solid var(--line); }
  td { padding:7px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }
  tr:hover td { background:#f8fafc; }
  .note { font-size:12px; color:var(--muted); margin-top:10px; line-height:1.7; }
  .cols2 { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
  @media(max-width:980px){ .cols2{grid-template-columns:1fr;} }
</style>
</head>
<body>
<h1>销售数据看板 V2（业务负责人修正口径）</h1>
<div class="meta">取数 2026-10-10 11:00 ｜ 多客 3 年 50,731 单全量明细 + 客户 17,186 家 + 实时库存 4,248 款 ｜ 当年当季=2026年·冬季<br>
口径：客单价=购买金额÷购买单数（退单不计）；连带=件数÷购买单数；补单金额=老客（非首单）下单金额；新客=3年全历史首次下单</div>

<div class="grid">
  ${card('近30日销售额(¥)', money(p30.amt), `${p30.orders} 单（购买 ${p30.buyN}）`)}
  ${card('近30日连带', f1(p30.attach) + ' 件/单', `新客 ${f1(p30.newAttach)} vs 老客 ${f1(p30.oldAttach)}`)}
  ${card('近30日补单金额(¥)', money(p30.reorderAmt), `占 ${(p30.reorderAmt / p30.amt * 100).toFixed(0)}%（老客贡献）`)}
  ${card('30-60天未下单', dormant.t1 + ' 家', '每日推送跟进')}
  ${card('60天-1年未下单', dormant.t2 + ' 家', '重点盘活池')}
  ${card('1-2年未下单', dormant.t3 + ' 家', '超2年已剔除')}
  ${card('预售欠货款', String(J.stock_owed_current_season.length), '负库存·补货最紧急', 'danger')}
</div>

<section>
<h2>总览（7日 / 半月 / 30日）</h2>
${table(['周期','单数','购买单数','金额(¥)','件数','连带(件/单)','新客购买单数','新客金额','新客连带','老客购买单数','老客金额','老客连带','补单金额'],
  [J.overview.p7, J.overview.p15, J.overview.p30].map((p, i) => {
    const l = ['近7日','近半月','近30日'][i];
    return [l, p.orders, p.buyN, money(p.amt), money(p.qty), f1(p.attach), p.newBuyN, money(p.newAmt), f1(p.newAttach), p.oldBuyN, money(p.oldAmt), f1(p.oldAttach), money(p.reorderAmt)];
  }))}
</section>

<section>
<h2>客户流失预警 · 30-60天档（按净额，前 12 家）</h2>
${table(['客户','等级','最后下单','间隔天','下单数','退单数','购买件数','退货件数','购买金额','退货金额','客单价','件单价'],
  J.dormant_30_60.slice(0, 12).map(r => [r.name, r.vip, r.last, r.gapDays, r.buyN, r.retN, money(r.buyQty), money(r.retQty), money(r.buyAmt), money(r.retAmt), money(r.aov), f1(r.unitPrice)]))}
<div class="note">60天-1年 ${dormant.t2} 家、1-2年 ${dormant.t3} 家完整名单见 JSON。</div>
</section>

<div class="cols2">
<section>
<h2>动销 TOP10 · 近7日（全品类）</h2>
${table(['款号','款名','销量','销售额','客户数','实时库存'], J.move_top_week.slice(0, 10).map(g => [g.ref, g.name, g.qty, money(g.amt), g.clients, g.stock]))}
</section>
<section>
<h2>动销 TOP10 · 近30日（全品类）</h2>
${table(['款号','款名','销量','销售额','客户数','实时库存'], J.move_top_month.slice(0, 10).map(g => [g.ref, g.name, g.qty, money(g.amt), g.clients, g.stock]))}
</section>
</div>

<section>
<h2>售罄率 TOP12（近30日销量 ÷ 衣者当前库存）</h2>
${table(['款号','款名','近30日销量','当前库存(衣者)','售罄率','客户数'], J.sell_through_30d.slice(0, 12).map(s => [s.ref, s.name, s.sold30, s.stock, Math.round(s.rate * 100) + '%', s.clients]))}
<div class="note">分母为衣者当前库存（累计总进货字段待系统方上线后切换）；>100% = 近期销量超当前库存（预售/补单在途）。</div>
</section>

<div class="cols2">
<section>
<h2>新品累计客户数 TOP10（对照 150 家普及面）</h2>
${table(['款号','款名','品类','累计客户数','累计销量','金额'], J.new_product_client_top.map(p => [p.ref, p.name, p.cat, p.clients, p.qty, money(p.amt)]))}
</section>
<section>
<h2>导购业绩（近30日）</h2>
${table(['导购','单数','金额','新客金额','老客金额','补单金额'], J.seller_30d.slice(0, 8).map(s => [s.seller, s.times, money(s.amt), money(s.newAmt), money(s.oldAmt), money(s.reorderAmt)]))}
</section>
</div>

<section>
<h2>库存告急（0&lt;库存&lt;50 且有动销）+ 预售欠货（负库存）</h2>
${table(['类型','款号','款名','实时库存','近7日销量','近30日销量','周转(周)'],
  J.stock_warn_current_season.map(s => ['告急', s.ref, s.name, s.stock, s.w, s.m, s.turn])
    .concat(J.stock_owed_current_season.slice(0, 8).map(s => ['欠货', s.ref, s.name, s.stock, s.w, s.m, '-'])))}
<div class="note">仅统计当年当季（2026年·冬季）。欠货=负库存（预售），按近30日销量排序=补货紧迫度。</div>
</section>

<div class="note">⚠️ 待拍板：售罄预警阈值 / 库存告急线 / ABCD-vip 对应 / 内部账户剔除清单（内部户A、清货、版衣特卖等仍在中，JSON 可先行过滤）。</div>
</body>
</html>`;
const out = path.join(SKILL, 'out/销售数据看板-2026-10-10.html');
fs.writeFileSync(out, html);
console.log('DASHBOARD V2 ->', out);
