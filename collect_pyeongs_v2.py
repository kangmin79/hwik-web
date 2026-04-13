# -*- coding: utf-8 -*-
"""
collect_pyeongs_v2.py — 건축물대장 전유공용면적 조회로 단지별 평형 수집

목적: 단지별 전용/공급면적 타입 수집 → apartments.pyeongs 업데이트
주기: 6개월~1년에 1회 (collect_complexes.py와 독립 실행)

사용법:
  python collect_pyeongs_v2.py --sigungu 11260          # 중랑구
  python collect_pyeongs_v2.py --sigungu 11260,11710    # 중랑구+송파구
  python collect_pyeongs_v2.py --region seoul           # 서울 전체
  python collect_pyeongs_v2.py --region all             # 서울+인천+경기

흐름:
  1. apartments에서 해당 구 단지 조회
  2. K-apt BassInfo 재조회 → bjdCode, kaptAddr 확보
  3. 건축물대장 전유공용면적 API 호출 (최대 20페이지, 수렴 시 조기 종료)
  4. (mgmBldrgstPk, hoNm) 단위로 전용+공용 집계
  5. 고유 전용면적 타입별 공급면적 계산 (중앙값)
  6. apartments.pyeongs 업데이트
"""
import os, sys, re, ssl, json, time, argparse
import urllib.request, urllib.parse
import urllib3, requests
from requests.adapters import HTTPAdapter
from collections import defaultdict

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

urllib3.disable_warnings()

# ── 환경변수 로드 ─────────────────────────────────────────
if os.path.exists(".env"):
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

GOV_KEY      = os.environ.get("GOV_SERVICE_KEY", "")
SUPABASE_URL = "https://jqaxejgzkchxbfzgzyzi.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not GOV_KEY:
    sys.exit("❌ GOV_SERVICE_KEY 없음")
if not SUPABASE_KEY:
    sys.exit("❌ SUPABASE_SERVICE_ROLE_KEY 없음")

# ── HTTP 세션 ─────────────────────────────────────────────
class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount("https://", TLSAdapter())
session.verify = False

BASS_URL   = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4"
EXPOS_URL  = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo"

# ── 유틸 ─────────────────────────────────────────────────
def _str(v): return str(v).strip() if v is not None else ""
def _float(v):
    try: return float(v)
    except: return None

def kapt_get(url, params, retries=3):
    for i in range(retries):
        try:
            r = session.get(url, params=params, timeout=15)
            body = r.json().get("response", {}).get("body", {})
            return body
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(1)
    return {}

def supabase_get(path, params):
    url = f"{SUPABASE_URL}/rest/v1/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def supabase_patch(table, kapt_code, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?kapt_code=eq.{urllib.parse.quote(kapt_code)}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="PATCH", headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    })
    with urllib.request.urlopen(req) as r:
        return r.status

# ── 지번 파싱 ─────────────────────────────────────────────
def parse_jibun(kapt_addr: str):
    """kaptAddr에서 sigunguCd, bjdongCd, bun, ji 추출
    예: '서울특별시 중랑구 면목동 1518- 면목신우아파트'
        '서울특별시 송파구 가락동 21-6 가락2차쌍용아파트'
    """
    parts = kapt_addr.split()
    # 번지 패턴: 숫자(-숫자?)
    bun, ji = None, "0000"
    dong_idx = None
    for i, p in enumerate(parts):
        if p.endswith("동") or p.endswith("리"):
            dong_idx = i
        if dong_idx is not None and i > dong_idx:
            m = re.match(r"^(\d+)(?:-(\d*))?$", p)
            if m:
                bun = m.group(1).zfill(4)
                ji_raw = m.group(2) or "0"
                ji = ji_raw.zfill(4) if ji_raw else "0000"
                break
    return bun, ji

# ── 건축물대장 전유공용면적 조회 ─────────────────────────
def fetch_expos(sigungu_cd: str, bjdong_cd: str, bun: str, ji: str) -> tuple:
    """전유공용면적 페이지네이션 조회.
    - 최대 20페이지 수집 (API 실제 페이지당 ~100건 기준 최대 2000건)
    - 평형 타입 수렴 시 조기 종료 (연속 3페이지에서 새 타입 없으면 중단)
    """
    base_params = {
        "serviceKey": GOV_KEY,
        "sigunguCd":  sigungu_cd,
        "bjdongCd":   bjdong_cd,
        "platGbCd":   "0",
        "bun":        bun,
        "ji":         ji,
        "numOfRows":  1000,
        "_type":      "json",
    }
    all_items = []
    total = 0
    seen_exclu_types = set()
    no_new_type_pages = 0

    for page in range(1, 21):  # 최대 20페이지
        try:
            params = {**base_params, "pageNo": page}
            body = kapt_get(EXPOS_URL, params)
            if page == 1:
                total = int(body.get("totalCount") or 0)
            items_raw = body.get("items", {})
            if isinstance(items_raw, dict):
                items = items_raw.get("item", [])
            else:
                items = items_raw or []
            if isinstance(items, dict):
                items = [items]
            if not items:
                break
            all_items.extend(items)

            # 이번 페이지에서 새 전용면적 타입 발견 여부 확인
            new_types = {
                round(float(it.get("area") or 0), 2)
                for it in items
                if str(it.get("exposPubuseGbCd", "")).strip() == "1"
                and str(it.get("mainPurpsCd", "")).strip() == "02001"
                and float(it.get("area") or 0) > 0
            }
            if new_types - seen_exclu_types:
                no_new_type_pages = 0
                seen_exclu_types |= new_types
            else:
                no_new_type_pages += 1

            # 전체 수집 완료 or 타입 수렴 (연속 3페이지 새 타입 없음)
            if len(all_items) >= total or no_new_type_pages >= 3:
                break
        except Exception:
            break

    return all_items, total

