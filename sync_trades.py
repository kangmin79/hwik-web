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
SUPABASE_URL_FALLBACK = "https://jqaxejgzkchxbfzgzyzi.supabase.co"
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

# ── 인천 10개 구/군 ──────────────────────────────────────
INCHEON_GU = {
    "28110": "중구",   "28140": "동구",     "28177": "미추홀구",
    "28185": "연수구", "28200": "남동구",   "28237": "부평구",
    "28245": "계양구", "28260": "서구",     "28710": "강화군",
    "28720": "옹진군",
}

# ── 경기 39개 시/구 ──────────────────────────────────────
GYEONGGI_SI = {
    "41111": "수원시 장안구", "41113": "수원시 권선구",
    "41115": "수원시 팔달구", "41117": "수원시 영통구",
    "41131": "성남시 수정구", "41133": "성남시 중원구", "41135": "성남시 분당구",
    "41150": "의정부시",      "41170": "안양시 만안구", "41171": "안양시 동안구",
    "41190": "부천시",        "41210": "평택시",
    "41250": "안산시 상록구", "41271": "안산시 단원구",
    "41273": "고양시 덕양구", "41281": "고양시 일산동구", "41285": "고양시 일산서구",
    "41290": "과천시",        "41310": "구리시",          "41360": "남양주시",
    "41370": "오산시",        "41390": "시흥시",          "41410": "군포시",
    "41430": "의왕시",        "41450": "하남시",
    "41461": "용인시 처인구", "41463": "용인시 기흥구",  "41465": "용인시 수지구",
    "41480": "파주시",        "41500": "이천시",          "41550": "안성시",
    "41570": "김포시",        "41590": "화성시",          "41610": "광주시",
    "41630": "양주시",        "41650": "포천시",          "41670": "여주시",
    "41800": "연천군",        "41820": "가평군",          "41830": "양평군",
}

# ── 수도권 전체 ───────────────────────────────────────────
ALL_REGIONS = {**SEOUL_GU, **INCHEON_GU, **GYEONGGI_SI}

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
        }, headers={"Accept": "application/xml"}, timeout=60)

        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item"):
            row = {c.tag: (c.text.strip() if c.text else "") for c in item}
            row["_lawd_cd"] = lawd_cd
            row["_year_month"] = year_month

            # 전월세 API: monthlyRent(월세금) > 0이면 월세, 아니면 전세
            if deal_type == "전세":
                monthly = row.get("monthlyRent") or row.get("monthlyAmount") or "0"
                try:
                    monthly_val = int(str(monthly).replace(",", "").strip() or "0")
                except:
                    monthly_val = 0
                row["_deal_type"] = "월세" if monthly_val > 0 else "전세"
            else:
                row["_deal_type"] = deal_type

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
    codes = lawd_codes or list(ALL_REGIONS.keys())
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

    # 1건씩 upsert (data 필드가 크므로)
    total = 0
    for row in rows:
        for attempt in range(3):
            try:
                resp = sb_session.post(
                    f"{SUPABASE_URL}/rest/v1/trade_cache",
                    headers=SB_HEADERS,
                    json=[row],
                    timeout=60,
                )
                if resp.status_code in (200, 201):
                    total += 1
                    break
                else:
                    if attempt < 2:
                        time.sleep(1)
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    print(f"  ⚠️ upsert 실패: {row['kapt_code']}/{row['year_month']} — {e}")

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


def load_trade_cache_for_gu(lawd_cd: str) -> list:
    """특정 구의 trade_cache 전체 로드"""
    all_rows = []
    offset = 0
    limit = 500
    while True:
        for attempt in range(3):
            try:
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
                    timeout=90,
                )
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(3)
                else:
                    print(f"  ⚠️ trade_cache 로드 실패: {lawd_cd} offset={offset}")
                    return all_rows
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
                # item에 이미 _deal_type이 있으면 유지 (전세/월세 분리됨)
                if "_deal_type" not in item:
                    item["_deal_type"] = row.get("deal_type", "")
                if "_year_month" not in item:
                    item["_year_month"] = row.get("year_month", "")
                matched.append(item)

    return matched


