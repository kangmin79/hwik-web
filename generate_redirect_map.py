# -*- coding: utf-8 -*-
"""
generate_redirect_map.py — 구버전 apt- slug → 신버전 slug 리다이렉트 맵 생성

danji/apt-redirect.json 출력
404.html에서 이 파일을 로드해 구 URL → 새 URL 자동 이동
"""
import os, sys, json, time
import requests

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

for fname in (".env", "env"):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    if not os.path.exists(path): continue
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

SB_URL = "https://jqaxejgzkchxbfzgzyzi.supabase.co"
SB_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
H = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slug_utils import make_danji_slug

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DANJI_DIR = os.path.join(BASE_DIR, "danji")

# ── 1. 현재 danji/ 폴더의 신버전 slug 목록 ──────────────────
print("신버전 slug 목록 로드 중...")
new_slugs = {
    f[:-5]  # .html 제거
    for f in os.listdir(DANJI_DIR)
    if f.endswith(".html") and not f.startswith("apt-")
}
print(f"  신버전 slug {len(new_slugs):,}개")

# complex_name → slug 역인덱스 (이름으로 새 slug 검색용)
# 파일명에서 이름 추출: {prefix}-{name}-{id}.html
# id 패턴: a[0-9]+  (소문자 a + 숫자)
import re
name_to_slug = {}
for slug in new_slugs:
    m = re.match(r'^(.+)-([a-z]\d{5,})$', slug)
    if m:
        name_part = m.group(1)  # {prefix}-{name}
        # 마지막 '-' 이전 = 전체 slug에서 id만 뗀 것
        # name_part의 마지막 '-' 이후가 complex_name slug
        parts = name_part.rsplit('-', 1)
        if len(parts) == 2:
            name_clean = parts[1]  # 단지명 slug 부분
            if name_clean not in name_to_slug:
                name_to_slug[name_clean] = slug
            else:
                # 중복 시 둘 다 보관 (리스트로)
                existing = name_to_slug[name_clean]
                if isinstance(existing, list):
                    existing.append(slug)
                else:
                    name_to_slug[name_clean] = [existing, slug]

print(f"  이름→slug 인덱스 {len(name_to_slug):,}개")

# ── 2. Supabase에서 apt- 항목 조회 ──────────────────────────
print("\napt- 항목 조회 중...")
apt_data = []
offset = 0
while True:
    r = requests.get(
        f"{SB_URL}/rest/v1/danji_pages",
        headers=H,
        params={
            "select": "id,complex_name,location,address",
            "id": "like.apt-*",
            "order": "id",
            "offset": offset,
            "limit": 500,
        },
        timeout=30,
    )
    batch = r.json() if r.status_code == 200 else []
    if not batch:
        break
    apt_data.extend(batch)
    offset += 500
    if len(batch) < 500:
        break
    time.sleep(0.1)

print(f"  apt- 항목 {len(apt_data):,}개 로드")

# ── 3. apt- slug 계산 + 신버전 slug 매핑 ────────────────────
print("\n매핑 생성 중...")
redirect_map = {}
matched = 0
unmatched = []

for d in apt_data:
    old_id = d.get("id", "")
    name = d.get("complex_name", "")
    location = d.get("location", "")
    address = d.get("address", "")

    # 구버전 slug 계산 (ID 자체에 이름 포함)
    old_slug = make_danji_slug(name, location, old_id, address)

    # 신버전 slug 검색: complex_name의 slug 형태로 검색
    from slug_utils import clean as _clean
    name_clean = _clean(name)
    new_slug = None

    if name_clean in name_to_slug:
        val = name_to_slug[name_clean]
        if isinstance(val, str):
            new_slug = val
        elif isinstance(val, list):
            # 여러 개면 location으로 구분
            loc_parts = (location or "").split()
            for s in val:
                if any(_clean(p) in s for p in loc_parts):
                    new_slug = s
                    break
            if not new_slug:
                new_slug = val[0]

    if new_slug:
        redirect_map[old_slug] = new_slug
        matched += 1
    else:
        unmatched.append(f"{old_slug} ({name})")

print(f"  매칭 성공: {matched:,}개")
print(f"  매칭 실패: {len(unmatched):,}개")
if unmatched[:5]:
    print("  실패 샘플:", unmatched[:5])

# ── 4. JSON 저장 ─────────────────────────────────────────────
out_path = os.path.join(DANJI_DIR, "apt-redirect.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(redirect_map, f, ensure_ascii=False, separators=(",", ":"))

size_kb = os.path.getsize(out_path) / 1024
print(f"\n✅ 저장: {out_path} ({size_kb:.0f} KB, {len(redirect_map):,}개 항목)")
