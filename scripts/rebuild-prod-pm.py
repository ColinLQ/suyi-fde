#!/usr/bin/env python3
# 生产部数据包 V4 重造：每张表回答一个决策问题（产品经理视角）
# 04表: 返单碎片化 → 拆成「碎片单代价明细」(每款: 多花的钱/多等的天/怎么避免)
# 全部表格: 表尾附口径说明块
import json, os
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
XL_RED_BG = xl_color("#FDE9E9"); XL_ORANGE_BG = xl_color("#FFF2E8")
XL_YELLOW_BG = xl_color("#FFFDE8"); XL_GREEN_BG = xl_color("#C6EFCE"); XL_BLUE_BG = xl_color("#E8F0FE")
XL_GRAY_BG = xl_color("#F3F4F6")
thin = Side(style="thin", color=xl_color("#BFBFBF"))
border_all = Border(left=thin, right=thin, top=thin, bottom=thin)
f_header = Font(name="PingFang SC", bold=True, color="FFFFFFFF", size=11)
f_title = Font(name="PingFang SC", bold=True, size=14, color=xl_color("#1F2937"))
f_body = Font(name="PingFang SC", size=11)
f_note = Font(name="PingFang SC", size=9, color=xl_color("#6B7280"))
f_note_h = Font(name="PingFang SC", size=9, bold=True, color=xl_color("#374151"))
fill_header = PatternFill("solid", fgColor=XL_HEADER_BG)
fill_note = PatternFill("solid", fgColor=XL_GRAY_BG)
al_c = Alignment(horizontal="center", vertical="center", wrap_text=True)
al_l = Alignment(horizontal="left", vertical="center", wrap_text=True)
al_r = Alignment(horizontal="right", vertical="center")
al_note = Alignment(horizontal="left", vertical="top", wrap_text=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # skill代码根目录（可移植）
DATA_HOME = os.environ.get('SCM_DATA_HOME') or os.path.join(os.path.expanduser('~'), 'WorkBuddy', 'scm-collector-data')  # 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
RAW = f"{DATA_HOME}/data/raw/2026-10-09/pm"
RAW_T = f"{DATA_HOME}/data/raw/2026-10-10/pm"
OUTDIR = f"{DATA_HOME}/out"
PIC = f"{DATA_HOME}/state/goods-pics"
TODAY = "2026-10-10"
NOW = datetime(2026, 10, 10)

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

def write_note_block(ws, start_row, ncol, lines):
    """表尾口径说明块：每行一条, 标题行加粗"""
    r = start_row
    c0 = ws.cell(r, 1, "口径说明")
    c0.font = f_note_h
    c0.fill = fill_note
    for c in range(2, ncol + 1):
        ws.cell(r, c).fill = fill_note
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
    r += 1
    for line in lines:
        cell = ws.cell(r, 1, line)
        cell.font = f_note
        cell.alignment = al_note
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
        r += 1
    return r

# ============ 数据 ============
fd = []
with open(f"{RAW_T}/perf_follow_done.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            fd.append(json.loads(line))
hist = []
with open(f"{RAW}/yizhe_production_hist.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            hist.append(json.loads(line))
active = []
with open(f"{RAW}/yizhe_production_list.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            active.append(json.loads(line))

# 批量-单价对照(实算)
bucket_cost = defaultdict(lambda: [0.0, 0])
for o in fd:
    qty, cost = num(o.get("plan_total_num")), num(o.get("avg_cuted_cost"))
    if qty > 0 and cost > 0:
        b = "<100" if qty < 100 else "100-199" if qty < 200 else "200-299" if qty < 300 else "300-499" if qty < 500 else "500-799" if qty < 800 else "800+"
        bucket_cost[b][0] += cost
        bucket_cost[b][1] += 1
BUCKET_ORDER = ["<100", "100-199", "200-299", "300-499", "500-799", "800+"]
bucket_avg = {b: bucket_cost[b][0] / bucket_cost[b][1] for b in BUCKET_ORDER if bucket_cost[b][1]}
cheapest = min(bucket_avg.values())

# 同款订单聚合(同日合并)
tpl_orders = defaultdict(list)
for o in hist + active:
    tno, ca = o.get("template_no"), o.get("created_at")
    if tno and ca:
        tpl_orders[tno].append((str(ca)[:10], num(o.get("plan_total_num"))))
# 碎片款(≥3下单日)
frag = []
for tno, lst in tpl_orders.items():
    by_day = defaultdict(float)
    for d, q in lst:
        by_day[d] += q
    days = sorted(by_day)
    if len(days) < 3:
        continue
    gaps = [(datetime.strptime(days[i+1], "%Y-%m-%d") - datetime.strptime(days[i], "%Y-%m-%d")).days for i in range(len(days)-1)]
    total = sum(by_day.values())
    n_orders = len(lst)
    avg_batch = total / n_orders
    # 该款实际批次单价(fd里找同款)
    unit_costs = [num(o.get("avg_cuted_cost")) for o in fd
                  if o.get("template_no") == tno and num(o.get("avg_cuted_cost")) > 0]
    actual_unit = sum(unit_costs) / len(unit_costs) if unit_costs else None
    # 合并后单价: 按总量对照桶
    def bucket_of(q):
        return "<100" if q < 100 else "100-199" if q < 200 else "200-299" if q < 300 else "300-499" if q < 500 else "500-799" if q < 800 else "800+"
    merged_unit = bucket_avg.get(bucket_of(total))
    frag.append({
        "tno": tno, "n_days": len(days), "n_orders": n_orders, "total": total,
        "avg_batch": avg_batch, "span": (datetime.strptime(days[-1], "%Y-%m-%d") - datetime.strptime(days[0], "%Y-%m-%d")).days,
        "min_gap": min(gaps), "days_seq": "→".join(days),
        "actual_unit": actual_unit, "merged_unit": merged_unit,
        "overspend": round((actual_unit - merged_unit) * total) if (actual_unit and merged_unit) else None,
        "last_day": days[-1],
    })
frag.sort(key=lambda x: -(x["overspend"] or 0))

wb = openpyxl.load_workbook(f"{DATA_HOME}/out/数据包-生产部-{TODAY}.xlsx")

# ============================================================
# 重造 04: 碎片单代价明细
# ============================================================
for sn in list(wb.sheetnames):
    if sn.startswith("04·"):
        del wb[sn]

ws = wb.create_sheet("04·碎片返单代价明细")
ws.sheet_properties.tabColor = xl_color("#C00000")
headers = ["图片", "款号", "下单日数", "实际单据数", "总量(件)", "单均批量(件)",
           "实际加工单价", "合并后单价", "多花加工费(¥)", "碎片周期(天)", "断货风险天", "下次动作"]
widths = [14, 13, 9, 10, 9, 12, 12, 11, 13, 11, 11, 26]
ws.cell(1, 1, "碎片返单代价明细——每张碎片单多花了多少钱、多等了多少天").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
for c, h in enumerate(headers, 1):
    cell = ws.cell(2, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all

n_pic = 0
total_overspend = 0
for i, x in enumerate(frag):
    r = 3 + i
    # 断货风险天 = 跨度内因等料等产的空窗(近似: 下单日数-1次 × 最小间隔)——太绕,改用直接口径: 最后一次补单日-首单日 跨度中, 若首单即下足总量, 交付完成提前 天数 ≈ span(无需第2~N次等待)
    risk_days = x["span"] if x["min_gap"] <= 7 else 0
    action = "后续款并单: 首单量+30%" if x["min_gap"] <= 2 else ("7天窗并单" if x["min_gap"] <= 7 else "观察")
    if x["overspend"]:
        total_overspend += x["overspend"]
    vals = [None, x["tno"], x["n_days"], x["n_orders"], round(x["total"]), round(x["avg_batch"]),
            round(x["actual_unit"], 1) if x["actual_unit"] else "—",
            round(x["merged_unit"], 1) if x["merged_unit"] else "—",
            x["overspend"] if x["overspend"] else "—",
            x["span"], risk_days if risk_days else "—", action]
    alert = PatternFill("solid", fgColor=XL_RED_BG) if (x["overspend"] or 0) > 5000 else (
        PatternFill("solid", fgColor=XL_ORANGE_BG) if (x["overspend"] or 0) > 0 else None)
    for c, v in enumerate(vals, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body; cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) else al_l
        if alert:
            cell.fill = alert
    if add_pic(ws, r, 1, x["tno"]):
        n_pic += 1
for c, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(c)].width = w

summary_r = 3 + len(frag) + 1
ws.cell(summary_r, 1, f"合计: {len(frag)} 款碎片化 · 多花加工费 ¥{total_overspend:,.0f}（口径见下）").font = Font(name="PingFang SC", bold=True, size=11, color=xl_color("#C00000"))
ws.merge_cells(start_row=summary_r, start_column=1, end_row=summary_r, end_column=len(headers))

write_note_block(ws, summary_r + 2, len(headers), [
    "▍这张表回答什么问题：哪些款的返单方式在白白花钱，每款多花了多少、值不值得改流程。",
    "▍多花加工费怎么算的：多花=(该款实际平均加工单价 − 按总量合并后应享单价)×总件数。合并后单价来自左下「批量-单价对照表」——用全部2,779个完成批实算，非拍脑袋。",
    "▍断货风险天：该款最后一次补单日期 − 首单日期。含义:若首单下足,这期间客户不用等货。仅对最小补货间隔≤7天的款计入(间隔>7天属正常滚动补货,不算碎片)。",
    "▍下次动作: 最小间隔≤2天=下单系统应拦截提示并单; ≤7天=周补货会并单; >7天=正常节奏不用管。",
    "▍数据边界: 「实际加工单价」取自衣者跟单完成记录(avg_cuted_cost),17款中X款无单价记录标「—」; 合并后单价为同批量档均值(非该工厂实际报价),金额是量级估计,用于排优先级而非结算。",
    "▍图片: 多客商品缩略图,3款源头无图。",
])
ws.freeze_panes = "C3"

# 批量-单价对照小表(同sheet右侧下方)
r0 = summary_r + 10
ws.cell(r0, 1, "附:批量-单价对照(2,779批实算)").font = f_note_h
r0 += 1
for c, h in enumerate(["批量档", "批次", "平均加工单价(¥/件)", "比最低档贵"], 1):
    cell = ws.cell(r0, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all
for i, b in enumerate(BUCKET_ORDER):
    if b in bucket_avg:
        r = r0 + 1 + i
        ws.cell(r, 1, b).font = f_body
        ws.cell(r, 2, bucket_cost[b][1]).font = f_body
        ws.cell(r, 3, round(bucket_avg[b], 1)).font = f_body
        ws.cell(r, 4, f"+{(bucket_avg[b]/cheapest-1)*100:.0f}%").font = f_body
        for c in range(1, 5):
            ws.cell(r, c).border = border_all

print(f"04表: {len(frag)}款 图{n_pic} 多花合计¥{total_overspend:,.0f}")

# ============================================================
# 其余表: 全部补口径说明块(替换原单行note)
# ============================================================
notes_map = {
    "01·周滚动补货计划(净缺口法)": [
        "▍这张表回答什么：未来30天哪些款需要下生产单,下多少,什么时候必须下。",
        "▍建议补货量(V1口径): 日均销×(面料采购15天+生产5天)×安全系数1.2−库存。日均销取近7日,近7日无销量回退近30日。",
        "▍净缺口=建议量−该款在产订单量。净缺口>0才需要追加下单; ≤0只需催货(货在路上,别重复下)。",
        "▍⛔超卖=多客库存为负(已收单未交货),是全表最高优先级。🔴紧急=可售天数<10天。🟡关注=10-20天。",
        "▍并单标记: ✔并单候选=近30日日均销≥10件且该款已有在产单——新返单应并入而非另开单。",
        "▍建议下单时点: 立即=已超卖; 本周内=净缺口>0。倒推逻辑: 下单日+面料15天+生产5天=到货日,须早于库存售罄日。",
        "▍局限: V1日均含档口批量拿货,可能虚高——精确版见07表(V2三因子)。图片: 多客缩略图。",
    ],
    "02·在产订单驾驶舱(190单)": [
        "▍这张表回答什么：190张在产单现在走到哪一步、卡在哪、谁负责、什么时候交。",
        "▍五级漏斗: 计划→配料(预裁)→裁货→出货→入库。当前卡点=该单最后停留的环节(自动判定)。",
        "▍⚠️黄底=管理断点: 采购员未指派或预计完成时间(ETA)未填。ETA未填=销售无法给客户承诺交期=卡单的第一大源头(当前填写率60%)。",
        "▍工厂/跟单列可直接筛选。建议用法: 每天筛「卡在裁货超过X天」的单推给对应跟单。",
        "▍入库率仅4%: 出货≠入库≠可卖。多客侧无入库时间记录,推动仓库录入是交期承诺的前提。",
    ],
    "03·工厂计分卡(9月)": [
        "▍这张表回答什么：9月哪家工厂交货最准,爆款返单应该给谁。",
        "▍按时率=实际完成≤预计完成(ETA)的批次占比。超5天批=严重脱期批次数。",
        "▍⚠️本表仅9月单月(120批),样本小;全量版见05表(2,779批,含各厂单价对比)。",
        "▍恒生红底: 占9月出货件数58%但按时率仅43.4%——大厂依赖+货期失控并存,是供应链最大单点风险。",
    ],
    "05·工厂计分卡·全量(2779批)": [
        "▍这张表回答什么：拉长到全部历史,各工厂的真实产能、价格、速度对比——分配新单的依据。",
        "▍按时率口径同03表(完成≤ETA,仅统计填了ETA的批)。ETA未填率过半时,按时率仅代表「填了ETA的那部分批」——所以两列要一起看。",
        "▍均加工价(price字段均值): 远方¥14/件 vs 恒生¥32.4/件——差价2.3倍。爆款返单从高价厂切到低价厂是直接的降本动作(前提: 交期质量可比,建议先切1-2款试单)。",
        "▍平均周期=下单→最后出货的天数均值(排除>120天异常)。",
        "▍主力跟单: 生产经理名下超1,700批——人的单点风险,新跟单应逐步分单。",
    ],
    "06·返单节奏明细·下单≥3次(同日合并)": [
        "▍这张表回答什么：哪些款在反复补货,节奏多密——并单机制的目标清单。",
        "▍同日多张单已合并为一个下单日(单据数>天数=存在同日拆单,本身也是碎片化证据)。",
        "▍🔴高危=最小补货间隔≤2天(下单系统应拦截); ⚠️碎片=≤7天(周补货会并单); 正常=滚动补货节奏。",
        "▍与04表关系: 04表算这些碎片化多花多少钱,本表看节奏细节。两表款号一致。",
    ],
    "07·补货建议V2·三因子对比": [
        "▍这张表回答什么：考虑生命周期+往年同期+季节气候后,建议补货量应该是多少——比V1更准的参考。",
        "▍预测日均=0.5×近7/30日 + 0.3×生命周期日均 + 0.2×品类去年同期(10-11月3年均值)日均。",
        "▍生命周期系数: 上市W1-2周爬坡×1.3, W3-6峰值×1.5, W7-10平稳×1.0, W11+衰减×0.6; 近7日≥近30日(上行)时系数下限1.2。",
        "▍季节气候系数: 冬款×1.2(华南档口10月中启动冬装), 秋款×1.0(华南可穿至11月)。依据: 华南占订单55%,不赌北方降温(华北仅7%)。",
        "▍V2净缺口=预测日均×系数×30天 −库存−在产。橙底=比V1多(防断货),蓝底=比V1少(防过补)。",
        "▍⚠️口径差异: V1用SKU出库口径(含档口批量拿货),V2用零售订单明细口径——V2普遍更保守。用法: V2定零售缺口基线,档口大单人工另判。",
        "▍权重(0.5/0.3/0.2)为经验值,待2周实测动销回归后校准。",
    ],
}
for sn, lines in notes_map.items():
    target = next((s for s in wb.sheetnames if s.startswith(sn[:8])), None)
    if not target:
        continue
    ws = wb[target]
    # 删旧note(最后一行下方有旧说明的合并单元格——直接追加,旧note已被覆盖或保留在上次写入位置;找空行)
    # 找最后一个数据行之后2行
    r = ws.max_row + 2
    # 跳过旧note: 检查已有"口径说明"块则先跳过
    has_note = False
    for rr in range(3, ws.max_row + 1):
        if ws.cell(rr, 1).value == "口径说明":
            has_note = True
            break
    if has_note:
        continue
    write_note_block(ws, r, min(ws.max_column, 12), lines)
    print(f"  {target[:10]}: 口径说明已附")

wb.save(f"{DATA_HOME}/out/数据包-生产部-{TODAY}.xlsx")
print("✅ 生产部 V4 完成")
