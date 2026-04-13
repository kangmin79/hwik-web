# -*- coding: utf-8 -*-
"""
build_danji_from_v2.py — trade_raw_v2 → danji_pages 집계

trade_cache(구버전) 대신 trade_raw_v2(신버전)로 danji_pages를 채운다.
apartments.apt_seq 기준으로 trade_raw_v2를 조회해 집계.

사용법:
  python build_danji_from_v2.py --region seoul         # 서울만
  python build_danji_from_v2.py --sigungu 11260        # 중랑구만 (테스트)
  python build_danji_from_v2.py --kapt A13120403       # 단지 1개 (--dry 테스트용)
  python build_danji_from_v2.py --region all           # 전체
  python build_danji_from_v2.py --region all --dry     # 저장 안 하고 출력만

주의:
  - apt_seq 없는 단지는 건너뜀 (match_apt_seq.py 먼저 실행 필요)
  - 거래 3건 미만 단지는 thin content로 제외
  - nearby_* 필드는 기존 danji_pages 값 보존 (덮어쓰지 않음)
"""

import os, sys, re, json, argparse, time
from datetime import datetime, date
from collections import defaultdict
import requests

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

# ── 환경변수 로드 ─────────────────────────────────────────
for fname in (".env", "env"):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    if not os.path.exists(path): continue
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

SB_URL = "https://jqaxejgzkchxbfzgzyzi.supabase.co"
SB_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not SB_KEY:
    sys.exit("❌ SUPABASE_SERVICE_ROLE_KEY 없음")

H      = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"}
H_W    = {**H, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}