# ── 단지명 정규화 (bldNm 매칭용) ─────────────────────────
def _normalize_bldnm(name: str) -> str:
    """공백 제거, 소문자, '아파트'/'동번호' 등 제거"""
    name = re.sub(r'(아파트|APT|apt)\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\d+동$', '', name)
    return re.sub(r'\s+', '', name).lower().strip()

# ── 평형 추출 ─────────────────────────────────────────────
def extract_pyeongs(items: list, kapt_name: str = "") -> list:
    """
    (mgmBldrgstPk, hoNm) 단위로 전용+공용 집계
    → 고유 전용면적별 공급면적 계산

    kapt_name: 단지명 — bldNm 필터링으로 같은 번지 복수 단지 혼재 방지
    반환: [{'exclu': 59.84, 'supply': 84.96}, ...]
    """
    # bldNm 기반 필터링 (같은 번지에 복수 단지가 있을 때 혼재 방지)
    if kapt_name:
        clean = _normalize_bldnm(kapt_name)
        filtered = [
            it for it in items
            if clean and (
                clean in _normalize_bldnm(it.get("bldNm", ""))
                or _normalize_bldnm(it.get("bldNm", "")) in clean
            )
        ]
        # 필터 결과가 전체의 10% 이상이면 사용, 아니면 필터 없이 전체 사용
        # (단지명이 건축물대장 bldNm과 크게 다른 경우 대비)
        if len(filtered) >= len(items) * 0.1:
            items = filtered

    # {(pk, ho): {'exclu': float, 'pub': float}}
    units = defaultdict(lambda: {"exclu": 0.0, "pub": 0.0})

    for item in items:
        pk   = item.get("mgmBldrgstPk", "")
        ho   = item.get("hoNm", "").strip()
        gb   = str(item.get("exposPubuseGbCd", "")).strip()
        purp = str(item.get("mainPurpsCd", "")).strip()
        area = _float(item.get("area")) or 0.0

        if not pk or not ho or area <= 0:
            continue

        key = (pk, ho)
        if gb == "1" and purp == "02001":   # 전유 + 아파트 용도만
            units[key]["exclu"] += area
        elif gb == "2":                     # 공용
            units[key]["pub"] += area

    if not units:
        return []

    # 전용면적 기준으로 그룹화
    type_map = defaultdict(list)
    for key, v in units.items():
        exclu = round(v["exclu"], 2)
        if exclu <= 0:
            continue
        supply = round(exclu + v["pub"], 2)
        type_map[exclu].append(supply)

    # 각 타입의 공급면적 대표값 (중앙값)
    # 공급/전용 비율이 1.0 미만이거나 3.5 초과면 오염 데이터로 판단
    # → supply 없이 exclu만 저장 (화면에서 전용면적만 표시)
    MAX_SUPPLY_RATIO = 3.5
    result = []
    for exclu, supplies in sorted(type_map.items()):
        supplies.sort()
        median_supply = supplies[len(supplies) // 2]
        ratio = median_supply / exclu if exclu > 0 else 0
        if ratio < 1.0 or ratio > MAX_SUPPLY_RATIO:
            result.append({"exclu": exclu})
        else:
            result.append({"exclu": exclu, "supply": round(median_supply, 2)})

    return result

# ── 단지 처리 ─────────────────────────────────────────────
def process_apt(apt: dict, dry: bool = False) -> str:
    """단지 하나 처리. 결과 상태 문자열 반환."""
    kapt_code = apt["kapt_code"]
    kapt_name = apt.get("kapt_name", "")

    # 1. K-apt BassInfo 재조회 → bjdCode, kaptAddr
    try:
        body = kapt_get(BASS_URL, {"serviceKey": GOV_KEY, "kaptCode": kapt_code, "_type": "json"})
        item = body.get("item")
        if isinstance(item, list):
            item = item[0] if item else {}
        bass = item or {}
    except Exception as e:
        return f"BassInfo 실패: {e}"

    bjd_code  = _str(bass.get("bjdCode"))  # 10자리: 1126010100
    kapt_addr = _str(bass.get("kaptAddr"))

    if not bjd_code or len(bjd_code) < 10:
        return "bjdCode 없음"

    sigungu_cd = bjd_code[:5]   # 앞 5자리: 11260
    bjdong_cd  = bjd_code[5:10] # 뒤 5자리: 10100

    # 2. 번지 파싱
    bun, ji = parse_jibun(kapt_addr)
    if not bun:
        return f"번지 파싱 실패: {kapt_addr}"

    # 3. 건축물대장 API 호출
    items, total = fetch_expos(sigungu_cd, bjdong_cd, bun, ji)
    if not items:
        return f"건축물대장 데이터 없음 (sigungu={sigungu_cd} bjdong={bjdong_cd} bun={bun} ji={ji})"

    # 4. 평형 추출 (kapt_name 전달로 bldNm 필터링 활성화)
    pyeongs = extract_pyeongs(items, kapt_name=kapt_name)
    if not pyeongs:
        return f"평형 추출 실패 (records={len(items)})"

    # 5. DB 업데이트
    if not dry:
        supabase_patch("apartments", kapt_code, {"pyeongs": pyeongs})

    types_str = ", ".join(
        f"{p['exclu']}㎡→{p['supply']}㎡" if 'supply' in p else f"{p['exclu']}㎡(전용만)"
        for p in pyeongs
    )
    return f"✅ {len(pyeongs)}개 타입 ({types_str}) [건축물대장 {total}건]"

# ── 메인 ─────────────────────────────────────────────────
def main():
    from regions import (
        SEOUL_GU, INCHEON_GU, GYEONGGI_SI,
        BUSAN_GU, DAEGU_GU, GWANGJU_GU, DAEJEON_GU, ULSAN_GU,
        SEJONG_SI, CHUNGBUK_SI, CHUNGNAM_SI,
        JEONBUK_SI, JEONNAM_SI, GYEONGBUK_SI, GYEONGNAM_SI,
        GANGWON_SI, JEJU_SI, ALL_REGIONS,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--sigungu", type=str, help="쉼표 구분 구 코드 (예: 11260,11710)")
    parser.add_argument("--region",  type=str, help="seoul/incheon/gyeonggi/busan/.../all")
    parser.add_argument("--dry",     action="store_true", help="DB 저장 안 하고 출력만")
    args = parser.parse_args()

    if not args.sigungu and not args.region:
        sys.exit("--sigungu 또는 --region 필요")

    REGION_MAP = {
        "seoul":     SEOUL_GU,    "incheon":   INCHEON_GU,  "gyeonggi":  GYEONGGI_SI,
        "busan":     BUSAN_GU,    "daegu":     DAEGU_GU,    "gwangju":   GWANGJU_GU,
        "daejeon":   DAEJEON_GU,  "ulsan":     ULSAN_GU,    "sejong":    SEJONG_SI,
        "chungbuk":  CHUNGBUK_SI, "chungnam":  CHUNGNAM_SI,
        "jeonbuk":   JEONBUK_SI,  "jeonnam":   JEONNAM_SI,
        "gyeongbuk": GYEONGBUK_SI, "gyeongnam": GYEONGNAM_SI,
        "gangwon":   GANGWON_SI,  "jeju":      JEJU_SI,
    }

    # 대상 구 코드 결정
    if args.sigungu:
        codes = [c.strip() for c in args.sigungu.split(",")]
    elif args.region == "all":
        codes = list(ALL_REGIONS.keys())
    else:
        if args.region not in REGION_MAP:
            sys.exit(f"❌ 알 수 없는 region: {args.region}")
        codes = list(REGION_MAP[args.region])

    # Supabase에서 해당 구 단지 조회
    apts = []
    for code in codes:
        rows = supabase_get("apartments", {
            "select": "kapt_code,kapt_name,sgg",
            "lawd_cd": f"eq.{code}",
            "kapt_code": "like.A*",
            "limit": 1000,
        })
        apts.extend(rows)

    print(f"처리 대상: {len(apts)}개 단지")
    if args.dry:
        print("(dry 모드 — DB 저장 안 함)")

    ok, fail, skip = 0, 0, 0
    for i, apt in enumerate(apts, 1):
        name = apt.get("kapt_name", "")
        result = process_apt(apt, dry=args.dry)
        status = "✅" if result.startswith("✅") else "⚠️"
        print(f"  [{i}/{len(apts)}] {apt.get('sgg','')} {name}: {result}")
        if result.startswith("✅"):
            ok += 1
        else:
            fail += 1
        time.sleep(0.1)  # API 과부하 방지

    print(f"\n{'='*50}")
    print(f"완료: 성공 {ok}개 / 실패 {fail}개")

if __name__ == "__main__":
    main()
