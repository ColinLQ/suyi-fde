#!/usr/bin/env node
// capture-pages.mjs — CDP翻页收割器（零依赖；浏览器UI兜底采集时使用）。铁律①修订附件（2026-09-24用户批准）。
// 边界（与SKILL.md一致，违反即违规）：
//   ① 仅使用 CDP 的 DOM域（定位元素/取坐标）、Input域（真实点击/按键）、Network域（监听响应并落盘）
//   ② 页内脚本已于2026-09-25用户批准解禁（Runtime.evaluate等可用于翻页驱动/数据解析），本脚本沿用DOM坐标点击即可
//   ③ 只读——仅点击分页/筛选控件，永不点击保存/删除/导出类按钮（无论UI点击还是脚本执行）
//   ④ 本脚本不向源系统发起任何HTTP请求——数据全部来自本浏览器 Network 事件的响应体（浏览器是唯一数据通道）
// 用法：node scripts/capture-pages.mjs --api <接口URL片段> --file <输出jsonl路径> --list-path <行数组路径，如 data.list>
//        [--match-url <当前标签页URL片段>] [--max-pages 50] [--port 9222] [--interval 1500] [--selector <css选择器>]
// 前置：Chrome 以 --remote-debugging-port=<port> 启动（与MCP同一浏览器）；第1页由智能体收割后调用本脚本续采2..N页
// 输出：最后一行打印JSON摘要 {"ok":true,"pages":N,"rows":M,"reason":"..."} 供智能体核对；失败退出码1，智能体回落纯MCP逐页收割
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i++) {
  const t = argv[i].replace(/^--/, '');
  if (t.includes('=')) { const [k, v] = t.split('='); args[k] = v; }
  else if (argv[i + 1] && !argv[i + 1].startsWith('--')) { args[t] = argv[i + 1]; i++; }
  else args[t] = true;
}
const api = args.api, listPath = args['list-path'] || 'data.list';
const maxPages = Number(args['max-pages'] || 50);
const port = Number(args.port || 9222);
const interval = Number(args.interval || 1500);
const matchUrl = args['match-url'] || '';
const selectors = args.selector ? [args.selector] : [
  '.ant-pagination-next:not(.ant-pagination-disabled)',
  '.ant-pagination li[title="下一页"]:not(.ant-pagination-disabled)',
  'li.next:not(.ant-pagination-disabled)',
  'button[aria-label="next"]:not(:disabled)',
];
if (!args.api || !args.file) { console.error('[capture-pages] 缺少 --api 或 --file 参数'); process.exit(2); }
const outPath = path.isAbsolute(args.file) ? args.file : path.join(root, args.file);
fs.mkdirSync(path.dirname(outPath), { recursive: true });

// —— 连接调试端口，定位目标标签页 ——
let page;
try {
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  page = tabs.filter(p => p.type === 'page' && (!matchUrl || p.url.includes(matchUrl)))[0];
} catch (e) {
  console.error(JSON.stringify({ ok: false, error: `连不上调试端口 ${port}（Chrome需以 --remote-debugging-port=${port} 启动）：${e.message}` }));
  process.exit(1);
}
if (!page) { console.error(JSON.stringify({ ok: false, error: `找不到匹配标签页（match-url=${matchUrl || '任意'}）` })); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('CDP WebSocket连接失败')); });

let seq = 0; const pending = new Map();
let onEvent = () => {};
ws.onmessage = m => {
  const d = JSON.parse(String(m.data));
  if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.rej(new Error(d.error.message)) : p.res(d.result); }
  else onEvent(d);
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params }));
});
const sleep = ms => new Promise(r => setTimeout(r, ms));

// —— Network事件登记：responseReceived记URL，loadingFinished入完成队列 ——
const respUrl = new Map(); const finished = []; const harvested = new Set();
let waiter = null;
onEvent = d => {
  if (d.method === 'Network.responseReceived') respUrl.set(d.params.requestId, d.params.response.url);
  else if (d.method === 'Network.loadingFinished') { finished.push(d.params.requestId); if (waiter) { waiter(); waiter = null; } }
};
const waitForTarget = async timeoutMs => {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const rid = finished.find(r => !harvested.has(r) && (respUrl.get(r) || '').includes(api));
    if (rid) return rid;
    if (Date.now() > deadline) return null;
    await new Promise(r => { waiter = r; setTimeout(r, 250); });
  }
};
const dig = (o, p) => p.split('.').reduce((a, k) => (a == null ? a : a[k]), o);

// —— 定位"下一页"按钮中心坐标（DOM域，只读查询） ——
const findNext = async () => {
  const { root: doc } = await send('DOM.getDocument', { depth: 0 });
  for (const sel of selectors) {
    const { nodeId } = await send('DOM.querySelector', { nodeId: doc.nodeId, selector: sel });
    if (!nodeId) continue;
    await send('DOM.scrollIntoViewIfNeeded', { nodeId }).catch(() => {});
    const box = await send('DOM.getBoxModel', { nodeId }).catch(() => null);
    if (!box || !box.model) continue;
    const c = box.model.content || (box.model.quads && box.model.quads[0]);
    if (!c || c.length < 8) continue;
    return { x: Math.round((c[0] + c[2] + c[4] + c[6]) / 4), y: Math.round((c[1] + c[3] + c[5] + c[7]) / 4) };
  }
  return null;
};
const click = (x, y) => Promise.all([
  send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 }),
  send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 1, clickCount: 1 }),
]).then(() => {});

// —— 主循环：点下一页 → 等目标响应 → 落盘追加 ——
await send('Network.enable');
await send('DOM.enable');
let pages = 0, rows = 0, reason = 'no_next_button';
try {
  while (pages < maxPages) {
    const btn = await findNext();
    if (!btn) { reason = pages === 0 ? 'single_page_or_no_button' : 'no_next_button'; break; }
    await click(btn.x, btn.y);
    const rid = await waitForTarget(20000);
    if (!rid) { reason = pages === 0 ? 'no_response_first_click' : 'timeout_no_response'; break; }
    harvested.add(rid);
    let body = null;
    for (let t = 0; t < 2 && body == null; t++) {
      const r = await send('Network.getResponseBody', { requestId: rid }).catch(() => null);
      if (r) body = r.base64 ? Buffer.from(r.body, 'base64').toString('utf8') : r.body;
      else await sleep(300);
    }
    if (body == null) { reason = 'get_body_failed'; break; }
    const arr = dig(JSON.parse(body), listPath);
    if (!Array.isArray(arr) || arr.length === 0) { reason = 'empty_page_tail'; break; }
    fs.appendFileSync(outPath, arr.map(r => JSON.stringify(r)).join('\n') + '\n');
    pages++; rows += arr.length;
    await sleep(interval); // 限速：对源系统友好
  }
  console.log(JSON.stringify({ ok: true, pages, rows, reason, file: outPath }));
} catch (e) {
  console.log(JSON.stringify({ ok: false, pages, rows, error: e.message, file: outPath }));
  process.exitCode = 1;
} finally {
  try { ws.close(); } catch {}
}
