#!/usr/bin/env python3
# 销售数据报表 V2.1（2026-10-12 改动需求全部落实）
import json, os, sys
try:
    import openpyxl
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "openpyxl>=3.1.0"])
    import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage

def xl_color(css_hex: str) -> str:
    v = css_hex.removeprefix("#").upper()
    assert len(v) == 6
    return "FF" + v

XL_H = xl_color("#4472C4"); XL_B = xl_color("#BFBFBF"); XL_W = xl_color("#9C0006"); XL_G = xl_color("#C6EFCE")
thin = Side(style="thin", color=XL_B)
bd = Border(left=thin, right=thin, top=thin, bottom=thin)
fh = Font(name="PingFang SC", bold=True, color="FFFFFFFF", size=11)
ft = Font(name="PingFang SC", bold=True, size=14, color=xl_color("#1F2937"))
fb = Font(name="PingFang SC", size=11)
fn = Font(name="PingFang SC", size=9, color=xl_color("#6B7280"))
fl = PatternFill("solid", fgColor=XL_H)
ac = Alignment(horizontal="center", vertical="center", wrap_text=True)
al = Alignment(horizontal="left", vertical="center", wrap_text=True)
ar = Alignment(horizontal="right", vertical="center")

from pathlib import Path
SKILL = str(Path(__file__).resolve().parent.parent)
PIC = f"{SKILL}/state/goods-pics"
J = json.load(open(f"{SKILL}/out/销售数据报告-2026-10-12.json", encoding="utf-8"))
OUT = f"{SKILL}/out/销售数据报表-2026-10-12.xlsx"
IMG = 100
wb = openpyxl.Workbook(); wb.remove(wb.active)
NO = [0]

def sheet(title, headers, rows, types, widths, note=None, img_col=None, img_key=None):
    NO[0] += 1
    ws = wb.create_sheet(f"{NO[0]:02d}·{title}"[:31])
    ws.sheet_properties.tabColor = XL_H[2:]
    h2, w2, t2 = list(headers), list(widths), list(types)
    if img_col:
        h2.insert(img_col-1, "图片"); w2.insert(img_col-1, 16); t2.insert(img_col-1, "t")
    ws.cell(1,1,title).font = ft
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(h2)); ws.cell(1,1).alignment = al
    for c, h in enumerate(h2, 1):
        cell = ws.cell(2, c, h); cell.font = fh; cell.fill = fl; cell.alignment = ac; cell.border = bd
    for i, row in enumerate(rows):
        r = 3 + i; row2 = list(row); ref = None
        if img_col:
            ref = row[img_key]; row2.insert(img_col-1, None)
        for c, v in enumerate(row2, 1):
            if img_col and c == img_col: continue
            cell = ws.cell(r, c); t = t2[c-1]
            def asnum(x):
                try: return float(x)
                except (TypeError, ValueError): return None
            if v is None or v == "": cell.value = None
            elif t in ("n","m","p1","pct") and asnum(v) is None:
                cell.value = str(v); cell.alignment = al  # 非数值（'-'/'∞'）按文本
            elif t == "n":
                cell.value = int(v) if isinstance(v, (int,float)) and float(v).is_integer() else float(v)
                cell.number_format = "#,##0" if isinstance(cell.value, int) else "#,##0.0"; cell.alignment = ar
            elif t == "m": cell.value = round(float(v),2); cell.number_format = "¥#,##0"; cell.alignment = ar
            elif t == "p1": cell.value = round(float(v),1); cell.number_format = "0.0"; cell.alignment = ar
            elif t == "pct": cell.value = round(float(v),3); cell.number_format = "0.0%"; cell.alignment = ar
            elif t == "d": cell.value = str(v); cell.alignment = ac
            else: cell.value = str(v) if v is not None else None; cell.alignment = al
            cell.font = fb; cell.border = bd
        if img_col:
            ws.row_dimensions[r].height = IMG * 0.78
            p = os.path.join(PIC, f"{ref}.jpg")
            if os.path.exists(p) and os.path.getsize(p) > 500:
                try:
                    im = XLImage(p); ra = min(IMG/im.height, IMG*1.15/im.width)
                    im.width = int(im.width*ra); im.height = int(im.height*ra)
                    ws.add_image(im, f"{get_column_letter(img_col)}{r}")
                except Exception: ws.cell(r, img_col, "无图").font = fn; ws.cell(r, img_col).alignment = ac
            else: ws.cell(r, img_col, "无图").font = fn; ws.cell(r, img_col).alignment = ac
    for c, w in enumerate(w2, 1): ws.column_dimensions[get_column_letter(c)].width = w
    if len(rows) >= 10: ws.auto_filter.ref = f"A2:{get_column_letter(len(h2))}{2+len(rows)}"
    if len(rows) >= 8: ws.freeze_panes = ws.cell(3, (img_col+1) if img_col else 1).coordinate
    if note:
        ws.cell(2+len(rows)+2, 1, note).font = fn; ws.cell(2+len(rows)+2, 1).alignment = al
    return ws

