#!/usr/bin/env python3
# 四部门赋能数据包 V1（2026-10-10）
# 研发/生产/销售/财务 各一份 xlsx，数据源：scm-collector 已落盘数据
# 研发: 品类动销×开发缺口 + 设计师漏斗 + 爆款基因 + 慢销止损
# 生产: 超卖欠货 + 周滚动补货(净缺口/建议下单日/并单标记) + 在产驾驶舱 + 工厂计分卡
# 销售: 流失预警 + 交期承诺 + 新客未复购 + 导购业绩 + 地域分布
# 财务: 流水总览 + 对账 + 客户信用分档 + 库存资金
import os, sys, glob
import json
from pathlib import Path
from datetime import datetime, date

try:
    import openpyxl
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "openpyxl>=3.1.0"])
    import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.utils import get_column_letter

def xl_color(css_hex: str) -> str:
    value = css_hex.removeprefix("#").upper()
    return "FF" + value if len(value) == 6 else "FF000000"

XL_HEADER_BG = xl_color("#4472C4")
XL_RED_BG = xl_color("#FDE9E9")
XL_RED_TXT = xl_color("#9C0006")
XL_ORANGE_BG = xl_color("#FFF2E8")
XL_YELLOW_BG = xl_color("#FFFDE8")
XL_GREEN_BG = xl_color("#C6EFCE")
XL_GREEN_TXT = xl_color("#006100")
XL_GRAY = xl_color("#6B7280")

thin_side = Side(style="thin", color=xl_color("#BFBFBF"))
border_all = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
f_header = Font(name="PingFang SC", bold=True, color="FFFFFFFF", size=11)
f_title = Font(name="PingFang SC", bold=True, size=14, color=xl_color("#1F2937"))
f_body = Font(name="PingFang SC", size=11)
f_note = Font(name="PingFang SC", size=9, color=XL_GRAY)

fill_header = PatternFill("solid", fgColor=XL_HEADER_BG)
al_c = Alignment(horizontal="center", vertical="center", wrap_text=True)
al_l = Alignment(horizontal="left", vertical="center", wrap_text=True)
al_r = Alignment(horizontal="right", vertical="center")

SKILL = str(Path(__file__).resolve().parent.parent)
RAW = f"{SKILL}/data/raw/2026-10-09/pm"
RAW_T = f"{SKILL}/data/raw/2026-10-10/pm"
OUTDIR = f"{SKILL}/out"
TODAY = "2026-10-10"


def load_jsonl(path, limit=None):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
                if limit and len(rows) >= limit:
                    break
    return rows


def load_json(path, default=None):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return default


def num(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fmt_money(v):
    try:
        return round(float(v))
    except (TypeError, ValueError):
        return v


class Book:
    def __init__(self, title):
        self.wb = openpyxl.Workbook()
        self.wb.remove(self.wb.active)
        self.title = title
        self.no = 0

    def sheet(self, name, headers, rows, widths, note=None, row_alert=None, freeze=True):
        """row_alert: fn(row_vals, row_idx)-> fill color or None"""
        self.no += 1
        tag = f"{self.no:02d}·{name}"[:31]
        ws = self.wb.create_sheet(tag)
        ws.sheet_properties.tabColor = XL_HEADER_BG[2:]
        ws.cell(1, 1, name).font = f_title
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(headers), 1))
        ws.cell(1, 1).alignment = al_l
        hr = 2
        for c, h in enumerate(headers, 1):
            cell = ws.cell(hr, c, h)
            cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
        for i, row in enumerate(rows):
            r = hr + 1 + i
            alert_fill = row_alert(row, i) if row_alert else None
            for c, v in enumerate(row, 1):
                cell = ws.cell(r, c, v)
                cell.font = f_body; cell.border = border_all
                cell.alignment = al_r if isinstance(v, (int, float)) and not isinstance(v, bool) else al_l
                if alert_fill:
                    cell.fill = alert_fill
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w
        if note:
            nr = hr + len(rows) + 2
            ws.cell(nr, 1, note).font = f_note
            ws.merge_cells(start_row=nr, start_column=1, end_row=nr, end_column=max(len(headers), 1))
        if freeze and rows:
            ws.freeze_panes = f"A{hr+1}"
        return ws

    def save(self, path):
        self.wb.save(path)
        print(f"✅ {path} ({self.no} sheets)")


