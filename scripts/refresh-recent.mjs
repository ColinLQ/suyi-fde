#!/usr/bin/env node
// 增量刷新：近10日订单列表 + 新单明细，合并进 hist3y/details
import fs from 'node:fs';
import path from 'node:path';
const SKILL = path.resolve(import.meta.dirname, '..');
const RAW = path.join(SKILL, 'data/raw/2026-10-09/pm');
const auth = JSON.parse(fs.readFileSync(path.join(SKILL, 'state/auth.json'), 'utf8'));
const key = auth.duoke.creds.key;
const BASE = 'https://api.duoke.net/index.php';
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36';
const HDRS = { 'User-Agent': UA, 'Referer': 'https://air-web.duoke.net/', 'Origin': 'https://air-web.duoke.net', 'accept-language': 'chs' };
const sleep = ms => new Promise(r => setTimeout(r, ms));

// list by window
async function fetchWindow(sday, eday) {
  const out = []; let page = 1;
  for (;;) {
    const q = new URLSearchParams({ bi_key:'documentList', keyword:'', page:String(page), page_num:'50', type:'custom', sday, eday,
      order_type: '{"options":["sale_order"],"allSelected":0}', lang:'chs', key });
    const r = await fetch(`${BASE}/order/new_view_all?${q}`, { headers: HDRS });
    const j = await r.json();
    if (j.err !== 0) throw new Error('api ' + j.err);
    const rows = j.list || []; out.push(...rows);
    const total = +(j.list_num || 0);
    if (rows.length < 50 || j.is_last === 1 || page * 50 >= total) return out;
    page++; await sleep(300);
  }
}
async function fetchDetail(id) {
  const url = `${BASE}/pluginsWeb/orderInfo/${id}?key=${key}&lang=chs&data_type=json`;
  for (let a = 1; a <= 3; a++) {
    try {
      const r = await fetch(url, { headers: HDRS });
      if (r.status === 429) { await sleep(1500 * a); continue; }
      const j = await r.json();
      if (j.err === 0 && j.data?.doc_info) return j.data;
      return null;
    } catch (e) { if (a === 3) return null; await sleep(800 * a); }
  }
  return null;
}
(async () => {
  // 1) 刷新 2026-09-20 ~ 2026-10-10 窗口
  const fresh = await fetchWindow('2026-09-20', '2026-10-10');
  console.log('window rows:', fresh.length);
  const listF = path.join(RAW, 'duoke_orders_hist3y.jsonl');
  const existing = fs.readFileSync(listF, 'utf8').trim().split('\n').map(l => JSON.parse(l));
  const have = new Set(existing.map(o => o.id || o.number));
  const add = fresh.filter(o => !have.has(o.id || o.number));
  console.log('new orders:', add.length);
  if (add.length) fs.appendFileSync(listF, add.map(r => JSON.stringify(r)).join('\n') + '\n');
  // 2) 新单明细
  const detF = path.join(RAW, 'duoke_order_details.jsonl');
  const doneDet = new Set(fs.readFileSync(detF, 'utf8').trim().split('\n').filter(Boolean).map(l => { try { return JSON.parse(l).doc_id; } catch { return null; } }));
  let n = 0;
  for (const o of add) {
    const id = o.id || o.number;
    if (doneDet.has(id)) continue;
    const d = await fetchDetail(id);
    const g = d ? (d.doc_info?.goods_info || []).map(x => ({
      doc_id: d.doc_info.id, ctime: d.doc_info.ctime, client_id: d.doc_info.client_id, client_name: (d.doc_info.client_info?.first_name || ''),
      shop_id: d.doc_info.shop_id, seller: d.doc_info.seller_info?.name || '', item_ref: x.item_ref, name: x.name,
      color: x.pure_color_name || x.color_name, size: x.size_name, quantity: +x.quantity, price: +x.price, cost: +x.cost,
      category: x.category_name, brand: x.brand_name, year: x.year_name, season: x.season_name,
    })) : [];
    fs.appendFileSync(detF, JSON.stringify({ doc_id: id, rows: g.length, goods: g }) + '\n');
    n++; await sleep(100);
  }
  console.log('new details:', n);
  // 3) is_before 语义验证：取一个多单客户的最早单与晚单
  const byc = {};
  existing.concat(add).forEach(o => { (byc[o.client_id] = byc[o.client_id] || []).push(o); });
  const multi = Object.entries(byc).filter(([, arr]) => arr.length >= 20).sort((a, b) => b[1].length - a[1].length)[0];
  const sorted = multi[1].sort((a, b) => +a.ctime - +b.ctime);
  const firstDoc = sorted[0], laterDoc = sorted[sorted.length - 3];
  for (const o of [firstDoc, laterDoc]) {
    const d = await fetchDetail(o.id);
    console.log(`is_before check: client=${o.customer_name} doc=${o.id} ctime=${new Date(+o.ctime*1000).toISOString().slice(0,10)} is_before=${d ? d.doc_info.is_before : 'n/a'}`);
  }
})();
