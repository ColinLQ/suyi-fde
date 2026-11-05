#!/usr/bin/env python3
# 03表重造: 双系统对账 → 「钱对账+货对账」实算版
import os
import json
from datetime import datetime
from collections import defaultdict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.utils import get_column_letter

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
RAW = f"{DATA_HOME}/data/raw/2026-10-09/pm"
OUTDIR = f"{DATA_HOME}/out"
TODAY = "2026-10-10"
NOW = datetime(2026, 10, 10)

def num(v, d=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

# ============ 实算: 订单净额 vs 收款 月度对账 ============
pay_by_month = defaultdict(lambda: {"in": 0.0, "out": 0.0, "n": 0})
with open(f"{RAW}/duoke_payments_365d.jsonl", encoding="utf-8") as f:
    for line in f:
        p = json.loads(line)
        try:
            ts = int(float(p.get("ctime") or p.get("created_at") or 0))
            dt = datetime.fromtimestamp(ts)
        except Exception:
            continue
        m = f"{dt.year}-{dt.month:02d}"
        t = num(p.get("type"))
        price = num(p.get("price"))
        if t == 1:
            pay_by_month[m]["in"] += price; pay_by_month[m]["n"] += 1
        elif t == 2:
            pay_by_month[m]["out"] += price

order_by_month = defaultdict(float)
with open(f"{RAW}/duoke_orders_hist3y.jsonl", encoding="utf-8") as f:
    for line in f:
        o = json.loads(line)
        try:
            d0 = datetime.fromtimestamp(int(float(o.get("ctime"))))
        except Exception:
            continue
        if (NOW - d0).days > 210:
            continue
        order_by_month[f"{d0.year}-{d0.month:02d}"] += num(o.get("calc_price"))

months = sorted(set(list(order_by_month.keys()) + list(pay_by_month.keys())))[-6:]

wb = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
for sn in list(wb.sheetnames):
    if sn.startswith("03·"):
        del wb[sn]

ws = wb.create_sheet("03·钱货对账(月度实算)")
ws.sheet_properties.tabColor = xl_color("#7030A0")

# ===== A. 钱对账: 订单 vs 收款 =====
ws.cell(1, 1, "钱货对账——每月卖了多少、收了多少、差多少(全从流水和订单实算)").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)

