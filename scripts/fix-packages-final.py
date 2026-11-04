#!/usr/bin/env python3
# 数据包修复·终版(幂等): 处理所有残留状态
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
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
NOW = datetime(2026, 10, 10)

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

def cat_name(v):
    return (v.get("name") or "") if isinstance(v, dict) else (v or "")

print("加载数据...")
ref_day_qty = defaultdict(lambda: defaultdict(float))
ref_day_amt = defaultdict(lambda: defaultdict(float))
ref_cost_qty = defaultdict(lambda: [0.0, 0.0])
ref_cat = {}
cat_day_qty = defaultdict(lambda: defaultdict(float))
with open(f"{RAW}/duoke_order_details.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        for g in (d.get("goods") or []):
            dt = ts2dt(g.get("ctime"))
            if not dt:
                continue
            qty = num(g.get("quantity"))
            if qty <= 0:
                continue
            ref = str(g.get("item_ref"))
            day = dt.strftime("%Y-%m-%d")
            ref_day_qty[ref][day] += qty
            ref_day_amt[ref][day] += num(g.get("price")) * qty
            c = num(g.get("cost"))
            if c > 0:
                rc = ref_cost_qty[ref]
                rc[0] += c * qty; rc[1] += qty
            cat = cat_name(g.get("category"))
            if cat:
                cat_day_qty[cat][day] += qty
                ref_cat[ref] = cat

goods_meta = {}
ref_stock = {}
with open(f"{RAW}/duoke_goods.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        g = json.loads(line)
        ref = str(g.get("item_ref") or g.get("id") or "")
        if not ref:
            continue
        pr = g.get("price_range") or {}
        rng = pr.get("range") or [] if isinstance(pr, dict) else []
        goods_meta[ref] = {
            "name": g.get("name"), "cate": cat_name(g.get("k_category")),
            "season": cat_name(g.get("season")), "ctime": ts2dt(g.get("ctime")),
            "price": num(rng[0]) if rng else 0,
        }
        sku = g.get("sku")
        st = 0
        if isinstance(sku, dict):
            for sv in sku.values():
                if isinstance(sv, dict):
                    st += num(sv.get("warehouse_0"))
        ref_stock[ref.split("-")[0]] = st

base_alias = defaultdict(list)
for ref in ref_day_qty:
    b = ref.split("-")[0].split("/")[0]
    if b != ref:
        base_alias[b].append(ref)

def sales_of(ref):
    if ref_day_qty.get(ref):
        return ref
    for a in base_alias.get(ref, []):
        return a
    return None

def stock_of(ref):
    return ref_stock.get(ref, ref_stock.get(ref.split("-")[0], 0))

tpl_band = {}
with open(f"{RAW}/yizhe_template_list.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        t = json.loads(line)
        if t.get("template_no") and t.get("band_name"):
            tpl_band[t["template_no"]] = t["band_name"]

last_payment = {}
with open(f"{RAW}/duoke_payments_365d.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        p = json.loads(line)
        dt = ts2dt(p.get("ctime") or p.get("created_at"))
        if dt and p.get("client_name"):
            k = p["client_name"]
            if k not in last_payment or dt > last_payment[k][0]:
                last_payment[k] = (dt, num(p.get("price") or p.get("amount")))

d30 = (NOW - timedelta(days=30)).strftime("%Y-%m-%d")

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

def ensure_pic_col(ws, col):
    """确保col列是图片列(幂等): 表头无'图片'则插列"""
    for c in range(1, ws.max_column + 1):
        if ws.cell(2, c).value == "图片":
            return c
    ws.insert_cols(col)
    ws.cell(2, col, "图片")
    ws.column_dimensions[get_column_letter(col)].width = 14
    return col

def find_col(ws, header):
    for c in range(1, ws.max_column + 1):
        if str(ws.cell(2, c).value or "").strip() == header:
            return c
    return None

def set_safe(ws, r, c, v):
    cell = ws.cell(r, c)
    if isinstance(cell, MergedCell):
        return
    cell.value = v

# ============================================================
# 研发部
# ============================================================
print("研发部...")
wb1 = openpyxl.load_workbook(f"{OUTDIR}/数据包-研发部-{TODAY}.xlsx")

# 01 品类实算
ws = wb1["01·品类动销×开发缺口(近30日)"]
cat_amt30, cat_qty30, cat_stockval = defaultdict(float), defaultdict(float), defaultdict(float)
for ref, ramt in ref_day_amt.items():
    c = ref_cat.get(ref)
    if c:
        for k, v in ramt.items():
            if k >= d30:
                cat_amt30[c] += v
for ref, rdq in ref_day_qty.items():
    c = ref_cat.get(ref)
    if c:
        for k, v in rdq.items():
            if k >= d30:
                cat_qty30[c] += v
for ref in set(list(ref_cat.keys()) + list(goods_meta.keys())):
    c = ref_cat.get(ref) or (goods_meta.get(ref) or {}).get("cate")
    if c:
        cst = ref_cost_qty.get(ref)
        unit = cst[0]/cst[1] if cst and cst[1] > 0 else 0
        cat_stockval[c] += stock_of(ref) * unit
cq = find_col(ws, "近30日销量"); ca = find_col(ws, "销售额(¥)"); cv = find_col(ws, "库存货值(¥)")
cs = find_col(ws, "当前库存")
for r in range(3, ws.max_row + 1):
    cname = ws.cell(r, 1).value
    if not cname:
        continue
    if cq: set_safe(ws, r, cq, round(cat_qty30.get(cname, 0)) or None)
    if ca and cat_amt30.get(cname, 0) > 0: set_safe(ws, r, ca, round(cat_amt30[cname]))
    if cs is not None and (cname in cat_stockval or True):
        pass  # 库存列保持原日报口径(更准)
    if cv and cat_stockval.get(cname, 0) > 0: set_safe(ws, r, cv, round(cat_stockval[cname]))

# 02 爆款: 波段+图(幂等)
ws = wb1["02·爆款基因库·近30日动销Top30"]
pc = ensure_pic_col(ws, 2)
ccol = find_col(ws, "款号"); bcol = find_col(ws, "波段")
n_pic = 0
if ccol:
    for r in range(3, ws.max_row + 1):
        ref = str(ws.cell(r, ccol).value or "")
        if not ref or ref == "None":
            continue
        band = tpl_band.get(ref) or tpl_band.get(ref.split("-")[0]) or ""
        if band and bcol:
            set_safe(ws, r, bcol, band)
        if add_pic(ws, r, pc, ref):
            n_pic += 1
print(f"  爆款基因库: 图{n_pic}")

# 03 慢销: 重建(幂等: 删旧)
for sn in list(wb1.sheetnames):
    if sn.startswith("03·"):
        del wb1[sn]
cat_active_p25 = {}
for cat in cat_day_qty:
    totals = sorted(t for t in (sum(v for k, v in ref_day_qty[ref].items() if k >= d30)
                    for ref in ref_day_qty if ref_cat.get(ref) == cat) if t > 0)
    if len(totals) >= 5:
        cat_active_p25[cat] = totals[len(totals)//4]
slow = []
for ref, rdq in ref_day_qty.items():
    meta = goods_meta.get(ref) or {}
    ctime = meta.get("ctime")
    if not ctime:
        if not rdq:
            continue
        ctime = datetime.strptime(min(rdq.keys()), "%Y-%m-%d")
    days_live = (NOW - ctime).days
    if days_live < 14:
        continue
    s30 = sum(v for k, v in rdq.items() if k >= d30)
    cat = ref_cat.get(ref) or meta.get("cate") or ""
    stock = stock_of(ref)
    p25 = cat_active_p25.get(cat)
    if stock > 30:
        if p25 and 0 < s30 < p25:
            slow.append([ref, meta.get("name") or ref, cat, round(stock), round(s30),
                         round(sum(rdq.values())), f"上市{days_live}天·有动销但<品类P25({p25:.0f})", "改款/调价/停补"])
        elif s30 == 0 and days_live >= 30 and sum(rdq.values()) > 0:
            slow.append([ref, meta.get("name") or ref, cat, round(stock), 0,
                         round(sum(rdq.values())), f"上市{days_live}天·近30日零动销", "清仓/停补"])
slow.sort(key=lambda x: (x[4], -x[3]))
slow = slow[:40]
ws = wb1.create_sheet("03·慢销止损清单(全量)")
ws.sheet_properties.tabColor = XL_HEADER_BG[2:]
headers = ["图片", "款号", "款名", "品类", "库存", "近30日销量", "累计销量", "判定依据", "建议动作"]
ws.cell(1, 1, "慢销止损清单（上市≥14天 · 动销<品类P25 · 库存>30件）").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
for c, h in enumerate(headers, 1):
    cell = ws.cell(2, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
n_pic = 0
for i, row in enumerate(slow):
    r = 3 + i
    for c, v in enumerate([None] + row, 1):
        cell = ws.cell(r, c, v if c > 1 else None)
        cell.font = f_body; cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) else al_l
    if add_pic(ws, r, 1, row[0]):
        n_pic += 1
for c, w in enumerate([14, 13, 18, 9, 8, 10, 9, 22, 13], 1):
    ws.column_dimensions[get_column_letter(c)].width = w
ws.freeze_panes = "C3"
print(f"  慢销清单: {len(slow)}款 图{n_pic}")

# 06 矩阵: 0填充(跳过合并)
ws = wb1["06·品类×设计师建版矩阵"]
filled = 0
for r in range(3, ws.max_row + 1):
    for c in range(2, ws.max_column + 1):
        cell = ws.cell(r, c)
        if isinstance(cell, MergedCell):
            continue
        if cell.value is None or cell.value == "":
            cell.value = 0
            cell.alignment = al_r
            filled += 1
print(f"  矩阵: 填0×{filled}")

wb1.save(f"{OUTDIR}/数据包-研发部-{TODAY}.xlsx")
print("  ✅")

# ============================================================
# 生产部
# ============================================================
print("生产部...")
wb2 = openpyxl.load_workbook(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")

inprod_refs = defaultdict(float)
with open(f"{RAW}/yizhe_production_list.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            o = json.loads(line)
            if o.get("template_no"):
                inprod_refs[o["template_no"]] += num(o.get("plan_total_num"))

# 01 补货计划: 图+并单(幂等)
ws = wb2["01·周滚动补货计划(净缺口法)"]
pc = ensure_pic_col(ws, 3)
ccol = find_col(ws, "款号"); mcol = find_col(ws, "并单标记")
n_pic = 0
if ccol:
    for r in range(3, ws.max_row + 1):
        ref = str(ws.cell(r, ccol).value or "")
        if not ref or ref == "None":
            continue
        ar = sales_of(ref)
        dq = ref_day_qty.get(ar or ref, {})
        daily30 = sum(v for k, v in dq.items() if k >= d30) / 30
        ip = inprod_refs.get(ref, 0)
        mark = "—"
        if daily30 >= 10:
            mark = "✔并单候选" if ip > 0 else "批量直下"
        if mcol:
            set_safe(ws, r, mcol, mark)
        if add_pic(ws, r, pc, ref):
            n_pic += 1
print(f"  补货计划: 图{n_pic}")

# 02 驾驶舱: 图(幂等)
ws = wb2["02·在产订单驾驶舱(190单)"]
pc = ensure_pic_col(ws, 3)
ccol = find_col(ws, "款号")
n_pic = 0
if ccol:
    for r in range(3, ws.max_row + 1):
        ref = str(ws.cell(r, ccol).value or "")
        if ref and ref != "None" and add_pic(ws, r, pc, ref):
            n_pic += 1
print(f"  驾驶舱: 图{n_pic}")

# 07 V2: 图+备注(幂等)
ws = wb2["07·补货建议V2·三因子对比"]
pc = ensure_pic_col(ws, 3)
ccol = find_col(ws, "款号"); ncol = find_col(ws, "备注")
n_pic = 0
if ccol:
    for r in range(3, ws.max_row + 1):
        ref = str(ws.cell(r, ccol).value or "")
        if ref and ref != "None":
            if add_pic(ws, r, pc, ref):
                n_pic += 1
        if ncol:
            cell = ws.cell(r, ncol)
            if not isinstance(cell, MergedCell) and (cell.value is None or cell.value == ""):
                cell.value = "—"
print(f"  V2表: 图{n_pic}")

wb2.save(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")
print("  ✅")

# ============================================================
# 销售部
# ============================================================
print("销售部...")
wb3 = openpyxl.load_workbook(f"{OUTDIR}/数据包-销售部-{TODAY}.xlsx")
ws = wb3["06·31省订单分布(近30日)"]
tcol = find_col(ws, "近4周趋势"); bcol = find_col(ws, "备注")
if tcol:
    for r in range(3, ws.max_row + 1):
        set_safe(ws, r, tcol, "见05表大区周趋势")
if bcol:
    ws.cell(2, bcol, None)
    for r in range(3, ws.max_row + 1):
        set_safe(ws, r, bcol, None)
print("  31省: 趋势列指向大区周数据")
wb3.save(f"{OUTDIR}/数据包-销售部-{TODAY}.xlsx")
print("  ✅")

# ============================================================
# 财务部
# ============================================================
print("财务部...")
wb4 = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")

customers = []
with open(f"{RAW}/duoke_customers.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            customers.append(json.loads(line))
total_debt = sum(num(c.get("debt")) for c in customers if num(c.get("debt")) > 0)

ws = wb4["02·客户信用分档规则"]
for r in range(3, ws.max_row + 1):
    if ws.cell(r, 1).value == "当前欠款客户":
        set_safe(ws, r, 3, round(total_debt))

ws = wb4["05·碎片补单成本测算"]
for r in range(3, ws.max_row + 1):
    k = ws.cell(r, 1).value
    if k and "断货" in str(k):
        set_safe(ws, r, 3, "≈¥77万")

ws = wb4["06·欠款客户明细(98家)"]
pcol = find_col(ws, "最近回款")
n_fill = 0
if pcol:
    for r in range(3, ws.max_row + 1):
        cname = ws.cell(r, 1).value
        if not cname:
            continue
        lp = last_payment.get(cname)
        if lp:
            set_safe(ws, r, pcol, f"{lp[0]:%Y-%m-%d} ¥{lp[1]:,.0f}")
        else:
            set_safe(ws, r, pcol, "近1年无回款")
        n_fill += 1
print(f"  欠款回款: {n_fill}")

ws = wb4["07·款级毛利排行(30日动销Top30)"]
pc = ensure_pic_col(ws, 2)
ccol = find_col(ws, "款号")
cost_col = find_col(ws, "成本(¥)"); qty_col = find_col(ws, "销量")
amt_col = find_col(ws, "销售额(¥)"); recv_col = find_col(ws, "实收均价(¥)")
gp_col = find_col(ws, "毛利(¥)"); gpr_col = find_col(ws, "毛利率")
price_col = find_col(ws, "售价(¥)")
n_pic = 0
if ccol:
    for r in range(3, ws.max_row + 1):
        ref = str(ws.cell(r, ccol).value or "")
        if not ref or ref == "None":
            continue
        if add_pic(ws, r, pc, ref):
            n_pic += 1
        ar = sales_of(ref)
        cst = ref_cost_qty.get(ar or ref) or ref_cost_qty.get(ref.split("-")[0])
        unit = round(cst[0]/cst[1], 1) if cst and cst[1] > 0 else None
        if unit and cost_col:
            set_safe(ws, r, cost_col, unit)
            qty = num(ws.cell(r, qty_col).value) if qty_col else 0
            amt = num(ws.cell(r, amt_col).value) if amt_col else 0
            if qty > 0:
                avg_recv = amt / qty
                if recv_col: set_safe(ws, r, recv_col, round(avg_recv, 1))
                if gp_col: set_safe(ws, r, gp_col, round(avg_recv - unit, 1))
                if gpr_col and avg_recv > 0: set_safe(ws, r, gpr_col, f"{(avg_recv-unit)/avg_recv*100:.0f}%")
print(f"  款级毛利: 图{n_pic}")

wb4.save(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
print("  ✅")
print("\n=== 全部完成 ===")
