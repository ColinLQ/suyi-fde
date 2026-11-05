#!/usr/bin/env python3
# build-perf-excel.py — 绩效分析报告 Excel 生成器（主交付物）
# 数据源：out/performance-2026-09.json（build-performance-report.mjs 产出）
import json, re, sys
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage

import os
ROOT = Path(__file__).resolve().parent.parent
DATA_HOME = Path(os.environ.get('SCM_DATA_HOME') or (Path.home() / 'WorkBuddy' / 'scm-collector-data'))  # 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
data = json.loads((DATA_HOME / 'out' / 'performance-2026-09.json').read_text(encoding='utf-8'))
MONTH = data['统计月']
COST_PATH = DATA_HOME / 'out' / f'cost-{MONTH}.json'
COST = json.loads(COST_PATH.read_text(encoding='utf-8')) if COST_PATH.exists() else None
PIC_DIR = DATA_HOME / 'state' / 'goods-pics'

def pic_of(ref):
    """款号→本地图路径；匹配顺序：原样 → 全角/双横线归一 → 去客户后缀的纯款号；无图返回 None"""
    if not ref:
        return None
    ref = str(ref)
    cands = [ref, ref.replace('—', '-').replace('–', '-')]
    m = re.split(r'[-—–]{2,}', ref)[0] if '--' in ref else None
    base = re.split(r'[-—–]', ref)[0]
    if re.match(r'^(L[TQMW]|S[TQWM]|ST|PT|PW)\d{6}', base):
        cands.append(base)
    for name in cands:
        p = PIC_DIR / f'{name}.jpg'
        if p.exists() and p.stat().st_size > 500:
            return p
    return None

def add_pic_col(ws, col, header_row, refs, cell_w=45, img_h=96):
    """在指定列插入商品图：行高按图撑起，图锚定在单元格"""
    ws.cell(row=header_row, column=col, value='图片')
    ws.cell(row=header_row, column=col).font = head_font
    ws.cell(row=header_row, column=col).fill = head_fill
    ws.cell(row=header_row, column=col).border = border
    ws.cell(row=header_row, column=col).alignment = Alignment(horizontal='center', vertical='center')
    ws.column_dimensions[get_column_letter(col)].width = cell_w
    for i, ref in enumerate(refs):
        rr = header_row + 1 + i
        p = pic_of(ref)
        if p:
            img = XLImage(str(p))
            scale = img_h / img.height
            img.width = int(img.width * scale)
            img.height = img_h
            img.anchor = f'{get_column_letter(col)}{rr}'
            ws.add_image(img)
            if (ws.row_dimensions[rr].height or 0) < img_h * 0.78:
                ws.row_dimensions[rr].height = img_h * 0.78
        else:
            c = ws.cell(row=rr, column=col, value='无图')
            c.font = Font(name='PingFang SC', size=9, color='999999')
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.border = border

# 款号在各明细表中的列位置（第2列=款号，图片列统一插在表尾）
DETAIL_PIC_SHEETS = {
    '采购明细': '款号',
    '成本核算明细': '款号',
    '成本异常清单': '款号',
    '生产明细': '款号',
    '设计下单明细': '款号',
    '仓库明细': '款号',
}

# —— 样式 ——
NAVY = '1F3864'; LIGHT = 'D9E2F2'; RED_F = 'FFC7CE'; RED_T = '9C0006'
GREEN_F = 'C6EFCE'; GREEN_T = '006100'; YELLOW_F = 'FFEB9C'
title_font = Font(name='PingFang SC', size=14, bold=True, color=NAVY)
head_font = Font(name='PingFang SC', size=10, bold=True, color='FFFFFF')
head_fill = PatternFill('solid', fgColor=NAVY)
thin = Side(style='thin', color='B0B7C3')
border = Border(left=thin, right=thin, top=thin, bottom=thin)

def sheet_fill(ws, title, note=None):
    ws['A1'] = title; ws['A1'].font = title_font
    r = 2
    if note:
        ws.cell(row=r, column=1, value=note).font = Font(name='PingFang SC', size=9, italic=True, color='666666')
        r += 1
    return r + 1

