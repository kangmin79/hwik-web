# -*- coding: utf-8 -*-
"""
collect_complexes.py — K-apt 단지 마스터 수집
아파트 단지 목록 + BassInfo + DtlInfo → apartments 테이블 upsert

사용법:
  python collect_complexes.py --sigungu 11260          # 중랑구 테스트
  python collect_complexes.py --region seoul           # 서울 전체
  python collect_complexes.py --region all             # 서울+인천+경기 전체
  python collect_complexes.py --sigungu 11260 --dry    # 저장 안 하고 출력만
"""

import os
import sys
import ssl
import time
import argparse
import json

import requests
import urllib3
from requests.adapters import HTTPAdapter

# UTF-8 출력
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

urllib3.disable_warnings()


# ── 환경변수 로드 ──────────────────────────────────────────
def _load_env():
    for fname in (".env", "env"):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

GOV_KEY    = os.environ.get("GOV_SERVICE_KEY", "")
SB_URL     = os.environ.get("SUPABASE_URL", "https://api.hwik.kr")
SB_KEY     = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
KAKAO_KEY  = os.environ.get("KAKAO_REST_API_KEY", "") or os.environ.get("KAKAO_REST_KEY", "")

if not GOV_KEY:
    sys.exit("❌ GOV_SERVICE_KEY 없음")
if not SB_KEY:
    sys.exit("❌ SUPABASE_SERVICE_ROLE_KEY 없음")
if not KAKAO_KEY:
    print("⚠️  KAKAO_REST_API_KEY 없음 — 좌표 취득 불가, 기존 좌표 유지")

SB_HEADERS = {
    "apikey": SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",  # kapt_code 기준 upsert
}


# ── SSL 우회 (정부 API) ────────────────────────────────────
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
sb_session    = requests.Session()


# ── API 엔드포인트 ─────────────────────────────────────────
LIST_URL  = "https://apis.data.go.kr/1613000/AptListService3/getSigunguAptList3"
BASS_URL  = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4"
DTL_URL   = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusDtlInfoV4"
KAKAO_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


# ── 지역 코드 ─────────────────────────────────────────────
from regions import (
    SEOUL_GU, INCHEON_GU, GYEONGGI_SI,
    BUSAN_GU, DAEGU_GU, GWANGJU_GU, DAEJEON_GU, ULSAN_GU,
    SEJONG_SI, CHUNGBUK_SI, CHUNGNAM_SI,
    JEONBUK_SI, JEONNAM_SI, GYEONGBUK_SI, GYEONGNAM_SI,
    GANGWON_SI, JEJU_SI,
)
from slug_utils import make_danji_slug

REGION_MAP = {
    "seoul":     SEOUL_GU,
    "incheon":   INCHEON_GU,
    "gyeonggi":  GYEONGGI_SI,
    "busan":     BUSAN_GU,
    "daegu":     DAEGU_GU,
    "gwangju":   GWANGJU_GU,
    "daejeon":   DAEJEON_GU,
    "ulsan":     ULSAN_GU,
    "sejong":    SEJONG_SI,
    "chungbuk":  CHUNGBUK_SI,
    "chungnam":  CHUNGNAM_SI,
    "jeonbuk":   JEONBUK_SI,
    "jeonnam":   JEONNAM_SI,
    "gyeongbuk": GYEONGBUK_SI,
    "gyeongnam": GYEONGNAM_SI,
    "gangwon":   GANGWON_SI,
    "jeju":      JEJU_SI,
}


# ── 파싱 유틸 ─────────────────────────────────────────────
def _int(s, default=None):
    try:
        v = str(s).replace(",", "").strip()
        if not v:
            return default
        return int(float(v))  # float 먼저 변환 (225.0 같은 값 처리)
    except (ValueError, TypeError):
        return default

def _float(s, default=None):
    try:
        v = str(s).replace(",", "").strip()
        return float(v) if v else default
    except (ValueError, TypeError):
        return default

def _str(s):
    v = str(s).strip() if s else ""
    return v if v else None


# ── K-apt API 호출 (재시도) ────────────────────────────────
def _kapt_get(url, params, retries=3):
    for attempt in range(retries):
        try:
            resp = gov_session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json().get("response", {}).get("body", {})
            return body
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                raise e
    return {}


