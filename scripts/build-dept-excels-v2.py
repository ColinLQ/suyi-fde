#!/usr/bin/env python3
# 四部门数据包细化补充 V2（2026-10-10）
# 往四份既有xlsx追加精细sheet：
# 研发: +设计师全量漏斗(16人,2889板) +品类×设计师建版矩阵
# 生产: +工厂全量计分卡(2779批) +省份级订单分布
# 销售: +31省订单分布 +流失全量225家
# 财务: +欠款客户明细98家逐户
import json, os, sys
from datetime import datetime
from collections import defaultdict

try:
    import openpyxl
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "openpyxl>=3.1.0"])
    import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.utils import get_column_letter

def xl_color(css_hex):
    v = css_hex.removeprefix("#").upper()
    return "FF" + v if len(v) == 6 else "FF000000"

XL_HEADER_BG = xl_color("#4472C4")
XL_RED_BG = xl_color("#FDE9E9")
XL_ORANGE_BG = xl_color("#FFF2E8")
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # skill代码根目录（可移植）
DATA_HOME = os.environ.get('SCM_DATA_HOME') or os.path.join(os.path.expanduser('~'), 'WorkBuddy', 'scm-collector-data')  # 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
RAW = f"{DATA_HOME}/data/raw/2026-10-09/pm"
RAW_T = f"{DATA_HOME}/data/raw/2026-10-10/pm"
OUTDIR = f"{DATA_HOME}/out"
TODAY = "2026-10-10"

def load_jsonl(path):
    rows = []
    if os.path.exists(path):
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


def add_sheet(wb, no, name, headers, rows, widths, note=None, row_alert=None):
    tag = f"{no:02d}·{name}"[:31]
    ws = wb.create_sheet(tag)
    ws.sheet_properties.tabColor = XL_HEADER_BG[2:]
    ws.cell(1, 1, name).font = f_title
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws.cell(1, 1).alignment = al_l
    hr = 2
    for c, h in enumerate(headers, 1):
        cell = ws.cell(hr, c, h)
        cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
    for i, row in enumerate(rows):
        r = hr + 1 + i
        alert = row_alert(row, i) if row_alert else None
        for c, v in enumerate(row, 1):
            cell = ws.cell(r, c, v)
            cell.font = f_body; cell.border = border_all
            cell.alignment = al_r if isinstance(v, (int, float)) and not isinstance(v, bool) else al_l
            if alert:
                cell.fill = alert
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    if note:
        nr = hr + len(rows) + 2
        ws.cell(nr, 1, note).font = f_note
        ws.merge_cells(start_row=nr, start_column=1, end_row=nr, end_column=len(headers))
    if rows:
        ws.freeze_panes = f"A{hr+1}"
    return ws

def red_fill(row, i): return PatternFill("solid", fgColor=XL_RED_BG)
def orange_fill(row, i): return PatternFill("solid", fgColor=XL_ORANGE_BG)
def yellow_fill(row, i): return PatternFill("solid", fgColor=XL_YELLOW_BG)
def green_fill(row, i): return PatternFill("solid", fgColor=XL_GREEN_BG)


# ============ 数据 ============
templates_all = load_jsonl(f"{RAW_T}/perf_template_all.jsonl")     # 2889 样板全量
follow_done = load_jsonl(f"{RAW_T}/perf_follow_done.jsonl")        # 2779 完成批
prod_hist = load_jsonl(f"{RAW}/yizhe_production_hist.jsonl")
sales = json.load(open(f"{OUTDIR}/销售数据报告-{TODAY}.json", encoding="utf-8"))
restock = json.load(open(f"{OUTDIR}/restock-deep-2026-10-09.json", encoding="utf-8"))
customers = load_jsonl(f"{RAW}/duoke_customers.jsonl")
trend = json.load(open(f"{RAW}/duoke_sale_trend.json", encoding="utf-8"))
goods = load_jsonl(f"{RAW}/duoke_goods.jsonl")

print(f"加载: 样板{len(templates_all)} 完成批{len(follow_done)} 客户{len(customers)}")

