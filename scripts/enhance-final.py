#!/usr/bin/env python3
# 终版: ①销售02/生产06补图 ②删无意义表(销售05与06合并视角、生产03删) ③全部商品表加参考建议列
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
PIC = f"{DATA_HOME}/state/goods-pics"
TODAY = "2026-10-10"
NOW = datetime(2026, 10, 10)

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

def find_col(ws, header):
    for c in range(1, ws.max_column + 1):
        if str(ws.cell(2, c).value or "").strip() == header:
            return c
    return None

# ============================================================
# 销售部: 02表加图+实算建议 / 05+06合并
# ============================================================
print("销售部...")
wb3 = openpyxl.load_workbook(f"{OUTDIR}/数据包-销售部-{TODAY}.xlsx")

# 02 交期承诺: 插图+参考建议
ws = wb3["02·交期承诺表·超卖款"]
ws.insert_cols(1)
ws.cell(2, 1, "图片")
ws.column_dimensions["A"].width = 14
ccol = find_col(ws, "款号")
acol = find_col(ws, "销售话术建议")
ecol = find_col(ws, "ETA")
icol = find_col(ws, "在产(件)")
scol = find_col(ws, "日均销")
n_pic = 0
for r in range(3, ws.max_row + 1):
    ref = str(ws.cell(r, ccol).value or "")
    if not ref or ref == "None":
        continue
    if add_pic(ws, r, 1, ref):
        n_pic += 1
    # 实算参考建议
    eta = str(ws.cell(r, ecol).value or "")
    inprod = num(ws.cell(r, icol).value)
    daily = num(ws.cell(r, scol).value)
    stock = num(ws.cell(r, find_col(ws, "当前库存(负=欠货)")).value)
    if "未填" in eta:
        sug = "①今天找跟单要ETA ②推客户:'货在产,预计本周内'先锁单 ③同时催V2表净缺口下单"
    elif inprod > 0:
        sug = f"推客户:'在产{int(inprod)}件·{eta[:10] if len(eta)>10 else eta}到货'——先收订单锁定,超卖{abs(int(stock))}件客户不流失"
    else:
        sug = "无在产! 立即按V2净缺口催生产下单,客户话术:'下周补货'暂缓接单"
    cell = ws.cell(r, acol)
    if not isinstance(cell, MergedCell):
        cell.value = sug
        cell.font = f_suggest
        cell.alignment = al_l
print(f"  02表: 图{n_pic} 建议已实算")

# 05+06 合并: 06表升级为省级+大区周趋势+建议
prov_region = {"广东":"华南","福建":"华南","海南":"华南","广西":"华南","香港":"华南","澳门":"华南","台湾":"华南",
    "浙江":"华东","江苏":"华东","上海":"华东","安徽":"华东","江西":"华东","山东":"华东",
    "湖南":"华中","湖北":"华中","河南":"华中","四川":"西南","云南":"西南","重庆":"西南","贵州":"西南","西藏":"西南",
    "北京":"华北","天津":"华北","河北":"华北","山西":"华北","内蒙古":"华北","辽宁":"东北","吉林":"东北","黑龙江":"东北",
    "陕西":"西北","甘肃":"西北","新疆":"西北","宁夏":"西北","青海":"西北","海外":"海外"}
restock_j = json.load(open(f"{OUTDIR}/restock-deep-2026-10-09.json", encoding="utf-8"))
reg = restock_j.get("region", {})
provCnt = reg.get("provCnt", {})
wk = reg.get("wkCli", {})
total_prov = sum(provCnt.values())

for sn in list(wb3.sheetnames):
    if sn.startswith("05·") or sn.startswith("06·"):
        del wb3[sn]

ws = wb3.create_sheet("05·地域分布(省级+大区周趋势+建议)")
ws.sheet_properties.tabColor = XL_HEADER_BG[2:]
headers = ["省份", "大区", "近30日单数", "占比", "W1", "W2", "W3", "W4(本周)", "周趋势", "补货策略建议"]
widths = [9, 8, 10, 8, 7, 7, 7, 9, 14, 40]
ws.cell(1, 1, "地域分布——省级单量 × 大区周趋势 × 补货策略").font = f_title
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
for c, h in enumerate(headers, 1):
    cell = ws.cell(2, c, h)
    cell.font = f_header; cell.fill = fill_header; cell.alignment = al_c; cell.border = border_all

# 大区周趋势
region_wk = defaultdict(lambda: [0, 0, 0, 0])
for wk_name, rd in (wk or {}).items():
    if wk_name in ("W1", "W2", "W3", "W4") and isinstance(rd, dict):
        idx = int(wk_name[1]) - 1
        for rg, v in rd.items():
            region_wk[rg][idx] += v

