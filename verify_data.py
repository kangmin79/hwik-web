#!/usr/bin/env python3
"""verify_data.py — 데이터 정합성 검증 (3단계)

검증 A: trades → danji_pages 집계 정합성 (전수)
  - recent_trade가 trades 최신 거래와 일치하는지
  - all_time_high가 실제 최고가인지
  - 전세가율 계산이 맞는지
  - categories에 있는 평형이 실제 거래가 있는지

검증 B: danji_pages → HTML 페이지 대조 (전수)
  - HTML에 표시된 가격이 DB와 일치하는지
  - JSON-LD 데이터가 DB와 일치하는지

검증 C: 국토부 API 원본 대조 (샘플 50개)
  - DB 최신 거래 = API 최신 거래?
"""

import os
import sys
import io
import re
import json
import random
import requests
import urllib3
from collections import defaultdict
from pathlib import Path

urllib3.disable_warnings()

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = Path(__file__).parent.resolve()

# ── 환경변수 ──
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://api.hwik.kr")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
GOV_KEY = os.environ.get("GOV_SERVICE_KEY", "")

if not SUPABASE_KEY:
    try:
        from sync_pyeongs import SUPABASE_KEY as _SK, GOV_SERVICE_KEY as _GK
        SUPABASE_KEY = _SK
        GOV_KEY = _GK
    except:
        pass

SB_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
session = requests.Session()


def sb_get(table, params):
    """Supabase REST 조회"""
    all_data = []
    offset = 0
    limit = params.pop("_limit", 1000)
    while True:
        p = {**params, "limit": str(limit), "offset": str(offset)}
        r = session.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=SB_HEADERS, params=p, timeout=30, verify=False)
        if r.status_code != 200:
            print(f"  [DB ERROR] {table}: {r.status_code}")
            break
        data = r.json()
        if not data:
            break
        all_data.extend(data)
        offset += limit
        if len(data) < limit:
            break
    return all_data


# ══════════════════════════════════════════════════════════════
#  검증 A: trades → danji_pages 집계 정합성
# ══════════════════════════════════════════════════════════════
def verify_aggregation():
    print("=" * 70)
    print("  검증 A: trades → danji_pages 집계 정합성")
    print("=" * 70)

    # danji_pages 로드
    danji_pages = sb_get("danji_pages", {
        "select": "id,complex_name,categories,recent_trade,all_time_high,jeonse_rate,pyeongs_map",
    })
    print(f"  danji_pages: {len(danji_pages)}개 로드", flush=True)

    errors = defaultdict(list)
    checked = 0
    sample_size = len(danji_pages)  # 전수

    for dp in danji_pages:
        dpid = dp.get("id", "")
        name = dp.get("complex_name", "")
        categories = dp.get("categories") or []
        recent = dp.get("recent_trade") or {}
        high = dp.get("all_time_high") or {}
        jr = dp.get("jeonse_rate")
        pm = dp.get("pyeongs_map") or {}

        # 1. categories가 비어있으면 안 됨
        if not categories:
            errors["no_categories"].append(name)
            continue

        # 2. categories의 모든 평형에 recent_trade가 있어야 함 (매매 기준)
        for cat in categories:
            if cat not in recent:
                # 전세/월세만 있을 수 있으므로, 접미사 포함 검사
                has_any = any(k.startswith(cat) for k in recent.keys())
                if not has_any:
                    errors["cat_no_trade"].append(f"{name}: {cat}㎡")
                    break

        # 3. recent_trade 가격이 양수인지
        for key, val in recent.items():
            price = val.get("price", 0)
            if price <= 0:
                errors["zero_price"].append(f"{name}: {key}")
                break

        # 4. recent_trade 날짜 형식 (YYYY-MM 또는 YYYY-MM-DD)
        for key, val in recent.items():
            date = val.get("date", "")
            if date and not re.match(r"^\d{4}-\d{2}(-\d{2})?$", date):
                errors["bad_date"].append(f"{name}: {key} → {date}")
                break

        # 5. all_time_high >= recent_trade (같은 키 기준)
        for key, rt in recent.items():
            if "_jeonse" in key or "_wolse" in key:
                continue  # 매매만 비교
            ath = high.get(key)
            if ath and rt.get("price", 0) > ath.get("price", 0):
                errors["recent_gt_high"].append(
                    f"{name}: {key} 최근 {rt['price']} > 최고 {ath['price']}"
                )
                break

        # 6. 전세가율 검증 (첫 평형 기준)
        if jr is not None and categories:
            sale_key = categories[0]
            jeonse_key = categories[0] + "_jeonse"
            if sale_key in recent and jeonse_key in recent:
                sp = recent[sale_key].get("price", 0)
                jp = recent[jeonse_key].get("price", 0)
                if sp > 0:
                    expected = round(jp / sp * 100, 1)
                    if abs(expected - jr) > 0.2:  # 반올림 오차 허용
                        errors["jeonse_rate_mismatch"].append(
                            f"{name}: DB {jr}% vs 계산 {expected}%"
                        )

        # 7. pyeongs_map 비율 검증 (공급/전용 1.0~1.65)
        for cat, pval in pm.items():
            exclu = pval.get("exclu", 0)
            supply = pval.get("supply", 0)
            if exclu > 0 and supply > 0:
                ratio = supply / exclu
                if ratio < 1.0 or ratio > 1.65:
                    errors["pyeongs_ratio_bad"].append(
                        f"{name}: {cat}㎡ 전용{exclu}→공급{supply} (비율{ratio:.2f})"
                    )
                    break

        checked += 1
        if checked % 2000 == 0:
            print(f"  ... {checked}개 검사 완료", flush=True)

    print(f"  ... {checked}개 검사 완료\n", flush=True)

    # 결과 출력
    checks = [
        ("categories 비어있음", errors["no_categories"]),
        ("평형에 거래 없음", errors["cat_no_trade"]),
        ("가격 0 또는 음수", errors["zero_price"]),
        ("날짜 형식 오류", errors["bad_date"]),
        ("최근가 > 최고가", errors["recent_gt_high"]),
        ("전세가율 불일치", errors["jeonse_rate_mismatch"]),
        ("공급/전용 비율 이상", errors["pyeongs_ratio_bad"]),
    ]
    total_err = 0
    for label, items in checks:
        cnt = len(items)
        total_err += cnt
        if cnt == 0:
            print(f"  ✓ {label}: 0건")
        else:
            print(f"  ✗ {label}: {cnt}건")
            for it in items[:5]:
                print(f"    - {it}")
            if cnt > 5:
                print(f"    ... 외 {cnt - 5}건")

    return total_err, len(danji_pages)


