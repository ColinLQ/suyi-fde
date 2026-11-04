#!/usr/bin/env python3
# 终修: 清理重复图片 + 修财务07列错位
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
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
RAW = f"{SKILL}/data/raw/2026-10-09/pm"
OUTDIR = f"{SKILL}/out"
PIC = f"{SKILL}/state/goods-pics"
TODAY = "2026-10-10"

def num(v, d=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def ts2dt(v):
    try:
        s = str(v)
        if s.replace(".", "").isdigit() and len(s) >= 9:
            return datetime.fromtimestamp(int(float(s)))
    except Exception:
        pass
    return None

# 成本(加权)
ref_cost_qty = defaultdict(lambda: [0.0, 0.0])
ref_qty30 = defaultdict(float)
base_alias = defaultdict(list)
ref_all = set()
with open(f"{RAW}/duoke_order_details.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        for g in (d.get("goods") or []):
            dt = ts2dt(g.get("ctime"))
            qty = num(g.get("quantity"))
            if qty <= 0:
                continue
            ref = str(g.get("item_ref"))
            ref_all.add(ref)
            c = num(g.get("cost"))
            if c > 0:
                rc = ref_cost_qty[ref]
                rc[0] += c * qty; rc[1] += qty
            if dt and dt >= datetime(2026, 9, 10):
                ref_qty30[ref] += qty
for ref in ref_all:
    b = ref.split("-")[0].split("/")[0]
    if b != ref:
        base_alias[b].append(ref)

def cost_of(ref):
    for cand in (ref, *(base_alias.get(ref.split("-")[0], []))):
        cst = ref_cost_qty.get(cand)
        if cst and cst[1] > 0:
            return cst[0] / cst[1]
    return None

def qty30_of(ref):
    for cand in (ref, *(base_alias.get(ref.split("-")[0], []))):
        if cand in ref_qty30:
            return ref_qty30[cand]
    return 0

# 品类均值成本
cat_cost_sum = defaultdict(lambda: [0.0, 0.0])
with open(f"{RAW}/duoke_order_details.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        for g in (d.get("goods") or []):
            c, q = num(g.get("cost")), num(g.get("quantity"))
            cat = g.get("category")
            cat = cat.get("name") if isinstance(cat, dict) else cat
            if c > 0 and q > 0 and cat:
                cc = cat_cost_sum[cat]
                cc[0] += c * q; cc[1] += q
cat_avg_cost = {k: v[0]/v[1] for k, v in cat_cost_sum.items() if v[1] > 0}

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

# ---------- 研发部 02: 清图重插 ----------
print("研发部02 清图重插...")
wb1 = openpyxl.load_workbook(f"{OUTDIR}/数据包-研发部-{TODAY}.xlsx")
ws = wb1["02·爆款基因库·近30日动销Top30"]
ws._images = []   # 清全部旧图
# 找列
pic_col = ccol = None
for c in range(1, ws.max_column + 1):
    h = ws.cell(2, c).value
    if h == "图片":
        pic_col = c
    if h == "款号":
        ccol = c
n = 0
if pic_col and ccol:
    for r in range(3, ws.max_row + 1):
        ref = str(ws.cell(r, ccol).value or "")
        if ref and ref != "None" and add_pic(ws, r, pic_col, ref):
            n += 1
print(f"  重插{n}图")
wb1.save(f"{OUTDIR}/数据包-研发部-{TODAY}.xlsx")

# ---------- 生产部 01/02/07: 清图重插 ----------
print("生产部清图重插...")
wb2 = openpyxl.load_workbook(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")
for sn in ["01·周滚动补货计划(净缺口法)", "02·在产订单驾驶舱(190单)", "07·补货建议V2·三因子对比"]:
    ws = wb2[sn]
    ws._images = []
    pic_col = ccol = None
    for c in range(1, ws.max_column + 1):
        h = ws.cell(2, c).value
        if h == "图片":
            pic_col = c
        if h == "款号":
            ccol = c
    n = 0
    if pic_col and ccol:
        for r in range(3, ws.max_row + 1):
            ref = str(ws.cell(r, ccol).value or "")
            if ref and ref != "None" and add_pic(ws, r, pic_col, ref):
                n += 1
    print(f"  {sn[:12]}: 重插{n}图")
wb2.save(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")

# ---------- 财务部 07: 重建(修列错位) ----------
print("财务部07重建...")
wb4 = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
old = wb4["07·款级毛利排行(30日动销Top30)"]
# 读原数据(款号A, 款名B, 品类C, 售价D...插图列B后错位)——直接从sales JSON重建
sales = json.load(open(f"{OUTDIR}/销售数据报告-{TODAY}.json", encoding="utf-8"))
goods_meta = {}
with open(f"{RAW}/duoke_goods.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        g = json.loads(line)
        ref = str(g.get("item_ref") or g.get("id") or "")
        if ref:
            pr = g.get("price_range") or {}
            rng = pr.get("range") or [] if isinstance(pr, dict) else []
            goods_meta[ref] = {"name": g.get("name"), "price": num(rng[0]) if rng else 0}

for sn in list(wb4.sheetnames):
    if sn.startswith("07·"):
        del wb4[sn]

ws = wb4.create_sheet("07·款级毛利排行(30日动销Top30)")
ws.sheet_properties.tabColor = XL_HEADER_BG[2:]
headers = ["图片", "款号", "款名", "品类", "售价(¥)", "成本(¥)", "销量", "销售额(¥)", "实收均价(¥)", "毛利(¥)", "毛利率"]
widths = [14, 13, 20, 10, 9, 9, 8, 11, 11, 9, 8]
ws.cell(1, 1, "款级毛利排行（近30日动销Top30 · 成本=订单明细加权）").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
for c, h in enumerate(headers, 1):
    cell = ws.cell(2, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
n_pic = 0
rows = []
for m in (sales.get("move_top_month") or [])[:30]:
    ref = str(m.get("ref"))
    meta = goods_meta.get(ref, {})
    price = meta.get("price") or 0
    qty = num(m.get("qty"))
    amt = num(m.get("amt"))
    cst = cost_of(ref)
    cst_label = round(cst, 1) if cst else None
    if not cst:
        cst = cat_avg_cost.get(m.get("cat"))
        cst_label = f"{cst:.1f}(品类均)" if cst else "无成本数据"
    avg_recv = amt / qty if qty > 0 else 0
    gp = (avg_recv - cst) if (cst and not isinstance(cst_label, str)) or (cst and "(品类均)" in str(cst_label)) else None
    if cst and avg_recv > 0:
        gp = avg_recv - cst
        gpr = f"{gp/avg_recv*100:.0f}%{'*' if '(品类均)' in str(cst_label) else ''}"
    else:
        gp, gpr = None, ""
    rows.append([ref, m.get("name"), m.get("cat"), round(price) or "", cst_label,
                 round(qty), round(amt), round(avg_recv, 1), round(gp, 1) if gp is not None else "", gpr])
for i, row in enumerate(rows):
    r = 3 + i
    for c, v in enumerate([None] + row, 1):
        cell = ws.cell(r, c, v if c > 1 else None)
        cell.font = f_body; cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) else al_l
    if add_pic(ws, r, 1, row[0]):
        n_pic += 1
for c, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(c)].width = w
note = "成本=该款历史订单明细cost按数量加权; 新款无明细记录时用品类均值(标*)。实收均价=销售额÷销量。毛利率=(实收-成本)/实收。精确成本待月度核算(衣者面料+加工明细)。参考:毛衣类均值¥38.2/T恤¥30.4/马甲¥27.9。"
nr = 3 + len(rows) + 1
ws.cell(nr, 1, note).font = f_note
ws.merge_cells(start_row=nr, start_column=1, end_row=nr, end_column=len(headers))
ws.freeze_panes = "C3"
print(f"  重建{n_pic}图")
wb4.save(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")

# 终验
print("\n=== 终验 ===")
for dept in ["研发部", "生产部", "财务部"]:
    wb = openpyxl.load_workbook(f"{OUTDIR}/数据包-{dept}-{TODAY}.xlsx")
    total = sum(len(ws._images) for ws in wb.worksheets)
    print(f"{dept}: {total}图")
ws7 = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")["07·款级毛利排行(30日动销Top30)"]
for row in ws7.iter_rows(min_row=3, max_row=5, values_only=True):
    print("毛利:", str(row[1:8])[:120])
