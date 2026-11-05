#!/usr/bin/env node
// match-template-no.mjs — 款号映射：全等 → 辅助(款名+品类) → 人工队列。零网络。
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const stateDir = path.join(dataHome, 'state');
fs.mkdirSync(stateDir, { recursive: true });
const db = JSON.parse(fs.readFileSync(path.join(stateDir, 'db.json'), 'utf8'));
const dates = Object.keys(db.days).sort();
const date = dates[dates.length - 1];
const slots = db.days[date] || {};
const day = slots.am || slots.pm;
const mapPath = path.join(stateDir, 'mapping.json');
const mapping = fs.existsSync(mapPath) ? JSON.parse(fs.readFileSync(mapPath, 'utf8')) : { pairs: [], manual_queue: [] };

// 衣者样板 vs 多客商品（按item_ref聚合）
const duokeByRef = {};
day.duoke.skus.forEach(s => { (duokeByRef[s.item_ref] = duokeByRef[s.item_ref] || []).push(s); });
const known = new Set(mapping.pairs.map(p => p.item_ref));

let auto = 0, aux = 0, queued = 0;
day.yizhe.templates.forEach(t => {
  if ([...known].includes(t.template_no)) return; // 已有人工确认
  if (duokeByRef[t.template_no]) {
    // 全等命中
    if (!mapping.pairs.find(p => p.template_no === t.template_no)) {
      mapping.pairs.push({ template_no: t.template_no, item_ref: t.template_no, method: 'exact', confidence: 1 });
      auto++;
    }
    return;
  }
  // 辅助：款名+品类
  const cand = Object.entries(duokeByRef).find(([, skus]) => skus[0].goods_name === t.template_name && skus[0].cate === t.cat_name);
  if (cand) {
    mapping.pairs.push({ template_no: t.template_no, item_ref: cand[0], method: 'aux', confidence: 0.8 });
    aux++;
    return;
  }
  // 人工队列
  const q = mapping.manual_queue.find(q => q.template_no === t.template_no);
  if (!q && t.template_status_name !== '废版') {
    mapping.manual_queue.push({ template_no: t.template_no, template_name: t.template_name, cat_name: t.cat_name, design_user: t.design_user, status: '待确认' });
    queued++;
  }
});
fs.writeFileSync(mapPath, JSON.stringify(mapping, null, 1));

const total = mapping.pairs.length + mapping.manual_queue.length;
const rate = total ? (mapping.pairs.length / total * 100).toFixed(1) : '0';
console.log(`[match] ${date}：全等命中 ${auto}，辅助命中 ${aux}，人工队列 ${queued}（累计待确认 ${mapping.manual_queue.filter(q => q.status === '待确认').length}）`);
console.log(`[match] 整体匹配率 ${rate}%（目标 ≥98%）`);
