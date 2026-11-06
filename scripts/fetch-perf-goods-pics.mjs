#!/usr/bin/env node
// 拉取绩效报表涉及的款号图片：perf/cost JSON 收集款 → 多客 get_goods_detail 取 pic hash → CDN 缩略图
// 输出 state/goods-pics/<item_ref>.jpg + 复用 state/goods-pics.json hash 缓存
// 用法: node fetch-perf-goods-pics.mjs   （读 out/performance-2026-09.json 与 out/cost-2026-09.json 的统计月）
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');  // skill代码根目录（可移植）
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const rl = f => fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));

const perf = JSON.parse(fs.readFileSync(path.join(dataHome, 'out/performance-2026-09.json'), 'utf8'));
const costP = path.join(SKILL, `out/cost-${perf['统计月']}.json`);
const cost = fs.existsSync(costP) ? JSON.parse(fs.readFileSync(costP, 'utf8')) : { '成本明细': [] };

// 1. 收集报表全部款号
const refs = new Set();
for (const x of perf['采购明细'] || []) x['款号'] && refs.add(x['款号']);
for (const x of perf['生产明细'] || []) x['款号'] && refs.add(x['款号']);
for (const x of perf['设计明细'] || []) x['款号'] && refs.add(x['款号']);
for (const x of perf['仓库明细'] || []) x['款号'] && refs.add(x['款号']);
for (const x of cost['成本明细'] || []) x['款号'] && refs.add(x['款号']);
console.log('报表涉及款号:', refs.size);

// 2. 多客 goods id 映射（取最新一份全量快照）
const pmRoot = path.join(dataHome, 'data/raw');
let goodsF = null, goodsMtime = 0;
(function find(dir) {
  let ents = [];
  try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
  for (const e of ents) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) find(p);
    else if (e.name === 'duoke_goods.jsonl') {
      const m = fs.statSync(p).mtimeMs;
      if (m > goodsMtime) { goodsMtime = m; goodsF = p; }
    }
  }
})(pmRoot);
if (!goodsF) { console.error('未找到 duoke_goods.jsonl'); process.exit(1); }
console.log('goods 快照:', goodsF);
const ref2id = new Map();
for (const g of rl(goodsF)) if (g.item_ref) ref2id.set(g.item_ref, g.id);

// 3. hash 缓存 + 下载
const auth = JSON.parse(fs.readFileSync(path.join(dataHome, 'state/auth.json'), 'utf8'));
const key = auth.duoke.creds.key;
const HDRS = { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36', 'Referer': 'https://air.duoke.net/', 'Origin': 'https://air-web.duoke.net', 'accept-language': 'chs' };
const CDN = 'https://cn-cdn-oss.duoke.net/user_19228/';
const THUMB = '?x-oss-process=image/resize,m_mfit,h_140,w_140/quality,q_80';
const sleep = ms => new Promise(r => setTimeout(r, ms));

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
  const missRefs = [];
  const list = [...refs];
  for (let i = 0; i < list.length; i++) {
    const ref = list[i];
    const local = path.join(picDir, ref + '.jpg');
    if (fs.existsSync(local) && fs.statSync(local).size > 500 && cache[ref]) { skip++; continue; }
    const id = ref2id.get(ref);
    if (!id) { miss++; missRefs.push(ref); continue; }
    const hash = cache[ref] || await fetchPicHash(id);
    if (!hash) { miss++; cache[ref] = null; missRefs.push(ref); await sleep(150); continue; }
    cache[ref] = hash;
    const dl = await download(hash, ref);
    dl ? ok++ : (miss++, missRefs.push(ref));
    if ((i + 1) % 40 === 0) { console.log(`  ...${i + 1}/${list.length} (ok${ok} skip${skip} miss${miss})`); fs.writeFileSync(cacheF, JSON.stringify(cache, null, 1)); }
    await sleep(120);
  }
  fs.writeFileSync(cacheF, JSON.stringify(cache, null, 1));
  console.log(`PICS done: ok=${ok} skip=${skip} miss=${miss} -> ${picDir}`);
  if (missRefs.length) { fs.writeFileSync(path.join(dataHome, 'state/goods-pics-miss.json'), JSON.stringify(missRefs, null, 1)); console.log('缺失款清单 -> state/goods-pics-miss.json'); }
})();
