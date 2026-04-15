# -*- coding: utf-8 -*-
"""
sync_trades.py — sitemap 재생성 + 주변 단지/시설 업데이트

구 파이프라인(trade_cache 기반) 완전 제거 — 2026-04-13
  - 실거래 수집: collect_trades_v2.py → trade_raw_v2
  - 집계:        build_danji_from_v2.py → danji_pages

이 파일이 하는 일:
  1. sitemap.xml 재생성  (--sitemap-only, GitHub Actions에서 사용)
  2. 주변 단지/시설 업데이트  (--nearby-only, 필요 시 수동 실행)

사용법:
  python sync_trades.py --sitemap-only     # sitemap만 재생성
  python sync_trades.py --nearby-only      # 주변 단지/지하철/학교 업데이트
"""

import os
import sys
import time
import argparse
from datetime import datetime
from collections import defaultdict

import requests

# UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)


# ── 환경변수 로드 ──────────────────────────────────────
def _load_env():
    for fname in (".env", "env"):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://api.hwik.kr")
SUPABASE_URL_FALLBACK = "https://jqaxejgzkchxbfzgzyzi.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_KEY:
    print("❌ SUPABASE_SERVICE_ROLE_KEY 없음")
    sys.exit(1)

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

sb_session = requests.Session()

from regions import ALL_REGIONS