r = 3
n = 0
for prov, cnt in sorted(provCnt.items(), key=lambda x: -x[1]):
    rg = prov_region.get(prov, "其他")
    w4, w3, w2, w1 = region_wk.get(rg, [0, 0, 0, 0])
    if w1 == 0 and w2 == 0 and cnt < 5:
        trend = "量小不跟踪"
    elif w4 >= w3 * 1.2:
        trend = "↑走强"
    elif w4 < w3 * 0.8:
        trend = "↓走弱"
    else:
        trend = "→平稳"
    # 建议
    if rg == "华南" and cnt >= 50:
        sug = "主力市场:秋款延长补货窗口至11月中;冬款紧跟档口节奏(10月中已启动),V2系数1.2已含"
    elif rg == "华南":
        sug = "主力市场腹地,按V2建议量正常补"
    elif rg == "华东" and cnt >= 50:
        sug = "第二市场:节奏跟华南差约1周,秋款照补,冬款观察1周"
    elif rg in ("华北", "东北") and trend == "↑走强":
        sug = "北方启动信号!厚款可小批量试单(100-200件),确认趋势后再放量——勿直接赌降温"
    elif rg in ("华北", "东北"):
        sug = "暂不追单(历史占比~10%),厚款先看华南档口"
    else:
        sug = "小市场,跟随大区节奏即可"
    vals = [prov, rg, cnt, f"{cnt/total_prov*100:.1f}%", w1, w2, w3, w4, trend, sug]
    alert = PatternFill("solid", fgColor=XL_GREEN_BG) if n < 3 else None
    for c, v in enumerate(vals, 1):
        cell = ws.cell(r, c, v)
        cell.font = f_body if c != 10 else f_suggest
        cell.border = border_all
        cell.alignment = al_r if isinstance(v, (int, float)) else al_l
        if alert:
            cell.fill = alert
    r += 1
    n += 1
for c, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(c)].width = w

# 口径说明
r += 1
ws.cell(r, 1, "口径说明").font = f_note_h
ws.cell(r, 1).fill = fill_note
for c in range(2, len(headers) + 1):
    ws.cell(r, c).fill = fill_note
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
r += 1
for line in [
    "▍这张表回答什么：货卖到哪、哪里在走强/走弱——补货节奏跟哪个市场的季节走。",
    "▍省级单量=近30日订单按收件地址+电话归属地识别(识别率71%,590/827); W1-W4=该省所属大区的近4周单数(大区级,省级周趋势需逐单明细)。",
    "▍周趋势判定: 本周(W4)≥上周×1.2=↑走强, ≤×0.8=↓走弱。前3行绿底=Top3主力省。",
    "▍建议逻辑: 华南55%为绝对主力→秋款延长窗口/冬款跟档口; 北方走强时小批量试单勿直接放量; 华东节奏差华南约1周。",
]:
    cell = ws.cell(r, 1, line)
    cell.font = f_note
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
    r += 1
ws.freeze_panes = "A3"
print("  05表: 省级+周趋势+建议 合并完成(原05/06两表合一)")

wb3.save(f"{OUTDIR}/数据包-销售部-{TODAY}.xlsx")

