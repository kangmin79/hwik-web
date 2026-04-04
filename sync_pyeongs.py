# -*- coding: utf-8 -*-
"""
건축물대장 API로 전체 단지의 전용/공급면적 수집
- getBrExposPubuseAreaInfo API 호출
- 호별 전용면적 + 공용면적 → 분양면적(공급면적) 계산
- apartments.pyeongs 업데이트

사용법:
  python sync_pyeongs.py              # pyeongs 비어있는 단지만
  python sync_pyeongs.py --all        # 전체 갱신
  python sync_pyeongs.py --gu 11680   # 특정 구만
"""

import os
import sys
import json
import time
import math
import argparse
import ssl
import urllib3
import requests
from requests.adapters import HTTPAdapter
from collections import defaultdict

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

urllib3.disable_warnings()


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

BUILDING_API_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo"

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


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

# 주거용도만 (상가/주차장 등 제외)
APT_TYPES = {"아파트", "공동주택", "연립주택", "다세대주택"}
OFFI_TYPES = {"오피스텔"}


def load_apartments(only_empty=True, gu=None):
    """apartments 테이블 로드"""
    all_apts = []
    offset = 0
    limit = 1000
    while True:
        params = {
            "select": "kapt_code,kapt_name,bjd_code,jibun,property_type,pyeongs,lawd_cd",
            "limit": str(limit),
            "offset": str(offset),
        }
        if only_empty:
            params["or"] = "(pyeongs.is.null,pyeongs.eq.[])"
        if gu:
            params["lawd_cd"] = f"eq.{gu}"
        resp = sb_session.get(
            f"{SUPABASE_URL}/rest/v1/apartments",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params,
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
    return all_apts


def fetch_building_areas(sigunguCd, bjdongCd, bun, ji):
    """건축물대장 전유공용면적 API 호출"""
    base_params = {
        "serviceKey": GOV_SERVICE_KEY,
        "sigunguCd": sigunguCd,
        "bjdongCd": bjdongCd,
        "bun": bun,
        "ji": ji,
        "numOfRows": "100",
        "_type": "json",
    }

    try:
        r = gov_session.get(BUILDING_API_URL, params={**base_params, "pageNo": "1"}, timeout=15)
        if r.status_code != 200:
            return []
        body = r.json().get("response", {}).get("body", {})
        total = int(body.get("totalCount", 0))

        items = body.get("items") or {}
        lst = items.get("item", [])
        if isinstance(lst, dict):
            lst = [lst]
        item_list = lst or []

        # 평형 파악 목적 → 최대 10페이지(1000건)
        total_pages = math.ceil(total / 100)
        max_pages = min(total_pages, 10)

        for page in range(2, max_pages + 1):
            r = gov_session.get(BUILDING_API_URL, params={**base_params, "pageNo": str(page)}, timeout=15)
            if r.status_code == 200:
                body2 = r.json().get("response", {}).get("body", {})
                items2 = body2.get("items") or {}
                lst2 = items2.get("item", [])
                if isinstance(lst2, dict):
                    lst2 = [lst2]
                item_list.extend(lst2 or [])

        return item_list

    except Exception as e:
        return []


RESIDENTIAL_COMMON_KEYWORDS = ['복도', '계단', '승강기', '홀', '현관', '통로', '벽체', '엘리베이터']

def is_residential_common(etc_purps):
    """주거공용 여부 판별 (복도/계단/승강기/홀/현관/통로/벽체만)"""
    if not etc_purps:
        return False
    return any(k in etc_purps for k in RESIDENTIAL_COMMON_KEYWORDS)


def calc_pyeongs(items, property_type):
    """호별 전용 + 주거공용만 합산 → [{exclu, supply}, ...]"""
    # 호별 전용/주거공용 합산 (전체 items에서 — 용도 필터는 전유에만 적용)
    target_types = OFFI_TYPES if property_type == "offi" else APT_TYPES

    ho_expos = {}       # 호 → 전용면적
    ho_res_common = {}  # 호 → 주거공용면적만

    for it in items:
        gb = it.get("exposPubuseGbCd", "")
        ho = it.get("hoNm", "").strip()
        purp_nm = it.get("mainPurpsCdNm", "")
        etc_purps = it.get("etcPurps", "").strip()
        try:
            ar = float(it.get("area", 0) or 0)
        except:
            ar = 0
        if not ho or ar <= 0:
            continue

        if gb == "1" and purp_nm in target_types:
            # 전유 (아파트/오피스텔 용도만)
            ho_expos[ho] = ho_expos.get(ho, 0) + ar
        elif gb == "2" and is_residential_common(etc_purps):
            # 공용 중 주거공용만 (복도/계단/승강기/홀/현관/통로/벽체)
            ho_res_common[ho] = ho_res_common.get(ho, 0) + ar

    # 공급면적 = 전용 + 주거공용
    raw = defaultdict(list)
    for ho, expos in ho_expos.items():
        res_com = ho_res_common.get(ho, 0)
        supply = expos + res_com
        raw[round(expos, 2)].append(round(supply, 2))

    if not raw:
        return []

    # 2㎡ 이내 클러스터링
    keys = sorted(raw.keys())
    clusters = []
    current = [keys[0]]
    for k in keys[1:]:
        if k - current[0] <= 2.0:
            current.append(k)
        else:
            clusters.append(current)
            current = [k]
    clusters.append(current)

    result = []
    for cluster in clusters:
        rep = max(cluster, key=lambda k: len(raw[k]))
        all_supply = []
        for k in cluster:
            all_supply.extend(raw[k])
        avg_supply = round(sum(all_supply) / len(all_supply), 2) if all_supply else 0
        result.append({
            "exclu": round(rep, 2),
            "supply": avg_supply,
        })

    result.sort(key=lambda x: x["exclu"])
    return result


def update_pyeongs(kapt_code, pyeongs):
    """apartments 테이블 업데이트"""
    for attempt in range(3):
        try:
            resp = sb_session.patch(
                f"{SUPABASE_URL}/rest/v1/apartments?kapt_code=eq.{kapt_code}",
                headers=SB_HEADERS,
                json={"pyeongs": pyeongs},
                timeout=15,
            )
            return resp.status_code in (200, 204)
        except:
            if attempt < 2:
                time.sleep(1)
    return False


def main():
    parser = argparse.ArgumentParser(description="건축물대장 전용/공급면적 수집")
    parser.add_argument("--all", action="store_true", help="전체 단지 갱신")
    parser.add_argument("--gu", default=None, help="특정 구만 (예: 11680)")
    args = parser.parse_args()

    print("=" * 50)
    print("📐 전용/공급면적 수집 (건축물대장 API)")
    print("=" * 50)

    apts = load_apartments(only_empty=not args.all, gu=args.gu)
    print(f"\n📦 대상 단지: {len(apts)}개")

    success = 0
    fail = 0
    skip = 0

    for i, apt in enumerate(apts):
        kapt_code = apt["kapt_code"]
        bjd_code = apt.get("bjd_code") or ""
        jibun = apt.get("jibun") or ""
        prop_type = apt.get("property_type") or "apt"

        if len(bjd_code) < 10 or not jibun:
            skip += 1
            continue

        sigunguCd = bjd_code[:5]
        bjdongCd = bjd_code[5:]

        # 지번 파싱 (본번-부번)
        parts = jibun.split("-")
        bun = parts[0].strip().zfill(4)
        ji = parts[1].strip().zfill(4) if len(parts) > 1 else "0000"

        # API 호출
        items = fetch_building_areas(sigunguCd, bjdongCd, bun, ji)

        if items:
            pyeongs = calc_pyeongs(items, prop_type)
            if pyeongs:
                ok = update_pyeongs(kapt_code, pyeongs)
                if ok:
                    success += 1
                else:
                    fail += 1
            else:
                skip += 1
        else:
            skip += 1

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(apts)}] 성공:{success} 실패:{fail} 건너뜀:{skip}")

        # API rate limit
        time.sleep(0.2)

    print(f"\n{'=' * 50}")
    print(f"✅ 완료: 성공 {success} / 실패 {fail} / 건너뜀 {skip} / 전체 {len(apts)}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
