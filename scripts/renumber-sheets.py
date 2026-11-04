#!/usr/bin/env python3
# 终修: sheet编号重排(按原逻辑顺序)
import openpyxl

SKILL = str(Path(__file__).resolve().parent.parent)
TODAY = "2026-10-10"

ORDER = {
    "生产部": ["周滚动补货计划", "在产订单驾驶舱", "碎片返单代价明细", "工厂计分卡·全量", "返单节奏明细", "补货建议V2"],
    "销售部": ["流失预警", "交期承诺表", "新客15天", "导购业绩", "地域分布", "流失全量"],
    "研发部": ["品类动销", "爆款基因库", "慢销止损", "设计师全量漏斗", "品类×设计师"],
}

for dept, keys in ORDER.items():
    wb = openpyxl.load_workbook(f"{SKILL}/out/数据包-{dept}-{TODAY}.xlsx")
    # 当前实际顺序
    cur = list(wb.sheetnames)
    # 目标顺序: 按keys匹配
    target = []
    for k in keys:
        m = next((s for s in cur if k in s), None)
        if m:
            target.append(m)
    # 未匹配的保持原相对顺序追加
    for s in cur:
        if s not in target:
            target.append(s)
    # 重命名: 先去掉旧编号, 按target顺序加新编号
    # 用两步避免重名冲突
    tmp_map = {}
    for i, s in enumerate(target):
        name = s.split("·", 1)[1] if "·" in s else s
        tmp_map[s] = f"TMP{i}|" + name
    for s in target:
        wb[s].title = tmp_map[s]
    for i, s in enumerate(target):
        wb[tmp_map[s]].title = f"{i+1:02d}·" + tmp_map[s].split("|", 1)[1]
    wb.save(f"{SKILL}/out/数据包-{dept}-{TODAY}.xlsx")
    print(f"{dept}: {[s[:16] for s in wb.sheetnames]}")
print("✅ 编号已重排")
