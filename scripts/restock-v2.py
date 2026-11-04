#!/usr/bin/env python3
# 补货建议量 V2.2 最终版
# 因子: ①历史销量(近7/30日+生命周期曲线) ②往年同期(品类×10-11月,3年均值)
#      ③季节×气候系数(华南主区+换季窗口) + 安全护栏
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

SKILL = str(Path(__file__).resolve().parent.parent)
RAW = f"{SKILL}/data/raw/2026-10-09/pm"
OUTDIR = f"{SKILL}/out"
TODAY = "2026-10-10"
HORIZON = 30
W_RECENT, W_LIFE, W_YOY = 0.5, 0.3, 0.2

def num(v, d=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def ts2dt(v):
    try:
        s = str(v)
        if s.replace(".", "").isdigit() and len(s) >= 9:
            return datetime.fromtimestamp(int(float(s)))
    except Exception:
        pass
    return None

def cat_name(v):
    return (v.get("name") or "") if isinstance(v, dict) else (v or "")

print("加载数据...")
ref_day_qty = defaultdict(lambda: defaultdict(float))
ref_cat_from_detail = {}   # 款→品类(从明细反查)
cat_day_qty = defaultdict(lambda: defaultdict(float))
with open(f"{RAW}/duoke_order_details.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        for g in (d.get("goods") or []):
            dt = ts2dt(g.get("ctime"))
            if not dt:
                continue
            qty = num(g.get("quantity"))
            if qty <= 0:
                continue
            ref = str(g.get("item_ref"))
            day = dt.strftime("%Y-%m-%d")
            ref_day_qty[ref][day] += qty
            c = cat_name(g.get("category"))
            if c:
                cat_day_qty[c][day] += qty
                ref_cat_from_detail[ref] = c   # 最后一次出现的品类(款基本不变品类)

goods_meta = {}
with open(f"{RAW}/duoke_goods.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        g = json.loads(line)
        ref = str(g.get("item_ref") or g.get("id") or "")
        if not ref:
            continue
        goods_meta[ref] = {
            "name": g.get("name"), "season": cat_name(g.get("season")),
            "ctime": ts2dt(g.get("ctime")),
        }

# 别名: SW2641076 → SW2641076-1
base_alias = defaultdict(list)
for ref in ref_day_qty:
    base = ref.split("-")[0].split("/")[0]
    if base != ref:
        base_alias[base].append(ref)

restock = json.load(open(f"{OUTDIR}/restock-deep-2026-10-09.json", encoding="utf-8"))
NOW = datetime(2026, 10, 10)

def sales_of(ref):
    if ref_day_qty.get(ref):
        return ref_day_qty[ref], ref
    for alias in base_alias.get(ref, []):
        return ref_day_qty[alias], alias
    return None, ref

def recent_daily(dq, days):
    if not dq:
        return 0.0
    s = 0
    for i in range(1, days + 1):
        s += dq.get((NOW - timedelta(days=i)).strftime("%Y-%m-%d"), 0)
    return s / days

# 品类同期日均(10-11月, 3年)
cat_yoy_cache = {}
def yoy_of(cat):
    if not cat:
        return 0.0
    if cat in cat_yoy_cache:
        return cat_yoy_cache[cat]
    dq = cat_day_qty.get(cat)
    v = 0.0
    if dq:
        tot = sum(qty for k, qty in dq.items()
                  if any(k.startswith(f"{y}-{m:02d}") for y in (2023, 2024, 2025) for m in (10, 11)))
        v = tot / (3 * 61)
    cat_yoy_cache[cat] = v
    return v

results = []
for it in restock.get("rows", []):
    ref = str(it.get("item_ref"))
    meta = goods_meta.get(ref, {})
    stock = num(it.get("stock"))
    inprod = num(it.get("inprod"))
    v1_net = num(it.get("net"))

    dq, actual_ref = sales_of(ref)
    # 品类: 明细反查优先(商品档案k_category多为空)
    cat = ref_cat_from_detail.get(actual_ref) or ref_cat_from_detail.get(ref) or ""
    season = meta.get("season", "")

    r7 = recent_daily(dq, 7)
    r30 = recent_daily(dq, 30)

    # 生命周期: 用销量首日作起点(别名/无上市日都稳)
    life_daily, weeks = 0.0, 0
    if dq:
        first_sale = min(dq.keys())
        life_days = max(1, (NOW - datetime.strptime(first_sale, "%Y-%m-%d")).days)
        life_daily = sum(dq.values()) / life_days
        # 护栏: 生命周期日均 ≤ 2×近30日均值(防别名/新品脉冲虚高)
        if r30 > 0:
            life_daily = min(life_daily, 2 * r30)
        weeks = max(1, life_days // 7 + 1)

    # 生命周期系数(与近7/30趋势联动)
    if weeks == 0:
        lf, stage = 0.9, "无销量"
    elif weeks <= 2:
        lf, stage = 1.3, f"W{weeks}爬坡"
    elif weeks <= 6:
        lf, stage = 1.5, f"W{weeks}峰值"
    elif weeks <= 10:
        lf, stage = 1.0, f"W{weeks}平稳"
    else:
        lf, stage = 0.6, f"W{weeks}衰减"
    if r30 > 0:
        if r7 >= r30:
            lf = max(lf, 1.2)
            stage += "·上行"
        elif r7 < 0.7 * r30:
            stage += "·下行"
        else:
            if 0 < lf < 1.0:
                lf = 1.0
            stage += "·平稳"

    yoy = yoy_of(cat)

    # 季节×气候
    winter_cats = {"羽绒服", "毛衣", "毛衣开衫", "毛衣马甲", "棉服", "呢料外套", "双面呢（羊绒）"}
    if season == "冬季" or cat in winter_cats:
        cf, cf_desc = 1.2, "冬款·华南启动期"
    elif season == "秋季":
        cf, cf_desc = 1.0, "秋款·华南延长窗"
    else:
        cf, cf_desc = 1.0, season or "未标注"

    if not dq:
        results.append({"item_ref": ref, "name": it.get("name"), "level": it.get("level"), "action": it.get("action"),
                        "cate": cat, "stock": stock, "inprod": inprod, "recent7": "-", "recent30": "-",
                        "life": "-", "stage": "无销量", "yoy": round(yoy, 1), "climate": cf_desc,
                        "pred": "-", "future30": "-", "v1_net": v1_net, "v2_net": round(v1_net),
                        "diff": 0, "note": "⚠️无销量明细(疑档口预占),按V1执行+核实"})
        continue

    base_recent = r7 if r7 > 0 else r30
    num_sum = den = 0.0
    for w, v in ((W_RECENT, base_recent), (W_LIFE, life_daily), (W_YOY, yoy)):
        if v > 0:
            num_sum += w * v
            den += w
    pred = num_sum / den if den else 0.0
    future30 = pred * lf * cf * HORIZON
    v2_net = max(0, round(future30 - max(0, stock) - inprod))
    # 上限护栏: 单款追单 ≤ 预测日均×1.5×45天(防极端)
    cap = round(pred * 1.5 * 45)
    v2_net = min(v2_net, cap)

    results.append({"item_ref": ref, "name": it.get("name"), "level": it.get("level"), "action": it.get("action"),
                    "cate": cat, "stock": stock, "inprod": inprod,
                    "recent7": round(r7, 1), "recent30": round(r30, 1),
                    "life": round(life_daily, 1), "stage": stage, "yoy": round(yoy, 1),
                    "climate": cf_desc, "pred": round(pred, 1), "future30": round(future30),
                    "v1_net": v1_net, "v2_net": v2_net, "diff": v2_net - v1_net, "note": ""})

results.sort(key=lambda x: -x["v2_net"])
json.dump({"date": TODAY, "version": "v2.2",
           "factors": {"recent": W_RECENT, "lifecycle": W_LIFE, "yoy": W_YOY, "horizon": HORIZON,
                       "note": "pred_daily=加权(近7/30日, 生命周期曲线, 品类去年同期); future30=pred×生命周期系数×季节气候系数×30天; v2_net=future30−库存−在产"},
           "rows": results},
          open(f"{OUTDIR}/restock-v2-{TODAY}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

up = [r for r in results if r["diff"] > 50]
down = [r for r in results if r["diff"] < -50]
print(f"V2.2 vs V1: 上调{len(up)} 下调{len(down)} 持平{len(len_same) if (len_same := [r for r in results if abs(r['diff']) <= 50]) else 0}")
print("\n=== 下调Top6(防过补) ===")
for r in sorted(results, key=lambda x: x["diff"])[:6]:
    print(f"  {r['item_ref']} {str(r['name'])[:11]:13s} V1{r['v1_net']:>6.0f}→V2{r['v2_net']:>5} ({r['diff']:+.0f}) |近7={r['recent7']} 近30={r['recent30']} {r['stage']} 同期={r['yoy']} [{r['cate']}]")
print("\n=== 上调Top6(防断货) ===")
for r in sorted(results, key=lambda x: -x["diff"])[:6]:
    print(f"  {r['item_ref']} {str(r['name'])[:11]:13s} V1{r['v1_net']:>6.0f}→V2{r['v2_net']:>5} ({r['diff']:+.0f}) |近7={r['recent7']} 近30={r['recent30']} {r['stage']} 同期={r['yoy']} {r['climate']}")
print("\n=== 关键款复核 ===")
for ref in ("SW2641076", "PT2631016", "ST263825", "SW2641078", "PM2641166"):
    r = next((x for x in results if x["item_ref"] == ref), None)
    if r:
        print(f"  {ref}: V1{r['v1_net']:.0f}→V2{r['v2_net']} | {r['stage']} 同期={r['yoy']} [{r['cate']}] {r['climate']}")