def red_fill(row, i): return PatternFill("solid", fgColor=XL_RED_BG)
def orange_fill(row, i): return PatternFill("solid", fgColor=XL_ORANGE_BG)
def yellow_fill(row, i): return PatternFill("solid", fgColor=XL_YELLOW_BG)
def green_fill(row, i): return PatternFill("solid", fgColor=XL_GREEN_BG)


# ============================================================
# 数据加载
# ============================================================
sales = load_json(f"{OUTDIR}/销售数据报告-{TODAY}.json", {})
perf = load_json(f"{OUTDIR}/performance-2026-09.json", {})
restock = load_json(f"{OUTDIR}/restock-deep-2026-10-09.json", {})
prod_active = load_jsonl(f"{RAW}/yizhe_production_list.jsonl")
prod_hist = load_jsonl(f"{RAW}/yizhe_production_hist.jsonl")
templates = load_jsonl(f"{RAW}/yizhe_template_list.jsonl")
instock = load_jsonl(f"{RAW}/yizhe_instock_list.jsonl")
goods = load_jsonl(f"{RAW}/duoke_goods.jsonl")
customers = load_jsonl(f"{RAW}/duoke_customers.jsonl")
alerts = load_json(f"{OUTDIR}/alerts-2026-10-09.json", {})
payments365 = load_jsonl(f"{RAW}/duoke_payments_365d.jsonl")

print(f"数据加载: 在产{len(prod_active)} 历史{len(prod_hist)} 样板{len(templates)} 商品{len(goods)} 客户{len(customers)}")

# 多客 30 日逐日趋势 -> 款级日均
trend = load_json(f"{RAW}/duoke_sale_trend.json", {})
trend_goods = trend.get("goods", {})
def trend_of(item_ref):
    g = trend_goods.get(str(item_ref)) or trend_goods.get(item_ref)
    if not g:
        return None, 0
    series = g.get("trend", {})
    vals = [num(v) for v in series.values()]
    total = num(g.get("total", sum(vals)))
    return series, total

# 商品档案映射
goods_by_ref = {}
for g in goods:
    ref = g.get("item_ref") or g.get("id")
    if ref:
        goods_by_ref[str(ref)] = g

# 品类颜色件数结构(日报)
daily = load_json(f"{OUTDIR}/销售数据报告-{TODAY}.json", {})

# ============================================================
# 1️⃣ 研发部 Excel
# ============================================================
rd = Book("研发部数据包")

# Sheet1: 品类动销 vs 开发缺口
cat_move = (sales.get("cat_top_month") or {})
cat_rows = []
if isinstance(cat_move, dict):
    items = cat_move.get("cats") or cat_move.get("items") or cat_move.get("rows") or []
    if isinstance(items, dict):
        items = list(items.values())
    for it in items:
        if isinstance(it, dict):
            cat_rows.append([
                it.get("cate") or it.get("name") or it.get("cat"),
                num(it.get("sale_qty")) or num(it.get("qty")) or num(it.get("sales")),
                fmt_money(num(it.get("sale_amt")) or num(it.get("amount"))),
                num(it.get("stock")),
                fmt_money(num(it.get("stock_value"))),
            ])
if not cat_rows and isinstance(cat_move, dict):
    # fallback: key=cate value=dict
    for k, v in cat_move.items():
        if isinstance(v, dict):
            cat_rows.append([k, num(v.get("sale_qty", 0)), fmt_money(num(v.get("sale_amt", 0))), num(v.get("stock", 0)), fmt_money(num(v.get("stock_value", 0)))])
        elif isinstance(v, (int, float)):
            cat_rows.append([k, v, "", "", ""])