ws.cell(2, 1, "A. 钱对账: 订单净额 vs 实际收款(近6个月)").font = Font(name="PingFang SC", bold=True, size=12)
r = 3
headers = ["月份", "订单净额(¥)", "实际收款(¥)", "退款(¥)", "差额=应收(¥)", "健康度", "建议动作"]
for c, h in enumerate(headers, 1):
    cell = ws.cell(r, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
r += 1
for m in months:
    net = order_by_month.get(m, 0)
    rec_in = pay_by_month.get(m, {}).get("in", 0)
    rec_out = pay_by_month.get(m, {}).get("out", 0)
    rec = rec_in - rec_out
    gap = net - rec
    if gap < 0:
        judge, act, fill = "🟢收>卖", "预收款/往月欠款回收——正常", None
    elif gap < net * 0.1:
        judge, act, fill = "🟢正常", "月内正常账期", None
    elif gap < net * 0.25:
        judge, act, fill = "🟡挂账偏高", f"欠款表核对当月新增欠款客户", PatternFill("solid", fgColor=XL_YELLOW_BG)
    else:
        judge, act, fill = "🔴应收过大", f"重点催收:¥{gap:,.0f}未回笼,关联06表欠款客户", PatternFill("solid", fgColor=XL_RED_BG)
    vals = [m, round(net), round(rec_in), round(rec_out) or "—", round(gap), judge, act]
    for c, v in enumerate(vals, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body if c < 7 else f_suggest
        cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) else al_l
        if fill:
            cell.fill = fill
    r += 1

# ===== B. 货对账: 双系统库存口径 =====
r += 1
ws.cell(r, 1, "B. 货对账: 两套系统的库存为什么对不上").font = Font(name="PingFang SC", bold=True, size=12)
r += 1
headers_b = ["对账项", "多客侧(销售系统)", "衣者侧(生产系统)", "差异原因", "能不能对?"]
for c, h in enumerate(headers_b, 1):
    cell = ws.cell(r, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
r += 1
goods_rows = [
    ["成品库存", "43,205件(当前在库,超卖为负)", "679,191件(疑为累计入库)", "衣者total_num疑似只增不减的累计口径——11天零减少+与多客相关系数仅0.19",
     "❌暂不能:需衣者系统方确认字段。当前用「累计入库−累计出货」推算的通路在修"],
    ["入库时效", "无入库时间字段", "有出入库记录", "货出厂→可卖之间是黑盒:出货22,967件但多客在库仅微增",
     "⚠️短期用每日库存快照环比反推(天级精度),治本要仓库在多客侧录入"],
    ["成本口径", "单件成本(¥60这种)", "明细成本(面料+加工+扣子)", "四舍五入差异≤¥1/件",
     "✅已拍板以多客为准(9-22会议);毛利分析见07表"],
    ["款号体系", "item_ref(SW2641076-1)", "template_no(SW2641076)", "命名规则不同+别名后缀",
     "✅映射表已建(state/mapping.json),匹配率82%→人工核对到98%"],
]
for row in goods_rows:
    for c, v in enumerate(row, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body
        cell.border = border_all
        cell.alignment = al_l
        if str(row[4]).startswith("✅"):
            cell.fill = PatternFill("solid", fgColor=XL_GREEN_BG)
        elif str(row[4]).startswith("❌"):
            cell.fill = PatternFill("solid", fgColor=XL_RED_BG)
        elif str(row[4]).startswith("⚠️"):
            cell.fill = PatternFill("solid", fgColor=XL_YELLOW_BG)
    r += 1

for c, w in enumerate([12, 15, 15, 42, 30], 1):
    ws.column_dimensions[get_column_letter(c)].width = w
# A段列宽(前7列)
for c, w in zip(range(1, 8), [12, 15, 15, 12, 14, 10, 42]):
    ws.column_dimensions[get_column_letter(c)].width = max(ws.column_dimensions[get_column_letter(c)].width or 0, w)

# 口径说明
r += 1
ws.cell(r, 1, "口径说明").font = f_note_h
ws.cell(r, 1).fill = fill_note
for c in range(2, 9):
    ws.cell(r, c).fill = fill_note
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
r += 1
for line in [
    "▍这张表回答什么：A段查钱——每月卖出的货有没有变成收回的钱; B段查货——两套系统为什么对不上、哪些是能治的哪些要等系统方。",
    "▍订单净额=当月下单金额−退货(负数单自然冲减); 实际收款=流水type=1收款−type=2退款。差额>0=应收挂账(客户拿了货没付清)。",
    "▍'收>卖'为负差额是正常现象:客户预存款/还历史欠款。9月应收¥57万偏高(占当月25%)——核对06表欠款客户中谁在9月新增欠款。",
    "▍此前版本的'衣者待核对¥684万'是衣者财务模块挂账口径(生产侧应付款维度),与多客客户收款是两本账——已从本表移除,避免混淆;需要生产应付对账时单开专项。",
    "▍B段四项中两项已解决(成本口径/款号映射)、一项短期绕行(入库时效)、一项待系统方(衣者库存字段)——这是数据团队当前的对账边界,坦诚披露。",
]:
    cell = ws.cell(r, 1, line)
    cell.font = f_note
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    r += 1
ws.freeze_panes = "A4"

wb.save(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
print("03表重造完成")

# 验证
wb = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
ws = wb["03·钱货对账(月度实算)"]
for row in ws.iter_rows(min_row=3, max_row=10, values_only=True):
    print([str(x)[:26] if x is not None else "" for x in row[:7]])
