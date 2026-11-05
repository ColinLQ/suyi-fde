#!/usr/bin/env node
// 批量拉取商品图片：报表涉及的款 → get_goods_detail 取 pic hash → CDN 下载缩略图
// 输出 state/goods-pics/<item_ref>.jpg + state/goods-pics.json（hash缓存）
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');  // skill代码根目录（可移植）
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const PM = path.join(dataHome, 'data/raw/2026-10-09/pm');
const rl = f => fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));

const auth = JSON.parse(fs.readFileSync(path.join(dataHome, 'state/auth.json'), 'utf8'));
const key = auth.duoke.creds.key;
const HDRS = { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36', 'Referer': 'https://air.duoke.net/', 'Origin': 'https://air-web.duoke.net', 'accept-language': 'chs' };
const CDN = 'https://cn-cdn-oss.duoke.net/user_19228/';
const THUMB = '?x-oss-process=image/resize,m_mfit,h_140,w_140/quality,q_80';

const sleep = ms => new Promise(r => setTimeout(r, ms));

// 报表 JSON 里的所有款
const J = JSON.parse(fs.readFileSync(path.join(dataHome, 'out/销售数据报告-2026-10-10.json'), 'utf8'));
const refs = new Set();
[...J.move_top_week, ...J.move_top_halfmonth, ...J.move_top_month,
 ...(Object.values(J.cat_top_month || {}).flat()),
 ...J.sell_through_30d, ...J.new_product, ...J.new_product_client_top,
 ...J.stock_max_current_season, ...J.stock_warn_current_season, ...J.stock_owed_current_season]
  .forEach(x => x.ref && refs.add(x.ref));
console.log('refs need pics:', refs.size);

// goods id 映射
const goods = rl(path.join(PM, 'duoke_goods.jsonl'));
const ref2id = new Map(goods.map(g => [g.item_ref, g.id]));

// 缓存
const picDir = path.join(dataHome, 'state/goods-pics');
fs.mkdirSync(picDir, { recursive: true });
const cacheF = path.join(dataHome, 'state/goods-pics.json');
const cache = fs.existsSync(cacheF) ? JSON.parse(fs.readFileSync(cacheF, 'utf8')) : {};

async function fetchPicHash(id) {
  const body = new FormData();
  body.append('id', String(id)); body.append('type', 'all'); body.append('show_custom_fields', 'true'); body.append('lang', 'chs'); body.append('key', key);
  for (let a = 1; a <= 3; a++) {
    try {
      const r = await fetch('https://api.duoke.net/index.php/analysis/get_goods_detail', { method: 'POST', headers: HDRS, body });
      const j = await r.json();
      if (j.err === 0 && j.goods) return j.goods.pic_url || (j.goods.sku && j.goods.sku[0] ? j.goods.sku[0].img : null) || null;
      return null;
    } catch (e) { if (a === 3) return null; await sleep(800 * a); }
  }
  return null;
}

async function download(hash, ref) {
  const out = path.join(picDir, ref + '.jpg');
  if (fs.existsSync(out) && fs.statSync(out).size > 500) return true;
  for (let a = 1; a <= 3; a++) {
    try {
      const r = await fetch(CDN + hash + THUMB, { headers: { 'User-Agent': HDRS['User-Agent'], Referer: 'https://air.duoke.net/' } });
      if (!r.ok) return false;
      const buf = Buffer.from(await r.arrayBuffer());
      if (buf.length < 500) return false;
      fs.writeFileSync(out, buf);
      return true;
    } catch (e) { if (a === 3) return false; await sleep(800 * a); }
  }
  return false;
}

(async () => {
  let ok = 0, miss = 0, skip = 0;
  const list = [...refs];
  for (let i = 0; i < list.length; i++) {
    const ref = list[i];
    const local = path.join(picDir, ref + '.jpg');
    if (fs.existsSync(local) && fs.statSync(local).size > 500 && cache[ref]) { skip++; continue; }
    const id = ref2id.get(ref);
    if (!id) { console.error('no goods id:', ref); miss++; continue; }
    const hash = await fetchPicHash(id);
    if (!hash) { miss++; cache[ref] = null; await sleep(150); continue; }
    cache[ref] = hash;
    const dl = await download(hash, ref);
    dl ? ok++ : miss++;
    if ((i + 1) % 40 === 0) { console.log(`  ...${i + 1}/${list.length} (ok${ok} miss${miss})`); fs.writeFileSync(cacheF, JSON.stringify(cache, null, 1)); }
    await sleep(120);
  }
  fs.writeFileSync(cacheF, JSON.stringify(cache, null, 1));
  console.log(`PICS done: ok=${ok} skip=${skip} miss=${miss} -> ${picDir}`);
})();