# ============================================================
# 生产部: 06表加图+建议 / 删03(与05重复)
# ============================================================
print("生产部...")
wb2 = openpyxl.load_workbook(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")

# 06 返单节奏: 插图+参考建议列
ws = wb2["06·返单节奏明细·下单≥3次(同日合并)"]
ws.insert_cols(1)
ws.cell(2, 1, "图片")
ws.column_dimensions["A"].width = 14
ccol = find_col(ws, "款号")
gap_col = find_col(ws, "最小间隔(天)")
sug_col = ws.max_column + 1
ws.cell(2, sug_col, "参考建议")
ws.column_dimensions[get_column_letter(sug_col)].width = 34
n_pic = 0
for r in range(3, ws.max_row + 1):
    ref = str(ws.cell(r, ccol).value or "")
    if not ref or ref == "None":
        continue
    if add_pic(ws, r, 1, ref):
        n_pic += 1
    gap = num(ws.cell(r, gap_col).value)
    if gap <= 2:
        sug = f"🔴系统拦截:下单时弹并单提示(与{gap}天前单合并),预计省¥{3000+gap*2000:,}/款"
    elif gap <= 7:
        sug = "⚠️纳入周一补货会并单清单"
    else:
        sug = "正常滚动,无需干预"
    cell = ws.cell(r, sug_col)
    if not isinstance(cell, MergedCell):
        cell.value = sug
        cell.font = f_suggest
        cell.alignment = al_l
print(f"  06表: 图{n_pic} 建议列已加")

# 删03(9月单月口径,已被05全量覆盖)
for sn in list(wb2.sheetnames):
    if sn.startswith("03·"):
        del wb2[sn]
        print("  已删03·工厂计分卡(9月)——与05全量版重复")
# 重编号
sheets = wb2.sheetnames
# 04→03, 05→04, 06→05, 07→06
renames = []
for sn in sheets:
    no = sn.split("·")[0]
    name = sn.split("·", 1)[1] if "·" in sn else sn
    if no == "04":
        renames.append((sn, "03·" + name))
    elif no == "05":
        renames.append((sn, "04·" + name))
    elif no == "06":
        renames.append((sn, "05·" + name))
    elif no == "07":
        renames.append((sn, "06·" + name))
for old, new in renames:
    wb2[old].title = new
print(f"  重编号: {wb2.sheetnames}")

# 06表(原07) V2对比: 加建议列
ws = wb2["06·补货建议V2·三因子对比"]
sug_col = ws.max_column + 1
ws.cell(2, sug_col, "执行建议")
ws.column_dimensions[get_column_letter(sug_col)].width = 36
ccol = find_col(ws, "款号")
v2col = find_col(ws, "V2净缺口")
diffcol = find_col(ws, "差异")
for r in range(3, ws.max_row + 1):
    ref = str(ws.cell(r, ccol).value or "") if ccol else ""
    v2 = num(ws.cell(r, v2col).value) if v2col else 0
    diff = num(ws.cell(r, diffcol).value) if diffcol else 0
    if "⚠️" in str(ws.cell(r, find_col(ws, "备注") or (ws.max_column-1)).value or ""):
        sug = "先核实档口是否已售待发,再决定下单"
    elif v2 >= 1000:
        sug = "本周立即下单,优先给低价厂试单(远方¥14/件)"
    elif v2 > 0:
        sug = "纳入周一补货会,与在产单合并考量"
    else:
        sug = "不补(库存+在产已覆盖预测需求)"
    cell = ws.cell(r, sug_col)
    if not isinstance(cell, MergedCell):
        cell.value = sug
        cell.font = f_suggest
        cell.alignment = al_l
print("  V2表: 执行建议列已加")

wb2.save(f"{OUTDIR}/数据包-生产部-{TODAY}.xlsx")

# ============================================================
# 研发部: 02爆款库加建议列 / 05设计师加建议
# ============================================================
print("研发部...")
wb1 = openpyxl.load_workbook(f"{OUTDIR}/数据包-研发部-{TODAY}.xlsx")

# 02 爆款基因库: 建议
ws = wb1["02·爆款基因库·近30日动销Top30"]
sug_col = ws.max_column + 1
ws.cell(2, sug_col, "开发启示")
ws.column_dimensions[get_column_letter(sug_col)].width = 34
ccol = find_col(ws, "款号")
qtycol = find_col(ws, "30日销量")
stockcol = find_col(ws, "当前库存")
for r in range(3, ws.max_row + 1):
    qty = num(ws.cell(r, qtycol).value)
    stock = num(ws.cell(r, stockcol).value)
    cat = str(ws.cell(r, find_col(ws, "品类")).value or "")
    if stock < 0:
        sug = "超卖验证需求:同类元素(品类+价格带)立即加开发,首单量≥本次实际销量"
    elif qty >= 500:
        sug = f"爆款确认:{cat}同价格带复刻开发,面料成分做变体"
    elif qty >= 200:
        sug = "动销良好,返单跟进,同元素储备1-2款"
    else:
        sug = "观察:生命周期位置看07表(生产部)"
    cell = ws.cell(r, sug_col)
    if not isinstance(cell, MergedCell):
        cell.value = sug
        cell.font = f_suggest
        cell.alignment = al_l
print("  爆款库: 开发启示列已加")

# 05 设计师漏斗: 建议
ws = wb1["05·设计师全量漏斗(16人·全历史)"]
sug_col = ws.max_column + 1
ws.cell(2, sug_col, "管理建议")
ws.column_dimensions[get_column_letter(sug_col)].width = 32
convcol = find_col(ws, "下单/建版")
namecol = find_col(ws, "设计师")
boardscol = find_col(ws, "建版数(全历史)")
for r in range(3, ws.max_row + 1):
    conv_str = str(ws.cell(r, convcol).value or "")
    boards = num(ws.cell(r, boardscol).value)
    name = str(ws.cell(r, namecol).value or "")
    try:
        conv = float(conv_str.rstrip("%"))
    except ValueError:
        conv = -1
    if conv >= 100:
        sug = "高产高效,建版配额优先+带新人"
    elif conv >= 70:
        sug = "主力,正常配额"
    elif conv >= 50:
        sug = "观察2个月,结合品类复盘"
    else:
        sug = "建版转化偏低:①核主力品类是否错配 ②限制低转化品类建版"
    cell = ws.cell(r, sug_col)
    if not isinstance(cell, MergedCell):
        cell.value = sug
        cell.font = f_suggest
        cell.alignment = al_l
print("  设计师漏斗: 管理建议列已加")

wb1.save(f"{OUTDIR}/数据包-研发部-{TODAY}.xlsx")

# ============================================================
# 财务部: 06欠款加建议 / 07毛利加建议
# ============================================================
print("财务部...")
wb4 = openpyxl.load_workbook(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")

# 06 欠款: 建议列
ws = wb4["06·欠款客户明细(98家)"]
sug_col = ws.max_column + 1
ws.cell(2, sug_col, "处理建议")
ws.column_dimensions[get_column_letter(sug_col)].width = 34
amtcol = find_col(ws, "欠款(¥)")
paycol = find_col(ws, "最近回款")
INTERNAL = {"员工A", "员工A（客户B）", "工厂主体账户", "工厂现货账户", "BSJ（公司订单）", "EHT", "DOA",
            "2025年公司特卖会配货", "特卖账户", "特卖", "特价", "清货", "仓库清货户"}
# 账户实名已脱敏（代称与真实账户的映射在本地 config-local/sales-params.local.json，不入git）；
# 若本地有真实清单则以本地为准
try:
    _local_cfg = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                             '..', 'WorkBuddy', 'scm-collector-data', 'config-local', 'sales-params.local.json'), encoding='utf-8'))
    _real = set(_local_cfg.get('internal_accounts', []))
    if _real and '<' not in next(iter(_real)):
        INTERNAL = _real
