// cdp.mjs — 零依赖裸 CDP 客户端（2026-11-05 V1.8 新增，chrome-devtools MCP 移除后替代其页面级能力）
// 提供：CDP WebSocket 附加、命令收发、JS 求值、标签页列表/新建。
// check-login.mjs（第0步登录校验）与 cdp-eval.mjs（兜底UI采集/排查）共用。
// 只读红线：本库不限制方法（写操作由调用方按 SKILL 铁律自律——保存/删除/导出/提交一律禁止）。

const sleep = ms => new Promise(r => setTimeout(r, ms));

/** 极简 CDP 客户端：附加到一个 tab/browser 的 webSocketDebuggerUrl */
export class Cdp {
  constructor(wsUrl) { this.wsUrl = wsUrl; this.ws = null; this.seq = 0; this.pending = new Map(); this.onEvent = () => {}; }

  async attach(timeoutMs = 8000) {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((res, rej) => {
      const t = setTimeout(() => rej(new Error(`CDP WebSocket 连接超时（${this.wsUrl}）`)), timeoutMs);
      this.ws.onopen = () => { clearTimeout(t); res(); };
      this.ws.onerror = () => { clearTimeout(t); rej(new Error('CDP WebSocket 连接失败')); };
    });
    this.ws.onmessage = m => {
      const d = JSON.parse(String(m.data));
      if (d.id && this.pending.has(d.id)) {
        const p = this.pending.get(d.id); this.pending.delete(d.id);
        d.error ? p.rej(new Error(d.error.message)) : p.res(d.result);
      } else this.onEvent(d);
    };
    return this;
  }

  send(method, params = {}) {
    return new Promise((res, rej) => {
      const id = ++this.seq;
      this.pending.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => { if (this.pending.has(id)) { this.pending.delete(id); rej(new Error(`CDP ${method} 响应超时`)); } }, 30000);
    });
  }

  /** 页面内执行 JS 表达式并返回值（returnByValue；表达式须自带 JSON.stringify 承载复杂结构）。
   *  awaitPromise:true 时等待表达式返回的 Promise（读 IndexedDB 等异步场景） */
  async evalExpr(expression, { awaitPromise = false } = {}) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise });
    if (r.exceptionDetails) throw new Error(`页面JS异常: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
    return r.result?.value;
  }

  close() { try { this.ws?.close(); } catch {} }
}

/** 列出调试端点上的页面标签：GET http://127.0.0.1:{port}/json */
export async function listTabs(httpBase) {
  const r = await fetch(`http://${httpBase}/json`, { signal: AbortSignal.timeout(5000) });
  const tabs = await r.json();
  return tabs.filter(t => t.type === 'page');
}

/** 新建标签页：Chrome 111+ 要求 PUT，旧版 GET，两种都试 */
export async function newTab(httpBase, url) {
  const u = `http://${httpBase}/json/new?${new URLSearchParams({ url })}`;
  for (const method of ['PUT', 'GET']) {
    try { const r = await fetch(u, { method, signal: AbortSignal.timeout(5000) }); if (r.ok) return await r.json(); } catch {}
  }
  return null;
}

/** 轮询等待页面就绪并采集稳定状态（URL + readyState + 是否存在可见密码输入框）。
 *  V1.9.2 修复：旧版 stableSince 逻辑自相矛盾（重置条件与返回条件冲突，stableMs 实际无效，
 *  且首次 complete 前 last 为空时永不返回→白等满 maxMs）。新版：URL 稳定持续 stableMs 且 complete 即返回。 */
export async function waitPageStable(cdp, { maxMs = 15000, stableMs = 2500 } = {}) {
  const deadline = Date.now() + maxMs;
  let lastUrl = '', stableSince = 0, last = null;
  while (Date.now() < deadline) {
    let st = null;
    try {
      st = JSON.parse(await cdp.evalExpr(`JSON.stringify({url:location.href,ready:document.readyState,pw:(()=>{const e=document.querySelector('input[type=password]');return !!(e&&e.offsetParent!==null);})()})`));
    } catch {} // 页面跳转瞬间 evaluate 可能失败，下轮重试
    if (st) {
      last = st;
      if (st.url !== lastUrl) { lastUrl = st.url; stableSince = Date.now(); }
      if (st.ready === 'complete' && lastUrl && Date.now() - stableSince >= stableMs) return st;
    }
    await sleep(500);
  }
  return last; // 超时返回最后观测状态
}
