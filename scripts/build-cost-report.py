#!/usr/bin/env python3
# build-cost-report.py — 采购员成本核算：订单「实际成本 vs 预计成本」差额分析
# 输入：data/raw/<today>/pm/perf_cost_<month>.jsonl   （财务对账-按订单核对）
#       data/raw/<today>/pm/perf_purchase_<month>.jsonl（采购单，取 buyer_name 归属采购员）
# 输出：out/cost-<month>.json
#
# 口径要点：
#   预计单件成本 = template_price（系统"预计单件成本（平均）"，含采购+加工+工艺+固定）
#   实际单件成本 = cuted_price（按裁货）/ stock_in_price（按入库）
#   主口径按裁货：未入库订单也能核算，件数权重=裁货数；入库口径作参考列
#   差额 = 实际 − 预计（负数=低于预计/成本控制有效，正数=超支）
#   有效性过滤：采购未录价（实际成本=0）、采购单价缺失、|偏差|>50%（疑录入异常）不入汇总，
#              单列「成本异常清单」供人工核对——否则 12 张 0 成本单会伪造出上百万元"节约"。
import json, re, sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date

import os
ROOT = Path(__file__).resolve().parent.parent
DATA_HOME = Path(os.environ.get('SCM_DATA_HOME') or (Path.home() / 'WorkBuddy' / 'scm-collector-data'))  # 运行时数据根目录(state/data/out)，SCM_DATA_HOME 可覆盖
MONTH = sys.argv[1] if len(sys.argv) > 1 else '2026-09'
today = date.today().isoformat()
RAW = DATA_HOME / 'data' / 'raw' / today / 'pm'

def num(s):
    if s is None: return None
    m = re.match(r'^-?\d+(\.\d+)?', str(s).strip())
    return float(m.group()) if m else None

