# -*- coding: utf-8 -*-
"""
seed_apartments.py — 전국 확장용 apartments 테이블 초기 시딩

국토부 단지 API 2개 + 카카오 지오코딩으로 apartments 테이블에 신규 시도 단지 일괄 삽입.
수도권은 이미 채워져 있으므로, 신규 확장 지역(부산/대구/광주/대전/울산 등)에 대해서만 실행.

흐름:
  1. AptListService3/getSigunguAptList3 — 시군구별 단지코드 목록 (bjdCode, kaptName, as1~3)
  2. AptBasisInfoServiceV4/getAphusBassInfoV4 — 각 단지 상세 (세대수, 주소, 입주일, 시공사, 층수 등)
  3. Kakao address.json — doroJuso → lat/lon
  4. Supabase apartments 테이블 POST (resolution=merge-duplicates)

사용법:
  python seed_apartments.py --sido busan            # 부산 전체 (16개 시군구)
  python seed_apartments.py --sigungu 29110         # 특정 시군구만 (광주 동구 등 테스트용)
  python seed_apartments.py --sido all              # 5개 광역시 전체
  python seed_apartments.py --sigungu 29110 --dry   # 실제 저장 없이 출력만
"""

import os
import sys
import json
import time
import ssl
import argparse
import urllib3
import requests
from requests.adapters import HTTPAdapter

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

urllib3.disable_warnings()

# ── 환경변수 ──
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

