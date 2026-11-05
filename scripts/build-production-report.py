#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生产监控日报生成器（会议规则版）—— scm-collector V2.3 新增链路
================================================================
输入：data/raw/<日期>/<槽>/ 下由 fetch-endpoints.mjs --batch first 采集的衣者真实数据
  - yizhe_production_list.jsonl  生产订单（147级别，在产）
  - yizhe_cuted_records.jsonl    裁床记录（按生产单汇总为裁床数）
  - yizhe_material_store.jsonl   物料库存（主料+辅料结存）
  - yizhe_factory_list.jsonl     工厂列表
输出：out/生产监控日报_<日期>.xlsx（5 sheet，每个 sheet = 汇总(上) + 明细(中) + 口径说明(下)）

规则来源：2026-10-23 生产需求会议（老板拍板），规则全文见 references/生产监控口径.md
迁移性：仅相对路径 + 本地时间，无任何机器特定路径；换设备登录衣者后跑同一条命令即得相同结果。

用法（在 skill 根目录执行）：
  node scripts/fetch-endpoints.mjs --batch first --date <YYYY-MM-DD> \
      --only yizhe_production_list.jsonl,yizhe_cuted_records.jsonl,yizhe_material_store.jsonl,yizhe_factory_list.jsonl
  python3 scripts/build-production-report.py --date <YYYY-MM-DD> [--slot am]

