# -*- coding: utf-8 -*-
"""
collect_trades_v2.py — 실거래 수집 v2
국토부 4개 API → trade_raw_v2 (1건=1행, aptSeq 포함)

기존 sync_trades.py / trade_cache 는 건드리지 않음.
이 스크립트는 trade_raw_v2 테이블만 씀.

사용법:
  python collect_trades_v2.py               # 당월+전월 (일일 동기화)
  python collect_trades_v2.py --init        # 최근 36개월 전체 수집
  python collect_trades_v2.py --months 6    # 최근 6개월
  python collect_trades_v2.py --lawd 11200  # 특정 구만 (테스트)
"""

import os
import sys
import ssl
import time
import argparse
import xml.etree.ElementTree as ET
from datetime import datetime
from dateutil.relativedelta import relativedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
from requests.adapters import HTTPAdapter

# UTF-8 출력
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

urllib3.disable_warnings()


# ── 환경변수 ──────────────────────────────────────────────
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

GOV_KEY  = os.environ.get("GOV_SERVICE_KEY", "")
SB_URL   = os.environ.get("SUPABASE_URL", "https://api.hwik.kr")
SB_KEY   = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not GOV_KEY:
    sys.exit("❌ GOV_SERVICE_KEY 없음")
if not SB_KEY:
    sys.exit("❌ SUPABASE_SERVICE_ROLE_KEY 없음")

SB_HEADERS = {
    "apikey": SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=ignore-duplicates",  # 이미 있는 거래는 무시
}


# ── SSL 우회 (정부 API) ───────────────────────────────────
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

sb_session = requests.Session()


# ── 지역 코드 ─────────────────────────────────────────────
from regions import SEOUL_GU, INCHEON_GU, GYEONGGI_SI, BUSAN_GU, DAEGU_GU, GWANGJU_GU, DAEJEON_GU, ULSAN_GU

ALL_LAWD = {}
ALL_LAWD.update(SEOUL_GU)
ALL_LAWD.update(INCHEON_GU)
ALL_LAWD.update(GYEONGGI_SI)
ALL_LAWD.update(BUSAN_GU)
ALL_LAWD.update(DAEGU_GU)
ALL_LAWD.update(GWANGJU_GU)
ALL_LAWD.update(DAEJEON_GU)
ALL_LAWD.update(ULSAN_GU)


# ── 국토부 API 엔드포인트 ─────────────────────────────────
# 현재 아파트만 수집 (오피스텔은 aptSeq 없어 별도 파이프라인 필요 — 추후 확장)
APIS = [
    # (url, prop_type, is_rent)
    ("http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",  "apt",  False),
    ("http://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",           "apt",  True),
    # ("https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade",    "offi", False),  # 추후 확장
    # ("https://apis.data.go.kr/1613000/RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent",      "offi", True),   # 추후 확장
]


# ── 파싱 유틸 ────────────────────────────────────────────
def _int(s, default=0):
    try:
        return int(str(s).replace(",", "").strip()) if s else default
    except (ValueError, TypeError):
        return default

def _float(s, default=None):
    try:
        return float(str(s).strip()) if s else default
    except (ValueError, TypeError):
        return default

def _str(s):
    return str(s).strip() if s else None


# ── XML 수집 ──────────────────────────────────────────────
def _fetch_xml(lawd_cd: str, year_month: str, api_url: str) -> list[dict]:
    """국토부 API 1회 호출 → XML item 목록 반환"""
    for attempt in range(3):
        try:
            resp = gov_session.get(
                api_url,
                params={
                    "serviceKey": GOV_KEY,
                    "LAWD_CD": lawd_cd,
                    "DEAL_YMD": year_month,
                    "pageNo": "1",
                    "numOfRows": "9999",
                },
                headers={"Accept": "application/xml"},
                timeout=60,
            )
            if resp.status_code != 200:
                return []
            root = ET.fromstring(resp.content)
            return [
                {c.tag: (c.text.strip() if c.text else "") for c in item}
                for item in root.findall(".//item")
            ]
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  ⚠️ {lawd_cd}/{year_month} {api_url.split('/')[-1]}: {e}")
    return []


# ── 거래 파싱 ─────────────────────────────────────────────
def _parse_row(item: dict, lawd_cd: str, year_month: str, prop_type: str, is_rent: bool) -> dict | None:
    """XML item dict → trade_raw_v2 행. aptSeq 없으면 None 반환."""
    apt_seq = _str(item.get("aptSeq"))
    if not apt_seq:
        return None  # aptSeq 없는 건 건너뜀

    # 거래 유형 결정 (전세/월세 분리)
    if is_rent:
        # monthlyRent가 None/빈값이면 0, 양수면 월세
        monthly_raw = _int(item.get("monthlyRent") or item.get("monthlyAmount"), 0)
        deal_type = "월세" if monthly_raw > 0 else "전세"
        price = _int(item.get("deposit") or item.get("dealAmount"), 0) or None
        monthly_rent = monthly_raw if monthly_raw > 0 else None
    else:
        deal_type = "매매"
        price = _int(item.get("dealAmount"), 0) or None
        monthly_rent = None

    # 도로명 주소 숫자 파싱
    road_nm_bonbun = _int(item.get("roadNmBonbun"))
    road_nm_bubun  = _int(item.get("roadNmBubun"))

    # 단지명: 아파트는 aptNm, 오피스텔은 offiNm
    apt_nm = _str(item.get("aptNm") or item.get("offiNm"))

    return {
        "apt_seq":        apt_seq,
        "deal_type":      deal_type,
        "prop_type":      prop_type,
        "dealing_gbn":    _str(item.get("dealingGbn")),
        "lawd_cd":        lawd_cd,
        "deal_year":      _int(item.get("dealYear")),
        "deal_month":     _int(item.get("dealMonth")),
        "deal_day":       _int(item.get("dealDay")),
        "price":          price if price else None,
        "monthly_rent":   monthly_rent or 0,  # NOT NULL DEFAULT 0 (dedup 인덱스용)
        "excl_use_ar":    _float(item.get("excluUseAr") or item.get("exclusiveArea")),
        "floor":          _int(item.get("floor")) or None,
        "apt_nm":         apt_nm,
        "umd_nm":         _str(item.get("umdNm")),
        "umd_cd":         _str(item.get("umdCd")),
        "jibun":          _str(item.get("jibun")),
        "road_nm":        _str(item.get("roadNm")),
        "road_nm_bonbun": road_nm_bonbun if road_nm_bonbun else None,
        "road_nm_bubun":  road_nm_bubun if road_nm_bubun else 0,
        "build_year":     _int(item.get("buildYear")) or None,
        "raw":            item,
    }


