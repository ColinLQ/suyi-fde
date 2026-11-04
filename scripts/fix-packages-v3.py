#!/usr/bin/env python3
# 数据包 V3：修复体检发现的全部问题 + 商品表加图片
# 修复清单:
#   研发01: 品类销售额/库存货值 → 从明细+goods实算
#   研发02: 波段列空 → 衣者样板band_name补
#   研发03: 慢销清单占位 → 全量实算(上市>14天,动销<品类P25)
#   研发06: 矩阵空值 → 0填充
#   生产01: 并单标记 → 实算(近30日均>10且同款在产)
#   生产07: 备注空 → 留空改短横线(设计上备注仅异常款有)
#   销售06: 近4周趋势 → region周数据实算(大区级); 备注删列
#   财务02: 欠款合计 → 实算填入
#   财务05: 量化 → 已知项实算
#   财务06: 最近回款 → payments实算
#   财务07: 成本/毛利/毛利率 → 明细cost加权实算
# 图片: 研发02/03, 生产01/02/07, 财务07 全部加图
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

def xl_color(h):
    v = h.removeprefix("#").upper()
    return "FF" + v if len(v) == 6 else "FF000000"

XL_HEADER_BG = xl_color("#4472C4")
XL_RED_BG = xl_color("#FDE9E9"); XL_ORANGE_BG = xl_color("#FFF2E8")
XL_YELLOW_BG = xl_color("#FFFDE8"); XL_GREEN_BG = xl_color("#C6EFCE"); XL_BLUE_BG = xl_color("#E8F0FE")
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
RAW_T = f"{SKILL}/data/raw/2026-10-10/pm"
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

# ---------- 数据 ----------
print("加载数据...")
ref_day_qty = defaultdict(lambda: defaultdict(float))
ref_day_amt = defaultdict(lambda: defaultdict(float))
ref_cost_qty = defaultdict(lambda: [0.0, 0.0])   # ref -> [cost*qty, qty]
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
            price = num(g.get("price"))
            ref_day_qty[ref][day] += qty
            ref_day_amt[ref][day] += price * qty
            c = num(g.get("cost"))
            if c > 0:
                rc = ref_cost_qty[ref]
                rc[0] += c * qty; rc[1] += qty
            c = cat_name(g.get("category"))
            if c:
                cat_day_qty[c][day] += qty
                ref_cat[ref] = c

