#!/usr/bin/env node
// bit.mjs — 比特浏览器采集窗口客户端（2026-11-05 V1.8 chrome-devtools MCP 移除后新增）
// 职责：定位/拉起专用采集窗口，返回其 CDP 调试端口。全零依赖（Node 22 内置 fetch/WebSocket）。
// 窗口定位优先级：环境变量 SCM_BIT_WINDOW_ID → 按 name=suyi 精确匹配 → 报错引导创建。
// Local API 地址：SCM_BIT_API（默认 http://127.0.0.1:54345），鉴权头 SCM_BIT_API_KEY 或配置文件 ~/.workbuddy/mcp.json 的 bitbrowser.headers.x-api-key。
// 用法（供其他脚本 import）：
//   import { getCollectorWindow } from './bit.mjs';
//   const win = await getCollectorWindow({ open: true });  // { id, name, http, ws, pid } 或抛错
// 也可直接命令行自检：node scripts/bit.mjs [--no-open] [--json]
//   --no-open：只找不拉起（窗口未开时返回 found:false）
// 输出（--json 或默认末行）：JSON { ok, found, window: {id,name,http,ws}, bitApi }
// 铁律不变：只调用 Local API 的只读接口与 browser/open（幂等，已开则原样返回端口），不触碰任何写接口。

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const BIT_API = process.env.SCM_BIT_API || 'http://127.0.0.1:54345';
const WINDOW_NAME = 'suyi';

function apiKey() {
  if (process.env.SCM_BIT_API_KEY) return process.env.SCM_BIT_API_KEY;
  try { // 从 WorkBuddy mcp.json 读 bitbrowser 鉴权头，避免凭据再落一份
    const cfg = JSON.parse(fs.readFileSync(path.join(os.homedir(), '.workbuddy', 'mcp.json'), 'utf8'));
    const b = cfg.mcpServers?.bitbrowser || cfg.bitbrowser;
    return b?.headers?.['x-api-key'] || null;
  } catch { return null; }
}

async function bitPost(apiPath, body = {}) {
  const key = apiKey();
  const headers = { 'Content-Type': 'application/json' };
  if (key) headers['x-api-key'] = key;
  const res = await fetch(`${BIT_API}${apiPath}`, {
    method: 'POST', headers, body: JSON.stringify(body),
    signal: AbortSignal.timeout(90000), // browser/open 冷启动可能较慢
  });
  if (!res.ok) throw new Error(`比特Local API ${apiPath} HTTP ${res.status}（客户端未运行？默认地址 ${BIT_API}）`);
  const j = await res.json();
  if (!j.success) throw new Error(`比特Local API ${apiPath} 失败：${j.msg || JSON.stringify(j).slice(0, 200)}`);
  return j.data;
}

// 定位采集窗口：环境变量指定 id 优先，否则按名称精确匹配
async function findWindow() {
  const envId = process.env.SCM_BIT_WINDOW_ID;
  if (envId) {
    const d = await bitPost('/browser/detail', { id: envId });
    return { id: d.id, name: d.name };
  }
  const d = await bitPost('/browser/list', { page: 0, pageSize: 100, name: WINDOW_NAME });
  const hit = (d.list || []).find(b => b.name === WINDOW_NAME && !b.isDelete);
  return hit ? { id: hit.id, name: hit.name } : null;
}

/**
 * 获取采集窗口的 CDP 端点。
 * @param {object} opts
 * @param {boolean} opts.open 窗口未开时是否拉起（默认 true；open 幂等——已开窗口原样返回现有端口）
 * @returns {Promise<{id:string,name:string,http:string,ws:string,pid?:number}>}
 */
export async function getCollectorWindow(opts = {}) {
  const open = opts.open !== false;
  let win = await findWindow();
  if (!win) {
    throw new Error(`比特浏览器中未找到名为「${WINDOW_NAME}」的采集窗口。请在比特浏览器客户端创建（或由智能体用 browser-create 创建）：无代理直连（noproxy），并登录衣者+多客两系统。也可用环境变量 SCM_BIT_WINDOW_ID 指定既有窗口 id。`);
  }
  // 已开窗口直接拿端口（browser/ports：{窗口id: {ws, http,...}}），避免重复 open 的等待
  try {
    const ports = await bitPost('/browser/ports');
    const p = ports?.[win.id];
    if (p?.http) {
      return { id: win.id, name: win.name, http: String(p.http).replace(/^https?:\/\//, ''), ws: p.ws || '', ...(p.pid ? { pid: p.pid } : {}) };
    }
  } catch {}
  if (!open) return null; // --no-open 模式：窗口未运行
  const d = await bitPost('/browser/open', { id: win.id });
  return { id: win.id, name: win.name || d.name, http: String(d.http).replace(/^https?:\/\//, ''), ws: d.ws, ...(d.pid ? { pid: d.pid } : {}) };
}

// —— 命令行自检入口 ——
const isMain = process.argv[1] && import.meta.url === (await import('node:url')).pathToFileURL(process.argv[1]).href;
if (isMain) {
  const argv = process.argv.slice(2);
  const noOpen = argv.includes('--no-open');
  try {
    const win = await getCollectorWindow({ open: !noOpen });
    console.log(JSON.stringify({ ok: true, found: true, window: win, bitApi: BIT_API }));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, found: false, error: e.message, bitApi: BIT_API }));
    process.exit(1);
  }
}