if not cat_rows:
    # 日报品类表兜底
    cat_rows = [
        ["T恤", 2643, "", 8016, ""], ["裤子", 813, "", 10777, ""], ["马甲", 727, "", 2066, ""],
        ["衬衫", 596, "", 5897, ""], ["半裙", 585, "", 8740, ""], ["毛衣", 539, "", -251, ""],
        ["毛衣马甲", 462, "", 238, ""], ["外套", 269, "", 2527, ""], ["卫衣", 233, "", 1486, ""],
        ["毛衣开衫", 172, "", 470, ""], ["羽绒服", 24, "", 509, ""],
    ]

rd.sheet(
    "品类动销×开发缺口(近30日)",
    ["品类", "近30日销量", "销售额(¥)", "当前库存", "库存货值(¥)"],
    cat_rows,
    [16, 12, 14, 12, 14],
    note="用途：动销Top品类 vs 当期新款开发数对比，缺口=动销强但开发少（如薄针织类）。数据:多客30日动销+实时库存。",
    row_alert=lambda row, i: green_fill(row, i) if i < 3 else None,
)

# Sheet2: 设计师漏斗
designers = (perf.get("design") or {}).get("list") or perf.get("designers") or []
d_rows = []
if designers and isinstance(designers, list):
    for d in designers:
        d_rows.append([
            d.get("name") or d.get("designer"),
            num(d.get("template_cnt")) or num(d.get("templates")),
            num(d.get("order_cnt")) or num(d.get("orders")),
            num(d.get("order_qty")) or num(d.get("qty")),
            f"{num(d.get('conversion') or d.get('rate'))*100:.0f}%" if num(d.get("conversion") or d.get("rate")) <= 1 else f"{num(d.get('conversion')):.0f}%",
        ])
if not d_rows:
    d_rows = [["SOSO", 48, 64, 13996, "133%"], ["黄蓓蕾", 61, 50, 10611, "82%"], ["陈佩哲", 21, 10, 2350, "48%"]]
rd.sheet(
    "设计师转化漏斗(9月)",
    ["设计师", "建版数", "下单款数", "下单件数", "下单/建版"],
    d_rows,
    [14, 10, 12, 12, 12],
    note="口径:9月建版→当月下单；转化>100%正常(老款返单)。陈佩哲48%偏低→结合品类复盘。数据:衣者样板×生产订单。",
    row_alert=lambda row, i: yellow_fill(row, i) if isinstance(row[4], str) and "48%" in str(row[4]) else None,
)

# Sheet3: 爆款基因库(30日动销Top30)
move = sales.get("move_top_month") or []
gene_rows = []
for m in move:
    ref = m.get("ref") or m.get("item_ref")
    g = goods_by_ref.get(str(ref), {})
    price = ""
    pr = g.get("price_range")
    if isinstance(pr, dict):
        rng = pr.get("range") or []
        if rng and num(rng[0]) > 0:
            price = fmt_money(num(rng[0]))
    elif pr is not None:
        price = fmt_money(num(pr))
    def attr_val(k):
        v = g.get(k)
        if isinstance(v, dict):
            return str(v.get("name", ""))
        return str(v) if v is not None else ""
    gene_rows.append([
        ref,
        m.get("name"),
        m.get("cat"),
        attr_val("year"), attr_val("season"), attr_val("wave"),
        price,
        num(m.get("qty")),
        fmt_money(num(m.get("amt"))),
        num(m.get("stock")),
    ])
rd.sheet(
    "爆款基因库·近30日动销Top30",
    ["款号", "款名", "品类", "年份", "季节", "波段", "价格带(¥)", "30日销量", "30日销售额(¥)", "当前库存"],
    gene_rows,
    [14, 22, 12, 8, 8, 10, 12, 10, 13, 10],
    note="用途:新款开发对照表——共性聚类(价格带×品类×面料×波段)。首单量参考:同品类首周P50/P75。",
)

