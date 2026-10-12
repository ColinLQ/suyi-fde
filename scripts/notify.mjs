#!/usr/bin/env node
// notify.mjs — 企微推送（双通道，2026-10-08 V1.4 改造）
// 通道A（默认）：WorkBuddy 内置企微（wecom-cli aibot）——向授权人推送，无需 webhook 配置
// 通道B（可选）：企微群机器人 webhook——读 config/wecom-webhook.local.json，未配置自动跳过
// 推送内容：企微版日报总览 + 预警专项（授权人）；五部门分版（配置了对应群时走webhook）
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const run = promisify(execFile);

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i++) {
  const t = argv[i].replace(/^--/, '');
  if (t.includes('=')) args[t] = t.split('=')[1];
  else if (argv[i + 1] && !argv[i + 1].startsWith('--')) { args[t] = argv[i + 1]; i++; }
  else args[t] = true;
}
const date = args.date || new Date(Date.now() - new Date.getTimezoneOffset() * 60000).toISOString().slice(0, 10); // 本地日期
const outDir = path.join(root, 'out');
const read = f => { const p = path.join(outDir, f); return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null; };

// —— 通道A：wecom-cli aibot 发授权人 ——
// whoami 输出含安全提示噪音，授权人ID以 "ID":"wo..." 模式提取；发送成功以退出码+errcode双重判定
async function pushAibot(title, text) {
  const content = `**${title}**\n${text}`.slice(0, 20000);
  try {
    const who = await run('wecom-cli', ['identity', 'whoami'], { timeout: 15000 });
    // whoami 输出为非标准JSON（身份嵌在提示文本里）：授权真人ID=「wo」前缀、紧跟「授权真人用户身份」段；机器人是「aib」前缀，不能用作chat_id
    const m = (who.stdout || '').match(/授权真人用户身份[\s\S]{0,200}?ID[：:]\s*(wo[\w-]+)/) || (who.stdout || '').match(/"(wo[\w-]+)"/);
    if (!m) throw new Error('未解析到授权人ID');
    const payload = JSON.stringify({ chat_id: m[1], msg_type: 'markdown', markdown: { content } });
    const r = await run('wecom-cli', ['message', 'aibot', 'send', '--json', payload], { timeout: 20000, maxBuffer: 1024 * 1024 });
    if (/"errcode"\s*:\s*[1-9]/.test(r.stdout || '')) throw new Error('接口返回业务错误: ' + (r.stdout || '').slice(0, 120));
    console.log(`[notify][aibot] ✅ 已推送：${title}`);
    return true;
  } catch (e) {
    console.log(`[notify][aibot] ❌ ${title}：${String(e.message || e).slice(0, 160)}`);
    return false;
  }
}

// —— 通道B：webhook 群机器人（保留原逻辑，配置了才生效） ——
const cfgPath = path.join(root, 'config', 'wecom-webhook.local.json');
const groups = fs.existsSync(cfgPath) ? (JSON.parse(fs.readFileSync(cfgPath, 'utf8')).groups || {}) : {};
const url = g => groups[g] || groups.default;
async function pushWebhook(group, text) {
  const u = url(group);
  if (!u) return;
  try {
    const res = await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ msgtype: 'markdown', markdown: { content: text.slice(0, 4000) } }) });
    const j = await res.json().catch(() => ({}));
    console.log(`[notify][webhook] ${group} 群：${j.errcode === 0 ? '✅ 已推送' : '❌ ' + JSON.stringify(j)}`);
  } catch (e) { console.log(`[notify][webhook] ${group} 群：❌ ${String(e.message || e).slice(0, 120)}`); }
}

// —— 主流程 ——
const boss = read(`日报-${date}-企微版.txt`);
if (boss) await pushAibot(`经营日报 ${date}`, boss);
else console.log(`[notify] 无 日报-${date}-企微版.txt（先跑 report-daily.mjs）`);

// 预警专项：⛔超卖与🔴紧急（取补货深度分析前12行，避免总览折叠漏看）
const deep = read(`补货深度分析-${date}.md`);
if (deep) {
  const rows = deep.split('\n').filter(l => /^\|\s*(⛔|🔴)/.test(l)).slice(0, 12);
  if (rows.length) {
    const cells = r => r.split('|').map(x => x.trim()).filter(Boolean);
    const alertText = ['需处理预警（按净缺口排序）：', '', '| 级别 | 款号 | 品名 | 库存 | 净补 | 动作 |', '|---|---|---|---|---|---|',
      ...rows.map(r => { const c = cells(r); return `| ${c.slice(0, 6).join(' | ')} |`; })].join('\n');
    await pushAibot(`补货/超卖预警 ${date}`, alertText);
  }
}

// webhook 通道：分部门群（未配置自动跳过，无提示噪音）
for (const g of ['研发', '生产', '销售', '财务', '仓库']) {
  const t = read(`日报-${date}-${g}版.txt`);
  if (t && url(g)) await pushWebhook(g, t);
}
console.log('[notify] 推送完成');
