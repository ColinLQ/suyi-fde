#!/usr/bin/env node
// 增量补采多客商品档案（含10月新款），刷新最新 goods 快照供图片拉取
// 用法: node fetch-goods-refresh.mjs
// 产出: data/raw/<date>/pm/duoke_goods.jsonl（覆盖当日）
import fs from 'node:fs';
import path from 'node:path';

const SKILL = path.resolve(import.meta.dirname, '..');
const auth = JSON.parse(fs.readFileSync(path.join(SKILL, 'state/auth.json'), 'utf8'));
const key = auth.duoke.creds.key;
const HDRS = { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36', 'Referer': 'https://air.duoke.net/', 'Origin': 'https://air-web.duoke.net', 'accept-language': 'chs' };
const API = 'https://api.duoke.net/index.php/goods/get_by_order';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const today = new Date();
const fmt = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const day = fmt(today);
const outDir = path.join(SKILL, 'data/raw', day, 'pm');
fs.mkdirSync(outDir, { recursive: true });
const outFile = path.join(outDir, 'duoke_goods.jsonl');

const body0 = {
  bi_key: 'productList-instock', days: -1,
  sday: '2015-01-01', eday: day,       // @wide 宽窗口全量
  order: 'utime', isasc: 0, keyword: '',
  show_sku: 1,
  goods_status: JSON.stringify({ options: ['disable=0'], allSelected: 0 }),
  dimension: JSON.stringify({ options: ['goods'], allSelected: 0 }),
  key, lang: 'chs',
};

(async () => {
  const rows = [];
  let page = 1;
  while (true) {
    const body = new FormData();
    for (const [k, v] of Object.entries({ ...body0, page })) body.append(k, String(v));
    let j = null;
    for (let a = 1; a <= 3; a++) {
      try {
        const r = await fetch(API, { method: 'POST', headers: HDRS, body });
        j = await r.json();
        break;
      } catch (e) { if (a === 3) throw e; await sleep(800 * a); }
    }
    if (!j || j.err !== 0) { console.error('API err page', page, JSON.stringify(j)?.slice(0, 200)); break; }
    const list = j.goods || [];
    rows.push(...list);
    console.log(`page ${page}: +${list.length} (total ${rows.length}, server total ${j.total ?? '?'})`);
    if (!list.length || (j.total && rows.length >= j.total) || page > 400) break;
    page++;
    await sleep(200);
  }
  fs.writeFileSync(outFile, rows.map(r => JSON.stringify(r)).join('\n') + '\n');
  console.log('saved:', outFile, rows.length, 'rows');
})();