依赖：python3 + openpyxl（无其他第三方依赖）
"""
import json, os, argparse, sys
from collections import defaultdict, Counter
from datetime import date, timedelta, datetime as dt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # skill 根目录
DATA_HOME = os.environ.get('SCM_DATA_HOME') or os.path.join(os.path.expanduser('~'), 'WorkBuddy', 'scm-collector-data')  # 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖

# ============================================================
# D5 可配置参数（会议拍板；修改需留痕到 out/param-changes.log）
# ============================================================
PARAMS = {
    "qty_threshold": 0.01,        # A2 数量偏差阈值 1%
    "qty_exempt": 2,              # 正常损耗豁免件数（差≤2件不计预警）
    "overdue_tolerance": 0,       # B3 出货多出容差（零容差）
    "lead_days": 7,               # C1 货期基准天数（裁床开工+7天兜底）
    "near_days": 2,               # 临期提醒天数
    "fac_over_red": 5,            # 工厂逾期≥N单 = 红·重点关注
    "material_surplus_min": 50,   # 主料剩余≥N单位 = 可复用
}

def load_params():
    """可选覆盖：config/production-params.json 存在则合并（迁移设备后无需改动脚本）"""
    p = os.path.join(ROOT, 'config', 'production-params.json')
    if os.path.exists(p):
        try:
            PARAMS.update(json.load(open(p, encoding='utf-8')))
            print("[params] 已加载 config/production-params.json 覆盖")
        except Exception as e:
            print("[params] 覆盖文件解析失败，用默认:", e)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True, help='YYYY-MM-DD')
    ap.add_argument('--slot', default='am', choices=['am','pm'])
    args = ap.parse_args()
    load_params()

    base = os.path.join(DATA_HOME, 'data', 'raw', args.date, args.slot)
    def rp(name): return os.path.join(base, name)
    missing = [f for f in ('yizhe_production_list.jsonl','yizhe_cuted_records.jsonl','yizhe_material_store.jsonl') if not os.path.exists(rp(f))]
    if missing:
        print("缺少采集文件:", missing)
        print("请先执行: node scripts/fetch-endpoints.mjs --batch first --date %s --slot %s --only %s" % (
            args.date, args.slot, ','.join(m.replace('.jsonl','') for m in missing)))
        sys.exit(2)

    prod = [json.loads(l) for l in open(rp('yizhe_production_list.jsonl'), encoding='utf-8')]
    cut  = [json.loads(l) for l in open(rp('yizhe_cuted_records.jsonl'), encoding='utf-8')]
    mat  = [json.loads(l) for l in open(rp('yizhe_material_store.jsonl'), encoding='utf-8')]
    TODAY = dt.strptime(args.date, '%Y-%m-%d').date()
    def num(x): return x['value'] if isinstance(x, dict) else (x or 0)

    TH, EXEMPT = PARAMS["qty_threshold"], PARAMS["qty_exempt"]
    LEAD, NEAR = PARAMS["lead_days"], PARAMS["near_days"]

    cutmap = defaultdict(int)
    for c in cut: cutmap[c['production_id']] += c.get('cuted_num') or 0

    # ---- D-1 数量比对 ----
    rows_qty = []
    for p in sorted(prod, key=lambda x: x['production_sn']):
        cn, on = cutmap.get(p['production_id'], 0), num(p['stock_out_num'])
        if not cn: continue
        d2 = on - cn; r2 = d2/cn
        if d2 > PARAMS["overdue_tolerance"]: st, tier = "多出 %+-d 件（零容差）" % d2, "红·多出"
        elif d2 < 0 and abs(d2) > EXEMPT and abs(r2) > TH: st, tier = "少出 %+-d 件（%.1f%%）" % (d2, r2*100), "红·少出"
        elif d2 < 0: st, tier = "正常损耗 %+-d 件" % d2, "灰·豁免"
        else: st, tier = "对平", "绿·正常"
        rows_qty.append([p['production_sn'], p['template_no'], p.get('factory_name') or '—', cn, on, d2, (r2 if cn else ''), tier, st])
    n_multi = len([r for r in rows_qty if r[7]=="红·多出"]); n_under = len([r for r in rows_qty if r[7]=="红·少出"])
    n_gray  = len([r for r in rows_qty if r[7]=="灰·豁免"]); n_ok    = len([r for r in rows_qty if r[7]=="绿·正常"])

    # ---- D-2 货期 ----
    rows_due = []
    no_due_cnt = 0
    for p in prod:
        est = p.get('estimated_finish_time'); cb = p.get('cuted_begin_time'); fb = ""
        if est:
            try: due = dt.strptime(est[:10], '%Y-%m-%d').date()
            except: continue
        elif cb: due = dt.strptime(cb[:10], '%Y-%m-%d').date() + timedelta(days=LEAD); fb = "裁床开工+%d天兜底" % LEAD
        else: no_due_cnt += 1; continue
        if num(p['stock_out_num']) >= p['plan_total_num']: continue
        left = (due - TODAY).days
        if left < 0: tier, st = "红·逾期", "逾期 %d 天" % (-left)
        elif left <= NEAR: tier, st = "黄·临期", "临期"
        else: continue
        rows_due.append([p['production_sn'], p['template_no'], p.get('factory_name') or '—', p['plan_total_num'], num(p['stock_out_num']), due.strftime('%Y-%m-%d'), left, tier, st, fb])
    rows_due.sort(key=lambda r: r[6])
    n_over = len([r for r in rows_due if r[7]=="红·逾期"]); n_near = len([r for r in rows_due if r[7]=="黄·临期"])

    # ---- D-4 工厂负荷 ----
    fac = defaultdict(lambda: {'orders':0,'plan':0,'cut':0,'out':0,'over':0})
    for p in prod:
        fn = p.get('factory_name') or '未分厂'; d = fac[fn]
        d['orders']+=1; d['plan']+=p['plan_total_num']; d['cut']+=num(p['cuted_num']); d['out']+=num(p['stock_out_num'])
    for r in rows_due:
        if r[7]=="红·逾期" and (r[2] in fac): fac[r[2]]['over'] += 1
    rows_fac = []
    for fn, d in sorted(fac.items(), key=lambda kv:-kv[1]['plan']):
        cr = d['out']/d['plan'] if d['plan'] else 0
        tier = "红·重点关注" if d['over']>=PARAMS["fac_over_red"] else ("黄·有逾期" if d['over']>0 else "绿·正常")
        rows_fac.append([fn, d['orders'], d['plan'], d['cut'], d['out'], d['over'], cr, tier])

    # ---- D-5 物料 ----
    neg = [m for m in mat if float(m.get('total_gap_num') or 0) < 0 or float(m.get('gap') or 0) < 0]
    neg.sort(key=lambda m: float(m.get('total_gap_num') or 0))
    surplus = [m for m in mat if float(m.get('total_gap_num') or 0) > 0 and m.get('material_type')==1 and float(m.get('total_gap_num') or 0) >= PARAMS["material_surplus_min"]]
    surplus.sort(key=lambda m: -float(m.get('total_gap_num') or 0))

    # ================= Excel 渲染 =================
    F_TITLE=Font(name='PingFang SC',size=14,bold=True,color='1F2328'); F_SEC=Font(name='PingFang SC',size=12,bold=True,color='FFFFFF')
    F_HDR=Font(name='PingFang SC',size=10.5,bold=True,color='374151'); F_TXT=Font(name='PingFang SC',size=10.5,color='1F2328')
    F_MUT=Font(name='PingFang SC',size=9.5,color='9CA3AF'); F_NUM=Font(name='PingFang SC',size=11,bold=True,color='2563EB')
    F_BIG=Font(name='PingFang SC',size=16,bold=True,color='DC2626'); F_AMBB=Font(name='PingFang SC',size=16,bold=True,color='B45309')
    FILL_SEC=PatternFill('solid',fgColor='2563EB'); FILL_KQ=PatternFill('solid',fgColor='6B7280'); FILL_HDR=PatternFill('solid',fgColor='EFF3F8')
    FILL_RED=PatternFill('solid',fgColor='FEF2F2'); FILL_AMB=PatternFill('solid',fgColor='FFFBEB'); FILL_GRN=PatternFill('solid',fgColor='ECFDF5'); FILL_GRY=PatternFill('solid',fgColor='F9FAFB')
    FILL_KPI=PatternFill('solid',fgColor='F6F7F9')
    THIN=Border(bottom=Side(style='thin',color='E5E7EB'))
    AL_C=Alignment(horizontal='center',vertical='center'); AL_L=Alignment(horizontal='left',vertical='center',wrap_text=True); AL_R=Alignment(horizontal='right',vertical='center')
    TIERS={"红":FILL_RED,"黄":FILL_AMB,"绿":FILL_GRN,"灰":FILL_GRY}
    DISPLAY={"红·多出":"🔴 多出","红·少出":"🔴 少出","灰·豁免":"⚪ 正常损耗","绿·正常":"✅ 正常","红·逾期":"🔴 逾期","黄·临期":"🟡 临期","红·重点关注":"🔴 重点关注","黄·有逾期":"🟡 有逾期","红·负结存":"🔴 负结存","黄·可复用":"🟡 可复用"}
    TF_RED=Font(name='PingFang SC',size=10.5,bold=True,color='DC2626'); TF_AMB=Font(name='PingFang SC',size=10.5,bold=True,color='B45309')
    TF_GRN=Font(name='PingFang SC',size=10.5,bold=True,color='047857'); TF_GRY=Font(name='PingFang SC',size=10.5,color='6B7280')
    TIER_FONT={"红":TF_RED,"黄":TF_AMB,"绿":TF_GRN,"灰":TF_GRY}
    def tier_fill(t): return TIERS.get(str(t)[:1])

    wb=Workbook()
    def sec_header(ws,row,text,ncols,fill=FILL_SEC):
        ws.merge_cells(start_row=row,start_column=1,end_row=row,end_column=ncols)
        c=ws.cell(row=row,column=1,value=text); c.font=F_SEC; c.fill=fill; c.alignment=AL_L; return row+1
    def write_table(ws,row,headers,rows,tier_col=None,num_cols=(),pct_cols=(),add_filter=False):
        hdr_row=row
        for j,h in enumerate(headers,1):
            c=ws.cell(row=row,column=j,value=h); c.font=F_HDR; c.fill=FILL_HDR; c.alignment=AL_C; c.border=THIN
        row+=1
        for r in rows:
            fill=tier_fill(r[tier_col]) if tier_col is not None else None
            for j,v in enumerate(r,1):
                c=ws.cell(row=row,column=j,value=v); c.font=F_TXT; c.border=THIN
                c.alignment=AL_R if j in num_cols or j in pct_cols else AL_L
                if j in pct_cols and isinstance(v,float): c.number_format='0.0%'
                if fill: c.fill=fill
                if tier_col is not None and j-1==tier_col:
                    c.value=DISPLAY.get(str(v),str(v)); c.font=TIER_FONT.get(str(v)[:1],F_TXT); c.alignment=AL_C
            row+=1
        if add_filter and rows: ws.auto_filter.ref="A%d:%s%d"%(hdr_row,get_column_letter(len(headers)),row-1)
        return row
    def kpi_block(ws,row,items):
        col=1
        for label,val,note,big in items:
            for rr in (row,row+1,row+2):
                ws.merge_cells(start_row=rr,start_column=col,end_row=rr,end_column=col+2)
                for cc in range(col,col+3): ws.cell(row=rr,column=cc).fill=FILL_KPI
            c1=ws.cell(row=row,column=col,value=label); c1.font=Font(name='PingFang SC',size=10,color='6B7280'); c1.alignment=AL_L
            c2=ws.cell(row=row+1,column=col,value=val); c2.font=big or F_NUM; c2.alignment=AL_L
            c3=ws.cell(row=row+2,column=col,value=note); c3.font=F_MUT; c3.alignment=AL_L
            col+=3
        return row+3
    def legend_line(ws,row,text,ncols):
        ws.merge_cells(start_row=row,start_column=1,end_row=row,end_column=ncols)
        c=ws.cell(row=row,column=1,value=text); c.font=Font(name='PingFang SC',size=9.5,italic=True,color='6B7280'); c.alignment=AL_L; return row+1
    def koujing_block(ws,row,lines,ncols):
        row=sec_header(ws,row,"口径与统计说明",ncols,FILL_KQ)
        for tag,txt in lines:
            ws.merge_cells(start_row=row,start_column=1,end_row=row,end_column=ncols)
            c=ws.cell(row=row,column=1,value="【%s】%s"%(tag,txt)); c.font=Font(name='PingFang SC',size=9.5,color='4B5563'); c.alignment=AL_L
            ws.row_dimensions[row].height=26; row+=1
        return row

    ws=wb.active; ws.title="总览"; ws.sheet_view.showGridLines=False
    for j in range(1,10): ws.column_dimensions[get_column_letter(j)].width=13
    ws.merge_cells('A1:I1'); c=ws.cell(1,1,"生产监控日报 · %s（数据来源：衣者ERP 直连采集）"%args.date); c.font=F_TITLE
    r=legend_line(ws,2,"图例：🔴 需处理 ｜ 🟡 关注 ｜ ⚪ 正常损耗（差异≤%d件豁免）｜ ✅ 正常 —— 各明细页行底色与档位同义"%EXEMPT,9)
    r=3
    r=sec_header(ws,r,"一、今日速览",9)
    r=kpi_block(ws,r,[
        ("数量异常（裁床↔出货）",n_multi+n_under,"多出 %d 单 · 少出 %d 单"%(n_multi,n_under),F_BIG),
        ("货期逾期（未出足）",n_over,"另有临期 %d 单"%n_near,F_BIG),
        ("辅料负结存",len(neg),"领用超采购，疑记录错误/流失",F_BIG),
        ("主料剩余可复用",len(surplus),"剩余量≥%d 单位"%PARAMS["material_surplus_min"],F_NUM),
        ("在产订单",len(prod),"计划 %s 件"%format(sum(p['plan_total_num'] for p in prod),','),F_NUM),
    ])
    r=sec_header(ws,r,"二、分级统计",9)
    r=write_table(ws,r,["监控模块","🔴 异常","🟡 关注","⚪ 豁免","✅ 正常","合计","说明"],[
        ["裁床数↔出货数",n_multi+n_under,0,n_gray,n_ok,n_multi+n_under+n_gray+n_ok,"多出零容差；少出>1%且>2件"],
        ["货期（未出足订单）",n_over,n_near,0,0,n_over+n_near,"预计完工日优先，缺省开工+%d天"%LEAD],
        ["工厂负荷",len([x for x in rows_fac if x[7].startswith('红')]),len([x for x in rows_fac if x[7].startswith('黄')]),0,len([x for x in rows_fac if x[7].startswith('绿')]),len(rows_fac),"按逾期单数分档（≥%d红/≥1黄）"%PARAMS["fac_over_red"]],
        ["辅料结存",len(neg),0,0,0,len(neg),"结存为负即红"],
        ["主料剩余",0,len(surplus),0,0,len(surplus),"≥%d单位列示"%PARAMS["material_surplus_min"]],
    ],num_cols=(2,3,4,5,6))
    r+=1
    r=sec_header(ws,r,"三、今日最需处理 TOP5（按逾期天数）",9)
    r=write_table(ws,r,["类型","生产单/款号","工厂","关键数字","建议动作"],
        [["货期","%s（%s）"%(x[1],x[0]),x[2],"应完工 %s，已逾期 %d 天，出 %s/%s"%(x[5],-x[6],x[4],x[3]),"催出货/问原因"] for x in rows_due[:5]])
    r+=1
    r=koujing_block(ws,r,[
        ("数据来源","衣者ERP 直连 API 采集；生产订单 %d 单、裁床记录 %d 条、物料库存 %d 条。"%(len(prod),len(cut),len(mat))),
        ("时间口径","今日=%s；逾期=应完工日<今日 且 出货数<计划数；临期=剩余≤%d天。"%(args.date,NEAR)),
        ("规则来源","2026-10-23 生产需求会议（老板拍板参数），详见 references/生产监控口径.md。"),
        ("已开工口径","已开工=有裁床记录的生产单（%d/%d）；未开工单无比对基准，不进 D-1。"%(len(rows_qty),len(prod))),
        ("未纳入模块","采购数↔裁床数（预裁数字段未回填完整，待老板确认口径）；次品（多客次品仓接口未接入，待生产对接人确认）；辅料损耗率（标准未定）。"),
    ],9)

    ws2=wb.create_sheet("①数量比对(裁床vs出货)"); ws2.sheet_view.showGridLines=False
    for j,w in enumerate([16,15,12,9,9,9,10,14,24],1): ws2.column_dimensions[get_column_letter(j)].width=w
    ws2.merge_cells('A1:I1'); c=ws2.cell(1,1,"D-1 · 裁床数 ↔ 出货数 比对"); c.font=F_TITLE
    r=legend_line(ws2,2,"图例：🔴 多出（零容差）/ 少出（>1%%且>2件）＝需处理 ｜ ⚪ 正常损耗＝差异≤%d件豁免 ｜ ✅ 对平 ｜ 表头可点击筛选"%EXEMPT,9); r=3
    r=sec_header(ws2,r,"汇总",9)
    n_total=len(rows_qty)
    r=kpi_block(ws2,r,[
        ("红色异常",n_multi+n_under,"多出 %d · 少出 %d"%(n_multi,n_under),F_BIG),
        ("正常损耗豁免",n_gray,"差≤%d件不计预警"%EXEMPT,F_NUM),
        ("完全对平",n_ok,"裁=出",F_NUM),
        ("已开工订单",n_total,"占在产 %d%%"%(n_total*100//len(prod) if prod else 0),F_NUM),
    ])
    r=sec_header(ws2,r,"明细（共 %d 单已开工，红行=需处理）"%n_total,9)
    r=write_table(ws2,r,["生产单号","款号","工厂","裁床数","出货数","差异(件)","差异率","档位","状态说明"],rows_qty,tier_col=7,num_cols=(4,5,6),pct_cols=(7,),add_filter=True)
    r+=1
    r=koujing_block(ws2,r,[
        ("比对基准","裁床数=衣者裁床记录(cuted_order_panel)按生产单汇总；出货数=生产单 stock_out_num。"),
        ("多出判定","出货数>裁床数即预警，零容差（老板：裁多少出多少，多出必有问题）→ 需工厂书面解释并留痕。"),
        ("少出判定","差异率>%.0f%% 且 差异>%d件；差≤%d件视为正常损耗（调机/坯布头），豁免不预警。"%(TH*100,EXEMPT,EXEMPT)),
        ("阈值参数","阈值为后台可配置参数（config/production-params.json），修改需留痕。"),
        ("统计","🔴 多出 %d 单（合计多 %d 件）；🔴 少出 %d 单；⚪ 正常损耗 %d 单；✅ 对平 %d 单。"%(n_multi,sum(r[5] for r in rows_qty if r[7]=="红·多出"),n_under,n_gray,n_ok)),
        ("已知噪音","约50%缺口单疑似分批出货未录全，建议跟单先核对系统录入再追责工厂。"),
    ],9)

    ws3=wb.create_sheet("②货期预警"); ws3.sheet_view.showGridLines=False
    for j,w in enumerate([16,15,12,9,9,12,9,12,10,16],1): ws3.column_dimensions[get_column_letter(j)].width=w
    ws3.merge_cells('A1:J1'); c=ws3.cell(1,1,"D-2 · 货期预警（逾期 + 临期）"); c.font=F_TITLE
    r=legend_line(ws3,2,"图例：🔴 逾期（应完工日已过且未出足）＝需处理 ｜ 🟡 临期（剩余≤%d天）｜ 口径：预计完工日优先，缺省裁床开工+%d天"%(NEAR,LEAD),10); r=3
    r=sec_header(ws3,r,"汇总",10)
    r=kpi_block(ws3,r,[
        ("逾期（未出足）",n_over,"红档",F_BIG),
        ("临期（≤%d天）"%NEAR,n_near,"黄档",F_AMBB),
        ("有预计完工日",sum(1 for p in prod if p.get('estimated_finish_time')),"/ %d 单"%len(prod),F_NUM),
        ("兜底+%d天启用"%LEAD,len([r for r in rows_due if r[9]]),"无预计日自动算",F_NUM),
    ])
    r=sec_header(ws3,r,"明细（共 %d 单，按剩余天数升序）"%len(rows_due),10)
    r=write_table(ws3,r,["生产单号","款号","工厂","计划件","已出","应完工日","剩余天数","档位","状态","口径"],rows_due,tier_col=7,num_cols=(4,5,7),add_filter=True)
    r+=1
    worst = rows_due[0] if rows_due else None
    r=koujing_block(ws3,r,[
        ("应完工日判定","优先取衣者预计完工时间；缺失时按 裁床开工日+%d个自然日 兜底（老板会议原话：面料到工厂后7天）。"%LEAD),
        ("逾期定义","应完工日<今日 且 出货数<计划数（已出足的自动排除，避免误报）。"),
        ("重复预警","正式版每24小时重推一次未关闭逾期项（本表为当日快照）。"),
        ("统计","🔴 逾期 %d 单；🟡 临期 %d 单。%s"%(n_over,n_near,("最久：%s@%s %d 天。"%(worst[1],worst[2],-worst[6])) if worst else "")),
        ("数据建议","%d 单中 %d 单无预计完工日，建议跟单补录，兜底仅作过渡。"%(len(prod),no_due_cnt)),
    ],10)

    ws4=wb.create_sheet("③工厂负荷"); ws4.sheet_view.showGridLines=False
    for j,w in enumerate([14,9,10,10,10,9,11,14],1): ws4.column_dimensions[get_column_letter(j)].width=w
    ws4.merge_cells('A1:H1'); c=ws4.cell(1,1,"D-4 · 工厂负荷看板（在产）"); c.font=F_TITLE
    r=legend_line(ws4,2,"图例：🔴 逾期≥%d单＝重点关注 ｜ 🟡 有逾期 ｜ ✅ 正常 ｜ 建议新单避开红档工厂"%PARAMS["fac_over_red"],8); r=3
    r=sec_header(ws4,r,"汇总",8)
    zero_out=len([x for x in rows_fac if x[4]==0 and x[3]>0])
    top=rows_fac[0] if rows_fac else ("—",0,0,0,0,0,0,"")
    hengsheng=[x for x in rows_fac if x[6]>0.9 and x[1]>=10]
    r=kpi_block(ws4,r,[
        ("在产工厂",len(rows_fac),"含未分厂",F_NUM),
        ("最大负荷",top[0],"%d 单 / %s 件"%(top[1],format(top[2],',')),F_BIG),
        ("零出货工厂",zero_out,"已裁未出，需核查",F_AMBB),
        ("高负荷高逾期",len(hengsheng),"完成率>90%且≥10单，排产避开",F_BIG),
    ])
    r=sec_header(ws4,r,"明细（按计划件数降序）",8)
    r=write_table(ws4,r,["工厂","在产单","计划件","已裁","已出","逾期单","出货完成率","档位"],rows_fac,tier_col=7,num_cols=(2,3,4,5,6),pct_cols=(7,),add_filter=True)
    r+=1
    r=koujing_block(ws4,r,[
        ("负荷口径","在产单=生产订单列表(状态进行中/未开始)；完成率=已出货÷计划件数；逾期单=该厂名下货期红档单数。"),
        ("分档规则","逾期≥%d单=🔴 重点关注；1-%d单=🟡 有逾期；0=✅ 正常（会议规则：看负荷松紧排新单）。"%(PARAMS["fac_over_red"],PARAMS["fac_over_red"]-1)),
        ("产能参数","衬衣500/外套300/统一卡点400件每天（老板拍板）；4天备货触发线需在手量字段，衣者列表接口未提供，暂未启用。"),
    ],8)

    ws5=wb.create_sheet("④辅料物料"); ws5.sheet_view.showGridLines=False
    for j,w in enumerate([14,16,10,11,11,12,32],1): ws5.column_dimensions[get_column_letter(j)].width=w
    ws5.merge_cells('A1:G1'); c=ws5.cell(1,1,"D-5 · 物料结存监控（主料+辅料）"); c.font=F_TITLE
    r=legend_line(ws5,2,"图例：🔴 负结存＝领用超采购需盘点 ｜ 🟡 主料剩余≥%d单位可复用 ｜ 款号关联待采购补录（F4）"%PARAMS["material_surplus_min"],7); r=3
    r=sec_header(ws5,r,"汇总",7)
    r=kpi_block(ws5,r,[
        ("负结存物料",len(neg),"领用>采购，疑错账/流失",F_BIG),
        ("主料剩余可复用",len(surplus),"≥%d单位（米/码/kg）"%PARAMS["material_surplus_min"],F_AMBB),
        ("物料总记录",len(mat),"主料+辅料",F_NUM),
    ])
    topn=min(15,len(neg)); tops=min(15,len(surplus))
    r=sec_header(ws5,r,"明细A · 负结存（缺口最大前 %d / 共 %d 条）"%(topn,len(neg)),7)
    rows_n=[[m.get('material_no') or '—',m.get('material_name') or '—',m.get('unit') or '',float(m.get('gap') or 0),float(m.get('total_gap_num') or 0),(m.get('related_template_nos') or '—'),"红·负结存"] for m in neg[:15]]
    r=write_table(ws5,r,["物料编号","名称","单位","本次结存","累计结存","关联款号","档位"],rows_n,tier_col=6,num_cols=(4,5),add_filter=True)
    r+=1
    r=sec_header(ws5,r,"明细B · 主料剩余可复用（前 %d / 共 %d 条，按剩余量降序）"%(tops,len(surplus)),7)
    rows_s=[[m.get('material_no') or '—',m.get('material_name') or '—',m.get('unit') or '',float(m.get('total_gap_num') or 0),float(m.get('avg_price') or 0),float(m.get('avg_price') or 0)*float(m.get('total_gap_num') or 0),"黄·可复用"] for m in surplus[:15]]
    r=write_table(ws5,r,["物料编号","名称","单位","剩余量","参考单价(¥)","参考货值(¥)","档位"],rows_s,tier_col=6,num_cols=(4,5,6),add_filter=True)
    r+=1
    r=koujing_block(ws5,r,[
        ("结存口径","结存=采购入库−生产领用（衣者物料库存 gap/total_gap_num）；负数=领用超采购，可能为：错账、损耗未录、或物料流失。"),
        ("可复用判定","material_type=1(主料) 且累计结存≥%d 单位；建议转设计端评估复用（老板：常年累积就是成本）。"%PARAMS["material_surplus_min"]),
        ("已知卡点(F4)","衣者物料库存『不勾对款号』，related_template_nos 大面积为空 → 负结存无法定位到具体款式，需采购侧补录规则后才能逐款追责。"),
        ("辅料损耗率","正式阈值待生产经理+采购定标后启用（建议方向：小五金2%/B料1%）。"),
        ("统计","负结存 %d 条（按 gap<0 或 total_gap_num<0 任一命中）；剩余≥%d 的主料 %d 条。"%(len(neg),PARAMS["material_surplus_min"],len(surplus))),
    ],7)

    outdir=os.path.join(DATA_HOME, 'out'); os.makedirs(outdir,exist_ok=True)
    out=os.path.join(outdir,"生产监控日报_%s.xlsx"%args.date)
    wb.save(out)
    print("[done] 已生成:",out)
    print("[stats] 数量异常 %d（多%d/少%d）｜货期逾期 %d｜辅料负结存 %d｜主料剩余 %d"%(
        n_multi+n_under,n_multi,n_under,n_over,len(neg),len(surplus)))

if __name__=='__main__':
    main()
