#!/usr/bin/env python3
# 数据包完整性体检 + 图片缓存盘点
import os, glob
import json
from pathlib import Path
from collections import defaultdict
import openpyxl

SKILL = str(Path(__file__).resolve().parent.parent)
TODAY = "2026-10-10"

print("=" * 60)
print("一、四份数据包完整性体检")
print("=" * 60)
issues = []
for dept in ["研发部", "生产部", "销售部", "财务部"]:
    f = f"{SKILL}/out/数据包-{dept}-{TODAY}.xlsx"
    if not os.path.exists(f):
        issues.append(f"[缺失] {dept} 文件不存在")
        continue
    wb = openpyxl.load_workbook(f)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(min_row=3, values_only=True))
        rows = [r for r in rows if r[0] is not None]
        if not rows:
            issues.append(f"[空表] {dept}/{ws.title}")
            continue
        ncol = 0
        for r in rows[:1]:
            ncol = len([x for x in r if x is not None])
        # 统计每列空值率
        header_row = list(ws.iter_rows(min_row=2, max_row=2, values_only=True))[0]
        headers = [h for h in header_row if h]
        n = len(rows)
        for ci in range(len(headers)):
            vals = [r[ci] if ci < len(r) else None for r in rows]
            empty = sum(1 for v in vals if v is None or v == "" or v == "-")
            if empty / n > 0.3:  # 空值率>30%
                issues.append(f"[稀疏] {dept}/{ws.title[:20]} 列「{headers[ci]}」空值 {empty}/{n} ({empty/n*100:.0f}%)")
        # 示例/占位数据检测
        for r in rows[:5]:
            for v in r:
                if isinstance(v, str) and ("示例" in v or "待…生成" in v or "待补" in v):
                    issues.append(f"[占位] {dept}/{ws.title[:20]} 存在示例值: {v[:30]}")
                    break

for x in issues:
    print(" ", x)

print()
print("=" * 60)
print("二、图片缓存盘点")
print("=" * 60)
pic_dir = f"{SKILL}/state/goods-pics"
pics = {}
if os.path.isdir(pic_dir):
    for p in glob.glob(f"{pic_dir}/*"):
        pics[os.path.splitext(os.path.basename(p))[0]] = p
print(f"缓存图片: {len(pics)} 张")
sample = list(pics.items())[:3]
for k, v in sample:
    print(f"  {k} -> {os.path.basename(v)} ({os.path.getsize(v)//1024}KB)")

# 数据包涉及的商品款号清单(需配图的表)
need_pics = defaultdict(set)
wb = openpyxl.load_workbook(f"{SKILL}/out/数据包-生产部-{TODAY}.xlsx")
for wsname in ["01·周滚动补货计划(净缺口法)", "07·补货建议V2·三因子对比"]:
    if wsname in wb.sheetnames:
        for r in wb[wsname].iter_rows(min_row=3, values_only=True):
            if r[1]:
                ref = str(r[1]).split("-")[0]
                need_pics["生产部"].add(ref)
wb2 = openpyxl.load_workbook(f"{SKILL}/out/数据包-研发部-{TODAY}.xlsx")
for wsname in ["02·爆款基因库·近30日动销Top30", "03·慢销止损清单"]:
    if wsname in wb2.sheetnames:
        for r in wb2[wsname].iter_rows(min_row=3, values_only=True):
            if r[0]:
                need_pics["研发部"].add(str(r[0]).split("-")[0])

total_refs = set()
for d, refs in need_pics.items():
    have = sum(1 for x in refs if x in pics)
    print(f"{d}: 需图 {len(refs)} 款, 已缓存 {have}, 缺 {len(refs)-have}")
    total_refs |= refs

# 商品档案的pic_url
goods_pic = {}
with open(f"{SKILL}/data/raw/2026-10-09/pm/duoke_goods.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        g = json.loads(line)
        ref = str(g.get("item_ref") or g.get("id") or "")
        pu = g.get("pic_url")
        if ref and pu:
            if isinstance(pu, list):
                pu = pu[0] if pu else ""
            goods_pic[ref.split("-")[0]] = pu
print(f"\n商品档案pic_url: {len(goods_pic)} 款")
miss = [x for x in total_refs if x not in pics]
have_url = sum(1 for x in miss if x in goods_pic)
print(f"缺图款 {len(miss)} 中, {have_url} 款有pic_url可下载")

# 衣者样板图(研发部设计师矩阵可用)
tpl_thumb = {}
with open(f"{SKILL}/data/raw/2026-10-09/pm/yizhe_template_list.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        t = json.loads(line)
        if t.get("template_no") and t.get("template_thumb"):
            tpl_thumb[t["template_no"]] = t["template_thumb"]
print(f"衣者样板图: {len(tpl_thumb)} 款")