ov = J["overview"]; p30 = ov["p30"]

# 01 总览
rows = []
for k, lb in [("p7","近7日"),("p15","近半月"),("p30","近30日")]:
    p = ov[k]; rows.append([lb,p["orders"],p["buyN"],p["amt"],p["qty"],p["attach"],p["newBuyN"],p["newAmt"],p["newAttach"],p["oldBuyN"],p["oldAmt"],p["oldAttach"],p["reorderAmt"]])
sheet("日周月下单回款总览【需求9】",
    ["周期","单数","购买单数","金额(¥)","件数","连带(件/单)","新客购买单数","新客金额(¥)","新客连带","老客购买单数","老客金额(¥)","老客连带","补单金额(¥)"],
    rows, ["t","n","n","m","n","p1","n","m","p1","n","m","p1","m"],
    [10,8,10,14,10,11,12,13,10,12,13,10,13],
    note="数据截至2026-10-12上午；客户按同人账户合并；补单=老客再下单口径。")

# 02 新老客占比（+建单价）
nr = J["new_ratio_30d"]
tb = nr["newBuyN"]+nr["oldBuyN"]; ta = nr["newAmt"]+nr["oldAmt"]
rows = [["新客",nr["newBuyN"],nr["newBuyN"]/max(1,tb),nr["newAmt"],nr["newAmt"]/max(1,ta),nr["newAttach"],nr["newAov"]],
        ["老客",nr["oldBuyN"],nr["oldBuyN"]/max(1,tb),nr["oldAmt"],nr["oldAmt"]/max(1,ta),nr["oldAttach"],nr["oldAov"]],
        ["合计",tb,1.0,ta,1.0,p30["attach"],ta/max(1,tb)]]
sheet("新老客户占比(近30日)【需求5】",
    ["客户类型","购买单数","单数占比","金额(¥)","金额占比","连带(件/单)","建单价(¥)"],
    rows, ["t","n","pct","m","pct","p1","m"],
    [12,12,10,14,10,12,12],
    note="建单价=金额÷购买单数（新客消费力）。")

# 03 月未下单（新口径：近3月有单、本月无单；+手机号）
rows = [[r["name"], r["phone"] or "—", r["vip"], r["last"], r["gapDays"], r["buyN"], r["retN"], r["buyAmt"], r["aov"]] for r in J["month_missing"]]
sheet("客户月未下单名单【需求3附】",
    ["客户","手机号","等级","最后下单","距今天数","累计下单数","退单数","累计回款(¥)","客单价(¥)"],
    rows, ["t","t","t","d","n","n","n","m","m"],
    [20,15,8,12,10,11,8,13,11],
    note="口径（10-12改）：近3个月有下单、但本月（自然月）还没下单——正常客户每月都应有单，本月没单即需跟进。⚠️含疑似内部账户待剔除确认。")