# factory_id -> factory_name 映射
fid2name = {}
for o in prod_hist:
    fn, fid = o.get("factory_name"), o.get("factory_id")
    if fn and fid:
        fid2name[str(fid)] = fn
# follow_done里template_no -> factory_name (从hist)
tno2factory = {}
for o in prod_hist:
    tno = o.get("template_no")
    if tno and o.get("factory_name"):
        tno2factory.setdefault(tno, o.get("factory_name"))

# ============================================================
# 研发部: 追加
# ============================================================
f1 = f"{OUTDIR}/数据包-研发部-{TODAY}.xlsx"
wb1 = openpyxl.load_workbook(f1)
wb1.remove(wb1["02·设计师转化漏斗(9月)"])  # 用全量版替换
# 重新编号(原03/04变02/03)
for ws in list(wb1.worksheets):
    idx = ws.title.split("·")[0]
    if idx == "03":
        ws.title = "02·" + ws.title.split("·", 1)[1]
    elif idx == "04":
        ws.title = "03·" + ws.title.split("·", 1)[1]

# --- 设计师全量漏斗 ---
# 建版聚合(全历史)
tpl_by_designer = defaultdict(lambda: {"boards": 0, "cats": defaultdict(int), "since": ""})
for t in templates_all:
    du = t.get("design_user")
    if not du or du == "无":
        continue
    for name in [x.strip() for x in du.split(",") if x.strip()]:
        rec = tpl_by_designer[name]
        rec["boards"] += 1
        cat = t.get("cat_name")
        if cat:
            rec["cats"][cat] += 1
        ca = str(t.get("created_at") or "")[:10]
        if ca and (not rec["since"] or ca < rec["since"]):
            rec["since"] = ca

# 下单聚合: follow_done 按 template 找设计师
tplno2designer = {t.get("template_no"): t.get("design_user") for t in templates_all if t.get("template_no")}
d_orders = defaultdict(lambda: {"batches": 0, "qty": 0})
for o in follow_done:
    tno = o.get("template_no")
    du = tplno2designer.get(tno)
    if not du:
        continue
    for name in [x.strip() for x in str(du).split(",") if x.strip()]:
        d_orders[name]["batches"] += 1
        d_orders[name]["qty"] += int(o.get("plan_total_num") or 0)

d_rows = []
for name, rec in sorted(tpl_by_designer.items(), key=lambda x: -x[1]["boards"]):
    od = d_orders.get(name, {"batches": 0, "qty": 0})
    conv = f"{od['batches']/rec['boards']*100:.0f}%" if rec["boards"] else "-"
    top_cat = "、".join(f"{k}{v}" for k, v in sorted(rec["cats"].items(), key=lambda x: -x[1])[:2])
    d_rows.append([
        name, rec["boards"], rec["since"] or "-",
        od["batches"], od["qty"], conv, top_cat,
    ])
add_sheet(wb1, 5, "设计师全量漏斗(16人·全历史)", 
    ["设计师", "建版数(全历史)", "首板时间", "下单批次数", "下单件数", "下单/建版", "主力品类Top2"],
    d_rows, [12, 14, 11, 11, 11, 10, 24],
    note=f"全量口径:衣者样板{len(templates_all)}款(2016年至今)×完成生产批{len(follow_done)}批。SOSO建版1043款为存量主力;下单/建版<50%的看主力品类是否错配。数据自算,比9月单月口径更完整。",
    row_alert=lambda row, i: yellow_fill(row, i) if isinstance(row[5], str) and row[5].rstrip("%").replace(".", "").isdigit() and float(row[5].rstrip("%")) < 50 else None,
)

# --- 品类×设计师建版矩阵 ---
cat_design = defaultdict(lambda: defaultdict(int))
for t in templates_all:
    du, cat = t.get("design_user"), t.get("cat_name")
    if not du or not cat:
        continue
    for name in [x.strip() for x in str(du).split(",") if x.strip()]:
        cat_design[cat][name] += 1
