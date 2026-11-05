#!/usr/bin/env node
// build-performance-report.mjs — 绩效分析与提成计算报告生成器。
// 数据源：data/raw/2026-10-10/pm/perf_*.jsonl（fetch-performance-history.mjs 全量回捞）
// 产出：out/performance-2026-09.json（供 build-perf-excel.py 生成 Excel 交付物）
// 口径依据：绩效分析与提成计算需求文档-V1（2026-10-10）
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const SRC = path.join(dataHome, 'data', 'raw', '2026-10-10', 'pm');
const OUT = path.join(dataHome, 'out');
fs.mkdirSync(OUT, { recursive: true });
const MONTH = '2026-09'; // 统计月：9月（10月仍在进行中，不作完整月统计）

const read = f => fs.readFileSync(path.join(SRC, f), 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
const stockout = read('perf_stockout_all.jsonl');       // 全量出货 4467
const purchase = read('perf_purchase_all.jsonl');       // 全状态采购 2953
const followDone = read('perf_follow_done.jsonl');      // 已完成跟单 2779
const followActive = read('perf_follow_active.jsonl');  // 在产跟单 194
const instockDone = read('perf_instock_done.jsonl');    // 已入库 4285
const templates = read('perf_template_all.jsonl');      // 样板全量 2889

// —— 工具 ——
const day = ts => (ts || '').slice(0, 10);
const dnum = ts => { const d = day(ts); return d && /^\d{4}-\d{2}-\d{2}$/.test(d) ? Math.floor(new Date(d + 'T00:00:00').getTime() / 864e5) : null; };
const diffDays = (a, b) => { const x = dnum(a), y = dnum(b); return x != null && y != null ? x - y : null; };
const inMonth = (ts, m) => (ts || '').startsWith(m);
const reachTime = r => { // 主料最后到厂时间（跟单follow_process文本解析）
  const step = (r.follow_process || []).find(s => s.process_name === '物料到厂');
  if (!step) return null;
  const f = {}; for (const x of step.fields || []) f[x.field_name] = x.value;
  const raw = f['主料最后到厂'];
  return raw && raw !== '-' ? raw : null;
};
const fmt1 = n => (n == null ? '-' : Number.isInteger(n) ? String(n) : n.toFixed(1));

// ══════════════ 需求1：采购跟单绩效 ══════════════
// 口径：按 created_at 月统计接单量；完成=采购完成且已到厂；超时=order_purchase_time_diff/order_reach_time_diff>0
const purchaseMonthly = purchase.filter(r => inMonth(r.created_at, MONTH));
const buyerStat = {};
for (const r of purchaseMonthly) {
  const b = r.buyer_name || '(未分配)';
  const s = buyerStat[b] ??= { 接单数: 0, 采购完成: 0, 采购中: 0, 待采购: 0, 已到厂: 0, 部分到厂: 0, 待到厂: 0, 采购超期: 0, 到厂超期: 0, 件数: 0 };
  s.接单数++; s.件数 += Number(r.plan_total_num || 0);
  if (r.buy_status === 3) s.采购完成++; else if (r.buy_status === 2) s.采购中++; else s.待采购++;
  if (r.reach_status === 3) s.已到厂++; else if (r.reach_status === 2) s.部分到厂++; else s.待到厂++;
  if (Number(r.order_purchase_time_diff) > 0) s.采购超期++;
  if (Number(r.order_reach_time_diff) > 0) s.到厂超期++;
}
// 采购明细（当月）
const purchaseDetail = purchaseMonthly.map(r => ({
  采购单号: r.purchase_sn, 款号: r.template_no, 采购员: r.buyer_name || '(未分配)',
  下单日期: r.created_at, 件数: r.plan_total_num, 工厂: r.factory_name || '',
  采购状态: r.buy_status_desc, 到厂状态: r.reach_status_desc,
  采购超期天数: Number(r.order_purchase_time_diff) > 0 ? r.order_purchase_time_diff : 0,
  到厂超期天数: Number(r.order_reach_time_diff) > 0 ? r.order_reach_time_diff : 0,
})).sort((a, b) => (a.下单日期 < b.下单日期 ? -1 : 1));

// ══════════════ 需求2：生产跟单绩效 ══════════════
// 口径：月出货按 stockout_at；实际周期=出货-主料到厂（跟单ID关联）；超时分级以"实际出货-预计出货"为轴
const followIdx = new Map();
for (const r of [...followDone, ...followActive]) followIdx.set(r.follow_order_id, r);
const stockoutMonthly = stockout.filter(r => inMonth(r.stockout_at, MONTH));
const followerStat = {};
const productionDetail = [];
for (const r of stockoutMonthly) {
  const name = r.follower_user_name || '(未分配)';
  const s = followerStat[name] ??= { 出货批次: 0, 出货件数: 0, 款数: new Set(), 准时: 0, 超1到2天: 0, 超3到5天: 0, 超5天以上: 0, 数据缺失: 0, 采购段延误: 0, 生产段延误: 0, 无法归因: 0, 周期样本: [] };
  s.出货批次++; s.出货件数 += Number(r.total_num || 0); s.款数.add(r.template_no);
  const fo = followIdx.get(r.follow_order_id);
  const est = fo?.estimated_finish_time || r.estimated_finish_time || '';
  const reach = fo ? reachTime(fo) : null;
  const overdue = diffDays(day(r.stockout_at), day(est)); // 实际-预计；null=缺预计
  // 延误归因：延期单中，主料到厂日晚于预计出货日 → 采购段延误；到厂按时但出货仍晚 → 生产段延误
  let attrib = '-';
  if (overdue == null) { grade: s.数据缺失++; attrib = '缺预计时间'; }
  else if (overdue <= 0) { s.准时++; }
  else if (overdue <= 2) { s.超1到2天++; }
  else if (overdue <= 5) { s.超3到5天++; }
  else { s.超5天以上++; }
  if (overdue != null && overdue > 0) {
    if (!reach) { attrib = '无法归因(缺到厂)'; s.无法归因++; }
    else if (diffDays(day(reach), day(est)) > 0) { attrib = '采购段延误'; s.采购段延误++; }
    else { attrib = '生产段延误'; s.生产段延误++; }
  }
  let grade;
  if (overdue == null) grade = '数据缺失';
  else if (overdue <= 0) grade = '准时';
  else if (overdue <= 2) grade = '超1-2天';
  else if (overdue <= 5) grade = '超3-5天';
  else grade = '超5天以上';
  const cyc = reach ? diffDays(day(r.stockout_at), day(reach)) : null;
  if (cyc != null) s.周期样本.push(cyc);
  productionDetail.push({
    出货日期: day(r.stockout_at), 款号: r.template_no, 跟单员: name, 工厂: r.factory_name || '',
    出货件数: r.total_num, 生产单号: r.production_sn,
    下单时间: day(r.order_created_at || ''),
    主料到厂: reach ? day(reach) : '(缺失)',
    实际周期天: cyc != null ? cyc : '(缺失)',
    预计出货: est ? day(est) : '(未填)', 实际出货: day(r.stockout_at),
    与预计差异天: overdue != null ? overdue : '(缺预计)',
    超时分级: grade, 延误归因: attrib, 订单类型: r.production_type_desc || '',
  });
}
for (const [k, s] of Object.entries(followerStat)) {
  s.款数 = s.款数.size;
  const arr = s.周期样本; delete s.周期样本;
  arr.sort((a, b) => a - b);
  s.平均周期 = arr.length ? +(arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(1) : null;
  s.周期中位 = arr.length ? arr[Math.floor((arr.length - 1) / 2)] : null;
  s.周期样本数 = arr.length;
}
productionDetail.sort((a, b) => (a.出货日期 < b.出货日期 ? -1 : 1));

// 工厂维度透视（企业完善：哪家工厂最拖）
const factoryStat = {};
for (const d of productionDetail) {
  const f = d.工厂 || '(未分配)';
  const s = factoryStat[f] ??= { 出货批次: 0, 出货件数: 0, 准时: 0, 超1到2天: 0, 超3到5天: 0, 超5天以上: 0, 数据缺失: 0, 采购段延误: 0, 生产段延误: 0 };
  s.出货批次++; s.出货件数 += Number(d.出货件数 || 0);
  const g = d.超时分级;
  if (g === '准时' || g === '超1-2天' || g === '超3-5天' || g === '超5天以上' || g === '数据缺失') {
    if (g === '超1-2天') s.超1到2天++;
    else if (g === '超3-5天') s.超3到5天++;
    else s[g]++;
  }
  const a = d.延误归因;
  if (a === '采购段延误' || a === '生产段延误') s[a]++;
}
for (const s of Object.values(factoryStat)) {
  const total = s.准时 + s.超1到2天 + s.超3到5天 + s.超5天以上;
  s.按时率 = total ? +(s.准时 / total * 100).toFixed(1) : null;
}

// ══════════════ 需求3：设计师月下单数量 ══════════════
// 口径：当月被下生产单的款（去重），来自生产订单。production 数据源用 follow 单（含 created_at）
const designedTemplates = new Map(templates.map(r => [r.template_no, r]));
const orderTemplates = [...followDone, ...followActive].filter(r => inMonth(r.created_at, MONTH));
const designerStat = {};
for (const r of orderTemplates) {
  const tpl = designedTemplates.get(r.template_no);
  const d = tpl?.design_user || '(未知)';
  const s = designerStat[d] ??= { 下单款数: new Set(), 下单件数: 0, 下单批次: 0 };
  s.下单款数.add(r.template_no); s.下单件数 += Number(r.plan_total_num || 0); s.下单批次++;
}
for (const s of Object.values(designerStat)) s.下单款数 = s.下单款数.size;

// 设计师建版数（月内新建样板）
for (const t of templates) {
  if (!inMonth(t.created_at, MONTH)) continue;
  const d = t.design_user || '(未知)';
  const s = designerStat[d] ??= { 下单款数: new Set(), 下单件数: 0, 下单批次: 0, 建版数: 0 };
  s.建版数 = (s.建版数 || 0) + 1;
}
// 转化率 = 下单款数(当月下单批次中的款) / 当月建版数 —— 注意款可能跨月，此处按"当月下单的款的设计师"计
for (const [d, s] of Object.entries(designerStat)) {
  s.设计转化率 = s.建版数 ? +(s.下单款数 / s.建版数 * 100).toFixed(0) + '%' : '-';
}

// 设计师明细：当月下单款清单
const designerDetail = orderTemplates.map(r => {
  const tpl = designedTemplates.get(r.template_no);
  return { 下单日期: day(r.created_at), 款号: r.template_no, 设计师: tpl?.design_user || '(未知)', 品类: tpl?.cat_name || '', 下单件数: r.plan_total_num, 订单类型: r.production_type_desc || '', 波段: tpl?.band_name || '' };
}).sort((a, b) => (a.下单日期 < b.下单日期 ? -1 : 1));

// ══════════════ 需求4：仓库录入及时性 ══════════════
// 口径：衣者出库(stockout_at) → 衣者入库(created_at) 时效；T+1 内=及时。月度统计+每日清单
const stockoutIdx = new Map(stockout.map(r => [r.record_id, r]));
const instockMonthly = instockDone.filter(r => inMonth(r.created_at, MONTH));
const warehouseStat = {}; const instockDaily = {};
const warehouseDetail = [];
for (const r of instockMonthly) {
  const so = stockoutIdx.get(r.stockout_record_id);
  if (!so) continue; // 无关联出库记录（含历史出库早于全量窗口，全量已覆盖）
  const user = r.username || '(未知)';
  const lag = diffDays(day(r.created_at), day(so.stockout_at)); // 入库-出库
  const timely = lag != null && lag <= 1;
  const s = warehouseStat[user] ??= { 入库单数: 0, 及时数: 0, 超1天: 0, 缺时间无法算: 0, lag样本: [] };
  s.入库单数++;
  if (lag == null) s.缺时间无法算++;
  else if (timely) { s.及时数++; s.lag样本.push(lag); }
  else { s.超1天++; s.lag样本.push(lag); }
  const dk = day(so.stockout_at); instockDaily[dk] = (instockDaily[dk] || 0) + 1;
  warehouseDetail.push({ 出库日期: dk, 出库件数: so.total_num, 款号: r.template_no, 生产单号: r.production_sn || '', 仓库录入人: user, 入库日期: day(r.created_at), 相差天数: lag != null ? lag : '(缺失)', 是否及时: lag != null ? (lag <= 1 ? '及时' : '超时') : '无法判定' });
}
for (const s of Object.values(warehouseStat)) {
  s.及时率 = s.入库单数 ? +(s.及时数 / s.入库单数 * 100).toFixed(1) : null;
  const a = s.lag样本; delete s.lag样本;
  s.平均延迟 = a.length ? +(a.reduce((x, y) => x + y, 0) / a.length).toFixed(1) : null;
}
warehouseDetail.sort((a, b) => (a.出库日期 < b.出库日期 ? -1 : 1));

// ══════════════ 汇总输出 ══════════════
const summary = {
  统计月: MONTH,
  数据就绪度: {
    采购月单量: purchaseMonthly.length, 出货月批次: stockoutMonthly.length,
    月出货件数: stockoutMonthly.reduce((a, r) => a + Number(r.total_num || 0), 0),
    月入库单: instockMonthly.length, 样板总量: templates.length,
  },
  采购跟单: buyerStat, 采购明细: purchaseDetail,
  生产跟单: followerStat, 生产明细: productionDetail, 工厂透视: factoryStat,
  设计师: designerStat, 设计明细: designerDetail,
  仓库: warehouseStat, 仓库明细: warehouseDetail,
  数据质量说明: {
    预计出货时间填写率: `${productionDetail.filter(d => d.预计出货 !== '(未填)').length}/${productionDetail.length}`,
    主料到厂可解析率: `${productionDetail.filter(d => d.主料到厂 !== '(缺失)').length}/${productionDetail.length}`,
    多客入库时间: '多客系统无入库时间记录，仓库时效按衣者内部口径（出库→入库），多客对齐方案见需求文档V1',
    统计范围: `出货${stockout.length}批/采购${purchase.length}单/完成跟单${followDone.length}/在产${followActive.length}/入库${instockDone.length}/样板${templates.length}（全量回捞 2026-10-10）`,
  },
};
fs.writeFileSync(path.join(OUT, 'performance-2026-09.json'), JSON.stringify(summary, null, 1));
console.log('[perf-report] JSON →', path.join(OUT, 'performance-2026-09.json'));
console.log(JSON.stringify({
  采购员数: Object.keys(buyerStat).length, 跟单员数: Object.keys(followerStat).length,
  设计师数: Object.keys(designerStat).length, 仓库人数: Object.keys(warehouseStat).length,
  明细行: { 采购: purchaseDetail.length, 生产: productionDetail.length, 设计: designerDetail.length, 仓库: warehouseDetail.length },
}, null, 1));
