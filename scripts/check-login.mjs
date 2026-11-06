#!/usr/bin/env node
// check-login.mjs — 第0步登录态硬校验（V1.9.2：页面跳转 + 浏览器内API调用结果判定；不读 storage/IndexedDB）
// 判定信号（2026-11-05 用户拍板"看页面跳登录页 / 在浏览器里调API判断"）：
//   ① 登录页跳转：导航后 URL 落在登录页（如 scm.yizheyun.com/user/login、air.duoke.net/login）或出现可见密码框 → 未登录。
//      注意衣者/多客均为 SPA：未登录访问业务页会**先短暂呈现业务页再客户端跳转登录页**——必须等跳转完成，抢跑会误判（V1.8.1 教训）。
//   ② 浏览器内 API 结果（CDP Network 只读监听）：页面打开时浏览器自己会带凭据调业务 API，读首个响应体判定：
//      衣者 api.yizheyun.com：code=200 → 已登录；code=201 → 未登录/凭据失效（被顶号同型）
//      多客 api.duoke.net：err=0 → 已登录；err≠0 → 未登录
//   ③ 业务页稳定不跳转：加载完成后在业务页 URL 稳定 ≥8 秒未跳登录页 → 已登录（SPA 仅在未鉴权时跳登录）。
//   判定优先级：登录页/密码框（未登录） > API结果 > 稳定不跳转；超时未见任何明确信号 → 按未登录（宁可误杀不漏放，配合铁律3硬停）。
// 退出码：两系统均登录=0；任一未登录=1；浏览器/网络异常=2。
// 用法：node scripts/check-login.mjs [--timeout 15000] [--json]
// 末行始终输出 JSON：{ ok, yizhe:{login,url,evidence}, duoke:{login,url,evidence}, window:{id,http} }
// 只读红线：仅开页/读URL/读DOM密码框/监听浏览器自身请求，不点击、不填表、不主动构造任何 API 调用。

import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { pathToFileURL } from 'node:url';
import { getCollectorWindow } from './bit.mjs';
import { Cdp, listTabs, newTab } from './cdp.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const argv = process.argv.slice(2);
const getArg = k => { const i = argv.indexOf(`--${k}`); return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : null; };
const timeoutMs = Number(getArg('timeout') || 15000);
const quietJson = argv.includes('--json');

// 登录事件记录（与登录阻断流程配套：铁律3要求追加 state/login-events.jsonl）
export function logLoginEvent(events) {
  try {
    const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data');
    fs.mkdirSync(path.join(dataHome, 'state'), { recursive: true });
    fs.appendFileSync(path.join(dataHome, 'state', 'login-events.jsonl'),
      events.map(e => JSON.stringify({ ts: new Date().toISOString(), ...e })).join('\n') + '\n');
  } catch {}
}

const SYSTEMS = [
  { key: 'yizhe', name: '衣者', host: 'scm.yizheyun.com', loginPath: '/user/login', apiHost: 'api.yizheyun.com',
    seed: 'https://scm.yizheyun.com/sample-management/list' },
  { key: 'duoke', name: '多客', host: 'air.duoke.net', loginPath: '/login', apiHost: 'api.duoke.net',
    seed: 'https://air.duoke.net/goods/list' },
];

const PROBE_EXPR = `JSON.stringify({url:location.href,pw:(()=>{const e=document.querySelector('input[type=password]');return !!(e&&e.offsetParent!==null);})(),ready:document.readyState})`;
const STABLE_BUSINESS_MS = 8000; // 业务页稳定多久视为"未跳登录"信号

// 从 API 响应体提取登录判定（只认 code/err 字段；其他业务错误码不作为登录依据）
function apiVerdictFrom(sysKey, bodyText) {
  try {
    const j = JSON.parse(bodyText);
    if (sysKey === 'yizhe') {
      const code = String(j.code);
      if (code === '200') return { verdict: 'ok', msg: '衣者业务API code=200' };
      if (code === '201') return { verdict: 'auth-fail', msg: '衣者业务API code=201（未登录/凭据失效）' };
    } else {
      const err = Number(j.err);
      if (err === 0) return { verdict: 'ok', msg: '多客业务API err=0' };
      if (err !== 0 && !Number.isNaN(err)) return { verdict: 'auth-fail', msg: `多客业务API err=${err}（未登录/凭据失效）` };
    }
  } catch {}
  return null;
}

