#!/usr/bin/env node
// 销售数据需求采集：3年销售订单全量 + 订单明细行
// 数据源：多客 order/new_view_all（列表）+ pluginsWeb/orderInfo（明细）
// 只读接口；凭据来自 state/auth.json（实时登录态收割缓存）
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');  // skill代码根目录（可移植）
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const RAW = path.join(dataHome, 'data/raw/2026-10-09/pm');
const auth = JSON.parse(fs.readFileSync(path.join(dataHome, 'state/auth.json'), 'utf8'));
const key = auth.duoke.key || auth.duoke.creds?.key;
if (!key) { console.error('no duoke key'); process.exit(1); }
const BASE = 'https://api.duoke.net/index.php';
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36';
const HDRS = { 'User-Agent': UA, 'Referer': 'https://air-web.duoke.net/', 'Origin': 'https://air-web.duoke.net', 'accept-language': 'chs' };

const sleep = ms => new Promise(r => setTimeout(r, ms));
function ymd(d){ return d.toISOString().slice(0,10); }

// ---- 1) 3年订单列表（按月分窗，月订单量~300-600，page_size=50 走3-13页）----
async function fetchMonth(sday, eday) {
  const out = [];
  let page = 1;
  for (;;) {
    const q = new URLSearchParams({ bi_key:'documentList', keyword:'', page:String(page), page_num:'50', type:'custom', sday, eday,
      order_type: '{"options":["sale_order"],"allSelected":0}', lang:'chs', key });
    const url = `${BASE}/order/new_view_all?${q}`;
    let j;
    try {
      const r = await fetch(url, { headers: HDRS });
      j = await r.json();
    } catch (e) { return { err: 'fetch:' + e.message, rows: out }; }
    if (j.err !== 0) return { err: 'api err ' + j.err + ' ' + (j.msg||''), rows: out };
    const rows = j.list || [];
    out.push(...rows);
    const total = +(j.list_num || 0);
    if (rows.length < 50 || j.is_last === 1 || page * 50 >= total) return { rows: out, total };
    page++;
    await sleep(300);
  }
}

// ---- 2) 订单明细（商品行）----
async function fetchDetail(id) {
  const url = `${BASE}/pluginsWeb/orderInfo/${id}?key=${key}&lang=chs&data_type=json`;
  for (let a = 1; a <= 3; a++) {
    try {
      const r = await fetch(url, { headers: HDRS });
      if (r.status === 429) { await sleep(1500 * a); continue; }
      const j = await r.json();
      if (j.err === 0 && j.data?.doc_info) return j.data;
    } catch (e) { if (a === 3) return null; await sleep(800 * a); }
  }
  return null;
}

const mode = process.argv[2] || 'list';
const D = s => new Date(s + 'T00:00:00+08:00');

(async () => {
  fs.mkdirSync(RAW, { recursive: true });

  if (mode === 'list') {
    // 2023-10-01 ~ 2026-10-09 按自然月
    const months = [];
    let cur = D('2023-10-01');
    const end = D('2026-10-09');
    while (cur <= end) {
      const s = ymd(cur);
      const nm = new Date(cur); nm.setMonth(nm.getMonth() + 1);
      const e = (nm > end ? end : new Date(nm.getTime() - 86400000));
      months.push([s, ymd(e)]);
      cur = nm;
    }
    const all = [];
    const issues = [];
    for (const [s, e] of months) {
      const { rows, total, err } = await fetchMonth(s, e);
      if (err) { issues.push({ s, e, err }); console.error(`[X] ${s}~${e}: ${err}`); }
      else console.log(`[ok] ${s}~${e}: ${rows.length}/${total||'?'}`);
      all.push(...rows);
      await sleep(400);
    }
    const outF = path.join(RAW, 'duoke_orders_hist3y.jsonl');
    fs.writeFileSync(outF, all.map(r => JSON.stringify(r)).join('\n') + '\n');
    fs.writeFileSync(path.join(RAW, 'duoke_orders_hist3y.meta.json'), JSON.stringify({ fetched_at: new Date().toISOString(), months, issues, count: all.length }, null, 2));
    console.log(`TOTAL ${all.length} orders -> ${outF}; issues=${issues.length}`);
  }

  if (mode === 'detail') {
    // 并发6拉明细；断点续传（done集合）；--days N 只拉近N日单
    const listF = path.join(RAW, 'duoke_orders_hist3y.jsonl');
    const orders = fs.readFileSync(listF, 'utf8').trim().split('\n').map(l => JSON.parse(l));
    const outF = path.join(RAW, 'duoke_order_details.jsonl');
    const tmpF = outF + '.tmp';
    const done = new Set();
    if (fs.existsSync(outF)) fs.readFileSync(outF, 'utf8').trim().split('\n').filter(Boolean).forEach(l => { try { done.add(JSON.parse(l).doc_id); } catch {} });
    const daysArg = process.argv.includes('--days') ? +process.argv[process.argv.indexOf('--days') + 1] : null;
    const cutoff = daysArg ? Date.now() / 1000 - daysArg * 86400 : 0;
    const todo = orders.filter(o => { const id = o.id || o.number; return !done.has(id) && (!cutoff || +o.ctime >= cutoff); });
    console.log(`todo ${todo.length} (done ${done.size}, days=${daysArg || 'all'})`);
    let n = 0, fail = 0;
    const buf = [];
    const flush = () => { if (buf.length) { fs.appendFileSync(outF, buf.join('\n') + '\n'); buf.length = 0; } };
    const CONC = 6;
    let idx = 0;
    async function worker() {
      while (idx < todo.length) {
        const o = todo[idx++];
        const id = o.id || o.number;
        const d = await fetchDetail(id);
        if (d) {
          const g = (d.doc_info?.goods_info || []).map(x => ({
            doc_id: d.doc_info.id, ctime: d.doc_info.ctime, client_id: d.doc_info.client_id, client_name: (d.doc_info.client_info?.first_name || ''),
            shop_id: d.doc_info.shop_id, seller: d.doc_info.seller_info?.name || '', item_ref: x.item_ref, name: x.name,
            color: x.pure_color_name || x.color_name, size: x.size_name, quantity: +x.quantity, price: +x.price, cost: +x.cost,
            category: x.category_name, brand: x.brand_name, year: x.year_name, season: x.season_name,
          }));
          buf.push(JSON.stringify({ doc_id: id, rows: g.length, goods: g }));
        } else {
          buf.push(JSON.stringify({ doc_id: id, rows: 0, goods: [], err: 'no data' }));
          fail++;
        }
        n++;
        if (buf.length >= 60) flush();
        if (n % 500 === 0) { flush(); console.log(`  ...${n}/${todo.length} (fail ${fail})`); }
        await sleep(80);
      }
    }
    await Promise.all(Array.from({ length: CONC }, worker));
    flush();
    console.log(`DETAILS done: ${n} ok=${n - fail} fail=${fail} -> ${outF}`);
  }
})();
