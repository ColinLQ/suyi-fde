#!/usr/bin/env node
// alert-rules.mjs — 补货预警 + 超期红号。规则参数读取 config/rules.json。零网络。
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const rules = JSON.parse(fs.readFileSync(path.join(root, 'config', 'rules.json'), 'utf8'));
const R = rules['补货预警'];
const db = JSON.parse(fs.readFileSync(path.join(dataHome, 'state', 'db.json'), 'utf8'));
const dates = Object.keys(db.days).sort();
const date = args_date();
function args_date() {
  const a = process.argv.find(x => x.startsWith('--date='));
  return a ? a.split('=')[1] : dates[dates.length - 1];
}
const slots = db.days[date] || {};
const day = slots.am || slots.pm;
if (!day) { console.error('无该日数据'); process.exit(1); }

const out = { date, restock_alerts: [], overdue_orders: [], overdue_summary: {} };

// —— 1) 补货预警（款级聚合：库存/近7日日均 → 剩余天数） ——
const byRef = {};
day.duoke.skus.forEach(s => {
  const g = byRef[s.item_ref] = byRef[s.item_ref] || { item_ref: s.item_ref, name: s.goods_name, cate: s.cate, stock: 0, sold7: 0, sold30: 0, cost: 0, n: 0 };
  g.stock += s.stock; g.sold7 += s.sold_last7; g.sold30 += s.sold_30; g.cost += s.cost_price * s.stock; g.n++;
});
Object.values(byRef).forEach(g => {
  let dailyAvg = g.sold7 / 7;
  const oversold = g.stock < 0; // 超卖欠货：库存为负=已接单未回货（2026-09-28修复：原 stock<=0 return 漏掉全部超卖款）
  if (dailyAvg < 1) {
    if (oversold && g.sold30 / 30 >= 1) dailyAvg = g.sold30 / 30; // 超卖款近7日动销弱时回退30日日均（缺口真实存在）
    else return; // 无动销不补货；超卖且30日零动销=历史呆滞 → 记入 stale_oversold 待核销，不进预警
  }
  const daysLeft = g.stock / dailyAvg;
  if (!oversold && daysLeft >= R['预警阈值天']) return;
  const suggest = Math.max(0, Math.ceil(dailyAvg * (R['面料采购周期天'] + R['生产周期天']) * R['安全系数'] - g.stock));
  out.restock_alerts.push({
    item_ref: g.item_ref, name: g.name || `(品名待补) ${g.item_ref}`, cate: g.cate,
    stock: g.stock, daily_avg: Math.round(dailyAvg * 10) / 10, days_left: oversold ? '已超卖' : Math.round(daysLeft * 10) / 10,
    suggest_qty: suggest, stock_value: Math.round(g.cost),
    level: oversold ? '⛔超卖' : (daysLeft < 10 ? '🔴紧急' : '🟡关注')
  });
});
// 排序：超卖 > 紧急 > 关注；同级按剩余天数升序（"已超卖"置顶）
const LV = { '⛔超卖': 0, '🔴紧急': 1, '🟡关注': 2 };
const dl = x => x.days_left === '已超卖' ? -1e9 : x.days_left;
out.restock_alerts.sort((a, b) => (LV[a.level] - LV[b.level]) || (dl(a) - dl(b)));
// 呆滞超卖（30日零动销的负库存款）：不补货但需盘点核销，单独披露
out.stale_oversold = Object.values(byRef).filter(g => g.stock < 0 && g.sold7 / 7 < 1 && g.sold30 / 30 < 1).map(g => ({ item_ref: g.item_ref, gap: Math.abs(g.stock) }));

// —— 2) 超期红号（衣者跟单 less_finish_time.is_warn） ——
day.yizhe.follow_orders.forEach(o => {
  if (o.less_finish_time?.is_warn === 1) {
    out.overdue_orders.push({ template_no: o.template_no, type: o.production_type_desc, step: o.current_step, over: o.less_finish_time.value, factory: o.factory_name, follower: o.follower_user_name });
  }
});
const byStep = {};
out.overdue_orders.forEach(o => (byStep[o.step] = (byStep[o.step] || 0) + 1));
out.overdue_summary = byStep;

const outDir = path.join(dataHome, 'out'); fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, `alerts-${date}.json`), JSON.stringify(out, null, 1));
console.log(`[alert] ${date}：补货预警 ${out.restock_alerts.length} 款（紧急 ${out.restock_alerts.filter(a => a.level.includes('紧急')).length}）；超期订单 ${out.overdue_orders.length} 单`);
console.log(`[alert] 超期分布：${JSON.stringify(byStep)}`);
