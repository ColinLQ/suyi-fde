#!/usr/bin/env node
// mock-capture.mjs — 模拟"MCP浏览器采集"的产出（字段结构与真实API抓包文档一致）
// Demo 用途：当前环境无客户登录态，用模拟数据跑通全链路。上线时此步骤替换为
// chrome-devtools MCP 的 navigate_page + list_network_requests + get_network_request，
// 后续 ingest/match/alert/reconcile/report 脚本链完全不变。
// 红线：本文件不访问任何网络，仅生成本地文件。
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataHome = process.env.SCM_DATA_HOME || path.join(os.homedir(), 'WorkBuddy', 'scm-collector-data'); // 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i++) {
  const t = argv[i].replace(/^--/, '');
  if (t.includes('=')) { const [k, v] = t.split('='); args[k] = v; }
  else if (argv[i + 1] && !argv[i + 1].startsWith('--')) { args[t] = argv[i + 1]; i++; }
  else args[t] = true;
}
const date = args.date || new Date().toISOString().slice(0, 10);
const slot = args.slot || (new Date().getHours() >= 14 ? 'pm' : 'am'); // 与 ingest.mjs 槽位口径一致
let rawDir = path.join(dataHome, 'data', 'raw', date, slot);
if (fs.existsSync(rawDir) && fs.readdirSync(rawDir).length > 0) {
  // 防污染护栏：槽位已有数据时隔离Demo产物（历史事故：am槽曾混入mock）
  rawDir = path.join(dataHome, 'data', 'raw', date, '_quarantine_mock');
  console.warn(`[mock-capture] ⚠️ ${date}/${slot} 槽已有数据，Demo产物改写入 _quarantine_mock/ 防污染`);
}
fs.mkdirSync(rawDir, { recursive: true });
fs.mkdirSync(path.join(dataHome, 'state'), { recursive: true });
fs.writeFileSync(path.join(rawDir, '_source_demo'), new Date().toISOString()); // Demo标记：ingest据此标注数据来源

// —— 确定性伪随机（同日期可复现） ——
let seed = 20260924;
const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
const ri = (min, max) => Math.floor(rnd() * (max - min + 1)) + min;
const pick = arr => arr[ri(0, arr.length - 1)];
const f1 = n => Math.round(n * 10) / 10;
const f2 = n => Math.round(n * 100) / 100;

const write = (file, rows) => {
  const isJson = file.endsWith('.json');
  fs.writeFileSync(path.join(rawDir, file), isJson ? JSON.stringify(rows, null, 2) : rows.map(r => JSON.stringify(r)).join('\n'));
  console.log(`  ✓ ${file} (${Array.isArray(rows) ? rows.length : 1}条)`);
};

console.log(`[mock-capture] 日期=${date} 生成模拟抓取数据 → ${path.relative(root, rawDir)}/`);

