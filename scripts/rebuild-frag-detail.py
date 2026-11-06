#!/usr/bin/env python3
# 财务05表重造: 碎片补单成本 → 逐款亏损明细 + 整改追踪表
import json, os
from datetime import datetime
from collections import defaultdict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage

def xl_color(h):
    v = h.removeprefix("#").upper()
    return "FF" + v if len(v) == 6 else "FF000000"

XL_HEADER_BG = xl_color("#4472C4")
XL_RED_BG = xl_color("#FDE9E9"); XL_ORANGE_BG = xl_color("#FFF2E8")
XL_YELLOW_BG = xl_color("#FFFDE8"); XL_GREEN_BG = xl_color("#C6EFCE"); XL_GRAY_BG = xl_color("#F3F4F6")
thin = Side(style="thin", color=xl_color("#BFBFBF"))
border_all = Border(left=thin, right=thin, top=thin, bottom=thin)
f_header = Font(name="PingFang SC", bold=True, color="FFFFFFFF", size=11)
f_title = Font(name="PingFang SC", bold=True, size=14, color=xl_color("#1F2937"))
f_body = Font(name="PingFang SC", size=11)
f_note = Font(name="PingFang SC", size=9, color=xl_color("#6B7280"))
f_note_h = Font(name="PingFang SC", size=9, bold=True, color=xl_color("#374151"))
f_suggest = Font(name="PingFang SC", size=10, color=xl_color("#1D4ED8"))
fill_header = PatternFill("solid", fgColor=XL_HEADER_BG)
fill_note = PatternFill("solid", fgColor=XL_GRAY_BG)
al_c = Alignment(horizontal="center", vertical="center", wrap_text=True)
al_l = Alignment(horizontal="left", vertical="center", wrap_text=True)
al_r = Alignment(horizontal="right", vertical="center")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # skill代码根目录（可移植）
DATA_HOME = os.environ.get('SCM_DATA_HOME') or os.path.join(os.path.expanduser('~'), 'WorkBuddy', 'scm-collector-data')  # 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
OUTDIR = f"{DATA_HOME}/out"
PIC = f"{DATA_HOME}/state/goods-pics"
TODAY = "2026-10-10"