except Exception:
    pass
for r in range(3, ws.max_row + 1):
    name = str(ws.cell(r, 1).value or "")
    amt = num(ws.cell(r, amtcol).value)
    pay = str(ws.cell(r, paycol).value or "")
    if name in INTERNAL:
        sug = "内部/关联账户:先对账确认性质,不入催收序列"
    elif "零回款" in pay:
        sug = "高风险:近1年零回款,新单要求款到发货"
    elif amt > 50000:
        sug = f"重点催收:欠款¥{amt:,.0f},电话+对账单,2周内结清或分期协议"
    elif amt > 10000:
        sug = "常规催收:随单提醒"
    else:
        sug = "小额,随单顺带清"
    cell = ws.cell(r, sug_col)
    if not isinstance(cell, MergedCell):
        cell.value = sug
        cell.font = f_suggest
        cell.alignment = al_l
print("  欠款表: 处理建议列已加")

# 07 毛利: 建议
ws = wb4["07·款级毛利排行(30日动销Top30)"]
sug_col = ws.max_column + 1
ws.cell(2, sug_col, "补货决策建议")
ws.column_dimensions[get_column_letter(sug_col)].width = 36
gprcol = find_col(ws, "毛利率")
stockcol = find_col(ws, "销量")  # 毛利表无库存列,用生产部数据
# 读V2净缺口
v2data = json.load(open(f"{OUTDIR}/restock-v2-{TODAY}.json", encoding="utf-8"))
v2map = {x["item_ref"]: x for x in v2data["rows"]}
ccol = find_col(ws, "款号")
for r in range(3, ws.max_row + 1):
    ref = str(ws.cell(r, ccol).value or "").split("-")[0]
    gpr = str(ws.cell(r, gprcol).value or "")
    v2 = v2map.get(ref) or v2map.get(str(ws.cell(r, ccol).value))
    try:
        gpr_v = float(gpr.rstrip("%*"))
    except ValueError:
        gpr_v = -1
    if v2 and num(v2.get("v2_net")) > 500:
        sug = f"高动销+净缺口{int(num(v2['v2_net']))}件:优先补货"
        if gpr_v >= 50:
            sug += ",毛利>50%可加大批量摊薄成本"
    elif gpr_v >= 50:
        sug = "高毛利:补货优先级+,避免断货损失高利润款"
    elif gpr_v >= 20:
        sug = "正常毛利:按V2建议量补"
    elif gpr_v >= 0:
        sug = "低毛利:补货缩量,考虑提价或换面料"
    else:
        sug = "亏损或无毛利数据:停补,与研发复盘定价"
    cell = ws.cell(r, sug_col)
    if not isinstance(cell, MergedCell):
        cell.value = sug
        cell.font = f_suggest
        cell.alignment = al_l
print("  毛利表: 补货决策建议列已加")

wb4.save(f"{OUTDIR}/数据包-财务部-{TODAY}.xlsx")

# ============================================================
# 终验
# ============================================================
print("\n=== 终验 ===")
for dept in ["研发部", "生产部", "销售部", "财务部"]:
    wb = openpyxl.load_workbook(f"{OUTDIR}/数据包-{dept}-{TODAY}.xlsx")
    total_img = sum(len(ws._images) for ws in wb.worksheets)
    print(f"{dept}: {len(wb.sheetnames)}表 {total_img}图 | {wb.sheetnames}")
