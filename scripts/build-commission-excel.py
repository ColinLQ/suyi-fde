#!/usr/bin/env python3
# build-commission-excel.py — 首单30天卖完统计 Excel（单表版）
# 输入：out/commission-<月>.json（commission-firstsell.mjs 产出）
# 输出：out/首单30天卖完统计-<月>.xlsx —— 单张统计表：每款一行
#   销量格式："白216/黑220"（F码省略尺码）；带码SKU "黑M30/黑L40"；首单外颜色追加在尾部
import json, sys, os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

MONTH = sys.argv[1] if len(sys.argv) > 1 else '2026-09'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'out', f'commission-{MONTH}.json')
OUT = os.path.join(ROOT, 'out', f'首单30天卖完统计-{MONTH}.xlsx')

data = json.load(open(SRC))
results = data['results']; quality = data['quality']
# 数据截至日：取 json 生成时刻（明细数据mtime近似）
DATA_ASOF = datetime.fromtimestamp(os.path.getmtime(SRC)).strftime('%Y-%m-%d')

wb = Workbook()
thin = Border(*[Side(style='thin', color='D9D9D9')] * 4)
HEAD_FILL = PatternFill('solid', fgColor='4472C4')
HEAD_FONT = Font(bold=True, color='FFFFFF', size=11)
OK_FILL = PatternFill('solid', fgColor='C6EFCE')       # 全部卖完-绿
PART_FILL = PatternFill('solid', fgColor='FFEB9C')     # 部分卖完-黄
NO_FILL = PatternFill('solid', fgColor='F2F2F2')       # 未卖完-灰
NA_FILL = PatternFill('solid', fgColor='FCE4EC')       # 无法判定-红底
SUM_FILL = PatternFill('solid', fgColor='DDEBF7')

def seg(color, size, qty):
    """SKU段：F码→'黑94'；实码→'黑M30'；数量0也显示"""
    s = f'{color}{size if size not in ('', 'F', '-', None) else ''}{qty}'
    return s

def sales_str(skus, extra):
    """销量串：首单SKU按原顺序 + 首单外颜色追加"""
    parts = [seg(s['color'], s['size'], s.get(qtykey, 0)) for s in skus for qtykey in ['_dummy']][:0]  # placeholder
    return parts

def qty_chain(skus, extra_list, key):
    parts = [seg(s['color'], s['size'], s.get(key, 0)) for s in skus]
    for u in extra_list:
        parts.append(seg(u['color'], u.get('size', ''), u.get(key if key in u else 'qty', 0)) if key in u else seg(u['color'], u.get('size', ''), u['qty']))
    return '/'.join(parts)

ws = wb.active; ws.title = f'首单30天卖完-{MONTH}'
ws.append(['款号', '品名', '上架时间(多客备注)', '首单时间(多客首销)', '开始卖时间', '窗口结束(上架起30天)', '首单数量', '窗口内销量', '累计销量(至月底)', '累计销量(按颜色)', '差额总数', '窗口后退货冲减', '卖完情况(每款差额)', '颜色核对提示', '备注'])