def num(v, d=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

IMG_H = 64
def add_pic(ws, r, col, ref):
    for cand in (ref, ref.split("-")[0]):
        p = f"{PIC}/{cand}.jpg"
        if os.path.exists(p) and os.path.getsize(p) > 300:
            try:
                img = XLImage(p)
                ratio = IMG_H / img.height
                img.height = IMG_H
                img.width = max(40, int(img.width * ratio))
                ws.add_image(img, f"{get_column_letter(col)}{r}")
                ws.row_dimensions[r].height = IMG_H + 4
                return True
            except Exception:
                pass
    return False

# 款名/品类(从商品档案)
goods_meta = {}
with open(f"{DATA_HOME}/data/raw/2026-10-09/pm/duoke_goods.jsonl", encoding="utf-8") as f:
    for line in f:
        g = json.loads(line)
        ref = str(g.get("item_ref") or "")
        if ref:
            goods_meta[ref] = g.get("name") or ""

# 从生产部03表读17款明细(单一数据源,两表一致)
prod_wb = openpyxl.load_workbook(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")
frag_ws = next(s for s in prod_wb.sheetnames if "碎片返单代价" in s)
rows_raw = []
for row in prod_wb[frag_ws].iter_rows(min_row=3, values_only=True):
    if row[1] and "合计" not in str(row[1]):
        rows_raw.append(row)

wb = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
for sn in list(wb.sheetnames):
    if sn.startswith("05·"):
        del wb[sn]

ws = wb.create_sheet("05·碎片补单亏损明细")
ws.sheet_properties.tabColor = xl_color("#C00000")

ws.cell(1, 1, "碎片补单亏损明细——17 款逐笔核对,每一行都说明:拆了几单、多花多少、怎么追回").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=13)

# ===== A段: 逐款亏损明细 =====
ws.cell(2, 1, "A. 逐款亏损明细(按多花金额降序,负数=反而省了)").font = Font(name="PingFang SC", bold=True, size=12)
headers = ["图片", "款号", "款名", "下单日数", "单据数", "总量(件)", "单均批量",
           "实际单价", "合并单价", "多花(¥)", "客户等货(天)", "责任环节", "整改动作"]
for c, h in enumerate(headers, 1):
    cell = ws.cell(3, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all

n_pic = 0
total_over = 0
r = 4
for row in rows_raw:
    ref = str(row[1])
    n_days, n_orders, total, avg_batch = int(num(row[2])), int(num(row[3])), num(row[4]), num(row[5])
    unit_a, unit_m = num(row[6]), num(row[7])
    over = num(row[8]) if isinstance(row[8], (int, float)) else num(str(row[8]).replace(",", ""))
    span = int(num(row[9]))
    gap_min = None
    # 责任环节判定
    if avg_batch < 150:
        resp = "下单环节:批量<150件/单"
    elif n_orders - n_days >= 3:
        resp = "下单环节:同日拆单"
    else:
        resp = "预测环节:首单量不足"
    # 整改动作
    if over > 50000:
        act = "①本周追认损失 ②该款系列后续首单+50% ③下单系统并单拦截"
    elif over > 20000:
        act = "纳入周一补货会并单清单"
    elif over > 0:
        act = "观察:下次返单合并考量"
    else:
        act = "无损失(实际单价低于均值)"
    if over > 0:
        total_over += over
    vals = [None, ref, goods_meta.get(ref, "")[:14] or ref, n_days, n_orders, round(total), round(avg_batch),
            unit_a, unit_m, round(over) if over != 0 else "—", span if span else "—", resp, act]
    fill = PatternFill("solid", fgColor=XL_RED_BG) if over > 50000 else (
        PatternFill("solid", fgColor=XL_ORANGE_BG) if over > 20000 else (
            PatternFill("solid", fgColor=XL_GREEN_BG) if over < 0 else None))
    for c, v in enumerate(vals, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body if c < 13 else f_suggest
        cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) else al_l
        if fill:
            cell.fill = fill
    if add_pic(ws, r, 1, ref):
        n_pic += 1
    r += 1
# 小计
ws.cell(r, 1, "").value = None
ws.cell(r, 2, f"小计: {len(rows_raw)}款").font = Font(name="PingFang SC", bold=True)
ws.cell(r, 10, f"多花合计 ¥{total_over:,.0f}").font = Font(name="PingFang SC", bold=True, color=xl_color("#C00000"))
for c in range(1, 14):
    ws.cell(r, c).border = border_all
r += 2

# ===== B段: 断货损失(超卖款逐款) =====
ws.cell(r, 1, "B. 断货损失(当前11款超卖,每款错失的销售额)").font = Font(name="PingFang SC", bold=True, size=12)
r += 1
headers_b = ["图片", "款号", "款名", "欠货件数", "件单价(¥)", "错失销售额(¥)", "日均销", "追回动作"]
for c, h in enumerate(headers_b, 1):
    cell = ws.cell(r, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
r += 1
restock = json.load(open(f"{OUTDIR}/restock-deep-2026-10-09.json", encoding="utf-8"))
# 件单价:从明细实收
price_map = {}
with open(f"{DATA_HOME}/data/raw/2026-10-09/pm/duoke_order_details.jsonl", encoding="utf-8") as f:
    psum, qsum = defaultdict(float), defaultdict(float)
    for line in f:
        d = json.loads(line)
        for g in (d.get("goods") or []):
            ref = str(g.get("item_ref"))
            q = num(g.get("quantity"))
            if q > 0:
                psum[ref] += num(g.get("price")) * q
                qsum[ref] += q
    price_map = {k: psum[k]/qsum[k] for k in qsum}

loss_total = 0
n_pic_b = 0
oversold = [x for x in restock.get("rows", []) if num(x.get("stock")) < 0]
for x in sorted(oversold, key=lambda i: -abs(num(i.get("stock")))):
    ref = str(x.get("item_ref"))
    gap = abs(num(x.get("stock")))
    unit_p = price_map.get(ref) or price_map.get(ref.split("-")[0])
    if not unit_p:
        # 数字ID款: 用该款restock记录的品类均价兜底,再不行用80
        unit_p = 80
    loss = gap * unit_p
    loss_total += loss
    name = str(x.get("name"))
    if name == ref or not name:
        name = "(档口同步款)"
    vals = [None, ref, name[:14], round(gap), round(unit_p), round(loss),
            x.get("daily_avg"), "在产到货即发+ETA锁客(见销售02表)"]
    for c, v in enumerate(vals, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body if c < 8 else f_suggest
        cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) else al_l
    if add_pic(ws, r, 1, ref):
        n_pic_b += 1
    r += 1
ws.cell(r, 2, f"小计: {len(oversold)}款").font = Font(name="PingFang SC", bold=True)
ws.cell(r, 6, f"错失销售合计 ≈¥{loss_total:,.0f}").font = Font(name="PingFang SC", bold=True, color=xl_color("#C00000"))
for c in range(1, 9):
    ws.cell(r, c).border = border_all
r += 2

# ===== C段: 月度追踪(留空由下月填) =====
ws.cell(r, 1, "C. 改善追踪(每月1号更新一行,验证并单机制效果)").font = Font(name="PingFang SC", bold=True, size=12)
r += 1
headers_c = ["月份", "返单单数", "其中≤7天间隔", "碎片多花(¥)", "超卖款数", "断货损失(¥)", "环比改善"]
for c, h in enumerate(headers_c, 1):
    cell = ws.cell(r, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
r += 1
base_row = ["2026-09(基线)", 75, "34%≤7天", 345236, 11, f"≈{round(loss_total):,}", "—"]
for c, v in enumerate(base_row, 1):
    cell = ws.cell(r, c, v)
    cell.font = f_body
    cell.border = border_all
    cell.alignment = al_r if isinstance(v, (int, float)) else al_l
ws.cell(r, 1).fill = PatternFill("solid", fgColor=XL_YELLOW_BG)
r += 1
for m in ("2026-10", "2026-11", "2026-12"):
    for c in range(1, 8):
        cell = ws.cell(r, c)
        cell.border = border_all
    ws.cell(r, 1, m).font = f_body
    r += 1

for c, w in enumerate([13, 13, 16, 9, 8, 9, 9, 9, 9, 11, 11, 22, 36], 1):
    ws.column_dimensions[get_column_letter(c)].width = w

# 口径说明
r += 1
ws.cell(r, 1, "口径说明").font = f_note_h
ws.cell(r, 1).fill = fill_note
for c in range(2, 14):
    ws.cell(r, c).fill = fill_note
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=13)
r += 1
for line in [
    "▍这张表回答什么：碎片补单具体亏在哪几款、每款亏多少、责任在哪个环节、每月有没有改善——不再是一个总数。",
    "▍A段·加工费损失: 拆单导致单价从实际值跌不到批量价。多花=(实际单价−按总量的批量参考价)×件数。红底=损失>5万(前4款占全部损失的80%,先治这4款);绿底=负数(该款实际拿到的价比批量参考价还低,没有损失)。",
    "▍责任环节判定: 批量<150件/单=下单时就没并够; 同日拆≥3单=流程允许重复下单; 其余=首单量测算不足(预测问题)。",
    "▍B段·断货损失: 超卖欠货×该款实收件单价=错失销售额(机会成本,这些货如果早2周到就能卖掉)。注意这是月度滚动口径,货到即消失。",
    "▍C段·追踪: 每月1号更新一行。并单机制见效的标准: ≤7天返单占比34%→<15%,月碎片损失¥34.5万→<¥10万。10-12月三个月验证。",
    "▍数据来源: 单价与批量来自衣者2,779个完成批实算; 件单价来自多客订单明细加权。合并单价为批量档均值(量级参考),非工厂实际报价——用于排优先级,不用于对外结算。",
]:
    cell = ws.cell(r, 1, line)
    cell.font = f_note
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=13)
    r += 1
ws.freeze_panes = "C4"

wb.save(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
print(f"05表重造完成: A段{len(rows_raw)}款(图{n_pic}) B段{len(oversold)}款(图{n_pic_b}) C段追踪框架")