// ============ 衣者 ============
// 1) 生产总览（/common/ott_manage/get_header_data 响应结构）
write('yizhe_header.json', {
  code: '200', msg: 'success',
  data: { production_num: '157', first_order: 83, back_order: 60, normal_order: 14,
    order_num: '33952', pre_cuted_num: '23361', cuted_num: '20739', stock_out_num: '17275',
    stock_in_num: '1895', inventory_num: '1895', owed_num: '32665',
    template_num: '2860', order_template_num: '1416', un_order_template_num: '1444' }
});
// 2) 生产异常（get_warn_data）
write('yizhe_warn.json', {
  code: '200',
  data: { total_error: 143, num_error: 91, time_error: 138, date_error: 64,
    no_factory_count: 35, no_buyer_count: 51, no_follower_count: 49, no_price_count: 54 }
});
// 3) 跟单进度（get_follow_order_list 核心字段）
const steps = ['分配工厂', '物料采购', '物料到厂', '裁货', '出货', '入库'];
const factories = ['恒生', '利兴', '鑫源', '博林丰', '展宏'];
const followOrders = Array.from({ length: 30 }, (_, i) => {
  const over = rnd() < 0.3;
  return {
    template_no: `SM26${String(41000 + i * 7).padStart(5, '0')}`,
    production_type_desc: pick(['首单', '首单', '返单', `返单${ri(2, 12)}`]),
    back_order_times: ri(0, 12),
    current_step: pick(steps),
    less_finish_time: over ? { value: `超${ri(1, 5)}天`, is_warn: 1 } : { value: `剩${ri(1, 9)}天`, is_warn: 0 },
    plan_total_num: ri(100, 800), cuted_num: ri(0, 400), stock_out_num: ri(0, 300), stock_in_num: ri(0, 200),
    factory_name: pick(factories), follower_user_name: pick(['龙文学', '肖小平', '陈佩哲'])
  };
});
write('yizhe_follow_orders.jsonl', followOrders);
// 4) 财务待付（get_finance_purchase_sum）
write('yizhe_finance_sum.json', {
  code: '200',
  data: { sum_total_price: '6624411.09', sum_paid_price: '0', sum_wait_paid_price: '6624411.09', sum_wait_bill_price: '6624411.09' }
});
// 5) 样板列表（get_template_list，Demo取40款）
const cats = ['羽绒服', '毛衣', '马甲', 'T恤', '连衣裙', '裤子'];
const designers = ['SOSO', '黄蓓蕾', '陈佩哲'];
const fabricTypes = ['针织', '梭织'];
const templates = Array.from({ length: 40 }, (_, i) => ({
  template_no: `SM26${String(41000 + i * 7).padStart(5, '0')}`,
  template_name: pick(['高领针织打底衫', '宽松羽绒马甲', '羊毛混纺连衣裙', '重磅纯棉T恤', '直筒休闲裤']),
  cat_name: pick(cats), brand_name: '素一', band_name: pick(['2026秋一波', '2026冬一波', '2026冬二波']),
  design_user: pick(designers), template_price: String(f2(ri(35, 120))),
  fabric_type: pick(fabricTypes), template_status_name: pick(['已下单', '已下单', '待下单', '废版'])
}));
write('yizhe_template_list.jsonl', templates);

