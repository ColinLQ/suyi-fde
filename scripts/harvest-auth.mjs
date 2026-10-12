#!/usr/bin/env node
// harvest-auth.mjs — 直连采集凭据收割器（2026-09-24用户批准解除直连禁令后新增；2026-09-25补端口自动发现；
// 2026-09-25用户批准解除代码注入禁令，收割改为 Runtime.evaluate 直读 localStorage 快路径优先）。
// 经CDP附加到采集浏览器（chrome-devtools MCP 拉起的浏览器或专用Chrome均可）：
//   快路径：Runtime.evaluate 直读页面 localStorage/sessionStorage，瞬时取得凭据；
//   回落：Network域被动监听浏览器自己发出的请求 + Page域导航触发（storage为空/结构变化时）。
// 端口发现：指定端口可达且已开两系统页面 → 直接采用、跳过扫描（日常单浏览器场景零浪费）；
// 否则优先指定端口（默认9222），不可达则枚举本机监听端口逐个探测 /json/version（MCP自行拉起的浏览器
// 常为随机端口，由此覆盖）。多浏览器并存时优先选**已打开目标系统页面**的那个；仅一个端口且无页面时自动新开标签页。
// 收割：衣者 token/cid/uid/plate_type/v/cv、多客 key/lang/version。
// 只读红线不变：不点击保存/删除/导出，不执行任何写操作脚本；凭据只写入本地 state/auth.json（不入交付物、不外传）；
// 不获取账号密码、不自动登录、不绕过认证。
// 用法：node scripts/harvest-auth.mjs [--port 9222] [--timeout 8000] [--check]
//       node scripts/harvest-auth.mjs --import <文件或目录>   # 兜底：导入MCP get_network_request(requestFilePath=…)保存的请求文件
//   --check：收割成功后各发一个只读探测请求验证登录态（衣者 get_user_info / 多客 admin_get_staff_list）
// 输出：末行打印JSON摘要；两系统均未收割到凭据时退出码1
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { pathToFileURL } from 'node:url';
const run = promisify(execFile);

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i++) {
  const t = argv[i].replace(/^--/, '');
  if (t.includes('=')) { const [k, v] = t.split('='); args[k] = v; }
  else if (argv[i + 1] && !argv[i + 1].startsWith('--')) { args[t] = argv[i + 1]; i++; }
  else args[t] = true;
}
const port = Number(args.port || 9222);
const timeoutMs = Number(args.timeout || 8000);

// —— 两系统的收割规则（快路径=storage直读扫描；回落=从浏览器自然产生的请求中被动提取） ——
const SYSTEMS = {
  yizhe: {
    tabMatch: 'scm.yizheyun.com',
    seed: 'https://scm.yizheyun.com/sample-management/list',
    apiMatch: u => u.startsWith('https://api.yizheyun.com'),
    storageScan: dump => {
      let creds = null;
      const visit = s => {
        if (creds || typeof s !== 'string' || !s.includes('token')) return;
        try {
          const j = JSON.parse(s);
          if (j && typeof j === 'object' && j.token && j.cid != null && j.uid != null) {
            creds = { token: String(j.token), cid: j.cid, uid: j.uid, plate_type: j.plate_type || 'backend', v: j.v || '', cv: j.cv || '' };
          }
        } catch {}
      };
      Object.values(dump.ls || {}).forEach(visit);
      Object.values(dump.ss || {}).forEach(visit);
      return creds;
    },
    extract: async (cand, send) => {
      let body = cand.postData;
      if (body == null) body = (await send('Network.getRequestPostData', { requestId: cand.requestId }).catch(() => null))?.body || null;
      if (!body) return null;
      try {
        const j = JSON.parse(body);
        if (!j.token) return null;
        return { token: String(j.token), cid: j.cid, uid: j.uid, plate_type: j.plate_type || 'backend', v: j.v || '', cv: j.cv || '' };
      } catch { return null; }
    },
  },
  duoke: {
    tabMatch: 'air.duoke.net',
    seed: 'https://air.duoke.net/goods/list',
    apiMatch: u => u.startsWith('https://api.duoke.net') && u.includes('key='),
    storageScan: dump => {
      const m = JSON.stringify(dump).match(/(\d+_[0-9a-f]{16,64})/); // 多客key形态：{user_id}_{32位hash}
      return m ? { key: m[1], lang: 'chs', version: '' } : null;
    },
    extract: async cand => {
      const u = new URL(cand.url);
      const key = u.searchParams.get('key');
      if (!key) return null;
      return { key, lang: u.searchParams.get('lang') || 'chs', version: u.searchParams.get('version') || '' };
    },
  },
};