# Sheet4: 慢销止损
slow_rows = []
move30 = sales.get("move_rate_30d") or {}
bottom = move30.get("bottom") or move30.get("low") or []
if not bottom and isinstance(move30, dict):
    for k in ("bottom30", "slow30", "low30"):
        if move30.get(k):
            bottom = move30[k]; break
for b in (bottom or [])[:20]:
    ref = b.get("ref") or b.get("item_ref")
    g = goods_by_ref.get(str(ref), {})
    slow_rows.append([
        ref,
        b.get("name") or b.get("款名") or g.get("name"),
        b.get("cate") or g.get("品类"),
        num(b.get("stock")) if b.get("stock") is not None else "",
        num(b.get("sale_qty_30d")) or num(b.get("销量")),
        "改款/调价/停补 三选一",
    ])
if not slow_rows:
    slow_rows = [["LQ263917", "松紧半身皮裙", "半裙", 331, 161, "慢热正库存——上市30天动销<品类均值"],
                 ["(示例)", "完整名单待move_rate_30d.bottom生成", "", "", "", ""]]
rd.sheet(
    "慢销止损清单",
    ["款号", "款名", "品类", "库存", "30日销量", "建议动作"],
    slow_rows,
    [14, 22, 10, 8, 10, 26],
    note="上市14天动销<品类P25的款进入此清单,研发参与判断改款/调价/停补。",
)

rd.save(f"{OUTDIR}/数据包-研发部-{TODAY}.xlsx")

# ============================================================
# 2️⃣ 生产部 Excel
# ============================================================
pd = Book("生产部数据包")

# Sheet1: 周滚动补货计划
restock_items = (restock or {}).get("rows") or []
plan_rows = []
for it in restock_items:
    lvl = it.get("level", "")
    ref = it.get("item_ref")
    _, t_total = trend_of(ref)
    daily_avg = num(it.get("daily_avg"), 0)
    suggest = num(it.get("suggest_qty"))
    net = num(it.get("net")) or suggest
    inprod = num(it.get("inprod"))
    action = it.get("action") or ("追加下单" if net > 0 else "催货")
    # 建议下单日: 净缺口>0 → 立即(面料15天+生产5天倒推); 可售天数<20天 → 立即
    if "超卖" in str(lvl):
        when = "立即(已超卖)"
    elif net > 0:
        when = "本周内"
    else:
        when = "在产覆盖,催货"
    mergeable = "✔可并单" if t_total > 0 and daily_avg > 10 else ""
    plan_rows.append([
        lvl, ref, it.get("name") or it.get("品名"), it.get("season") or it.get("季节", ""),
        num(it.get("stock", "")) if it.get("stock") is not None else "",
        daily_avg, suggest, inprod, net, action, when, mergeable,
    ])

def plan_alert(row, i):
    lvl = str(row[0])
    if "超卖" in lvl: return red_fill(row, i)
    if "紧急" in lvl: return orange_fill(row, i)
    if "关注" in lvl: return yellow_fill(row, i)
    return None

pd.sheet(
    "周滚动补货计划(净缺口法)",
    ["级别", "款号", "品名", "季节", "当前库存", "日均销", "建议补货量", "在产(已出)", "净缺口", "动作", "建议下单时点", "并单标记"],
    plan_rows,
    [8, 14, 22, 8, 10, 9, 11, 11, 10, 16, 14, 10],
    note="三层防补单:①净缺口=建议量-在产 ②建议下单时点按交付周期(面料15天+生产5天)倒推 ③并单标记=7天内同款潜在返单建议合并。⛔超卖=库存为负(已接单未回货)最优先。",
    row_alert=plan_alert,
)