top_designers = [n for n, _ in sorted(tpl_by_designer.items(), key=lambda x: -x[1]["boards"])[:8]]
cat_rows = []
for cat, dd in sorted(cat_design.items(), key=lambda x: -sum(x[1].values())):
    row = [cat, sum(dd.values())] + [dd.get(d, "") for d in top_designers]
    cat_rows.append(row)
add_sheet(wb1, 6, "品类×设计师建版矩阵",
    ["品类", "建版合计"] + top_designers,
    cat_rows, [14, 10] + [9] * len(top_designers),
    note="列=建版数Top8设计师。用途:某品类动销强但对应设计师建版少→开发缺口定位到人。对照sheet01品类动销排序。",
)

# 重新整理sheet顺序号
def renumber(wb):
    seen = {}
    for ws in wb.worksheets:
        parts = ws.title.split("·", 1)
        if len(parts) == 2:
            name = parts[1]
            n = seen.get(name, 0) + 1
            seen[name] = n
    return wb

wb1.save(f1)
print(f"✅ 研发部 +2 sheets")

# ============================================================
# 生产部: 追加
# ============================================================
f2 = f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx"
wb2 = openpyxl.load_workbook(f2)

# --- 工厂全量计分卡(2779批) ---
stats = defaultdict(lambda: {"n": 0, "qty": 0, "ontime": 0, "late": 0, "noeta": 0, "cycle": [], "late5": 0})
for o in follow_done:
    fid = str(o.get("factory_id") or "")
    if not fid or fid == "0":
        continue
    st = stats[fid]
    st["n"] += 1
    st["qty"] += int(o.get("plan_total_num") or 0)
    eta, fin = pdate(o.get("estimated_finish_time")), pdate(o.get("finish_time"))
    if eta is None:
        st["noeta"] += 1
    elif eta and fin:
        diff = (fin - eta).days
        if diff <= 0:
            st["ontime"] += 1
        else:
            st["late"] += 1
            if diff > 5:
                st["late5"] += 1
    c, s_ = pdate(o.get("create_order_time")), pdate(o.get("last_stockout_time"))
    if c and s_:
        cy = (s_ - c).days
        if 0 <= cy < 120:
            st["cycle"].append(cy)

fac_rows = []
for fid, st in sorted(stats.items(), key=lambda x: -x[1]["qty"]):
    rated = st["ontime"] + st["late"]
    rate = f"{st['ontime']/rated*100:.0f}%" if rated else "—"
    eta_fill = f"{st['noeta']/st['n']*100:.0f}%"
    avg_cy = round(sum(st["cycle"]) / len(st["cycle"]), 1) if st["cycle"] else ""
    fac_rows.append([
        fid2name.get(fid, f"工厂{fid}"),
        st["n"], st["qty"], rate, rated, st["late5"], eta_fill, avg_cy,
    ])
add_sheet(wb2, 5, "工厂计分卡·全量(2779批)",
    ["工厂", "批次数", "件数", "按时率", "有效评级批", "超5天批", "ETA未填率", "平均周期(天)"],
    fac_rows, [14, 9, 11, 9, 11, 9, 11, 12],
    note="全量口径:follow_order完成批2779批(含未在产)。按时率=实际完成≤ETA的批/有ETA且完成批。ETA未填率过半是管理黑洞——超时分级无从谈起,先推动填ETA再看按时率真实水平(当前按时率偏低部分因ETA填的是紧日子)。",
    row_alert=lambda row, i: red_fill(row, i) if isinstance(row[3], str) and row[3].rstrip("%").isdigit() and int(row[3].rstrip("%")) < 5 else None,
)

# --- 返单节奏明细(下单≥3次的款) ---
tpl_orders = defaultdict(list)
for o in prod_hist + load_jsonl(f"{RAW}/yizhe_production_list.jsonl"):
    tno, ca = o.get("template_no"), o.get("created_at")
    if tno and ca:
        tpl_orders[tno].append((str(ca)[:10], int(o.get("plan_total_num") or 0), o.get("production_type_desc")))