# ── 단지 목록 수집 (전체 페이지) ──────────────────────────
def fetch_list(sigungu_code: str) -> list[dict]:
    """sigunguCode로 해당 구의 단지 목록 전체 반환"""
    results = []
    page = 1
    while True:
        body = _kapt_get(LIST_URL, {
            "serviceKey":   GOV_KEY,
            "sigunguCode":  sigungu_code,
            "numOfRows":    100,
            "pageNo":       page,
            "_type":        "json",
        })
        total_count = _int(body.get("totalCount"), 0)
        items_raw = body.get("items", {})
        if isinstance(items_raw, dict):
            items = items_raw.get("item", [])
        else:
            items = items_raw or []
        if isinstance(items, dict):
            items = [items]

        results.extend(items)
        if len(results) >= total_count or not items:
            break
        page += 1
        time.sleep(0.1)

    return results


# ── BassInfo 수집 ─────────────────────────────────────────
def fetch_bass(kapt_code: str) -> dict:
    body = _kapt_get(BASS_URL, {
        "serviceKey": GOV_KEY,
        "kaptCode":   kapt_code,
        "_type":      "json",
    })
    item = body.get("item")
    if isinstance(item, list):
        return item[0] if item else {}
    return item or {}


# ── DtlInfo 수집 ─────────────────────────────────────────
def fetch_dtl(kapt_code: str) -> dict:
    body = _kapt_get(DTL_URL, {
        "serviceKey": GOV_KEY,
        "kaptCode":   kapt_code,
        "_type":      "json",
    })
    item = body.get("item")
    if isinstance(item, list):
        return item[0] if item else {}
    return item or {}


# ── Kakao 지오코딩 ─────────────────────────────────────────
def geocode(address: str) -> tuple[float | None, float | None]:
    if not KAKAO_KEY or not address:
        return None, None
    try:
        resp = kakao_session.get(
            KAKAO_URL,
            headers={"Authorization": f"KakaoAK {KAKAO_KEY}"},
            params={"query": address, "analyze_type": "exact"},
            timeout=10,
        )
        docs = resp.json().get("documents", [])
        if docs:
            return float(docs[0]["y"]), float(docs[0]["x"])
        # exact 실패 시 similar로 재시도
        resp2 = kakao_session.get(
            KAKAO_URL,
            headers={"Authorization": f"KakaoAK {KAKAO_KEY}"},
            params={"query": address, "analyze_type": "similar"},
            timeout=10,
        )
        docs2 = resp2.json().get("documents", [])
        if docs2:
            return float(docs2[0]["y"]), float(docs2[0]["x"])
    except Exception:
        pass
    return None, None


def keyword_geocode(name: str, region: str = "") -> tuple[float | None, float | None]:
    """단지명 + 지역으로 카카오 키워드 검색 → 좌표 반환 (주소 지오코딩 실패 시 폴백)"""
    if not KAKAO_KEY or not name:
        return None, None
    query = f"{region} {name}".strip() if region else name
    try:
        resp = kakao_session.get(
            KAKAO_KEYWORD_URL,
            headers={"Authorization": f"KakaoAK {KAKAO_KEY}"},
            params={"query": query, "category_group_code": "APT", "size": 1},
            timeout=10,
        )
        docs = resp.json().get("documents", [])
        if docs:
            return float(docs[0]["y"]), float(docs[0]["x"])
        # APT 카테고리 없으면 카테고리 없이 재시도
        resp2 = kakao_session.get(
            KAKAO_KEYWORD_URL,
            headers={"Authorization": f"KakaoAK {KAKAO_KEY}"},
            params={"query": query, "size": 1},
            timeout=10,
        )
        docs2 = resp2.json().get("documents", [])
        if docs2:
            return float(docs2[0]["y"]), float(docs2[0]["x"])
    except Exception:
        pass
    return None, None