def aggregate_danji(apt: dict, trades: list) -> dict | None:
    """단지별 거래 데이터를 danji_pages 포맷으로 집계"""
    if not trades:
        return None

    pyeongs = apt.get("pyeongs") or []
    # 공급면적 매핑 테이블 (전용→공급)
    pyeongs_map = {}  # {"39": {"exclu": 39, "supply": 91}}
    for p in pyeongs:
        exclu = p.get("exclu", 0)
        supply = p.get("supply", 0)
        if exclu <= 0:
            continue
        cat = str(round(exclu))
        pyeongs_map[cat] = {"exclu": round(exclu, 1), "supply": round(supply, 1)}

    # categories는 항상 실거래 데이터에서 추출 (거래 있는 평형만)
    areas = set()
    for t in trades:
        try:
            area = float(t.get("excluUseAr") or t.get("exclusiveArea") or 0)
            if area > 0:
                areas.add(str(round(area)))
        except:
            pass
    categories = sorted(areas, key=lambda x: float(x))

    # pyeongs_map에서 매칭 안 되는 카테고리는 가장 가까운 것으로 매핑 (±10㎡ 이내만)
    if pyeongs_map:
        pm_keys = [float(k) for k in pyeongs_map.keys()]
        for cat in categories:
            if cat not in pyeongs_map and pm_keys:
                closest = min(pm_keys, key=lambda k: abs(k - float(cat)))
                if abs(closest - float(cat)) <= 10:
                    pyeongs_map[cat] = pyeongs_map[str(round(closest))]

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

        if deal_type == "매매":
            suffix = ""
        elif deal_type == "전세":
            suffix = "_jeonse"
        elif deal_type == "월세":
            suffix = "_wolse"
        else:
            suffix = ""
        key = cat + suffix

        # 개별 거래 기록
        record = {"date": date_str, "price": price, "floor": floor}
        # 월세는 월세금도 저장
        if deal_type == "월세":
            monthly_raw = t.get("monthlyRent") or t.get("monthlyAmount") or "0"
            try:
                record["monthly"] = int(str(monthly_raw).replace(",", "").strip() or "0")
            except:
                record["monthly"] = 0
        price_history[key].append(record)

        # 최근 거래
        if key not in recent_trade or date_str > (recent_trade[key].get("date") or ""):
            recent_trade[key] = {
                "price": price,
                "floor": floor,
                "date": date_str,
                "type": deal_type,
            }

        # 3년 내 최고 (매매 + 전세)
        if deal_type in ("매매", "전세"):
            high_key = cat if deal_type == "매매" else cat + "_jeonse"
            if high_key not in all_time_high or price > all_time_high[high_key].get("price", 0):
                all_time_high[high_key] = {
                    "price": price,
                    "date": date_str,
                }

    if not recent_trade:
        return None

    # 거래 3건 미만 제외 (thin content — Google SEO)
    total_trade_count = sum(len(v) for v in price_history.values())
    if total_trade_count < 3:
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

    # 위치 정보 (없으면 제외)
    sgg = apt.get("sgg") or ""
    umd = apt.get("umd_nm") or ""
    location = f"{sgg} {umd}".strip() if sgg else ""
    if not location:
        return None

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

    # ★ ID = kapt_code 기반 (해시 없음, 어디서 실행해도 동일)
    import re as _re
    kapt_code = apt.get("kapt_code") or ""
    if kapt_code.startswith("A"):
        # 아파트: A10021652 → a10021652
        danji_id = kapt_code.lower()
    else:
        # 오피스텔: offi-11500-킹덤하이너스 → 정리
        cleaned = kapt_code.replace("/", "").replace(" ", "").lower()
        # 한글+영문+숫자+하이픈만 유지
        danji_id = _re.sub(r'[^a-z0-9가-힣\-]', '', cleaned)
        # 로마자 → 숫자
        _roman_map = {'ⅰ':'1','ⅱ':'2','ⅲ':'3','ⅳ':'4','ⅴ':'5',
                      'Ⅰ':'1','Ⅱ':'2','Ⅲ':'3','Ⅳ':'4','Ⅴ':'5'}
        for roman, num in _roman_map.items():
            danji_id = danji_id.replace(roman, num)
    if not danji_id:
        danji_id = "unknown-" + str(abs(id(apt)) % 10000)

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

    mgmt_fee = None
    try:
        mgmt_fee = int(apt.get("mgmt_fee") or 0) or None
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
        "heating": apt.get("heating") or None,
        "builder": apt.get("builder") or None,
        "mgmt_fee": mgmt_fee,
        "categories": categories,
        "pyeongs_map": pyeongs_map or None,
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

    # 같은 ID 중복 제거 (마지막 것 유지)
    seen = {}
    for d in danji_list:
        seen[d["id"]] = d
    danji_list = list(seen.values())

    batch_size = 50
    total = 0
    for i in range(0, len(danji_list), batch_size):
        batch = danji_list[i:i + batch_size]
        for attempt in range(3):
            try:
                resp = sb_session.post(
                    f"{SUPABASE_URL}/rest/v1/danji_pages",
                    headers=SB_HEADERS,
                    json=batch,
                    timeout=90,
                )
                if resp.status_code in (200, 201):
                    total += len(batch)
                else:
                    print(f"  ⚠️ danji_pages upsert: {resp.status_code} {resp.text[:200]}")
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(3)
                else:
                    print(f"  ⚠️ danji_pages upsert 실패: {e}")

    return total