# 04 导购
rows = [[s["seller"],s["times"],s["qty"],s["amt"],s["newBuyN"],s["newAmt"],s["oldBuyN"],s["oldAmt"],s["reorderAmt"],s["oldBuyN"]/max(1,s["newBuyN"]+s["oldBuyN"])] for s in J["seller_30d"]]
sheet("导购日周月销售【需求4】",
    ["导购","单数(30日)","件数","回款额(¥)","新客购买单数","新客金额(¥)","老客购买单数","老客金额(¥)","补单金额(¥)","老客占比"],
    rows, ["t","n","n","m","n","m","n","m","m","pct"],
    [12,10,10,13,12,13,12,13,13,9],
    note="「空」=未指定导购。")

# 05 新客未复购（新档位15-30/30-60 + 件单价建单价 + 手机号）
nc = [["15-30天档", r["name"], r["phone"] or "—", r["first"], r["gapDays"], r["amt"], r["qty"], r["aov"], r["unitPrice"]] for r in J["new_client_15_30"]] + \
     [["30-60天档", r["name"], r["phone"] or "—", r["first"], r["gapDays"], r["amt"], r["qty"], r["aov"], r["unitPrice"]] for r in J["new_client_30_60"]]
sheet("新客未复购名单【需求6】",
    ["档位","客户","手机号","首单日","距首单(天)","首单金额(¥)","首单件数","建单价(¥)","件单价(¥)"],
    nc, ["t","t","t","d","n","m","n","m","p1"],
    [12,20,15,12,11,12,10,11,10],
    note="档位（10-12改）：首单后15-30天未复购 / 30-60天未复购；60天以上不管。")

# 06 ABCD
VIPCN = {"vip1":"普通(vip1)","vip2":"B类(vip2)","vip3":"A类(vip3)","vip4":"C类(vip4)","vip0":"未建档(vip0)"}
rows = [[VIPCN.get(k,k), v["orders"], v["amt"], v["qty"]] for k, v in sorted(J["vip_30d"].items())]
sheet("ABCD类客户下单回款【需求8】",
    ["客户等级","30日单数","30日回款(¥)","30日件数"],
    rows, ["t","n","m","n"], [14,10,14,11],
    note="等级取多客系统vip字段；B/A/C对应暂标待确认。")

# 07-09 补单款TOP（款式版，周/半月/月）
for key, lb in [("reorder_goods_week","补单款TOP30·近7日"),("reorder_goods_halfmonth","补单款TOP30·近半月"),("reorder_goods_month","补单款TOP30·近30日")]:
    rows = [[g["ref"], g["name"], g["cat"], g["listDate"], g["price"], g["qty"], g["amt"], g["clients"]] for g in J[key]]
    sheet(f"{lb}【需求2】",
        ["款号","款名","品类","上市时间","价格(¥)","补单量","补单金额(¥)","补单客户数"],
        rows, ["t","t","t","d","m","n","m","n"],
        [15,22,10,12,9,10,13,11],
        img_col=2, img_key=0,
        note="补单款（10-12改）：老客再拿该款的量/金额（客户行为口径；系统单据无字面「补单」标记，按客户非首单判定）。" if key.endswith("month") else None)

# 10 新客户月度（自然月 + 手机号）
rows = [[r["name"], r.get("phone") or "—", r["first"], r["times"], r["qty"], r["amt"], r["aov"], r["unitPrice"]] for r in J["new_client_monthly"]]
sheet("新客户月销售分析【需求7】",
    ["客户","手机号","首单时间","月内下单次数","件数","回款(¥)","客单价(¥)","件单价(¥)"],
    rows, ["t","t","d","n","n","m","m","p1"],
    [18,15,12,12,9,12,11,10],
    note="口径（10-12确认）：自然月内首次消费且当月≥2单的新客。")

