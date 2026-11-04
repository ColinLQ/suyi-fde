#!/usr/bin/env python3
# 修正: ①工厂计分卡用factory_name+按款聚合去同日重复 ②返单明细同日合并
import os, sys
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.utils import get_column_letter

def xl_color(css_hex):
    v = css_hex.removeprefix("#").upper()
    return "FF" + v if len(v) == 6 else "FF000000"

XL_HEADER_BG = xl_color("#4472C4")
XL_RED_BG = xl_color("#FDE9E9")
XL_YELLOW_BG = xl_color("#FFFDE8")
XL_GREEN_BG = xl_color("#C6EFCE")
thin_side = Side(style="thin", color=xl_color("#BFBFBF"))
border_all = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
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
TODAY = "2026-10-10"

def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def num(v, d=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def pdate(v):
    if v in (None, "", 0, "0"):
        return None
    try:
        s = str(v)
        if s.replace(".", "").isdigit() and len(s) >= 9:
            return datetime.fromtimestamp(int(float(s)))
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None

def red_fill(row, i): return PatternFill("solid", fgColor=XL_RED_BG)
def yellow_fill(row, i): return PatternFill("solid", fgColor=XL_YELLOW_BG)
def green_fill(row, i): return PatternFill("solid", fgColor=XL_GREEN_BG)

follow_done = load_jsonl(f"{RAW_T}/perf_follow_done.jsonl")
prod_hist = load_jsonl(f"{RAW}/yizhe_production_hist.jsonl")
prod_active = load_jsonl(f"{RAW}/yizhe_production_list.jsonl")

# ============ 重写生产部 05 工厂全量计分卡 ============
wb2 = openpyxl.load_workbook(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")
del wb2["05·工厂计分卡·全量(2779批)"]

stats = defaultdict(lambda: {"n":0,"qty":0,"ontime":0,"late":0,"noeta":0,"cycle":[],"late5":0,"followers":defaultdict(int),"price":[]})
for o in follow_done:
    fn = o.get("factory_name")
    if not fn or fn == "无":
        continue
    st = stats[fn]
    st["n"] += 1
    st["qty"] += int(o.get("plan_total_num") or 0)
    fu = o.get("follower_user_name")
    if fu and fu != "无":
        st["followers"][fu] += 1
    p = num(o.get("price"))
    if p > 0:
        st["price"].append(p)
    eta, fin = pdate(o.get("estimated_finish_time")), pdate(o.get("finish_time"))
    if eta is None:
        st["noeta"] += 1
    elif eta and fin:
        if (fin - eta).days <= 0:
            st["ontime"] += 1
        else:
            st["late"] += 1
            if (fin - eta).days > 5:
                st["late5"] += 1
    c, s_ = pdate(o.get("create_order_time")), pdate(o.get("last_stockout_time"))
    if c and s_:
        cy = (s_ - c).days
        if 0 <= cy < 120:
            st["cycle"].append(cy)

fac_rows = []
for fn, st in sorted(stats.items(), key=lambda x: -x[1]["qty"]):
    rated = st["ontime"] + st["late"]
    rate = f"{st['ontime']/rated*100:.0f}%" if rated else "—"
    eta_fill = f"{st['noeta']/st['n']*100:.0f}%"
    avg_cy = round(sum(st["cycle"])/len(st["cycle"]), 1) if st["cycle"] else ""
    avg_price = round(sum(st["price"])/len(st["price"]), 1) if st["price"] else ""
    top_fol = "、".join(f"{k}{v}批" for k, v in sorted(st["followers"].items(), key=lambda x: -x[1])[:2])
    fac_rows.append([
        fn, st["n"], st["qty"], rate, st["late5"], eta_fill, avg_cy, avg_price, top_fol,
    ])

tag = "05·工厂计分卡·全量(2779批)"
ws = wb2.create_sheet(tag)
ws.sheet_properties.tabColor = XL_HEADER_BG[2:]
headers = ["工厂", "批次数", "件数", "按时率", "超5天批", "ETA未填率", "平均周期(天)", "均加工价(¥/件)", "主力跟单"]
widths = [14, 9, 11, 9, 9, 11, 12, 13, 20]
ws.cell(1, 1, "工厂计分卡·全量(2779批·含工厂名)").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
ws.cell(1, 1).alignment = al_l
for c, h in enumerate(headers, 1):
    cell = ws.cell(2, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
for i, row in enumerate(fac_rows):
    alert = red_fill(row, i) if isinstance(row[3], str) and row[3].rstrip("%").isdigit() and int(row[3].rstrip("%")) < 5 else None
    for c, v in enumerate(row, 1):
        cell = ws.cell(3+i, c, v)
        cell.font = f_body; cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) and not isinstance(v, bool) else al_l
        if alert:
            cell.fill = alert
for c, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(c)].width = w
note = ("全量口径:跟单完成批2779批。按时率=完成日≤ETA占比(仅计有ETA批);ETA未填率过半是管理黑洞。"
        "恒生/金马/博林丰等名称以follow_order实际记录为准。均加工价=price字段均值,可直接对比工厂报价。")
nr = 3 + len(fac_rows) + 1
ws.cell(nr, 1, note).font = f_note
ws.merge_cells(start_row=nr, start_column=1, end_row=nr, end_column=len(headers))
ws.freeze_panes = "A3"

# ============ 重写生产部 06 返单节奏(同日合并) ============
del wb2["06·返单节奏明细·下单≥3次"]
tpl_orders = defaultdict(list)
for o in prod_hist + prod_active:
    tno, ca = o.get("template_no"), o.get("created_at")
    if tno and ca:
        tpl_orders[tno].append((str(ca)[:10], int(o.get("plan_total_num") or 0)))

multi_rows = []
for tno, lst in tpl_orders.items():
    # 同日合并(一天内多单算一次下单动作)
    by_day = defaultdict(int)
    for d, q in lst:
        by_day[d] += q
    days = sorted(by_day)
    if len(days) < 3:
        continue
    gaps = [(datetime.strptime(days[i+1], "%Y-%m-%d") - datetime.strptime(days[i], "%Y-%m-%d")).days for i in range(len(days)-1)]
    total_qty = sum(by_day.values())
    min_gap = min(gaps)
    span = (datetime.strptime(days[-1], "%Y-%m-%d") - datetime.strptime(days[0], "%Y-%m-%d")).days
    single_cnt = len(lst)  # 实际单据数(含同日拆单)
    multi_rows.append([
        tno, len(days), single_cnt, total_qty, days[0], days[-1], f"{span}天",
        min_gap, "→".join(days),
        "🔴高危" if min_gap <= 2 else ("⚠️碎片" if min_gap <= 7 else "正常"),
    ])
multi_rows.sort(key=lambda x: -x[2])

tag = "06·返单节奏明细·下单≥3次(同日合并)"
ws = wb2.create_sheet(tag)
ws.sheet_properties.tabColor = XL_HEADER_BG[2:]
headers = ["款号", "下单天数", "实际单据数", "累计件数", "首单日", "最近单", "跨度", "最小间隔(天)", "下单日期序列(同日已并)", "定性"]
widths = [13, 9, 10, 10, 11, 11, 8, 12, 42, 9]
ws.cell(1, 1, "返单节奏明细·下单≥3次(同日已合并)").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
ws.cell(1, 1).alignment = al_l
for c, h in enumerate(headers, 1):
    cell = ws.cell(2, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
for i, row in enumerate(multi_rows):
    alert = red_fill(row, i) if "🔴" in str(row[9]) else (yellow_fill(row, i) if "⚠️" in str(row[9]) else None)
    for c, v in enumerate(row, 1):
        cell = ws.cell(3+i, c, v)
        cell.font = f_body; cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) and not isinstance(v, bool) else al_l
        if alert:
            cell.fill = alert
for c, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(c)].width = w
note = (f"共{len(multi_rows)}款按'下单日'去重后≥3次。同日拆单已合并(单据数>天数=存在同日拆单,本身也是碎片化证据)。"
        "最小间隔≤2天=🔴高危;≤7天=⚠️碎片(并单机制主目标)。LQ263807等款42天内10个下单日/多张单据——并单空间最大。")
nr = 3 + len(multi_rows) + 1
ws.cell(nr, 1, note).font = f_note
ws.merge_cells(start_row=nr, start_column=1, end_row=nr, end_column=len(headers))
ws.freeze_panes = "A3"

wb2.save(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")
print("✅ 生产部 05/06 已修正(工厂实名+同日合并)")

# 抽查
wb2 = openpyxl.load_workbook(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")
for wsname in ["05·工厂计分卡·全量(2779批)", "06·返单节奏明细·下单≥3次(同日合并)"]:
    ws = wb2[wsname]
    print(f"\n--- {wsname} ---")
    for row in ws.iter_rows(min_row=3, max_row=7, values_only=True):
        print(str(row)[:125])
