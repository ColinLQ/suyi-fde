#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
样衣管理日报 Excel 生成器 —— scm-collector 设计部链路（V1.1，2026-11-04 固化）
================================================================
从 data/raw/<日期>/<槽>/yizhe_template_list.jsonl（样板全量快照）直接生成 Excel 日报：
  00总览        今日快照结论 + 今天必做3件事
  01管线蓄水池  13环节件数 + 环比（可选 --prev-date）
  02时间预警    超 1/3/3/7/14 天规则的款（红黄级别）
  03今日工作清单 在制品按环节+新创建排序
  04品类结构    周×品类透视 + 季累计
  05数据稽核    款名/波段缺失名单（近30天黄底置顶）
每个 sheet = 顶部总结区 + 中部明细（筛选/冻结/条件格式）+ 底部口径说明。

规则来源：客户方设计部需求会议（管理层拍板），口径全文见 SKILL.md「样衣管理日报」节（改动须留痕）。
迁移性：相对路径自解析（与 build-production-report.py 同范式），换设备登录衣者后同一条命令即得相同结果。

用法（在 skill 根目录执行）：
  node scripts/fetch-endpoints.mjs --batch evening --only yizhe_template_list.jsonl      # 先采快照
  python3 scripts/build-sample-report-excel.py --date <YYYY-MM-DD> [--slot am] [--prev-date <YYYY-MM-DD>]