# ── 월별 수집 (4개 API 병렬) ──────────────────────────────
def collect_month(lawd_cd: str, year_month: str) -> list[dict]:
    """특정 구+월의 전체 거래 수집 → 파싱된 행 목록"""
    rows = []
    for api_url, prop_type, is_rent in APIS:
        items = _fetch_xml(lawd_cd, year_month, api_url)
        for item in items:
            row = _parse_row(item, lawd_cd, year_month, prop_type, is_rent)
            if row:
                rows.append(row)
    return rows


# ── Supabase upsert ────────────────────────────────────────
BATCH_SIZE = 500

def upsert(rows: list[dict]) -> int:
    """trade_raw_v2에 upsert. 이미 있는 건 무시(ignore-duplicates). 성공 건수 반환."""
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        for attempt in range(3):
            try:
                resp = sb_session.post(
                    f"{SB_URL}/rest/v1/trade_raw_v2"
                    "?on_conflict=apt_seq,deal_type,deal_year,deal_month,deal_day,floor,excl_use_ar,price,monthly_rent",
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
                        print(f"  ⚠️ upsert 실패 {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    print(f"  ⚠️ upsert 예외: {e}")
    return total


# ── 메인 실행 ─────────────────────────────────────────────
def run(months: list[str], lawd_codes: list[str]):
    total_saved = 0
    total_tasks = len(months) * len(lawd_codes)
    done = 0

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(collect_month, lawd_cd, ym): (lawd_cd, ym)
            for ym in months
            for lawd_cd in lawd_codes
        }
        for future in as_completed(futures):
            lawd_cd, ym = futures[future]
            done += 1
            try:
                rows = future.result()
                if rows:
                    saved = upsert(rows)
                    total_saved += saved
                    print(f"  [{done}/{total_tasks}] {lawd_cd} {ym}: {len(rows)}건 수집 / {saved}건 저장")
                else:
                    print(f"  [{done}/{total_tasks}] {lawd_cd} {ym}: 0건")
            except Exception as e:
                print(f"  [{done}/{total_tasks}] {lawd_cd} {ym}: ❌ {e}")

    return total_saved


def main():
    parser = argparse.ArgumentParser(description="실거래 수집 v2")
    parser.add_argument("--init",   action="store_true", help="최근 60개월(5년) 전체 수집")
    parser.add_argument("--months", type=int, default=2, help="최근 N개월 수집 (기본 2)")
    parser.add_argument("--lawd",   type=str, default=None, help="특정 구 lawd_cd (테스트용)")
    parser.add_argument("--region", type=str, default=None,
                        help="지역 (seoul/incheon/gyeonggi/busan/daegu/gwangju/daejeon/ulsan/all)")
    args = parser.parse_args()

    REGION_MAP = {
        "seoul":    SEOUL_GU,
        "incheon":  INCHEON_GU,
        "gyeonggi": GYEONGGI_SI,
        "busan":    BUSAN_GU,
        "daegu":    DAEGU_GU,
        "gwangju":  GWANGJU_GU,
        "daejeon":  DAEJEON_GU,
        "ulsan":    ULSAN_GU,
    }

    now = datetime.now()

    if args.init:
        month_count = 60
    else:
        month_count = args.months

    months = []
    for i in range(month_count):
        d = now - relativedelta(months=i)
        months.append(d.strftime("%Y%m"))

    if args.lawd:
        lawd_codes = [args.lawd]
        print(f"▶ 테스트 모드: lawd_cd={args.lawd}, {len(months)}개월")
    elif args.region and args.region != "all":
        if args.region not in REGION_MAP:
            sys.exit(f"❌ 알 수 없는 region: {args.region}. 가능한 값: {list(REGION_MAP.keys())}")
        lawd_codes = list(REGION_MAP[args.region].keys())
        print(f"▶ {args.region} {len(lawd_codes)}개 구, {len(months)}개월")
    else:
        lawd_codes = list(ALL_LAWD.keys())
        print(f"▶ 전체 {len(lawd_codes)}개 구, {len(months)}개월")

    print(f"  대상 월: {months[0]} ~ {months[-1]}")
    print()

    start = time.time()
    total = run(months, lawd_codes)
    elapsed = time.time() - start

    print()
    print(f"✅ 완료: {total}건 저장 ({elapsed:.0f}초)")


if __name__ == "__main__":
    main()
