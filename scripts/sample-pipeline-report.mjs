#!/usr/bin/env node
/**
 * sample-pipeline-report.mjs — 样衣管理日报（设计部会议需求落地 V1.0，2026-10-26）
 *
 * 依据 2026-10-23 设计部门沟通会老板拍板的规则：
 *   1. 管线蓄水池：13 个环节实时件数 + 环节间流转（今日快照 vs 上一快照）
 *   2. 时间预警：新开发→面辅料 1天 ｜ →打板 3天 ｜ →车板 3天 ｜ 攒20个可审版 ｜ 审版完成→下单 7天 ｜ 审版完成滞留 14天必提醒
 *   3. 废版率：单季废版/总建版（备注含废版原因五类关键词的占比）
 *   4. 新品开发品类结构：按创建日期归周 × 品类（周更）+ 当季累计
 *   5. 数据完整性稽核：款名/波段/季节/版次/预计上新缺失清单（补数督促）
 *   6. 今日工作清单：已打板+已车板按"波段最新季优先、新创建优先"排序（预计上新字段填充后自动接管排序）
 *
 * 用法：
 *   node scripts/sample-pipeline-report.mjs [--date YYYY-MM-DD] [--prev-date YYYY-MM-DD] [--out out/样衣管理日报-<date>.md]
 * 数据源：data/raw/<date>/am/yizhe_template_list.jsonl（fetch-endpoints.mjs detail 批次产出）
 * 只读：本脚本不调用任何写接口。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
function argOf(flag, def) { const i = args.indexOf(flag); return i >= 0 && args[i + 1] ? args[i + 1] : def; }

const today = argOf('--date', new Date().toISOString().slice(0, 10));
const slot = argOf('--slot', 'am');
const OUT = path.join(ROOT, argOf('--out', `out/样衣管理日报-${today}.md`));

// ---------- 规则常量（会议拍板，改动须留痕） ----------
const RULES = {
  fabircWaitDays: 1,      // 新开发→面辅料齐：1天
  patternDays: 3,         // →已打板：3天
  sewingDays: 3,          // →已车板：3天
  reviewTriggerCount: 20, // 攒够20个即可提前审版
  orderDays: 7,           // 审版完成→下单：7天
  stayWarnDays: 14,       // 审版完成滞留14天必须提醒
  fabricReadyDays: 2,     // 下单后面辅料2天内到齐（样衣面料到了即可）
};
// 环节顺序（按衣者 sort），用于"今日先做什么"排序权重
const STEP_ORDER = ['新开发', '面辅料齐', '已打板', '已车板', '复版', '审版完成', '废版', '待下单', '面辅料已填', '用量已算', '制单完善', '确认可下单', '已下单'];

function readSnapshot(date) {
  const base = path.join(ROOT, 'data', 'raw', date);
  // 当日无指定槽位文件时，回落到该日期任意槽位的快照
  const candidates = [path.join(base, slot, 'yizhe_template_list.jsonl'), path.join(base, 'am', 'yizhe_template_list.jsonl'), path.join(base, 'pm', 'yizhe_template_list.jsonl')];
  const p = candidates.find(c => fs.existsSync(c));
  if (!p) return null;
  const list = fs.readFileSync(p, 'utf8').split('\n').filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
  return { path: p, list };
}

function daysBetween(d1, d2) { return Math.floor((d2 - d1) / 86400000); }
const fmtN = n => (n ?? 0).toLocaleString('zh-CN');

// ---------- 主分析 ----------
const snap = readSnapshot(today);
if (!snap) { console.error(`[report] 未找到 ${today}/${slot} 快照，请先跑 fetch-endpoints.mjs --batch evening --only yizhe_template_list.jsonl`); process.exit(1); }
const rows = snap.list;
const now = new Date(today + 'T12:00:00+08:00');

// 1) 蓄水池
const pool = {};
for (const r of rows) { const st = r.template_status_name || '未知'; (pool[st] ||= []).push(r); }

// 2) 时间预警（基于 created_at 与当前环节；到达即入环节，停留=now-created_at，粗粒度但够用）
const warns = [];
const days = r => daysBetween(new Date(r.created_at), now);

for (const r of pool['新开发'] || []) { const d = days(r); if (d >= RULES.fabircWaitDays) warns.push({ lvl: d >= 3 ? '高' : '中', type: '面辅料未齐', no: r.template_no, name: r.template_name, band: r.band_name, days: d, hint: `新开发已停 ${d} 天（规则 ${RULES.fabircWaitDays} 天内到面辅料）` }); }
for (const r of pool['面辅料齐'] || []) { const d = days(r); if (d >= RULES.patternDays) warns.push({ lvl: d >= 5 ? '高' : '中', type: '待打板超时', no: r.template_no, name: r.template_name, band: r.band_name, days: d, hint: `面辅料已齐 ${d} 天未打板（规则 ${RULES.patternDays} 天内）` }); }
for (const r of pool['已打板'] || []) { const d = days(r); if (d >= RULES.sewingDays) warns.push({ lvl: d >= 5 ? '高' : '中', type: '待车板超时', no: r.template_no, name: r.template_name, band: r.band_name, days: d, hint: `已打板 ${d} 天未车板（规则 ${RULES.sewingDays} 天内）` }); }

// 审版：已车板+复版 攒够20个提醒
const reviewReady = [...(pool['已车板'] || []), ...(pool['复版'] || [])];

// 审版完成→下单 7天 / 滞留14天
const reviewDone = pool['审版完成'] || [];
for (const r of reviewDone) {
  const d = days(r);
  if (d >= RULES.stayWarnDays) warns.push({ lvl: '高', type: '审版完成滞留≥14天', no: r.template_no, name: r.template_name, band: r.band_name, days: d, hint: `再不下单来不及上货，今天必须决定：下单或转待下单/废版` });
  else if (d >= RULES.orderDays) warns.push({ lvl: '中', type: '待下单超时', no: r.template_no, name: r.template_name, band: r.band_name, days: d, hint: `审版完成已 ${d} 天未下单（规则 ${RULES.orderDays} 天内）` });
}

// 3) 废版率（全量口径）
const scrap = (pool['废版'] || []).length;
const scrapRate = rows.length ? (scrap / rows.length * 100) : 0;
// 废版原因五类关键词命中（备注在详情接口 remark，列表无；此维度待详情回捞后补全，先统计款名可判的）
const SCRAP_KEYS = [['雷同', '雷同款'], ['滞销', '含滞销元素'], ['价格', '价格带不匹配'], ['搭配', '搭配性不强'], ['主题', '主题性不强'], ['风格', '风格偏离']];

// 4) 品类结构（按创建日期归周；周一起算）
function weekKey(dateStr) {
  const d = new Date(dateStr.slice(0, 10) + 'T12:00:00+08:00');
  const day = (d.getDay() + 6) % 7; const mon = new Date(d); mon.setDate(d.getDate() - day);
  return mon.toISOString().slice(0, 10);
}
const RECENT_SEASON_START = '2026-10-01'; // 当季（2027春）开发窗口起点，跨季时改这里或走配置
const weekCat = new Map(); const seasonCat = new Map();
for (const r of rows) {
  const ca = r.created_at || '';
  if (ca < RECENT_SEASON_START) continue;
  const wk = weekKey(ca); const cat = r.cat_name || '未分类';
  if (!weekCat.has(wk)) weekCat.set(wk, new Map());
  const wm = weekCat.get(wk); wm.set(cat, (wm.get(cat) || 0) + 1);
  seasonCat.set(cat, (seasonCat.get(cat) || 0) + 1);
}

// 5) 数据完整性稽核
const missingName = rows.filter(r => !(r.template_name || '').trim());
const missingBand = rows.filter(r => !(r.band_name || '').trim());
const bandAnomaly = rows.filter(r => /^(C[1-9]|D[1-9])$/.test((r.band_name || '').trim())); // C1/C2 新编码未按规范
// 近30天新建款的缺失（补数优先级最高）
const cutoff30 = new Date(now); cutoff30.setDate(cutoff30.getDate() - 30);
const recent = rows.filter(r => new Date(r.created_at) >= cutoff30);
const recentMissingName = recent.filter(r => !(r.template_name || '').trim());
const recentMissingBand = recent.filter(r => !(r.band_name || '').trim());

// 6) 今日工作清单（预计上新字段填充率≈0，暂按：环节靠前+创建新 优先；字段补齐后自动切换排序）
const workToday = [];
for (const st of ['面辅料齐', '已打板', '已车板']) {
  for (const r of pool[st] || []) workToday.push({ st, no: r.template_no, name: r.template_name || '(款名空)', band: r.band_name || '(波段空)', ca: r.created_at, img: r.template_thumb || '' });
}
workToday.sort((a, b) => (a.st.localeCompare(b.st)) || (b.ca.localeCompare(a.ca)));

// ---------- 输出 Markdown ----------
const L = [];
L.push(`# 样衣管理日报 ${today}`);
L.push('');
L.push(`> 数据源：衣者样板全量快照（${slot}，${fmtN(rows.length)} 款）｜ 规则：2026-10-23 设计部会议拍板 ｜ 生成：scm-collector sample-pipeline-report V1.0`);
L.push('');
L.push(`## 一、管线蓄水池（各环节实时件数）`);
L.push('');
L.push('| 环节 | 件数 | 占比 |');
L.push('|---|---:|---:|');
for (const st of STEP_ORDER) { const n = (pool[st] || []).length; if (n || st !== '未知') L.push(`| ${st} | ${fmtN(n)} | ${(n / rows.length * 100).toFixed(1)}% |`); }
const otherKeys = Object.keys(pool).filter(k => !STEP_ORDER.includes(k));
for (const k of otherKeys) L.push(`| ${k}(未归类) | ${fmtN(pool[k].length)} | - |`);
L.push(`| **合计** | **${fmtN(rows.length)}** | 100% |`);
L.push('');
L.push(`- 未下单总量：**${fmtN(rows.length - (pool['已下单'] || []).length)}** 款（含废版 ${fmtN(scrap)}）`);
L.push(`- 废版率（全量累计）：**${scrapRate.toFixed(1)}%**（${fmtN(scrap)} / ${fmtN(rows.length)}）`);
L.push('');

L.push(`## 二、⚠️ 时间预警（${warns.length} 条）`);
L.push('');
if (!warns.length) L.push('今日无超时预警，流水线节奏正常。');
else {
  L.push('| 级别 | 类型 | 款号 | 款名 | 波段 | 停留 | 说明 |');
  L.push('|---|---|---|---|---|---|---|');
  const order = { '高': 0, '中': 1 };
  for (const w of warns.sort((a, b) => order[a.lvl] - order[b.lvl] || b.days - a.days).slice(0, 60)) {
    L.push(`| ${w.lvl} | ${w.type} | ${w.no} | ${w.name || '(空)'} | ${w.band || '(空)'} | ${w.days} 天 | ${w.hint} |`);
  }
  if (warns.length > 60) L.push(`\n（仅列前 60 条，共 ${warns.length} 条——绝大多数为历史积压款，建议先清理旧款再让规则生效）`);
}
L.push('');
const reviewCnt = reviewReady.length;
L.push(`### 审版提醒`);
L.push('');
L.push(`- 当前可审版池（已车板+复版）：**${fmtN(reviewCnt)} 个**${reviewCnt >= RULES.reviewTriggerCount ? ` → 已达 ${RULES.reviewTriggerCount} 个门槛，**今天可以安排审版**（不必等周节点）` : ` → 未达 ${RULES.reviewTriggerCount} 个门槛，等攒够或到周审节点`}`);
L.push(`- 审版完成待下单池：**${fmtN(reviewDone.length)} 个**（规则：${RULES.orderDays} 天内下单，滞留 ${RULES.stayWarnDays} 天必须处理）`);
L.push('');

L.push(`## 三、📋 今日工作清单（先做什么）`);
L.push('');
L.push(`> 排序规则：环节优先（面辅料齐→已打板→已车板）+ 同环节新创建优先。`);
L.push(`> 📌 待"预计上新时间"字段补填后，自动切换为【按预计上新紧迫度】排序（会议要求的最终形态）。`);
L.push('');
L.push(`| 优先 | 环节 | 款号 | 款名 | 波段 | 创建日期 |`);
L.push(`|---|---|---|---|---|---|`);
workToday.slice(0, 40).forEach((w, i) => L.push(`| ${i + 1} | ${w.st} | ${w.no} | ${w.name} | ${w.band} | ${w.ca?.slice(0, 10) || '-'} |`));
if (workToday.length > 40) L.push(`\n（仅列前 40 条，共 ${workToday.length} 条在制品）`);
L.push('');

L.push(`## 四、🧵 新品开发品类结构（${RECENT_SEASON_START.slice(0, 7)} 起，周更）`);
L.push('');
const wks = [...weekCat.keys()].sort();
if (!wks.length) { L.push('当季窗口内无新建样板。'); }
else {
  const cats = [...new Set([...seasonCat.keys()])].sort((a, b) => (seasonCat.get(b) || 0) - (seasonCat.get(a) || 0));
  L.push(`| 周(周一起) | ${cats.join(' | ')} | 周合计 |`);
  L.push(`|---|${cats.map(() => '---:').join('|')}|---:|`);
  for (const wk of wks) {
    const wm = weekCat.get(wk); const tot = [...wm.values()].reduce((a, b) => a + b, 0);
    L.push(`| ${wk} | ${cats.map(c => wm.get(c) || '-').join(' | ')} | ${tot} |`);
  }
  const seaTot = [...seasonCat.values()].reduce((a, b) => a + b, 0);
  L.push(`| **季累计** | ${cats.map(c => `**${seasonCat.get(c)}**`).join(' | ')} | **${seaTot}** |`);
  L.push('');
  L.push(`**结构占比**：${cats.map(c => `${c} ${(seasonCat.get(c) / seaTot * 100).toFixed(0)}%`).join('，')}`);
  L.push('');
  L.push(`> 使用方式：对照商品企划的目标结构，缺什么品类下周补什么；结合销售 TOP（另见销售数据报表）调整。`);
}
L.push('');

L.push(`## 五、🧹 数据完整性稽核（补数清单）`);
L.push('');
L.push(`| 检查项 | 全量缺失 | 近30天新建缺失 | 会议要求 |`);
L.push(`|---|---:|---:|---|`);
L.push(`| 款名（设计元素+领型/袖型+廓形+品类） | ${fmtN(missingName.length)} (${(missingName.length / rows.length * 100).toFixed(0)}%) | ${fmtN(recentMissingName.length)}/${fmtN(recent.length)} | 必填 |`);
L.push(`| 波段（如 2027春一波） | ${fmtN(missingBand.length)} (${(missingBand.length / rows.length * 100).toFixed(0)}%) | ${fmtN(recentMissingBand.length)}/${fmtN(recent.length)} | 必填 |`);
L.push(`| 波段填了 C1/C2 类未规范编码 | - | ${fmtN(bandAnomaly.length)} | 改用"2027春一波"式 |`);
L.push(`| 预计上新时间 expected_new_date | 字段存在，抽查≈0 填充（列表接口不含，需详情回捞核对） | - | 必填，AI 排序核心 |`);
L.push(`| 版次/季节/实际上新 | 系统字段已具备（edition_number/season_id/actual_new_date） | - | 必填 |`);
L.push('');
if (recentMissingName.length) {
  L.push(`<details><summary>近30天款名缺失名单（前30，点开）</summary>`);
  L.push('');
  L.push(recentMissingName.slice(0, 30).map(r => `- ${r.template_no}（${r.cat_name || '?'}，${r.created_at?.slice(0, 10)}，${r.template_status_name}）`).join('\n'));
  L.push('');
  L.push(`</details>`);
  L.push('');
}
if (recentMissingBand.length) {
  L.push(`<details><summary>近30天波段缺失名单（前30，点开）</summary>`);
  L.push('');
  L.push(recentMissingBand.slice(0, 30).map(r => `- ${r.template_no} ${r.template_name || '(款名空)'}`).join('\n'));
  L.push('');
  L.push(`</details>`);
  L.push('');
}

L.push(`## 六、🔁 环节流转（对比上一快照）`);
L.push('');
const prevDate = argOf('--prev-date', null);
let prev = null;
if (prevDate) prev = readSnapshot(prevDate);
if (prev) {
  const prevPool = {};
  for (const r of prev.list) { const st = r.template_status_name || '未知'; prevPool[st] = (prevPool[st] || 0) + 1; }
  L.push(`对比 ${prevDate}/${slot}（${fmtN(prev.list.length)} 款）：`);
  L.push('');
  L.push(`| 环节 | 上期 | 本期 | 变化 |`);
  L.push(`|---|---:|---:|---:|`);
  for (const st of STEP_ORDER) { const a = prevPool[st] || 0, b = (pool[st] || []).length; const d = b - a; if (a || b) L.push(`| ${st} | ${fmtN(a)} | ${fmtN(b)} | ${d > 0 ? '+' : ''}${d} |`); }
} else {
  L.push(`未指定 --prev-date，跳过环比。（可传 2026-10-09，该日有上一份全量快照）`);
}
L.push('');
L.push(`---`);
L.push(`### 附：会议规则备忘（本日报执行口径）`);
L.push(`- 面辅料 ${RULES.fabircWaitDays} 天内齐 → 打板 ${RULES.patternDays} 天内 → 车板 ${RULES.sewingDays} 天内 → 攒 ${RULES.reviewTriggerCount} 个即可审版（周审兜底）→ 审过 ${RULES.orderDays} 天内下单，滞留 ${RULES.stayWarnDays} 天必处理`);
L.push(`- 审版完成=确定马上下单（应清空）；待下单=审过观望；废版必须按五类原因写备注（雷同/滞销元素/价格带/搭配性/风格偏离）`);
L.push(`- 数据未补齐前：排序退化为"环节+新鲜度"；废版原因分析、版型分析、天气×厚度校验暂缺前置数据`);

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, L.join('\n'));

// 控制台摘要
const summary = { date: today, total: rows.length, pool: Object.fromEntries(STEP_ORDER.map(s => [s, (pool[s] || []).length])), warns: warns.length, warnsHigh: warns.filter(w => w.lvl === '高').length, reviewReady: reviewCnt, reviewDone: reviewDone.length, scrapRate: +scrapRate.toFixed(1), missingName: missingName.length, missingBand: missingBand.length, out: path.relative(ROOT, OUT) };
console.log(JSON.stringify(summary, null, 2));
