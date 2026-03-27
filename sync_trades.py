# -*- coding: utf-8 -*-
"""
실거래가 일일 동기화
- 초기: --init 플래그로 최근 36개월 전체 수집
- 이후: 당월 + 전월만 수집 (늦은 신고 반영)
- 수집 후 danji_pages 집계 업데이트

사용법:
  python sync_trades.py --init          # 최초 3년치 수집
  python sync_trades.py                 # 일일 동기화 (당월+전월)
  python sync_trades.py --months 6      # 최근 6개월 수집

GitHub Actions에서 매일 새벽 3시 실행
"""

import os
import sys
import json
import time
import math
import argparse
import ssl
import urllib3
import xml.etree.ElementTree as ET
from datetime import datetime
from dateutil.relativedelta import relativedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import requests
from requests.adapters import HTTPAdapter

# UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

urllib3.disable_warnings()


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

GOV_SERVICE_KEY = os.environ.get("GOV_SERVICE_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://api.hwik.kr")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not GOV_SERVICE_KEY:
    print("❌ GOV_SERVICE_KEY 없음")
    sys.exit(1)
if not SUPABASE_KEY:
    print("❌ SUPABASE_SERVICE_ROLE_KEY 없음")
    sys.exit(1)

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}


# ── SSL 우회 (정부 API) ────────────────────────────────
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


# ── 서울 25개 구 법정동코드 ─────────────────────────────
SEOUL_GU = {
    "11110": "종로구",   "11140": "중구",     "11170": "용산구",
    "11200": "성동구",   "11215": "광진구",   "11230": "동대문구",
    "11260": "중랑구",   "11290": "성북구",   "11305": "강북구",
    "11320": "도봉구",   "11350": "노원구",   "11380": "은평구",
    "11410": "서대문구", "11440": "마포구",   "11470": "양천구",
    "11500": "강서구",   "11530": "구로구",   "11545": "금천구",
    "11560": "영등포구", "11590": "동작구",   "11620": "관악구",
    "11650": "서초구",   "11680": "강남구",   "11710": "송파구",
    "11740": "강동구",
}

# ── API URL ─────────────────────────────────────────────
APT_TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
APT_RENT_URL  = "http://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
OFFI_TRADE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade"
OFFI_RENT_URL  = "https://apis.data.go.kr/1613000/RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent"


# ========================================================
# 1단계: 정부 API에서 실거래 수집
# ========================================================
def fetch_trades(lawd_cd: str, year_month: str, api_url: str, deal_type: str) -> list:
    """특정 구+월의 거래 데이터 수집"""
    try:
        resp = gov_session.get(api_url, params={
            "serviceKey": GOV_SERVICE_KEY,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": year_month,
            "pageNo": "1",
            "numOfRows": "9999",
        }, headers={"Accept": "application/xml"}, timeout=30)

        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item"):
            row = {c.tag: (c.text.strip() if c.text else "") for c in item}
            row["_deal_type"] = deal_type
            row["_lawd_cd"] = lawd_cd
            row["_year_month"] = year_month
            items.append(row)
        return items

    except Exception as e:
        print(f"  ⚠️ {lawd_cd}/{year_month}/{deal_type}: {e}")
        return []


def fetch_all_for_month(year_month: str, lawd_codes: list = None) -> dict:
    """
    특정 월의 서울 전체 실거래 수집
    반환: { "11110_매매_apt": [...], "11110_전세_apt": [...], ... }
    """
    codes = lawd_codes or list(SEOUL_GU.keys())
    apis = [
        (APT_TRADE_URL,  "매매", "apt"),
        (APT_RENT_URL,   "전세", "apt"),
        (OFFI_TRADE_URL, "매매", "offi"),
        (OFFI_RENT_URL,  "전세", "offi"),
    ]

    results = {}
    tasks = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        for code in codes:
            for api_url, deal_type, prop_type in apis:
                key = f"{code}_{deal_type}_{prop_type}"
                future = pool.submit(fetch_trades, code, year_month, api_url, deal_type)
                tasks.append((key, future))

        for key, future in tasks:
            try:
                data = future.result()
                if data:
                    results[key] = data
            except Exception as e:
                print(f"  ⚠️ {key}: {e}")

    total = sum(len(v) for v in results.values())
    print(f"  {year_month}: {total}건 수집 ({len(results)}개 구/유형)")
    return results


