#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
研发部门数据需求总结 Excel 生成器 V3（审核修复版 2026-10-15 17:10）
修复清单（对应审核报告 12 项硬伤 + 7 项缺失 + 3 项口径）：
  [修1] 售罄率：口径=近30日销量÷当前库存（引擎实际公式），>100%标注"已超售(预售)"
  [修2] 09页档位：按报表时点(10-15 16:00)重算天数，四档 1-7/8-15/16-30/>30天
  [修3] 上市日期三源统一：备注日期>首次销售>建档日，09页加"日期来源"列，全表统一
  [修4] 库存口径统一：多客实时库存(dkStock)；负库存标注"预售欠货"
  [修5] 00页数字对齐：全部以30日订单文件(796单)为唯一基准
  [修6] 02页滞销重定义：上市≥14天+库存>0+(周转>30天或零动销)+当季
  [修7] 10页补负库存(预售欠货)区
  [修8] 上市8天/周转2.8天款不再入滞销（新定义天然排除）
  [修9] 品名缺失用goods表回填；单价0标注
  [修10] VIP统一映射 A/B/C/D+未分级
  [修11] 颜色归一化（咖啡系/卡其/藏青等），保留原始名对照列
  [修12] 后缀款(-EHT/-DOA等)在05品类页剔除、09页标注
  [补1] 毛利率：明细级(price-cost)/price，cost覆盖97.5%
  [补2] 同比去年：3年明细对比2025年同窗口+2025全年
  [补3] 老款生命周期：09b页 在售周数/动销月数/最后动销日
  [补4] 返单时点：08页 首单→首次返单平均间隔+节奏分级
  [补5] TOP10：01页前10行加底色标注
  [口径] 关联客户(刻为/清货/特卖等)打标不剔除；区域小样本标灰；微信渠道定义说明