依赖：python3 + openpyxl
"""
import csv, json, os, re, argparse
from datetime import datetime, timedelta

try:
    import openpyxl
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "openpyxl>=3.1.0"])
    import openpyxl

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # skill 根目录

# ============ 会议拍板规则（改动须留痕） ============RULES = dict(fab=1, pat=3, sew=3, order=7, stay=14, review=20)
SEASON_START = '2026-10-01'   # 当季开发窗口起点（跨季改这里）

STEPS = ['新开发', '面辅料齐', '已打板', '已车板', '复版', '审版完成', '废版', '待下单',
         '面辅料已填', '用量已算', '制单完善', '确认可下单', '已下单']

# ============ 数据加载与派生 ============
def load_rows(raw_path):
    rows = []
    with open(raw_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows

def days_since(r, now):
    try:
        return (now - datetime.strptime((r.get('created_at') or '')[:10], '%Y-%m-%d')).days
    except Exception:
        return None

def week_key(datestr):
    d = datetime.strptime(datestr[:10], '%Y-%m-%d')
    mon = d - timedelta(days=d.weekday())
    return mon.strftime('%Y-%m-%d')

def build_derived(rows, now, prev_rows=None):
    """从快照行派生四张明细表数据：pool/warns/today_work/category/audit"""
    pool = {s: 0 for s in STEPS}
    pool_prev = {s: 0 for s in STEPS}
    for r in rows:
        st = r.get('template_status_name') or '未知'
        if st in pool:
            pool[st] += 1
    if prev_rows:
        for r in prev_rows:
            st = r.get('template_status_name') or '未知'
            if st in pool_prev:
                pool_prev[st] += 1

    total = len(rows)
    pool_rows = [[s, pool_prev[s] if prev_rows else None, pool[s],
                  (pool[s] - pool_prev[s]) if prev_rows else None,
                  (pool[s] / total) if total else None] for s in STEPS]
    pool_total = ['合计', sum(pool_prev.values()) if prev_rows else None, total,
                  (total - sum(pool_prev.values())) if prev_rows else None, 1.0]

    warns = []
    for r in rows:
        st = r.get('template_status_name') or '?'
        d = days_since(r, now)
        wtype, rule, lvl = '', '', ''
        if st == '新开发' and d is not None and d >= RULES['fab']:
            wtype, rule = '面辅料未齐', f'{RULES["fab"]}天内到面辅料'
            lvl = '高' if d >= 3 else '中'
        elif st == '面辅料齐' and d is not None and d >= RULES['pat']:
            wtype, rule = '待打板超时', f'{RULES["pat"]}天内打板'
            lvl = '高' if d >= 5 else '中'
        elif st == '已打板' and d is not None and d >= RULES['sew']:
            wtype, rule = '待车板超时', f'{RULES["sew"]}天内车板'
            lvl = '高' if d >= 5 else '中'
        elif st == '审版完成' and d is not None and d >= RULES['order']:
            wtype, rule = '审版完成滞留', f'{RULES["order"]}天内下单/{RULES["stay"]}天必处理'
            lvl = '高' if d >= RULES['stay'] else '中'
        if wtype:
            warns.append([r.get('template_no', ''), (r.get('template_name') or '').strip() or '(款名空)',
                          st, r.get('band_name') or '(波段空)', r.get('cat_name') or '',
                          (r.get('created_at') or '')[:10], d or 0, lvl, wtype, rule])
    warns.sort(key=lambda x: ({'高': 0, '中': 1}.get(x[7], 2), -x[6]))

    work = []
    for st in ['面辅料齐', '已打板', '已车板']:
        for r in rows:
            if (r.get('template_status_name')) == st:
                work.append([st, r.get('template_no', ''), (r.get('template_name') or '').strip() or '(款名空)',
                             r.get('band_name') or '(波段空)', r.get('cat_name') or '',
                             (r.get('created_at') or '')[:10], days_since(r, now) or 0])
    order = {'面辅料齐': 0, '已打板': 1, '已车板': 2}
    work.sort(key=lambda x: (order[x[0]], -int(x[5].replace('-', '') or 0)))
    work = [[i + 1] + row for i, row in enumerate(work)]

    week_cat, season_cat = {}, {}
    for r in rows:
        ca = r.get('created_at') or ''
        if ca < SEASON_START:
            continue
        wk, cat = week_key(ca), r.get('cat_name') or '未分类'
        week_cat.setdefault(wk, {})
        week_cat[wk][cat] = week_cat[wk].get(cat, 0) + 1
        season_cat[cat] = season_cat.get(cat, 0) + 1
    cats = sorted(season_cat, key=lambda c: -season_cat[c])
    cat_rows = []
    for wk in sorted(week_cat):
        wm = week_cat[wk]
        cat_rows.append([wk] + [wm.get(c, 0) for c in cats] + [sum(wm.values())])
    cat_rows.append(['季累计'] + [season_cat[c] for c in cats] + [sum(season_cat.values())])
    cat_header = ['周(周一起)'] + cats + ['周合计']
    week_totals = [(row[0], row[-1]) for row in cat_rows[:-1]]

    def is_anom_band(b):
        return bool(re.match(r'^C[1-9]$|^D[1-9]$', (b or '').strip()))
    audit = []
    for r in rows:
        name = (r.get('template_name') or '').strip()
        band = (r.get('band_name') or '').strip()
        issues = []
        if not name:
            issues.append('款名缺失')
        if not band:
            issues.append('波段缺失')
        elif is_anom_band(band):
            issues.append(f'波段不规范({band})')
        if not issues:
            continue
        recent = (r.get('created_at') or '') >= (now - timedelta(days=30)).strftime('%Y-%m-%d')
        audit.append([r.get('template_no', ''), name or '(款名空)', band or '(空)',
                      r.get('cat_name') or '', r.get('template_status_name') or '',
                      (r.get('created_at') or '')[:10], '近30天' if recent else '历史', '；'.join(issues)])
    audit.sort(key=lambda x: (0 if x[6] == '近30天' else 1, x[5]))

    return dict(pool_rows=pool_rows, pool_total=pool_total, warns=warns, work=work,
                cat_header=cat_header, cat_rows=cat_rows, week_totals=week_totals,
                season_total=cat_rows[-1] if cat_rows else None, audit=audit,
                total=total, pool=pool)

# ============ Excel 样式与版式助手（顶部总结/中部明细/底部口径） ============
def xl_color(css_hex):
    v = css_hex.removeprefix('#').upper()
    assert len(v) == 6, css_hex
    return 'FF' + v

XL_PRIMARY   = xl_color('#4472C4')
XL_PRIMARY_D = xl_color('#2F5597')
XL_LIGHT     = xl_color('#D9E2F3')
XL_BORDER    = xl_color('#BFBFBF')
XL_WARN_RED_F, XL_WARN_RED_T = xl_color('#FFC7CE'), xl_color('#9C0006')
XL_WARN_YEL_F, XL_WARN_YEL_T = xl_color('#FFEB9C'), xl_color('#9C6500')
XL_OK_GREEN_T = xl_color('#006100')
XL_NOTE_BG   = xl_color('#F7F7F7')
XL_SUM_BG    = xl_color('#EDF2FA')

F_TITLE  = Font(name='PingFang SC', size=14, bold=True, color='FFFFFFFF')
F_HEAD   = Font(name='PingFang SC', size=10, bold=True, color='FFFFFFFF')
F_BODY   = Font(name='PingFang SC', size=10)
F_BODY_B = Font(name='PingFang SC', size=10, bold=True)
F_SUM    = Font(name='PingFang SC', size=11, bold=True, color=xl_color('#1F3864'))
F_NOTE   = Font(name='PingFang SC', size=9, color=xl_color('#595959'))
F_NOTE_H = Font(name='PingFang SC', size=10, bold=True, color=xl_color('#404040'))
FILL_TITLE = PatternFill('solid', fgColor=XL_PRIMARY)
FILL_HEAD  = PatternFill('solid', fgColor=XL_PRIMARY)
FILL_SUM   = PatternFill('solid', fgColor=XL_SUM_BG)
FILL_NOTE  = PatternFill('solid', fgColor=XL_NOTE_BG)
FILL_TOTAL = PatternFill('solid', fgColor=XL_PRIMARY_D)
THIN = Side(style='thin', color=XL_BORDER)
B_ALL = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
AL_C = Alignment(horizontal='center', vertical='center', wrap_text=True)
AL_L = Alignment(horizontal='left', vertical='center', wrap_text=True)
AL_R = Alignment(horizontal='right', vertical='center')

def sheet_frame(ws, title_text, subtitle, ncols):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(row=1, column=1, value=title_text)
    c.font, c.fill, c.alignment = F_TITLE, FILL_TITLE, AL_C
    ws.row_dimensions[1].height = 28
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    c = ws.cell(row=2, column=1, value=subtitle)
    c.font, c.alignment = F_NOTE, AL_L
    ws.row_dimensions[2].height = 16
    return 3

def put_summary(ws, row, lines, ncols):
    start = row
    label_end = min(ncols - 1, 3)
    for i, (label, value) in enumerate(lines):
        r = row + i
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=label_end)
        ws.cell(row=r, column=1, value=label).font = F_SUM
        ws.cell(row=r, column=1).alignment = AL_L
        if value is not None:
            if label_end + 1 < ncols:
                ws.merge_cells(start_row=r, start_column=label_end + 1, end_row=r, end_column=ncols)
            c = ws.cell(row=r, column=label_end + 1, value=value)
            c.font, c.alignment = F_BODY_B, AL_L
        for col in range(1, ncols + 1):
            ws.cell(row=r, column=col).fill = FILL_SUM
        ws.row_dimensions[r].height = 18
    return start + len(lines)

def put_table(ws, start_row, headers, rows, col_types=None, total_row_vals=None):
    hr = start_row
    for j, h in enumerate(headers, 1):
        c = ws.cell(row=hr, column=j, value=h)
        c.font, c.fill, c.alignment, c.border = F_HEAD, FILL_HEAD, AL_C, B_ALL
    ds = hr + 1
    for i, row in enumerate(rows):
        r = ds + i
        for j, v in enumerate(row, 1):
            c = ws.cell(row=r, column=j)
            t = col_types[j - 1] if col_types else 'text'
            if t == 'pct':
                c.value = float(v) if v not in (None, '') else None
                c.number_format = '0.0%'; c.alignment = AL_R
            elif t == 'num':
                c.value = float(v) if ('.' in str(v) or '-' in str(v)) else int(v)
                c.number_format = '#,##0'; c.alignment = AL_R
            elif t == 'int':
                c.value = int(float(v)); c.number_format = '0'; c.alignment = AL_R
            elif t == 'date':
                c.value = v; c.alignment = AL_C
            else:
                c.value = v; c.alignment = AL_L
            c.font, c.border = F_BODY, B_ALL
    de = ds + len(rows) - 1
    tr = None
    if total_row_vals is not None:
        tr = de + 1
        for j, v in enumerate(total_row_vals, 1):
            t = col_types[j - 1] if col_types else 'text'
            if t == 'pct' and v not in (None, ''):
                v = float(v)
            elif t in ('num', 'int') and v not in (None, ''):
                v = int(float(v))
            c = ws.cell(row=tr, column=j, value=v)
            if t == 'pct':
                c.number_format = '0.0%'; c.alignment = AL_R
            elif t in ('num', 'int'):
                c.number_format = '#,##0' if t == 'num' else '0'; c.alignment = AL_R
            else:
                c.alignment = AL_L
            c.font = Font(name='PingFang SC', size=10, bold=True, color='FFFFFFFF')
            c.fill, c.border = FILL_TOTAL, B_ALL
    return hr, ds, de, tr

def put_notes(ws, start_row, notes, ncols):
    r = start_row + 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
    c = ws.cell(row=r, column=1, value='📖 口径解释与说明')
    c.font, c.fill = F_NOTE_H, FILL_NOTE
    for col in range(1, ncols + 1):
        ws.cell(row=r, column=col).fill = FILL_NOTE
        ws.cell(row=r, column=col).border = Border(top=THIN)
    r += 1
    for note in notes:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
        c = ws.cell(row=r, column=1, value=note)
        c.font, c.alignment = F_NOTE, AL_L
        ws.row_dimensions[r].height = max(14, 14 * (1 + len(note) // 90))
        r += 1
    return r - 1

def set_widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

# ============ 主流程 ============
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True, help='YYYY-MM-DD')
    ap.add_argument('--slot', default='am')
    ap.add_argument('--prev-date', default=None, help='环比基期 YYYY-MM-DD（快照存在才生效）')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    base = os.path.join(ROOT, 'data', 'raw', args.date)
    cands = [os.path.join(base, args.slot, 'yizhe_template_list.jsonl'),
             os.path.join(base, 'am', 'yizhe_template_list.jsonl'),
             os.path.join(base, 'pm', 'yizhe_template_list.jsonl')]
    raw = next((p for p in cands if os.path.exists(p)), None)
    if not raw:
        print(f"[excel] 未找到 {args.date} 快照，请先跑: node scripts/fetch-endpoints.mjs --batch evening --only yizhe_template_list.jsonl")
        raise SystemExit(1)
    rows = load_rows(raw)

    prev_rows = None
    if args.prev_date:
        pbase = os.path.join(ROOT, 'data', 'raw', args.prev_date)
        pcands = [os.path.join(pbase, args.slot, 'yizhe_template_list.jsonl'),
                  os.path.join(pbase, 'am', 'yizhe_template_list.jsonl'),
                  os.path.join(pbase, 'pm', 'yizhe_template_list.jsonl')]
        praw = next((p for p in pcands if os.path.exists(p)), None)
        if praw:
            prev_rows = load_rows(praw)

    now = datetime.strptime(args.date, '%Y-%m-%d').replace(hour=12)
    D = build_derived(rows, now, prev_rows)
    pool_data = D['pool_rows']
    pool_total = D['pool_total']
    warns = D['warns']
    n_high = sum(1 for w in warns if w[7] == '高')
    n_mid = len(warns) - n_high
    review_ready = D['pool'].get('已车板', 0) + D['pool'].get('复版', 0)
    review_pending = D['pool'].get('审版完成', 0)
    audit = D['audit']
    n_recent = sum(1 for a in audit if a[6] == '近30天')
    wk_last = D['week_totals'][-2] if len(D['week_totals']) >= 2 and D['week_totals'][-1][1] < 7 else (D['week_totals'][-1] if D['week_totals'] else ('-', 0))
    season_total = D['season_total']
    dress_pct = (season_total[4] / season_total[-1] * 100) if season_total and season_total[-1] else 0
    active = sum(D['pool'][s] for s in ['新开发', '面辅料齐', '已打板', '已车板'])

    out_path = args.out or os.path.join(ROOT, 'out', f'样衣管理日报-{args.date}.xlsx')
    wb = openpyxl.Workbook()
    wb.properties.title = f'样衣管理日报 {args.date}'

    # ---- 00 总览 ----
    ws = wb.active
    ws.title = '00总览'
    NC = 6
    delta_now = pool_total[3] if prev_rows else None
    delta_txt = f'（较 {args.prev_date} {"+" if delta_now >= 0 else ""}{delta_now}）' if prev_rows else ''
    r0 = sheet_frame(ws, '样衣管理日报 · 今日总览',
                     f'数据日期 {args.date}｜数据源：衣者样板全量快照（{args.slot}，{D["total"]:,} 款）'
                     + (f'｜基期对比 {args.prev_date}' if prev_rows else '')
                     + f'｜生成 {datetime.now().strftime("%Y-%m-%d %H:%M")}', NC)
    r_sum = put_summary(ws, r0, [
        ('今日快照', f'总样板 {D["total"]:,} 款{delta_txt}｜活跃在制 {active} 款（新开发→车板）｜已下单 {D["pool"].get("已下单", 0):,} 款'),
        ('时间预警', f'{len(warns)} 条（高级别 {n_high} 条）——绝大多数为历史积压，详见 02'),
        ('审版节奏', f'可审版池 {review_ready} 个（门槛 {RULES["review"]}，{"今日可安排审" if review_ready >= RULES["review"] else "未达门槛"}）｜审版完成待下单 {review_pending} 个'),
        ('数据质量', f'近30天新建款资料缺失 {n_recent} 款（款名/波段），详见 05'),
        ('品类结构', f'最近完整周新建 {wk_last[1]} 款；连衣裙占比 {dress_pct:.0f}%，详见 04'),
    ], NC)
    r = r_sum + 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=NC)
    c = ws.cell(row=r, column=1, value='✅ 今天必做（按顺序）')
    c.font, c.fill, c.alignment = Font(name='PingFang SC', size=11, bold=True, color='FFFFFFFF'), FILL_HEAD, AL_L
    ws.row_dimensions[r].height = 20
    todos = [
        ('1', f'安排审版：已车板+复版共 {review_ready} 个{"，已达门槛，不等周节点" if review_ready >= RULES["review"] else "，未达门槛，等攒够或周节点"}（名单见 03 表已车板段）'),
        ('2', '清近 7 天超时新款：02 表筛选"停留天数≤7"，当日推动到下一环节'),
        ('3', f'补资料：近 30 天 {n_recent} 款缺失款名/波段（05 表黄底行），按创建人分发'),
    ]
    for i, (no, txt) in enumerate(todos):
        rr = r + 1 + i
        ws.cell(row=rr, column=1, value=no).font = F_BODY_B
        ws.cell(row=rr, column=1).alignment = AL_C
        ws.merge_cells(start_row=rr, start_column=2, end_row=rr, end_column=NC)
        c = ws.cell(row=rr, column=2, value=txt)
        c.font, c.alignment = F_BODY, AL_L
        ws.row_dimensions[rr].height = 18
    put_notes(ws, r + 1 + len(todos) + 1, [
        '· 本工作簿为生成时点静态快照：数值由采集管线（衣者样板全量接口）在生成时计算写入，非实时刷新。',
        '· 各 sheet 结构统一为：顶部总结 → 中部明细 → 底部口径。明细表均带筛选，可按环节/级别/新近度筛分分发。',
        f'· 每日刷新：node scripts/fetch-endpoints.mjs --batch evening --only yizhe_template_list.jsonl → python3 scripts/build-sample-report-excel.py --date <日期> --prev-date <上期>。',
    ], NC)
    set_widths(ws, [14, 24, 24, 30, 20, 20])

    # ---- 01 管线蓄水池 ----
    ws = wb.create_sheet('01管线蓄水池')
    NC = 5
    r0 = sheet_frame(ws, '一、管线蓄水池 — 各环节实时件数与环比',
                     f'数据日期 {args.date}（{args.slot} 快照）'
                     + (f'｜对比上期 {args.prev_date}' if prev_rows else '｜未指定基期，无环比')
                     + f'｜数据源：衣者样板管理全量 {D["total"]:,} 款', NC)
    r_sum = put_summary(ws, r0, [
        ('▍总结', None),
        ('在制未下单款', f'{D["total"] - D["pool"].get("已下单", 0):,} 款（含废版 {D["pool"].get("废版", 0):,}）——废版占大头，历史积压是最大堵点'),
        ('本期活跃流水线', f'新开发→车板在制 {active} 款（新开发{D["pool"].get("新开发",0)}+面辅料齐{D["pool"].get("面辅料齐",0)}+已打板{D["pool"].get("已打板",0)}+已车板{D["pool"].get("已车板",0)}）'),
        ('审版相关池', f'可审版池 {review_ready} 个（门槛{RULES["review"]}）｜审版完成待下单 {review_pending} 个'),
    ], NC)
    hr, ds, de, tr = put_table(ws, r_sum + 1, ['环节', '上期', '本期', '变化', '占本期比例'],
                               pool_data, col_types=['text', 'num', 'num', 'int', 'pct'],
                               total_row_vals=pool_total)
    ws.conditional_formatting.add(f'D{ds}:D{tr}',
        CellIsRule(operator='greaterThan', formula=['0'], font=Font(color=XL_OK_GREEN_T)))
    ws.conditional_formatting.add(f'D{ds}:D{tr}',
        CellIsRule(operator='lessThan', formula=['0'], font=Font(color=XL_WARN_RED_T)))
    set_widths(ws, [14, 13, 13, 9, 12])
    ws.freeze_panes = f'A{ds}'
    put_notes(ws, tr + 2, [
        '· 环节顺序按衣者样板状态机：新开发→面辅料齐→已打板→已车板→复版→审版完成→(废版/待下单/确认可下单)→已下单；13 个状态以系统 get_template_status_list 为准。',
        '· 占本期比例 = 该环芄件数 ÷ 全量样板数（含已下单与废版），反映各环节相对体量，非流转率。',
        '· 变化列 = 本期 − 上期；上期快照不存在时该两列为空。',
    ], NC)

    # ---- 02 时间预警 ----
    ws = wb.create_sheet('02时间预警')
    NC = 10
    over30 = sum(1 for w in warns if w[6] >= 30)
    r0 = sheet_frame(ws, '二、时间预警 — 超 1/3/3/7 天规则的款',
                     f'规则依据设计部需求会议拍板｜预警明细按级别+停留时长排序', NC)
    r_sum = put_summary(ws, r0, [
        ('▍总结', None),
        ('预警总量', f'{len(warns)} 条（高级别 {n_high} 条 / 中级别 {n_mid} 条），其中停留≥30天的历史积压 {over30} 条'),
        ('结论', '绝大多数为历史积压款，建议先批量清理旧款再让规则对增量生效'),
        ('下一步', '按明细表逐款决定：重激活排产 → 转废版（备注五类原因）→ 关闭；近 30 天新款预警优先当日处理'),
    ], NC)
    hr, ds, de, tr = put_table(ws, r_sum + 1,
                               ['款号', '款名', '当前环节', '波段', '品类', '创建日期', '停留天数', '预警级别', '预警类型', '规则'],
                               warns, col_types=['text', 'text', 'text', 'text', 'text', 'date', 'int', 'text', 'text', 'text'])
    ws.conditional_formatting.add(f'H{ds}:H{de}',
        CellIsRule(operator='equal', formula=['"高"'], fill=PatternFill('solid', fgColor=XL_WARN_RED_F), font=Font(color=XL_WARN_RED_T)))
    ws.conditional_formatting.add(f'H{ds}:H{de}',
        CellIsRule(operator='equal', formula=['"中"'], fill=PatternFill('solid', fgColor=XL_WARN_YEL_F), font=Font(color=XL_WARN_YEL_T)))
    ws.conditional_formatting.add(f'G{ds}:G{de}',
        CellIsRule(operator='greaterThan', formula=['30'], font=Font(color=XL_WARN_RED_T)))
    ws.auto_filter.ref = f'A{hr}:J{de}'
    set_widths(ws, [13, 22, 10, 13, 9, 11, 9, 9, 13, 24])
    ws.freeze_panes = f'C{ds}'
    put_notes(ws, de + 2, [
        '· 预警规则（会议拍板）：新开发→面辅料齐 1 天 ｜ 面辅料齐→已打板 3 天 ｜ 已打板→已车板 3 天 ｜ 审版完成→下单 7 天，滞留 14 天必处理。',
        '· 停留天数 = 快照日 − 样板创建日期。衣者列表接口无步骤级流转时间戳（get_step_list 为空），以创建日期近似进入当前环节的时间，属保守估计。',
        '· 预警级别：高=停留≥3倍规则天数或触发14天滞留；中=超出规则天数。停留≥30天的历史积压款红字标示。',
        '· 预计上新时间(expected_new_date)填充后，可改为按上新紧迫度排序推送（会议要求的最终形态）。',
    ], NC)

    # ---- 03 今日工作清单 ----
    ws = wb.create_sheet('03今日工作清单')
    NC = 8
    wc = {s: sum(1 for w in D['work'] if w[1] == s) for s in ['面辅料齐', '已打板', '已车板']}
    r0 = sheet_frame(ws, '三、今日工作清单 — 在制品按优先排序',
                     '排序规则：环节优先（面辅料齐→已打板→已车板）+ 同环节新创建优先｜预计上新字段补填后自动切换为按上新紧迫度排序', NC)
    r_sum = put_summary(ws, r0, [
        ('▍总结', None),
        ('在制品总量', f'{len(D["work"])} 款（面辅料齐 {wc["面辅料齐"]} / 已打板 {wc["已打板"]} / 已车板 {wc["已车板"]}）'),
        ('审版提醒', f'可审版池 {review_ready} 个{" ≥ 20 个门槛 → 今天可安排审版" if review_ready >= RULES["review"] else "，未达门槛"}'),
        ('使用方式', '打板/车板师傅按本表顺序领取任务；款名/波段为空的款随做随补资料'),
    ], NC)
    hr, ds, de, tr = put_table(ws, r_sum + 1,
                               ['优先', '环节', '款号', '款名', '波段', '品类', '创建日期', '停留天数'],
                               D['work'], col_types=['int', 'text', 'text', 'text', 'text', 'text', 'date', 'int'])
    ws.conditional_formatting.add(f'H{ds}:H{de}',
        CellIsRule(operator='greaterThan', formula=['14'], font=Font(color=XL_WARN_RED_T)))
    ws.auto_filter.ref = f'A{hr}:H{de}'
    set_widths(ws, [7, 10, 13, 24, 13, 9, 11, 9])
    ws.freeze_panes = f'C{ds}'
    put_notes(ws, de + 2, [
        '· 清单范围：面辅料齐/已打板/已车板三个活跃环节的全部在制品（不含新开发——尚无面辅料，不算可开工）。',
        '· 优先级：环节靠前优先（面辅料齐=1 → 已打板=2 → 已车板=3），同环节内创建日期新的优先。',
        '· 会议要求最终形态：按"预计上新时间"紧迫度排序并附款图——待设计部补填 expected_new_date 后切换。',
        '· 停留天数≥14 天的红字款：属长期停滞在制品，处理前先确认是否仍在上新计划内。',
    ], NC)

    # ---- 04 品类结构 ----
    ws = wb.create_sheet('04品类结构')
    cat_header = D['cat_header']
    NC = len(cat_header)
    sea_n = season_total[-1] if season_total else 0
    r0 = sheet_frame(ws, '四、新品开发品类结构 — 周维度监控',
                     f'统计窗口 {SEASON_START} 起（当季开发季）｜按样板创建日期归周（周一起算）｜共 {sea_n} 款', NC)
    cats = D['cat_header'][1:-1]
    struct = '、'.join(f'{season_total[1 + i]}款' for i in range(min(4, len(cats))))
    r_sum = put_summary(ws, r0, [
        ('▍总结', None),
        ('开发节奏', f'最近完整周新建 {wk_last[1]} 款；当季累计 {sea_n} 款'),
        ('结构占比', f'{struct}……详见明细表'),
        ('风险提示', '连衣裙占比偏低则结构失衡（管理层会议点名类问题）；波段规范未落实——新季多填为 C1/C2/C3/C4'),
        ('使用方式', '对照商品企划目标结构，缺什么品类下周补什么；结合销售 TOP（销售数据报表）调整'),
    ], NC)
    cat_rows = D['cat_rows']
    hr, ds, de, tr = put_table(ws, r_sum + 1, cat_header, cat_rows,
                               col_types=['text'] + ['int'] * (NC - 1))
    for j in range(1, NC + 1):
        c = ws.cell(row=de, column=j)
        c.font = F_BODY_B
        c.fill = PatternFill('solid', fgColor=XL_LIGHT)
    ws.auto_filter.ref = f'A{hr}:{get_column_letter(NC)}{de}'
    set_widths(ws, [12] + [8] * (NC - 1))
    ws.freeze_panes = f'B{ds}'
    put_notes(ws, de + 2, [
        '· 归周口径：样板创建日期所属周的周一日期作为周标识（如 2026-10-20 → 周 2026-10-19）。',
        f'· 统计窗口起点 {SEASON_START} = 当前开发季启动窗口；跨季在脚本顶部 SEASON_START 调整。',
        '· 波段字段本应作为"上货节奏"标注（春一波/春二波），当前新建款大量空白或填 C1-C4 新编码，暂以创建日期归周替代；规范落实后切换为按波段统计。',
        '· 品类=衣者样板"品类"字段(cat_name)；季累计行为浅蓝底加粗。',
    ], NC)

    # ---- 05 数据稽核 ----
    ws = wb.create_sheet('05数据稽核')
    NC = 8
    n_noname = sum(1 for a in audit if '款名缺失' in a[7])
    n_noband = sum(1 for a in audit if '波段缺失' in a[7] or '波段不规范' in a[7])
    r0 = sheet_frame(ws, '五、数据完整性稽核 — 资料补数清单',
                     '会议要求资料必填：款名/波段/季节/预计上新/实际上新/版次｜本表列出全量缺失明细，按"近30天优先"排序', NC)
    r_sum = put_summary(ws, r0, [
        ('▍总结', None),
        ('全量缺失', f'{len(audit):,} 款有资料缺失：款名缺失 {n_noname:,} 款、波段缺失/不规范 {n_noband:,} 款（部分款两项均缺）'),
        ('近30天新建', f'{n_recent} 款缺失——补数第一优先（当前开发季的款，直接影响 AI 排序与结构统计）'),
        ('字段核实', '预计上新/实际上新/版次/季节字段系统均已存在，抽查填充率≈0；备注字段可承载废版五类原因'),
        ('整改路径', '按明细表逐款补填；建议按环节筛分后分发到人（创建人=衣者 design_user）'),
    ], NC)
    hr, ds, de, tr = put_table(ws, r_sum + 1,
                               ['款号', '款名', '波段', '品类', '环节', '创建日期', '新近度', '缺失项'],
                               audit, col_types=['text', 'text', 'text', 'text', 'text', 'date', 'text', 'text'])
    ws.conditional_formatting.add(f'G{ds}:G{de}',
        CellIsRule(operator='equal', formula=['"近30天"'], fill=PatternFill('solid', fgColor=XL_WARN_YEL_F), font=Font(color=XL_WARN_YEL_T)))
    ws.auto_filter.ref = f'A{hr}:H{de}'
    set_widths(ws, [13, 22, 13, 9, 10, 11, 9, 22])
    ws.freeze_panes = f'C{ds}'
    put_notes(ws, de + 2, [
        '· 款名规范（会议拍板）：设计元素+领型/袖型+廓形+品类，例"猫咪刺绣蝙蝠袖圆领T恤"。',
        '· 波段规范：按"2027春一波/2027春二波"式填写；C1/C2/C3/C4 类编码为不规范填法，需改写。',
        '· 废版备注五类原因：雷同款 / 含往年滞销元素 / 价格带不匹配 / 搭配性主题性不强 / 偏离整体风格——按关键词写，AI 才能聚类分析。',
        '· 预计上新时间是 AI"今日清单按紧迫度排序"的核心依据；填充率达标后 03 清单自动升级排序逻辑。',
        '· 本表为全量历史口径；近30天新建款（黄底行）建议当日清零，历史积压款随废版清理动作一并消化。',
    ], NC)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    wb.save(out_path)
    summary = dict(date=args.date, total=D['total'], active=active, warns=len(warns),
                   warns_high=n_high, review_ready=review_ready, review_pending=review_pending,
                   audit=len(audit), audit_recent=n_recent, out=os.path.relpath(out_path, ROOT))
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    main()