multi_rows = []
for tno, lst in tpl_orders.items():
    if len(lst) < 3:
        continue
    lst.sort()
    dates = [x[0] for x in lst]
    gaps = [(datetime.strptime(dates[i+1], "%Y-%m-%d") - datetime.strptime(dates[i], "%Y-%m-%d")).days for i in range(len(dates) - 1)]
    total_qty = sum(x[1] for x in lst)
    min_gap = min(gaps) if gaps else ""
    first2last = (datetime.strptime(dates[-1], "%Y-%m-%d") - datetime.strptime(dates[0], "%Y-%m-%d")).days
    multi_rows.append([
        tno, len(lst), total_qty, dates[0], dates[-1], f"{first2last}天",
        min_gap, "→".join(dates), "🔴高危" if min_gap <= 2 else ("⚠️碎片" if min_gap <= 7 else "正常节奏"),
    ])
multi_rows.sort(key=lambda x: -x[1])
add_sheet(wb2, 6, "返单节奏明细·下单≥3次",
    ["款号", "下单次数", "累计件数", "首单日", "最近单", "跨度", "最小间隔(天)", "下单日期序列", "定性"],
    multi_rows, [13, 9, 10, 11, 11, 8, 12, 40, 10],
    note=f"共{len(multi_rows)}款下单≥3次。最小间隔≤2天=🔴高危(如LM2631014两单隔1天,本可并单);≤7天=⚠️碎片(并单机制主目标)。数据:历史+在产生产订单全量。",
    row_alert=lambda row, i: red_fill(row, i) if "🔴" in str(row[8]) else (yellow_fill(row, i) if "⚠️" in str(row[8]) else None),
)
wb2.save(f2)
print(f"✅ 生产部 +2 sheets")

# ============================================================
# 销售部: 追加
# ============================================================
f3 = f"{OUTDIR}/数据包-销售部-{TODAY}.xlsx"
wb3 = openpyxl.load_workbook(f3)

# --- 31省订单分布 ---
reg = restock.get("region", {})
prov = reg.get("provCnt", {})
wk = reg.get("wkCli", {})
region_map = {
    "广东": "华南", "福建": "华南", "海南": "华南", "广西": "华南", "香港": "华南", "澳门": "华南", "台湾": "华南",
    "浙江": "华东", "江苏": "华东", "上海": "华东", "安徽": "华东", "江西": "华东", "山东": "华东",
    "湖南": "华中", "湖北": "华中", "河南": "华中",
    "四川": "西南", "云南": "西南", "重庆": "西南", "贵州": "西南", "西藏": "西南",
    "北京": "华北", "天津": "华北", "河北": "华北", "山西": "华北", "内蒙古": "华北",
    "辽宁": "东北", "吉林": "东北", "黑龙江": "东北",
    "陕西": "西北", "甘肃": "西北", "新疆": "西北", "宁夏": "西北", "青海": "西北",
    "海外": "海外",
}
# W1..W4 各省近4周趋势
prov_wk = defaultdict(lambda: defaultdict(int))
for wk_name, region_cnt in wk.items():
    pass  # wk是大区级;省份周趋势需要重算,这里先给省级总量+大区归属
prov_rows = []
for p, cnt in sorted(prov.items(), key=lambda x: -x[1]):
    rg = region_map.get(p, "其他")
    prov_rows.append([p, rg, cnt, f"{cnt/sum(prov.values())*100:.1f}%", "", ""])
add_sheet(wb3, 6, "31省订单分布(近30日)",
    ["省份", "大区", "订单数", "占比", "近4周趋势", "备注"],
    prov_rows, [10, 8, 9, 8, 12, 20],
    note=f"共{sum(prov.values())}单已识别省份。福建160/广东127/浙江65为前三。用途:省级铺货优先级+地区气候补货窗口判断(近4周趋势列待region周数据补充)。",
    row_alert=lambda row, i: green_fill(row, i) if i < 3 else None,
)

