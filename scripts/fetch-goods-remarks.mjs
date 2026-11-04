#!/usr/bin/env node
// 批量拉取商品备注（goods/get desc字段）→ state/goods-remarks.json
// 上市时间口径（2026-10-12 柳红）：备注里的日期优先；无备注 → 首次销售时间
import fs from 'node:fs';
import path from 'node:path';

const SKILL = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');  // skill根目录（可移植）
const auth = JSON.parse(fs.readFileSync(path.join(SKILL, 'state/auth.json'), 'utf8'));
const key = auth.duoke.creds.key;
const HDRS = { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36', 'Referer': 'https://air.duoke.net/', 'Origin': 'https://air-web.duoke.net', 'accept-language': 'chs' };
const rl = f => fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
// 商品库自动发现：data/raw 下最新 duoke_goods.jsonl（可移植）
const findGoods = () => {
  const hits = [];
  const walk = d => fs.readdirSync(d, { withFileTypes: true }).forEach(e => {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name === 'duoke_goods.jsonl') hits.push(p);
  });
  walk(path.join(SKILL, 'data/raw'));
  if (!hits.length) throw new Error('未找到 duoke_goods.jsonl');
  hits.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  return hits[0];
};
const goods = rl(findGoods());
const sleep = ms => new Promise(r => setTimeout(r, ms));

// 缓存
const outF = path.join(SKILL, 'state/goods-remarks.json');
const cache = fs.existsSync(outF) ? JSON.parse(fs.readFileSync(outF, 'utf8')) : {};

// 日期解析：备注中找 2026.x.x / 2026-10-1 / 10月1日 / 10.1 等
function parseDate(str) {
  if (!str) return null;
  const s = String(str);
  let m = s.match(/(20\d{2})[年\-\./](\d{1,2})[月\-\./](\d{1,2})/);
  if (m) return `${m[1]}-${String(m[2]).padStart(2, '0')}-${String(m[3]).padStart(2, '0')}`;
  m = s.match(/(\d{1,2})月(\d{1,2})[日号]/);
  if (m) { const y = new Date().getFullYear(); return `${y}-${String(m[1]).padStart(2, '0')}-${String(m[2]).padStart(2, '0')}`; }
  m = s.match(/^(\d{1,2})[.\/](\d{1,2})$/);
  if (m) { const y = new Date().getFullYear(); return `${y}-${String(m[1]).padStart(2, '0')}-${String(m[2]).padStart(2, '0')}`; }
  return null;
}

(async () => {
  let n = 0, miss = 0, hit = 0;
  for (const g of goods) {
    const ref = g.item_ref, id = g.id;
    if (cache[ref] && cache[ref].fetched) { if (cache[ref].date) hit++; continue; }
    try {
      const r = await fetch(`https://api.duoke.net/index.php/goods/get?id=${id}&lang=chs&key=${key}`, { headers: HDRS });
      const j = await r.json();
      const desc = (j.err === 0 && j.info && j.info.desc) ? String(j.info.desc).trim() : '';
      const date = parseDate(desc);
      cache[ref] = { fetched: true, remark: desc, date };
      if (date) hit++;
      n++;
      if (n % 100 === 0) { console.log(`  ...${n} (含日期备注 ${hit})`); fs.writeFileSync(outF, JSON.stringify(cache, null, 1)); }
      await sleep(80);
    } catch (e) {
      miss++;
      cache[ref] = { fetched: false, remark: '', date: null };
      await sleep(300);
    }
  }
  fs.writeFileSync(outF, JSON.stringify(cache, null, 1));
  console.log(`REMARKS done: fetched=${n} cacheHit=${goods.length - n} withDate=${hit} fail=${miss} -> ${outF}`);
})();