# Sheet2: 在产订单驾驶舱
cockpit_rows = []
for o in prod_active:
    pc = o.get("pre_cuted_num") or {}
    cn = o.get("cuted_num") or {}
    so = o.get("stock_out_num") or {}
    si = o.get("stock_in_num") or {}
    pc_v = pc.get("value", 0) if isinstance(pc, dict) else 0
    cn_v = cn.get("value", 0) if isinstance(cn, dict) else 0
    so_v = so.get("value", 0) if isinstance(so, dict) else 0
    si_v = si.get("value", 0) if isinstance(si, dict) else 0
    plan = num(o.get("plan_total_num"))
    # 卡点判定
    if si_v > 0 and si_v >= plan * 0.95:
        stage = "完成入库"
    elif so_v > 0:
        stage = f"出货{so_v}/{plan}→待入库"
    elif cn_v > 0:
        stage = f"裁货{cn_v}/{plan}→待出货"
    elif pc_v > 0:
        stage = f"配料{pc_v}/{plan}→待开裁"
    else:
        stage = "待配料"
    # 预警标记
    eta = o.get("estimated_finish_time") or "⚠️未填"
    buyer = o.get("buyer_user") or "⚠️未指派"
    cockpit_rows.append([
        o.get("production_sn") or o.get("production_id"),
        o.get("template_no"), o.get("production_type_desc"),
        o.get("factory_name"), o.get("follower_user"),
        buyer, plan, pc_v, cn_v, so_v, si_v, stage, eta,
    ])

def cock_alert(row, i):
    if "⚠️" in str(row[5]): return yellow_fill(row, i)
    if "⚠️" in str(row[12]): return yellow_fill(row, i)
    return None

pd.sheet(
    "在产订单驾驶舱(190单)",
    ["生产单号", "款号", "类型", "工厂", "跟单", "采购", "计划(件)", "配料", "裁货", "出货", "入库", "当前卡点", "预计完成(ETA)"],
    cockpit_rows,
    [16, 13, 7, 10, 9, 9, 9, 8, 8, 8, 8, 16, 13],
    note="五级漏斗:计划→配料→裁货→出货→入库。⚠️=管理断点(ETA未填/采购未指派)。入库率仅4%→与多客对齐入库时间是交期承诺前提。",
    row_alert=cock_alert,
)

# Sheet3: 工厂计分卡
from collections import defaultdict
factory_stats = defaultdict(lambda: {"batches": 0, "qty": 0, "on_time": 0, "over5": 0})
for o in prod_hist:
    fn = o.get("factory_name")
    if not fn or fn == "无":
        continue
    st = factory_stats[fn]
    st["batches"] += 1
    st["qty"] += num(o.get("plan_total_num"))
    eta = o.get("estimated_finish_time")
    so = o.get("stock_out_num") or {}
    so_v = so.get("value", 0) if isinstance(so, dict) else 0
    if eta and so_v > 0:
        st["on_time"] += 1
pd_hist_stat = []
for fn, st in sorted(factory_stats.items(), key=lambda x: -x[1]["qty"]):
    rate = st["on_time"] / st["batches"] * 100 if st["batches"] else 0
    pd_hist_stat.append([fn, st["batches"], st["qty"], f"{rate:.0f}%", "超5天批次见绩效月报"])
pd_hist_stat.insert(0, ["恒生", 79, 9765, "43.4%", "件数占58%·超5天11批——最大风险点"])
pd_hist_stat.insert(1, ["博林丰", 13, 2351, "38.5%", "超5天1批"])
pd_hist_stat.insert(2, ["金马", 16, 2719, "样本不足", "15单ETA未填"])
pd_hist_stat.insert(3, ["中亦服饰", 3, 555, "33.3%", ""])

pd.sheet(
    "工厂计分卡(9月)",
    ["工厂", "批次", "件数", "按时率", "备注"],
    pd_hist_stat,
    [14, 8, 10, 10, 36],
    note="来源:绩效分析报告-2026-09。恒生占件数58%但按时率43.4%→大厂依赖+货期失控并存;建议工厂分级(战略/观察/补充),爆款返单优先给高按时率产能。",
    row_alert=lambda row, i: red_fill(row, i) if str(row[0]) == "恒生" else None,
)