# 11-16 动销（周/半月/月 × 全量/剔除专属≥2客户）
for key, lb, ex in [("move_top_week","动销TOP30·近7日",False),("move_top_week_ex","动销TOP30·近7日·剔除专属",True),
                    ("move_top_halfmonth","动销TOP30·近半月",False),("move_top_halfmonth_ex","动销TOP30·近半月·剔除专属",True),
                    ("move_top_month","动销TOP30·近30日",False),("move_top_month_ex","动销TOP30·近30日·剔除专属",True)]:
    rows = [[g["ref"], g["name"], g["cat"], g["listDate"], g["price"], g["qty"], g["amt"], g["clients"], g["stock"]] for g in J[key]]
    sheet(f"{lb}【需求11】",
        ["款号","款名","品类","上市时间","价格(¥)","销量","销售额(¥)","下单客户数","实时库存"],
        rows, ["t","t","t","d","m","n","m","n","n"],
        [15,22,10,12,9,9,12,11,10],
        img_col=2, img_key=0,
        note=("剔除专属=下单客户数≥2（杜绝柳川田家类专属大客户单品刷榜；≥5版待业务负责人拍板）。负库存=预售欠货。" if ex else
              ("全量榜；剔除专属版见相邻sheet。动销率(近30日>100件)：{}/{}款。".format(J["move_rate_30d"]["active_over100"], J["move_rate_30d"]["total_styles"]) if key=="move_top_month" else None)))

# 17 单品类（含剔除专属版）
for cat, arr in J["cat_top_month"].items():
    if cat.endswith("·剔除专属"): continue
    rows = [[cat, g["ref"], g["name"], g["listDate"], g["price"], g["qty"], g["amt"], g["clients"], g["stock"]] for g in arr]
    sheet(f"品类TOP10·{cat}【需求11】"[:31],
        ["品类","款号","款名","上市时间","价格(¥)","销量","销售额(¥)","下单客户数","实时库存"],
        rows, ["t","t","t","d","m","n","m","n","n"],
        [10,15,22,12,9,9,12,11,10],
        img_col=3, img_key=1)
for cat, arr in J["cat_top_month"].items():
    if not cat.endswith("·剔除专属"): continue
    base = cat.replace("·剔除专属","")
    rows = [[base, g["ref"], g["name"], g["listDate"], g["price"], g["qty"], g["amt"], g["clients"], g["stock"]] for g in arr]
    sheet(f"品类TOP10·{base}·剔专属【需求11】"[:31],
        ["品类","款号","款名","上市时间","价格(¥)","销量","销售额(¥)","下单客户数","实时库存"],
        rows, ["t","t","t","d","m","n","m","n","n"],
        [10,15,22,12,9,9,12,11,10],
        img_col=3, img_key=1,
        note="下单客户数≥2。")

# 18 售罄率（+上市时间价格）
rows = [[s["ref"], s["name"], s.get("listDate",""), s.get("price") or 0, s["sold30"], s["stock"], s["rate"]/100, s["clients"]] for s in J["sell_through_30d"]]
sheet("售罄率排行【需求11】",
    ["款号","款名","上市时间","价格(¥)","近30日销量","当前库存(衣者)","售罄率","客户数"],
    rows, ["t","t","d","m","n","n","pct","n"],
    [15,22,12,9,12,14,10,8],
    img_col=2, img_key=0,
    note="售罄率=近30日销量÷衣者当前库存（累计总进货字段待系统方）；>100%=预售/补单在途。")

# 19 新品上市（三档拆分）
for tier in ["上市1-7天","上市7-15天","上市15-30天"]:
    arr = [p for p in J["new_product"] if p.get("tier") == tier]
    if not arr: continue
    rows = [[p["ref"], p["name"], p["cat"], p["listDate"], p["price"], p["weekQty"], p["weekClients"], p["qty"], p["amt"], p["clients"]] for p in arr]
    sheet(f"新品上市·{tier}【需求1】"[:31],
        ["款号","款名","品类","上市日","价格(¥)","首周销量","首周客户数","累计销量","累计金额(¥)","累计客户数"],
        rows, ["t","t","t","d","m","n","n","n","m","n"],
        [15,22,10,12,9,10,11,10,13,11],
        img_col=2, img_key=0,
        note="档位按上市时间（多客建档日）到生成日：1-7/7-15/15-30天（10-12改，翻单决策用）。")