// ============ 多客 ============
// 6) 经营概览（console_summary）
write('duoke_console_summary.json', {
  err: 0,
  today_doc_amount: '31', today_doc_money: '140330.50', today_doc_goods_amount: '1684', today_new_client_amount: '2',
  trade_trend: [{ date: '2026-08', transaction_sum: '2063', transaction_money: '1691327' }, { date: '2026-09', transaction_sum: '1980', transaction_money: '1520380' }],
  transaction_top10: [
    { shop_id: '4', shop_name: '素一（十三行2918档）', transaction_money: '819267.00' },
    { shop_id: '1', shop_name: '手山（十三行7楼D29-30A）', transaction_money: '643192.00' },
    { shop_id: '5', shop_name: '总仓', transaction_money: '57921.00' }
  ]
});
// 7) 商品+SKU库存（goods/get_by_order，与衣者款号部分对应+部分前缀差异）
const colors = ['咖色', '灰色', '黑色', '杏色', '红色'];
const sizes = ['F', 'S', 'M', 'L'];
const goods = templates.filter(t => t.template_status_name !== '废版').map((t, i) => {
  const prefixVariants = [`SM26${String(41000 + i * 7).padStart(5, '0')}`, `SK26${String(41000 + i * 7).padStart(5, '0')}`, `LT26${String(41000 + i * 7).padStart(5, '0')}`];
  const sku = {};
  colors.slice(0, ri(1, 3)).forEach((c, ci) => sizes.slice(0, ri(1, 3)).forEach((s, si) => {
    const stock = ri(0, 400);
    sku[`sku${ci * 4 + si}`] = {
      color: { name: c }, size: { name: s },
      price_in: String(f2(Number(t.template_price) + ri(-1, 1))),   // 与衣者成本±1元内
      price_1: String(f2(Number(t.template_price) * (1.4 + rnd() * 0.5))),
      warehouse_0: stock, store_stock_0: stock, pre_sell_stock_0: ri(0, 50), onway_stock_0: ri(0, 100)
    };
  }));
  return {
    id: String(4400 + i), item_ref: pick(prefixVariants), name: t.template_name,
    cate_info: { name: t.cat_name }, year: { name: '2026年' }, season: { name: '秋季' },
    sku
  };
});
write('duoke_goods.jsonl', goods);
// 8) 30日动销（get_goods_sale_trend）
const trend = {};
goods.forEach(g => {
  const hot = rnd() < 0.2; // 20%爆款
  const days = {};
  for (let d = 0; d < 30; d++) {
    const dt = new Date(date); dt.setDate(dt.getDate() - d);
    days[dt.toISOString().slice(0, 10)] = hot ? ri(20, 90) : ri(0, 12);
  }
  trend[g.id] = { trend: days, total: Object.values(days).reduce((a, b) => a + b, 0) };
});
write('duoke_sale_trend.json', { days: 30, goods: trend });
// 9) 销售单据（order/new_view_all）
const clients = ['福建张三', '沈阳李四', '杭州王五', '武汉赵六', '北京钱七'];
const orders = Array.from({ length: 25 }, (_, i) => {
  const isReturn = rnd() < 0.12;
  const qty = ri(10, 250);
  return {
    number: String(1192600 + i), type: '1',
    shop_name: pick(['素一（十三行2918档）', '手山（十三行7楼D29-30A）']),
    customer_name: pick(clients), seller_name: pick(['demo店员A', 'demo店员B', 'demo店员C']),
    goods_quantity: isReturn ? -qty : qty, calc_price: String(f2((isReturn ? -1 : 1) * qty * ri(80, 150))),
    ctime: String(Math.floor(new Date(date).getTime() / 1000) - ri(0, 86400))
  };
});
write('duoke_orders.jsonl', orders);
// 10) 收支流水（payment/view_all）
const payments = Array.from({ length: 20 }, (_, i) => ({
  number: String(114330 + i), price: String(f2(ri(300, 20000))),
  payment_name: pick(['扫码支付', '银行转账', '现金']), pay_channel: 'order_pay',
  client_name: pick(clients), seller_name: pick(['demo店员A', 'demo店员B', 'demo店员C']),
  ctime: String(Math.floor(new Date(date).getTime() / 1000) - ri(0, 86400))
}));
write('duoke_payments.jsonl', payments);
// 11) 成衣入库（get_instock_list，US-01日报『待入库』）
const instock = followOrders.slice(0, 12).map((o, i) => ({
  template_no: o.template_no, production_sn: `D26092${String(40000 + i)}`,
  stockout_num: ri(100, 300), instock_num: rnd() < 0.5 ? 0 : ri(50, 250),
  bad_num: ri(0, 3), created_at: `${date} ${String(ri(9, 17)).padStart(2, '0')}:30:00`, factory_name: o.factory_name
}));
write('yizhe_instock_list.jsonl', instock);
// 12) 研发统计（template_stat/summary，US-01研发版）
write('yizhe_stat_summary.json', { code: '200', data: { build: { select: 45, today: 8, month_chain_ratio: 221.43 }, ordered: { select: 16, rate: 35.56 }, scrap: { select: 2, rate: 4.4 }, finish: { select: 30 } } });
// 13) 客户资料（customer/get_by_order type=1）
write('duoke_customers.jsonl', clients.map((c, i) => ({
  id: String(15000 + i), name: c, phone: String(ri(13000000000, 18999999999)),
  debt: pick(['0.00', '0.00', String(f2(ri(500, 30000)))]), days_not_purchased: ri(0, 120),
  goods_num: ri(1, 40), staff_name: pick(['demo店员A', 'demo店员B', 'demo店员C']), address: ''
})));

console.log('[mock-capture] 完成。下一步：node scripts/ingest.mjs --date ' + date + ' --slot ' + slot);