# ========================================================
# apartments 로드
# ========================================================
def load_apartments():
    """apartments 테이블에서 단지 목록 로드"""
    all_apts = []
    offset = 0
    limit = 1000
    while True:
        data = None
        for attempt in range(3):
            try:
                resp = sb_session.get(
                    f"{SUPABASE_URL}/rest/v1/apartments",
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                    params={
                        "select": "kapt_code,kapt_name,doro_juso,lat,lon,lawd_cd,property_type,households,use_date,sgg,umd_nm,pyeongs,slug,top_floor,parking,heating,builder,mgmt_fee",
                        "limit": str(limit),
                        "offset": str(offset),
                    },
                    timeout=90,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    break
                else:
                    print(f"  ⚠️ apartments 로드 {resp.status_code} (재시도 {attempt+1}/3)")
            except Exception as e:
                print(f"  ⚠️ apartments 로드 실패: {e} (재시도 {attempt+1}/3)")
            time.sleep(5)
        if not data:
            break
        all_apts.extend(data)
        offset += limit
        if len(data) < limit:
            break

    print(f"📦 apartments: {len(all_apts)}개 로드")
    return all_apts


# ========================================================
# 주변 단지 매칭
# ========================================================
def fill_nearby_complex(danji_list: list, apartments: list):
    """같은 property_type + 좌표 가까운 단지 5개를 nearby_complex에 채움"""
    import math

    name_to_type = {}
    for apt in apartments:
        name_to_type[apt.get("kapt_name", "")] = apt.get("property_type", "apt")

    def get_prop_type(danji):
        return name_to_type.get(danji.get("complex_name", ""), "apt")

    def haversine(lat1, lon1, lat2, lon2):
        if not all([lat1, lon1, lat2, lon2]):
            return 99999
        R = 6371000
        p = math.pi / 180
        a = 0.5 - math.cos((lat2-lat1)*p)/2 + math.cos(lat1*p)*math.cos(lat2*p)*(1-math.cos((lon2-lon1)*p))/2
        return R * 2 * math.asin(math.sqrt(a))

    type_groups = defaultdict(list)
    for d in danji_list:
        pt = get_prop_type(d)
        type_groups[pt].append(d)

    filled = 0
    for d in danji_list:
        pt = get_prop_type(d)
        lat1, lon1 = d.get("lat"), d.get("lng")
        if not lat1 or not lon1:
            continue

        candidates = []
        for other in type_groups[pt]:
            if other["id"] == d["id"]:
                continue
            dist = haversine(lat1, lon1, other.get("lat"), other.get("lng"))
            if dist < 2000:
                rt = other.get("recent_trade") or {}
                other_pm = other.get("pyeongs_map") or {}
                prices = {}
                for k, v in rt.items():
                    if "_" not in k and k.isdigit():
                        area = int(k)
                        supply = None
                        if str(area) in other_pm:
                            supply = round(other_pm[str(area)].get("supply", 0)) or None
                        prices[k] = {
                            "price": v.get("price"),
                            "date": v.get("date"),
                            "exclu": area,
                            "supply": supply,
                        }
                if not prices:
                    continue
                candidates.append({
                    "id": other["id"],
                    "name": other["complex_name"],
                    "location": other.get("location", ""),
                    "distance": round(dist),
                    "prices": prices,
                })

        candidates.sort(key=lambda x: x["distance"])
        d["nearby_complex"] = candidates[:5]
        if candidates:
            filled += 1

    print(f"  → {filled}개 단지에 주변 단지 매칭 완료")


# ========================================================
# 주변 지하철/학교 매칭
# ========================================================
def fill_nearby_facilities(danji_list: list):
    """각 단지에서 가장 가까운 지하철역 3개, 학교 3개를 매칭"""
    import math

    def haversine(lat1, lon1, lat2, lon2):
        if not all([lat1, lon1, lat2, lon2]):
            return 99999
        R = 6371000
        p = math.pi / 180
        a = 0.5 - math.cos((lat2-lat1)*p)/2 + math.cos(lat1*p)*math.cos(lat2*p)*(1-math.cos((lon2-lon1)*p))/2
        return R * 2 * math.asin(math.sqrt(a))

    print("  지하철역 로드 중...")
    stations = []
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/stations",
            headers={**SB_HEADERS, "Prefer": ""},
            params={"select": "name,line,lat,lon", "offset": offset, "limit": 1000}
        )
        data = resp.json() if resp.status_code == 200 else []
        if not data:
            break
        stations.extend(data)
        offset += 1000
        if len(data) < 1000:
            break
    print(f"  → {len(stations)}개 역 로드")

    print("  학교 로드 중...")
    schools = []
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/schools",
            headers={**SB_HEADERS, "Prefer": ""},
            params={"select": "name,type,lat,lon", "lat": "gte.36.9", "offset": offset, "limit": 1000}
        )
        data = resp.json() if resp.status_code == 200 else []
        if not data:
            break
        schools.extend(data)
        offset += 1000
        if len(data) < 1000:
            break
    schools = [s for s in schools if s.get("lat") and 36.9 < s["lat"] < 38.3 and 126.3 < s.get("lon", 0) < 127.9]
    print(f"  → {len(schools)}개 학교 로드 (수도권)")

    filled = 0
    for d in danji_list:
        lat1 = d.get("lat")
        lon1 = d.get("lng")
        if not lat1 or not lon1:
            continue

        nearby_st = []
        for s in stations:
            dist = haversine(lat1, lon1, s.get("lat"), s.get("lon"))
            if dist < 1000:
                nearby_st.append({"name": s["name"], "line": s.get("line", ""), "distance": round(dist)})
        nearby_st.sort(key=lambda x: x["distance"])
        d["nearby_subway"] = nearby_st[:3]

        school_candidates = []
        for s in schools:
            dist = haversine(lat1, lon1, s.get("lat"), s.get("lon"))
            if dist < 1500:
                school_candidates.append({"name": s["name"], "type": s.get("type", ""), "distance": round(dist)})
        school_candidates.sort(key=lambda x: x["distance"])
        nearby_sc = []
        picked = set()
        for s in school_candidates:
            t = s["type"]
            cat = "초" if "초등" in t else ("중" if "중학" in t else ("고" if "고등" in t else None))
            if cat and cat not in picked:
                nearby_sc.append(s)
                picked.add(cat)
            if len(picked) >= 3:
                break
        d["nearby_school"] = nearby_sc

        if nearby_st or nearby_sc:
            filled += 1

    print(f"  → {filled}개 단지에 지하철/학교 매칭 완료")


# ========================================================
# danji_pages nearby 필드 업데이트
# ========================================================
def update_nearby(danji_list: list):
    """nearby_subway, nearby_school, nearby_complex만 danji_pages에 upsert"""
    if not danji_list:
        return 0

    rows = []
    for d in danji_list:
        row = {"id": d["id"]}
        if d.get("nearby_subway") is not None:
            row["nearby_subway"] = d["nearby_subway"]
        if d.get("nearby_school") is not None:
            row["nearby_school"] = d["nearby_school"]
        if d.get("nearby_complex") is not None:
            row["nearby_complex"] = d["nearby_complex"]
        if len(row) > 1:
            rows.append(row)

    total = 0
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        for attempt in range(3):
            try:
                resp = sb_session.post(
                    f"{SUPABASE_URL}/rest/v1/danji_pages?on_conflict=id",
                    headers=SB_HEADERS,
                    json=batch,
                    timeout=60,
                )
                if resp.status_code in (200, 201):
                    total += len(batch)
                else:
                    print(f"  ⚠️ nearby upsert 실패: {resp.status_code} {resp.text[:200]}")
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(3)
                else:
                    print(f"  ⚠️ nearby upsert 예외: {e}")
    return total


