#!/usr/bin/env python3
# 07表重造: 成本三级回退(款明细加权→SKU进价→品类均) + 成本来源列
import os
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
from openpyxl.cell.cell import MergedCell

def xl_color(h):
    v = h.removeprefix("#").upper()
    return "FF" + v if len(v) == 6 else "FF000000"

XL_HEADER_BG = xl_color("#4472C4")
XL_GREEN_BG = xl_color("#C6EFCE"); XL_YELLOW_BG = xl_color("#FFFDE8"); XL_GRAY_BG = xl_color("#F3F4F6")
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

SKILL = str(Path(__file__).resolve().parent.parent)
RAW = f"{SKILL}/data/raw/2026-10-09/pm"
OUTDIR = f"{SKILL}/out"
PIC = f"{SKILL}/state/goods-pics"
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

# ===== 成本三级数据源 =====
# 1) 款级明细加权
det_cost = defaultdict(lambda: [0.0, 0.0])
cat_cost_sum = defaultdict(lambda: [0.0, 0.0])  # 品类均值
with open(f"{RAW}/duoke_order_details.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        for g in (d.get("goods") or []):
            c, q = num(g.get("cost")), num(g.get("quantity"))
            if c > 0 and q > 0:
                det_cost[str(g.get("item_ref"))][0] += c * q
                det_cost[str(g.get("item_ref"))][1] += q
            cat = g.get("category")
            cat = cat.get("name") if isinstance(cat, dict) else cat
            if c > 0 and q > 0 and cat:
                cat_cost_sum[cat][0] += c * q
                cat_cost_sum[cat][1] += q
det_avg = {k: v[0]/v[1] for k, v in det_cost.items() if v[1] > 0}
cat_avg = {k: v[0]/v[1] for k, v in cat_cost_sum.items() if v[1] > 0}

# 2) SKU进价 + 售价
sku_in, sale_price, goods_name = {}, {}, {}
with open(f"{RAW}/duoke_goods.jsonl", encoding="utf-8") as f:
    for line in f:
        g = json.loads(line)
        ref = str(g.get("item_ref") or g.get("id") or "")
        if not ref:
            continue
        goods_name[ref] = g.get("name") or ""
        pr = g.get("price_range") or {}
        rng = pr.get("range") or [] if isinstance(pr, dict) else []
        sale_price[ref] = num(rng[0]) if rng else 0
        prices = [num(s.get("price_in")) for s in (g.get("sku") or {}).values()
                  if isinstance(s, dict) and num(s.get("price_in")) > 0]
        if prices:
            sku_in[ref] = sum(prices) / len(prices)

alias_map = defaultdict(list)
for ref in set(list(det_avg.keys()) + list(sku_in.keys())):
    b = ref.split("-")[0].split("/")[0]
    if b != ref:
        alias_map[b].append(ref)

def cost_of(ref):
    """三级回退: 返回(成本, 来源标签)"""
    for cand in [ref, *alias_map.get(ref.split("-")[0], [])]:
        if cand in det_avg:
            return det_avg[cand], "①款明细加权"
    for cand in [ref, *alias_map.get(ref.split("-")[0], [])]:
        if cand in sku_in:
            return sku_in[cand], "②SKU进价"
    return None, None

sales = json.load(open(f"{OUTDIR}/销售数据报告-{TODAY}.json", encoding="utf-8"))
v2data = json.load(open(f"{OUTDIR}/restock-v2-{TODAY}.json", encoding="utf-8"))
v2map = {x["item_ref"]: x for x in v2data["rows"]}

wb = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
for sn in list(wb.sheetnames):
    if sn.startswith("07·"):
        del wb[sn]

ws = wb.create_sheet("07·款级毛利排行(30日Top30)")
ws.sheet_properties.tabColor = XL_HEADER_BG[2:]
headers = ["图片", "款号", "款名", "品类", "售价(¥)", "成本(¥)", "成本来源", "销量", "销售额(¥)",
           "实收均价(¥)", "毛利(¥)", "毛利率", "补货决策建议"]
widths = [13, 13, 16, 9, 8, 9, 13, 8, 11, 11, 9, 8, 34]
ws.cell(1, 1, "款级毛利排行——每款用自己能查到的最准成本,来源逐行标注").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
for c, h in enumerate(headers, 1):
    cell = ws.cell(2, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all

rows = []
n_pic = 0
src_stat = defaultdict(int)
for m in (sales.get("move_top_month") or [])[:30]:
    ref = str(m.get("ref"))
    cat = m.get("cat")
    price = sale_price.get(ref, 0)
    qty = num(m.get("qty"))
    amt = num(m.get("amt"))
    cost, src = cost_of(ref)
    if cost is None:
        cost = cat_avg.get(cat)
        src = "③品类均值" if cost else "无数据"
    src_stat[src] += 1
    avg_recv = amt / qty if qty > 0 else 0
    if cost and avg_recv > 0:
        gp = avg_recv - cost
        gpr = f"{gp/avg_recv*100:.0f}%"
    else:
        gp, gpr = None, ""
    # 建议
    v2 = v2map.get(ref) or v2map.get(ref.split("-")[0])
    sug = ""
    if src == "无数据":
        sug = "先补录该款进价(多客商品档案),毛利暂无法算"
    elif v2 and num(v2.get("v2_net")) > 500:
        sug = f"净缺口{int(num(v2['v2_net']))}件优先补"
        if gp is not None and gp / avg_recv >= 0.5:
            sug += ",毛利>50%加大批量摊薄"
    elif gp is not None and gp / avg_recv >= 0.5:
        sug = "高毛利:避免断货"
    elif gp is not None and gp / avg_recv < 0.2:
        sug = "低毛利:补货缩量/提价/换料"
    else:
        sug = "按V2建议量正常补"
    rows.append([None, ref, (goods_name.get(ref) or m.get("name") or ref)[:16], cat,
                 round(price) or "", round(cost, 1) if cost else "无", src,
                 round(qty), round(amt), round(avg_recv, 1), round(gp, 1) if gp is not None else "", gpr, sug])

for i, row in enumerate(rows):
    r = 3 + i
    src_fill = PatternFill("solid", fgColor=XL_GREEN_BG) if "①" in str(row[6]) else (
        PatternFill("solid", fgColor=XL_YELLOW_BG) if "③" in str(row[6]) else None)
    for c, v in enumerate(row, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body if c != 13 else f_suggest
        cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) else al_l
        if src_fill and c == 7:
            cell.fill = src_fill
    if add_pic(ws, r, 1, row[1]):
        n_pic += 1

for c, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(c)].width = w

r = 3 + len(rows) + 1
stat_line = "、".join(f"{k}×{v}款" for k, v in sorted(src_stat.items()))
ws.cell(r, 1, f"成本来源分布: {stat_line} —— ①最准(该款实际成交成本) ②准(SKU档案进价) ③兜底(同品类均值,黄底)").font = Font(name="PingFang SC", bold=True, size=10)
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
r += 2

ws.cell(r, 1, "口径说明").font = f_note_h
ws.cell(r, 1).fill = fill_note
for c in range(2, len(headers) + 1):
    ws.cell(r, c).fill = fill_note
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
r += 1
for line in [
    "▍这张表回答什么：卖得多的30款各赚多少钱——补货决策加毛利维度,高毛利款优先保供、低毛利款止损。",
    "▍成本为什么有的是品类均值: 多客的进价(price_in)由录入员手工填,部分新款上架时未填(如费尔岛马甲price_in=0)——此时明细cost也为空,只能用品类均值兜底并标黄。这些款补录进价后自动升级为②/①。",
    "▍三级回退: ①款明细加权=该款历史订单cost按数量加权(最准,反映实际成交) → ②SKU进价=多客商品档案(准,录入值) → ③品类均值(兜底,仅量级参考)。",
    "▍实收均价=销售额÷销量(零售实收含折扣); 毛利=实收均价−成本; 毛利率=毛利÷实收均价。",
    "▍无数据款的处理: 建议列已给出动作——去多客商品档案补录price_in,补录后本表自动用款价重算。",
    "▍精确到面料级的成本(面料+加工+辅料)在衣者BOM,月度成本核算时与多客口径交叉验证。",
]:
    cell = ws.cell(r, 1, line)
    cell.font = f_note
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
    r += 1
ws.freeze_panes = "C3"

wb.save(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
print(f"07表重造: {len(rows)}款 图{n_pic} | 来源分布: {dict(src_stat)}")