# ========================================================
# 2단계: trade_cache에 upsert
# ========================================================
def upsert_trade_cache(year_month: str, all_data: dict):
    """수집한 데이터를 trade_cache 테이블에 upsert"""
    rows = []
    for key, items in all_data.items():
        parts = key.split("_")
        lawd_cd = parts[0]
        deal_type = parts[1]
        prop_type = parts[2]

        rows.append({
            "kapt_code": f"{lawd_cd}_{prop_type}",
            "deal_type": deal_type,
            "year_month": year_month,
            "data": items,
        })

    if not rows:
        return 0

    # 배치 upsert (50개씩)
    batch_size = 50
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        resp = sb_session.post(
            f"{SUPABASE_URL}/rest/v1/trade_cache",
            headers=SB_HEADERS,
            json=batch,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            total += len(batch)
        else:
            print(f"  ⚠️ upsert 오류: {resp.status_code} {resp.text[:200]}")

    return total


# ========================================================
# 3단계: danji_pages 집계 업데이트
# ========================================================
def load_apartments():
    """apartments 테이블에서 단지 목록 로드"""
    all_apts = []
    offset = 0
    limit = 1000
    while True:
        resp = sb_session.get(
            f"{SUPABASE_URL}/rest/v1/apartments",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "select": "kapt_code,kapt_name,doro_juso,lat,lon,lawd_cd,property_type,households,use_date,sgg,umd_nm,pyeongs,slug,top_floor,parking",
                "limit": str(limit),
                "offset": str(offset),
            },
            timeout=30,
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        all_apts.extend(data)
        offset += limit
        if len(data) < limit:
            break

    print(f"📦 apartments: {len(all_apts)}개 로드")
    return all_apts


def load_trade_cache_for_gu(lawd_cd: str) -> list:
    """특정 구의 trade_cache 전체 로드"""
    all_rows = []
    offset = 0
    limit = 1000
    while True:
        resp = sb_session.get(
            f"{SUPABASE_URL}/rest/v1/trade_cache",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "select": "*",
                "kapt_code": f"like.{lawd_cd}_%",
                "limit": str(limit),
                "offset": str(offset),
                "order": "year_month.desc",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        all_rows.extend(data)
        offset += limit
        if len(data) < limit:
            break
    return all_rows


def match_trades_to_complex(apt: dict, trade_rows: list) -> list:
    """특정 단지에 해당하는 거래 필터링 (단지명 매칭)"""
    kapt_name = (apt.get("kapt_name") or "").replace(" ", "")
    slug = (apt.get("slug") or "").replace(" ", "")
    if not kapt_name:
        return []

    # 키워드 추출 (숫자태그 분리)
    import re
    name_clean = re.sub(r'\d+차|\d+단지|\d+블록', '', kapt_name)
    num_match = re.search(r'(\d+차|\d+단지|\d+블록)', kapt_name)
    num_tag = num_match.group(1) if num_match else ""

    matched = []
    for row in trade_rows:
        items = row.get("data") or []
        for item in items:
            apt_nm = (item.get("aptNm") or item.get("offiNm") or "").replace(" ", "")
            if not apt_nm:
                continue

            # 매칭: 단지명 포함 관계
            hit = False
            if kapt_name in apt_nm or apt_nm in kapt_name:
                hit = True
            elif name_clean and (name_clean in apt_nm or apt_nm in name_clean):
                hit = True
            elif slug and (slug in apt_nm or apt_nm in slug):
                hit = True

            # 숫자 태그 확인 (2차, 3차 구분)
            if hit and num_tag:
                if num_tag not in apt_nm and apt_nm not in kapt_name:
                    hit = False

            if hit:
                item["_deal_type"] = row.get("deal_type", "")
                item["_year_month"] = row.get("year_month", "")
                matched.append(item)

    return matched


def aggregate_danji(apt: dict, trades: list) -> dict | None:
    """단지별 거래 데이터를 danji_pages 포맷으로 집계"""
    if not trades:
        return None

    pyeongs = apt.get("pyeongs") or []
    # 전용면적 → 평형명 매핑
    exclu_to_cat = {}
    categories = []
    for p in pyeongs:
        exclu = p.get("exclu", 0)
        if exclu <= 0:
            continue
        cat = str(round(exclu))
        exclu_to_cat[exclu] = cat
        if cat not in categories:
            categories.append(cat)

    if not categories:
        # pyeongs 없으면 거래 데이터에서 추출
        areas = set()
        for t in trades:
            try:
                area = float(t.get("excluUseAr") or t.get("exclusiveArea") or 0)
                if area > 0:
                    areas.add(str(round(area)))
            except:
                pass
        categories = sorted(areas, key=lambda x: float(x))

    # 거래를 평형별로 분류
    def get_cat(trade_item):
        try:
            area = float(trade_item.get("excluUseAr") or trade_item.get("exclusiveArea") or 0)
        except:
            return None
        if area <= 0:
            return None
        # 가장 가까운 카테고리 매칭 (±3㎡ 허용)
        best_cat, best_diff = None, 999
        for cat in categories:
            diff = abs(area - float(cat))
            if diff < best_diff and diff <= 3:
                best_cat = cat
                best_diff = diff
        return best_cat

    def parse_price(t):
        """만원 단위 가격 파싱"""
        raw = t.get("dealAmount") or t.get("deposit") or t.get("보증금액") or ""
        try:
            return int(str(raw).replace(",", "").replace(" ", ""))
        except:
            return 0

    def parse_date(t):
        y = t.get("dealYear") or t.get("년") or ""
        m = t.get("dealMonth") or t.get("월") or ""
        d = t.get("dealDay") or t.get("일") or ""
        if y and m:
            return f"{y}-{str(m).zfill(2)}" + (f"-{str(d).zfill(2)}" if d else "")
        return t.get("_year_month", "")

    def parse_floor(t):
        try:
            return int(t.get("floor") or t.get("층") or 0)
        except:
            return 0

    # 분류
    recent_trade = {}
    all_time_high = {}
    price_history = defaultdict(list)  # {cat: [{date, price, floor}, ...]}

    for t in trades:
        cat = get_cat(t)
        if not cat:
            continue
        price = parse_price(t)
        if price <= 0:
            continue
        deal_type = t.get("_deal_type", "매매")
        date_str = parse_date(t)
        floor = parse_floor(t)

        suffix = "" if deal_type == "매매" else "_jeonse"
        key = cat + suffix

        # 개별 거래 기록 (점 하나 = 거래 1건)
        price_history[key].append({
            "date": date_str,
            "price": price,
            "floor": floor,
        })

        # 최근 거래
        if key not in recent_trade or date_str > (recent_trade[key].get("date") or ""):
            recent_trade[key] = {
                "price": price,
                "floor": floor,
                "date": date_str,
                "type": deal_type,
            }

        # 역대 최고 (매매만)
        if deal_type == "매매":
            if cat not in all_time_high or price > all_time_high[cat].get("price", 0):
                all_time_high[cat] = {
                    "price": price,
                    "date": date_str,
                }

    if not recent_trade:
        return None

    # 전세가율 계산 (첫 번째 평형 기준)
    jeonse_rate = None
    if categories:
        sale_key = categories[0]
        jeonse_key = categories[0] + "_jeonse"
        if sale_key in recent_trade and jeonse_key in recent_trade:
            sp = recent_trade[sale_key]["price"]
            jp = recent_trade[jeonse_key]["price"]
            if sp > 0:
                jeonse_rate = round(jp / sp * 100, 1)

    # price_history: 개별 거래를 날짜순 정렬
    ph = {}
    for key, items in price_history.items():
        sorted_items = sorted(items, key=lambda x: x.get("date", ""))
        ph[key] = sorted_items

    # 위치 정보
    sgg = apt.get("sgg") or ""
    umd = apt.get("umd_nm") or ""
    location = f"{sgg} {umd}".strip() if sgg else ""

    build_year = None
    use_date = apt.get("use_date") or ""
    if use_date and len(use_date) >= 4:
        try:
            build_year = int(use_date[:4])
        except:
            pass

    households = None
    try:
        households = int(apt.get("households") or 0) or None
    except:
        pass

    slug = apt.get("slug") or apt.get("kapt_name") or ""
    danji_id = slug.replace(" ", "-").lower()
    # 간단한 slug 정리
    import re as _re
    danji_id = _re.sub(r'[^a-z0-9가-힣\-]', '', danji_id)
    if not danji_id:
        danji_id = apt.get("kapt_code", "unknown")

    top_floor = None
    try:
        top_floor = int(apt.get("top_floor") or 0) or None
    except:
        pass

    parking = None
    try:
        parking = int(apt.get("parking") or 0) or None
    except:
        pass

    return {
        "id": danji_id,
        "complex_name": apt.get("kapt_name") or "",
        "location": location,
        "address": apt.get("doro_juso") or "",
        "lat": apt.get("lat"),
        "lng": apt.get("lon"),
        "total_units": households,
        "build_year": build_year,
        "top_floor": top_floor,
        "parking": parking,
        "categories": categories,
        "recent_trade": recent_trade,
        "all_time_high": all_time_high,
        "jeonse_rate": jeonse_rate,
        "price_history": ph,
        "seo_text": "",
        "updated_at": datetime.now().isoformat(),
    }


def update_danji_pages(danji_list: list):
    """danji_pages 테이블 upsert"""
    if not danji_list:
        return 0

    batch_size = 50
    total = 0
    for i in range(0, len(danji_list), batch_size):
        batch = danji_list[i:i + batch_size]
        resp = sb_session.post(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            headers=SB_HEADERS,
            json=batch,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            total += len(batch)
        else:
            print(f"  ⚠️ danji_pages upsert: {resp.status_code} {resp.text[:200]}")

    return total


# ========================================================
# 메인
# ========================================================
def main():
    parser = argparse.ArgumentParser(description="실거래가 동기화")
    parser.add_argument("--init", action="store_true", help="초기 36개월 전체 수집")
    parser.add_argument("--months", type=int, default=2, help="수집할 월 수 (기본: 2 = 당월+전월)")
    parser.add_argument("--skip-aggregate", action="store_true", help="집계 건너뛰기 (수집만)")
    parser.add_argument("--gu", default=None, help="특정 구만 (예: 11440=마포구)")
    args = parser.parse_args()

    months = 36 if args.init else args.months
    now = datetime.now()

    print(f"{'='*50}")
    print(f"🔄 실거래가 동기화")
    print(f"   모드: {'초기 수집 (36개월)' if args.init else f'일일 동기화 ({months}개월)'}")
    print(f"   시각: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # 수집할 월 목록
    ym_list = [(now - relativedelta(months=i)).strftime("%Y%m") for i in range(months)]
    print(f"📅 수집 대상: {ym_list[0]} ~ {ym_list[-1]} ({len(ym_list)}개월)")

    lawd_codes = [args.gu] if args.gu else list(SEOUL_GU.keys())

    # 1단계: 수집 + 저장
    total_trades = 0
    total_cached = 0
    for ym in ym_list:
        print(f"\n── {ym} ──")
        all_data = fetch_all_for_month(ym, lawd_codes)
        if all_data:
            cached = upsert_trade_cache(ym, all_data)
            total_cached += cached
            total_trades += sum(len(v) for v in all_data.values())
        time.sleep(0.5)  # API 부하 방지

    print(f"\n✅ 수집 완료: {total_trades}건 → trade_cache {total_cached}행 저장")

    # 2단계: 집계
    if args.skip_aggregate:
        print("⏭️  집계 건너뜀 (--skip-aggregate)")
        return

    print(f"\n{'='*50}")
    print(f"📊 danji_pages 집계 시작")
    print(f"{'='*50}\n")

    apartments = load_apartments()
    if not apartments:
        print("❌ apartments 테이블 비어있음")
        return

    # 구별로 처리
    gu_apts = defaultdict(list)
    for apt in apartments:
        code = apt.get("lawd_cd") or ""
        if code in SEOUL_GU:
            gu_apts[code].append(apt)

    danji_list = []
    for code in lawd_codes:
        if code not in gu_apts:
            continue
        gu_name = SEOUL_GU.get(code, code)
        apts = gu_apts[code]
        print(f"\n  {gu_name}: {len(apts)}개 단지")

        # 이 구의 trade_cache 로드
        cache_rows = load_trade_cache_for_gu(code)
        if not cache_rows:
            print(f"    ⚠️ trade_cache 없음")
            continue

        for apt in apts:
            trades = match_trades_to_complex(apt, cache_rows)
            if not trades:
                continue
            danji = aggregate_danji(apt, trades)
            if danji:
                danji_list.append(danji)

        print(f"    → {sum(1 for d in danji_list if d.get('location','').startswith(gu_name) or True)}개 집계")

    print(f"\n📦 danji_pages 업데이트: {len(danji_list)}개 단지")
    if danji_list:
        updated = update_danji_pages(danji_list)
        print(f"✅ {updated}개 upsert 완료")

    print(f"\n{'='*50}")
    print(f"🏁 동기화 완료")
    print(f"   거래: {total_trades}건")
    print(f"   단지: {len(danji_list)}개")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