# ── Supabase 유틸 ─────────────────────────────────────────
def sb_get(table, params, limit=1000):
    """전체 페이지네이션 조회"""
    rows, offset = [], 0
    while True:
        p = {**params, "limit": str(limit), "offset": str(offset)}
        r = requests.get(f"{SB_URL}/rest/v1/{table}", headers=H, params=p, timeout=30)
        if r.status_code != 200:
            print(f"  ⚠️ GET {table} {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        if not data: break
        rows.extend(data)
        if len(data) < limit: break
        offset += limit
    return rows


def sb_upsert(table, rows, conflict="id"):
    """배치 upsert (200개씩)"""
    if not rows: return 0
    total = 0
    for i in range(0, len(rows), 200):
        batch = rows[i:i+200]
        for attempt in range(3):
            try:
                r = requests.post(
                    f"{SB_URL}/rest/v1/{table}?on_conflict={conflict}",
                    headers=H_W, json=batch, timeout=60
                )
                if r.status_code in (200, 201):
                    total += len(batch); break
                elif attempt < 2:
                    time.sleep(2)
                else:
                    print(f"  ⚠️ upsert 실패 {r.status_code}: {r.text[:200]}")
            except Exception as e:
                if attempt < 2: time.sleep(2)
                else: print(f"  ⚠️ upsert 예외: {e}")
    return total


# ── 면적 매핑 ─────────────────────────────────────────────
def build_pyeongs_map(pyeongs: list) -> dict:
    """apartments.pyeongs → {cat: {exclu, supply}} 매핑 테이블"""
    pm = {}
    for p in (pyeongs or []):
        exclu = p.get("exclu", 0)
        if exclu <= 0: continue
        cat = str(round(exclu))
        entry = {"exclu": round(exclu, 1)}
        supply = p.get("supply")
        if supply and supply > 0:
            entry["supply"] = round(supply, 1)
        pm[cat] = entry
    return pm


def match_official(area_val: float, pm_keys: list) -> str | None:
    """실거래 전용면적 → 공식 평형 키 (±5㎡ 이내)"""
    if not pm_keys:
        return str(round(area_val))
    best_k, best_d = None, 999
    for pk in pm_keys:
        d = abs(area_val - pk)
        if d < best_d:
            best_k, best_d = pk, d
    return str(round(best_k)) if best_d <= 5 else None


# ── 핵심: trade_raw_v2 행 → 집계 ─────────────────────────
def aggregate(apt: dict, trades: list) -> dict | None:
    """
    apartments 행 + trade_raw_v2 행 목록 → danji_pages 행
    trade_raw_v2 필드:
      deal_type, excl_use_ar, price, monthly_rent,
      deal_year, deal_month, deal_day, floor, dealing_gbn
    """
    if not trades:
        return None

    pyeongs_map = build_pyeongs_map(apt.get("pyeongs"))
    pm_keys = sorted([float(k) for k in pyeongs_map.keys()]) if pyeongs_map else []

    # ── 1. 평형별 분류 ────────────────────────────────────
    areas = set()
    for t in trades:
        area = t.get("excl_use_ar") or 0
        try: area = float(area)
        except: continue
        if area <= 0: continue
        cat = match_official(area, pm_keys)
        if cat: areas.add(cat)

    categories = sorted(areas, key=lambda x: float(x))
    if not categories:
        return None

    # ── 2. 거래별 집계 ────────────────────────────────────
    recent_trade  = {}
    all_time_high = {}
    price_history = defaultdict(list)

    for t in trades:
        area = t.get("excl_use_ar") or 0
        try: area = float(area)
        except: continue
        if area <= 0: continue

        cat = match_official(area, pm_keys)
        if not cat: continue

        price = t.get("price") or 0
        try: price = int(price)
        except: price = 0
        if price <= 0: continue

        deal_type = t.get("deal_type", "매매")
        y = t.get("deal_year") or 0
        m = t.get("deal_month") or 0
        d = t.get("deal_day") or 0
        date_str = f"{y}-{str(m).zfill(2)}-{str(d).zfill(2)}" if y and m and d else (
                   f"{y}-{str(m).zfill(2)}" if y and m else "")

        floor = t.get("floor") or 0
        try: floor = int(floor)
        except: floor = 0

        kind = (t.get("dealing_gbn") or "").strip()
        if kind not in ("중개거래", "직거래"):
            kind = ""

        # suffix 결정
        if deal_type == "매매":   suffix = ""
        elif deal_type == "전세": suffix = "_jeonse"
        elif deal_type == "월세": suffix = "_wolse"
        else: continue

        key = cat + suffix

        # 개별 거래 기록
        record = {"date": date_str, "price": price, "floor": floor}
        if kind: record["kind"] = kind
        if deal_type == "월세":
            monthly = t.get("monthly_rent") or 0
            try: record["monthly"] = int(monthly)
            except: record["monthly"] = 0
        price_history[key].append(record)

        # 최근 거래 (날짜 최신)
        if key not in recent_trade or date_str > (recent_trade[key].get("date") or ""):
            recent_trade[key] = {
                "price": price, "floor": floor,
                "date": date_str, "type": deal_type, "kind": kind,
            }

        # 5년 내 최고가 (매매·전세)
        if deal_type in ("매매", "전세"):
            hkey = cat if deal_type == "매매" else cat + "_jeonse"
            if hkey not in all_time_high or price > all_time_high[hkey].get("price", 0):
                all_time_high[hkey] = {"price": price, "date": date_str, "kind": kind}

    if not recent_trade:
        return None

    # thin content 제외 (거래 3건 미만)
    total_cnt = sum(len(v) for v in price_history.values())
    if total_cnt < 3:
        return None

    # ── 3. 전세가율 ───────────────────────────────────────
    jeonse_rate = None
    if categories:
        sp = (recent_trade.get(categories[0]) or {}).get("price")
        jp = (recent_trade.get(categories[0] + "_jeonse") or {}).get("price")
        if sp and jp and sp > 0 and jp > 0:
            jeonse_rate = round(jp / sp * 100, 1)

    # ── 4. price_history 중복 제거 + 정렬 ────────────────
    ph = {}
    for key, items in price_history.items():
        seen = set()
        deduped = []
        for it in items:
            sig = (it.get("date",""), it.get("price",0),
                   it.get("floor",0), it.get("monthly",0), it.get("kind",""))
            if sig not in seen:
                seen.add(sig)
                deduped.append(it)
        ph[key] = sorted(deduped, key=lambda x: x.get("date",""))

    # ── 5. 단지 기본 정보 ─────────────────────────────────
    sgg = apt.get("sgg") or ""
    umd = apt.get("umd_nm") or ""
    location = f"{sgg} {umd}".strip()
    if not location:
        return None

    kapt_code = apt.get("kapt_code") or ""
    if not kapt_code:
        return None  # kapt_code 없으면 id 생성 불가
    danji_id = kapt_code.lower()

    build_year = apt.get("build_year")
    try: build_year = int(build_year) if build_year else None
    except: build_year = None

    households = apt.get("households")
    try: households = int(households) if households else None
    except: households = None

    top_floor = apt.get("top_floor")
    try: top_floor = int(top_floor) if top_floor else None
    except: top_floor = None

    return {
        "id":           danji_id,
        "complex_name": apt.get("kapt_name") or "",
        "location":     location,
        "address":      apt.get("doro_juso") or "",
        "lat":          apt.get("lat"),
        "lng":          apt.get("lon"),
        "total_units":  households,
        "build_year":   build_year,
        "top_floor":    top_floor,
        "heating":      apt.get("heat_type") or None,
        "builder":      apt.get("builder") or None,
        "parking":      apt.get("parking_ground") or None,
        "seo_text":     "",
        "categories":   categories,
        "pyeongs_map":  pyeongs_map or None,
        "recent_trade": recent_trade,
        "all_time_high":all_time_high,
        "jeonse_rate":  jeonse_rate,
        "price_history":ph,
        "updated_at":   datetime.now().isoformat(),
    }


# ── 지역 코드 ─────────────────────────────────────────────
from regions import (
    SEOUL_GU, INCHEON_GU, GYEONGGI_SI,
    BUSAN_GU, DAEGU_GU, GWANGJU_GU, DAEJEON_GU, ULSAN_GU,
    SEJONG_SI, CHUNGBUK_SI, CHUNGNAM_SI,
    JEONBUK_SI, JEONNAM_SI, GYEONGBUK_SI, GYEONGNAM_SI,
    GANGWON_SI, JEJU_SI, ALL_REGIONS,
)

REGION_MAP = {
    "seoul":     SEOUL_GU,    "incheon":   INCHEON_GU,  "gyeonggi":  GYEONGGI_SI,
    "busan":     BUSAN_GU,    "daegu":     DAEGU_GU,    "gwangju":   GWANGJU_GU,
    "daejeon":   DAEJEON_GU,  "ulsan":     ULSAN_GU,    "sejong":    SEJONG_SI,
    "chungbuk":  CHUNGBUK_SI, "chungnam":  CHUNGNAM_SI,
    "jeonbuk":   JEONBUK_SI,  "jeonnam":   JEONNAM_SI,
    "gyeongbuk": GYEONGBUK_SI, "gyeongnam": GYEONGNAM_SI,
    "gangwon":   GANGWON_SI,  "jeju":      JEJU_SI,
}


# ── 구 단위 처리 ──────────────────────────────────────────
def process_lawd(lawd_cd: str, sgg_name: str, dry: bool) -> tuple[int, int, int]:
    """lawd_cd 하나 처리. (처리, 성공, 건너뜀) 반환"""

    # 1. apartments 조회 (apt_seq 있는 것만)
    apts = sb_get("apartments", {
        "select": "kapt_code,kapt_name,apt_seq,sgg,umd_nm,doro_juso,"
                  "lat,lon,build_year,households,top_floor,heat_type,builder,pyeongs,parking_ground",
        "lawd_cd": f"eq.{lawd_cd}",
        "kapt_code": "like.A*",
        "apt_seq": "not.is.null",
    })
    if not apts:
        print(f"  [{sgg_name}] 단지 없음")
        return 0, 0, 0

    total = len(apts)
    ok = skip = 0
    danji_rows = []

    for apt in apts:
        apt_seq = apt.get("apt_seq")
        if not apt_seq:
            skip += 1; continue

        # 2. trade_raw_v2 조회 (해당 단지 전체 거래)
        trades = sb_get("trade_raw_v2", {
            "select": "deal_type,excl_use_ar,price,monthly_rent,"
                      "deal_year,deal_month,deal_day,floor,dealing_gbn",
            "apt_seq": f"eq.{apt_seq}",
            "prop_type": "eq.apt",
        }, limit=1000)

        # 3. 집계
        result = aggregate(apt, trades)
        if result is None:
            skip += 1
            continue

        danji_rows.append(result)
        ok += 1

        # 진행 상황 (50개마다)
        if (ok + skip) % 50 == 0:
            print(f"  [{sgg_name}] {ok+skip}/{total} 처리중 (성공 {ok}, 건너뜀 {skip})")

    print(f"  [{sgg_name}] {total}개 → 성공 {ok} / 건너뜀 {skip}")

    # 4. dry 모드면 첫 번째 결과만 출력
    if dry:
        if danji_rows:
            sample = danji_rows[0]
            print(f"\n  [DRY 샘플] {sample['complex_name']} ({sample['id']})")
            print(f"    categories: {sample['categories']}")
            print(f"    recent_trade 키: {list(sample['recent_trade'].keys())[:5]}")
            print(f"    price_history 키: {list(sample['price_history'].keys())[:3]}")
            cats = sample['categories']
            if cats:
                key = cats[0]
                ph = sample['price_history'].get(key, [])
                print(f"    {key}㎡ 거래 {len(ph)}건, 최신: {ph[-1] if ph else '-'}")
        return total, ok, skip

    # 5. nearby_* 필드 제거 → 기존 DB 값 보존 (upsert 시 덮어쓰지 않음)
    for d in danji_rows:
        for key in ("nearby_subway", "nearby_school", "nearby_complex"):
            if key in d and not d[key]:
                del d[key]

    # 6. upsert
    saved = sb_upsert("danji_pages", danji_rows)
    return total, saved, skip


# ── 메인 ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="trade_raw_v2 → danji_pages 집계")
    parser.add_argument("--region",  type=str, help="seoul/incheon/gyeonggi/busan/daegu/gwangju/daejeon/ulsan/all")
    parser.add_argument("--sigungu", type=str, help="특정 구 코드 (예: 11260,11710)")
    parser.add_argument("--kapt",    type=str, help="단지 1개 kapt_code (예: A13120403)")
    parser.add_argument("--dry",     action="store_true", help="저장 안 하고 출력만")
    args = parser.parse_args()

    if not any([args.region, args.sigungu, args.kapt]):
        parser.print_help(); sys.exit(1)

    # 대상 목록 구성
    targets = []  # [(lawd_cd, name)]

    if args.kapt:
        # 단지 1개 테스트
        kapt_code = args.kapt.upper()
        apts = sb_get("apartments", {
            "select": "kapt_code,kapt_name,apt_seq,sgg,umd_nm,doro_juso,"
                      "lat,lon,build_year,households,top_floor,heat_type,builder,pyeongs,lawd_cd",
            "kapt_code": f"eq.{kapt_code}",
        })
        if not apts:
            sys.exit(f"❌ 단지 없음: {kapt_code}")
        apt = apts[0]
        apt_seq = apt.get("apt_seq")
        if not apt_seq:
            sys.exit(f"❌ apt_seq 없음: {kapt_code} — match_apt_seq.py 먼저 실행")

        print(f"단지 테스트: {apt.get('kapt_name')} ({kapt_code}), apt_seq={apt_seq}")
        trades = sb_get("trade_raw_v2", {
            "select": "deal_type,excl_use_ar,price,monthly_rent,"
                      "deal_year,deal_month,deal_day,floor,dealing_gbn",
            "apt_seq": f"eq.{apt_seq}",
            "prop_type": "eq.apt",
        }, limit=1000)
        print(f"trade_raw_v2 거래 {len(trades)}건 조회")

        result = aggregate(apt, trades)
        if result is None:
            sys.exit("❌ 집계 결과 없음 (거래 없거나 3건 미만)")

        print(f"\n집계 결과:")
        print(f"  id:           {result['id']}")
        print(f"  complex_name: {result['complex_name']}")
        print(f"  location:     {result['location']}")
        print(f"  categories:   {result['categories']}")
        print(f"  recent_trade: {json.dumps(result['recent_trade'], ensure_ascii=False, indent=4)}")
        print(f"  jeonse_rate:  {result['jeonse_rate']}")
        cats = result['categories']
        if cats:
            key = cats[0]
            ph = result['price_history'].get(key, [])
            print(f"  price_history[{key}]: {len(ph)}건")
            if ph:
                print(f"    최초: {ph[0]}")
                print(f"    최신: {ph[-1]}")

        if not args.dry:
            saved = sb_upsert("danji_pages", [result])
            print(f"\n✅ danji_pages 저장 완료 ({saved}개)")
        else:
            print("\n[DRY] 저장 생략")
        return

    if args.sigungu:
        codes = [c.strip() for c in args.sigungu.split(",")]
        for code in codes:
            targets.append((code, ALL_REGIONS.get(code, code)))
    elif args.region == "all":
        targets.extend(ALL_REGIONS.items())
    else:
        targets.extend(REGION_MAP[args.region].items())

    print(f"대상: {len(targets)}개 구/시  dry={args.dry}")
    if args.dry:
        print("⚠️  DRY 모드 — danji_pages 저장 없음\n")

    t_total = t_ok = t_skip = 0
    start = time.time()

    for lawd_cd, name in targets:
        total, ok, skip = process_lawd(lawd_cd, name, args.dry)
        t_total += total; t_ok += ok; t_skip += skip

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"완료: {t_total}개 처리 / {t_ok}개 저장 / {t_skip}개 건너뜀 ({elapsed:.0f}초)")


if __name__ == "__main__":
    main()