# ========================================================
# 주변 단지 매칭
# ========================================================
def fill_nearby_complex(danji_list: list, apartments: list):
    """같은 property_type + 좌표 가까운 단지 3개를 nearby_complex에 채움"""
    import math

    # danji_list를 id로 인덱싱
    danji_map = {d["id"]: d for d in danji_list}

    # apartments를 kapt_code로 인덱싱 (property_type 확인용)
    apt_map = {}
    for apt in apartments:
        apt_map[apt.get("kapt_code", "")] = apt

    # danji → property_type 매핑
    name_to_type = {}
    for apt in apartments:
        name_to_type[apt.get("kapt_name", "")] = apt.get("property_type", "apt")

    def get_prop_type(danji):
        return name_to_type.get(danji.get("complex_name", ""), "apt")

    # 거리 계산
    def haversine(lat1, lon1, lat2, lon2):
        if not all([lat1, lon1, lat2, lon2]):
            return 99999
        R = 6371000
        p = math.pi / 180
        a = 0.5 - math.cos((lat2-lat1)*p)/2 + math.cos(lat1*p)*math.cos(lat2*p)*(1-math.cos((lon2-lon1)*p))/2
        return R * 2 * math.asin(math.sqrt(a))

    # property_type별 그룹
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

        # 같은 타입에서 거리순 정렬 (자기 자신 제외)
        candidates = []
        for other in type_groups[pt]:
            if other["id"] == d["id"]:
                continue
            dist = haversine(lat1, lon1, other.get("lat"), other.get("lng"))
            if dist < 2000:  # 2km 이내
                # 주변 단지의 매매 가격을 평형별로 저장
                rt = other.get("recent_trade") or {}
                other_pm = other.get("pyeongs_map") or {}
                prices = {}  # {"85": {"price":180000, "supply":172}, ...}
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

    # 지하철역 전체 로드 (1282개)
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

    # 학교 전체 로드 — 수도권 범위 (경기 남단 평택 36.99 ~ 경기 북단 연천 38.1)
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
    # 수도권 범위 필터 (평택~연천, 인천 서해안 포함)
    schools = [s for s in schools if s.get("lat") and 36.9 < s["lat"] < 38.3 and 126.3 < s.get("lon", 0) < 127.9]
    print(f"  → {len(schools)}개 학교 로드 (수도권)")

    filled = 0
    for d in danji_list:
        lat1 = d.get("lat")
        lon1 = d.get("lng")
        if not lat1 or not lon1:
            continue

        # 지하철: 1km 이내 (도보 13분), 가까운 순 3개
        nearby_st = []
        for s in stations:
            dist = haversine(lat1, lon1, s.get("lat"), s.get("lon"))
            if dist < 1000:
                nearby_st.append({
                    "name": s["name"],
                    "line": s.get("line", ""),
                    "distance": round(dist),
                })
        nearby_st.sort(key=lambda x: x["distance"])
        d["nearby_subway"] = nearby_st[:3]

        # 학교: 1.5km 이내, 초/중/고 각 1개씩 (가장 가까운)
        school_candidates = []
        for s in schools:
            dist = haversine(lat1, lon1, s.get("lat"), s.get("lon"))
            if dist < 1500:
                school_candidates.append({
                    "name": s["name"],
                    "type": s.get("type", ""),
                    "distance": round(dist),
                })
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
# 변동사항 보고서 이메일 발송
# ========================================================
def send_report(total_trades, total_cached, danji_count, danji_list, elapsed, is_init=False):
    """동기화 결과 보고서를 이메일로 발송"""
    import smtplib
    from email.mime.text import MIMEText

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    report_to = os.environ.get("REPORT_EMAIL", "bgtrfvcdewsx77@gmail.com")

    if not smtp_user or not smtp_pass:
        print("📧 이메일 설정 없음 (SMTP_USER/SMTP_PASS) → 보고서 건너뜀")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    mode = "초기 수집 (36개월)" if is_init else "일일 동기화"
    minutes = round(elapsed / 60, 1)

    # 구별 집계
    gu_stats = defaultdict(lambda: {"count": 0, "new_trades": 0})
    for d in danji_list:
        loc = d.get("location", "")
        gu = loc.split(" ")[0] if loc else "기타"
        gu_stats[gu]["count"] += 1
        # 최근 거래 날짜가 이번달/전월이면 새 거래
        rt = d.get("recent_trade") or {}
        for k, v in rt.items():
            if isinstance(v, dict) and v.get("date", "").startswith(today[:7]):
                gu_stats[gu]["new_trades"] += 1

    # 최고가 거래 TOP 5
    top_trades = []
    for d in danji_list:
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []
        for c in cats:
            t = rt.get(c)
            if t and t.get("price") and t.get("date", "").startswith(today[:7]):
                top_trades.append({
                    "name": d.get("complex_name", ""),
                    "location": d.get("location", ""),
                    "price": t["price"],
                    "date": t["date"],
                    "area": c,
                })
                break
    top_trades.sort(key=lambda x: -x["price"])

    # 보고서 본문
    body = f"""휙 실거래가 동기화 보고서 ({today})
{'='*50}

모드: {mode}
소요시간: {minutes}분
수집 거래: {total_trades:,}건
캐시 저장: {total_cached}행
집계 단지: {danji_count:,}개

구별 집계:
"""
    for gu in sorted(gu_stats.keys()):
        s = gu_stats[gu]
        body += f"  {gu}: {s['count']}개 단지"
        if s["new_trades"] > 0:
            body += f" (이번달 새 거래 {s['new_trades']}건)"
        body += "\n"

    if top_trades:
        body += f"\n이번달 고가 거래 TOP 5:\n"
        for i, t in enumerate(top_trades[:5]):
            price_uk = t["price"] // 10000
            price_rest = t["price"] % 10000
            price_str = f"{price_uk}억" if price_uk > 0 else ""
            if price_rest > 0:
                price_str += f" {price_rest:,}"
            body += f"  {i+1}. {t['name']} ({t['location']}) — {price_str}만원 ({t['area']}㎡, {t['date']})\n"

    body += f"""
{'='*50}
자동 생성 보고서 — hwik.kr
"""

    # 이메일 발송
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[휙] 실거래가 동기화 완료 — {today} ({danji_count:,}개 단지, {total_trades:,}건)"
        msg["From"] = smtp_user
        msg["To"] = report_to

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, report_to, msg.as_string())

        print(f"📧 보고서 이메일 발송 완료 → {report_to}")
    except Exception as e:
        print(f"⚠️ 이메일 발송 실패: {e}")