def write_table(ws, start_row, headers, rows, widths=None, red_cols=None, green_cols=None):
    red_cols = red_cols or set(); green_cols = green_cols or set()
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=c, value=h)
        cell.font = head_font; cell.fill = head_fill; cell.border = border
        cell.alignment = Alignment(horizontal='center', vertical='center')
    for i, row in enumerate(rows):
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=start_row + 1 + i, column=c, value=v)
            cell.border = border
            cell.alignment = Alignment(horizontal='center' if c > 1 else 'left', vertical='center')
            hn = headers[c-1]
            if hn in red_cols and isinstance(v, (int, float)) and v > 0:
                cell.fill = PatternFill('solid', fgColor=RED_F); cell.font = Font(name='PingFang SC', size=10, color=RED_T)
            elif hn in green_cols and isinstance(v, (int, float)):
                cell.fill = PatternFill('solid', fgColor=GREEN_F); cell.font = Font(name='PingFang SC', size=10, color=GREEN_T)
    for c, w in enumerate(widths or [], 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    return start_row + 1 + len(rows)

def add_notes(ws, notes):
    """在工作表底部追回口径说明区：标题条 + 编号条目（合并整行、自动估算行高）"""
    ncols = max(ws.max_column, 3)
    total_w = sum((ws.column_dimensions[get_column_letter(c)].width or 9) for c in range(1, ncols + 1))
    r = ws.max_row + 2
    bar = ws.cell(row=r, column=1, value='口径说明 · 本表数据是怎么算出来的')
    bar.font = Font(name='PingFang SC', size=10, bold=True, color=NAVY)
    bar.fill = PatternFill('solid', fgColor=LIGHT)
    bar.alignment = Alignment(horizontal='left', vertical='center')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
    ws.row_dimensions[r].height = 21
    for i, t in enumerate(notes, 1):
        rr = r + i
        cell = ws.cell(row=rr, column=1, value=f'{i}. {t}')
        cell.font = Font(name='PingFang SC', size=9, color='404040')
        cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
        ws.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=ncols)
        vis = sum(2 if ord(ch) > 127 else 1 for ch in t) + 4   # +4 = 行首"序号. "前缀占位
        per = max(12, int(total_w * 0.68))   # 每行显示宽度（中文按2计），按 68% 保守估算，确保不裁字
        lines = max(1, -(-vis // per))
        ws.row_dimensions[rr].height = min(16 * lines + 8, 160)

wb = Workbook()

# ═══ 1 报告总览 ═══
ws = wb.active; ws.title = '报告总览'
r = sheet_fill(ws, f'绩效分析与提成计算月报 · {MONTH}', '数据来源：衣者云SCM只读接口全量回捞（2026-10-10）；口径依据《绩效分析与提成计算需求文档-V1》')
d = data['数据就绪度']
overview = [
    ('采购跟单', f"{d['采购月单量']} 单 / {len(data['采购跟单'])} 名采购员（含未分配）", '采购/到厂超期单已标红，明细见「采购明细」'),
    ('生产跟单', f"{d['出货月批次']} 批 / {d['月出货件数']} 件 / {len(data['生产跟单'])} 名跟单员", '四级超时分级+实际周期，明细见「生产明细」'),
    ('设计师', f"{len(data['设计师'])} 名设计师 / 建版与下单双口径", '下单款数为建议提成口径'),
    ('仓库', f"{d['月入库单']} 单入库，及时率 100%（同日录入）", '衣者内部无区分度，瓶颈在多客侧对齐（多客无入库时间记录）'),
    ('样板块', f"样板总量 {d['样板总量']} 款（设计师归属底表）", ''),
]
if COST:
    cg0 = COST['全局']
    sign = '低于' if cg0['总差额'] < 0 else '高于'
    overview.insert(2, ('成本核算', f"{cg0['订单数']} 单中 {cg0['有效订单']} 单可核算，实际成本{sign}预计 {abs(cg0['总差额率%'])}%（{cg0['总差额']:+,.0f} 元）",
                        '按采购员归属；采购未录价/偏差异常单已剔除，见「成本异常清单」'))
r = write_table(ws, r, ['岗位', '当月规模', '说明'], overview, widths=[14, 44, 60])
r += 2
ws.cell(row=r, column=1, value='⚠ 数据质量提示').font = Font(name='PingFang SC', size=11, bold=True, color='BF8F00')
q = data['数据质量说明']
for i, (k, v) in enumerate(q.items(), 1):
    ws.cell(row=r + i, column=1, value=f'· {k}：{v}').font = Font(name='PingFang SC', size=9, color='555555')

# ═══ 2 采购汇总 ═══
ws = wb.create_sheet('采购汇总')
r = sheet_fill(ws, f'采购跟单绩效汇总 · {MONTH}', '口径：按采购单创建月；超期=系统延期标记（order_purchase/reach_time_diff>0）；件数=计划件数合计')
rows = []
for name, s in sorted(data['采购跟单'].items(), key=lambda x: -x[1]['接单数']):
    rows.append([name, s['接单数'], s['件数'], s['采购完成'], s['采购中'], s['待采购'],
                 s['已到厂'], s['部分到厂'], s['待到厂'], s['采购超期'], s['到厂超期'],
                 round(s['采购超期'] / s['接单数'] * 100, 1) if s['接单数'] else 0,
                 round(s['到厂超期'] / s['接单数'] * 100, 1) if s['接单数'] else 0])
r = write_table(ws, r, ['采购员', '接单数', '件数', '采购完成', '采购中', '待采购', '已到厂', '部分到厂', '待到厂', '采购超期', '到厂超期', '采购超期率%', '到厂超期率%'],
                rows, widths=[10, 8, 8, 9, 8, 8, 8, 9, 8, 9, 9, 11, 11],
                red_cols={'采购超期', '到厂超期', '采购超期率%', '到厂超期率%'})

# ═══ 3 采购明细 ═══
ws = wb.create_sheet('采购明细')
r = sheet_fill(ws, f'采购单明细 · {MONTH}（{len(data["采购明细"])} 单）', '提成底表：每单可追溯；超期天数>0标红')
pd = data['采购明细']
rows = [[x['采购单号'], x['款号'], x['采购员'], x['下单日期'], x['件数'], x['工厂'], x['采购状态'], x['到厂状态'], x['采购超期天数'], x['到厂超期天数']] for x in pd]
r = write_table(ws, r, ['采购单号', '款号', '采购员', '下单日期', '件数', '工厂', '采购状态', '到厂状态', '采购超期天数', '到厂超期天数'],
                rows, widths=[16, 13, 9, 11, 7, 10, 9, 9, 11, 11], red_cols={'采购超期天数', '到厂超期天数'})
ws.auto_filter.ref = f'A{r-len(rows)}:J{r-1}'; ws.freeze_panes = f'A{r-len(rows)+1}'

# ═══ 3.5 成本核算汇总 / 3.6 成本明细 / 3.7 成本异常（采购员成本控制） ═══
if COST:
    cg = COST['全局']
    # —— 汇总 ——
    ws = wb.create_sheet('成本核算汇总')
    r = sheet_fill(ws, f'采购员成本核算汇总 · {MONTH}',
                   '口径：实际成本 − 预计成本（负数=低于预计/控制有效）；仅统计有效单；采购员归属=采购单 buyer_name（生产单与采购单一一对应）')
    rows = []
    for name, s in COST['采购员成本'].items():
        rows.append([name, s['订单数'], s['有效订单'], s['有效样本率%'], s['计价件数'],
                     s['预计总成本'], s['实际总成本'], s['成本差额'], s['差额率%'],
                     s['单件预计'], s['单件实际'], s['单件差额'],
                     s['显著节约'], s['略优'], s['基本持平'], s['略超'], s['明显超支'],
                     s['采购成本占比%'], s['加工费占比%'], s['入库口径_差额'], s['评价']])
    rows.append(['合计', cg['订单数'], cg['有效订单'], round(cg['有效订单'] / cg['订单数'] * 100, 1) if cg['订单数'] else None,
                 cg['计价件数'], cg['预计总成本'], cg['实际总成本'], cg['总差额'], cg['总差额率%'],
                 cg['单件预计'], cg['单件实际'], cg['单件差额'],
                 sum(s['显著节约'] for s in COST['采购员成本'].values()), sum(s['略优'] for s in COST['采购员成本'].values()),
                 sum(s['基本持平'] for s in COST['采购员成本'].values()), sum(s['略超'] for s in COST['采购员成本'].values()),
                 sum(s['明显超支'] for s in COST['采购员成本'].values()), None, None, None, ''])
    r = write_table(ws, r, ['采购员', '订单数', '有效订单', '有效样本率%', '计价件数', '预计总成本', '实际总成本', '成本差额', '差额率%',
                            '单件预计', '单件实际', '单件差额', '显著节约', '略优', '基本持平', '略超', '明显超支',
                            '采购占成本%', '加工占成本%', '入库口径差额', '评价'],
                    rows, widths=[10, 8, 9, 11, 10, 13, 13, 12, 9, 9, 9, 9, 9, 7, 9, 7, 9, 11, 11, 12, 12],
                    red_cols={'明显超支', '略超'}, green_cols={'显著节约', '略优'})
    for c in range(1, 22):  # 合计行加粗
        cell = ws.cell(row=r - 1, column=c)
        cell.font = Font(name='PingFang SC', size=10, bold=True, color=NAVY)
        cell.fill = PatternFill('solid', fgColor=LIGHT)

    # —— 明细 ——
    ws = wb.create_sheet('成本核算明细')
    r = sheet_fill(ws, f'订单成本明细 · {MONTH}（{len(COST["成本明细"])} 单，可核算 {cg["有效订单"]} 单）',
                   '提成底表：一单一行的成本对比，可按采购员/款号/判定筛选；「有效性」≠有效 的单请勿直接用于考核（见「成本异常清单」）')
    rows = []
    for x in COST['成本明细']:
        rows.append([x['生产单号'], x['款号'], x['采购员'], x['采购单号'], x['工厂'], x['下单时间'], x['订单类型'], x['生产状态'],
                     x['下单数'], x['裁货数'], x['入库数'], x['计价基数'], x['预计单件成本'], x['实际单件成本'], x['单件差额'],
                     x['预计总成本'], x['实际总成本'], x['总差额'], x['差额率'], x['判定'],
                     x['单件采购成本'], x['单件加工费'], x['单件固定成本'], x['采购占成本%'], x['加工占成本%'], x['有效性']])
    r = write_table(ws, r, ['生产单号', '款号', '采购员', '采购单号', '工厂', '下单时间', '订单类型', '生产状态',
                            '下单数', '裁货数', '入库数', '计价基数', '预计单件', '实际单件', '单件差额',
                            '预计总成本', '实际总成本', '总差额', '差额率%', '判定',
                            '单件采购', '单件加工', '单件固定', '采购占比%', '加工占比%', '有效性'],
                    rows, widths=[16, 15, 9, 16, 11, 11, 8, 9, 8, 8, 8, 9, 9, 9, 9, 12, 12, 11, 8, 10, 9, 9, 9, 10, 10, 22])
    ws.auto_filter.ref = f'A{r-len(rows)}:Z{r-1}'; ws.freeze_panes = f'A{r-len(rows)+1}'

    # —— 异常清单 ——
    ws = wb.create_sheet('成本异常清单')
    r = sheet_fill(ws, f'成本数据异常清单 · {MONTH}（{len(COST["异常清单"])} 单）',
                   '这些单被排除在成本核算汇总之外：采购未录价会让实际成本变 0（伪造巨额节约），偏差>50% 多为单位或数量录入错误。建议逐单核实后重算')
    rows = []
    for x in COST['异常清单']:
        rows.append([x['生产单号'], x['款号'], x['采购员'], x['采购单号'], x['工厂'], x['下单时间'], x['生产状态'],
                     x['下单数'], x['裁货数'], x['入库数'], x['预计单件成本'], x['实际单件成本'], x['单件采购成本'],
                     x['差额率'], x['总差额'], x['有效性']])
    r = write_table(ws, r, ['生产单号', '款号', '采购员', '采购单号', '工厂', '下单时间', '生产状态',
                            '下单数', '裁货数', '入库数', '预计单件', '实际单件', '单件采购', '差额率%', '总差额', '异常原因'],
                    rows, widths=[16, 15, 9, 16, 11, 11, 9, 8, 8, 8, 9, 9, 9, 9, 12, 30],
                    red_cols={'总差额'})
    ws.auto_filter.ref = f'A{r-len(rows)}:P{r-1}'; ws.freeze_panes = f'A{r-len(rows)+1}'


# ═══ 4 生产跟单汇总 ═══
ws = wb.create_sheet('生产跟单汇总')
r = sheet_fill(ws, f'生产跟单绩效汇总 · {MONTH}', '超时分级：实际出货 − 预计出货（≤0 准时 / 1-2 / 3-5 / >5 天）；实际周期 = 实际出货 − 主料到厂；延误归因：延期单中主料到厂晚于预计出货=采购段，到厂按时仍晚=生产段')
rows = []
for name, s in sorted(data['生产跟单'].items(), key=lambda x: -x[1]['出货件数']):
    valid = s['准时'] + s['超1到2天'] + s['超3到5天'] + s['超5天以上']
    rows.append([name, s['出货批次'], s['款数'], s['出货件数'], s['准时'], s['超1到2天'], s['超3到5天'], s['超5天以上'], s['数据缺失'],
                 round(s['准时'] / valid * 100, 1) if valid else None,
                 s['采购段延误'], s['生产段延误'], s.get('无法归因', 0),
                 s['平均周期'], s['周期中位'], s['周期样本数']])
r = write_table(ws, r, ['跟单员', '出货批次', '款数', '出货件数', '准时', '超1-2天', '超3-5天', '超5天以上', '数据缺失', '按时率%', '采购段延误', '生产段延误', '无法归因', '平均周期(天)', '周期中位(天)', '周期样本'],
                rows, widths=[9, 9, 7, 9, 7, 9, 9, 10, 9, 9, 11, 11, 9, 12, 12, 9],
                red_cols={'超5天以上', '采购段延误', '生产段延误'}, green_cols={'准时', '按时率%'})

# ═══ 5 生产明细 ═══
ws = wb.create_sheet('生产明细')
r = sheet_fill(ws, f'出货明细 · {MONTH}（{len(data["生产明细"])} 批）', '延误归因：采购段=主料到厂已晚于预计出货（面料晚到挤占生产时间）；生产段=面料按时到但出货仍晚；「(缺预计)」=系统未填预计出货时间，无法分级')
rows = []
for x in data['生产明细']:
    rows.append([x['出货日期'], x['款号'], x['跟单员'], x['工厂'], x['订单类型'], x['出货件数'], x['下单时间'], x['主料到厂'], x['实际周期天'], x['预计出货'], x['实际出货'], x['与预计差异天'], x['超时分级'], x['延误归因']])
r = write_table(ws, r, ['出货日期', '款号', '跟单员', '工厂', '订单类型', '出货件数', '下单时间', '主料到厂', '实际周期(天)', '预计出货', '实际出货', '差异(天)', '超时分级', '延误归因'],
                rows, widths=[11, 13, 9, 11, 8, 8, 11, 11, 11, 11, 11, 9, 10, 13])
ws.auto_filter.ref = f'A{r-len(rows)}:N{r-1}'; ws.freeze_panes = f'A{r-len(rows)+1}'

# ═══ 6 工厂透视 ═══
ws = wb.create_sheet('工厂透视')
r = sheet_fill(ws, f'工厂货期透视 · {MONTH}', '延误归因已并入：生产段延误为主=工厂责任；部分工厂缺预计时间无法分级（样本见透视表）（管理动作：下单时强制填写）')
rows = []
for name, s in sorted(data['工厂透视'].items(), key=lambda x: -x[1]['出货件数']):
    valid = s['准时'] + s['超1到2天'] + s['超3到5天'] + s['超5天以上']
    rows.append([name, s['出货批次'], s['出货件数'], s['准时'], s['超1到2天'], s['超3到5天'], s['超5天以上'], s['数据缺失'], s['按时率'], s['采购段延误'], s['生产段延误']])
r = write_table(ws, r, ['工厂', '出货批次', '出货件数', '准时', '超1-2天', '超3-5天', '超5天以上', '数据缺失', '按时率%', '采购段延误', '生产段延误'],
                rows, widths=[12, 9, 9, 7, 9, 9, 10, 9, 9, 11, 11],
                red_cols={'超5天以上', '采购段延误', '生产段延误'}, green_cols={'准时', '按时率%'})

# ═══ 7 设计师汇总 ═══
ws = wb.create_sheet('设计师汇总')
r = sheet_fill(ws, f'设计师绩效汇总 · {MONTH}', '建议提成口径=下单款数（商业转化）；转化率>100%=下单款含历史建版，属正常（老款返单）')
rows = [[n, s.get('建版数', 0), s['下单款数'], s['下单批次'], s['下单件数'], s.get('设计转化率', '-')]
        for n, s in sorted(data['设计师'].items(), key=lambda x: -x[1]['下单件数'])]
r = write_table(ws, r, ['设计师', '建版数', '下单款数', '下单批次', '下单件数', '下单/建版转化'],
                rows, widths=[12, 8, 9, 9, 9, 13], green_cols={'下单件数'})

# ═══ 8 设计明细 ═══
ws = wb.create_sheet('设计下单明细')
r = sheet_fill(ws, f'当月下单款明细 · {MONTH}（{len(data["设计明细"])} 批）', '设计师归属来自样板档案 design_user')
rows = [[x['下单日期'], x['款号'], x['设计师'], x['品类'], x['波段'], x['订单类型'], x['下单件数']] for x in data['设计明细']]
r = write_table(ws, r, ['下单日期', '款号', '设计师', '品类', '波段', '订单类型', '下单件数'],
                rows, widths=[11, 13, 12, 10, 12, 8, 9])
ws.auto_filter.ref = f'A{r-len(rows)}:G{r-1}'; ws.freeze_panes = f'A{r-len(rows)+1}'

# ═══ 9 仓库汇总 ═══
ws = wb.create_sheet('仓库汇总')
r = sheet_fill(ws, f'仓库录入及时性 · {MONTH}', '口径：衣者出库→衣者入库相差天数，T+1 内=及时；多客无入库时间记录，跨系统对齐暂不可算（需推动仓库在多客规范录入或用库存日快照反推）')
rows = [[n, s['入库单数'], s['及时数'], s['超1天'], s['缺时间无法算'], s['及时率'], s['平均延迟']]
        for n, s in sorted(data['仓库'].items(), key=lambda x: -x[1]['入库单数'])]
r = write_table(ws, r, ['录入人', '入库单数', '及时数(T+1内)', '超1天', '缺时间', '及时率%', '平均延迟(天)'],
                rows, widths=[10, 9, 12, 8, 8, 9, 12], green_cols={'及时率%'}, red_cols={'超1天'})

# ═══ 10 仓库明细 ═══
ws = wb.create_sheet('仓库明细')
r = sheet_fill(ws, f'出库→入库对齐明细 · {MONTH}（{len(data["仓库明细"])} 单）', '关联键：stockout_record_id；每日推送清单可基于此表按日切')
rows = [[x['出库日期'], x['款号'], x['出库件数'], x['仓库录入人'], x['入库日期'], x['相差天数'], x['是否及时']] for x in data['仓库明细']]
r = write_table(ws, r, ['出库日期', '款号', '出库件数', '仓库录入人', '入库日期', '相差天数', '是否及时'],
                rows, widths=[11, 13, 9, 10, 11, 9, 9], green_cols={'是否及时'})

# ═══ 商品图片列：所有跟商品（款号）相关的明细表，表尾插"图片"列 ═══
# 图片来源：多客商品档案缩略图（state/goods-pics/<款号>.jpg），生成前跑 fetch-perf-goods-pics.mjs
NO_PIC = []
def nofile(ref):
    """多客 goods 快照中无此款档案（原样/归一化均未命中）"""
    r = str(ref)
    rows_g = _GOODS_REFS
    return r not in rows_g and r.replace('—', '-').replace('–', '-') not in rows_g

_GOODS_REFS = set()
_gf = DATA_HOME / 'data/raw/2026-10-09/pm/duoke_goods.jsonl'
if _gf.exists():
    for _line in _gf.read_text(encoding='utf-8').splitlines():
        if _line.strip():
            try:
                _r = json.loads(_line).get('item_ref')
                if _r:
                    _GOODS_REFS.add(_r)
            except Exception:
                pass

def add_pics(sheet_name, header_row_offset, ref_list):
    ws2 = wb[sheet_name]
    col = ws2.max_column + 1
    hr = ws2.max_row - len(ref_list) - header_row_offset + 1  # 表头所在行
    # 表头行 = 数据首行-1；write_table 从 start_row 写表头
    add_pic_col(ws2, col, hr, ref_list)

# 数据行定位重算：write_table 返回 表头行+1+行数；表头行 = 返回值-1-len(rows)
def _pic_block(sheet_name, refs):
    ws2 = wb[sheet_name]
    hr = None
    for rr in range(1, ws2.max_row + 1):
        v = ws2.cell(row=rr, column=1).value
        if v == '口径说明 · 本表数据是怎么算出来的':
            break
        if isinstance(v, str) and ('款号' in str(ws2.cell(row=rr, column=2).value or '') or v in ('采购单号', '生产单号', '下单日期', '出库日期')):
            hr = rr
    if hr is None:
        return
    col = ws2.max_column + 1
    add_pic_col(ws2, col, hr, refs)
    ws2.auto_filter.ref = ws2.auto_filter.ref.replace(
        ws2.auto_filter.ref.split(':')[-1], f'{get_column_letter(ws2.max_column)}{hr + len(refs)}'
    ) if ws2.auto_filter.ref else None

_pic_block('采购明细', [x['款号'] for x in data['采购明细']])
_pic_block('生产明细', [x['款号'] for x in data['生产明细']])
_pic_block('设计下单明细', [x['款号'] for x in data['设计明细']])
_pic_block('仓库明细', [x['款号'] for x in data['仓库明细']])
if COST:
    _pic_block('成本核算明细', [x['款号'] for x in COST['成本明细']])
    _pic_block('成本异常清单', [x['款号'] for x in COST['异常清单']])

# 统计无图款（供口径说明披露）
_all_refs = set()
for src in (data['采购明细'], data['生产明细'], data['设计明细'], data['仓库明细']):
    for x in src:
        if x.get('款号'):
            _all_refs.add(x['款号'])
if COST:
    for x in COST['成本明细']:
        if x.get('款号'):
            _all_refs.add(x['款号'])
NO_PIC = sorted(r for r in _all_refs if pic_of(r) is None)

# ═══ 各表底部：口径说明（给看表的人，可作审计依据） ═══
ORDERS = len({x['生产单号'] for x in data['生产明细'] if x.get('生产单号')})
_oc = {}
for _x in data['生产明细']:
    _oc[_x.get('生产单号')] = _oc.get(_x.get('生产单号'), 0) + 1
MULTI = sum(1 for v in _oc.values() if v > 1)
MAXB = max(_oc.values()) if _oc else 0
NOTES = {
    '报告总览': [
        f'统计月：{MONTH}（月报建议每月 1 日出上月；当月进行中的月份不作完整月统计）。',
        f'数据来源：衣者云 SCM 只读接口全量回捞。绩效类数据（采购/生产/设计/仓库）为 2026-10-10 快照；成本核算数据为 2026-10-23 实时回捞。同一表内不混用不同时点数据。',
        f'统计范围：{q["统计范围"]}。',
        '落月口径：一律按业务发生时间归月（出货=出货时间 stockout_at、采购=采购单创建时间 created_at），不按数据录入时间——保证同一笔业务只在发生月计提一次，避免跨月重复。',
        '四岗位提成口径建议：采购=接单数×超期折减；生产跟单=出货件数×超时分级系数；设计=下单款数；仓库=及时率。系数与封顶规则待管理层拍板，定稿前本报告仅作核算依据、不直接出金额。',
        '每张汇总表都配有对应"明细"表（一单/一批一行，含单号款号，可回系统原单核对），可直接作为提成底表使用。',
        f'商品图片：六张明细表（采购/生产/设计/仓库/成本核算/成本异常）表尾均附"图片"列，取自多客商品档案缩略图（匹配顺序：原款号 → 全角横线归一 → 去客户后缀纯款号）。本月报表涉及 {len(_all_refs)} 款，其中 {len(_all_refs) - len(NO_PIC)} 款有图、{len(NO_PIC)} 款无图。无图两类原因：①多客有档案但从未上传图片（{len(NO_PIC) - len([r for r in NO_PIC if nofile(r)])} 款，需补传）；②多客无此款档案（{len([r for r in NO_PIC if nofile(r)])} 款，新款未建档或建档晚于档案快照 2026-10-09，管理动作：新款建档时把图片上传设为必填步骤）。',
        '本文件不含独立的口径总表——每张工作表底部即该表的口径说明（取数接口、落月规则、公式、缺失值处理、异常披露）。口径调整（如超时分档、提成系数、联名款拆分）改生成脚本后重算当月即可，不影响原始数据。',
        '只读声明：全程只读查询接口，未做任何保存/删除/导出类写操作。',
    ],
    '采购汇总': [
        f'数据源：采购单接口全状态回捞（buy_status=3 即"采购完成"），{MONTH} 按创建时间落月共 {d["采购月单量"]} 单。',
        '接单数=该采购员当月创建的采购单数；件数=计划总件数 plan_total_num 合计（非实际到货件数）。',
        '采购超期/到厂超期直接取系统字段 order_purchase_time_diff / order_reach_time_diff（下单→采购完成、下单→到厂的延期天数），>0 即超期；不是我方二次计算的。',
        '"未分配"=采购单 buyer_name 为空（9 月 32 单，占 22%）。这批单会同时稀释各采购员的超期率，建议先在系统补分配规则，再用于提成核算。',
        '超期率分母均为接单数。同一单可能同时"采购超期"和"到厂超期"，两列不可相加；判断真实瓶颈看"到厂超期"。',
        '提成建议：9 月到厂超期率 63.4%（采购超期率低得多），说明延误主要发生在工厂交货段而非采购下单段，建议以"到厂超期率"作为主要折减项。',
    ],
    '采购明细': [
        '一行=一张采购单。采购单号 purchase_sn 可回衣者系统原单逐条核对。',
        '超期天数为系统字段原值；0 或空=未超期，>0 已标红。',
        '采购状态/到厂状态为系统描述原值（采购完成/采购中/待采购、已到厂/部分到厂/待到厂），未做映射改写。',
        '下单日期=采购单创建日期，仅用于落月归属，不代表到货日期。',
        '本表为采购提成底表：可按采购员筛选，与「采购汇总」逐人小计对得上。',
        f'图片列=多客商品档案缩略图（按款号匹配）；显示"无图"=多客该款未上传图片或未建档（本月无图款共 {len(NO_PIC)} 个，明细见「报告总览」数据质量提示）。',
    ],
    '生产跟单汇总': [
        f'数据源：裁床出货记录（stockout_panel/record_list），按出货时间 stockout_at 落 {MONTH}：{d["出货月批次"]} 批 / {d["月出货件数"]:,} 件。',
        f'出货批次 ≠ 订单数：{d["出货月批次"]} 批对应 {ORDERS} 个生产单，其中 {MULTI} 单分了多批出货（最多一单出 {MAXB} 批）。一个订单可分多次交货，所以批次数大于订单数——系统按订单行统计、本表按出货批次统计，这是两边数字不同的第一个原因。',
        f'与系统页面口径的差异：跟单管理按"出货时间筛月"圈出的是订单行，页面"出货数"=命中订单的累计出货（含同批订单 8 月出的 1,472 件、10 月出的 234 件）；本表 {d["月出货件数"]:,} 件只算 {MONTH} 当月实际出掉的货。8 月那批已在 8 月计过，再算一次就是重复计提。',
        '超时分级=实际出货日 − 预计出货日：≤0 为"准时"，1-2 天、3-5 天、>5 天以上依次三档（按管理层 2026-10 确认的口径）。',
        '按时率=准时 ÷（准时+超1-2+超3-5+超5天以上）；"数据缺失"（未填预计出货时间）不计入分母，因此按时率是"可评估样本"内的比率，非全量。',
        '实际周期=实际出货日 − 主料最后到厂日，取自跟单进度"物料到厂"步骤文本；主料优先，辅料时间未纳入。该指标衡量从"有料可做"到"货出仓"的真实生产时长，与预计周期的差异反映工厂执行。',
        '延误归因（回答"是不是采购的问题"）：延期单中若主料到厂日 > 预计出货日 → 采购段延误（面料晚到已挤占生产时间）；若到厂按时而出货仍晚 → 生产段延误（工厂拿到料没按期交货）；两者缺一 → 无法归因。9 月结论：可归因延误单中绝大多数为生产段。',
        f'数据缺失说明：{q["预计出货时间填写率"]} 批已填预计出货时间，其余未填（集中在个别工厂）→ 无法分级，会低估实际超时率。管理动作：下单时把预计出货时间设为必填。',
    ],
    '生产明细': [
        '一行=一次出货（一个批次）。同一款号可能多行（分批发货），按款号筛选可看单款全部分批。',
        '下单时间=生产订单创建时间（order_created_at）。它与"主料到厂""实际出货"共同构成 下单→到厂→出货 完整时间轴，可定位卡在哪一段。',
        '主料到厂=跟单进度"物料到厂"步骤里的"主料最后到厂"值；显示"(缺失)"表示该步骤未填或无法解析。',
        '实际周期(天)=实际出货 − 主料到厂；"(缺失)"表示到厂时间不可解析，该行不参与周期均值。',
        '差异(天)=实际出货 − 预计出货。负数=提前出货，0=准时，正数=延期。显示"(缺预计)"=系统未填预计出货时间，该行不参与分级。',
        '延误归因仅在延期单上给出；准时/提前出货的单显示"-"（无延误可归因）。采购段=面料晚到，生产段=工厂拖期。',
        '异常提示：明细中若存在下单日晚于出货日的时间倒挂行（疑为返单或系统记录问题），已原样保留未做修正，核算时请单独核实。',
        f'图片列=多客商品档案缩略图（按款号匹配）；"无图"=该款多客未上传图片或未建档。',
    ],
    '工厂透视': [
        '分组维度=出货记录上的工厂字段 factory_name，一行一家工厂；同一工厂可能承接多类订单。',
        f'批次/件数/四级分级/延误归因均按出货批次计数，与「生产跟单汇总」同源同口径，两表总批次应一致（{d["出货月批次"]} 批）。',
        '按时率=准时 ÷ 有效样本（剔除"数据缺失"）。有效样本过少的工厂（如仅 1 个有效样本者）按时率仅供参考，不足以评价工厂能力。',
        '采购段延误/生产段延误为该厂延期单的责任拆分：用于区分"面料没到"与"工厂拖期"。生产段占比高=该厂自身交付能力问题，应纳入工厂考核而非跟单员个人。',
        '9 月关键读数：恒生占出货件数 58% 但准时率 43.4%、生产段延误 40 批——大厂依赖与货期失控并存，是降本增效第一抓手（建议谈交付条款/分单）。',
    ],
    '设计师汇总': [
        '建版数=当月新建样板数（样板档案创建时间落月），反映"设计产出量"。',
        '下单款数=当月生产单涉及款去重（含老款返单），反映"设计被下单采用量"——建议作为提成口径，因为它对齐商业转化，避免只建版不下单也拿提成。',
        '下单/建版转化率=下单款数 ÷ 建版数。>100% 属正常（当月下单的款里有历史建版的老款返单），不代表数据错误；<100% 表示建版未被采用。',
        '设计师归属取样板档案 design_user 字段；联名款（如"SOSO,李亚欣"）按系统原始字符串整体归组，未拆分到个人——如联名需各半计，请指定拆分规则后重算。',
        '下单件数=当月该设计师款对应生产单的计划件数合计（与采购/生产表的件数同源）。',
    ],
    '设计下单明细': [
        '一行=一个款的一次下单（生产单）。同款多次返单会多行。',
        '下单日期=生产单创建日期，用于落月归属。',
        '设计师来自样板档案 design_user 字段；品类、波段、订单类型均为系统字段原值，未做归并。',
        '可按设计师筛选，核对「设计师汇总」的款数/件数小计；按品类/波段筛选可看设计结构是否失衡。',
        '图片列=多客商品档案缩略图（按款号匹配）；"无图"=该款多客未上传图片或未建档。',
    ],
    '仓库汇总': [
        f'当前口径：衣者出库时间 → 衣者入库时间，相差 ≤1 天记为及时（T+1 合理窗口）；关联键为 stockout_record_id，可一一对应。',
        f'{MONTH} {d["月入库单"]} 单入库全部为同日录入，及时率 100%——该口径在衣者内部没有区分度，不能反映真实录入延迟，仅作基线。',
        '需求要求的是"衣者出库 vs 多客入库"跨系统对齐（多客入库时间才代表真正入账时点），但多客系统目前没有入库时间字段，该口径暂无法计算。',
        '过渡方案：用多客库存日快照的环比增量反推当日入库量（T+1 精度够用），配合款号映射对齐；治本方案是推动仓库在多客规范录入入库时间字段。',
        '缺时间=入库单无入库时间或未能关联到出库记录，不计入及时率分母；该列数值越大，说明采集/关联越不完整。',
    ],
    '仓库明细': [
        '一行=一张入库单，通过 stockout_record_id 关联回对应的出库记录。',
        '相差天数=入库日期 − 出库日期；≤1 天=及时，>1=超时（当前数据全部为 0 天）。',
        '每日推送清单可基于本表按"出库日期"切分当日数据，T+1 推送前一天出库未入库的清单。',
        '仓库录入人取入库单 username 字段，代表实际操作人（非出库人）。',
        '图片列=多客商品档案缩略图（按款号匹配）；"无图"=该款多客未上传图片或未建档。',
    ],
    '成本核算汇总': [
        '数据源：衣者云「财务对账-按订单核对」（/backend/finance/get_production_process_list），按生产单下单时间落月；采购员归属取自采购单 buyer_name（9 月 145 张采购单对应 145 个生产单，一一对应，无一单多采购员）。',
        '口径：预计成本=系统"预计单件成本（平均）"×计价件数；实际成本=系统"实际单件成本"×计价件数；差额=实际−预计。负数=实际低于预计（成本控制有效），正数=超支。差额率=差额÷预计。',
        '为什么用"按裁货"而不是"按入库"：9 月 150 单中 76 单尚未入库，入库口径只能覆盖 69 单。裁货口径覆盖 144 单，样本更全；明细表另列"入库单件成本"作参考，两口径趋势一致时结论才稳。',
        '"有效订单"与"订单数"的差：采购尚未录价会让实际成本变成 0，偏差>50% 多为单位/数量录入错误——这些单若计入，会凭空造出上百万元"节约"。故剔除后单列，「成本异常清单」逐单可查。',
        '不可拆分说明：系统只提供"预计单件成本"总额，没有"预计采购成本"分项，工艺成本亦为残差推算。所以无法在数学上把差额拆成"采购段"与"加工段"；明细表给出采购/加工占比，供人工判断超支到底出在面料还是工厂。',
        '评价分档：≤−3% 显著节约 / −3%~−1% 略优 / ±1% 基本持平 / 1%~3% 略超 / >3% 明显超支。未分配采购员的单不作个人考核，仅反映流程缺口。',
        '提成建议：成本差额率适合作为"超额利润分享"的加分项而非扣罚项——差额在 ±1% 内已属正常预估精度，真正该管的是"采购未录价"这类流程问题，它让成本无法被评估。',
    ],
    '成本核算明细': [
        '一行=一个生产单（下单月归属）。生产单号/采购单号均可回衣者系统原单核对。',
        '预计单件=系统预估单件成本；实际单件=按裁货的实际单件成本；单件差额=实际−预计。',
        '预计总成本/实际总成本=单件成本×计价件数；总差额=实际总成本−预计总成本。',
        '计价基数：按裁货（默认，件数=裁货数）；裁货为 0 时用入库数；两者皆无则按下单数兜底并标注——不同基数的单不可直接比金额，只可比差额率。',
        '单件采购/单件加工/单件固定：成本结构拆解，用于判断超支来自面料采购还是工厂加工（采购占比高=更受采购议价影响）。',
        '有效性列："有效"以外的单（采购未录价、单价缺失、偏差>50%）请勿直接用于考核，先核实再重算。',
        '图片列=多客商品档案缩略图（按款号匹配）；"无图"=该款多客未上传图片或未建档。',
    ],
    '成本异常清单': [
        '本表是从成本核算中剔除的订单及剔除原因，属数据质量问题而非绩效结论。',
        '"采购未录价（实际成本为0）"：采购单还没填单价或尚未采购，系统实际成本为 0，一算就是 −100% 的假节约——必须剔除。',
        '"偏差>50%（疑单位或录入异常）"：常见于单价按米/件混填、数量单位错误（如按整卷计价），金额影响可达数万元，建议优先核实。',
        '处理动作：把本表按采购员筛出，逐单核对采购单价与数量；数据补齐后重跑（改统计月参数），汇总数字会自动更新。',
        '本表金额仅作定位参考，不代表真实成本差异。',
        '图片列=多客商品档案缩略图（按款号匹配）；"无图"=该款多客未上传图片或未建档。',
    ],
}
for _name, _items in NOTES.items():
    if _name in wb.sheetnames:
        add_notes(wb[_name], _items)

out = DATA_HOME / 'out' / f'绩效分析报告-{MONTH}.xlsx'
wb.save(out)
print('saved:', out)