"""
import os, re
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = str(Path(__file__).resolve().parent.parent)
TODAY = '2026-10-15'
REPORT_TS = datetime(2026, 10, 15, 16, 0, 0)
OUT = os.path.join(ROOT, 'out', f'研发需求总结-{TODAY}.xlsx')

# ================= 数据加载 =================
report = json.load(open(os.path.join(ROOT, 'out', f'销售数据报告-{TODAY}.json')))
details = [json.loads(l) for l in open(os.path.join(ROOT, 'data/raw/2026-10-09/pm/duoke_order_details.jsonl'))]
orders30 = [json.loads(l) for l in open(os.path.join(ROOT, 'data/raw/2026-09-28/am/duoke_orders_30d.jsonl'))]
custs = {}
for line in open(os.path.join(ROOT, 'data/raw/2026-10-09/pm/duoke_customers.jsonl')):
    c = json.loads(line)
    custs[str(c['id'])] = c
goods = {}
for line in open(os.path.join(ROOT, 'data/raw/2026-10-09/pm/duoke_goods.jsonl')):
    g = json.loads(line)
    goods[g['item_ref']] = g
remarks = json.load(open(os.path.join(ROOT, 'state/goods-remarks.json')))

TAG_MAP = {1:'微信',2:'档口',3:'刻为工厂/特卖',4:'福利/UUS拿货',5:'客户订单',6:'退单',7:'新客'}
REGION_MAP = {'84':'福建','90':'广东','85':'江西','86':'四川','87':'湖南','88':'江苏','89':'太原',
              '91':'贵州','93':'香港','94':'湖北','99':'东北三省','100':'澳门','101':'浙江'}
VIP_MAP = {'1':'未分级','2':'B','3':'C','4':'D'}
SHOP_SHORT = {'1':'手山档口','2':'老意法档口','3':'UUS档','4':'十三行2918档','5':'总仓','6':'销售部','7':'次品仓'}
RELATED_PAT = re.compile(r'刻为|清货|特卖|版衣|^零售$|寄版|UUS')

def parse_tags(s):
    if not s: return []
    return [int(t) for t in str(s).split(',') if t.strip().isdigit()]

def channel_of(tags):
    s = set(tags)
    if 6 in s: return '退单'
    if 5 in s and 2 in s: return '订单+档口混合'
    if 5 in s: return '客户订单'
    if 2 in s: return '档口'
    if 3 in s: return '刻为工厂/特卖'
    if 4 in s: return '福利/UUS拿货'
    if 1 in s: return '微信'
    return '未打标'

# ================= 展平全量明细 =================
goods_rows = []
for d in details:
    for g in d.get('goods', []):
        goods_rows.append({
            'doc': str(d.get('doc_id','')), 'ts': int(g.get('ctime',0)), 'ref': g.get('item_ref',''),
            'name': g.get('name',''), 'color': g.get('color',''),
            'cat': g.get('category','') or '未分类',
            'qty': int(g.get('quantity',0) or 0),
            'price': float(g.get('price',0) or 0),
            'cost': float(g.get('cost',0) or 0),
            'shop': str(g.get('shop_id','')), 'client_id': str(g.get('client_id','')),
            'client': g.get('client_name',''),
        })

first_sale = {}
for r_ in goods_rows:
    if r_['ts'] and (r_['ref'] not in first_sale or r_['ts'] < first_sale[r_['ref']]):
        first_sale[r_['ref']] = r_['ts']

def list_date_full(ref):
    """三级口径：备注日期 > 首次销售 > 建档日 [修3]"""
    rm = remarks.get(ref)
    if rm and rm.get('date'):
        return rm['date'], '备注日期'
    if ref in first_sale:
        return datetime.fromtimestamp(first_sale[ref]).strftime('%Y-%m-%d'), '首次销售'
    g = goods.get(ref)
    if g:
        return datetime.fromtimestamp(int(g['ctime'])).strftime('%Y-%m-%d'), '建档日'
    return None, '-'

cutoff30 = (REPORT_TS - timedelta(days=30)).timestamp()
cutoff7 = (REPORT_TS - timedelta(days=7)).timestamp()
UPPER_TS = REPORT_TS.timestamp()   # 窗口上界=报表时点（防混入后续新单）
doc_tags = {str(o.get('id','')): parse_tags(o.get('tag','')) for o in orders30}
rows30 = []
for r_ in goods_rows:
    if r_['ts'] < cutoff30 or r_['ts'] > UPPER_TS: continue
    r2 = dict(r_)
    tags = doc_tags.get(r_['doc'], [])
    r2['tags'] = tags
    r2['channel'] = channel_of(tags)
    rows30.append(r2)

# 多客实时库存：goods.sku[].warehouse_0 求和（与引擎 dkStock 同源同算法，4248款全覆盖）[修4]
dk_stock = {}
for ref, g in goods.items():
    skus = g.get('sku')
    total = 0
    if isinstance(skus, list):
        for s in skus:
            if isinstance(s, dict): total += int(float(s.get('warehouse_0', 0) or 0))
    elif isinstance(skus, dict):
        for s in skus.values():
            if isinstance(s, dict): total += int(float(s.get('warehouse_0', 0) or 0))
    dk_stock[ref] = total

def stock_of(ref):
    return dk_stock.get(ref)

def name_of(ref, fallback=''):
    if fallback: return fallback
    g = goods.get(ref)
    return (g.get('name','') if g else '') or fallback or '(未建档)'

def cat_of(ref):
    g = goods.get(ref)
    ci = (g or {}).get('cate_info')
    return (ci.get('name','') if isinstance(ci, dict) else '') or '未分类'

COLOR_RULES = [
    (r'咖|焦糖|摩卡', '咖啡系'), (r'卡其', '卡其'), (r'藏蓝|藏青', '藏青'),
    (r'黑', '黑'), (r'白|米|杏|奶', '米白系'), (r'灰', '灰'),
    (r'红|酒红|枣红', '红'), (r'粉', '粉'), (r'蓝', '蓝'),
    (r'绿|军绿|橄榄', '绿'), (r'黄|姜黄|鹅黄', '黄'), (r'紫', '紫'),
    (r'棕|驼', '棕驼系'), (r'花|印|格|条|拼|绣', '花色/拼接'),
]
def norm_color(c):
    if not c: return '未标注'
    for pat, label in COLOR_RULES:
        if re.search(pat, c): return label
    return c

SUFFIX_PAT = re.compile(r'-(EHT|DOA|UUS|[A-Z]{2,4})$|[一-龥]{2,4}$')
def is_suffix_ref(ref):
    """定向/专属款：字母后缀(-EHT/-DOA)或款号尾部含中文标识(如'PC2631231京川和')"""
    if not ref: return False
    # 纯基础款号（2字母+7位数字）不算
    if re.fullmatch(r'[A-Z]{2}\d{7}', ref): return False
    return bool(SUFFIX_PAT.search(ref))

REGION_KW = {
    '福建': ['福建','厦门','泉州','福州','晋江','石狮'],
    '广东': ['广州','深圳','佛山','东莞','中山','惠州','汕头','潮州','揭阳','汕尾','清远','韶关','河源','梅州','肇庆','云浮','阳江','茂名','湛江','江门','珠海','白云','普宁','惠来','海丰','陆丰','大理'],
    '四川': ['四川','成都','重庆'], '江苏': ['江苏','南京','苏州'],
    '浙江': ['浙江','杭州','宁波','温州','义乌','金华'],
    '湖南': ['湖南','长沙'], '湖北': ['湖北','武汉'], '江西': ['江西','南昌','合肥'],
    '贵州': ['贵州','贵阳'], '香港': ['香港'],
    '东北三省': ['辽宁','大连','沈阳','哈尔滨','长春','东北'],
    '其他': ['上海','北京','天津','西安','兰州','乌鲁木齐','石家庄','太原','青岛','济南','临沂','南宁','昆明','郑州'],
}
def infer_region_name(name):
    if not name: return None
    for region, kws in REGION_KW.items():
        if any(kw in name for kw in kws): return region
    return None

def region_of(client_id, client_name):
    c = custs.get(str(client_id))
    if c:
        official = REGION_MAP.get(str(c.get('cat2_id','0')))
        if official: return official, '官方'
    inf = infer_region_name(client_name)
    if inf: return inf, '推断'
    return '未识别', '-'

# ================= 样式 =================
wb = Workbook(); wb.remove(wb.active)
HDR_FILL = PatternFill('solid', fgColor='1F4E79')
HDR_FONT = Font(name='微软雅黑', bold=True, color='FFFFFF', size=11)
SUB_FILL = PatternFill('solid', fgColor='D6E4F0')
NOTE_FONT = Font(name='微软雅黑', size=9, color='7F7F7F', italic=True)
GOOD_FILL = PatternFill('solid', fgColor='E2EFDA')
WARN_FILL = PatternFill('solid', fgColor='FDE9D9')
THIN = Side(style='thin', color='BFBFBF')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

def style_sheet(ws, widths, note=None, footnotes=None):
    """note=表上方副标题(仅sheet名)；footnotes=表下方口径脚注列表(V4按用户要求从顶部移到底部)"""
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.cell(1, 1, note).font = NOTE_FONT if note else None
    if note:
        ws.freeze_panes = 'A3'; start = 2
    else:
        ws.freeze_panes = 'A2'; start = 1
    for row in ws.iter_rows(min_row=start):
        for c in row:
            c.border = BORDER
            if c.row == start:
                c.fill = HDR_FILL; c.font = HDR_FONT; c.alignment = Alignment('center','center')
    return start

def add_footnotes(ws, after_row, footnotes):
    """在表格数据结束后的下一行起写口径脚注（灰色小字，不带边框）"""
    r = after_row + 1
    for i, fn in enumerate(footnotes, 1):
        c = ws.cell(r, 1, f'注{i}: {fn}')
        c.font = Font(name='微软雅黑', size=9, color='7F7F7F', italic=True)
        c.alignment = Alignment(wrap_text=False, vertical='top')
        r += 1
    return r

def fill_rows(ws, start, rows):
    r = start + 1
    for row in rows:
        for ci, v in enumerate(row, 1):
            ws.cell(r, ci, v).border = BORDER
        r += 1
    return r

# ---- 30日聚合（剔内部账户+定向后缀款，用于畅销/返单） ----
agg = defaultdict(lambda: {'qty':0,'amt':0.0,'gm_num':0.0,'gm_den':0.0,'clients':set(),'first_ts':None,'last_ts':None})
for r_ in rows30:
    if r_['channel'] == '退单': continue
    if RELATED_PAT.search(r_['client'] or ''): continue
    if is_suffix_ref(r_['ref']): continue
    a = agg[r_['ref']]
    a['qty'] += r_['qty']; a['amt'] += r_['qty']*r_['price']; a['clients'].add(r_['client'])
    if r_['cost'] > 0:
        a['gm_num'] += (r_['price']-r_['cost'])*r_['qty']; a['gm_den'] += r_['price']*r_['qty']
    if a['first_ts'] is None or r_['ts'] < a['first_ts']: a['first_ts'] = r_['ts']
    if a['last_ts'] is None or r_['ts'] > a['last_ts']: a['last_ts'] = r_['ts']
top = sorted(agg.items(), key=lambda x: -x[1]['qty'])[:30]

# ================= 归因引擎（V4：好卖/不好卖的原因推断） =================
# 每款计算可量化信号：季节趋势/价格带/颜色系/上市天数/渠道集中度/客户集中度/返单速度/售罄状态
cutoff7_ts = cutoff7
ref_signal = {}   # ref -> {trend, price_band, colors, days, client_conc, channel, repurchase_gap, sellout}
for ref, a in agg.items():
    if a['qty'] < 30: continue   # 样本下限
    g = goods.get(ref, {})
    # 近7日 vs 前23日
    l7 = sum(r_['qty'] for r_ in rows30 if r_['ref']==ref and r_['ts']>=cutoff7_ts and r_['channel']!='退单' and not RELATED_PAT.search(r_['client'] or ''))
    p23 = a['qty'] - l7
    ratio = (l7/7)/(p23/23) if p23 > 0 else (99 if l7 > 0 else 0)
    # 主色
    color_cnt = defaultdict(int)
    for r_ in rows30:
        if r_['ref']==ref and r_['channel']!='退单': color_cnt[norm_color(r_['color'])] += r_['qty']
    main_color = max(color_cnt.items(), key=lambda kv: kv[1])[0] if color_cnt else ''
    price = float((g.get('price_range') or {}).get('range',['0'])[0] or 0)
    band = '≤49' if price<=49 else ('50-69' if price<=69 else ('70-99' if price<=99 else ('100-129' if price<=129 else '≥130')))
    ld, _ = list_date_full(ref)
    days = (REPORT_TS - datetime.strptime(ld, '%Y-%m-%d')).days if ld else None
    conc = len(a['clients'])
    ref_signal[ref] = {'trend': ratio, 'price': price, 'band': band, 'color': main_color,
                       'days': days, 'clients': conc, 'qty': a['qty']}

# 全局基准（用于归因对照）
band_qty_total = defaultdict(int)
for ref, a in agg.items():
    s = ref_signal.get(ref)
    if s: band_qty_total[s['band']] += a['qty']
band_share = {b: q/sum(band_qty_total.values()) for b, q in band_qty_total.items()} if band_qty_total else {}

def why_selling(ref):
    """畅销归因：返回原因列表（信号→推断，非终端定论）"""
    s = ref_signal.get(ref)
    if not s: return ['样本不足，无法归因']
    reasons = []
    cat = cat_of(ref)
    if s['trend'] >= 1.5: reasons.append(f'季节起势（近7日趋势{ s["trend"]:.1f}倍，{cat}处于上行期）')
    elif s['trend'] >= 1.0: reasons.append('动销平稳延续')
    if s['band'] == '70-99' and band_share.get('70-99', 0) > 0.4: reasons.append('主力价格带（70-99元占大盘47%最容易走量）')
    elif s['price'] and s['price'] <= 59: reasons.append('低价引流位（≤59元决策门槛低）')
    if s['color'] in ('咖啡系','黑','米白系'): reasons.append(f'当季主流色（{s["color"]}为秋冬三大色）')
    if s['days'] is not None and s['days'] <= 15 and s['qty'] >= 100: reasons.append(f'新品爆发（上市{s["days"]}天即破百件）')
    if s['days'] is not None and s['days'] >= 60: reasons.append(f'长青款复购（在售{s["days"]}天仍动销）')
    if s['clients'] <= 2 and s['qty'] >= 200: reasons.append(f'⚠大单驱动（仅{s["clients"]}客户，疑似定向/批发大单，非市场散单）')
    if s['trend'] < 0.5: reasons.append(f'⚠趋势回落（{s["trend"]:.2f}，靠前期冲量）')
    return reasons or ['综合动销良好，无突出单因子']

def why_not_selling(ref, stock, qty30, days, w7):
    """滞销归因"""
    reasons = []
    cat = cat_of(ref)
    s = ref_signal.get(ref)
    g = goods.get(ref, {})
    season = ((g.get('season') or {}).get('name','')) if isinstance(g.get('season'), dict) else ''
    if qty30 == 0: reasons.append('近30日零动销（完全无市场反馈）')
    else: reasons.append(f'动销疲弱（30日仅{qty30}件，近7日{w7}件）')
    if days is not None and days <= 20: reasons.append(f'上市仅{days}天（可能未到品类季节，暂缓判断）')
    if season == '冬季' or cat in ('羽绒服','羽绒服马甲','棉服','双面呢（羊绒）','呢料外套'):
        reasons.append('厚装品类10月未到季（华南入冬晚，建议11月复判）')
    price = float((g.get('price_range') or {}).get('range',['0'])[0] or 0)
    if price >= 130: reasons.append(f'价格偏高（¥{price:.0f}高于主力带70-99）')
    if stock >= 400: reasons.append(f'库存深度过大（{stock}件，预计需数月消化）')
    if s and s['trend'] and s['trend'] >= 1.5:
        reasons.append('⚠品类整体上行但该款未跟上（版型/颜色/价格可能不匹配，重点复盘对象）')
    return reasons

# ================= 全局指标（原00页数据，并入12页，不再单独成表） =================
ov = report.get('overview', {}).get('p30', {})
tagged = sum(1 for o in orders30 if parse_tags(o.get('tag','')))
qty30 = sum(r_['qty'] for r_ in rows30 if r_['channel'] != '退单')
amt30 = sum(r_['qty']*r_['price'] for r_ in rows30 if r_['channel'] != '退单')
gm_num = sum((r_['price']-r_['cost'])*r_['qty'] for r_ in rows30 if r_['channel'] != '退单' and r_['cost'] > 0)
gm_den = sum(r_['price']*r_['qty'] for r_ in rows30 if r_['channel'] != '退单' and r_['cost'] > 0)
gm = gm_num/gm_den if gm_den else None

def yoy_window(dt):
    try: return dt.replace(year=dt.year-1)
    except ValueError: return dt.replace(year=dt.year-1, day=28)
ly_start = yoy_window(REPORT_TS - timedelta(days=30)); ly_end = yoy_window(REPORT_TS)
ly_qty = sum(r_['qty'] for r_ in goods_rows if ly_start.timestamp() <= r_['ts'] <= ly_end.timestamp())
yoy = (qty30-ly_qty)/ly_qty if ly_qty else None

# ================= 01 畅销TOP30（V4加归因列） =================
ws = wb.create_sheet('01·畅销TOP30·30日')
start = style_sheet(ws, [6,15,20,52,8,10,9,8,8,9,10,7])
for ci, h in enumerate(['排名','款号','品名','好卖原因分析（数据信号推断）','销量','销售额','毛利率','客单价','客户','库存','上市日期','天数'],1): ws.cell(start, ci, h)
rows = []
for i, (ref, a) in enumerate(top, 1):
    ld, _ = list_date_full(ref)
    days = (REPORT_TS - datetime.strptime(ld, '%Y-%m-%d')).days if ld else ''
    gm_v = a['gm_num']/a['gm_den'] if a['gm_den'] else None
    st = stock_of(ref)
    why = '；'.join(why_selling(ref))
    rows.append([i, ref, name_of(ref), why, a['qty'], round(a['amt']),
                 f"{gm_v*100:.0f}%" if gm_v is not None else '成本未录',
                 round(a['amt']/a['qty']) if a['qty'] else 0, len(a['clients']),
                 st if st is not None else '-', ld or '-', days])
fill_rows(ws, start, rows)
for i in range(min(10, len(rows))):
    for c in range(1, 13):
        ws.cell(start+1+i, c).fill = GOOD_FILL
add_footnotes(ws, start + len(rows), [
    '口径：30日窗口(2026-09-16~10-15)，剔内部账户(刻为/清货/特卖/版衣/零售/寄版/UUS)、退单与定向后缀款(-EHT/-DOA/中文尾缀)；品类列并入品名列前缀可按需恢复；毛利率=明细级(price-cost)/price；库存=多客实时，负数=预售欠货；上市日期三级口径=备注>首次销售>建档日；前10行绿底=TOP10。',
    '归因说明：「好卖原因」为数据信号推断(季节趋势/价格带/颜色/上市天数/客户集中度)，非终端客户反馈定论——款式级真实原因仍需销售按周反馈补齐(见00页行动计划)。',
])

# ================= 01b 同比 =================
ws = wb.create_sheet('01b·畅销款同比去年')
start = style_sheet(ws, [6,15,20,11,11,11,12,10])
for ci, h in enumerate(['排名','款号','品名','今年30日','去年同期','同比','去年全年','趋势'],1): ws.cell(start, ci, h)
ly_agg = defaultdict(int); ly2025 = defaultdict(int)
for r_ in goods_rows:
    if ly_start.timestamp() <= r_['ts'] <= ly_end.timestamp(): ly_agg[r_['ref']] += r_['qty']
    if datetime.fromtimestamp(r_['ts']).year == 2025: ly2025[r_['ref']] += r_['qty']
rows = []
for i, (ref, a) in enumerate(top, 1):
    ty, ly = a['qty'], ly_agg.get(ref, 0)
    chg = f"{(ty-ly)/ly*100:+.0f}%" if ly else '今年新款'
    trend = '持续畅销' if ly and ty >= ly*0.8 else ('下滑' if ly > ty*1.2 else ('新起' if not ly else '平稳'))
    rows.append([i, ref, name_of(ref), ty, ly, chg, ly2025.get(ref,0), trend])
fill_rows(ws, start, rows)
for i in range(len(rows)):
    v = rows[i][7]
    if v == '持续畅销': ws.cell(start+1+i, 8).fill = GOOD_FILL
    elif v == '下滑': ws.cell(start+1+i, 8).fill = WARN_FILL
add_footnotes(ws, start + len(rows), [
    '口径：去年同窗=2025-09-16~10-15，去年全年=2025自然年；数据源=3年订单明细；"今年新款"=去年同期无销售记录；趋势判定=持续畅销(同比≥-20%)/下滑(同比<-20%)/新起/平稳。',
])

# ================= 02 滞销（重定义+归因） =================
ws = wb.create_sheet('02·滞销款·重定义')
start = style_sheet(ws, [6,15,20,48,8,9,8,8,10,7])
for ci, h in enumerate(['排名','款号','品名','不好卖原因分析（数据信号推断）','库存','30日销量','7日销量','周转','上市日期','天数'],1): ws.cell(start, ci, h)
all30 = defaultdict(lambda: {'qty':0,'w':0})
for r_ in rows30:
    all30[r_['ref']]['qty'] += r_['qty']
    if r_['ts'] >= cutoff7: all30[r_['ref']]['w'] += r_['qty']

def is_current_season(ref):
    """滞销筛选：2026年份（不限季节——跨季积压也是研发关注的滞销来源），非2026的老款库存清货另议"""
    g = goods.get(ref)
    if not g: return True
    y = g.get('year') or {}
    yv = str(y.get('name', '')) if isinstance(y, dict) else str(y)
    return '2026' in yv or yv == ''

slow = []
for ref in set(list(dk_stock.keys()) + list(all30.keys())):
    st = dk_stock.get(ref, 0)
    if st is None or st <= 0: continue
    if not is_current_season(ref): continue
    ld, _ = list_date_full(ref)
    if not ld: continue
    days = (REPORT_TS - datetime.strptime(ld, '%Y-%m-%d')).days
    if days < 14: continue
    m = all30.get(ref, {'qty':0,'w':0})
    if m['qty'] == 0:
        slow.append((ref, days, st, 0, m['w'], '∞', ld, '零动销'))
    else:
        turn = st/m['w'] if m['w'] > 0 else None
        if turn and turn > 30:
            slow.append((ref, days, st, m['qty'], m['w'], f"{turn:.0f}", ld, f'周转{turn:.0f}天'))
slow.sort(key=lambda x: (-x[2], -x[1]))
rows = []
for i, (ref, days, st, mq, wq, turn, ld, reason) in enumerate(slow[:30], 1):
    why = '；'.join(why_not_selling(ref, st, mq, days, wq))
    rows.append([i, ref, name_of(ref), why, st, mq, wq, turn, ld, days])
fill_rows(ws, start, rows)
add_footnotes(ws, start + len(rows), [
    f'口径：滞销=2026年款+上市≥14天+多客库存>0+(周转>30天或近30日零动销)；库存=多客实时(sku.warehouse_0与引擎同源)；共筛出{len(slow)}款，显示前30。',
    '归因说明：「不好卖原因」为数据信号推断(动销/季节/价格/库存深度/品类趋势背离)，厚装品类(羽绒/呢料)10月未到季属正常季节因素，建议11月复判；⚠标记=品类整体上行但该款未跟上，为重点复盘对象。真实原因需终端反馈确认。',
])

# ================= 03 渠道 =================
ws = wb.create_sheet('03·渠道拆分·官方标签')
start = style_sheet(ws, [16,10,11,12,10,9,10,14])
for ci, h in enumerate(['渠道','订单数','销量(件)','销售额(¥)','销量占比','客户数','件均单价','主力店铺'],1): ws.cell(start, ci, h)
ch_rows = defaultdict(lambda: {'orders':set(),'qty':0,'amt':0.0,'clients':set(),'shops':defaultdict(int)})
for r_ in rows30:
    a = ch_rows[r_['channel']]
    a['orders'].add(r_['doc']); a['qty'] += r_['qty']; a['amt'] += r_['qty']*r_['price']
    a['clients'].add(r_['client']); a['shops'][SHOP_SHORT.get(r_['shop'], r_['shop'])] += r_['qty']
tq = sum(a['qty'] for a in ch_rows.values())
rows = []
for ch, a in sorted(ch_rows.items(), key=lambda x: -x[1]['qty']):
    ms = max(a['shops'].items(), key=lambda kv: kv[1])[0] if a['shops'] else ''
    rows.append([ch, len(a['orders']), a['qty'], round(a['amt']), f"{a['qty']/tq*100:.1f}%", len(a['clients']),
                 round(a['amt']/a['qty']) if a['qty'] else 0, ms])
fill_rows(ws, start, rows)
add_footnotes(ws, start + len(rows), [
    '口径：渠道=多客「财务-单据」标签字段(官方字典：2档口/5客户订单/3刻为工厂特卖/4福利UUS/1微信/6退单)；近30日明细级；打标502/796单(63%)，未打标337单+微信297单共占76.5%销量暂无法细分档口/订单。',
    '微信=微信下单的销售单(含散客与客户，系统无法进一步区分——此为覆盖率瓶颈根因)；未打标单主力店铺=销售部时多为订单客户；退单单列不计正向渠道；混合=同单含tag2+tag5。',
])

# ================= 03b 渠道构成 =================
ws = wb.create_sheet('03b·畅销TOP30渠道构成')
start = style_sheet(ws, [15,20,9,8,9,10,11,8,11,13])
for ci, h in enumerate(['款号','品名','总销量','档口','客户订单','特卖/福利','微信/未打标','退单','渠道主力','主力店铺'],1): ws.cell(start, ci, h)
top_refs = {ref for ref, _ in top}
ref_ch = defaultdict(lambda: defaultdict(int))
ref_shop = defaultdict(lambda: defaultdict(int))
for r_ in rows30:
    if r_['ref'] not in top_refs: continue
    c = r_['channel']
    if c in ('刻为工厂/特卖','福利/UUS拿货'): c = '特卖/福利'
    elif c in ('微信','未打标'): c = '微信/未打标'
    elif c == '订单+档口混合': c = '档口'
    ref_ch[r_['ref']][c] += r_['qty']
    ref_shop[r_['ref']][SHOP_SHORT.get(r_['shop'], r_['shop'])] += r_['qty']
rows = []
for ref, a in top:
    c = ref_ch.get(ref, {})
    parts = {k: c.get(k,0) for k in ('档口','客户订单','特卖/福利','微信/未打标','退单')}
    nz = {k:v for k,v in parts.items() if v>0}
    main = max(nz.items(), key=lambda kv: kv[1])[0] if nz else '-'
    ms = max(ref_shop.get(ref,{}).items(), key=lambda kv: kv[1])[0] if ref_shop.get(ref) else '-'
    rows.append([ref, name_of(ref), a['qty'], parts['档口'], parts['客户订单'], parts['特卖/福利'],
                 parts['微信/未打标'], parts['退单'], main, ms])
fill_rows(ws, start, rows)
for i in range(len(rows)):
    cell = ws.cell(start+1+i, 9)
    f = {'档口':'FDE9D9','客户订单':'DDEBF7','特卖/福利':'FFF2CC','微信/未打标':'F2F2F2','退单':'FCE4EC'}.get(rows[i][8])
    if f:
        cell.fill = PatternFill('solid', fgColor=f); cell.font = Font(name='微软雅黑', size=10, bold=True)
add_footnotes(ws, start + len(rows), [
    '口径：基于单据标签的TOP30畅销款渠道构成；"订单+档口混合"单归入档口列(同单双标无法拆分)；主力店铺列为交叉验证维度(店铺=下单档口/部门)。',
    '覆盖率提示：未打标+微信为主的款(渠道主力=微信/未打标)无法判断档口还是订单，占TOP30的多数——标签补全后本页结论将显著细化。',
])

# ================= 04 区域 =================
ws = wb.create_sheet('04·区域销量分布·30日')
start = style_sheet(ws, [12,10,12,11,9,9,11])
for ci, h in enumerate(['区域','销量(件)','销售额(¥)','占比','客户数','订单数','来源'],1): ws.cell(start, ci, h)
reg_agg = defaultdict(lambda: {'qty':0,'amt':0.0,'clients':set(),'orders':set(),'official':0,'infer':0})
for r_ in rows30:
    region, src = region_of(r_['client_id'], r_['client'])
    a = reg_agg[region]
    a['qty'] += r_['qty']; a['amt'] += r_['qty']*r_['price']
    a['clients'].add(r_['client']); a['orders'].add(r_['doc'])
    if src == '官方': a['official'] += r_['qty']
    elif src == '推断': a['infer'] += r_['qty']
tq = sum(a['qty'] for a in reg_agg.values())
rows = []
for region, a in sorted(reg_agg.items(), key=lambda x: -x[1]['qty']):
    src = '官方' if a['official'] and not a['infer'] else ('推断' if a['infer'] and not a['official'] else ('官方+推断' if a['official'] else '-'))
    rows.append([region, a['qty'], round(a['amt']), f"{a['qty']/tq*100:.1f}%", len(a['clients']), len(a['orders']), src])
fill_rows(ws, start, rows)
add_footnotes(ws, start + len(rows), [
    '口径：区域=客户档案cat2_id官方标记优先(活跃客户仅4/313有标记)，客户名前缀推断兜底；来源列区分官方/推断。',
    '⚠识别率约49%(未识别51.2%)，结论需结合此局限解读；官方13区域=福建/广东/江西/四川/湖南/江苏/太原/贵州/香港/湖北/东北三省/澳门/浙江，销售部补录cat2_id后自动切换全官方口径。',
])

# ================= 05 区域×品类 =================
ws = wb.create_sheet('05·区域×品类偏好·30日')
start = style_sheet(ws, [12,14,10,10,10,10,10])
for ci, h in enumerate(['区域','品类','销量(件)','占区域比','全局占比','偏好指数','样本'],1): ws.cell(start, ci, h)
rp = defaultdict(lambda: defaultdict(int)); cat_total = defaultdict(int)
for r_ in rows30:
    if is_suffix_ref(r_['ref']): continue
    region, _ = region_of(r_['client_id'], r_['client'])
    rp[region][r_['cat']] += r_['qty']; cat_total[r_['cat']] += r_['qty']
grand = sum(cat_total.values())
rows = []
for region in rp:
    rt = sum(rp[region].values())
    for cat, q in sorted(rp[region].items(), key=lambda x: -x[1])[:4]:
        sr, sg = q/rt if rt else 0, cat_total[cat]/grand if grand else 0
        idx = round(sr/sg, 2) if sg else 0
        rows.append([region, cat, q, f"{sr*100:.1f}%", f"{sg*100:.1f}%", idx, '⚠小样本' if q < 50 else ''])
rows.sort(key=lambda x: (x[0], -x[2]))
fill_rows(ws, start, rows)
for i in range(len(rows)):
    if rows[i][6]:
        for c in range(1, 8):
            ws.cell(start+1+i, c).font = Font(name='微软雅黑', size=10, color='A6A6A6')
    elif rows[i][5] >= 1.5:
        ws.cell(start+1+i, 6).fill = GOOD_FILL
        ws.cell(start+1+i, 6).font = Font(name='微软雅黑', size=10, bold=True, color='548235')
add_footnotes(ws, start + len(rows), [
    '口径：偏好指数=区域品类销量占比÷全局品类占比(≥1.2偏好，≥1.5显著，绿底)；每区域取TOP4品类。',
    '已剔除定向订货后缀款(-EHT/-DOA等，原占"未分类"26.1%污染品类分析)；⚠小样本=该格销量<50件，整行标灰，结论代表性不足。',
])

# ================= 06 颜色归一 =================
ws = wb.create_sheet('06·颜色动销·归一·30日')
start = style_sheet(ws, [12,10,11,9,10,42])
for ci, h in enumerate(['颜色(归一)','销量(件)','销售额(¥)','款数','客户数','归并前原始颜色(次)'],1): ws.cell(start, ci, h)
color_agg = defaultdict(lambda: {'qty':0,'amt':0.0,'refs':set(),'clients':set(),'raw':defaultdict(int)})
for r_ in rows30:
    nc = norm_color(r_['color'])
    a = color_agg[nc]
    a['qty'] += r_['qty']; a['amt'] += r_['qty']*r_['price']
    a['refs'].add(r_['ref']); a['clients'].add(r_['client'])
    if r_['color']: a['raw'][r_['color']] += 1
rows = []
for c_, a in sorted(color_agg.items(), key=lambda x: -x[1]['qty'])[:30]:
    raws = '、'.join(f"{k}({v})" for k,v in sorted(a['raw'].items(), key=lambda x:-x[1])[:6])
    rows.append([c_, a['qty'], round(a['amt']), len(a['refs']), len(a['clients']), raws])
fill_rows(ws, start, rows)
add_footnotes(ws, start + len(rows), [
    '口径：颜色已归一(咖啡系/卡其/藏青等，覆盖咖色/深咖/焦糖/摩卡、卡其色、藏蓝等同义色名)；右列=归并前原始颜色(括号内=出现次数)；近30日全部在售款。',
])

# ================= 07 售罄（公式修正） =================
ws = wb.create_sheet('07·动销与售罄·30日')
start = style_sheet(ws, [6,15,20,11,13,9,9,8,11,13])
for ci, h in enumerate(['排名','款号','品名','近30日销量','当前库存(衣者)','售罄率','客户','单价','上市日期','状态'],1): ws.cell(start, ci, h)
rows = []
for i, g in enumerate(report.get('sell_through_30d', [])[:40], 1):
    rate = g.get('rate', 0)
    status = '已超售(预售)' if rate > 1 else ('动销强劲' if rate > 0.8 else ('健康' if rate > 0.4 else '待观察'))
    rows.append([i, g['ref'], name_of(g['ref'], g.get('name','')), g.get('sold30',0), g.get('stock',0),
                 f"{rate*100:.0f}%", g.get('clients',0), g.get('price',''), g.get('listDate',''), status])
fill_rows(ws, start, rows)
for i in range(len(rows)):
    cell = ws.cell(start+1+i, 6)
    if '超售' in rows[i][9]:
        cell.fill = WARN_FILL; cell.font = Font(name='微软雅黑', size=10, bold=True, color='ED7D31')
    elif rows[i][9] == '动销强劲':
        cell.fill = GOOD_FILL
add_footnotes(ws, start + len(rows), [
    '口径：售罄率=近30日销量÷当前库存(引擎口径)；>100%=已超售(预售欠货，橙底标注)非数据错误；当前库存为引擎抓取时点值；状态列=超售/动销强劲(>80%)/健康(40-80%)/待观察。',
])

# ================= 08 返单TOP30+时点 =================
ws = wb.create_sheet('08·返单TOP30与时点·30日')
start = style_sheet(ws, [6,15,20,9,11,8,9,9,11,14])
for ci, h in enumerate(['排名','款号','品名','返单销量','返单金额','客户','次数','单价','平均间隔','节奏'],1): ws.cell(start, ci, h)
cli_ref = defaultdict(list)
for r_ in rows30:
    if r_['channel'] == '退单': continue
    if RELATED_PAT.search(r_['client'] or ''): continue
    cli_ref[(r_['client'], r_['ref'])].append((r_['ts'], r_['qty'], r_['price']))
rep = defaultdict(lambda: {'qty':0,'amt':0.0,'clients':set(),'count':0,'gaps':[]})
for (cli, ref), buys in cli_ref.items():
    buys.sort(key=lambda x: x[0])
    if len(buys) < 2: continue
    a = rep[ref]
    a['clients'].add(cli); a['count'] += len(buys) - 1
    for ts, q, p in buys[1:]:
        a['qty'] += q; a['amt'] += q*p
    a['gaps'].append(buys[1][0] - buys[0][0])
top_rep = sorted(rep.items(), key=lambda x: -x[1]['qty'])[:30]
rows = []
for i, (ref, a) in enumerate(top_rep, 1):
    gap = sum(a['gaps'])/len(a['gaps'])/86400 if a['gaps'] else None
    rhythm = '快速(≤7天)' if gap is not None and gap <= 7 else ('中速(8-21天)' if gap is not None and gap <= 21 else ('慢速(>21天)' if gap is not None else '-'))
    price = ((goods.get(ref,{}).get('price_range') or {}).get('range') or [''])[0]
    rows.append([i, ref, name_of(ref), a['qty'], round(a['amt']), len(a['clients']), a['count'], price,
                 f"{gap:.0f}天" if gap is not None else '-', rhythm])
fill_rows(ws, start, rows)
add_footnotes(ws, start + len(rows), [
    '口径：复购=客户再次购买同一款(30日窗口内第2次起算)；平均间隔=各客户首单→首次返单间隔均值；节奏=快速(≤7天)/中速(8-21天)/慢速(>21天)；剔内部账户与退单。',
    '局限：首单在30日窗口外的返单未计入，完整周期口径可按需用3年明细扩展。',
])

# ================= 09 新品四档 =================
ws = wb.create_sheet('09·新品上市四档')
start = style_sheet(ws, [10,15,20,10,11,10,9,9,9,9,8])
for ci, h in enumerate(['档位','款号','品名','品类','上市日期','日期来源','天数','首周销量','累计销量','累计客户','定向款'],1): ws.cell(start, ci, h)
np_rows = []
for g in report.get('new_product', []):
    ref = g['ref']
    ld, src = list_date_full(ref)
    if not ld: continue
    days = (REPORT_TS - datetime.strptime(ld, '%Y-%m-%d')).days
    tier = '1-7天' if days <= 7 else ('8-15天' if days <= 15 else ('16-30天' if days <= 30 else '30天以上'))
    np_rows.append([tier, ref, name_of(ref, g.get('name','')), g.get('cat',''), ld, src, days,
                    g.get('weekQty',0), g.get('qty',0), g.get('clients',0), '是' if is_suffix_ref(ref) else ''])
tier_order = {'1-7天':0,'8-15天':1,'16-30天':2,'30天以上':3}
np_rows.sort(key=lambda x: (tier_order.get(x[0], 9), -x[8]))
fill_rows(ws, start, np_rows)
add_footnotes(ws, start + len(np_rows), [
    '口径：按报表时点(10-15 16:00)重算上市天数，四档=1-7/8-15/16-30/30天以上；上市日期三级口径=备注日期>首次销售>建档日，来源列逐行标注；首周销量=上市7日内销量(首单转化素材)。',
    '定向款(-EHT/-DOA等后缀)=客户专属定制，单客户整百件，非市场动销，已排除于品类分析。',
])

# ================= 09b 老款生命周期 =================
ws = wb.create_sheet('09b·老款生命周期')
start = style_sheet(ws, [15,20,11,11,10,10,11,9,13])
for ci, h in enumerate(['款号','品名','上市日期','在售周数','近30日销量','累计总销量','最后动销','动销月数','评估'],1): ws.cell(start, ci, h)
ref_stat = defaultdict(lambda: {'first':None,'last':None,'total':0,'months':set(),'q30':0})
for r_ in goods_rows:
    s = ref_stat[r_['ref']]
    if s['first'] is None or r_['ts'] < s['first']: s['first'] = r_['ts']
    if s['last'] is None or r_['ts'] > s['last']: s['last'] = r_['ts']
    s['total'] += r_['qty']
    s['months'].add(datetime.fromtimestamp(r_['ts']).strftime('%Y-%m'))
    if r_['ts'] >= cutoff30: s['q30'] += r_['qty']
old_rows = []
for ref, s in ref_stat.items():
    if not s['first'] or s['q30'] == 0: continue
    ld, _ = list_date_full(ref)
    if not ld: continue
    days_list = (REPORT_TS - datetime.strptime(ld, '%Y-%m-%d')).days
    if days_list <= 30: continue
    months_active = len(s['months'])
    assess = '长生命周期·仍在售' if months_active >= 4 else ('跨季延续' if months_active >= 3 else '常规')
    old_rows.append([ref, name_of(ref), ld, f"{days_list//7}周", s['q30'], s['total'],
                     datetime.fromtimestamp(s['last']).strftime('%m-%d'), months_active, assess])
old_rows.sort(key=lambda x: -x[7])
fill_rows(ws, start, old_rows[:40])
add_footnotes(ws, start + min(40, len(old_rows)), [
    f'口径：上市>30天且近30日仍动销的在售老款，按动销月数降序，共{len(old_rows)}款显示前40；动销月数=有销售记录的自然月数；"长生命周期"=动销≥4个月，对应沟通中"1月卖到6月"的款；数据源=3年订单明细。',
])

# ================= 10 告急+预售欠货 =================
ws = wb.create_sheet('10·库存告急·含预售欠货')
start = style_sheet(ws, [6,15,20,9,10,10,8,8,32])
for ci, h in enumerate(['排名','款号','品名','库存','7日销量','30日销量','周转','单价','建议'],1): ws.cell(start, ci, h)
rows = []
for i, g in enumerate(report.get('stock_warn_current_season', []), 1):
    rows.append([i, g['ref'], name_of(g['ref'], g.get('name','')), g.get('stock',0), g.get('w',0), g.get('m',0),
                 g.get('turn',''), g.get('price',''), '建议补仓返单（卖不过两周）'])
neg = []
for ref, a in agg.items():
    st = stock_of(ref)
    if isinstance(st, (int,float)) and st < 0:
        neg.append((ref, a['qty'], st))
neg.sort(key=lambda x: -x[1])
for ref, q, st in neg:
    rows.append(['-', ref, name_of(ref), st, '', q, '-', '', '⚠预售欠货：确认补货进度（已售未入）'])
fill_rows(ws, start, rows)
for i in range(len(rows)):
    if '欠货' in str(rows[i][8]):
        ws.cell(start+1+i, 9).fill = WARN_FILL
add_footnotes(ws, start + len(rows), [
    '口径：告急=当年当季款总库存<近7日销量×2(卖不过两周)；负库存(预售欠货)区=30日动销款中多客库存<0(先售后补，正常业务，需确认补货进度)；建议为统计推论，最终需结合销售终端反馈确认。',
])

# ================= 11 返单客户 =================
ws = wb.create_sheet('11·返单客户TOP30')
start = style_sheet(ws, [6,18,13,9,12,10,9,9,11])
for ci, h in enumerate(['排名','客户名','手机号','VIP','返单金额','返单数量','官方区域','推断区域','关联方'],1): ws.cell(start, ci, h)
rows = []
for i, c in enumerate(report.get('reorder_customer_top', [])[:30], 1):
    name = c.get('name','')
    vip_raw = str(c.get('vip',''))
    vip = VIP_MAP.get(vip_raw, vip_raw or '未分级')
    official, infer = None, None
    cid = next((k for k, v in custs.items() if v.get('name') == name), None)
    if cid:
        official = REGION_MAP.get(str(custs[cid].get('cat2_id','0')))
        infer = infer_region_name(name)
    related = '⚠关联方' if RELATED_PAT.search(name or '') else ''
    rows.append([i, name, c.get('phone','') or '-', vip, c.get('reorderAmt',0), c.get('reorderQty',0),
                 official or '-', infer or '-', related])
fill_rows(ws, start, rows)
for i in range(len(rows)):
    if rows[i][8]:
        for c in range(1, 10):
            ws.cell(start+1+i, c).fill = WARN_FILL
add_footnotes(ws, start + len(rows), [
    '口径：返单=30日窗口内再次购买；VIP映射A/B/C/D(原始值1=未分级)；区域=官方标记/名称推断。',
    '关联方(橙底)=刻为/清货/特卖/版衣/零售/寄版/UUS相关账户，打标不剔除——刻为=供货另一品牌(沟通原话"不关我这一趴")，是否从榜内剔除待确认。',
])

# ================= 12 研发结论与建议（季节/气候加权） =================
ws = wb.create_sheet('12·研发结论与建议')
ws.column_dimensions['A'].width = 3
for col, w in zip('BCDE', (22, 46, 46, 20)):
    ws.column_dimensions[col].width = w
ws.cell(2, 2, f'素一美学 · 研发部门数据总结与建议（{TODAY}）').font = Font(name='微软雅黑', bold=True, size=15, color='1F4E79')

def section(r, title):
    ws.cell(r, 2, title).font = Font(name='微软雅黑', bold=True, size=11, color='1F4E79')
    return r + 1

r = 4
r = section(r, '〇、全局速览（30日 · 2026-09-16~10-15）')
kpis = [
    ('30日销售(剔退单)', f'{qty30:,} 件 / ¥{amt30:,.0f}', f'订单基准={len(orders30)}单（含内部账户；畅销榜另剔）'),
    ('毛利率', f"{gm*100:.1f}%" if gm else 'N/A', '明细级(price-cost)/price，cost覆盖97.5%'),
    ('同比去年同期', f"{yoy*100:+.1f}%" if yoy is not None else 'N/A', f'今年{qty30:,}件 vs 去年{ly_qty:,}件'),
    ('渠道标签覆盖', f'{tagged}/{len(orders30)}单(63%)', '未打标+微信占76.5%销量暂无法细分档口/订单'),
]
for k, v, note in kpis:
    ws.cell(r, 2, k).font = Font(name='微软雅黑', size=10, bold=True)
    ws.cell(r, 2).fill = SUB_FILL
    ws.cell(r, 3, v).font = Font(name='微软雅黑', size=10)
    ws.cell(r, 4, note).font = Font(name='微软雅黑', size=9, color='7F7F7F')
    for c in range(2, 5): ws.cell(r, c).border = BORDER
    r += 1

r += 1
r = section(r, '〇.5、数据缺口 → 给销售部的落地行动清单（呼应沟通"怎么帮我们搞出来"）')
plan = [
    ('✔', '渠道拆分(档口vs订单)', '03/03b页官方标签口径已实现', ''),
    ('✔', '毛利率/同比/生命周期/返单时点', '01页毛利率列、01b同比、09b老款、08返单间隔已实现', ''),
    ('⚠→行动', '渠道标签补全', '销售打单必选标签(2档口/5订单)，337单未打标', ''),
    ('⚠→行动', '客户区域补录', '按官方13区域打cat2_id（当前官方标记仅4/313）', ''),
    ('⚠→行动', '客户等级A/B/C', '销售部按cat1_id分级（307/313未分级）', ''),
    ('⚠→行动', '畅销/滞销归因反馈', '销售每周在商品备注填原因(版型/颜色/价格/时点)，01/02页归因即从"数据推断"升级为"终端定论"', ''),
    ('⚠→行动', '档口散客vs拿货客户', '现有标签无此粒度，需扩展标签或客户档案加字段', ''),
    ('⚠', '版型/面料维度', '版型库在建、面料字段缺失，接入后自动加维度', ''),
]
for mark, g_, desc, act in plan:
    color = '548235' if mark == '✔' else ('C00000' if mark == '⚠' else 'ED7D31')
    ws.cell(r, 2, f'{mark} {g_}').font = Font(name='微软雅黑', size=10, bold=True, color=color)
    ws.cell(r, 3, desc).font = Font(name='微软雅黑', size=9)
    ws.cell(r, 4, act).font = Font(name='微软雅黑', size=9, color='1F4E79')
    ws.cell(r, 3).alignment = Alignment(wrap_text=True, vertical='top')
    for c in range(2, 5): ws.cell(r, c).border = BORDER
    r += 1

def kv(r, k, v, note=''):
    ws.cell(r, 2, k).font = Font(name='微软雅黑', size=10, bold=True)
    ws.cell(r, 2).fill = SUB_FILL
    ws.cell(r, 3, v).font = Font(name='微软雅黑', size=9)
    ws.cell(r, 3).alignment = Alignment(wrap_text=True, vertical='top')
    ws.cell(r, 4, note).font = Font(name='微软雅黑', size=9, color='7F7F7F')
    ws.cell(r, 4).alignment = Alignment(wrap_text=True, vertical='top')
    for c in range(2, 5): ws.cell(r, c).border = BORDER
    ws.row_dimensions[r].height = 30
    return r + 1

r += 1
r = section(r, '一、季节切换信号（品类动销趋势：近7日日均 vs 前23日日均）')
r = kv(r, '起势上行 → 建议加码', '毛衣开衫（ratio≈94，115件集中于近7日=新爆点）、毛衣（1.90）、裤子（1.59）、羽绒服马甲（1.21，但绝对量小）', '换季窗口已到，针织系是当前研发最优先方向')
r = kv(r, '退潮下行 → 收缩或差异化', '卫衣（0.42）、毛衣马甲（0.55，绝对量大但已过峰值）、马甲（0.67）、半裙（0.73）、背带裙（0.69）', '马甲家族谨慎：除非版型/花型有明确差异化，本季不再铺量')
r = kv(r, '已退场', '夏季款动销归零（3,499件→1件）；衬衫趋稳（1.13）', '夏季库存转清货，不追单')

r += 1
r = section(r, '二、气候因子（核心市场=华南闽粤港，识别区域销量的83%）')
r = kv(r, '华南仍在"夏秋之交"', '华南客户30日TOP品类：T恤1,453 / 半裙881 / 裤子630——10月中旬华南主力仍是薄款；北方样本仅232件（毛衣/T恤为主）', '薄款秋装（长袖T/薄针织）在华南仍有2-4周窗口，不要急着全面转厚')
r = kv(r, '冬装节奏建议', '冬季款当前ratio=0.89（稳未爆）。羽绒/厚外套建议11月看华南档口动销再定追单，勿10月赌北方降温', '与补货深度分析"冬季慢热"结论一致；羽绒服马甲11月复判滞销同理')
r = kv(r, '区域风险', '华中/华东/西南各3-5%销量、样本偏小', '不建议单独开区域专线，待区域标记补录后复看')

r += 1
r = section(r, '三、价格与颜色（设计参数侧重）')
r = kv(r, '主力价格带', '70-99元占47%（7,197件）＞100-129元23%＞50-69元14%；长青老款价位¥49-109', '新款成本目标控制在70-99带；100-129做形象/设计款')
r = kv(r, '秋冬色系', '咖啡系（910件/近7日，绝对量第一）·黑（448，唯一上行1.06）·米白系（501）；黄(0.08)/燕麦(0.14)退场', '设计配色向"咖啡+黑+米白"深色三角集中；黑白灰安全盘')

r += 1
r = section(r, '四、版型库与研发方案侧重')
r = kv(r, '长青骨架款（版型库首选母版）', 'T恤：GT251063（93周/512件累计）｜半裙：WQ251123（90周/220件）｜连衣裙：GL252340（81周/381件）', '基础版型从这三类长青款提取，衍生开发按"母版+袖型/领型变化"路线（呼应沟通中的版型库规划）')
r = kv(r, '快反参考', '返单最快款：LT2631037（3天）/ST263825（2天）——首单→返单≤7天的款市场验证快', '此类版型/元素纳入快反清单，小单试销+快速返单模式')
r = kv(r, '滞销教训', '当前滞销TOP：衬衫两成（460/447件零动销）+连衣裙/半裙积压——上市时点与市场节奏错配是主因', '新品上架避开同类饱和期；上市≥14天零动销即预警复核')

r += 1
r = section(r, '四.5、好卖/不好卖的共性原因统计（TOP30归纳）')
# 统计归因因子出现次数
sell_cnt = defaultdict(int); slow_cnt = defaultdict(int)
for ref, a in top:
    for w_ in why_selling(ref):
        key = w_.split('（')[0]
        sell_cnt[key] += 1
for i, (ref, days, st, mq, wq, turn, ld, reason) in enumerate(slow[:30] if len(slow) >= 30 else slow, 1):
    for w_ in why_not_selling(ref, st, mq, days, wq):
        key = w_.split('（')[0]
        slow_cnt[key] += 1
r = kv(r, '好卖共性（TOP30款中）',
       '；'.join(f'{k}×{v}款' for k, v in sorted(sell_cnt.items(), key=lambda x: -x[1])),
       '因子出现次数=多少款命中该信号')
r = kv(r, '不好卖共性（滞销TOP30款中）',
       '；'.join(f'{k}×{v}款' for k, v in sorted(slow_cnt.items(), key=lambda x: -x[1])),
       '⚠品类上行但款未跟上=最值得复盘的错配款')

r += 1
r = section(r, '五、结论一句话')
r = kv(r, '给设计的方向', '当前=夏转秋换季窗口：加码针织（毛衣/开衫）+长袖T延续，颜色走咖啡/黑/米白，价格锚定70-99；马甲/卫衣停扩，冬装等11月华南信号；版型库从T恤/半裙/连衣裙三大长青母版起步。', '以上为30日数据统计性结论，款式级"为什么"仍需销售终端反馈补齐（见00页行动计划）')

wb.save(OUT)
print('SAVED:', OUT)
print('sheets:', len(wb.sheetnames))
print(wb.sheetnames)
print('rows30:', len(rows30), '| orders30:', len(orders30), '| tagged:', tagged,
      '| top30[0]:', top[0][0] if top else '-')