RED = Font(color='C00000', bold=True)      # 差额正数（缺口）-红
GREEN = Font(color='2E7D32', bold=True)    # 差额负数（卖超）-绿
for r in results:
    skus = r.get('skus') or []
    ref = r['ref']
    fo = r.get('firstSale', '-') or '-'
    # 窗口后退货冲减串
    ar = r.get('afterReturn') or []
    ret_str = '/'.join(seg(u['color'], u['size'], u['qty']) for u in ar) if ar else '无'
    if not skus:
        ws.append([ref, r.get('name', ''), r.get('remarkDate') or '无', fo, r['T'], r['end'], '无首单记录', '-', '-', '-', '-', ret_str, '无法判定', '-', r.get('note', '')])
    else:
        # 首单数量串（降级款只有一行"全部颜色尺码"）
        if r.get('qtyBasis', '').startswith('计划数'):
            first_str = f"{r['firstQtyTotal']}(计划)"
            win_str = str(r.get('winTotal', 0))
            done_str = r.get('conclusion', '')
        else:
            first_str = '/'.join(seg(s['color'], s['size'], s['firstQty']) for s in skus)
            win_parts = [seg(s['color'], s['size'], s.get('soldQty', 0)) for s in skus]
            win_parts += [seg(u['color'], u.get('size', ''), u['qty']) for u in (r.get('unmatched') or [])]
            win_str = '/'.join(win_parts)
            sku_label = lambda s: s['color'] if s['size'] in ('', 'F', '-', None) else f"{s['color']}{s['size']}"
            marks = '/'.join((f"{sku_label(s)}✓" if s.get('soldOut') else f"{sku_label(s)}✗{s.get('gap', 0)}") for s in skus)
            done_str = f"{marks}（{r.get('conclusion','')}）"
        # 累计至统计月底（总数 + 按颜色）
        all_str = r.get('monthEndTotal', '-')
        by_color = r.get('monthEndByColor') or []
        color_str = '/'.join(f"{c['color']}{c['qty']}" for c in by_color) if by_color else '-'
        # 颜色核对提示：多客售出颜色 vs 衣者首单颜色对不上的
        ci = r.get('colorIssues') or []
        if not ci:
            check_str = '✓ 一致' if by_color else '-'
        else:
            parts = []
            for x in ci:
                if x['similar']:
                    parts.append(f"⚠ {x['color']}(近似{x['similar']}?)")
                else:
                    parts.append(f"⚠ {x['color']}(首单无此色)")
            check_str = '；'.join(parts)
        # 差额总数：负=未达标(红)，正=达标(绿)，0=刚好
        gap_t = r.get('gapTotal')
        gap_str = str(gap_t) if gap_t is not None else '-'
        # 备注：质量提示
        notes = []
        if r.get('note'): notes.append(r['note'])
        for q in quality:
            if q['ref'] == ref and q['issue'] != '无首单记录':
                notes.append(q['detail'] if q['issue'] == '首单批次间接关联' else ('含首单外颜色/尺码' if '首单外' in q['issue'] else q['detail']))
        ws.append([ref, r.get('name', ''), r.get('remarkDate') or '无', fo, r['T'], r['end'], first_str, win_str, all_str, color_str, gap_str, ret_str, done_str, check_str, '；'.join(notes)])
    conc = r.get('conclusion', '')
    fill = OK_FILL if conc == '全部卖完' else PART_FILL if conc.startswith('部分') else NO_FILL if conc == '未卖完' else NA_FILL
    for c in range(1, 16):
        ws.cell(ws.max_row, c).border = thin
        ws.cell(ws.max_row, c).alignment = Alignment(vertical='center')
    ws.cell(ws.max_row, 13).fill = fill
    # 颜色核对提示：有问题标黄底
    if check_str.startswith('⚠'):
        ws.cell(ws.max_row, 14).fill = PART_FILL
    # 差额总数颜色：负=未达标(红)，正=达标(绿)，0=刚好
    if gap_t is not None and isinstance(gap_t, (int, float)):
        ws.cell(ws.max_row, 11).font = RED if gap_t < 0 else GREEN if gap_t > 0 else Font(bold=True)

# 表头样式
for c in range(1, 16):
    cell = ws.cell(1, c); cell.fill = HEAD_FILL; cell.font = HEAD_FONT
    cell.alignment = Alignment(horizontal='center', vertical='center')
ws.freeze_panes = 'A2'
ws.auto_filter.ref = f"A1:O{ws.max_row}"
for col, w in zip('ABCDEFGHIJKLMNO', [13, 18, 15, 15, 11, 12, 30, 34, 13, 30, 10, 20, 34, 26, 24]):
    ws.column_dimensions[col].width = w

# 表尾口径注释
foot = ws.max_row + 2
notes = [
    '口径：开始卖时间=min(上架时间(多客备注),首单时间(多客首销))；窗口结束=上架日起共30个自然日（上架当天=第1天，即上架+29天，自然日含大小月，如8/16上架→9/14结束）；无备注的款用首销日期起算；',
    '仅纳入窗口结束月落在' + MONTH + '的款（共' + str(len(results)) + '款）；首单数量=衣者首单(production_type=1)入库SKU，"(计划)"标注=无入库明细降级用计划数；卖完判定=窗口内销量≥首单量（含退货负数冲减）；',
    '销量格式"白216/黑220"=按颜色（F码省略）；带尺码SKU如"黑M30"；累计销量=开始卖至' + MONTH + '月底（不分颜色总量 / 按颜色分解，含退货冲减）；数据截至' + DATA_ASOF + '；',
    '差额总数：任一颜色未达标→款未达标，差额=-Σ(未达标颜色缺口)为负数(红)；全部达标→差额=+Σ(超出量)为正数(绿)；0=刚好；卖完情况中"黑✗61"=黑色还差61件；',
    '颜色核对提示：多客累计售出颜色与衣者首单颜色比对，"⚠ 酱紫(首单无此色)"=多客有售但首单无此颜色；"(近似XX?)"=疑似同色异名需人工确认；一致则标✓；',
    '窗口后退货冲减=窗口结束日至月底的退货负数量按颜色/尺码汇总（"白-10"=白退10件）。',
]
for i, t in enumerate(notes):
    cell = ws.cell(foot + i, 1, t); cell.font = Font(size=9, color='808080')

wb.save(OUT)
print('→', OUT)
done = [r for r in results if r.get('conclusion') and r['conclusion'] != '无法判定']
print(f"{len(results)} 款 | 全部卖完 {sum(1 for r in done if r['conclusion']=='全部卖完')} | "
      f"部分 {sum(1 for r in done if r['conclusion'].startswith('部分'))} | 未卖完 {sum(1 for r in done if r['conclusion']=='未卖完')} | 无法判定 {len(results)-len(done)}")
