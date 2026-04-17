# -*- coding: utf-8 -*-
"""
build_search_index.py — hwik.kr 메인 검색용 JSON 인덱스 생성

실제 HTML 파일 리스트(danji/ dong/ gu/)를 기준으로 생성 → 404 방지.
apartments 테이블은 단지명 참조용으로만 사용.

출력: search_index.json
  { a: [{c,n,g,d,s}], d: [{n,g,u}], g: [{n,u}] }
  - a: 단지 (kapt_code, kapt_name, sgg, umd_nm, slug)
  - d: 동 (이름, 시군구 표시, 파일 slug)
  - g: 구 (표시 이름, 파일 slug)

URL 매핑 (클라이언트):
  /danji/{s}.html   /dong/{u}.html   /gu/{u}.html
"""
import os, sys, json, urllib.request, urllib.parse

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

if os.path.exists(".env"):
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

URL = "https://jqaxejgzkchxbfzgzyzi.supabase.co"
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not KEY:
    sys.exit("[ERR] SUPABASE_SERVICE_ROLE_KEY 없음")


def list_slugs(dir_name):
    if not os.path.isdir(dir_name):
        return set()
    return {
        f[:-5] for f in os.listdir(dir_name)
        if f.endswith(".html") and f != "index.html"
    }


def fetch_apartments():
    items = []
    offset = 0
    BATCH = 1000
    while True:
        params = {
            "select": "kapt_code,kapt_name,sgg,umd_nm,slug",
            "kapt_code": "like.A*",
            "limit": str(BATCH),
            "offset": str(offset),
            "order": "kapt_code",
        }
        url = f"{URL}/rest/v1/apartments?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "apikey": KEY,
            "Authorization": f"Bearer {KEY}",
        })
        with urllib.request.urlopen(req) as r:
            rows = json.loads(r.read())
        if not rows:
            break
        items.extend(rows)
        if len(rows) < BATCH:
            break
        offset += BATCH
    return items


def main():
    print("[1/4] 실제 HTML 파일 스캔 중...")
    danji_slugs = list_slugs("danji")
    dong_slugs = list_slugs("dong")
    gu_slugs = list_slugs("gu")
    print(f"      danji {len(danji_slugs):,}, dong {len(dong_slugs):,}, gu {len(gu_slugs):,}")

    print("[2/4] apartments 로드 중...")
    apts = fetch_apartments()
    print(f"      총 {len(apts):,}개")

    # 단지 인덱스 — slug가 실제 HTML 파일에 존재하는 것만
    a_items = []
    for a in apts:
        slug = a.get("slug") or ""
        if slug in danji_slugs:
            a_items.append({
                "c": a["kapt_code"],
                "n": a["kapt_name"],
                "g": a.get("sgg") or "",
                "d": a.get("umd_nm") or "",
                "s": slug,
            })

    # 동 인덱스 — 파일 slug 그대로, 표시 이름은 파싱
    d_items = []
    for slug in sorted(dong_slugs):
        parts = slug.split("-")
        if len(parts) < 2:
            continue
        dong_name = parts[-1]
        sigungu = " ".join(parts[1:-1])  # 시도 제외, 동 제외 나머지
        d_items.append({"n": dong_name, "g": sigungu, "u": slug})

    # 구 인덱스 — 파일 slug 그대로, 표시 이름은 하이픈→공백
    g_items = []
    for slug in sorted(gu_slugs):
        name = slug.replace("-", " ")
        g_items.append({"n": name, "u": slug})

    print(f"[3/4] 인덱스 생성: 단지 {len(a_items):,}, 동 {len(d_items):,}, 구 {len(g_items):,}")

    out = {"a": a_items, "d": d_items, "g": g_items}
    out_path = "search_index.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(out_path)
    print(f"[4/4] 저장: {out_path}  ({size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
