// 补拉指定清单款号图片: node fetch-pics-for-packages.mjs --list state/slow-refs.json
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');  // skill代码根目录（可移植）
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const PM = path.join(dataHome, 'data/raw/2026-10-09/pm');
const rl = f => fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));

const listArg = process.argv.find(x => x.startsWith('--list='));
const refs = listArg
  ? JSON.parse(fs.readFileSync(path.join(SKILL, listArg.split('=')[1]), 'utf8'))
  : (() => {
      const restockV1 = JSON.parse(fs.readFileSync(path.join(dataHome, 'out/restock-deep-2026-10-09.json'), 'utf8'));
      const restockV2 = JSON.parse(fs.readFileSync(path.join(dataHome, 'out/restock-v2-2026-10-10.json'), 'utf8'));
      const sales = JSON.parse(fs.readFileSync(path.join(dataHome, 'out/销售数据报告-2026-10-10.json'), 'utf8'));
      const s = new Set();
      restockV1.rows.forEach(x => x.item_ref && s.add(String(x.item_ref)));
      restockV2.rows.forEach(x => x.item_ref && s.add(String(x.item_ref)));
      [...(sales.move_top_month || []), ...(sales.sell_through_30d || []), ...(sales.new_product || [])].forEach(x => x.ref && s.add(String(x.ref)));
      return [...s];
    })();

const auth = JSON.parse(fs.readFileSync(path.join(dataHome, 'state/auth.json'), 'utf8'));
const key = auth.duoke.creds.key;
const HDRS = { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15;7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36', 'Referer': 'https://air.duoke.net/', 'Origin': 'https://air-web.duoke.net', 'accept-language': 'chs' };
const CDN = 'https://cn-cdn-oss.duoke.net/user_19228/';
const THUMB = '?x-oss-process=image/resize,m_mfit,h_140,w_140/quality,q_80';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const goods = rl(path.join(PM, 'duoke_goods.jsonl'));
const ref2id = new Map();
for (const g of goods) {
  if (g.item_ref) {
    ref2id.set(String(g.item_ref), g.id);
    const base = String(g.item_ref).split('-')[0];
    if (!ref2id.has(base)) ref2id.set(base, g.id);
  }
}

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
      if (buf.length < 300) return false;
      fs.writeFileSync(out, buf);
      return true;
    } catch (e) { if (a === 3) return false; await sleep(600 * a); }
  }
  return false;
}

let ok = 0, miss = [];
for (const ref of refs) {
  const out = path.join(picDir, ref + '.jpg');
  const base = ref.split('-')[0];
  const outB = path.join(picDir, base + '.jpg');
  if ((fs.existsSync(out) && fs.statSync(out).size > 500) || (fs.existsSync(outB) && fs.statSync(outB).size > 500)) { ok++; continue; }
  const id = ref2id.get(ref) || ref2id.get(base);
  if (!id) { miss.push(ref + '(无档案)'); continue; }
  const hash = cache[ref] || cache[base] || await fetchPicHash(id);
  if (hash) {
    cache[ref] = hash;
    const done = await download(hash, ref);
    if (done) { ok++; }
    else miss.push(ref);
  } else miss.push(ref + '(无图)');
  await sleep(120);
}
fs.writeFileSync(cacheF, JSON.stringify(cache, null, 1));
console.log(`图片: ${ok}/${refs.length}; 缺${miss.length}: ${miss.slice(0, 10).join(', ')}`);