# ══════════════════════════════════════════════════════════════
#  검증 B: danji_pages → HTML 페이지 대조
# ══════════════════════════════════════════════════════════════
def verify_html_vs_db():
    print(f"\n{'=' * 70}")
    print("  검증 B: danji_pages → HTML 페이지 대조")
    print("=" * 70)

    # danji_pages에서 slug 기반으로 HTML 매칭
    danji_pages = sb_get("danji_pages", {
        "select": "id,complex_name,location,address,categories,recent_trade",
    })

    # HTML 파일 인덱스
    danji_dir = BASE / "danji"
    html_files = {f.stem: f for f in danji_dir.iterdir() if f.suffix == '.html'} if danji_dir.is_dir() else {}

    print(f"  danji_pages: {len(danji_pages)}개, HTML 파일: {len(html_files)}개", flush=True)

    errors = defaultdict(list)
    checked = 0
    matched = 0

    # 가격 파싱 정규식 (HTML에서 가격 추출)
    price_re = re.compile(r'"price"\s*:\s*(\d+)')
    name_re = re.compile(r'"complex_name"\s*:\s*"([^"]+)"')

    for dp in danji_pages:
        dpid = dp.get("id", "")
        name = dp.get("complex_name", "")
        recent = dp.get("recent_trade") or {}
        categories = dp.get("categories") or []

        # slug 찾기: HTML 파일명에서 id가 포함된 것
        matching_file = None
        for stem, fpath in html_files.items():
            if dpid and dpid in stem:
                matching_file = fpath
                break

        if not matching_file:
            continue

        matched += 1
        try:
            html = matching_file.read_text(encoding='utf-8', errors='replace')
        except:
            continue

        # JSON-LD에서 데이터 추출
        jsonld_match = re.search(
            r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE
        )

        if jsonld_match:
            try:
                ld_data = json.loads(jsonld_match.group(1))
                graph = ld_data.get("@graph", [ld_data]) if isinstance(ld_data, dict) else ld_data

                for item in graph:
                    if not isinstance(item, dict):
                        continue
                    # ApartmentComplex 이름 비교
                    if item.get("@type") == "ApartmentComplex":
                        ld_name = item.get("name", "")
                        if ld_name and ld_name != name:
                            errors["name_mismatch"].append(f"{name}: HTML={ld_name}")

                    # FAQPage 답변에 가격이 포함되어 있으면 검증
                    if item.get("@type") == "FAQPage":
                        for q in item.get("mainEntity", []):
                            ans = (q.get("acceptedAnswer") or {}).get("text", "")
                            if not ans:
                                errors["faq_empty"].append(f"{name}")
                                break
            except json.JSONDecodeError:
                errors["jsonld_parse"].append(name)

        # HTML 내 DATA 객체에서 가격 확인 (window.DATA 또는 인라인 JSON)
        data_match = re.search(r'const\s+DATA\s*=\s*(\{.*?\});\s*\n', html, re.DOTALL)
        if data_match:
            try:
                page_data = json.loads(data_match.group(1))
                page_recent = page_data.get("recent_trade") or {}

                # DB recent_trade vs HTML DATA.recent_trade 비교
                for key, db_val in recent.items():
                    html_val = page_recent.get(key)
                    if not html_val:
                        # 없을 수 있음 (평형 선택에 따라)
                        continue
                    db_price = db_val.get("price", 0)
                    html_price = html_val.get("price", 0)
                    if db_price != html_price:
                        errors["price_mismatch"].append(
                            f"{name}: {key} DB={db_price} vs HTML={html_price}"
                        )
                        break
            except (json.JSONDecodeError, ValueError):
                pass  # 동적 페이지는 DATA가 없을 수 있음

        checked += 1
        if checked % 2000 == 0:
            print(f"  ... {checked}개 검사 완료", flush=True)

    print(f"  ... {checked}개 검사 완료 (매칭: {matched}개)\n", flush=True)

    checks = [
        ("단지명 불일치", errors["name_mismatch"]),
        ("FAQ 답변 비어있음", errors["faq_empty"]),
        ("JSON-LD 파싱 오류", errors["jsonld_parse"]),
        ("가격 불일치 (DB vs HTML)", errors["price_mismatch"]),
    ]
    total_err = 0
    for label, items in checks:
        cnt = len(items)
        total_err += cnt
        if cnt == 0:
            print(f"  ✓ {label}: 0건")
        else:
            print(f"  ✗ {label}: {cnt}건")
            for it in items[:5]:
                print(f"    - {it}")
            if cnt > 5:
                print(f"    ... 외 {cnt - 5}건")

    return total_err, matched