# ========================================================
# sitemap.xml 자동 생성
# ========================================================
def generate_sitemap(danji_list: list):
    """DB 전체 danji_pages 기반 sitemap.xml 생성 (--gu 옵션에도 전체 반영)"""
    base = "https://hwik.kr"
    today = datetime.now().strftime("%Y-%m-%d")

    # DB에서 전체 danji_pages ID를 가져옴 (특정 구만 집계해도 sitemap은 전체)
    all_danji = []
    offset = 0
    while True:
        resp = sb_session.get(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            headers={**SB_HEADERS, "Prefer": ""},
            params={"select": "id,complex_name,location,updated_at,categories,recent_trade", "order": "id", "offset": offset, "limit": 500},
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

    import re as _re
    from urllib.parse import quote as _quote

    _REGION_MAP = {
        "서울특별시":"서울","인천광역시":"인천","부산광역시":"부산",
        "대구광역시":"대구","광주광역시":"광주","대전광역시":"대전",
        "울산광역시":"울산","세종특별자치시":"세종","경기도":"경기",
        "강원특별자치도":"강원","충청북도":"충북","충청남도":"충남",
        "전북특별자치도":"전북","전라남도":"전남","경상북도":"경북",
        "경상남도":"경남","제주특별자치도":"제주",
        "서울":"서울","인천":"인천","부산":"부산","대구":"대구",
        "광주":"광주","대전":"대전","울산":"울산","세종":"세종",
        "경기":"경기","강원":"강원","충북":"충북","충남":"충남",
        "전북":"전북","전남":"전남","경북":"경북","경남":"경남","제주":"제주",
    }
    _METRO = {"서울","인천","부산","대구","광주","대전","울산"}
    def _clean(s):
        s = _re.sub(r'[^\w가-힣]', '-', s or "")
        return _re.sub(r'-+', '-', s).strip('-')
    def _make_slug(name, location, did, address=""):
        addr_parts = (address or "").split()
        region = _REGION_MAP.get(addr_parts[0], "") if addr_parts else ""
        parts = []
        if region:
            parts.append(region)
            if region in _METRO:
                if len(addr_parts) > 1 and addr_parts[1].endswith("구"):
                    parts.append(addr_parts[1])
            elif region != "세종":
                if len(addr_parts) > 1:
                    parts.append(_re.sub(r'(시|군)$', '', addr_parts[1]))
                if len(addr_parts) > 2 and addr_parts[2].endswith("구"):
                    parts.append(addr_parts[2])
        else:
            loc_parts = (location or "").split(" ")
            if loc_parts and loc_parts[0]:
                parts.append(_clean(loc_parts[0]))
        if did and (did.startswith("offi-") or did.startswith("apt-")):
            parts.append(did)
        else:
            parts.append(_clean(name))
            parts.append(did or "")
        return "-".join([_clean(p) for p in parts if p])

    urls = []
    # 정적 페이지 (priority/changefreq 제거 — Google이 무시함)
    for path in ['/', '/gu.html', '/about.html', '/ranking.html', '/ranking.html?region=incheon', '/ranking.html?region=gyeonggi', '/ranking.html?region=all']:
        urls.append(f'  <url><loc>{base}{path}</loc><lastmod>{today}</lastmod></url>')

    # 구/시 목록 페이지 (서울+인천+경기 전체, 중복 제거)
    seen_gu = set()
    for region_name in ALL_REGIONS.values():
        if region_name in seen_gu:
            continue
        seen_gu.add(region_name)
        safe_name = _quote(region_name, safe='')
        urls.append(f'  <url><loc>{base}/gu.html?name={safe_name}</loc><lastmod>{today}</lastmod></url>')

    # 단지 페이지 (거래 데이터 있는 단지만 — Google 신뢰도 향상)
    included = 0
    excluded = 0
    for d in all_danji:
        did = d.get("id", "")
        if not did:
            continue
        # 거래 데이터 있는지 확인
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []
        has_trade = any(rt.get(c) for c in cats)
        if not has_trade:
            excluded += 1
            continue
        slug = _make_slug(d.get("complex_name", ""), d.get("location", ""), did, d.get("address", ""))
        safe_slug = _quote(slug, safe="-")
        lastmod = (d.get("updated_at") or today)[:10]
        urls.append(f'  <url><loc>{base}/danji/{safe_slug}</loc><lastmod>{lastmod}</lastmod></url>')
        included += 1

    # 동 페이지 (거래 있는 단지 3개 이상인 동만)
    from collections import defaultdict as _defaultdict
    dong_trade_count = _defaultdict(int)  # (gu, dong) → 거래 있는 단지 수
    for d in all_danji:
        loc = d.get("location", "")
        if not loc:
            continue
        parts = loc.split(" ", 1)
        if len(parts) < 2:
            continue
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []
        if any(rt.get(c) for c in cats):
            dong_trade_count[(parts[0], parts[1])] += 1

    dong_count = 0
    for (gu, dong), cnt in sorted(dong_trade_count.items()):
        if cnt < 3:
            continue
        dong_slug = f"{gu}-{dong}"
        dong_slug = _re.sub(r'[^\w가-힣]', '-', dong_slug)
        dong_slug = _re.sub(r'-+', '-', dong_slug).strip('-')
        safe_dong_slug = _quote(dong_slug, safe="-")
        urls.append(f'  <url><loc>{base}/dong/{safe_dong_slug}</loc><lastmod>{today}</lastmod></url>')
        dong_count += 1

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += '\n'.join(urls)
    xml += '\n</urlset>\n'

    # 스크립트와 같은 폴더의 sitemap.xml에 저장
    sitemap_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"\n🗺️  sitemap.xml 생성: 단지 {included}개 + 동 {dong_count}개 포함, {excluded}개 제외 (거래 없음)")


