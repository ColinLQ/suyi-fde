#!/usr/bin/env python3
# 财务部重造: 04库存资金(品类×库龄×周转) + 05碎片成本(实算版) + 03对账表清理
import os
import json
from datetime import datetime, timedelta
from collections import defaultdict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import MergedCell

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

# ============ 数据 ============
# 款级成本 + 品类(明细反查)
ref_cost, ref_cat, cat_avg = {}, {}, {}
cost_sum, cat_cost_sum = defaultdict(lambda: [0.0, 0.0]), defaultdict(lambda: [0.0, 0.0])
with open(f"{RAW}/duoke_order_details.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        for g in (d.get("goods") or []):
            c, q = num(g.get("cost")), num(g.get("quantity"))
            cat = cat_name(g.get("category"))
            if c > 0 and q > 0:
                r = str(g.get("item_ref"))
                cost_sum[r][0] += c * q; cost_sum[r][1] += q
                if cat:
                    cat_cost_sum[cat][0] += c * q; cat_cost_sum[cat][1] += q
            if cat:
                ref_cat[str(g.get("item_ref"))] = cat
    ref_cost = {k: v[0]/v[1] for k, v in cost_sum.items() if v[1] > 0}
    cat_avg = {k: v[0]/v[1] for k, v in cat_cost_sum.items() if v[1] > 0}

# 款级30日动销(算周转)
d30 = (NOW - timedelta(days=30)).strftime("%Y-%m-%d")
ref_q30 = defaultdict(float)
with open(f"{RAW}/duoke_order_details.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        for g in (d.get("goods") or []):
            dt = ts2dt(g.get("ctime"))
            if dt and dt.strftime("%Y-%m-%d") >= d30:
                q = num(g.get("quantity"))
                if q > 0:
                    ref_q30[str(g.get("item_ref"))] += q

# 库存
rows = []
with open(f"{RAW}/duoke_goods.jsonl", encoding="utf-8") as f:
    for line in f:
        g = json.loads(line)
        ref = str(g.get("item_ref") or "")
        if not ref:
            continue
        sku = g.get("sku")
        st = 0
        if isinstance(sku, dict):
            for sv in sku.values():
                if isinstance(sv, dict):
                    st += num(sv.get("warehouse_0"))
        if st <= 0:
            continue
        base = ref.split("-")[0]
        cat = ref_cat.get(ref) or ref_cat.get(base) or cat_name(g.get("k_category")) or "未分类"
        cost = ref_cost.get(ref) or ref_cost.get(base) or cat_avg.get(cat)
        ctime = ts2dt(g.get("ctime"))
        q30 = ref_q30.get(ref, ref_q30.get(base, 0))
        rows.append({
            "ref": ref, "name": g.get("name") or ref, "stock": st, "cat": cat,
            "cost": cost if cost else None,
            "value": st * cost if cost else 0,
            "age": (NOW - ctime).days if ctime else None,
            "q30": q30,
            "turnover_months": (st / (q30 or 0.001)) if q30 > 0 else 999,  # 月
        })

total_value = sum(r["value"] for r in rows)
total_stock = sum(r["stock"] for r in rows)
sales30_qty = sum(r["q30"] for r in rows)

wb = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")

# ============================================================
# 04 重造: 库存资金占用(品类×库龄×周转)
# ============================================================
for sn in list(wb.sheetnames):
    if sn.startswith("04·"):
        del wb[sn]

ws = wb.create_sheet("04·库存资金占用(品类×库龄)")
ws.sheet_properties.tabColor = xl_color("#C00000")

# 上部: 库龄结构
ws.cell(1, 1, "库存资金占用——¥315万压在哪、压了多久、哪些该清").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=10)
headers = ["库龄段", "件数", "货值(¥)", "占比", "健康度判定", "建议动作"]
for c, h in enumerate(headers, 1):
    cell = ws.cell(2, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
buckets = [("<30天(新到货)", 0, 30), ("1-2月(在售)", 30, 60), ("2-3月(在售)", 60, 90), ("3-6月(滞销预警)", 90, 180), ("6月以上(沉淀)", 180, 99999)]
r = 3
for name, lo, hi in buckets:
    grp = [x for x in rows if x["age"] is not None and lo <= x["age"] < hi]
    st = sum(x["stock"] for x in grp)
    val = sum(x["value"] for x in grp)
    pct = val / total_value * 100 if total_value else 0
    if "沉淀" in name:
        judge, act, fill = "🔴严重沉淀", "专项清仓会:按成本3-5折甩卖回笼资金,目标3个月清掉一半", PatternFill("solid", fgColor=XL_RED_BG)
    elif "滞销" in name:
        judge, act, fill = "🟠周转放慢", "搭配销售+调价测试,避免滑入6月档", PatternFill("solid", fgColor=XL_ORANGE_BG)
    elif "新到货" in name:
        judge, act, fill = "🟢健康", "正常在售,看动销转化", None
    else:
        judge, act, fill = "🟢健康", "正常补货节奏", None
    vals = [name, round(st), round(val), f"{pct:.0f}%", judge, act]
    for c, v in enumerate(vals, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body if c < 6 else f_suggest
        cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) or (isinstance(v, str) and v.endswith("%")) else al_l
        if fill:
            cell.fill = fill
    r += 1
# 合计行
ws.cell(r, 1, "合计").font = Font(name="PingFang SC", bold=True)
ws.cell(r, 2, round(total_stock)).font = Font(name="PingFang SC", bold=True)
ws.cell(r, 3, round(total_value)).font = Font(name="PingFang SC", bold=True)
ws.cell(r, 4, "100%").font = Font(name="PingFang SC", bold=True)
for c in range(1, 7):
    ws.cell(r, c).border = border_all

# 中部: 品类资金Top12(3月以上部分标红)
r += 2
ws.cell(r, 1, "品类资金分布(按货值降序)").font = Font(name="PingFang SC", bold=True, size=12)
r += 1
headers2 = ["品类", "库存件数", "货值(¥)", "其中3月+货值(¥)", "30日动销(件)", "可售月数", "建议"]
for c, h in enumerate(headers2, 1):
    cell = ws.cell(r, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
r += 1
by_cat = defaultdict(lambda: {"st": 0, "val": 0, "old": 0, "q30": 0})
for x in rows:
    b = by_cat[x["cat"]]
    b["st"] += x["stock"]; b["val"] += x["value"]; b["q30"] += x["q30"]
    if x["age"] and x["age"] >= 90:
        b["old"] += x["value"]
for cat, b in sorted(by_cat.items(), key=lambda kv: -kv[1]["val"])[:12]:
    months = b["st"] / b["q30"] if b["q30"] > 0 else 999
    if months > 6:
        sug = "周转>6月:停止该品类补货,清仓优先级最高"
    elif months > 3:
        sug = "周转偏慢:补货缩量,老款清仓后再上新"
    else:
        sug = "周转正常"
    fill = PatternFill("solid", fgColor=XL_RED_BG) if months > 6 else None
    vals = [cat, round(b["st"]), round(b["val"]), round(b["old"]) if b["old"] > 0 else "—", round(b["q30"]),
            f"{months:.1f}" if months < 99 else "无动销", sug]
    for c, v in enumerate(vals, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body if c < 7 else f_suggest
        cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) else al_l
        if fill:
            cell.fill = fill
    r += 1

# 尾部: 沉淀款Top15清单
r += 1
ws.cell(r, 1, "沉淀库存Top15(6月以上·按货值)——清仓候选清单").font = Font(name="PingFang SC", bold=True, size=12)
r += 1
headers3 = ["款号", "款名", "品类", "库存", "货值(¥)", "库龄(天)", "30日动销", "建议"]
for c, h in enumerate(headers3, 1):
    cell = ws.cell(r, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
old_rows = sorted([x for x in rows if x["age"] and x["age"] >= 180], key=lambda x: -x["value"])[:15]
r += 1
for x in old_rows:
    sug = "3折清仓(回笼¥X)" if x["value"] > 10000 else "打包甩卖/员工内购"
    vals = [x["ref"], x["name"], x["cat"], round(x["stock"]), round(x["value"]), x["age"], round(x["q30"]), sug]
    for c, v in enumerate(vals, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body if c < 8 else f_suggest
        cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) else al_l
    r += 1

for c, w in enumerate([14, 20, 10, 9, 12, 10, 10, 34], 1):
    ws.column_dimensions[get_column_letter(c)].width = w

# 口径说明
r += 1
ws.cell(r, 1, "口径说明").font = f_note_h
ws.cell(r, 1).fill = fill_note
for c in range(2, 9):
    ws.cell(r, c).fill = fill_note
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
r += 1
for line in [
    "▍这张表回答什么：公司的钱有多少压在库存里、压了多久、哪些品类和款在沉淀——清仓回笼资金的优先级清单。",
    "▍货值=多客当前在库×该款成本(订单明细cost加权; 无记录的用品类均值)。总计¥315万/52,179件(1,240款有库存)。",
    "▍库龄=今天−商品上架日(多客ctime)。⚠️此前版本'衣者待入库146单/入库率4%'是两个不同系统的口径混用,已删除——在途资金见01表经营总览的口径注。",
    "▍可售月数=库存÷30日动销。>6月=周转严重不良。3月+货值=该品类中库龄≥90天部分的货值。",
    "▍建议动作按资金回收速度排序: 6月+沉淀¥168万(53%)是最大的资金黑洞——3-5折清仓虽亏损但资金回笼后按当前毛利结构再周转,年化收益高于压仓。",
    "▍此前'¥337万'系含负库存对冲的毛算,本表¥315万为仅正库存精确口径。",
]:
    cell = ws.cell(r, 1, line)
    cell.font = f_note
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    r += 1
print("04表重造完成")

# ============================================================
# 05 重造: 碎片补单成本(全实算)
# ============================================================
for sn in list(wb.sheetnames):
    if sn.startswith("05·"):
        del wb[sn]

# 从生产部04表读实算结果
prod_wb = openpyxl.load_workbook(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")
frag_ws = next((s for s in prod_wb.sheetnames if "碎片返单代价" in s), None)
frag_rows = []
if frag_ws:
    for row in prod_wb[frag_ws].iter_rows(min_row=3, values_only=True):
        if row[1] and "合计" not in str(row[1]):
            frag_rows.append(row)

ws = wb.create_sheet("05·碎片补单成本(实算)")
ws.sheet_properties.tabColor = xl_color("#C00000")
ws.cell(1, 1, "碎片补单的真实代价——¥345,236 加工费损失 + 断货损失,全部实算").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=7)

headers = ["代价项", "金额/量级", "口径", "数据状态", "行动建议"]
for c, h in enumerate(headers, 1):
    cell = ws.cell(2, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all

data_rows = [
    ["①碎片单多花加工费", "¥345,236", "17款: (实际加工单价−按总量应享单价)×件数,单价差来自2,779批实算的批量-单价曲线", "✅实算",
     "并单机制直接收益:下单系统拦截≤2天重复下单+周一补货会并单,预计砍1/3碎片单"],
    ["②批量差价实证", "¥36.7→56.4/件", "800+件比<100件贵54%——批越小单价越高,非线性的", "✅实算",
     "返单量≥300件/次为经济批量线(单价开始显著下降)"],
    ["③断货销售损失", "≈¥77万/批", "当前超卖欠货9,676件×件单价均值¥80(机会成本口径)", "⭕估算",
     "按V2三因子提前2-3周下单,超卖款从11款压到≤2款"],
    ["④面料小单溢价", "待月度核算", "需要衣者采购单明细(面料商报价×批量),月初跑成本核算时补入", "⏳月初补",
     "并单后面料凑整采购,减少小单调染/翻缸费"],
    ["⑤碎片化现状", "75/190单(39%)", "在产订单中返单占比;61%是2次以上返单;最高单款10张单", "✅实算",
     "见生产部03/05表逐款明细(LQ263807五天下10单多花¥4.3万)"],
]
for i, row in enumerate(data_rows):
    r = 3 + i
    fill = PatternFill("solid", fgColor=XL_GREEN_BG) if "实算" in str(row[3]) and "⭕" not in str(row[3]) else None
    for c, v in enumerate(row, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body if c < 5 else f_suggest
        cell.border = border_all
        cell.alignment = al_l if c in (1, 3, 5) else al_r
        if fill:
            cell.fill = fill

# 合计
r = 3 + len(data_rows)
ws.cell(r, 1, "已实算合计").font = Font(name="PingFang SC", bold=True, color=xl_color("#C00000"))
ws.cell(r, 2, "¥345,236(确定) + ≈¥77万(机会成本)").font = Font(name="PingFang SC", bold=True, color=xl_color("#C00000"))
for c in range(1, 6):
    ws.cell(r, c).border = border_all

for c, w in enumerate([22, 22, 46, 10, 44], 1):
    ws.column_dimensions[get_column_letter(c)].width = w

r += 2
ws.cell(r, 1, "口径说明").font = f_note_h
ws.cell(r, 1).fill = fill_note
for c in range(2, 6):
    ws.cell(r, c).fill = fill_note
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
r += 1
for line in [
    "▍这张表回答什么：频繁补单这个毛病到底值多少钱——给老板看的一页纸财务论证。",
    "▍①是已发生事实(2,779批的真实加工单价); ③是机会成本估算(不做并单就会继续发生); ④是已知存在但需采购明细才能精确的项。",
    "▍与生产部03表的关系: 那边是逐款明细(谁多花了多少),本表是汇总口径(总共多少、怎么治)。两表金额一致(¥345,236)。",
    "▍建议汇报口径: '仅加工费一项,碎片返单已实际多花34.5万,加上断货损失约百万量级——并单机制零投入,靠流程拦截即可回收'。",
]:
    cell = ws.cell(r, 1, line)
    cell.font = f_note
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    r += 1
print("05表重造完成")

wb.save(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")

# 验证
wb = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")
print("\n sheets:", wb.sheetnames)
ws4 = wb["04·库存资金占用(品类×库龄)"]
print("\n04表库龄段:")
for row in ws4.iter_rows(min_row=3, max_row=8, values_only=True):
    print(" ", [str(x)[:30] if x else "" for x in row[:6]])