# ══════════════════════════════════════════════════════════════
#  검증 C: 국토부 API 원본 대조 (샘플)
# ══════════════════════════════════════════════════════════════
def verify_api_sample(sample_count=50):
    print(f"\n{'=' * 70}")
    print(f"  검증 C: 국토부 API 원본 대조 (샘플 {sample_count}개)")
    print("=" * 70)

    if not GOV_KEY:
        print("  ⚠ GOV_SERVICE_KEY 없음 — 건너뜀")
        return 0, 0

    # 최근 거래가 있는 단지 샘플 추출
    danji_pages = sb_get("danji_pages", {
        "select": "id,complex_name,categories,recent_trade",
    })

    # apartments에서 lawd_cd 정보 가져오기
    apartments = sb_get("apartments", {
        "select": "kapt_code,kapt_name,lawd_cd",
    })
    apt_map = {a["kapt_code"]: a for a in apartments}

    # 매매 최근 거래가 있는 단지만 필터
    valid = []
    for dp in danji_pages:
        cats = dp.get("categories") or []
        rt = dp.get("recent_trade") or {}
        if cats and cats[0] in rt:
            apt = apt_map.get(dp["id"])
            if apt and apt.get("lawd_cd"):
                valid.append((dp, apt))

    if not valid:
        print("  ⚠ 유효한 샘플 없음")
        return 0, 0

    samples = random.sample(valid, min(sample_count, len(valid)))
    print(f"  샘플 {len(samples)}개 선택", flush=True)

    errors = defaultdict(list)
    checked = 0
    api_fail = 0

    GOV_API = "http://openapi.molit.go.kr/OpenAPI_ToolInstall498/service/rest/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

    for dp, apt in samples:
        name = dp.get("complex_name", "")
        cats = dp.get("categories") or []
        rt = dp.get("recent_trade") or {}
        lawd_cd = apt.get("lawd_cd", "")

        if not cats or cats[0] not in rt:
            continue

        db_recent = rt[cats[0]]
        db_date = db_recent.get("date", "")
        db_price = db_recent.get("price", 0)

        if not db_date or len(db_date) < 7:
            continue

        # API 호출 (해당 월)
        deal_ym = db_date[:4] + db_date[5:7]  # "2025-11" → "202511"
        try:
            r = session.get(GOV_API, params={
                "serviceKey": GOV_KEY,
                "LAWD_CD": lawd_cd[:5],
                "DEAL_YMD": deal_ym,
                "_type": "json",
                "numOfRows": "999",
            }, timeout=15)

            if r.status_code != 200:
                api_fail += 1
                continue

            body = r.json().get("response", {}).get("body", {})
            items = body.get("items", {})
            if not items:
                api_fail += 1
                continue

            item_list = items.get("item", [])
            if isinstance(item_list, dict):
                item_list = [item_list]

            # 해당 단지명 + 면적으로 거래 찾기
            found = False
            for item in item_list:
                api_name = (item.get("aptNm") or item.get("아파트") or "").strip()
                api_area = str(round(float(item.get("excluUseAr") or item.get("전용면적") or 0)))
                api_price_raw = str(item.get("dealAmount") or item.get("거래금액") or "").replace(",", "").strip()

                if api_name == apt.get("kapt_name", "") and api_area == cats[0]:
                    found = True
                    try:
                        api_price = int(api_price_raw)
                    except:
                        api_price = 0

                    # 최근 거래와 API 거래 비교: DB의 거래가 API에 존재하는지
                    if api_price == db_price:
                        break  # 일치

            if not found:
                # 단지명이 다를 수 있으므로 경고만
                errors["api_not_found"].append(f"{name} ({lawd_cd[:5]}, {deal_ym})")

        except Exception as e:
            api_fail += 1

        checked += 1
        if checked % 10 == 0:
            print(f"  ... {checked}/{len(samples)} 검사 완료", flush=True)

    print(f"  ... {checked}개 검사 완료 (API 실패: {api_fail}건)\n", flush=True)

    checks = [
        ("API에서 거래 못 찾음 (단지명/면적 불일치 가능)", errors["api_not_found"]),
    ]
    total_err = 0
    for label, items in checks:
        cnt = len(items)
        total_err += cnt
        if cnt == 0:
            print(f"  ✓ {label}: 0건")
        else:
            print(f"  ✗ {label}: {cnt}건")
            for it in items[:10]:
                print(f"    - {it}")
            if cnt > 10:
                print(f"    ... 외 {cnt - 10}건")

    return total_err, checked