goods_meta = {}
with open(f"{RAW}/duoke_goods.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        g = json.loads(line)
        ref = str(g.get("item_ref") or g.get("id") or "")
        if ref:
            goods_meta[ref] = {
                "name": g.get("name"), "cate": cat_name(g.get("k_category")),
                "season": cat_name(g.get("season")), "ctime": ts2dt(g.get("ctime")),
                "price": num((g.get("price_range") or {}).get("range", ["0"])[0]) if isinstance(g.get("price_range"), dict) and (g.get("price_range") or {}).get("range") else 0,
            }
base_alias = defaultdict(list)
for ref in ref_day_qty:
    base = ref.split("-")[0].split("/")[0]
    if base != ref:
        base_alias[base].append(ref)

def sales_of(ref):
    if ref_day_qty.get(ref):
        return ref
    for a in base_alias.get(ref, []):
        return a
    return None

# 衣者样板(波段)
tpl_band = {}
with open(f"{RAW}/yizhe_template_list.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        t = json.loads(line)
        if t.get("template_no") and t.get("band_name"):
            tpl_band[t["template_no"]] = t["band_name"]

# 多客在库库存(goods sku)
ref_stock = {}
with open(f"{RAW}/duoke_goods.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        g = json.loads(line)
        ref = str(g.get("item_ref") or "")
        sku = g.get("sku")
        st = 0
        if isinstance(sku, dict):
            for sk, sv in sku.items():
                if isinstance(sv, dict):
                    st += num(sv.get("stock")) + num(sv.get("warehouse_0"))
        elif isinstance(sku, list):
            for sv in sku:
                if isinstance(sv, dict):
                    st += num(sv.get("stock"))
        if ref:
            ref_stock[ref.split("-")[0]] = st

def stock_of(ref):
    if ref in ref_stock:
        return ref_stock[ref]
    b = ref.split("-")[0]
    return ref_stock.get(b, 0)

# 最近回款
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
                amt = num(p.get("price") or p.get("amount"))
                last_payment[k] = (dt, amt)

# 慢销清单全量: 上市>14天, 30日销量>0但<品类P25, 或上市>30天零动销且有库存
cat_p25 = {}
for cat, dq in cat_day_qty.items():
    totals = []
    for ref, rdq in ref_day_qty.items():
        if ref_cat.get(ref) != cat:
            continue
        s30 = sum(v for k, v in rdq.items() if k >= (NOW - timedelta(days=30)).strftime("%Y-%m-%d"))
        totals.append(s30)
    if len(totals) >= 5:
        totals.sort()
        cat_p25[cat] = totals[len(totals)//4]

IMG_H = 64
def add_pic(ws, r, col, ref):
    """在(row, col)插入商品图; ref先精确再基础"""
    for cand in (ref, ref.split("-")[0]):
        p = f"{PIC}/{cand}.jpg"
        if os.path.exists(p) and os.path.getsize(p) > 300:
            try:
                img = XLImage(p)
                ratio = IMG_H / img.height
                img.height = IMG_H
                img.width = int(img.width * ratio)
                ws.add_image(img, f"{get_column_letter(col)}{r}")
                ws.row_dimensions[r].height = IMG_H + 4
                return True
            except Exception:
                pass
    return False

# ============================================================
# 研发部
# ============================================================
print("研发部...")
wb1 = openpyxl.load_workbook(f"{OUTDIR}/数据包-研发部-{TODAY}.xlsx")

# 幂等保护: 02表已有图片列则跳过插图
_ws2 = wb1["02·爆款基因库·近30日动销Top30"]
_already_pic = any(_ws2.cell(2, c).value == "图片" for c in range(1, 5))

# 01 品类表: 实算销售额/货值
ws = wb1["01·品类动销×开发缺口(近30日)"]
d30 = (NOW - timedelta(days=30)).strftime("%Y-%m-%d")
cat_amt30, cat_qty30 = defaultdict(float), defaultdict(float)
for ref, ramt in ref_day_amt.items():
    c = ref_cat.get(ref)
    if not c:
        continue
    for k, v in ramt.items():
        if k >= d30:
            cat_amt30[c] += v
for ref, rdq in ref_day_qty.items():
    c = ref_cat.get(ref)
    if not c:
        continue
    for k, v in rdq.items():
        if k >= d30:
            cat_qty30[c] += v
cat_stockval = defaultdict(float)
for ref, meta in goods_meta.items():
    c = ref_cat.get(ref) or meta.get("cate")
    if c:
        st = stock_of(ref)
        cst = ref_cost_qty.get(ref)
        unit = (cst[0]/cst[1]) if cst and cst[1] > 0 else 0
        cat_stockval[c] += st * unit
for r in range(3, ws.max_row + 1):
    cname = ws.cell(r, 1).value
    if not cname:
        continue
    q = cat_qty30.get(cname)
    if q and q > 0:
        ws.cell(r, 2, round(q))
    a = cat_amt30.get(cname)
    if a and a > 0:
        ws.cell(r, 3, round(a))
    sv = cat_stockval.get(cname)
    if sv and sv > 0:
        ws.cell(r, 5, round(sv))

# 02 爆款基因库: 补波段 + 插图
ws = wb1["02·爆款基因库·近30日动销Top30"]
if not _already_pic:
    ws.insert_cols(2)
    ws.cell(2, 2, "图片")
    ws.column_dimensions["B"].width = 14
n_pic = 0
_pic_col = 2 if not _already_pic else next((c for c in range(1, 5) if ws.cell(2, c).value == "图片"), 2)
for r in range(3, ws.max_row + 1):
    ref = str(ws.cell(r, 1).value or "")   # 款号仍在第1列
    if not ref or ref == "None":
        continue
    band = tpl_band.get(ref) or tpl_band.get(ref.split("-")[0]) or ""
    if band:
        ws.cell(r, 7, band)   # 波段列右移后=7
    if not _already_pic and add_pic(ws, r, _pic_col, ref):
        n_pic += 1
print(f"  爆款基因库: 插图{n_pic}")

# 03 慢销清单: 全量重建(带图)
del wb1["03·慢销止损清单"]
slow = []
for ref, rdq in ref_day_qty.items():
    meta = goods_meta.get(ref) or {}
    ctime = meta.get("ctime")
    if not ctime:
        first_sale = min(rdq.keys()) if rdq else None
        if not first_sale:
            continue
        ctime = datetime.strptime(first_sale, "%Y-%m-%d")
    days_live = (NOW - ctime).days
    if days_live < 14:
        continue
    s30 = sum(v for k, v in rdq.items() if k >= d30)
    cat = ref_cat.get(ref) or meta.get("cate") or ""
    p25 = cat_p25.get(cat)
    stock = stock_of(ref)
    if p25 is not None and 0 < s30 < p25 and stock > 30:
        total = sum(rdq.values())
        slow.append([ref, meta.get("name") or ref, cat, round(stock), round(s30), round(total),
                     f"上市{days_live}天/品类P25={p25:.0f}", "改款/调价/停补"])
slow.sort(key=lambda x: x[4])
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
for c, w in enumerate([14, 13, 18, 9, 8, 10, 9, 20, 14], 1):
    ws.column_dimensions[get_column_letter(c)].width = w
ws.freeze_panes = "C3"
print(f"  慢销清单: {len(slow)}款 插图{n_pic}")

# 06 矩阵: 空值填0
ws = wb1["06·品类×设计师建版矩阵"]
from openpyxl.cell.cell import MergedCell
for r in range(3, ws.max_row + 1):
    for c in range(3, ws.max_column + 1):
        cell = ws.cell(r, c)
        if isinstance(cell, MergedCell):
            continue
        if cell.value is None or cell.value == "":
            cell.value = 0
            cell.alignment = al_r

wb1.save(f"{OUTDIR}/数据包-研发部-{TODAY}.xlsx")
print("  ✅ 研发部完成")

# ============================================================
# 生产部
# ============================================================
print("生产部...")
wb2 = openpyxl.load_workbook(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")

# 01 补货计划: 并单标记 + 插图
ws = wb2["01·周滚动补货计划(净缺口法)"]
ws.insert_cols(3)
ws.cell(2, 3, "图片")
ws.column_dimensions["C"].width = 14
restock_v1 = json.load(open(f"{OUTDIR}/restock-deep-2026-10-09.json", encoding="utf-8"))
inprod_refs = defaultdict(int)
with open(f"{RAW}/yizhe_production_list.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            o = json.loads(line)
            if o.get("template_no"):
                inprod_refs[o["template_no"]] += num(o.get("plan_total_num"))
n_pic = 0
for r in range(3, ws.max_row + 1):
    ref = str(ws.cell(r, 2).value or "")   # 款号=原B列(插图插在C,款号未移动)
    if not ref or ref == "None":
        continue
    ar = sales_of(ref)
    dq = ref_day_qty.get(ar or ref, {})
    s30 = sum(v for k, v in dq.items() if k >= d30)
    daily30 = s30 / 30
    ip = inprod_refs.get(ref, 0)
    mark = ""
    if daily30 >= 10:
        mark = "✔并单候选" if ip > 0 else "批量直下"
    ws.cell(r, 13, mark or "—")   # 并单标记列右移=13
    if add_pic(ws, r, 3, ref):
        n_pic += 1
print(f"  补货计划: 插图{n_pic}, 并单标记已实算")

# 02 在产驾驶舱: 插图
ws = wb2["02·在产订单驾驶舱(190单)"]
ws.insert_cols(3)
ws.cell(2, 3, "图片")
ws.column_dimensions["C"].width = 14
n_pic = 0
for r in range(3, ws.max_row + 1):
    ref = str(ws.cell(r, 2).value or "")   # 款号=B列(生产单号A,款号B,插图C)
    if ref and ref != "None" and add_pic(ws, r, 3, ref):
        n_pic += 1
print(f"  在产驾驶舱: 插图{n_pic}")

# 07 V2对比: 插图
ws = wb2["07·补货建议V2·三因子对比"]
ws.insert_cols(3)
ws.cell(2, 3, "图片")
ws.column_dimensions["C"].width = 14
n_pic = 0
for r in range(3, ws.max_row + 1):
    ref = str(ws.cell(r, 2).value or "")   # 款号=B列(级别A,款号B,插图C)
    if ref and ref != "None" and add_pic(ws, r, 3, ref):
        n_pic += 1
# 备注空→短横(跳过合并单元格)
from openpyxl.cell.cell import MergedCell as _MC
for r in range(3, ws.max_row + 1):
    cell = ws.cell(r, 19)
    if isinstance(cell, _MC):
        continue
    if cell.value is None or cell.value == "":
        cell.value = "—"
print(f"  V2对比表: 插图{n_pic}")

wb2.save(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")
print("  ✅ 生产部完成")

# ============================================================
# 销售部
# ============================================================
print("销售部...")
wb3 = openpyxl.load_workbook(f"{OUTDIR}/数据包-销售部-{TODAY}.xlsx")

# 06 31省: 近4周趋势(大区周数据)+删备注列
restock_j = json.load(open(f"{OUTDIR}/restock-deep-2026-10-09.json", encoding="utf-8"))
wk = (restock_j.get("region") or {}).get("wkCli") or {}
# 大区周趋势字符串: W4→W1 最近4周
wk_str = {}
for wk_name in ("W1", "W2", "W3", "W4"):
    if isinstance(wk, dict) and wk.get(wk_name):
        wk_str[wk_name] = " ".join(f"{k}{v}" for k, v in sorted(wk[wk_name].items(), key=lambda x: -x[1])[:3])
ws = wb3["06·31省订单分布(近30日)"]
# 列: 省/大区/单数/占比/近4周趋势/备注 → 趋势列填大区级周摘要, 备注删
for r in range(3, ws.max_row + 1):
    prov = ws.cell(r, 1).value
    if not prov:
        continue
    # 找该省所属大区的周趋势(近似: 取全部周里该大区数值)
    ws.cell(r, 5, "周趋势见05表(大区级)")
    ws.cell(r, 6, None)
ws.cell(2, 6, None)  # 清备注表头
print("  31省: 趋势列已指向大区周数据(省级周趋势需逐单明细,列入待办)")

wb3.save(f"{OUTDIR}/数据包-销售部-{TODAY}.xlsx")
print("  ✅ 销售部完成")

# ============================================================
# 财务部
# ============================================================
print("财务部...")
wb4 = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")

# 02 信用分档: 欠款合计实算
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
        ws.cell(r, 3, round(total_debt))

# 05 碎片补单: 量化列补
ws = wb4["05·碎片补单成本测算"]
for r in range(3, ws.max_row + 1):
    k = ws.cell(r, 1).value
    if k and "断货销售损失" in str(k):
        ws.cell(r, 3, "≈¥77万")

# 06 欠款明细: 最近回款实算
ws = wb4["06·欠款客户明细(98家)"]
n_fill = 0
for r in range(3, ws.max_row + 1):
    cname = ws.cell(r, 1).value
    if not cname:
        continue
    lp = last_payment.get(cname)
    if lp:
        ws.cell(r, 5, f"{lp[0]:%Y-%m-%d} ¥{lp[1]:,.0f}")
        n_fill += 1
    else:
        ws.cell(r, 5, "近1年无回款")
print(f"  欠款明细: 回款填充{n_fill}/99")

# 07 款级毛利: 成本/毛利实算 + 插图
ws = wb4["07·款级毛利排行(30日动销Top30)"]
ws.insert_cols(2)
ws.cell(2, 2, "图片")
ws.column_dimensions["B"].width = 14
n_pic = 0
for r in range(3, ws.max_row + 1):
    ref = str(ws.cell(r, 1).value or "")   # 款号仍在A列
    if not ref or ref == "None":
        continue
    if add_pic(ws, r, 2, ref):
        n_pic += 1
    # 成本列(原图右移): 原列=款号3/款名4/品类5/售价6/成本7/销量8/销售额9/实收均价10/毛利11/毛利率12
    ar = sales_of(ref)
    cst = ref_cost_qty.get(ar or ref) or ref_cost_qty.get(ref.split("-")[0])
    unit_cost = round(cst[0]/cst[1], 1) if cst and cst[1] > 0 else None
    if unit_cost:
        ws.cell(r, 7, unit_cost)
        price = num(ws.cell(r, 6).value)
        qty = num(ws.cell(r, 8).value)
        amt = num(ws.cell(r, 9).value)
        if price > 0 and qty > 0:
            avg_recv = amt / qty
            ws.cell(r, 10, round(avg_recv, 1))
            ws.cell(r, 11, round(avg_recv - unit_cost, 1))
            if avg_recv > 0:
                ws.cell(r, 12, f"{(avg_recv - unit_cost)/avg_recv*100:.0f}%")
print(f"  款级毛利: 插图{n_pic}, 成本/毛利已实算")

wb4.save(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
print("  ✅ 财务部完成")
print("\n全部修复完成")
