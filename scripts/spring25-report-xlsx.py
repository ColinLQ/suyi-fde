#!/usr/bin/env python3
# 2025春季复盘 Excel 明细生成 V2 —— 图片直接内嵌显示（非URL链接）
import json, os, io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # skill代码根目录（可移植）
DATA_HOME = os.environ.get('SCM_DATA_HOME') or os.path.join(os.path.expanduser('~'), 'WorkBuddy', 'scm-collector-data')  # 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
YEAR = '2025'
for i, a in enumerate(sys.argv):
    if a == '--year' and i + 1 < len(sys.argv): YEAR = sys.argv[i + 1]
R = json.load(open(f'{DATA_HOME}/out/spring{YEAR[2:]}-review-data.json'))
CACHE = f'{DATA_HOME}/state/img-cache'

# ---- 图片工具：下载缓存 → 居中裁方 → 缩至64×64 PNG → openpyxl 内嵌 ----
def make_thumb(url):
    if not url:
        return None
    src = os.path.join(CACHE, url.split('/')[-1])
    if not os.path.exists(src):
        return None
    try:
        im = PILImage.open(src).convert('RGB')
        w, h = im.size
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2)).resize((64, 64), PILImage.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except Exception:
        return None

wb = Workbook()
hdr_fill = PatternFill('solid', fgColor='F59E0B')
hdr_font = Font(bold=True, color='FFFFFF', size=11)
thin = Side(style='thin', color='D9D9D9')
border = Border(left=thin, right=thin, top=thin, bottom=thin)
center = Alignment(horizontal='center', vertical='center')
IMG_COL_W, IMG_ROW_H = 10, 54  # 列宽约72px / 行高72px，容纳64×64图

def sheet_with_imgs(ws, title, headers, rows, widths, img_col=None, items=None):
    """rows: 数据行(不含图); img_col: 图片所在列号(1起); items: 每行的img url列表"""
    ws.title = title
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(1, c)
        cell.fill, cell.font, cell.alignment, cell.border = hdr_fill, hdr_font, center, border
    for r in rows:
        ws.append(r)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'A2'
    if img_col and items:
        letter = get_column_letter(img_col)
        ws.column_dimensions[letter].width = IMG_COL_W
        for i, url in enumerate(items):
            row = i + 2
            ws.row_dimensions[row].height = IMG_ROW_H
            cell = ws.cell(row, img_col)
            cell.alignment = center
            buf = make_thumb(url)
            if buf:
                img = XLImage(buf)
                img.anchor = f'{letter}{row}'
                ws.add_image(img)
            else:
                cell.value = '无图'
                cell.font = Font(color='999999', size=9)

# ============ 汇总 ============
ws = wb.active
data = [
    (f'{YEAR}春款数', R['totals']['totStyles']),
    ('SKU总数(单款单色)', R['skuStats']['skuTotal']),
    ('有效SKU(动销>100件)', R['skuStats']['validSku']),
    ('生产计划总量(件)', R['totals']['totPlan']),
    ('全周期净销量(件)', R['totals']['totQty']),
    ('净销售额(元)', R['totals']['totAmt']),
]
sheet_with_imgs(ws, '汇总', ['指标', '数值'], data, [24, 16])

# ============ 畅销/滞销 TOP20 ============
for key, title in [('hot20', '畅销TOP20'), ('cold20', '滞销TOP20')]:
    w = wb.create_sheet(title)
    rows = [[i + 1, x['ref'], x['name'], x['cat'], '', x['qty'], x['amt'], x['stock'], x['price'], x['ctime']] for i, x in enumerate(R[key])]
    sheet_with_imgs(w, title, ['排名', '款号', '品名', '品类', '图片', '净销量', '净销售额', '当前库存', '吊牌价', '建档日期'], rows, [6, 12, 22, 10, 10, 10, 12, 10, 8, 11], img_col=5, items=[x['img'] for x in R[key]])

# ============ 售罄率 ============
for key, title in [('selloutTop10', '全盘售罄率最高'), ('selloutLow10', '全盘售罄率最低')]:
    w = wb.create_sheet(title)
    rows = [[i + 1, x['ref'], x['name'], x['cat'], '', x['qty'], x['stock'], float(x['rate'])] for i, x in enumerate(R[key])]
    sheet_with_imgs(w, title, ['排名', '款号', '品名', '品类', '图片', '净销量', '当前库存', '售罄率%'], rows, [6, 12, 22, 10, 10, 10, 10, 9], img_col=5, items=[x['img'] for x in R[key]])

# ============ 超卖预警 ============
w = wb.create_sheet('超卖预警')
rows = [[x['ref'], x['name'], x['cat'], '', x['qty'], x['stock']] for x in R['oversellTop']]
sheet_with_imgs(w, '超卖预警', ['款号', '品名', '品类', '图片', '净销量', '当前库存(负)'], rows, [12, 24, 10, 10, 10, 12], img_col=4, items=[x.get('img','') for x in R['oversellTop']])

# ============ 品类售罄率 ============
w = wb.create_sheet('品类售罄率')
rows = []
for x in R['catTop5']: rows.append(['最高', x['cat'], x['styles'], round(x['qty']), round(x['stock']), float(x['rate'])])
for x in R['catLow5']: rows.append(['最低', x['cat'], x['styles'], round(x['qty']), round(x['stock']), float(x['rate'])])
sheet_with_imgs(w, '品类售罄率', ['榜单', '品类', '款数', '净销量', '库存', '售罄率%'], rows, [8, 14, 8, 11, 11, 9])

# ============ 库存最大TOP20 ============
w = wb.create_sheet('库存最大TOP20')
rows = [[i + 1, x['ref'], x['name'], x['cat'], '', x['stock'], x['qty']] for i, x in enumerate(R['stockTop20'])]
sheet_with_imgs(w, '库存最大', ['排名', '款号', '品名', '品类', '图片', '当前库存', '净销量'], rows, [6, 12, 22, 10, 10, 10, 10], img_col=5, items=[x['img'] for x in R['stockTop20']])

# ============ 上市动销 ============
for key, title in [('month1Top10', '上市1月动销最高'), ('month1Low10', '上市1月动销最低'), ('month2Top10', '上市2月动销最高'), ('month2Low10', '上市2月动销最低')]:
    w = wb.create_sheet(title[:30])
    rows = [[i + 1, x['ref'], x['name'], x['cat'], '', x.get('q30', x.get('q60', 0)), x['plan'], round(x.get('r30', x.get('r60', 0)) * 100)] for i, x in enumerate(R[key])]
    sheet_with_imgs(w, title[:28], ['排名', '款号', '品名', '品类', '图片', '窗口净销量', '计划产量', '动销率%'], rows, [6, 12, 22, 10, 10, 11, 10, 9], img_col=5, items=[x['img'] for x in R[key]])

# ============ 品类对比 ============
w = wb.create_sheet('品类生产vs销售')
rows = [[x['cat'], x['styles'], x['plan'], float(x['prodShare']), x['qty'], float(x['qtyShare']), x['amt'], float(x['amtShare']), round(float(x['prodShare']) - float(x['qtyShare']), 1)] for x in R['catCompare']]
sheet_with_imgs(w, '品类生产vs销售', ['品类', '款数', '计划产量', '产量占比%', '净销量', '销量占比%', '净销售额', '销售额占比%', '产-销偏差pct'], rows, [14, 8, 11, 10, 10, 10, 12, 11, 12])

# ============ 颜色对比 ============
w = wb.create_sheet('颜色生产vs销售')
cats = []
seen = set()
for x in R['colorCompare']['prod'] + R['colorCompare']['sale']:
    if x['c'] not in seen:
        seen.add(x['c']); cats.append(x['c'])
pmap = {x['c']: x for x in R['colorCompare']['prod']}
smap = {x['c']: x for x in R['colorCompare']['sale']}
rows = []
for c in cats:
    p, s = pmap.get(c), smap.get(c)
    if not p and not s: continue
    ps = float(p['share']) if p else 0.0
    ss = float(s['share']) if s else 0.0
    rows.append([c, p['n'] if p else 0, ps, s['n'] if s else 0, ss, round(ps - ss, 1)])
sheet_with_imgs(w, '颜色生产vs销售', ['颜色', '生产件数', '生产占比%', '销售件数', '销售占比%', '产-销偏差pct'], rows, [10, 11, 10, 11, 10, 12])

# ============ 价格段 ============
w = wb.create_sheet('价格段生产vs销售')
rows = [[x['band'], x['styles'], x['plan'], float(x['prodShare']), x['qty'], float(x['qtyShare']), x['amt'], round(float(x['prodShare']) - float(x['qtyShare']), 1)] for x in R['priceBands'] if x['styles'] > 0 or x['qty'] > 100]
sheet_with_imgs(w, '价格段', ['价格段', '款数', '计划产量', '产量占比%', '净销量', '销量占比%', '净销售额', '产-销偏差pct'], rows, [10, 8, 11, 10, 10, 10, 12, 12])

# ============ 有效SKU ============
w = wb.create_sheet('有效SKU明细')
rows = [[i + 1, x['ref'], x['name'], x['cat'], x['color'], x['qty']] for i, x in enumerate(R['skuStats']['validList'])]
sheet_with_imgs(w, '有效SKU', ['排名', '款号', '品名', '品类', '颜色', '净销量'], rows, [6, 12, 24, 10, 10, 10])

# ============ 返单/退货 ============
w = wb.create_sheet('返单款TOP10')
rows = [[i + 1, x['ref'], x['name'], x['cat'], '', x['qty'], x['reorderQty']] for i, x in enumerate(R['reorderTop10'])]
sheet_with_imgs(w, '返单TOP10', ['排名', '款号', '品名', '品类', '图片', '总净销量', '返单数量'], rows, [6, 12, 24, 10, 10, 11, 11], img_col=5, items=[x['img'] for x in R['reorderTop10']])

w = wb.create_sheet('退货款TOP10')
rows = [[i + 1, x['ref'], x['name'], x['cat'], '', x['qty'], x['retQty']] for i, x in enumerate(R['returnTop10'])]
sheet_with_imgs(w, '退货TOP10', ['排名', '款号', '品名', '品类', '图片', '净销量', '退货量'], rows, [6, 12, 24, 10, 10, 11, 10], img_col=5, items=[x['img'] for x in R['returnTop10']])

out = f'{DATA_HOME}/out/{YEAR}春季复盘-数据明细.xlsx'
wb.save(out)
nimg = sum(len(ws._images) for ws in wb.worksheets)
print('Excel V2 完成:', out, os.path.getsize(out) // 1024, 'KB | sheets:', len(wb.sheetnames), '| 内嵌图片:', nimg)