# ── 단지 행 조립 ──────────────────────────────────────────
def build_row(list_item: dict, bass: dict, dtl: dict, sigungu_code: str) -> dict | None:
    """K-apt 응답 3개를 합쳐 apartments 테이블 행으로 변환.
    codeAptNm 이 허용 유형이 아니면 None 반환.
    허용: 아파트 / 주상복합 / 도시형 생활주택(아파트)
    """
    ALLOWED_TYPES = {"아파트", "주상복합", "도시형 생활주택(아파트)", "도시형 생활주택(주상복합)"}
    # 건물 종류 필터
    # - 빈값(미등록): K-apt에 유형 미등록 단지 → 제외
    # - 도시형 생활주택(주상복합), 연립주택 등 → 제외
    prop_type = _str(bass.get("codeAptNm")) or ""
    if not prop_type:
        return None  # K-apt 유형 미등록
    if prop_type not in ALLOWED_TYPES:
        return None  # 허용 유형 외 (연립, 도시형주상복합 등)

    kapt_code = _str(list_item.get("kaptCode"))
    if not kapt_code:
        return None

    kapt_name = _str(bass.get("kaptName")) or _str(list_item.get("kaptName"))
    if not kapt_name:
        return None

    # 주소: doroJuso(도로명) 우선, 없으면 kaptAddr(지번) 사용
    doro_juso = _str(bass.get("doroJuso")) or _str(bass.get("kaptAddr"))

    # 법정동명: list API의 as3 (가장 정확)
    umd_nm = _str(list_item.get("as3"))
    if not umd_nm:
        print(f"    ⚠️ umd_nm 없음 건너뜀: {kapt_code} {kapt_name}")
        return None

    # 시군구명: list API의 as2 → 없으면 sigungu_code로 폴백 (NULL 방지)
    sgg = _str(list_item.get("as2")) or sigungu_code

    # lawd_cd: 법정동코드(bjdCode) 앞 5자리 → 없으면 sigungu_code 사용
    bjd_code = _str(bass.get("bjdCode")) or _str(list_item.get("bjdCode"))
    lawd_cd  = bjd_code[:5] if bjd_code and len(bjd_code) >= 5 else sigungu_code

    # apt_seq: K-apt aptSeq (trade_raw_v2 연결 키) — K-apt API에 없음, match_apt_seq.py로 채움
    apt_seq = None

    # jibun: kaptAddr에서 추출 (trade_raw_v2.jibun 매칭용)
    # kaptAddr 형식: "서울특별시 중랑구 묵동 171-4 묵동공감대아파트"
    jibun = None
    kapt_addr_raw = _str(bass.get("kaptAddr"))
    if kapt_addr_raw:
        parts = kapt_addr_raw.split()
        dong_idx = None
        for i, p in enumerate(parts):
            if p.endswith("동") or p.endswith("리"):
                dong_idx = i
            if dong_idx is not None and i > dong_idx:
                import re as _re
                m = _re.match(r"^(\d+)(?:-(\d*))?$", p)
                if m:
                    bun = m.group(1)
                    ji_raw = m.group(2) or ""
                    jibun = f"{bun}-{ji_raw}" if ji_raw else bun
                    break

    # 최고층: ktownFlrNo (kaptTopFloor는 오류 있음 — 사용 금지)
    top_floor = _int(bass.get("ktownFlrNo"))

    # 대지면적
    land_area = _float(bass.get("kaptTarea"))

    # 동수
    total_dong = _int(bass.get("kaptDongCnt"))

    # 세대수
    households = _int(bass.get("kaptdaCnt"))

    # 분양구분
    trade_type = _str(bass.get("codeSaleNm"))

    # 준공년도
    use_date  = _str(bass.get("kaptUsedate")) or ""
    build_year = int(use_date[:4]) if len(use_date) >= 4 and use_date[:4].isdigit() else None

    # 추가 기본정보
    heat_type  = _str(bass.get("codeHeatNm")) or None   # 난방방식
    hall_type  = _str(bass.get("codeHallNm")) or None   # 복도유형(계단식/복도식)
    mgr_type   = _str(bass.get("codeMgrNm"))  or None   # 관리방식
    ho_cnt     = _int(bass.get("hoCnt"))                # 호수
    base_floor = _int(bass.get("kaptBaseFloor"))        # 지하층수
    builder    = _str(bass.get("kaptBcompany")) or None # 시공사
    developer  = _str(bass.get("kaptAcompany")) or None # 시행사
    mparea60   = _int(bass.get("kaptMparea60"))         # 60㎡ 이하 세대수
    mparea85   = _int(bass.get("kaptMparea85"))         # 60~85㎡ 세대수
    mparea135  = _int(bass.get("kaptMparea135"))        # 85~135㎡ 세대수
    mparea136  = _int(bass.get("kaptMparea136"))        # 135㎡ 초과 세대수

    # 엘리베이터 / 주차
    elevator_count    = _int(dtl.get("kaptdEcnt"))
    parking_ground    = _int(dtl.get("kaptdPcnt"))
    parking_underground = _int(dtl.get("kaptdPcntu"))


    # 좌표: doroJuso 지오코딩 → kaptAddr 지오코딩 → 키워드 검색 순으로 폴백
    jibun_addr = _str(bass.get("kaptAddr"))
    lat, lon = geocode(doro_juso) if doro_juso else (None, None)
    if lat is None and jibun_addr and jibun_addr != doro_juso:
        lat, lon = geocode(jibun_addr)
    if lat is None:
        lat, lon = keyword_geocode(kapt_name, f"{sgg} {umd_nm}" if sgg else umd_nm)

    # slug 생성: kapt_code 소문자로 → 기존 danji_pages ID(소문자)와 URL 일치
    location = f"{sgg} {umd_nm}" if sgg else umd_nm
    slug = make_danji_slug(kapt_name, location, kapt_code.lower(), doro_juso or "")

    row = {
        "kapt_code":           kapt_code,
        "kapt_name":           kapt_name,
        "complex_type":        prop_type,
        "doro_juso":           doro_juso,
        "umd_nm":              umd_nm,
        "sgg":                 sgg,
        "lawd_cd":             lawd_cd,
        "slug":                slug,
        "build_year":          build_year,
        "households":          households,
        "total_dong":          total_dong,
        "land_area":           land_area,
        "trade_type":          trade_type,
        "top_floor":           top_floor,
        "lat":                 lat,
        "lon":                 lon,
        "apt_seq":             apt_seq or None,
        "jibun":               jibun or None,
        "heat_type":           heat_type,
        "hall_type":           hall_type,
        "mgr_type":            mgr_type,
        "ho_cnt":              ho_cnt or None,
        "base_floor":          base_floor or None,
        "builder":             builder,
        "developer":           developer,
        "mparea60":            mparea60 or None,
        "mparea85":            mparea85 or None,
        "mparea135":           mparea135 or None,
        "mparea136":           mparea136 or None,
        "elevator_count":      elevator_count or None,
        "parking_ground":      parking_ground or None,
        "parking_underground": parking_underground or None,
    }
    return row


