#!/usr/bin/env python3
# 将 V2 补货建议写入生产部Excel(07表) 
import json
from pathlib import Path
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.utils import get_column_letter

def xl_color(h):
    v = h.removeprefix("#").upper()
    return "FF" + v if len(v) == 6 else "FF000000"

XL_HEADER_BG = xl_color("#4472C4")
XL_RED_BG = xl_color("#FDE9E9")
XL_ORANGE_BG = xl_color("#FFF2E8")
XL_YELLOW_BG = xl_color("#FFFDE8")
XL_GREEN_BG = xl_color("#C6EFCE")
XL_BLUE_BG = xl_color("#E8F0FE")
thin = Side(style="thin", color=xl_color("#BFBFBF"))
border_all = Border(left=thin, right=thin, top=thin, bottom=thin)
f_header = Font(name="PingFang SC", bold=True, color="FFFFFFFF", size=11)
f_title = Font(name="PingFang SC", bold=True, size=14, color=xl_color("#1F2937"))
f_body = Font(name="PingFang SC", size=11)
f_note = Font(name="PingFang SC", size=9, color=xl_color("#6B7280"))
fill_header = PatternFill("solid", fgColor=XL_HEADER_BG)
al_c = Alignment(horizontal="center", vertical="center", wrap_text=True)
al_l = Alignment(horizontal="left", vertical="center", wrap_text=True)
al_r = Alignment(horizontal="right", vertical="center")

SKILL = str(Path(__file__).resolve().parent.parent)
TODAY = "2026-10-10"

data = json.load(open(f"{SKILL}/out/restock-v2-{TODAY}.json", encoding="utf-8"))
rows = data["rows"]

wb = openpyxl.load_workbook(f"{SKILL}/out/数据包-生产部-{TODAY}.xlsx")
# 删旧重建
for name in list(wb.sheetnames):
    if name.startswith("07·"):
        del wb[name]

ws = wb.create_sheet("07·补货建议V2·三因子对比")
ws.sheet_properties.tabColor = xl_color("#7030A0")
headers = ["级别", "款号", "品名", "品类", "季节气候", "库存", "在产",
           "近7日均", "近30日均", "生命周期日均", "生命周期位置", "品类同期日均",
           "预测日均", "未来30天需求", "V1净缺口", "V2净缺口", "差异", "备注"]
widths = [8, 13, 16, 9, 15, 8, 8, 8, 9, 11, 14, 12, 9, 12, 9, 9, 8, 22]

ws.cell(1, 1, "补货建议量 V2（三因子加权 × 生命周期系数 × 季节气候系数）").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
ws.cell(1, 1).alignment = al_l
for c, h in enumerate(headers, 1):
    cell = ws.cell(2, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all

for i, r in enumerate(rows):
    vals = [
        r.get("level"), r.get("item_ref"), r.get("name"), r.get("cate"), r.get("climate"),
        r.get("stock"), r.get("inprod"),
        r.get("recent7"), r.get("recent30"), r.get("life"), r.get("stage"), r.get("yoy"),
        r.get("pred"), r.get("future30"), r.get("v1_net"), r.get("v2_net"), r.get("diff"), r.get("note") or "",
    ]
    diff = r.get("diff") if isinstance(r.get("diff"), (int, float)) else 0
    if diff > 100:
        fill = PatternFill("solid", fgColor=XL_ORANGE_BG)   # 上调=防断货
    elif diff < -100:
        fill = PatternFill("solid", fgColor=XL_BLUE_BG)     # 下调=防过补
    else:
        fill = None
    for c, v in enumerate(vals, 1):
        cell = ws.cell(3 + i, c, v)
        cell.font = f_body; cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) and not isinstance(v, bool) else al_l
        if fill:
            cell.fill = fill

for c, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(c)].width = w
note = ("公式: 预测日均=0.5×近7/30日均 + 0.3×生命周期日均 + 0.2×品类去年同期日均(10-11月3年均值); "
        "未来30天=预测日均×生命周期系数(W1-2爬坡1.3/W3-6峰值1.5/W7-10平稳1.0/W11+衰减0.6,近7≥近30时≥1.2)×季节气候系数(冬款1.2/秋款1.0); "
        "V2净缺口=未来30天需求−库存−在产; 上限护栏=预测日均×1.5×45天。"
        "橙底=较V1上调(防断货), 蓝底=下调(防过补)。⚠️口径提示: V1的日均含SKU出库口径(含档口批量), V2用订单明细口径(零售下单)——两口径并存,差异大的款人工复核。")
nr = 3 + len(rows) + 1
ws.cell(nr, 1, note).font = f_note
ws.merge_cells(start_row=nr, start_column=1, end_row=nr, end_column=len(headers))
ws.cell(nr, 1).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
ws.row_dimensions[nr].height = 45
ws.freeze_panes = "D3"

wb.save(f"{SKILL}/out/数据包-生产部-{TODAY}.xlsx")
print(f"✅ 生产部Excel +V2对比表 ({len(rows)}款)")
print(f"sheets: {wb.sheetnames}")
