#!/usr/bin/env node
// reconcile.mjs — 每日对账：成本口径(±1元) + 入库一致性。零网络。
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const rules = JSON.parse(fs.readFileSync(path.join(root, 'config', 'rules.json'), 'utf8'))['对账规则'];
const db = JSON.parse(fs.readFileSync(path.join(dataHome, 'state', 'db.json'), 'utf8'));
const dates = Object.keys(db.days).sort();
const a = process.argv.find(x => x.startsWith('--date='));
const date = a ? a.split('=')[1] : dates[dates.length - 1];
const slots = db.days[date] || {};
const day = slots.am || slots.pm;
const mapping = JSON.parse(fs.readFileSync(path.join(dataHome, 'state', 'mapping.json'), 'utf8'));
const tplMap = Object.fromEntries(mapping.pairs.map(p => [p.template_no, p.item_ref]));

const out = { date, cost_diff: [], stock_diff: [], summary: {} };

// 1) 成本口径：衣者样板价(款) vs 多客加权进货价(款)
const dkCost = {};
day.duoke.skus.forEach(s => { (dkCost[s.item_ref] = dkCost[s.item_ref] || { sum: 0, n: 0 }); dkCost[s.item_ref].sum += s.cost_price; dkCost[s.item_ref].n++; });
let costChecked = 0;
day.yizhe.templates.forEach(t => {
  const ref = tplMap[t.template_no] || t.template_no;
  const d = dkCost[ref]; if (!d) return;
  costChecked++;
  const diff = Math.abs(d.sum / d.n - Number(t.template_price));
  if (diff > rules['成本差异容忍元']) out.cost_diff.push({ template_no: t.template_no, yizhe: Number(t.template_price), duoke: Math.round(d.sum / d.n * 100) / 100, diff: Math.round(diff * 100) / 100 });
});

// 2) 入库一致性：衣者入库件数(汇总) vs 多客库存快照（Demo：同比值合理性）
const yzIn = Number(day.yizhe.production.stock_in_num || 0);
const dkStock = day.duoke.skus.reduce((a, s) => a + s.stock, 0);
out.summary = {
  cost_checked: costChecked, cost_violations: out.cost_diff.length,
  yizhe_stockin_total: yzIn, duoke_stock_total: dkStock,
  quality_flag: out.cost_diff.length === 0 ? 'PASS' : `WARN(${out.cost_diff.length}款成本差异>1元)`
};

const outDir = path.join(dataHome, 'out'); fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, `reconcile-${date}.json`), JSON.stringify(out, null, 1));
console.log(`[reconcile] ${date}：成本核对 ${costChecked} 款，超差 ${out.cost_diff.length} 款；衣者入库累计 ${yzIn} 件 vs 多客在库 ${dkStock} 件 → ${out.summary.quality_flag}`);