async function checkSystem(httpBase, tabs, sys, deadline) {
  let tab = tabs.find(t => (t.url || '').includes(sys.host));
  if (!tab) {
    tab = await newTab(httpBase, sys.seed);
    if (!tab) return { login: null, url: '', evidence: '无法新建标签页（/json/new 失败）' };
    await new Promise(r => setTimeout(r, 800));
  }
  const c = new Cdp(tab.webSocketDebuggerUrl);
  const apiRequests = new Map(); // requestId -> url（浏览器自己发的 api 请求）
  let apiVerdict = null;         // { verdict, msg } 一旦得出不再覆盖
  let bodyAttempts = 0;          // 最多读5个响应体，够出判定即止
  c.onEvent = d => {
    try {
      if (d.method === 'Network.responseReceived') {
        const r = d.params.response;
        if (r.url.includes(sys.apiHost)) apiRequests.set(d.params.requestId, r.url);
      } else if (d.method === 'Network.loadingFinished' && apiRequests.has(d.params.requestId) && !apiVerdict && bodyAttempts < 5) {
        bodyAttempts++;
        c.send('Network.getResponseBody', { requestId: d.params.requestId })
          .then(rb => {
            const v = apiVerdictFrom(sys.key, rb?.body || '');
            if (v && !apiVerdict) apiVerdict = v;
          }).catch(() => {});
      }
    } catch {}
  };
  try {
    await c.attach();
    await c.send('Network.enable').catch(() => {});
    await c.send('Page.navigate', { url: sys.seed }).catch(() => {});
    let lastUrl = '', stableSince = 0, last = null;
    while (Date.now() < deadline) {
      let st = null;
      try { st = JSON.parse(await c.evalExpr(PROBE_EXPR)); } catch {}
      if (st) {
        last = st;
        lastUrl = st.url || lastUrl;
        const u = lastUrl.startsWith('http') ? new URL(lastUrl) : null;
        // ① 登录页跳转（最高优先级：无论API说了什么，被踢回登录页就是未登录）
        const onLogin = (u && u.hostname === sys.host && u.pathname.includes(sys.loginPath)) || st.pw === true;
        if (onLogin) return { login: false, url: lastUrl, evidence: st.pw && !(u && u.pathname.includes(sys.loginPath)) ? '检测到登录表单（可见密码框）' : 'URL跳转到登录页' };
        // ② 浏览器内 API 判定结果
        if (apiVerdict) {
          if (apiVerdict.verdict === 'ok') return { login: true, url: lastUrl, evidence: `${apiVerdict.msg}（浏览器内实测）` };
          if (apiVerdict.verdict === 'auth-fail') return { login: false, url: lastUrl, evidence: apiVerdict.msg };
        }
        // ③ 业务页稳定不跳转（SPA 仅未鉴权时跳登录页；complete 后稳定8秒=已登录）
        if (st.ready === 'complete') {
          if (stableSince === 0 || !lastUrl || lastUrl !== (last._stableUrl || '')) { stableSince = Date.now(); last._stableUrl = lastUrl; }
          if (lastUrl && Date.now() - stableSince >= STABLE_BUSINESS_MS) {
            return { login: true, url: lastUrl, evidence: `业务页稳定${STABLE_BUSINESS_MS / 1000}秒未跳登录页（无API明确信号）` };
          }
        }
      }
      await new Promise(r => setTimeout(r, 500));
    }
    return { login: false, url: lastUrl, evidence: `等待${timeoutMs}ms无明确信号（超时按未登录处理）` };
  } catch (e) {
    return { login: null, url: '', evidence: `CDP校验异常：${e.message}` };
  } finally { c.close(); }
}

async function main() {
  const out = { ok: false, yizhe: null, duoke: null, window: null, ts: new Date().toISOString() };
  try {
    const win = await getCollectorWindow({ open: true }); // 幂等拉起
    out.window = { id: win.id, name: win.name, http: win.http };
    if (!quietJson) console.log(`[check-login] 采集窗口 ${win.name} 已在线（CDP ${win.http}）`);

    const tabs = await listTabs(win.http);
    const deadline = Date.now() + timeoutMs;
    const results = await Promise.all(SYSTEMS.map(s => checkSystem(win.http, tabs, s, deadline)));
    for (let i = 0; i < SYSTEMS.length; i++) {
      out[SYSTEMS[i].key] = results[i];
      if (!quietJson) {
        const r = results[i];
        console.log(`  ${SYSTEMS[i].name}：${r.login === true ? '✓ 已登录' : r.login === false ? '✗ 未登录' : '? 未知'}（${r.evidence}）`);
      }
    }
    const ok = out.yizhe?.login === true && out.duoke?.login === true;
    out.ok = ok;
    // 未登录事件落盘（登录阻断流程素材；已登录不记）
    const fails = SYSTEMS.filter((s, i) => results[i].login !== true).map(s => {
      const r = out[s.key];
      return { system: s.name, login: r.login, reason: r.evidence, url: r.url };
    });
    if (fails.length) logLoginEvent(fails.map(f => ({ ...f, trigger: 'check-login' })));
    console.log(JSON.stringify({ ok, yizhe: out.yizhe, duoke: out.duoke, window: out.window }));
    process.exit(ok ? 0 : fails.some(f => f.login === false) ? 1 : 2);
  } catch (e) {
    console.error(`[check-login] ${e.message}`);
    console.log(JSON.stringify({ ok: false, error: e.message, window: out.window }));
    process.exit(2);
  }
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) await main();