# ========================================================
# sitemap 생성
# ========================================================
def generate_sitemap(danji_list: list):
    """DB 전체 danji_pages 기반 sitemap.xml 생성"""
    base = "https://hwik.kr"
    today = datetime.now().strftime("%Y-%m-%d")

    all_danji = []
    offset = 0
    while True:
        resp = sb_session.get(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            headers={**SB_HEADERS, "Prefer": ""},
            params={"select": "id,complex_name,location,address,updated_at,categories,recent_trade", "order": "id", "offset": offset, "limit": 500},
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else []
        if not data:
            break
        all_danji.extend(data)
        offset += 500
        if len(data) < 500:
            break
        time.sleep(0.2)

    from urllib.parse import quote as _quote
    from slug_utils import make_danji_slug as _make_slug, make_dong_slug as _make_dong_slug

    urls = []
    static_pages = [
        ('/', 'daily', '1.0'),
        ('/about.html', 'monthly', '0.3'),
    ]
    for path, freq, pri in static_pages:
        urls.append(f'  <url><loc>{base}{path}</loc><lastmod>{today}</lastmod><changefreq>{freq}</changefreq><priority>{pri}</priority></url>')

    # dong 인덱스 페이지
    dong_index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dong", "index.html")
    if os.path.isfile(dong_index_path):
        urls.append(f'  <url><loc>{base}/dong/</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>')

    gu_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gu")
    if os.path.isdir(gu_dir):
        urls.append(f'  <url><loc>{base}/gu/</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>')
        for fname in sorted(os.listdir(gu_dir)):
            if fname.endswith(".html") and fname != "index.html":
                slug = fname[:-5]
                safe = _quote(slug, safe='-')
                urls.append(f'  <url><loc>{base}/gu/{safe}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>')

    rank_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ranking")
    if os.path.isdir(rank_dir):
        urls.append(f'  <url><loc>{base}/ranking/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>')
        for fname in sorted(os.listdir(rank_dir)):
            if fname.endswith(".html") and fname != "index.html":
                slug = fname[:-5]
                urls.append(f'  <url><loc>{base}/ranking/{slug}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>0.7</priority></url>')

    danji_html_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "danji")
    existing_slugs = set()
    if os.path.isdir(danji_html_dir):
        existing_slugs = {f[:-5] for f in os.listdir(danji_html_dir) if f.endswith(".html")}
    included = 0
    excluded = 0
    for d in all_danji:
        did = d.get("id", "")
        if not did:
            continue
        if did.startswith("offi-") or did.startswith("apt-"):
            excluded += 1
            continue
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []
        has_trade = any(rt.get(c) for c in cats)
        if not has_trade:
            excluded += 1
            continue
        slug = _make_slug(d.get("complex_name", ""), d.get("location", ""), did, d.get("address", ""))
        safe_slug = _quote(slug, safe="-")
        if existing_slugs and slug not in existing_slugs:
            excluded += 1
            continue
        latest_trade_date = ""
        for c in cats:
            td = (rt.get(c) or {}).get("date", "")
            if td and td > latest_trade_date:
                latest_trade_date = td
        lastmod = latest_trade_date[:10] if latest_trade_date else (d.get("updated_at") or today)[:10]
        urls.append(f'  <url><loc>{base}/danji/{safe_slug}</loc><lastmod>{lastmod}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>')
        included += 1

    from collections import defaultdict as _defaultdict
    from slug_utils import detect_region as _detect_region
    dong_trade_count = _defaultdict(int)
    dong_addr_cache = {}
    dong_latest_date = {}
    for d in all_danji:
        if (d.get("id") or "").startswith("offi-"):
            continue
        loc = d.get("location", "")
        if not loc:
            continue
        parts = loc.split(" ", 1)
        if len(parts) < 2:
            continue
        region = _detect_region(d.get("address", "") or "")
        if not region:
            continue
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []
        if any(rt.get(c) for c in cats):
            key = (region, parts[0], parts[1])
            dong_trade_count[key] += 1
            addr_val = d.get("address", "") or ""
            if addr_val and (key not in dong_addr_cache or not dong_addr_cache[key]):
                dong_addr_cache[key] = addr_val
            for c in cats:
                td = (rt.get(c) or {}).get("date", "")
                if td and td > dong_latest_date.get(key, ""):
                    dong_latest_date[key] = td

    dong_html_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dong")
    existing_dong_slugs = set()
    if os.path.isdir(dong_html_dir):
        # index.html 제외하고 실제 동 슬러그만 수집
        existing_dong_slugs = {
            f[:-5] for f in os.listdir(dong_html_dir)
            if f.endswith(".html") and f != "index.html"
        }

    dong_count = 0
    seen_dong_slugs = set()
    # trade 기반 slug set (cnt>=1 이면 포함 — HTML이 존재하면 sitemap에 등록)
    trade_based_slugs = set()
    for (region, gu, dong), cnt in dong_trade_count.items():
        addr = dong_addr_cache.get((region, gu, dong), "")
        trade_based_slugs.add(_make_dong_slug(gu, dong, addr))

    for (region, gu, dong), cnt in sorted(dong_trade_count.items()):
        if cnt < 3:
            continue
        addr = dong_addr_cache.get((region, gu, dong), "")
        dong_slug = _make_dong_slug(gu, dong, addr)
        safe_dong_slug = _quote(dong_slug, safe="-")
        if safe_dong_slug in seen_dong_slugs:
            continue
        if existing_dong_slugs and dong_slug not in existing_dong_slugs:
            continue
        seen_dong_slugs.add(safe_dong_slug)
        dong_lastmod = dong_latest_date.get((region, gu, dong), today)[:10]
        urls.append(f'  <url><loc>{base}/dong/{safe_dong_slug}</loc><lastmod>{dong_lastmod}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>')
        dong_count += 1

    # cnt < 3 이지만 HTML 파일이 존재하는 동 페이지도 sitemap에 등록 (priority 낮춤)
    for slug in sorted(existing_dong_slugs - seen_dong_slugs):
        safe_slug = _quote(slug, safe="-")
        urls.append(f'  <url><loc>{base}/dong/{safe_slug}</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.6</priority></url>')
        dong_count += 1

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += '\n'.join(urls)
    xml += '\n</urlset>\n'

    sitemap_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"\n🗺️  sitemap.xml 생성: 단지 {included}개 + 동 {dong_count}개 포함, {excluded}개 제외")