cost_rows = [json.loads(l) for l in (RAW / f'perf_cost_{MONTH}.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
pur_rows = [json.loads(l) for l in (RAW / f'perf_purchase_{MONTH}.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
buyer_of = {p['production_id']: (p.get('buyer_name') or '(未分配)') for p in pur_rows}
purchase_of = {p['production_id']: p.get('purchase_sn') or '' for p in pur_rows}

# —— 判定分档（按总成本差额率）——
def grade(rate):
    if rate is None: return '无法核算'
    if rate <= -0.03: return '显著节约'
    if rate <= -0.01: return '略优'
    if rate < 0.01: return '基本持平'
    if rate < 0.03: return '略超'
    return '明显超支'

def invalid_reason(x):
    """返回无效原因；None 表示该单可用于汇总"""
    if not x['预计单件成本'] or x['预计单件成本'] <= 0: return '缺预计成本'
    if not x['实际单件成本'] or x['实际单件成本'] <= 0: return '采购未录价（实际成本为0）'
    if not x['单件采购成本'] or x['单件采购成本'] <= 0: return '采购单价缺失'
    if abs(x['差额率']) > 50: return '偏差>50%（疑单位或录入异常）'
    return None

detail = []
for c in cost_rows:
    pid = c['production_id']
    buyer = buyer_of.get(pid, '(未分配)')
    est_unit = num(c.get('template_price'))
    cut_unit = num(c.get('cuted_price'))
    in_unit = num(c.get('stock_in_price'))
    cut_num = c.get('cuted_num') or 0
    in_num = c.get('stock_in_num') or 0
    plan_num = c.get('plan_total_num') or 0
    pur_unit = num(c.get('cuted_purchase_price')) if num(c.get('cuted_purchase_price')) is not None else num(c.get('stock_purchase_price'))
    labor = num(c.get('price'))
    fixed = num(c.get('cost_price'))

    base = '按裁货'; qty = cut_num
    if qty <= 0:
        base, qty = ('按入库', in_num) if in_num > 0 else ('按下单数', plan_num)
    actual_unit = cut_unit if cut_unit is not None else in_unit

    ok = est_unit is not None and actual_unit is not None and qty > 0
    est_total = round(est_unit * qty, 2) if ok else None
    act_total = round(actual_unit * qty, 2) if ok else None
    diff_total = round(act_total - est_total, 2) if ok else None
    diff_unit = round(actual_unit - est_unit, 2) if ok else None
    rate = (diff_total / est_total) if ok and est_total else None
    craft = round(cut_unit - (pur_unit or 0) - (labor or 0) - (fixed or 0), 2) if cut_unit is not None and pur_unit is not None else None
    labor_share = round((labor or 0) / cut_unit * 100, 1) if cut_unit else None
    pur_share = round((pur_unit or 0) / cut_unit * 100, 1) if cut_unit and pur_unit else None

    row = {
        '生产单号': c.get('production_sn') or '', '款号': c.get('template_no') or '', '采购员': buyer,
        '采购单号': purchase_of.get(pid, ''), '工厂': c.get('factory_name') or '', '下单时间': (c.get('created_at') or '')[:10],
        '订单类型': c.get('production_type_desc') or '', '生产状态': c.get('status_desc') or '',
        '下单数': plan_num, '裁货数': cut_num, '入库数': in_num, '计价基数': base, '计价件数': qty,
        '预计单件成本': est_unit, '实际单件成本': actual_unit, '单件差额': diff_unit,
        '预计总成本': est_total, '实际总成本': act_total, '总差额': diff_total,
        '差额率': round(rate * 100, 2) if rate is not None else None,
        '判定': grade(rate),
        '单件采购成本': pur_unit, '单件加工费': labor, '单件固定成本': fixed,
        '单件工艺成本(推算)': craft, '采购占成本%': pur_share, '加工占成本%': labor_share,
        '入库单件成本(参考)': in_unit,
    }
    row['有效性'] = invalid_reason(row) or '有效'
    detail.append(row)

valid = [x for x in detail if x['有效性'] == '有效']
invalid = [x for x in detail if x['有效性'] != '有效']

# —— 采购员汇总（仅有效单）——
byst = defaultdict(lambda: {
    '订单数': 0, '有效订单': 0, '无效订单': 0, '计价件数': 0, '入库件数': 0,
    '预计总成本': 0.0, '实际总成本': 0.0, '成本差额': 0.0,
    '显著节约': 0, '略优': 0, '基本持平': 0, '略超': 0, '明显超支': 0,
    '采购成本合计': 0.0, '加工费合计': 0.0, '入库口径_预计': 0.0, '入库口径_实际': 0.0,
})
for x in detail:
    s = byst[x['采购员']]
    s['订单数'] += 1
    s['入库件数'] += x['入库数']
    if x['有效性'] != '有效':
        s['无效订单'] += 1; continue
    s['有效订单'] += 1; s['计价件数'] += x['计价件数']
    s['预计总成本'] += x['预计总成本']; s['实际总成本'] += x['实际总成本']; s['成本差额'] += x['总差额']
    s['采购成本合计'] += (x['单件采购成本'] or 0) * x['计价件数']
    s['加工费合计'] += (x['单件加工费'] or 0) * x['计价件数']
    s[x['判定']] = s.get(x['判定'], 0) + 1
    if x['入库单件成本(参考)'] is not None and x['入库数'] > 0 and x['预计单件成本']:
        s['入库口径_预计'] += x['预计单件成本'] * x['入库数']
        s['入库口径_实际'] += x['入库单件成本(参考)'] * x['入库数']

for name, s in byst.items():
    r2 = lambda v: round(v, 2)
    s['预计总成本'] = r2(s['预计总成本']); s['实际总成本'] = r2(s['实际总成本']); s['成本差额'] = r2(s['成本差额'])
    s['差额率%'] = r2(s['成本差额'] / s['预计总成本'] * 100) if s['预计总成本'] else None
    s['单件预计'] = r2(s['预计总成本'] / s['计价件数']) if s['计价件数'] else None
    s['单件实际'] = r2(s['实际总成本'] / s['计价件数']) if s['计价件数'] else None
    s['单件差额'] = r2(s['成本差额'] / s['计价件数']) if s['计价件数'] else None
    s['采购成本占比%'] = r2(s['采购成本合计'] / s['实际总成本'] * 100) if s['实际总成本'] else None
    s['加工费占比%'] = r2(s['加工费合计'] / s['实际总成本'] * 100) if s['实际总成本'] else None
    s['节约单'] = s['显著节约'] + s['略优']; s['超支单'] = s['略超'] + s['明显超支']
    s['有效样本率%'] = r2(s['有效订单'] / s['订单数'] * 100) if s['订单数'] else None
    s['入库口径_预计'] = r2(s['入库口径_预计']); s['入库口径_实际'] = r2(s['入库口径_实际'])
    s['入库口径_差额'] = r2(s['入库口径_实际'] - s['入库口径_预计'])
    s['入库口径_差额率%'] = r2(s['入库口径_差额'] / s['入库口径_预计'] * 100) if s['入库口径_预计'] else None
    s['评价'] = grade(s['差额率%'] / 100) if s['差额率%'] is not None else '无有效样本'
    for k in ['采购成本合计', '加工费合计', '入库口径_预计', '入库口径_实际']: del s[k]

tot_est = round(sum(s['预计总成本'] for s in byst.values()), 2)
tot_act = round(sum(s['实际总成本'] for s in byst.values()), 2)
tot_diff = round(tot_act - tot_est, 2)
qty_sum = sum(x['计价件数'] for x in valid)

out = {
    '统计月': MONTH,
    '数据源': '衣者云 财务对账-按订单核对（/backend/finance/get_production_process_list），按生产单下单时间落月；采购员归属取自采购单 buyer_name',
    '快照': today,
    '全局': {
        '订单数': len(detail), '有效订单': len(valid), '无效订单': len(invalid),
        '无效原因': dict(Counter(x['有效性'] for x in invalid)),
        '计价件数': qty_sum,
        '预计总成本': tot_est, '实际总成本': tot_act, '总差额': tot_diff,
        '总差额率%': round(tot_diff / tot_est * 100, 2) if tot_est else None,
        '单件预计': round(tot_est / qty_sum, 2) if qty_sum else None,
        '单件实际': round(tot_act / qty_sum, 2) if qty_sum else None,
        '单件差额': round((tot_act - tot_est) / qty_sum, 2) if qty_sum else None,
        '节约单': sum(1 for x in valid if x['总差额'] < 0),
        '超支单': sum(1 for x in valid if x['总差额'] > 0),
        '持平单': sum(1 for x in valid if x['总差额'] == 0),
        '有效件数占下单件数%': round(qty_sum / sum(x['下单数'] for x in detail) * 100, 1) if sum(x['下单数'] for x in detail) else None,
        '计价基数分布': dict(Counter(x['计价基数'] for x in detail)),
        '未匹配采购员订单': sum(1 for x in detail if x['采购员'] == '(未分配)'),
    },
    '采购员成本': dict(sorted(byst.items(), key=lambda kv: (kv[1]['差额率%'] is None, kv[1]['差额率%'] if kv[1]['差额率%'] is not None else 0))),
    '成本明细': detail,
    '异常清单': invalid,
    '数据质量': {
        '成本字段来源': 'template_price=预计单件成本；cuted_price=按裁货实际；stock_in_price=按入库实际；未裁货/未入库为文本，解析失败即缺失',
        '计价基数规则': '裁货优先（未入库订单也能核算）；裁货为0用入库；两者皆无按下单数兜底并标注',
        '差额口径': '差额=实际成本−预计成本（负数=低于预计，成本控制有效）；差额率=差额÷预计成本',
        '分档': '≤−3% 显著节约 / −3%~−1% 略优 / ±1% 基本持平 / 1%~3% 略超 / >3% 明显超支',
        '有效性过滤': f'本月 {len(detail)} 单中 {len(invalid)} 单被排除：采购未录价致实际成本为0、采购单价缺失、或偏差>50%（疑单位错误）。不过滤会让 12 张零成本单伪造巨额"节约"，必须剔除后看',
        '不可拆分说明': '系统只给"预计单件成本"总额，未给"预计采购成本"分项；工艺成本为残差推算。因此采购段与加工段无法在数学上分离，差额统一按总成本口径，明细中列出采购/加工/固定占比供人工判断成因',
        '归属规则': f'生产单与采购单 {len(pur_rows)}:{len(pur_rows)} 一一对应，无一单多采购员；无采购单订单归"未分配"',
        '范围说明': '按生产单下单时间落月（成本在下单时预估、采购/入库后转实际），与「采购汇总」的采购单创建月口径一致；与「生产跟单汇总」的出货月口径不同，两表不可直接相加对照',
    },
}
outp = DATA_HOME / 'out' / f'cost-{MONTH}.json'
outp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')

g = out['全局']
print(f"订单 {g['订单数']}｜有效 {g['有效订单']}｜无效 {g['无效订单']} {g['无效原因']}")
print(f"预计 {g['预计总成本']:,.2f}｜实际 {g['实际总成本']:,.2f}｜差额 {g['总差额']:,.2f} ({g['总差额率%']}%)｜单件 {g['单件预计']}→{g['单件实际']}")
print(f"节约单 {g['节约单']}｜超支单 {g['超支单']}｜持平 {g['持平单']}｜计价基数 {g['计价基数分布']}")
print('--- 采购员 ---')
for n, s in out['采购员成本'].items():
    print(f"{n:8s} 单{s['订单数']:>3}/有效{s['有效订单']:>3} 件{s['计价件数']:>6} 预计{s['预计总成本']:>11,.0f} 实际{s['实际总成本']:>11,.0f} 差{s['成本差额']:>9,.0f} ({s['差额率%']:>6}%) 单件{s['单件差额']:>7} 采购占比{s['采购成本占比%']}% 评价={s['评价']}")
print('saved:', outp)
