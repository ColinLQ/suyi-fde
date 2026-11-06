#!/usr/bin/env node
// cdp-eval.mjs — 通用页面执行工具（2026-11-05 V1.8 新增；chrome-devtools MCP 移除后，兜底B/登录排查的"AI之眼"）
// 场景：直连采集整系统失败走 references/采集兜底.md 附B（浏览器UI采集）时，AI 用本脚本看页面、取DOM、
//       驱动翻页等只读操作；登录异常排查同理。每步"脚本执行→AI读结果→下一步"，与原 MCP 交互等价。
// 用法：
//   node scripts/cdp-eval.mjs --system yizhe|duoke --js '<JS表达式>'          # 对该系统标签页求值
//   node scripts/cdp-eval.mjs --system yizhe --url 'https://...' [--wait 3000] # 先导航到指定URL再求值
//   node scripts/cdp-eval.mjs --system yizhe --text                            # 求值结果为文本时直接打印（默认）
//   node scripts/cdp-eval.mjs --system yizhe --out <文件>                      # 大结果落文件（数据根目录 out/ 或绝对路径）
//   node scripts/cdp-eval.mjs --list                                          # 列出采集窗口所有标签页
// 表达式约定：须自带 JSON.stringify(...) 承载结构化结果；纯字符串直接返回。
// 只读红线（铁律5）：本工具可用于只读查询与翻页驱动；保存/删除/导出/提交类写操作一律禁止，
// 「导出」按钮未获用户明确放开前禁止点击。AI 责任自负，工具不拦截。
import path from 'node:path';
import os from 'node:os';
import { pathToFileURL } from 'node:url';
import { getCollectorWindow } from './bit.mjs';
import { Cdp, listTabs } from './cdp.mjs';

const argv = process.argv.slice(2);
const getArg = k => { const i = argv.indexOf(`--${k}`); return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : null; };

const HOSTS = { yizhe: 'scm.yizheyun.com', duoke: 'air.duoke.net' };

async function main() {
  if (argv.includes('--list')) {
    const win = await getCollectorWindow({ open: true });
    const tabs = await listTabs(win.http);
    tabs.forEach((t, i) => console.log(`${i + 1}. [${t.type}] ${t.title?.slice(0, 40)} ${t.url}`));
    console.log(JSON.stringify({ ok: true, window: win.http, tabs: tabs.length }));
    return;
  }
  const sysKey = getArg('system');
  const host = sysKey && HOSTS[sysKey];
  if (!host) { console.error('用法：--system yizhe|duoke （或 --list 查看标签页）；--js <表达式> [--url <导航目标>] [--out <文件>]'); process.exit(2); }
  const js = getArg('js');
  if (!js) { console.error('缺少 --js <JS表达式>（结构化结果请自带 JSON.stringify）'); process.exit(2); }
  const navUrl = getArg('url');
  const waitMs = Number(getArg('wait') || 3000);
  const outFile = getArg('out');

  const win = await getCollectorWindow({ open: true });
  const tabs = await listTabs(win.http);
  let tab = tabs.find(t => (t.url || '').includes(host));
  if (!tab) { console.error(`采集窗口中无 ${host} 标签页，请先跑 check-login.mjs 或手动打开`); process.exit(2); }

  const c = new Cdp(tab.webSocketDebuggerUrl);
  try {
    await c.attach();
    if (navUrl) {
      await c.send('Page.navigate', { url: navUrl }).catch(e => { console.error(`导航失败：${e.message}`); process.exit(2); });
      await new Promise(r => setTimeout(r, waitMs));
    }
    const val = await c.evalExpr(js);
    const text = typeof val === 'string' ? val : JSON.stringify(val, null, 2);
    if (outFile) {
      const p = path.isAbsolute(outFile) ? outFile : path.join(process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'), 'out', outFile);
      const { mkdirSync, writeFileSync } = await import('node:fs');
      mkdirSync(path.dirname(p), { recursive: true });
      writeFileSync(p, text);
      console.log(JSON.stringify({ ok: true, saved: p, bytes: text.length, url: tab.url }));
    } else {
      console.log(text);
      console.log(JSON.stringify({ ok: true, url: tab.url }));
    }
  } finally { c.close(); }
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) await main().catch(e => { console.error(e.message); process.exit(2); });