const sleep = ms => new Promise(r => setTimeout(r, ms));
const listTabs = async p => (await (await fetch(`http://127.0.0.1:${p}/json`)).json()).filter(t => t.type === 'page');
const openTab = async (p, url) => {
  const u = `http://127.0.0.1:${p}/json/new?${new URLSearchParams({ url })}`;
  for (const method of ['PUT', 'GET']) { // Chrome 111+ 要求 PUT，旧版 GET
    try { const r = await fetch(u, { method }); if (r.ok) return await r.json(); } catch {}
  }
  return null;
};

// —— DevTools 端口发现：指定端口优先，失败则枚举本机监听端口探测（覆盖MCP自启/随机端口的浏览器） ——
async function listeningPorts() {
  let out = '';
  try { out = (await run('netstat', ['-an'])).stdout || ''; } catch { return []; }
  let lines = out.split('\n').filter(l => /LISTEN/i.test(l));
  if (!lines.length) lines = out.split('\n').filter(l => /^\s*tcp/i.test(l)); // 状态词被本地化的兜底
  const ports = new Set();
  for (const line of lines) for (const tok of line.trim().split(/\s+/)) {
    const m = tok.match(/[:.](\d{2,5})$/); // 兼容 127.0.0.1:9222 / 127.0.0.1.9222 / *.9222 / [::1]:9222
    if (m) { const p = Number(m[1]); if (p > 0 && p < 65536) ports.add(p); }
  }
  return [...ports];
}
const probePort = async p => {
  try {
    const j = await (await fetch(`http://127.0.0.1:${p}/json/version`, { signal: AbortSignal.timeout(600) })).json();
    return j && (j.webSocketDebuggerUrl || j.Browser) ? p : null;
  } catch { return null; }
};
async function discoverPorts(hint) {
  const found = [];
  if (hint && await probePort(hint)) {
    // 快路径：hint端口已打开两系统页面 → 就是日常唯一的采集浏览器，直接采用、跳过全端口扫描（省netstat+逐端口探测）
    try {
      const tabs = await listTabs(hint);
      if (tabs.some(t => t.url.includes(SYSTEMS.yizhe.tabMatch)) && tabs.some(t => t.url.includes(SYSTEMS.duoke.tabMatch))) return [hint];
    } catch {}
    found.push(hint);
  }
  const cand = (await listeningPorts()).filter(p => p !== hint);
  for (let i = 0; i < cand.length; i += 50) {
    const res = await Promise.all(cand.slice(i, i + 50).map(probePort));
    found.push(...res.filter(Boolean));
  }
  return found;
}

async function harvestTab(tab, cfg) {
  let ws;
  try { ws = new WebSocket(tab.webSocketDebuggerUrl); await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('CDP WebSocket连接失败')); }); }
  catch (e) { return { ok: false, reason: e.message }; }

  let seq = 0; const pending = new Map(); let onEvent = () => {};
  ws.onmessage = m => {
    const d = JSON.parse(String(m.data));
    if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.rej(new Error(d.error.message)) : p.res(d.result); }
    else onEvent(d);
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params }));
  });

  // —— 快路径：Runtime.evaluate 直读页面storage（2026-09-25解除代码注入禁令后新增，瞬时完成） ——
  try {
    const r = await send('Runtime.evaluate', {
      expression: 'JSON.stringify({ls:{...localStorage},ss:{...sessionStorage}})',
      returnByValue: true,
    });
    if (r?.result?.value) {
      let dump = null; try { dump = JSON.parse(r.result.value); } catch {}
      const creds = dump && cfg.storageScan(dump);
      if (creds) { try { ws.close(); } catch {} return { ok: true, creds, via: 'storage直读' }; }
    }
  } catch {} // storage不可读/为空/结构变化 → 走网络监听回落

  const candidates = [];
  onEvent = d => {
    if (d.method === 'Network.requestWillBeSent') {
      const r = d.params.request;
      if (r.url.startsWith('https://api.yizheyun.com') || r.url.startsWith('https://api.duoke.net')) {
        candidates.push({ requestId: d.params.requestId, url: r.url, postData: r.postData });
      }
    }
  };
  try {
    await send('Network.enable');
    const deadline = Date.now() + timeoutMs;
    let creds = null;
    // 静默等待浏览器自己的请求（衣者有 get_red_num 轮询，多半等得到）；静默过半则重新导航强制触发
    while (!creds && Date.now() < deadline) {
      for (const c of candidates) { creds = await cfg.extract(c, send); if (creds) break; }
      if (creds) break;
      if (Date.now() > deadline - timeoutMs / 2) await send('Page.navigate', { url: cfg.seed }).catch(() => {});
      await sleep(300);
    }
    return creds ? { ok: true, creds } : { ok: false, reason: `等待${timeoutMs}ms未观测到带凭据的请求（大概率未登录）` };
  } finally {
    try { ws.close(); } catch {}
  }
}