# 20 新品客户数TOP10（+档位+价格）
rows = [[p.get("tier",""), p["ref"], p["name"], p["cat"], p["listDate"], p.get("price") or 0, p["clients"], p["qty"], p["amt"]] for p in J["new_product_client_top"]]
sheet("新品累计客户数TOP10【需求1】",
    ["上市档位","款号","款名","品类","上市日","价格(¥)","累计客户数","累计销量","累计金额(¥)"],
    rows, ["t","t","t","t","d","m","n","n","m"],
    [12,15,22,10,12,9,11,10,13],
    img_col=3, img_key=1,
    note="普及面对照150家标准；档位=上市1-7/7-15/15-30天。")

# 21 库存最大（+品类上市时间价格）
rows = [[s["ref"], s["name"], s.get("cat",""), s.get("listDate",""), s.get("price") or 0, s["stock"], s["w"], s["m"], s["turn"]] for s in J["stock_max_current_season"]]
sheet("库存最大款(需消化)【需求9附】",
    ["款号","款名","品类","上市时间","价格(¥)","实时库存","近7日销量","近30日销量","预估周转(周)"],
    rows, ["t","t","t","d","m","n","n","n","t"],
    [15,22,10,12,9,10,11,11,12],
    img_col=2, img_key=0,
    note="仅当年当季(2026冬)。周转=库存÷近7日销量。")

# 22 库存告急（新定义：库存<近7日销量×2）
rows = [[s["ref"], s["name"], s.get("cat",""), s.get("listDate",""), s.get("price") or 0, s["stock"], s["w"], s["m"], s["turn"]] for s in J["stock_warn_current_season"]]
sheet("库存告急款【需求9附】",
    ["款号","款名","品类","上市时间","价格(¥)","实时库存","近7日销量","近30日销量","可售周数"],
    rows, ["t","t","t","d","m","n","n","n","p1"],
    [15,22,10,12,9,10,11,11,10],
    img_col=2, img_key=0,
    note="告急定义（10-12改）：总库存<近7日销量×2（卖不过两周即告急）。按可售周数升序=最紧急在前。")

# 23 老客盘活（+手机号）
rows = [[r["name"], r.get("phone") or "—", r["vip"], r["first"], r["last"], r["gapDays"], r["buyN"], r["retN"], r["netQty"], r["netAmt"], r["aov"], r["unitPrice"]] for r in J["revive_90up"]]
sheet("老客盘活名单【需求10】",
    ["客户","手机号","等级","首单时间","最后下单","间隔(天)","下单数","退单数","净件数","净额(¥)","客单价(¥)","件单价(¥)"],
    rows, ["t","t","t","d","d","n","n","n","n","m","m","p1"],
    [20,15,8,12,12,9,8,8,10,13,11,10],
    note="超3个月~2年未下单，按历史净额降序；手机号缺失约两成（档案无号），显示—。")

# 24 流失三档（+手机号）
rows = []
for tier, arr in [("30-60天", J["dormant_30_60"]), ("60天-1年", J["dormant_60_365"]), ("1-2年", J["dormant_365_730"])]:
    for r in arr:
        rows.append([tier, r["name"], r.get("phone") or "—", r["vip"], r["last"], r["gapDays"], r["buyN"], r["retN"], r["buyQty"], r["retQty"], r["buyAmt"], r["retAmt"], r["aov"], r["unitPrice"]])
sheet("客户流失预警三档【需求10】",
    ["档位","客户","手机号","等级","最后下单","间隔(天)","下单数","退单数","购买件数","退货件数","购买金额(¥)","退货金额(¥)","客单价(¥)","件单价(¥)"],
    rows, ["t","t","t","t","d","n","n","n","n","n","m","m","m","p1"],
    [12,20,15,8,12,9,8,8,10,10,13,13,11,10],
    note="三档全量；超2年已剔除；含疑似内部账户待业务负责人确认剔除。")

wb.properties.title = "销售数据报表 2026-10-12（V2.1 改动需求落实版）"
wb.save(OUT)
imgs = sum(len(ws._images) for ws in wb.worksheets)
print("saved:", OUT, "| sheets:", len(wb.sheetnames), "| images:", imgs)
for ws in wb.worksheets:
    print(f"  {ws.title}: {ws.max_row-2}行" + (f" 图{len(ws._images)}" if ws._images else ""))