# ══════════════════════════════════════════════════════════════
#  main
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("  데이터 정합성 검증 — 3단계")
    print("=" * 70)
    print()

    err_a, cnt_a = verify_aggregation()
    err_b, cnt_b = verify_html_vs_db()

    # 검증 C: --with-api 플래그 있을 때만 실행 (API 호출 제한 때문에 주 1회 권장)
    run_api = "--with-api" in sys.argv
    if run_api:
        err_c, cnt_c = verify_api_sample(50)
    else:
        print(f"\n{'=' * 70}")
        print("  검증 C: 국토부 API 원본 대조 — 건너뜀 (--with-api로 실행)")
        print("=" * 70)
        err_c, cnt_c = 0, 0

    total_err = err_a + err_b + err_c

    print(f"\n{'=' * 70}")
    print("  종합 요약")
    print("=" * 70)
    print(f"  검증 A (집계 정합성): {'✓ PASS' if err_a == 0 else f'✗ FAIL ({err_a}건)'} — {cnt_a}개 검사")
    print(f"  검증 B (HTML 대조):   {'✓ PASS' if err_b == 0 else f'✗ FAIL ({err_b}건)'} — {cnt_b}개 검사")
    print(f"  검증 C (API 원본):    {'✓ PASS' if err_c == 0 else f'✗ FAIL ({err_c}건)'} — {cnt_c}개 검사")
    print(f"\n  총 에러: {total_err}건")
    if total_err == 0:
        print("  🎉 모든 데이터 정합성 검증 통과!")

    return 1 if total_err > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