# ── Supabase upsert ────────────────────────────────────────
BATCH_SIZE = 200

def upsert_rows(rows: list[dict]) -> int:
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        for attempt in range(3):
            try:
                resp = sb_session.post(
                    f"{SB_URL}/rest/v1/apartments?on_conflict=kapt_code",
                    headers=SB_HEADERS,
                    json=batch,
                    timeout=60,
                )
                if resp.status_code in (200, 201):
                    total += len(batch)
                    break
                else:
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        print(f"  ⚠️ upsert 실패 {resp.status_code}: {resp.text[:300]}")
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    print(f"  ⚠️ upsert 예외: {e}")
    return total


# ── 구 단위 처리 ──────────────────────────────────────────
def process_sigungu(sigungu_code: str, sigungu_name: str, dry: bool) -> tuple[int, int, int]:
    """sigungu 하나 처리. (total_found, apt_count, saved_count) 반환"""
    print(f"\n▶ {sigungu_name} ({sigungu_code}) 처리 중...")

    # 1. 단지 목록
    try:
        list_items = fetch_list(sigungu_code)
    except Exception as e:
        print(f"  ❌ 목록 수집 실패: {e}")
        return 0, 0, 0

    print(f"  총 {len(list_items)}개 단지 발견")

    rows = []
    apt_count = 0
    skip_count = 0

    for i, item in enumerate(list_items):
        kapt_code = item.get("kaptCode", "")
        kapt_name = item.get("kaptName", "")

        # 2. BassInfo
        try:
            bass = fetch_bass(kapt_code)
            time.sleep(0.05)  # API 과부하 방지
        except Exception as e:
            print(f"  ⚠️ BassInfo 실패 {kapt_code}: {e}")
            skip_count += 1
            continue

        # 유형 필터: 미등록(빈값) 및 허용 외 유형 건너뜀
        ALLOWED_TYPES = {"아파트", "주상복합", "도시형 생활주택(아파트)", "도시형 생활주택(주상복합)"}
        prop_type = (bass.get("codeAptNm") or "").strip()
        if not prop_type or prop_type not in ALLOWED_TYPES:
            skip_count += 1
            continue

        apt_count += 1

        # 3. DtlInfo
        try:
            dtl = fetch_dtl(kapt_code)
            time.sleep(0.05)
        except Exception as e:
            print(f"  ⚠️ DtlInfo 실패 {kapt_code}: {e}")
            dtl = {}

        # 4. 행 조립
        row = build_row(item, bass, dtl, sigungu_code)
        if row is None:
            skip_count += 1
            continue

        rows.append(row)

        # 진행 상황 (10개마다)
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(list_items)}] 처리 중... (아파트 {apt_count}개, 건너뜀 {skip_count}개)")

    print(f"  → 아파트 {apt_count}개 / 건너뜀 {skip_count}개 / 저장 대상 {len(rows)}개")

    if dry:
        if rows:
            print(f"  [DRY] 첫 번째 행 샘플:")
            print(json.dumps(rows[0], ensure_ascii=False, indent=4, default=str))
        return len(list_items), apt_count, 0

    # 5. Supabase upsert
    saved = upsert_rows(rows)
    print(f"  ✅ {saved}개 저장 완료")
    return len(list_items), apt_count, saved


