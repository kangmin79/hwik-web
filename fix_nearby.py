"""nearby_subway/nearby_school 복구 스크립트
danji_pages에서 좌표가 있는 전체 단지에 대해
stations/schools 테이블과 거리 계산 후 업데이트
"""
import requests, math, os, sys, time, json
from concurrent.futures import ThreadPoolExecutor, as_completed

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://api.hwik.kr")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not SUPABASE_KEY:
    print("❌ SUPABASE_SERVICE_ROLE_KEY 환경변수 필요")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}
HEADERS_READ = {**HEADERS, "Prefer": ""}

session = requests.Session()


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p = math.pi / 180
    a = (
        0.5 - math.cos((lat2 - lat1) * p) / 2
        + math.cos(lat1 * p) * math.cos(lat2 * p)
        * (1 - math.cos((lon2 - lon1) * p)) / 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def load_all(table, select, filter_fn=None):
    items = []
    offset = 0
    while True:
        r = session.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS_READ,
            params={"select": select, "offset": offset, "limit": 1000},
            timeout=30,
        )
        data = r.json() if r.status_code == 200 else []
        if not data:
            break
        items.extend(data)
        offset += 1000
        if len(data) < 1000:
            break
    if filter_fn:
        items = [x for x in items if filter_fn(x)]
    return items


def main():
    print("📍 nearby_subway/nearby_school 복구 시작\n")

    # 1) 지하철역 로드
    stations = load_all("stations", "name,line,lat,lon")
    print(f"  🚇 {len(stations)}개 역 로드")

    # 2) 학교 로드 (수도권)
    schools = load_all(
        "schools", "name,type,lat,lon",
        filter_fn=lambda s: s.get("lat") and 36.9 < s["lat"] < 38.3 and 126.3 < s.get("lon", 0) < 127.9
    )
    print(f"  🏫 {len(schools)}개 학교 로드")

    # 안전 검증: 데이터 0건이면 인증 실패 의심 → 즉시 중단
    if not stations:
        print("❌ 지하철역 0건 — 인증 실패 의심. 중단합니다.")
        sys.exit(1)
    if not schools:
        print("❌ 학교 0건 — 인증 실패 의심. 중단합니다.")
        sys.exit(1)

    # 3) danji_pages 전체 로드 (id, lat, lng만)
    danji = load_all("danji_pages", "id,lat,lng")
    print(f"  🏢 {len(danji)}개 단지 로드\n")

    # 4) 각 단지별 nearby 계산
    updates = []
    for d in danji:
        lat1 = d.get("lat")
        lon1 = d.get("lng")
        if not lat1 or not lon1:
            continue

        # 지하철: 1km 이내, 가까운 순 3개
        nearby_st = []
        for s in stations:
            dist = haversine(lat1, lon1, s.get("lat", 0), s.get("lon", 0))
            if dist < 1000:
                nearby_st.append({
                    "name": s["name"],
                    "line": s.get("line", ""),
                    "distance": round(dist),
                })
        nearby_st.sort(key=lambda x: x["distance"])
        nearby_st = nearby_st[:3]

        # 학교: 1.5km 이내, 초/중/고 각 1개
        candidates = []
        for s in schools:
            dist = haversine(lat1, lon1, s.get("lat", 0), s.get("lon", 0))
            if dist < 1500:
                candidates.append({
                    "name": s["name"],
                    "type": s.get("type", ""),
                    "distance": round(dist),
                })
        candidates.sort(key=lambda x: x["distance"])
        nearby_sc = []
        picked = set()
        for s in candidates:
            t = s["type"]
            cat = "초" if "초등" in t else ("중" if "중학" in t else ("고" if "고등" in t else None))
            if cat and cat not in picked:
                nearby_sc.append(s)
                picked.add(cat)
            if len(picked) >= 3:
                break

        updates.append({
            "id": d["id"],
            "nearby_subway": nearby_st,
            "nearby_school": nearby_sc,
        })

    print(f"  ✅ {len(updates)}개 단지 nearby 계산 완료\n")

    # 5) 병렬 PATCH로 nearby만 업데이트
    patch_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    total = 0
    errors = 0

    def patch_one(u):
        s = requests.Session()
        did = u["id"]
        body = {
            "nearby_subway": u["nearby_subway"],
            "nearby_school": u["nearby_school"],
        }
        for attempt in range(3):
            try:
                resp = s.patch(
                    f"{SUPABASE_URL}/rest/v1/danji_pages?id=eq.{did}",
                    headers=patch_headers,
                    json=body,
                    timeout=15,
                )
                if resp.status_code in (200, 204):
                    return True
                if attempt == 2:
                    return f"{did}: {resp.status_code}"
            except Exception as e:
                if attempt == 2:
                    return f"{did}: {e}"
                time.sleep(0.5)
        return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(patch_one, u): u for u in updates}
        for i, fut in enumerate(as_completed(futures)):
            result = fut.result()
            if result is True:
                total += 1
            else:
                errors += 1
                if isinstance(result, str):
                    print(f"  ⚠️ {result}")
            if (i + 1) % 2000 == 0:
                print(f"  ... {i+1}/{len(updates)} 완료")

    print(f"\n✅ {total}개 단지 nearby 복구 완료 (에러: {errors}건)")


if __name__ == "__main__":
    main()
