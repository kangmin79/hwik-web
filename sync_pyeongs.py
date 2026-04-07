# -*- coding: utf-8 -*-
"""
건축물대장 API로 전체 단지의 전용/공급면적 수집
- getBrExposPubuseAreaInfo API 호출 (bun만 사용, ji 생략 → 모든 부번 포함)
- bldNm(건물명)으로 단지별 필터링
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
import re
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

APT_TYPES = {"아파트", "공동주택", "연립주택", "다세대주택"}
OFFI_TYPES = {"오피스텔"}
RESIDENTIAL_COMMON_KEYWORDS = ['복도', '계단', '승강기', '홀', '현관', '통로', '벽체', '엘리베이터']


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


def fetch_bun_all(sigunguCd, bjdongCd, bun):
    """특정 번지의 모든 부번 전유공용면적 조회 (ji 생략)"""
    base_params = {
        "serviceKey": GOV_SERVICE_KEY,
        "sigunguCd": sigunguCd,
        "bjdongCd": bjdongCd,
        "bun": bun,
        "numOfRows": "500",
        "_type": "json",
    }

    try:
        r = gov_session.get(BUILDING_API_URL, params={**base_params, "pageNo": "1"}, timeout=30)
        if r.status_code != 200:
            return 0, []
        body = r.json().get("response", {}).get("body", {})
        total = int(body.get("totalCount", 0))

        if total == 0:
            return 0, []

        items = body.get("items") or {}
        lst = items.get("item", [])
        if isinstance(lst, dict):
            lst = [lst]
        item_list = lst or []

        total_pages = math.ceil(total / 500)

        for page in range(2, total_pages + 1):
            r = gov_session.get(BUILDING_API_URL, params={**base_params, "pageNo": str(page)}, timeout=30)
            if r.status_code == 200:
                body2 = r.json().get("response", {}).get("body", {})
                items2 = body2.get("items") or {}
                lst2 = items2.get("item", [])
                if isinstance(lst2, dict):
                    lst2 = [lst2]
                item_list.extend(lst2 or [])
            if page % 10 == 0:
                time.sleep(0.3)

        return total, item_list

    except Exception as e:
        print(f"    API 오류: {e}")
        return 0, []


def normalize_name(name):
    """단지명 정규화 (동번호 제거, 공백/괄호 제거)"""
    if not name:
        return ""
    n = name.strip()
    # "은마아파트 제13동", "래미안 101동", "아파트 5동" 등
    n = re.sub(r'\s*제?\d+동$', '', n)
    n = re.sub(r'\([^)]*\)', '', n)
    n = re.sub(r'\s+', '', n)
    return n


SUFFIX_BLOCK = re.compile(r'^(\d+차|\d+단지|\d+차아파트|임대|주상복합)')


def filter_items_for_apt(all_items, kapt_name):
    """전체 데이터에서 특정 단지의 items만 필터 (3단계 매칭)"""
    kn = normalize_name(kapt_name)
    if not kn or len(kn) < 2:
        return []

    bld_groups = defaultdict(list)
    for it in all_items:
        bn = normalize_name(it.get("bldNm", ""))
        if bn:
            bld_groups[bn].append(it)

    # 1단계: 정확 매칭
    if kn in bld_groups:
        return bld_groups[kn]

    # 2단계: 접두어 매칭 (4자 이상, 차수/단지 차단)
    if len(kn) >= 4:
        matched = []
        for bn, items in bld_groups.items():
            if bn.startswith(kn):
                remainder = bn[len(kn):]
                if not remainder or not SUFFIX_BLOCK.match(remainder):
                    matched.extend(items)
            elif kn.startswith(bn) and len(bn) >= 4:
                remainder = kn[len(bn):]
                if not remainder or not SUFFIX_BLOCK.match(remainder):
                    matched.extend(items)
        if matched:
            return matched

    # 3단계: 공통 접두어 (5자+ & 70% 이상)
    if len(kn) >= 5:
        best_match = []
        best_overlap = 0
        for bn, items in bld_groups.items():
            common = 0
            for c1, c2 in zip(kn, bn):
                if c1 == c2:
                    common += 1
                else:
                    break
            if common >= max(5, len(kn) * 0.7) and common > best_overlap:
                best_overlap = common
                best_match = items
        return best_match

    return []


def is_residential_common(etc_purps):
    if not etc_purps:
        return False
    return any(k in etc_purps for k in RESIDENTIAL_COMMON_KEYWORDS)


def calc_pyeongs(items, property_type):
    """호별 전용 + 주거공용만 합산 → [{exclu, supply}, ...]"""
    target_types = OFFI_TYPES if property_type == "offi" else APT_TYPES

    ho_expos = {}
    ho_res_common = {}

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
            ho_expos[ho] = ho_expos.get(ho, 0) + ar
        elif gb == "2" and is_residential_common(etc_purps):
            ho_res_common[ho] = ho_res_common.get(ho, 0) + ar

    raw = defaultdict(list)
    for ho, expos in ho_expos.items():
        res_com = ho_res_common.get(ho, 0)
        supply = expos + res_com
        raw[round(expos, 2)].append(round(supply, 2))

    if not raw:
        return []

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
    print("전용/공급면적 수집 (건축물대장 API)")
    print("  방식: bun만 사용 + ji 생략 + bldNm 필터")
    print("=" * 50)

    apts = load_apartments(only_empty=not args.all, gu=args.gu)
    print(f"\n대상 단지: {len(apts)}개")

    # 같은 bjd_code + bun으로 그룹화 (1회 API 호출로 여러 단지 처리)
    bun_groups = defaultdict(list)  # key: (sigunguCd, bjdongCd, bun)
    skip_no_bjd = 0
    for apt in apts:
        bjd_code = apt.get("bjd_code") or ""
        jibun = apt.get("jibun") or ""
        if len(bjd_code) < 10 or not jibun:
            skip_no_bjd += 1
            continue
        sigunguCd = bjd_code[:5]
        bjdongCd = bjd_code[5:]
        bun = jibun.split("-")[0].strip().zfill(4)
        bun_groups[(sigunguCd, bjdongCd, bun)].append(apt)

    print(f"번지 그룹: {len(bun_groups)}개 (bjd_code/jibun 없음: {skip_no_bjd}개)")

    success = 0
    fail = 0
    skip = 0
    bun_count = 0
    api_calls = 0

    for (sigunguCd, bjdongCd, bun), apt_list in bun_groups.items():
        bun_count += 1
        names = [a.get("kapt_name", "") for a in apt_list]

        # 같은 번지의 모든 부번 데이터 1회 조회
        total, all_items = fetch_bun_all(sigunguCd, bjdongCd, bun)
        api_calls += math.ceil(total / 500) if total > 0 else 1

        if not all_items:
            skip += len(apt_list)
            if bun_count % 100 == 0:
                print(f"  [{bun_count}/{len(bun_groups)}] 성공:{success} 실패:{fail} 건너뜀:{skip + skip_no_bjd} API:{api_calls}")
            time.sleep(0.3)
            continue

        # 각 단지별 bldNm 필터링
        for apt in apt_list:
            kapt_code = apt["kapt_code"]
            kapt_name = apt.get("kapt_name", "")
            prop_type = apt.get("property_type") or "apt"

            apt_items = filter_items_for_apt(all_items, kapt_name)

            if apt_items:
                pyeongs = calc_pyeongs(apt_items, prop_type)
                if pyeongs:
                    ok = update_pyeongs(kapt_code, pyeongs)
                    if ok:
                        success += 1
                        print(f"  OK {kapt_name}: {len(pyeongs)}개 평형 ({len(apt_items)}건)")
                    else:
                        fail += 1
                else:
                    skip += 1
            else:
                skip += 1

        # API rate limit
        time.sleep(0.3)

        if bun_count % 100 == 0:
            print(f"  [{bun_count}/{len(bun_groups)}] 성공:{success} 실패:{fail} 건너뜀:{skip + skip_no_bjd} API:{api_calls}")

    print(f"\n{'=' * 50}")
    print(f"완료: 성공 {success} / 실패 {fail} / 건너뜀 {skip + skip_no_bjd} / 전체 {len(apts)}")
    print(f"API 호출: 약 {api_calls}회")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