# ── 메인 ──────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="K-apt 단지 마스터 수집")
    parser.add_argument("--sigungu", type=str, default=None,
                        help="특정 구 코드 (예: 11260 = 중랑구)")
    parser.add_argument("--region",  type=str, default=None,
                        choices=["seoul", "incheon", "gyeonggi", "busan", "daegu", "gwangju", "daejeon", "ulsan", "all"],
                        help="지역 전체 수집")
    parser.add_argument("--dry",     action="store_true",
                        help="저장 안 하고 첫 결과만 출력")
    args = parser.parse_args()

    if not args.sigungu and not args.region:
        parser.print_help()
        sys.exit(1)

    # 처리할 (code, name) 목록 구성
    targets: list[tuple[str, str]] = []

    if args.sigungu:
        from regions import ALL_REGIONS
        # 쉼표 구분 복수 코드 지원 (예: --sigungu 11260,11710)
        codes = [c.strip() for c in args.sigungu.split(",")]
        for code in codes:
            name = ALL_REGIONS.get(code, code)
            targets.append((code, name))
    elif args.region == "all":
        for region_dict in [SEOUL_GU, INCHEON_GU, GYEONGGI_SI, BUSAN_GU, DAEGU_GU, GWANGJU_GU, DAEJEON_GU, ULSAN_GU,
                            SEJONG_SI, CHUNGBUK_SI, CHUNGNAM_SI, JEONBUK_SI, JEONNAM_SI,
                            GYEONGBUK_SI, GYEONGNAM_SI, GANGWON_SI, JEJU_SI]:
            targets.extend(region_dict.items())
    else:
        targets.extend(REGION_MAP[args.region].items())

    print(f"처리 대상: {len(targets)}개 구/시")
    if args.dry:
        print("⚠️  DRY RUN 모드 — Supabase 저장 없음\n")

    total_found = total_apt = total_saved = 0
    import time as _time
    start = _time.time()

    for code, name in targets:
        found, apt, saved = process_sigungu(code, name, args.dry)
        total_found += found
        total_apt   += apt
        total_saved += saved

    elapsed = _time.time() - start
    print(f"\n{'='*50}")
    print(f"✅ 완료: 총 {total_found}개 단지 조회 / 아파트 {total_apt}개 / {total_saved}개 저장 ({elapsed:.0f}초)")


if __name__ == "__main__":
    main()
