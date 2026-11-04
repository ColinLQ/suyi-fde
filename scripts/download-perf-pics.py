#!/usr/bin/env python3
# download-perf-pics.py — 报表款图片下载：cache hash 直下 + 全角横线款号映射到归一化款
import json, re, os, time, urllib.request
from pathlib import Path

SKILL = str(Path(__file__).resolve().parent.parent)
CDN = 'https://cn-cdn-oss.duoke.net/user_TENANT/'
THUMB = '?x-oss-process=image/resize,m_mfit,h_140,w_140/quality,q_80'

cache = json.load(open(f'{SKILL}/state/goods-pics.json', encoding='utf-8'))
no = json.load(open(f'{SKILL}/state/perf-no-pic.json', encoding='utf-8'))
picDir = f'{SKILL}/state/goods-pics'

def dl(hash_, out):
    if os.path.exists(out) and os.path.getsize(out) > 500:
        return True
    url = CDN + hash_ + THUMB
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://air.duoke.net/'})
    try:
        buf = urllib.request.urlopen(req, timeout=15).read()
        if len(buf) < 500:
            return False
        open(out, 'wb').write(buf)
        return True
    except Exception:
        return False

ok = fail = 0
for ref in no:
    n = re.sub(r'[—–]', '-', ref)
    h = cache.get(ref) or cache.get(n)
    if not h:
        continue
    out = f'{picDir}/{ref}.jpg'
    if dl(h, out):
        ok += 1
    else:
        fail += 1
    time.sleep(0.1)
print(f'补下完成: ok={ok} fail={fail}')

# 重算无图清单
no2 = [r for r in no if not (os.path.exists(f'{picDir}/{r}.jpg') and os.path.getsize(f'{picDir}/{r}.jpg') > 500)]
json.dump(no2, open(f'{SKILL}/state/perf-no-pic.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('仍无图:', len(no2))