# ========================================================
# 메인
# ========================================================
def main():
    parser = argparse.ArgumentParser(description="실거래가 동기화")
    parser.add_argument("--init", action="store_true", help="초기 36개월 전체 수집")
    parser.add_argument("--months", type=int, default=2, help="수집할 월 수 (기본: 2 = 당월+전월)")
    parser.add_argument("--skip-aggregate", action="store_true", help="집계 건너뛰기 (수집만)")
    parser.add_argument("--aggregate-only", action="store_true", help="집계만 (수집 건너뛰기)")
    parser.add_argument("--gu", default=None, help="특정 구/시만 (예: 11440=마포구, 28185=연수구, 41135=분당구)")
    parser.add_argument("--seoul", action="store_true", help="서울 전체만 처리")
    parser.add_argument("--gyeonggi", action="store_true", help="경기도 전체만 처리")
    parser.add_argument("--incheon", action="store_true", help="인천 전체만 처리")
    parser.add_argument("--reset-danji", action="store_true", help="danji_pages 전체 삭제 후 재생성")
    args = parser.parse_args()

    months = 36 if args.init else args.months
    now = datetime.now()

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
        print("❌ DB 연결 실패 (메인 + fallback 모두)")
        sys.exit(1)

    print(f"{'='*50}")
    print(f"🔄 실거래가 동기화")
    print(f"   모드: {'초기 수집 (36개월)' if args.init else f'일일 동기화 ({months}개월)'}")
    print(f"   시각: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    if args.gu:
        lawd_codes = [args.gu]
    elif args.seoul:
        lawd_codes = list(SEOUL_GU.keys())
    elif args.gyeonggi:
        lawd_codes = list(GYEONGGI_SI.keys())
    elif args.incheon:
        lawd_codes = list(INCHEON_GU.keys())
    else:
        lawd_codes = list(ALL_REGIONS.keys())

    # 1단계: 수집 + 저장 (--aggregate-only면 건너뜀)
    total_trades = 0
    total_cached = 0
    if not args.aggregate_only:
        ym_list = [(now - relativedelta(months=i)).strftime("%Y%m") for i in range(months)]
        print(f"📅 수집 대상: {ym_list[0]} ~ {ym_list[-1]} ({len(ym_list)}개월)")
        for ym in ym_list:
            print(f"\n── {ym} ──")
            all_data = fetch_all_for_month(ym, lawd_codes)
            if all_data:
                cached = upsert_trade_cache(ym, all_data)
                total_cached += cached
                total_trades += sum(len(v) for v in all_data.values())
            time.sleep(0.5)  # API 부하 방지
        print(f"\n✅ 수집 완료: {total_trades}건 → trade_cache {total_cached}행 저장")
    else:
        print("⏭️  수집 건너뜀 (--aggregate-only)")

    # 2단계: 집계
    if args.skip_aggregate:
        print("⏭️  집계 건너뜀 (--skip-aggregate)")
        return

    # --reset-danji: 기존 danji_pages 전체 삭제
    if args.reset_danji:
        print(f"\n🗑️  danji_pages 전체 삭제 중...")
        del_count = 0
        while True:
            resp = sb_session.get(
                f"{SUPABASE_URL}/rest/v1/danji_pages?select=id&limit=500",
                headers={**SB_HEADERS, "Prefer": ""},
                timeout=30,
            )
            ids = [r["id"] for r in resp.json()] if resp.status_code == 200 else []
            if not ids:
                break
            for batch_start in range(0, len(ids), 50):
                batch_ids = ids[batch_start:batch_start + 50]
                id_filter = ",".join(f'"{i}"' for i in batch_ids)
                sb_session.delete(
                    f"{SUPABASE_URL}/rest/v1/danji_pages?id=in.({id_filter})",
                    headers={**SB_HEADERS, "Prefer": ""},
                    timeout=30,
                )
                del_count += len(batch_ids)
            print(f"  삭제 {del_count}건...")
        print(f"✅ danji_pages 전체 삭제 완료: {del_count}건")

    print(f"\n{'='*50}")
    print(f"📊 danji_pages 집계 시작")
    print(f"{'='*50}\n")

    apartments = load_apartments()
    if not apartments:
        print("❌ apartments 테이블 비어있음")
        return

    # 구별로 처리 (서울+인천+경기)
    gu_apts = defaultdict(list)
    for apt in apartments:
        code = apt.get("lawd_cd") or ""
        if code in ALL_REGIONS:
            gu_apts[code].append(apt)

    danji_list = []
    for code in lawd_codes:
        if code not in gu_apts:
            continue
        gu_name = ALL_REGIONS.get(code, code)
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

        gu_count = sum(1 for d in danji_list if d.get('location','').startswith(gu_name))
        print(f"    → {gu_count}개 집계")

    # 주변 단지 매칭 (같은 property_type끼리)
    print(f"\n🏘️  주변 단지 매칭 중...")
    fill_nearby_complex(danji_list, apartments)

    # 주변 지하철/학교 매칭
    print(f"\n🚇 주변 지하철/학교 매칭 중...")
    fill_nearby_facilities(danji_list)

    print(f"\n📦 danji_pages 업데이트: {len(danji_list)}개 단지")
    if danji_list:
        updated = update_danji_pages(danji_list)
        print(f"✅ {updated}개 upsert 완료")

    # sitemap.xml 자동 생성
    generate_sitemap(danji_list)

    # 변동사항 보고서 생성 + 이메일 발송
    elapsed = (datetime.now() - now).total_seconds()
    send_report(
        total_trades=total_trades,
        total_cached=total_cached,
        danji_count=len(danji_list),
        danji_list=danji_list,
        elapsed=elapsed,
        is_init=args.init,
    )

    print(f"\n{'='*50}")
    print(f"🏁 동기화 완료")
    print(f"   거래: {total_trades}건")
    print(f"   단지: {len(danji_list)}개")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