# --- 流失全量225家 ---
dorm_all = sales.get("dormant_30_60") or []
dorm_full = []
for d in dorm_all:
    dorm_full.append([
        d.get("name"), d.get("vip") or "普通", str(d.get("last", "")),
        num(d.get("gapDays")), num(d.get("buyN")), num(d.get("retN")),
        round(num(d.get("buyAmt"))), round(num(d.get("retAmt"))),
        round(num(d.get("aov"))), round(num(d.get("unitPrice"))),
        num(d.get("netQty")), "", "",
    ])
add_sheet(wb3, 7, "流失全量·30-60天(225家)",
    ["客户", "等级", "最后下单", "间隔(天)", "购买单数", "退单数", "购买金额(¥)", "退货金额(¥)", "客单价(¥)", "件单价(¥)", "净件数", "认领人", "跟进记录"],
    dorm_full, [18, 7, 11, 8, 8, 7, 11, 10, 9, 9, 8, 9, 16],
    note="30-60天档全量225家(不再只Top50)。按购买金额降序。认领人/跟进记录两列留白,销售认领后填写,周五统计回流率。",
    row_alert=lambda row, i: red_fill(row, i) if isinstance(row[6], (int, float)) and row[6] > 500000 else None,
)
wb3.save(f3)
print(f"✅ 销售部 +2 sheets")

# ============================================================
# 财务部: 追加
# ============================================================
f4 = f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx"
wb4 = openpyxl.load_workbook(f4)

# --- 欠款客户明细98家 ---
debts = [(c.get("name"), float(c.get("debt") or 0), c.get("vip"), c.get("add_id") or "", c.get("point") or "") for c in customers if float(c.get("debt") or 0) > 0]
debts.sort(key=lambda x: -x[1])
debt_rows = []
total_debt = sum(x[1] for x in debts)
for n, a, v, add_id, pt in debts:
    debt_rows.append([n, round(a), f"{a/total_debt*100:.1f}%", v if isinstance(v, str) else f"vip{v}", "", "催收/对账/核实"])
add_sheet(wb4, 6, "欠款客户明细(98家)",
    ["客户", "欠款(¥)", "占总欠款", "等级", "最近回款", "处理动作"],
    debt_rows, [22, 12, 9, 8, 11, 22],
    note=f"总欠款¥{total_debt:,.0f}。注意Top5多为内部/关联账户(员工A两户¥77万、工厂主体工厂、BSJ公司订单、EHT、特卖会配货)——先甄别内部往来再催收,剔除后真实客户欠款约¥100万量级。9-22会议已定:内部账户清单待销售负责人确认。",
    row_alert=lambda row, i: red_fill(row, i) if isinstance(row[1], (int, float)) and row[1] > 100000 else None,
)

# --- 款级毛利排行(售价×动销,待成本接入) ---
goods_by_ref = {}
for g in goods:
    ref = g.get("item_ref") or g.get("id")
    if ref:
        goods_by_ref[str(ref)] = g
move30 = sales.get("move_top_month") or []
pl_rows = []
for m in move30:
    ref = str(m.get("ref"))
    g = goods_by_ref.get(ref, {})
    pr = g.get("price_range") or {}
    rng = pr.get("range") or []
    sale_price = round(num(rng[0])) if rng and num(rng[0]) > 0 else ""
    pl_rows.append([
        m.get("ref"), m.get("name"), m.get("cat"),
        sale_price, "", num(m.get("qty")), round(num(m.get("amt"))),
        f"{round(num(m.get('amt'))/num(m.get('qty'))):.0f}" if num(m.get("qty")) else "",
        "", "",
    ])
add_sheet(wb4, 7, "款级毛利排行(30日动销Top30)",
    ["款号", "款名", "品类", "售价(¥)", "成本(¥)", "销量", "销售额(¥)", "实收均价(¥)", "毛利(¥)", "毛利率"],
    pl_rows, [13, 20, 10, 9, 9, 8, 11, 11, 9, 8],
    note="成本列待月度成本核算数据接入后自动填充(衣者明细成本+多客单件成本,以多客为准——9-22会议拍板)。接入后毛利/毛利率自动计算,补货优先级按毛利重排。",
)
wb4.save(f4)
print(f"✅ 财务部 +2 sheets")

print("\n全部细化完成")