// —— 单系统收割：在已发现的端口里找已打开该系统页面的浏览器；唯一端口且无页面时自动开标签页 ——
async function harvestSystem(sysKey, cfg, ports) {
  if (!ports.length) return { ok: false, reason: '未发现任何Chrome DevTools端口（浏览器未启动，或以pipe模式启动）——请让智能体用chrome-devtools MCP打开采集页面后重试；仍不可达则按SKILL第1步附A用 --import 导入请求文件' };
  for (const p of ports) {
    let tabs; try { tabs = await listTabs(p); } catch { continue; }
    const tab = tabs.find(t => t.url.includes(cfg.tabMatch));
    if (tab) return harvestTab(tab, cfg);
  }
  if (ports.length === 1) { // 只有一个采集浏览器且没开系统页面 → 直接开（多浏览器并存时不自动选边，交给智能体用MCP开）
    const tab = await openTab(ports[0], cfg.seed);
    if (tab) { await sleep(1500); return harvestTab(tab, cfg); }
    return { ok: false, reason: `端口${ports[0]}无法新开标签页（/json/new 失败）` };
  }
  return { ok: false, reason: `发现${ports.length}个DevTools端口但均无${cfg.tabMatch}页面——请让智能体用MCP打开采集页面后重试（多浏览器并存时不自动选边）` };
}

// 供 fetch-endpoints.mjs 调用（每次采集前实时收割，避免陈旧凭据）
export async function harvestAuth(opts = {}) {
  const hint = Number(opts.port || port);
  const ports = await discoverPorts(hint);
  const [yizhe, duoke] = await Promise.all([harvestSystem('yizhe', SYSTEMS.yizhe, ports), harvestSystem('duoke', SYSTEMS.duoke, ports)]);
  const out = { yizhe, duoke, ports, harvested_at: new Date().toISOString() };
  if (yizhe.ok || duoke.ok) {
    fs.mkdirSync(path.join(root, 'state'), { recursive: true });
    fs.writeFileSync(path.join(root, 'state', 'auth.json'), JSON.stringify(out, null, 2));
  }
  return out;
}

// —— 兜底导入：解析 MCP get_network_request(requestFilePath=…) 落盘的请求文件，深度扫描凭据 ——
function deepScan(node, out, depth = 0) {
  if (depth > 12 || node == null) return;
  if (typeof node === 'string') {
    if (node.includes('"token"')) { try { const j = JSON.parse(node); if (j && typeof j === 'object') deepScan(j, out, depth + 1); } catch {} } // postData字符串里嵌着JSON请求体
    if (!out.duoke?.key) { const m = node.match(/key=(\d+_[0-9a-f]{16,64})/); if (m) (out.duoke ??= {}).key = m[1]; }
    if (!out.yizhe?.token) { const m = node.match(/"token"\s*:\s*"([0-9a-zA-Z]{8,64})"/); if (m) (out.yizhe ??= {}).token = m[1]; }
  } else if (Array.isArray(node)) node.forEach(n => deepScan(n, out, depth + 1));
  else if (typeof node === 'object') {
    if (node.token && node.cid != null && node.uid != null) {
      out.yizhe ??= { token: String(node.token), cid: node.cid, uid: node.uid, plate_type: node.plate_type || 'backend', v: node.v || '', cv: node.cv || '' };
    }
    if (typeof node.url === 'string') { const m = node.url.match(/key=(\d+_[0-9a-f]{16,64})/); if (m) (out.duoke ??= {}).key = m[1]; }
    Object.values(node).forEach(v => deepScan(v, out, depth + 1));
  }
}
function importCreds(target) {
  const out = {};
  const files = [];
  const st = fs.statSync(target);
  if (st.isDirectory()) files.push(...fs.readdirSync(target).filter(f => !f.startsWith('.')).map(f => path.join(target, f)));
  else files.push(target);
  for (const f of files) {
    if (!fs.statSync(f).isFile()) continue;
    const text = fs.readFileSync(f, 'utf8');
    try { deepScan(JSON.parse(text), out); } catch { deepScan(text, out); }
    if (out.yizhe?.token && out.duoke?.key) break;
  }
  if (out.duoke) { out.duoke.lang = 'chs'; out.duoke.version = out.duoke.version || ''; }
  return out;
}