# ========================================================
# 메인
# ========================================================
def main():
    parser = argparse.ArgumentParser(description="sitemap 재생성 / 주변 단지·시설 업데이트")
    parser.add_argument("--sitemap-only", action="store_true", help="sitemap.xml 재생성")
    parser.add_argument("--nearby-only",  action="store_true", help="주변 단지/지하철/학교 업데이트")
    args = parser.parse_args()

    # DB 연결 테스트 + fallback
    global SUPABASE_URL
    for url in [SUPABASE_URL, SUPABASE_URL_FALLBACK]:
        try:
            r = sb_session.get(
                f"{url}/rest/v1/apartments?select=kapt_code&limit=1",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                timeout=15,
            )
            if r.status_code == 200:
                SUPABASE_URL = url
                print(f"✅ DB 연결: {url}")
                break
        except Exception:
            pass
    else:
        print("❌ DB 연결 실패")
        sys.exit(1)

    if args.sitemap_only:
        print("🗺️  sitemap 재생성 중...")
        generate_sitemap([])
        return

    if args.nearby_only:
        print("🏘️  주변 단지/시설 업데이트 중...")
        apartments = load_apartments()

        # danji_pages에서 lat/lng/id/complex_name/recent_trade/pyeongs_map 로드
        danji_list = []
        offset = 0
        while True:
            resp = sb_session.get(
                f"{SUPABASE_URL}/rest/v1/danji_pages",
                headers={**SB_HEADERS, "Prefer": ""},
                params={"select": "id,complex_name,location,lat,lng,recent_trade,pyeongs_map",
                        "order": "id", "offset": offset, "limit": 500},
                timeout=30,
            )
            data = resp.json() if resp.status_code == 200 else []
            if not data:
                break
            danji_list.extend(data)
            offset += 500
            if len(data) < 500:
                break
        print(f"📦 danji_pages: {len(danji_list)}개 로드")

        fill_nearby_complex(danji_list, apartments)
        fill_nearby_facilities(danji_list)
        updated = update_nearby(danji_list)
        print(f"✅ {updated}개 nearby 업데이트 완료")
        return

    print("사용법:")
    print("  python sync_trades.py --sitemap-only   # sitemap 재생성")
    print("  python sync_trades.py --nearby-only    # 주변 단지/시설 업데이트")
    print()
    print("실거래 수집/집계는 새 파이프라인 사용:")
    print("  python collect_trades_v2.py --region all  # 실거래 수집")
    print("  python build_danji_from_v2.py --region all  # 집계")


if __name__ == "__main__":
    main()