GOV_SERVICE_KEY = os.environ.get("GOV_SERVICE_KEY", "")
KAKAO_REST_KEY = os.environ.get("KAKAO_REST_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://jqaxejgzkchxbfzgzyzi.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not GOV_SERVICE_KEY:
    print("❌ GOV_SERVICE_KEY 없음 (.env)")
    sys.exit(1)
if not KAKAO_REST_KEY:
    print("❌ KAKAO_REST_KEY 없음 (.env)")
    sys.exit(1)
if not SUPABASE_KEY:
    print("❌ SUPABASE_SERVICE_ROLE_KEY 없음 (.env)")
    sys.exit(1)

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

LIST_URL = "https://apis.data.go.kr/1613000/AptListService3/getSigunguAptList3"
DETAIL_URL = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4"
KAKAO_GEO_URL = "https://dapi.kakao.com/v2/local/search/address.json"


# ── 5대 광역시 LAWD_CD 매핑 ──
SIDO_SIGUNGU = {
    "busan": {
        "name": "부산광역시",
        "sigungu": {
            "26110": "중구",   "26140": "서구",     "26170": "동구",
            "26200": "영도구", "26230": "부산진구", "26260": "동래구",
            "26290": "남구",   "26320": "북구",     "26350": "해운대구",
            "26380": "사하구", "26410": "금정구",   "26440": "강서구",
            "26470": "연제구", "26500": "수영구",   "26530": "사상구",
            "26710": "기장군",
        },
    },
    "daegu": {
        "name": "대구광역시",
        "sigungu": {
            "27110": "중구", "27140": "동구",   "27170": "서구",
            "27200": "남구", "27230": "북구",   "27260": "수성구",
            "27290": "달서구","27710": "달성군", "27720": "군위군",
        },
    },
    "gwangju": {
        "name": "광주광역시",
        "sigungu": {
            "29110": "동구", "29140": "서구", "29155": "남구",
            "29170": "북구", "29200": "광산구",
        },
    },
    "daejeon": {
        "name": "대전광역시",
        "sigungu": {
            "30110": "동구", "30140": "중구", "30170": "서구",
            "30200": "유성구","30230": "대덕구",
        },
    },
    "ulsan": {
        "name": "울산광역시",
        "sigungu": {
            "31110": "중구", "31140": "남구", "31170": "동구",
            "31200": "북구", "31710": "울주군",
        },
    },
}


# ── HTTP 세션 (정부 API는 TLS 구버전 호환 필요) ──
class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

gov_session = requests.Session()
gov_session.mount("https://", TLSAdapter())
gov_session.verify = False

kakao_session = requests.Session()
sb_session = requests.Session()


# ── 단계 1: 시군구 단지 목록 ──
def fetch_apt_list(sigungu_code: str) -> list:
    """시군구 단지 코드/이름/법정동 목록 조회"""
    all_items = []
    page = 1
    while True:
        for attempt in range(3):
            try:
                r = gov_session.get(
                    LIST_URL,
                    params={
                        "serviceKey": GOV_SERVICE_KEY,
                        "sigunguCode": sigungu_code,
                        "numOfRows": 500,
                        "pageNo": page,
                        "_type": "json",
                    },
                    timeout=30,
                )
                if r.status_code != 200:
                    time.sleep(2)
                    continue
                body = r.json().get("response", {}).get("body", {}) or {}
                total = int(body.get("totalCount", 0) or 0)
                items = body.get("items")
                # items 변형 3가지 대응: list / {"item": list} / {"item": dict}
                if isinstance(items, list):
                    lst = items
                elif isinstance(items, dict):
                    inner = items.get("item", [])
                    lst = inner if isinstance(inner, list) else [inner] if inner else []
                else:
                    lst = []
                all_items.extend(lst)
                # 다음 페이지 필요?
                if len(all_items) >= total or not lst:
                    return all_items
                page += 1
                break
            except Exception as e:
                print(f"  ⚠️  fetch_apt_list 오류 ({sigungu_code} p{page}): {e}")
                time.sleep(2)
        else:
            return all_items
        if page > 100:  # 안전장치
            break
    return all_items


# ── 단계 2: 단지 상세 ──
def fetch_apt_detail(kapt_code: str) -> dict | None:
    """단지 상세정보 조회 (세대수, 입주일, 시공사, 층수, 난방, 주차, 단지종류)"""
    for attempt in range(3):
        try:
            r = gov_session.get(
                DETAIL_URL,
                params={
                    "serviceKey": GOV_SERVICE_KEY,
                    "kaptCode": kapt_code,
                    "_type": "json",
                },
                timeout=15,
            )
            if r.status_code != 200:
                time.sleep(1)
                continue
            item = r.json().get("response", {}).get("body", {}).get("item") or {}
            if not item or not item.get("kaptCode"):
                return None
            return item
        except Exception as e:
            if attempt == 2:
                print(f"  ⚠️  detail 실패 {kapt_code}: {e}")
            time.sleep(1)
    return None


# ── 단계 3: Kakao 지오코딩 ──
def geocode(address: str) -> tuple[float, float, str] | None:
    """도로명주소 → (lat, lon, jibun). jibun 추출 실패 시 ''"""
    if not address:
        return None
    for attempt in range(3):
        try:
            r = kakao_session.get(
                KAKAO_GEO_URL,
                headers={"Authorization": f"KakaoAK {KAKAO_REST_KEY}"},
                params={"query": address},
                timeout=10,
            )
            if r.status_code != 200:
                time.sleep(1)
                continue
            docs = r.json().get("documents", []) or []
            if not docs:
                return None
            d = docs[0]
            lat = float(d.get("y") or 0)
            lon = float(d.get("x") or 0)
            if lat <= 0 or lon <= 0:
                return None
            # 지번 주소 구조에서 bun-ji 추출 (예: "148-1")
            jibun_kakao = ""
            addr_obj = d.get("address") or {}
            main_no = (addr_obj.get("main_address_no") or "").strip()
            sub_no = (addr_obj.get("sub_address_no") or "").strip()
            if main_no:
                jibun_kakao = f"{main_no}-{sub_no}" if sub_no else main_no
            return (lat, lon, jibun_kakao)
        except Exception:
            time.sleep(1)
    return None


# ── 단계 4: Supabase 삽입 ──
def upsert_apartments(rows: list, dry_run: bool = False) -> int:
    """apartments 테이블에 upsert (kapt_code PK 기준)"""
    if not rows:
        return 0
    if dry_run:
        print(f"  [DRY RUN] {len(rows)}건 삽입 건너뜀")
        return 0

    success = 0
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        r = sb_session.post(
            f"{SUPABASE_URL}/rest/v1/apartments?on_conflict=kapt_code",
            headers={**SB_HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"},
            data=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
            timeout=60,
        )
        if r.status_code in (200, 201, 204):
            success += len(batch)
        else:
            print(f"  ❌ upsert 실패 ({r.status_code}): {r.text[:200]}")
    return success


# ── 본 처리 ──
def process_sigungu(lawd_cd: str, gu_name: str, sido_name: str, dry_run: bool) -> tuple[int, int]:
    """한 시군구 처리: 목록 → 상세 → 지오코딩 → 삽입.
    반환: (조회된 단지, 성공 삽입)"""
    print(f"\n▶ {sido_name} {gu_name} ({lawd_cd})")
    listing = fetch_apt_list(lawd_cd)
    print(f"  단지 목록: {len(listing)}개")
    if not listing:
        return 0, 0

    rows = []
    skipped_offi = 0
    skipped_geo = 0
    skipped_nodetail = 0
    skipped_other = 0

    for idx, item in enumerate(listing, 1):
        kapt_code = (item.get("kaptCode") or "").strip()
        kapt_name_list = (item.get("kaptName") or "").strip()
        bjd_code = (item.get("bjdCode") or "").strip()
        as3 = (item.get("as3") or "").strip()  # 읍면동

        if not kapt_code:
            skipped_other += 1
            continue

        # 상세 조회
        detail = fetch_apt_detail(kapt_code)
        if not detail:
            skipped_nodetail += 1
            continue

        kapt_name = (detail.get("kaptName") or kapt_name_list).strip()
        doro_juso = (detail.get("doroJuso") or "").strip()
        kapt_addr = (detail.get("kaptAddr") or "").strip()
        code_apt_nm = (detail.get("codeAptNm") or "").strip()
        households = str(detail.get("kaptdaCnt") or "").strip()
        use_date = (detail.get("kaptUsedate") or "").strip()
        top_floor = str(detail.get("kaptTopFloor") or "").strip()
        builder = (detail.get("kaptBcompany") or "").strip()
        heating = (detail.get("codeHeatNm") or "").strip()
        parking = str(detail.get("kaptTotPkCnt") or "").strip()

        # 오피스텔 제외 (프로젝트 정책)
        if "오피스텔" in code_apt_nm:
            skipped_offi += 1
            continue

        # 지번 추출 1차: kapt_addr "...동 148-1 단지명..." 패턴 (지번형 주소일 때)
        jibun = ""
        if kapt_addr and as3:
            after_dong = kapt_addr.split(as3, 1)[-1].strip()
            if after_dong:
                first_token = after_dong.split()[0] if after_dong.split() else ""
                if first_token and first_token[0].isdigit():
                    jibun = first_token

        # 지오코딩 (+ 카카오 응답에서 지번 fallback 수신)
        addr_for_geo = doro_juso or kapt_addr
        coords = geocode(addr_for_geo)
        if not coords:
            skipped_geo += 1
            print(f"  ⚠️  좌표 실패: {kapt_name} ({addr_for_geo})")
            continue
        lat, lon, jibun_kakao = coords

        # 지번 추출 2차: 1차 실패 시 카카오 역구조화 결과 사용 (도로명 주소 케이스 커버)
        if not jibun and jibun_kakao:
            jibun = jibun_kakao

        row = {
            "kapt_code": kapt_code,
            "kapt_name": kapt_name,
            "doro_juso": doro_juso,
            "jibun": jibun,
            "bjd_code": bjd_code,
            "lawd_cd": lawd_cd,
            "sido": sido_name,
            "sgg": gu_name,
            "umd_nm": as3,
            "lat": lat,
            "lon": lon,
            "property_type": "apt",
            "households": households,
            "use_date": use_date,
            "top_floor": top_floor,
            "builder": builder,
            "heating": heating,
            "parking": parking,
        }
        rows.append(row)

        if idx % 20 == 0:
            print(f"  [{idx}/{len(listing)}] 수집 중... ({len(rows)}건 준비)")

        # API 예절 (카카오 30/s, 정부 제한 불분명)
        time.sleep(0.05)

    print(
        f"  처리 완료: {len(rows)}건 준비 "
        f"(오피스텔 제외 {skipped_offi}, 상세없음 {skipped_nodetail}, "
        f"좌표실패 {skipped_geo}, 기타 {skipped_other})"
    )

    inserted = upsert_apartments(rows, dry_run=dry_run)
    print(f"  ✅ Supabase 삽입: {inserted}건")
    return len(rows), inserted


def main():
    parser = argparse.ArgumentParser(description="apartments 테이블 초기 시딩")
    parser.add_argument("--sido", choices=list(SIDO_SIGUNGU.keys()) + ["all"],
                        help="시도 단위 시딩 (busan/daegu/gwangju/daejeon/ulsan/all)")
    parser.add_argument("--sigungu", help="특정 시군구 코드만 (예: 29110=광주 동구)")
    parser.add_argument("--dry", action="store_true", help="실제 저장 없이 출력만")
    args = parser.parse_args()

    if not args.sido and not args.sigungu:
        parser.print_help()
        sys.exit(1)

    print("=" * 60)
    print("  apartments 시딩 시작")
    print(f"  DRY RUN: {args.dry}")
    print("=" * 60)

    t0 = time.time()
    targets = []  # list of (lawd_cd, gu_name, sido_name)

    if args.sigungu:
        # 단일 시군구 — 5개 광역시 전체에서 찾기
        found = False
        for sido_key, sido_info in SIDO_SIGUNGU.items():
            if args.sigungu in sido_info["sigungu"]:
                targets.append((args.sigungu, sido_info["sigungu"][args.sigungu], sido_info["name"]))
                found = True
                break
        if not found:
            print(f"❌ 알 수 없는 시군구 코드: {args.sigungu}")
            sys.exit(1)
    elif args.sido == "all":
        for sido_key, sido_info in SIDO_SIGUNGU.items():
            for code, name in sido_info["sigungu"].items():
                targets.append((code, name, sido_info["name"]))
    else:
        sido_info = SIDO_SIGUNGU[args.sido]
        for code, name in sido_info["sigungu"].items():
            targets.append((code, name, sido_info["name"]))

    total_prepared = 0
    total_inserted = 0
    for lawd_cd, gu_name, sido_name in targets:
        prepared, inserted = process_sigungu(lawd_cd, gu_name, sido_name, args.dry)
        total_prepared += prepared
        total_inserted += inserted

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(f"  시군구 {len(targets)}개 처리 완료 ({elapsed:.1f}s)")
    print(f"  준비: {total_prepared}건 / 삽입: {total_inserted}건")
    print("=" * 60)


if __name__ == "__main__":
    main()