// —— 只读登录探测（--check）：用收割到的凭据各发一个查询请求，验证登录态真实有效 ——
async function probe(c) {
  try {
    if (c.sysKey === 'yizhe') {
      const res = await fetch('https://api.yizheyun.com/common/user/get_user_info', {
        method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://scm.yizheyun.com' },
        body: JSON.stringify({ token: c.creds.token, cid: c.creds.cid, uid: c.creds.uid, plate_type: c.creds.plate_type, v: c.creds.v, cv: c.creds.cv }),
        signal: AbortSignal.timeout(15000),
      });
      const j = await res.json().catch(() => ({}));
      return j.code === '200' ? { ok: true, msg: `已登录（${j.data?.name || j.data?.user_name || '员工'}）` } : { ok: false, msg: `code=${j.code} ${j.msg || ''}` };
    }
    const u = new URL('https://api.duoke.net/index.php/user/admin_get_staff_list');
    u.searchParams.set('lang', c.creds.lang || 'chs');
    if (c.creds.version) u.searchParams.set('version', c.creds.version);
    u.searchParams.set('key', c.creds.key);
    const j = await (await fetch(u, { signal: AbortSignal.timeout(15000) })).json().catch(() => ({}));
    return Number(j.err) === 0 ? { ok: true, msg: '已登录' } : { ok: false, msg: `err=${j.err} ${j.msg || ''}` };
  } catch (e) { return { ok: false, msg: e.message }; }
}

async function main() {
  if (args.import) { // 兜底导入模式：智能体先用MCP把两系统请求落盘，再导入凭据
    const t = path.isAbsolute(args.import) ? args.import : path.join(process.cwd(), args.import);
    if (!fs.existsSync(t)) { console.error(`[harvest-auth] --import 路径不存在：${t}`); process.exit(2); }
    const creds = importCreds(t);
    const result = { yizhe: creds.yizhe ? { ok: true, creds: creds.yizhe } : { ok: false, reason: '请求文件中未发现衣者token' }, duoke: creds.duoke ? { ok: true, creds: creds.duoke } : { ok: false, reason: '请求文件中未发现多客key' }, harvested_at: new Date().toISOString() };
    if (creds.yizhe || creds.duoke) {
      fs.mkdirSync(path.join(root, 'state'), { recursive: true });
      fs.writeFileSync(path.join(root, 'state', 'auth.json'), JSON.stringify(result, null, 2));
    }
    console.log(`  衣者：${creds.yizhe ? '✓ 已从请求文件导入token' : '✗ ' + result.yizhe.reason}`);
    console.log(`  多客：${creds.duoke ? '✓ 已从请求文件导入key' : '✗ ' + result.duoke.reason}`);
    console.log(JSON.stringify({ yizhe: { ok: !!creds.yizhe }, duoke: { ok: !!creds.duoke }, auth_file: creds.yizhe || creds.duoke ? path.join(root, 'state', 'auth.json') : null }));
    process.exit(creds.yizhe || creds.duoke ? 0 : 1);
  }
  console.log(`[harvest-auth] 自动发现采集浏览器DevTools端口（优先${port}，其次扫描本机监听端口）…`);
  const r = await harvestAuth({ port });
  console.log(`  发现端口：${r.ports.length ? r.ports.join(', ') : '无'}`);
  const summary = {};
  for (const k of ['yizhe', 'duoke']) {
    summary[k] = r[k].ok ? { ok: true } : { ok: false, reason: r[k].reason };
    console.log(`  ${k === 'yizhe' ? '衣者' : '多客'}：${r[k].ok ? '✓ 凭据已收割' : '✗ ' + r[k].reason}`);
  }
  if (args.check && r.yizhe.ok) { const p = await probe({ sysKey: 'yizhe', creds: r.yizhe.creds }); summary.yizhe.check = p; console.log(`  衣者登录探测：${p.ok ? '✓ ' + p.msg : '✗ ' + p.msg}`); }
  if (args.check && r.duoke.ok) { const p = await probe({ sysKey: 'duoke', creds: r.duoke.creds }); summary.duoke.check = p; console.log(`  多客登录探测：${p.ok ? '✓ ' + p.msg : '✗ ' + p.msg}`); }
  summary.auth_file = r.yizhe.ok || r.duoke.ok ? path.join(root, 'state', 'auth.json') : null;
  console.log(JSON.stringify(summary));
  process.exit(r.yizhe.ok || r.duoke.ok ? 0 : 1);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
