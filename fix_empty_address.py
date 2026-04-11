# -*- coding: utf-8 -*-
"""
fix_empty_address.py — apartments.doro_juso 및 danji_pages.address 가 빈 행을
Kakao 역지오코딩으로 보충 (lat/lon → 도로명주소).

사용법:
  python fix_empty_address.py           # 실제 업데이트
  python fix_empty_address.py --dry     # 드라이런
"""
import os, sys, time, json, argparse, requests

# .env 로드
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

SB_URL = os.environ.get("SUPABASE_URL", "https://jqaxejgzkchxbfzgzyzi.supabase.co")
SB_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
KAKAO_KEY = os.environ.get("KAKAO_REST_KEY", "")

if not SB_KEY or not KAKAO_KEY:
    print("SUPABASE_SERVICE_ROLE_KEY / KAKAO_REST_KEY missing")
    sys.exit(1)

H = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"}
UH = {**H, "Content-Type": "application/json", "Prefer": "return=minimal"}
COORD2ADDR = "https://dapi.kakao.com/v2/local/geo/coord2address.json"


def fetch_empty_address_rows():
    """apartments 중 doro_juso 가 비고 lat/lon 이 있는 행"""
    all_rows = []
    offset = 0
    while True:
        r = requests.get(
            f"{SB_URL}/rest/v1/apartments",
            headers={**H, "Range": f"{offset}-{offset + 999}"},
            params={
                "select": "kapt_code,kapt_name,doro_juso,lat,lon",
                "lat": "not.is.null",
                "lon": "not.is.null",
                "order": "kapt_code",
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"조회 실패: {r.status_code} {r.text[:200]}")
            break
        batch = r.json()
        if not batch:
            break
        for row in batch:
            dj = (row.get("doro_juso") or "").strip()
            if not dj:
                all_rows.append(row)
        if len(batch) < 1000:
            break
        offset += 1000
    return all_rows


def reverse_geocode_road(lat, lon):
    """Kakao coord2address → 도로명주소 문자열"""
    try:
        r = requests.get(
            COORD2ADDR,
            headers={"Authorization": f"KakaoAK {KAKAO_KEY}"},
            params={"x": str(lon), "y": str(lat), "input_coord": "WGS84"},
            timeout=10,
        )
        if r.status_code != 200:
            return ""
        docs = r.json().get("documents", []) or []
        if not docs:
            return ""
        road = docs[0].get("road_address") or {}
        addr = (road.get("address_name") or "").strip()
        if addr:
            return addr
        # fallback: 지번주소
        jibun = docs[0].get("address") or {}
        return (jibun.get("address_name") or "").strip()
    except Exception:
        return ""


def update_apartment_address(kapt_code, address):
    r = requests.patch(
        f"{SB_URL}/rest/v1/apartments?kapt_code=eq.{kapt_code}",
        headers=UH,
        data=json.dumps({"doro_juso": address}).encode("utf-8"),
        timeout=30,
    )
    return r.status_code in (200, 204)


def update_danji_page_address(kapt_code, address):
    """danji_pages.address 동기화. id = kapt_code.lower() 형식."""
    danji_id = (kapt_code or "").lower()
    r = requests.patch(
        f"{SB_URL}/rest/v1/danji_pages?id=eq.{danji_id}",
        headers=UH,
        data=json.dumps({"address": address}).encode("utf-8"),
        timeout=30,
    )
    return r.status_code in (200, 204)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    print("빈 doro_juso 조회 중...")
    rows = fetch_empty_address_rows()
    print(f"  대상: {len(rows)}건")
    if not rows:
        print("빈 address 없음")
        return

    if args.dry:
        print("\n[DRY] 샘플 10건:")
        for r in rows[:10]:
            print(f"  {r.get('kapt_code')} | {r.get('kapt_name')} | lat={r.get('lat')} lon={r.get('lon')}")
        return

    filled = 0
    failed = 0
    for i, row in enumerate(rows, 1):
        lat = row.get("lat")
        lon = row.get("lon")
        if not lat or not lon:
            failed += 1
            continue
        addr = reverse_geocode_road(lat, lon)
        if addr:
            ok1 = update_apartment_address(row["kapt_code"], addr)
            update_danji_page_address(row["kapt_code"], addr)  # best-effort
            if ok1:
                filled += 1
            else:
                failed += 1
        else:
            failed += 1
        if i % 10 == 0:
            print(f"  [{i}/{len(rows)}] 성공 {filled}, 실패 {failed}")
        time.sleep(0.05)

    print(f"\n완료: 성공 {filled} / 실패 {failed} / 대상 {len(rows)}")


if __name__ == "__main__":
    main()