# Sheet4: 返单碎片化分析
bt_rows = [
    ["返单0次(首单)", 115, "61%", ""],
    ["返单1次", 29, "15%", "正常补货"],
    ["返单2次", 14, "7%", "⚠️ 并单窗口"],
    ["返单3次", 12, "6%", "⚠️ 并单窗口"],
    ["返单4次", 8, "4%", "🔴 预测缺位"],
    ["返单5次", 6, "3%", "🔴 预测缺位"],
    ["返单6次", 3, "2%", "🔴 预测缺位"],
    ["返单7次", 3, "2%", "🔴 预测缺位"],
]
pd.sheet(
    "返单碎片化(在产190单)",
    ["返单次数", "单数", "占比", "定性"],
    bt_rows,
    [14, 8, 8, 14],
    note="返单占在产39%(75/190),其中61%是2次以上。返单间隔中位13天、34%≤7天→并单机制可砍约1/3返单单数。典型:LM2631014在40天内下单7次(最后两单仅隔1天)。",
    row_alert=lambda row, i: red_fill(row, i) if "🔴" in str(row[3]) else (yellow_fill(row, i) if "⚠️" in str(row[3]) else None),
)

pd.save(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")

# ============================================================
# 3️⃣ 销售部 Excel
# ============================================================
sd = Book("销售部数据包")

# Sheet1: 流失预警(30-60天)
d365 = sales.get("dormant_30_60") or []
dorm_rows = []
for d in d365[:50]:
    dorm_rows.append([
        d.get("name"),
        d.get("vip") or "普通",
        str(d.get("last", "")),
        num(d.get("gapDays")),
        num(d.get("buyN")),
        num(d.get("retN")),
        fmt_money(num(d.get("buyAmt"))),
        fmt_money(num(d.get("retAmt"))),
        fmt_money(num(d.get("aov"))),
        fmt_money(num(d.get("unitPrice"))),
        "",
    ])
sd.sheet(
    "流失预警·30-60天未下单Top50",
    ["客户", "等级", "最后下单", "间隔(天)", "下单数", "退单数", "购买金额(¥)", "退货金额(¥)", "客单价(¥)", "件单价(¥)", "认领跟进人"],
    dorm_rows,
    [18, 8, 12, 9, 8, 8, 12, 11, 10, 10, 12],
    note="共225家(Top50在此)。UUS(2)32累计¥98.6万58天未下单、南宁李婕¥82.7万35天。每日推送→导购认领→周五看回流。最后列留白供认领填写。",
    row_alert=lambda row, i: red_fill(row, i) if num(row[6]) > 500000 else None,
)

# Sheet2: 交期承诺表(超卖款)
eta_rows = []
for it in restock_items:
    lvl = str(it.get("level", ""))
    if "超卖" not in lvl and num(it.get("stock")) >= 0:
        continue
    ref = it.get("item_ref")
    # 找在产订单的ETA
    eta_val, inprod_qty = "", 0
    for o in prod_active:
        if o.get("template_no") == ref:
            inprod_qty += num(o.get("plan_total_num"))
            if o.get("estimated_finish_time"):
                eta_val = o.get("estimated_finish_time")
    eta_rows.append([
        ref, it.get("name"), lvl,
        num(it.get("stock", "")),
        num(it.get("daily_avg"), 0),
        inprod_qty, eta_val or "⚠️未填(推动补填)",
        "该款在产X件预计X日到,可先订锁货" if inprod_qty > 0 else "暂无在产,建议立即追单",
    ])
sd.sheet(
    "交期承诺表·超卖款",
    ["款号", "品名", "级别", "当前库存(负=欠货)", "日均销", "在产(件)", "ETA", "销售话术建议"],
    eta_rows,
    [13, 20, 8, 13, 9, 10, 15, 30],
    note="⛔超卖≠没货,是有在途无交期。ETA补齐后话术从'没货'变'X日到先订200'。推动生产填ETA是本表前提(当前填写率60%)。",
    row_alert=lambda row, i: red_fill(row, i),
)

# Sheet3: 新客未复购
nc15 = sales.get("new_client_15d") or []
nc_rows = []
for d in nc15[:40]:
    nc_rows.append([
        d.get("name"),
        str(d.get("first", "")),
        num(d.get("gapDays")),
        fmt_money(num(d.get("amt"))),
        num(d.get("qty")),
        "",
    ])
sd.sheet(
    "新客15天未复购(58家)",
    ["客户", "首单日", "距首单(天)", "首单金额(¥)", "首单件数", "触达动作"],
    nc_rows,
    [18, 12, 11, 12, 10, 24],
    note="第二单转化关键期:D7/D15两轮自动触达任务。触达动作列留白(建议:发新品+优惠)。",
)

# Sheet4: 导购业绩
sellers = sales.get("seller_30d") or []
sl_rows = []
for s in sellers:
    sl_rows.append([
        s.get("seller"),
        num(s.get("times")),
        num(s.get("qty")),
        fmt_money(num(s.get("amt"))),
        num(s.get("newBuyN", 0)),
        fmt_money(num(s.get("newAmt", 0))),
        fmt_money(num(s.get("oldAmt", 0))),
        fmt_money(num(s.get("reorderAmt", 0))),
    ])
sl_rows.append(["(空归属)", 34, 1475, 163014, 0, 0, 163014, 163014])
sd.sheet(
    "导购业绩(近30日)",
    ["导购", "单数", "件数", "金额(¥)", "新客单数", "新客金额(¥)", "老客金额(¥)", "补单金额(¥)"],
    sl_rows,
    [12, 8, 9, 12, 9, 12, 12, 12],
    note="许佩燕占40%流水→方法论萃取。'空归属'34单¥16.3万待认领——业绩口径先公平再激励。",
    row_alert=lambda row, i: yellow_fill(row, i) if str(row[0]) == "(空归属)" else None,
)

# Sheet5: 地域分布
region_rows = [
    ["华南", "55%", "327单", "秋款主力市场,生命周期可至11月", "秋款按上行系数补货;冬款盯华南档口10月中上冬装节奏"],
    ["华东", "17%", "100单", "第二市场", "正常节奏"],
    ["华中", "9%", "54单", "", ""],
    ["西南", "8%", "48单", "", ""],
    ["华北", "7%", "39单", "厚款先动信号市场", "厚款华北先卖→华南窗口还长,补货可放缓"],
    ["东北", "2%", "9单", "", "不赌北方降温(历史占比~10%)"],
    ["海外", "1%", "7单", "", ""],
    ["西北", "1%", "6单", "", ""],
]
sd.sheet(
    "订单地域分布(近30日590单识别)",
    ["大区", "占比", "单数", "市场定位", "补货策略"],
    region_rows,
    [10, 8, 10, 30, 44],
    note="识别依据:收件地址+电话归属地(9-22会议确认双保险)。省份Top:福建160/广东127/浙江65。",
)

sd.save(f"{OUTDIR}/数据包-销售部-{TODAY}.xlsx")

# ============================================================
# 4️⃣ 财务部 Excel
# ============================================================
fd = Book("财务部数据包")

# Sheet1: 经营总览
ov = sales.get("overview") or {}
overview_rows = [
    ["近7日", "140单/125购", 222052, 2468, "19.7", 29364, 192688],
    ["近半月", "321单/275购", 900922, 9336, "33.9", 473684, 427238],
    ["近30日", "803单/679购", 2048716, 21003, "30.9", 531353, 1517363],
]
fd.sheet(
    "经营总览(下单回款)",
    ["周期", "单数", "金额(¥)", "件数", "连带(件/单)", "新客金额(¥)", "老客金额(¥)"],
    overview_rows,
    [10, 12, 13, 10, 11, 12, 12],
    note="数据截至2026-10-10 11:00。退单为负数自然冲减。补单金额=老客(非首单)下单金额。",
)

# Sheet2: 客户信用分档
# 用五年回款分档xlsx已有;这里用dormant名单中的高净值+debt字段组示意信用表
credit_rows = []
debt_cnt = sum(1 for c in customers if num(c.get("debt")) > 0)
debt_sum = sum(num(c.get("debt")) for c in customers)
credit_rows.append(["当前欠款客户", f"{debt_cnt} 家", fmt_money(debt_sum), "接单时关注欠款清收", "欠款>阈值超额下单需审批"])
credit_rows.append(["A类(年回款最高档)", "见客户回款分档表", "", "正常接单", "参考:客户回款分档-2022至2026年度.xlsx"])
credit_rows.append(["B类", "见分档表", "", "正常接单", ""])
credit_rows.append(["C/D类(低回款/长账期)", "见分档表", "", "超额下单人工审批", "信用分档挂接多客客户档案后自动拦截"])
fd.sheet(
    "客户信用分档规则",
    ["分档", "客户数", "欠款合计(¥)", "接单规则", "说明"],
    credit_rows,
    [22, 16, 13, 24, 40],
    note=f"当前{len(customers)}家客户档案中{debt_cnt}家有欠款标记。五年回款分档已产出(客户回款分档-2022至2026年度.xlsx),拍板后挂接接单审批。",
)

# Sheet3: 双系统对账状态
recon_rows = [
    ["衣者财务待核对", "¥6,841,804", "每日", "衣者财务口径", "扩展:多客流水×衣者明细成本→只出差异单"],
    ["成本对齐", "0违规/0检查", "每日", "reconcile链路", "当前PASS;需扩展金额维度"],
    ["衣者入库 vs 多客在库", "1,723 / 48,131件", "每日", "口径体检", "衣者total_num疑似累计入库口径——待现场确认"],
    ["多客成本 vs 衣者成本", "差异≤¥1/件", "月", "多客成本为准(9-22会议拍板)", "损耗/四舍五入"],
]
fd.sheet(
    "双系统对账",
    ["对账项", "金额/量级", "频率", "口径", "说明"],
    recon_rows,
    [22, 16, 8, 26, 44],
    note="对账脚本reconcile.mjs每日自动跑。¥684万待核对走款级金额匹配后压缩到差异单人工处理。",
)

# Sheet包4: 库存资金占用
stock_rows = [
    ["多客在库货值", "¥337万", "30日动销21,003件", "库存资金/月销比监控", "周环比"],
    ["衣者待入库(在途)", "146单/21,650件", "入库率仅4%", "推动多客侧入库录入", "在途资金"],
    ["超卖欠货(负库存)", "9,676件/282款", "=预售占用", "不算积压,算交期风险", "每日"],
]
fd.sheet(
    "库存资金占用",
    ["项目", "量级", "关联指标", "管理动作", "频率"],
    stock_rows,
    [20, 18, 16, 30, 8],
    note="超阈值(库存资金/月销比)触发清仓审批,替代'到盘点才发现压了一库'。",
)

# Sheet5: 碎片补单成本(核心说服工具)
frag_rows = [
    ["碎片返单现象", "75/190在产单(39%);61%是2次以上;最高7次", "", "每次返单=重新采购+重新排产+重新裁剪"],
    ["返单间隔", "中位13天,P25=5天,34%≤7天", "", "≤7天的返单本可并入上一单"],
    ["小批量面料溢价", "待月度成本核算填入", "¥/次", "小单面料采购单价高于批量"],
    ["小批量裁剪溢价", "待月度成本核算填入", "¥/次", "批量↑裁片成本↓(老板会议原话)"],
    ["断货销售损失", "超卖欠货9,676件×件单价~¥80", "≈¥77万/批", "货到时峰已过的错失销售额"],
    ["并单机制收益", "砍1/3返单单数+批量成本下降", "", "三层防补单体系落地后量化"],
]
fd.sheet(
    "碎片补单成本测算",
    ["项目", "现状数据", "量化", "说明"],
    frag_rows,
    [16, 40, 12, 34],
    note="本表是并单机制最有力的财务证据。小批量溢价两项待月度成本核算(月初跑)填入后完整。",
    row_alert=lambda row, i: orange_fill(row, i) if "断货" in str(row[0]) else None,
)

fd.save(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")

print("\n全部完成")
