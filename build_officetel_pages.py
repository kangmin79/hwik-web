#!/usr/bin/env python3
"""
build_officetel_pages.py — 오피스텔 단지 SEO 페이지 (B안 축소 복원)

2026-04-22 롤백된 12,681개 페이지의 구조 복원 (pyeongs 없이).
공통 CSS: /officetel/style.css — D 디자인 단일 베이스 (아파트와 분리, 2026-04-26).
Chart.js: 거래량 바 + 실거래 scatter.
JSON-LD 3종: ApartmentComplex + BreadcrumbList + FAQPage.

환경변수:
  ONE_OFFI_ID=o3628910   # 단일 단지 프리뷰
"""
from __future__ import annotations

import html as html_mod
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote as url_quote

# 아파트 slug_utils 재사용 — dong/gu URL 패턴 일치
sys.path.insert(0, str(Path(__file__).resolve().parent))
from slug_utils import make_dong_slug, gu_url_slug  # noqa: E402
# D 디자인 (PC ≥768px) — preview_desktop_designs.py 와 단일 소스 공유
from officetel_design_d import DESIGN_D_BLOCK  # noqa: E402


# ── ENV ──────────────────────────────────────────────────────────────────────
def _load_env() -> None:
    here = Path(__file__).resolve().parent
    for name in (".env", "env"):
        p = here / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://jqaxejgzkchxbfzgzyzi.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

BASE_DIR = Path(__file__).resolve().parent
OFFI_DIR = BASE_DIR / "officetel"
KST = timezone(timedelta(hours=9))
BUILD_TIME_KST = datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")
BUILD_DATE_KST = datetime.now(KST).strftime("%Y-%m-%d")


def josa(word: str, pair: str = "은는") -> str:
    """한글 받침 여부로 조사 선택. pair='은는'|'이가'|'을를'|'과와' 등."""
    if not word:
        return pair[0]
    last = word[-1]
    if "가" <= last <= "힣":
        code = ord(last) - 0xAC00
        has_final = (code % 28) != 0
        return pair[0] if has_final else pair[1]
    return pair[0]
SB_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
NEARBY_RADIUS_KM = 10.0


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _get(path: str, params: dict | None = None, attempts: int = 3) -> list[dict]:
    from urllib.parse import urlencode
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    if params:
        url += "?" + urlencode(params, doseq=True)
    last: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=SB_HEADERS)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            last = e
            time.sleep(0.5 * (i + 1))
    raise last or RuntimeError("unreachable")


# ── 포맷 유틸 ────────────────────────────────────────────────────────────────
def esc(s) -> str:
    if s is None:
        return ""
    return html_mod.escape(str(s), quote=True)


def fmt_price(manwon: int | None) -> str:
    if not manwon or manwon <= 0:
        return "-"
    eok = manwon // 10000
    rest = manwon % 10000
    if eok and rest:
        return f"{eok}억 {rest:,}만"
    if eok:
        return f"{eok}억"
    return f"{manwon:,}만"


def fmt_deal_date_ymd(y: int, m: int, d: int) -> str:
    try:
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except Exception:
        return ""


def fmt_walk_min(dist_m: int | float | None) -> str:
    if dist_m is None:
        return ""
    try:
        minutes = max(1, int(round(float(dist_m) / 80)))  # 80m/분
        return f"{minutes}분"
    except Exception:
        return ""


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ── 데이터 로드 ──────────────────────────────────────────────────────────────
OFFI_COLS = (
    "id,mgm_bldrgst_pk,sido,sgg,umd,jibun,bjdong_cd,final_display_name,"
    "bld_nm,jibun_addr,jibun_lat,jibun_lng,road_addr,road_lat,road_lng,"
    "main_purps,build_year,use_apr_day,tot_area,grnd_flr,ugrnd_flr,"
    "hhld_cnt,ho_cnt,trade_count,excl_area_min,excl_area_max,url,slug,"
    "parking_total,parking_self,parking_mech,elevator_ride,strct_name,"
    "bc_ratio,vl_ratio,earthquake_rating,nearby_subway,nearby_school"
)


def fetch_all_officetels() -> list[dict]:
    out: list[dict] = []
    offset = 0
    page = 1000
    while True:
        rows = _get("officetels", {
            "select": OFFI_COLS, "order": "id", "offset": offset, "limit": page,
        })
        if not rows:
            break
        out.extend(rows)
        offset += page
        if len(rows) < page:
            break
    return out


def fetch_all_apartments() -> list[dict]:
    """아파트 단지 마스터 (주변 아파트 섹션용) — slug 있는 것만."""
    out: list[dict] = []
    offset = 0
    page = 1000
    cols = "id,kapt_code,kapt_name,sido,sgg,umd_nm,slug,doro_lat,doro_lon,jibun_lat,jibun_lon"
    while True:
        rows = _get("apartments", {
            "select": cols, "order": "id", "offset": offset, "limit": page,
            "slug": "not.is.null",
        })
        if not rows:
            break
        out.extend(rows)
        offset += page
        if len(rows) < page:
            break
    return out


def fetch_apartment_recent_trades() -> dict[str, dict]:
    """danji_pages.recent_trade 로드 → {danji_id: {price, date, type, excl_area}}."""
    out: dict[str, dict] = {}
    offset = 0
    page = 1000
    while True:
        rows = _get("danji_pages", {
            "select": "id,recent_trade", "order": "id", "offset": offset, "limit": page,
        })
        if not rows:
            break
        for r in rows:
            rt = r.get("recent_trade") or {}
            if not isinstance(rt, dict) or not rt:
                continue
            best = None
            for py_key, info in rt.items():
                if not isinstance(info, dict) or not info.get("price") or not info.get("date"):
                    continue
                py_str = str(py_key)
                # 아파트 wolse 는 price 단위 불명확 → 안전상 제외 (매매·전세만)
                if "_wolse" in py_str:
                    continue
                is_jeon = "_jeonse" in py_str
                tup = (info["date"], 0 if is_jeon else 1, py_key, info)
                if best is None or tup > best:
                    best = tup
            if best:
                _, is_sale, py_key, info = best
                try:
                    area = int(str(py_key).split("_")[0])
                except Exception:
                    area = None
                out[r["id"]] = {
                    "price": info["price"],
                    "date": info["date"],
                    "type": "매매" if is_sale else "전세",
                    "excl_area": area,
                }
        offset += page
        if len(rows) < page:
            break
    return out


def fetch_all_trades(oids: list[str] | None = None) -> dict[str, list[dict]]:
    """단지별 fetch_one_trades 를 병렬 실행 — 큰 offset 회피 (500 에러 방지).

    9,833 단지 × 단지당 평균 130건 → 단지당 1~2 요청. workers=10 (서버 보호).
    예상 2~4분.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if oids is None:
        raise ValueError("oids 필요 (단지 id 리스트)")
    g: dict[str, list[dict]] = {}
    total = 0
    done = 0

    def _one(oid: str) -> tuple[str, list[dict]]:
        try:
            return oid, fetch_one_trades(oid)
        except Exception as e:
            print(f"    {oid} 에러: {e}")
            return oid, []

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(_one, oid) for oid in oids]
        for fut in as_completed(futs):
            oid, rows = fut.result()
            rows = [t for t in rows if not t.get("is_canceled")]
            g[oid] = rows
            total += len(rows)
            done += 1
            if done % 500 == 0:
                print(f"    {done:,}/{len(oids):,} 단지 완료, rows {total:,}")
    print(f"  trades: {total:,} rows → {len(g):,} officetels")
    return g


def fetch_one_trades(oid: str) -> list[dict]:
    out: list[dict] = []
    offset = 0
    page = 1000
    while True:
        rows = _get("officetel_trades", {
            "select": ("officetel_id,deal_type,deal_year,deal_month,deal_day,"
                       "price,monthly_rent,excl_use_ar,floor,is_canceled,dealing_gbn"),
            "officetel_id": f"eq.{oid}",
            "order": "deal_year.desc,deal_month.desc,deal_day.desc",
            "offset": offset, "limit": page,
        })
        if not rows:
            break
        for t in rows:
            if not t.get("is_canceled"):
                out.append(t)
        offset += page
        if len(rows) < page:
            break
    return out


# ── 집계 ─────────────────────────────────────────────────────────────────────
def _addr_full(o: dict) -> str:
    """지번 주소 우선 (road_addr에 건물명이 잘못 저장된 케이스 방어)."""
    jibun = (o.get("jibun_addr") or "").strip()
    road = (o.get("road_addr") or "").strip()
    bld = (o.get("bld_nm") or "").strip()
    # 도로명 주소는 보통 공백을 포함 ("송파대로 111"). 공백 없거나 건물명과 겹치면 무효
    if road:
        no_space = " " not in road
        overlap = bld and (road == bld or road in bld or bld in road)
        if no_space or overlap:
            road = ""
    return road or jibun or f"{o.get('sido','')} {o.get('sgg','')} {o.get('umd','')}".strip()


def extract_areas(trades: list[dict], top_n: int = 6) -> list[tuple[int, int]]:
    """trades 에서 정수 ㎡ 기준 그룹 → 거래수 desc top_n. 반환: [(area_int, count), ...] 오름차순."""
    from collections import Counter
    c: Counter[int] = Counter()
    for t in trades:
        a = t.get("excl_use_ar")
        if a is None:
            continue
        try:
            ai = int(round(float(a)))
        except Exception:
            continue
        if ai <= 0:
            continue
        c[ai] += 1
    top = c.most_common(top_n)
    top.sort(key=lambda x: x[0])  # 면적 오름차순 표시
    return top


def filter_trades_by_area(trades: list[dict], area_int: int, tol: int = 1) -> list[dict]:
    """±tol ㎡ 범위의 거래만 반환."""
    out = []
    for t in trades:
        a = t.get("excl_use_ar")
        if a is None:
            continue
        try:
            ai = int(round(float(a)))
        except Exception:
            continue
        if abs(ai - area_int) <= tol:
            out.append(t)
    return out


def summarize(trades: list[dict]) -> dict:
    today = _date.today()
    y5 = today.year - 5
    y1 = today.year - 1  # 1년 평균 기준 (오늘 기준 12개월)
    m1 = today.month
    매매 = sorted([t for t in trades if t.get("deal_type") == "매매"],
                 key=lambda t: (t["deal_year"], t["deal_month"], t["deal_day"]), reverse=True)
    전세 = sorted([t for t in trades if t.get("deal_type") == "전세"],
                 key=lambda t: (t["deal_year"], t["deal_month"], t["deal_day"]), reverse=True)
    월세 = sorted([t for t in trades if t.get("deal_type") == "월세"],
                 key=lambda t: (t["deal_year"], t["deal_month"], t["deal_day"]), reverse=True)

    sale_5y = [t for t in 매매 if t["deal_year"] >= y5]
    jeon_5y = [t for t in 전세 if t["deal_year"] >= y5]
    wol_5y = [t for t in 월세 if t["deal_year"] >= y5]

    # 최근 1년 (오늘 기준 12개월 이내)
    def _within_1y(t: dict) -> bool:
        ty, tm = t.get("deal_year") or 0, t.get("deal_month") or 0
        return (ty > y1) or (ty == y1 and tm >= m1)
    sale_1y = [t for t in 매매 if _within_1y(t)]
    jeon_1y = [t for t in 전세 if _within_1y(t)]
    wol_1y = [t for t in 월세 if _within_1y(t)]

    recent_sale = 매매[0] if 매매 else None
    recent_jeon = 전세[0] if 전세 else None
    recent_wol = 월세[0] if 월세 else None

    top_sale = None
    if sale_5y:
        top_sale = max(sale_5y, key=lambda t: t.get("price") or 0)

    top_jeon = None
    if jeon_5y:
        top_jeon = max(jeon_5y, key=lambda t: t.get("price") or 0)

    # 5년 가격변동률 (매매): 첫해 평균 vs 최근 평균
    cagr = None
    if len(sale_5y) >= 4:
        yrs = defaultdict(list)
        for t in sale_5y:
            if t.get("price"):
                yrs[t["deal_year"]].append(t["price"])
        sorted_years = sorted(yrs.keys())
        if len(sorted_years) >= 2:
            old_y = sorted_years[0]
            new_y = sorted_years[-1]
            old_avg = sum(yrs[old_y]) / len(yrs[old_y])
            new_avg = sum(yrs[new_y]) / len(yrs[new_y])
            span = new_y - old_y
            if old_avg > 0 and span > 0:
                cagr = (pow(new_avg / old_avg, 1 / span) - 1) * 100

    avg_sale = None
    if sale_5y:
        ps = [t["price"] for t in sale_5y if t.get("price")]
        if ps:
            avg_sale = int(round(sum(ps) / len(ps)))

    avg_jeon = None
    if jeon_5y:
        ps = [t["price"] for t in jeon_5y if t.get("price")]
        if ps:
            avg_jeon = int(round(sum(ps) / len(ps)))

    avg_wol_dep = None
    avg_wol_rent = None
    if wol_5y:
        ds = [t["price"] for t in wol_5y if t.get("price")]
        rs = [t["monthly_rent"] for t in wol_5y if t.get("monthly_rent")]
        if ds:
            avg_wol_dep = int(round(sum(ds) / len(ds)))
        if rs:
            avg_wol_rent = int(round(sum(rs) / len(rs)))

    # 1년 평균 (slot 폴백 1순위)
    def _avg(items: list[dict], key: str) -> int | None:
        vs = [t[key] for t in items if t.get(key)]
        return int(round(sum(vs) / len(vs))) if vs else None
    avg_jeon_1y = _avg(jeon_1y, "price")
    avg_sale_1y = _avg(sale_1y, "price")
    avg_wol_dep_1y = _avg(wol_1y, "price")
    avg_wol_rent_1y = _avg(wol_1y, "monthly_rent")

    # 전세가율: 5년 평균 전세 ÷ 5년 평균 매매 × 100 (1건씩 비교는 시점 차/표본 작아 부정확)
    jr = None
    if avg_sale and avg_jeon and avg_sale > 0:
        jr = round(avg_jeon / avg_sale * 100, 1)

    # 거래량 by year (매매/전세/월세)
    vol = {"매매": defaultdict(int), "전세": defaultdict(int), "월세": defaultdict(int)}
    for t in trades:
        if t["deal_year"] >= y5:
            vol[t["deal_type"]][t["deal_year"]] += 1

    return {
        "total": len(trades),
        "sale": len(매매), "jeonse": len(전세), "wolse": len(월세),
        "sale_5y": len(sale_5y), "jeon_5y": len(jeon_5y), "wol_5y": len(wol_5y),
        "sale_1y": len(sale_1y), "jeon_1y": len(jeon_1y), "wol_1y": len(wol_1y),
        "recent_sale": recent_sale, "recent_jeon": recent_jeon, "recent_wol": recent_wol,
        "top_sale": top_sale, "top_jeon": top_jeon,
        "cagr5": cagr,
        "avg_sale": avg_sale, "avg_jeon": avg_jeon, "avg_wol_dep": avg_wol_dep, "avg_wol_rent": avg_wol_rent,
        "avg_sale_1y": avg_sale_1y, "avg_jeon_1y": avg_jeon_1y,
        "avg_wol_dep_1y": avg_wol_dep_1y, "avg_wol_rent_1y": avg_wol_rent_1y,
        "jeonse_rate": jr,
        "trades_sale": 매매, "trades_jeon": 전세, "trades_wol": 월세,
        "vol_by_year": vol,
    }


def nearby_apartments(o: dict, all_apts: list[dict], apt_recent: dict[str, dict],
                      radius_km: float = NEARBY_RADIUS_KM, top_n: int = 5) -> list[dict]:
    """주변 아파트 단지 (슬러그 존재 + recent_trade 존재 + 반경 내)."""
    lat = o.get("road_lat") or o.get("jibun_lat")
    lng = o.get("road_lng") or o.get("jibun_lng")
    if lat is None or lng is None:
        return []
    cand = []
    for a in all_apts:
        if not a.get("slug"):
            continue
        alat = a.get("doro_lat") or a.get("jibun_lat")
        alng = a.get("doro_lon") or a.get("jibun_lon")
        if alat is None or alng is None:
            continue
        d = haversine_km(lat, lng, alat, alng)
        if d > radius_km:
            continue
        rt = apt_recent.get(a["id"])
        if not rt:
            continue
        same_umd = 1 if a.get("umd_nm") == o.get("umd") else 0
        cand.append((d, same_umd, a, rt))
    cand.sort(key=lambda c: (-c[1], c[0]))
    out = []
    for d, _, a, rt in cand[:top_n]:
        out.append({
            "id": a["id"], "slug": a["slug"],
            "name": a.get("kapt_name") or "",
            "sgg": a.get("sgg") or "", "umd": a.get("umd_nm") or "",
            "distance_km": round(d, 2),
            "distance_m": int(round(d * 1000)),
            "excl_use_ar": rt.get("excl_area"),
            "recent_price": rt["price"],
            "recent_date": rt["date"],
            "recent_type": rt["type"],
        })
    return out


def nearby_officetels(o: dict, all_offi: list[dict], trades_map: dict,
                      radius_km: float = NEARBY_RADIUS_KM, top_n: int = 10) -> list[dict]:
    lat = o.get("road_lat") or o.get("jibun_lat")
    lng = o.get("road_lng") or o.get("jibun_lng")
    if lat is None or lng is None:
        return []
    cand = []
    for x in all_offi:
        if x["id"] == o["id"]:
            continue
        xlat = x.get("road_lat") or x.get("jibun_lat")
        xlng = x.get("road_lng") or x.get("jibun_lng")
        if xlat is None or xlng is None:
            continue
        d = haversine_km(lat, lng, xlat, xlng)
        if d > radius_km:
            continue
        # 같은 umd 우선 가중 (near 리스트)
        same_umd = 1 if x.get("umd") == o.get("umd") else 0
        cand.append((d, same_umd, x))
    cand.sort(key=lambda c: (-c[1], c[0]))  # 같은 동 먼저, 그 안에서 가까운 순

    out = []
    for d, _, x in cand[:top_n * 3]:  # 여유 있게 필터 후 top_n
        xt = trades_map.get(x["id"], [])
        if not xt:
            continue
        # 가장 최근 거래 (유형 무관) — 오피스텔은 월세 비중이 높음
        recent = None
        best_key = None
        for t in xt:
            if not t.get("price"):
                continue
            k = (t.get("deal_year") or 0, t.get("deal_month") or 0, t.get("deal_day") or 0)
            if best_key is None or k > best_key:
                best_key = k
                recent = t
        if not recent:
            continue
        out.append({
            "id": x["id"], "slug": x.get("slug"),
            "name": x.get("bld_nm") or "",
            "sgg": x.get("sgg") or "", "umd": x.get("umd") or "",
            "distance_km": round(d, 2),
            "distance_m": int(round(d * 1000)),
            "excl_use_ar": recent.get("excl_use_ar"),
            "recent_price": recent["price"],
            "recent_monthly_rent": recent.get("monthly_rent"),
            "recent_date": fmt_deal_date_ymd(
                recent["deal_year"], recent["deal_month"], recent["deal_day"]),
            "recent_type": recent.get("deal_type"),
        })
        if len(out) >= top_n:
            break
    return out


# ── HTML 렌더 ────────────────────────────────────────────────────────────────
SUBWAY_LINE_COLORS = {
    "1호선": "#0052A4", "2호선": "#00A84D", "3호선": "#EF7C1C", "4호선": "#00A5DE",
    "5호선": "#996CAC", "6호선": "#CD7C2F", "7호선": "#747F00", "8호선": "#E6186C",
    "9호선": "#BDB092",
    "경의중앙선": "#72C7A6", "수인분당선": "#E0A134", "분당선": "#E0A134",
    "신분당선": "#D4003B",
    "공항철도": "#0090D2", "GTX-A": "#8B2F8B", "우이신설선": "#B0CE18",
    "신림선": "#6789CA", "경춘선": "#0C8E72", "김포골드라인": "#A17800",
    "인천1호선": "#7CA8D5", "인천2호선": "#ED8000",
}


def _merge_subway_transfers(subway: list[dict]) -> list[dict]:
    """환승역 병합: 같은 역명에 여러 노선이 들어오면 한 항목으로 합침.
    - key: name 끝 '역' 제거 후 비교 → "선릉" / "선릉역" 동일 처리
    - output name: 항상 '~역' 형태로 통일
    - line: 노선들을 '·' 로 결합 (입력 순서 보존)
    - distance: 최소값
    - 정렬: distance 가까운 순
    """
    if not subway:
        return []
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for s in subway:
        nm = (s.get("name") or "").strip()
        if not nm:
            continue
        key = nm[:-1] if nm.endswith("역") else nm
        if key not in by_key:
            by_key[key] = {"name": key + "역", "lines": [], "distance": s.get("distance")}
            order.append(key)
        cur = by_key[key]
        ln = (s.get("line") or "").strip()
        if ln and ln not in cur["lines"]:
            cur["lines"].append(ln)
        d = s.get("distance")
        if d is not None and (cur["distance"] is None or d < cur["distance"]):
            cur["distance"] = d
    out = []
    for k in order:
        item = by_key[k]
        out.append({
            "name": item["name"],
            "line": "·".join(item["lines"]),
            "lines": item["lines"],
            "distance": item["distance"],
        })
    out.sort(key=lambda x: x.get("distance") if x.get("distance") is not None else 99999)
    return out


def _render_subway_tags(subway: list[dict]) -> str:
    if not subway:
        return ""
    items = []
    for s in subway[:3]:
        line = esc(s.get("line") or "")
        name = esc(s.get("name") or "")
        dist = fmt_walk_min(s.get("distance"))
        items.append(
            f'<span class="station-tag" style="margin-right:8px;">'
            f'<span class="line-badge" style="background:#3b82f6;">{line}</span>'
            f'<span class="station-name">{name}</span> '
            f'<span class="station-time">{dist}</span></span>'
        )
    sep = '<span class="tag-sep">·</span>'
    return '<div class="tag-line" style="gap:4px;">' + sep.join(items) + '</div>'


def _render_school_tags(schools: list[dict]) -> str:
    if not schools:
        return ""
    TYPE_SHORT = {"초등학교": "초", "중학교": "중", "고등학교": "고"}
    # 학교급 순(초→중→고) 정렬, 동급 내에서는 거리(가까운 순) 유지
    TYPE_ORDER = {"초등학교": 0, "중학교": 1, "고등학교": 2}
    schools = sorted(schools, key=lambda s: TYPE_ORDER.get(s.get("type") or "", 9))
    items = []
    for s in schools[:3]:
        name = esc(s.get("name") or "")
        typ = s.get("type") or ""
        short = TYPE_SHORT.get(typ, typ[:1] if typ else "")
        dist = fmt_walk_min(s.get("distance"))
        items.append(
            f'<span class="school-tag" style="display:inline-flex;align-items:center;gap:4px;color:rgba(255,255,255,0.85);margin-right:8px;">'
            f'<span class="school-type" style="display:inline-block;padding:0 5px;border-radius:8px;'
            f'font-size:9px;font-weight:600;background:rgba(163,212,104,0.3);color:#d7ebbb;">{esc(short)}</span>'
            f'<span style="color:rgba(255,255,255,0.85);">{name}</span>'
            f'<span style="color:rgba(255,255,255,0.5);font-size:11px;">{dist}</span>'
            f'</span>'
        )
    sep = '<span class="tag-sep">·</span>'
    return '<div class="tag-line" style="margin-top:4px;gap:4px;">' + sep.join(items) + '</div>'


def _trade_badge(t: dict) -> str:
    gb = t.get("dealing_gbn") or ""
    if gb == "직거래":
        return '<span class="badge-direct">직거래</span>'
    if gb == "중개거래":
        return '<span class="badge-trade">중개</span>'
    return ""


def _type_pill(deal_type: str) -> str:
    # 가독성 ↑: medium tint bg + 진한 텍스트 (모바일 가독성 보강)
    palette = {
        "매매": ("#fdba74", "#7c2d12"),
        "전세": ("#93c5fd", "#1e3a8a"),
        "월세": ("#6ee7b7", "#064e3b"),
    }
    bg, fg = palette.get(deal_type, ("#cbd5e1", "#334155"))
    return (f'<span style="display:inline-block;padding:2px 7px;border-radius:4px;'
            f'background:{bg};color:{fg};font-size:10.5px;font-weight:700;'
            f'letter-spacing:0.2px;line-height:1.4;margin-right:8px;vertical-align:middle;">'
            f'{esc(deal_type or "")}</span>')


def _fallback_trades(area_stats_map: dict[int, dict], ai: int, kind: str,
                     limit: int = 5) -> list[tuple[dict, str | None]]:
    """현재 평형+유형 → 부족하면 (가까운 평형 같은유형) → (같은 평형 다른 유형) → (다른 평형 다른 유형) 순으로 채움.

    반환: [(trade, flag)] — flag: None | 'area' | 'kind' | 'both'
    """
    KEY_OF = {"매매": "trades_sale", "전세": "trades_jeon", "월세": "trades_wol"}
    KINDS = ("매매", "전세", "월세")
    if ai not in area_stats_map:
        return []
    items: list[tuple[dict, str | None]] = []
    # Tier 1: 해당 평형 + 해당 유형
    for t in area_stats_map[ai][KEY_OF[kind]][:limit]:
        items.append((t, None))
    if len(items) >= limit:
        return items[:limit]
    other_areas = sorted(
        [a for a in area_stats_map if a != ai],
        key=lambda a: abs(a - ai)
    )
    # Tier 2: 다른 평형 (가까운 순) + 같은 유형
    for other_ai in other_areas:
        for t in area_stats_map[other_ai][KEY_OF[kind]]:
            if len(items) >= limit:
                return items[:limit]
            items.append((t, "area"))
    # Tier 3: 해당 평형 + 다른 유형
    for other_k in [k for k in KINDS if k != kind]:
        for t in area_stats_map[ai][KEY_OF[other_k]]:
            if len(items) >= limit:
                return items[:limit]
            items.append((t, "kind"))
    # Tier 4: 다른 평형 + 다른 유형
    for other_ai in other_areas:
        for other_k in [k for k in KINDS if k != kind]:
            for t in area_stats_map[other_ai][KEY_OF[other_k]]:
                if len(items) >= limit:
                    return items[:limit]
                items.append((t, "both"))
    return items[:limit]


def _fallback_badge(flag: str | None) -> str:
    # 유사 평형(area flag)은 detail 에 전용면적 표시되므로 생략
    if flag == "kind":
        return ('<span style="display:inline-block;padding:1px 6px;margin-left:6px;border-radius:4px;'
                'background:#f3e8ff;color:#6b21a8;font-size:10px;font-weight:600;vertical-align:middle;">'
                '다른 유형</span>')
    if flag == "both":
        return ('<span style="display:inline-block;padding:1px 6px;margin-left:6px;border-radius:4px;'
                'background:#f1f5f9;color:#475569;font-size:10px;font-weight:600;vertical-align:middle;">'
                '참고</span>')
    return ""


def _render_trade_items_fb(items_flag: list[tuple[dict, str | None]],
                           area_stats_map: dict[int, dict] | None = None,
                           limit: int = 5) -> str:
    if not items_flag:
        return '<p style="color:var(--sub);font-size:12px;">거래 내역이 없습니다.</p>'
    out = []
    for t, flag in items_flag[:limit]:
        dt = fmt_deal_date_ymd(t["deal_year"], t["deal_month"], t["deal_day"])
        price = fmt_price(t.get("price"))
        deal_type = t.get("deal_type") or ""
        if deal_type == "월세" and t.get("monthly_rent"):
            price = f"{price} / 월 {int(t['monthly_rent']):,}만"
        type_pill = _type_pill(deal_type)
        detail_parts = []
        if t.get("excl_use_ar"):
            detail_parts.append(f"전용 {float(t['excl_use_ar']):.2f}㎡")
        if t.get("floor") is not None:
            detail_parts.append(f"{t['floor']}층")
        detail = " · ".join(detail_parts)
        badge = _trade_badge(t)
        fb = _fallback_badge(flag)
        out.append(
            f'<tr class="trade-item">'
            f'<td class="trade-info"><div class="trade-price">{type_pill}{price}{badge}{fb}</div>'
            f'<div class="trade-detail">{detail}</div></td>'
            f'<td class="trade-date">{dt}</td></tr>'
        )
    return "".join(out)


def _render_trade_items(trades: list[dict], limit: int = 5) -> str:
    if not trades:
        return '<p style="color:var(--sub);font-size:12px;">거래 내역이 없습니다.</p>'
    out = []
    for t in trades[:limit]:
        dt = fmt_deal_date_ymd(t["deal_year"], t["deal_month"], t["deal_day"])
        price = fmt_price(t.get("price"))
        deal_type = t.get("deal_type") or ""
        if deal_type == "월세" and t.get("monthly_rent"):
            price = f"{price} / 월 {int(t['monthly_rent']):,}만"
        type_pill = _type_pill(deal_type)
        detail_parts = []
        if t.get("excl_use_ar"):
            detail_parts.append(f"전용 {float(t['excl_use_ar']):.2f}㎡")
        if t.get("floor") is not None:
            detail_parts.append(f"{t['floor']}층")
        detail = " · ".join(detail_parts)
        badge = _trade_badge(t)
        out.append(
            f'<tr class="trade-item">'
            f'<td class="trade-info"><div class="trade-price">{type_pill}{price}{badge}</div>'
            f'<div class="trade-detail">{detail}</div></td>'
            f'<td class="trade-date">{dt}</td></tr>'
        )
    return "".join(out)


def _render_nearby_items(items_data: list[dict], kind: str) -> str:
    """kind: 'officetel' | 'apartment'."""
    if kind == "apartment":
        href_prefix = "/danji/"
        tag_bg, tag_fg, tag_label = "#ecfeff", "#0e7490", "아파트"
    else:
        href_prefix = "/officetel/"
        tag_bg, tag_fg, tag_label = "#eef2ff", "#4338ca", "오피스텔"
    PRICE_COLORS = {"매매": "#ea580c", "전세": "#2563eb", "월세": "#059669"}
    items = []
    for n in items_data:
        href = f"{href_prefix}{n['slug']}.html"
        area = f" · 전용 {float(n['excl_use_ar']):.0f}㎡" if n.get("excl_use_ar") else ""
        dm = n.get("distance_m") or 0
        dist_txt = f"{dm}m" if dm < 1000 else f"{n['distance_km']}km"
        price_color = PRICE_COLORS.get(n.get("recent_type") or "", "inherit")
        price_str = fmt_price(n["recent_price"])
        if n.get("recent_type") == "월세" and n.get("recent_monthly_rent"):
            price_str = f"{price_str} / 월 {int(n['recent_monthly_rent']):,}만"
        items.append(
            f'<a class="nearby-item" href="{esc(href)}" style="text-decoration:none;color:inherit;">'
            f'<div>'
            f'<div class="nearby-name" style="font-weight:600;">'
            f'<span style="display:inline-block;padding:1px 6px;margin-right:6px;border-radius:4px;'
            f'background:{tag_bg};color:{tag_fg};font-size:10px;font-weight:600;vertical-align:middle;">{tag_label}</span>'
            f'{esc(n["name"])}</div>'
            f'<div class="nearby-sub">{esc(n.get("sgg",""))} {esc(n.get("umd",""))} · {dist_txt}{area}</div>'
            f'</div>'
            f'<div style="text-align:right;">'
            f'<div class="nearby-price" style="color:{price_color};">{price_str}</div>'
            f'<div style="font-size:11px;color:var(--sub);margin-top:2px;">'
            f'{_type_pill(n["recent_type"] or "")}{n["recent_date"]}</div>'
            f'</div>'
            f'</a>'
        )
    return '<div style="display:flex;flex-direction:column;gap:8px;">' + "".join(items) + '</div>'


def _render_nearby(near_offi: list[dict], near_apt: list[dict] | None = None) -> str:
    near_offi = [n for n in (near_offi or []) if n.get("slug")]
    near_apt = [n for n in (near_apt or []) if n.get("slug")]
    if not near_offi and not near_apt:
        return '<p style="color:var(--sub);font-size:12px;">주변 단지 데이터가 없습니다.</p>'
    parts = []
    if near_offi:
        parts.append(_render_nearby_items(near_offi, "officetel"))
    if near_apt:
        parts.append(
            '<div style="margin-top:16px;font-size:13px;font-weight:600;color:var(--dark);'
            'padding:0 2px;">주변 아파트</div>'
        )
        parts.append(_render_nearby_items(near_apt, "apartment"))
    return "".join(parts)


def _build_faq(o: dict, stats: dict) -> list[tuple[str, str]]:
    name = o.get("bld_nm") or ""
    qas = []

    # 1. 준공/호수
    yr = o.get("build_year")
    ho = o.get("ho_cnt") or o.get("hhld_cnt")
    if yr and ho:
        j = josa(name, "은는")
        qas.append((f"{name}{j} 몇 년 준공, 몇 호?",
                    f"{name}{j} {yr}년 준공 오피스텔로, 총 {int(ho):,}호실 규모입니다."))

    # 2. 최근 실거래가
    rs = stats.get("recent_sale")
    if rs and rs.get("price"):
        dt = fmt_deal_date_ymd(rs["deal_year"], rs["deal_month"], rs["deal_day"])
        qas.append((f"{name} 최근 실거래가는?",
                    f"최근 매매 실거래가는 {fmt_price(rs['price'])}입니다. ({dt} 기준)"))

    # 3. 5년 최고가
    ts = stats.get("top_sale")
    if ts and ts.get("price"):
        dt = fmt_deal_date_ymd(ts["deal_year"], ts["deal_month"], ts["deal_day"])
        qas.append((f"{name} 최근 5년 최고가는?",
                    f"최근 5년 매매 최고가는 {fmt_price(ts['price'])}입니다. ({dt})"))

    # 4. 매매 거래량
    if stats["sale_5y"]:
        qas.append((f"{name} 매매 거래는 얼마나 활발?",
                    f"최근 5년 매매 {stats['sale_5y']:,}건이 집계되었습니다."))

    # 5. 전세 시세
    if stats["jeon_5y"] and stats.get("avg_jeon"):
        qas.append((f"{name} 전세 시세는?",
                    f"최근 5년 전세 실거래 {stats['jeon_5y']:,}건 "
                    f"평균 보증금은 {fmt_price(stats['avg_jeon'])}입니다."))

    # 6. 월세
    if stats["wol_5y"] and stats.get("avg_wol_dep") and stats.get("avg_wol_rent"):
        qas.append((f"{name} 월세 평균은?",
                    f"최근 5년 월세 실거래 {stats['wol_5y']:,}건 평균은 "
                    f"보증금 {fmt_price(stats['avg_wol_dep'])} / 월세 {stats['avg_wol_rent']:,}만입니다."))

    # 7. 전용면적
    if o.get("excl_area_min") is not None and o.get("excl_area_max") is not None:
        lo = float(o["excl_area_min"])
        hi = float(o["excl_area_max"])
        qas.append((f"{name} 전용면적은?",
                    f"{name}의 전용면적은 {lo:.0f}㎡ ~ {hi:.0f}㎡ 범위입니다."))

    # 8. 주차
    pt = o.get("parking_total")
    if pt:
        parts = [f"총 {int(pt):,}대"]
        details = []
        if o.get("parking_self"):
            details.append(f"자주식 {int(o['parking_self']):,}대")
        if o.get("parking_mech"):
            details.append(f"기계식 {int(o['parking_mech']):,}대")
        if details:
            parts.append(f"({', '.join(details)})")
        qas.append((f"{name} 주차 가능 대수는?", f"{' '.join(parts)} 주차가 가능합니다."))

    # 9. 층수
    gf = o.get("grnd_flr")
    uf = o.get("ugrnd_flr")
    if gf:
        msg = f"지상 {int(gf)}층 규모입니다."
        if uf:
            msg += f" 지하 {int(uf)}층."
        qas.append((f"{name} 최고층은?", msg))

    # 10. 지하철
    sub = o.get("nearby_subway") or []
    if sub:
        inner = ", ".join(f"{s.get('line','')} {s.get('name','')}(도보 {fmt_walk_min(s.get('distance'))})"
                          for s in sub[:3])
        qas.append((f"{name} 주변 지하철은?", f"도보권에 {inner}이(가) 있습니다."))

    # 11. 학교
    sch = o.get("nearby_school") or []
    if sch:
        inner = ", ".join(f"{s.get('name','')}(도보 {fmt_walk_min(s.get('distance'))})"
                          for s in sch[:3])
        qas.append((f"{name} 주변 학교는?", f"도보권 학교: {inner}."))

    # 12. 건폐/용적
    if o.get("bc_ratio") is not None and o.get("vl_ratio") is not None:
        qas.append((f"{name} 건폐율·용적률은?",
                    f"건축물대장 기준 건폐율 {o['bc_ratio']}%, 용적률 {o['vl_ratio']}%입니다."))

    # 13. 내진
    if o.get("earthquake_rating"):
        qas.append((f"{name} 내진설계 등급은?",
                    f"내진설계 등급은 {o['earthquake_rating']}입니다 (최대지반가속도 기준)."))

    # 14. 구조
    if o.get("strct_name"):
        qas.append((f"{name} 건물 구조는?", f"{o['strct_name']}입니다."))

    # ── 롱테일 FAQ (검색량 작지만 정확도 ↑ 키워드) ──────────
    # 15. 역명 + 도보거리 (구체적 호선·역 조합)
    sub_for_lt = (o.get("nearby_subway") or [])[:3]
    for s in sub_for_lt[:2]:  # 가장 가까운 2개 역만 별도 FAQ
        nm = s.get("name") or ""
        ln = s.get("line") or ""
        mm = max(1, int(round(float(s.get("distance") or 0) / 80))) if s.get("distance") else None
        if nm and ln and mm:
            qas.append((f"{nm} 도보 거리에 있는 오피스텔?",
                        f"{name}{josa(name,'은는')} {ln} {nm} 도보 {mm}분 거리에 위치한 오피스텔입니다."))

    # 16. 신축 여부 (준공 5년 이내)
    if o.get("build_year"):
        try:
            yrs_old = _date.today().year - int(o["build_year"])
            if yrs_old <= 5:
                qas.append((f"{name} 신축 오피스텔인가요?",
                            f"{name}{josa(name,'은는')} {o['build_year']}년 준공으로 {yrs_old}년차 신축 오피스텔입니다."))
            elif yrs_old >= 20:
                qas.append((f"{name} 준공한 지 얼마나 되었나요?",
                            f"{name}{josa(name,'은는')} {o['build_year']}년 준공된 {yrs_old}년차 오피스텔입니다. 리모델링 여부는 거래 시 확인이 필요합니다."))
        except Exception:
            pass

    # 17. 가격대 검색 (5년 최고가 기준 가격대 언급)
    ts = stats.get("top_sale")
    if ts and ts.get("price"):
        eok_top = ts["price"] // 10000
        if eok_top >= 1:
            qas.append((f"{name} {eok_top}억대 매매 가능한가요?",
                        f"{name} 최근 5년 매매 최고가는 {fmt_price(ts['price'])}, "
                        f"평균은 {fmt_price(stats.get('avg_sale') or ts['price'])} 수준입니다. "
                        f"호수·층·평형에 따라 가격대가 달라집니다."))

    # 18. 같은 동 비교 — 인터널 링크 + 롱테일
    if o.get("umd") and o.get("sido") and o.get("sgg"):
        umd_x = o["umd"]
        sido_x = o["sido"]
        sgg_x = o["sgg"]
        qas.append((f"{umd_x} 오피스텔 중에 {name}만한 단지가 있나요?",
                    f"{umd_x}에는 {name} 외에도 여러 오피스텔이 있습니다. "
                    f"{sido_x} {sgg_x} {umd_x} 오피스텔 전체 목록과 시세 비교가 가능합니다."))

    # 19. 평형별 시세 (default_area 평형의 매매/전세/월세 한 번에)
    # _build_faq 는 stats(전체)만 받으므로 여기선 평형별 미지원 — 본문에서 처리

    # 20. 전세가 매매가 비교 (전세가율 대신 직접 수치 비교)
    rs = stats.get("recent_sale")
    rj = stats.get("recent_jeon")
    if rs and rj and rs.get("price") and rj.get("price") and rs["price"] > 0:
        ratio = round(rj["price"] / rs["price"] * 100, 1)
        qas.append((f"{name} 전세가가 매매가 대비 얼마나?",
                    f"최근 매매가 {fmt_price(rs['price'])}, 최근 전세가 {fmt_price(rj['price'])}로, "
                    f"전세가율은 약 {ratio}%입니다."))

    return qas


# ISO 3166-2:KR 시도 코드 (addressRegion 표준화)
SIDO_ISO = {
    "서울": "KR-11", "부산": "KR-26", "대구": "KR-27", "인천": "KR-28",
    "광주": "KR-29", "대전": "KR-30", "울산": "KR-31", "세종": "KR-50",
    "경기": "KR-41", "강원": "KR-42", "충북": "KR-43", "충남": "KR-44",
    "전북": "KR-45", "전남": "KR-46", "경북": "KR-47", "경남": "KR-48",
    "제주": "KR-49",
}


def _build_jsonld(o: dict, stats: dict, canonical: str, faqs: list[tuple[str, str]]) -> str:
    name = o.get("bld_nm") or ""
    addr = _addr_full(o)
    lat = o.get("road_lat") or o.get("jibun_lat")
    lng = o.get("road_lng") or o.get("jibun_lng")
    sido = o.get("sido") or ""
    sgg = o.get("sgg") or ""
    umd = o.get("umd") or ""

    # 1) Residence (오피스텔: 주거+업무 혼용. ApartmentComplex 보다 적합)
    building = {
        "@type": "Residence",
        "@id": canonical + "#building",
        "name": name,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": addr,
            "addressLocality": f"{sgg} {umd}".strip(),
            "addressRegion": SIDO_ISO.get(sido, sido),
            "addressCountry": "KR",
        },
        "url": canonical,
    }
    if o.get("build_year"):
        # ISO 8601 연도 (Schema.org Date)
        building["yearBuilt"] = f"{int(o['build_year']):04d}"
    if lat and lng:
        building["geo"] = {"@type": "GeoCoordinates", "latitude": lat, "longitude": lng}

    # additionalProperty (호실, 층) — Residence 표준 속성에 없으므로 PropertyValue 로
    add_props = []
    ho = o.get("ho_cnt") or o.get("hhld_cnt")
    if ho:
        add_props.append({
            "@type": "PropertyValue",
            "name": "총 호실 수",
            "value": int(ho),
            "unitText": "호",
        })
    if o.get("grnd_flr"):
        add_props.append({
            "@type": "PropertyValue",
            "name": "지상 최고층",
            "value": int(o["grnd_flr"]),
            "unitText": "층",
        })
    if o.get("strct_name"):
        add_props.append({
            "@type": "PropertyValue",
            "name": "구조",
            "value": o["strct_name"],
        })
    if add_props:
        building["additionalProperty"] = add_props

    # amenityFeature (지하철/학교 top 3) — value 를 QuantitativeValue 로 (분 단위)
    amenity = []
    for s in (o.get("nearby_subway") or [])[:3]:
        dist_m = s.get("distance")
        try:
            mins = max(1, int(round(float(dist_m) / 80))) if dist_m is not None else None
        except Exception:
            mins = None
        item = {
            "@type": "LocationFeatureSpecification",
            "name": f"{s.get('line') or ''} {s.get('name') or ''}".strip(),
        }
        if mins is not None:
            item["value"] = {"@type": "QuantitativeValue", "value": mins, "unitText": "분", "description": "도보 소요 시간"}
        amenity.append(item)
    for s in (o.get("nearby_school") or [])[:3]:
        dist_m = s.get("distance")
        try:
            mins = max(1, int(round(float(dist_m) / 80))) if dist_m is not None else None
        except Exception:
            mins = None
        item = {
            "@type": "LocationFeatureSpecification",
            "name": s.get("name") or "",
        }
        if mins is not None:
            item["value"] = {"@type": "QuantitativeValue", "value": mins, "unitText": "분", "description": "도보 소요 시간"}
        amenity.append(item)
    if amenity:
        building["amenityFeature"] = amenity

    # containedInPlace (동 > 시군구 > 시도 > 대한민국)
    building["containedInPlace"] = {
        "@type": "Place",
        "name": umd,
        "containedInPlace": {
            "@type": "AdministrativeArea",
            "name": sgg,
            "containedInPlace": {
                "@type": "AdministrativeArea",
                "name": sido,
                "containedInPlace": {"@type": "Country", "name": "대한민국"},
            },
        },
    }

    # 2) BreadcrumbList — 동 단계 추가 (HTML 과 일치, 아파트 패턴)
    _addr_for_slug = (o.get("jibun_addr") or o.get("road_addr") or "")
    gu_slug = url_quote(gu_url_slug(sido, sgg), safe="")
    dong_slug = url_quote(make_dong_slug(sgg, umd, _addr_for_slug), safe="")
    breadcrumbs = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
            {"@type": "ListItem", "position": 2, "name": f"{sido} {sgg}",
             "item": f"https://hwik.kr/officetel/gu/{gu_slug}.html"},
            {"@type": "ListItem", "position": 3, "name": umd,
             "item": f"https://hwik.kr/officetel/dong/{dong_slug}.html"},
            {"@type": "ListItem", "position": 4, "name": name},
        ],
    }

    # 3) FAQPage
    faq_ld = {
        "@type": "FAQPage",
        "mainEntity": [{
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a},
        } for q, a in faqs],
    }

    graph = {"@context": "https://schema.org", "@graph": [building, breadcrumbs, faq_ld]}
    return '<script type="application/ld+json">' + json.dumps(graph, ensure_ascii=False) + '</script>'


def _render_price_cards_html(stats_area: dict, kind: str = "매매") -> str:
    if kind == "전세":
        rs = stats_area["recent_jeon"]
        ts = stats_area["top_jeon"]
        label_recent = "최근 전세"
        label_top = "5년 최고 전세"
    else:
        rs = stats_area["recent_sale"]
        ts = stats_area["top_sale"]
        label_recent = "최근 매매"
        label_top = "5년 최고가"
    html = '<div class="price-cards">'
    if rs and rs.get("price"):
        dt_rs = fmt_deal_date_ymd(rs["deal_year"], rs["deal_month"], rs["deal_day"])
        change_primary = ""
        if ts and ts.get("price") and ts["price"] > 0 and rs["price"] != ts["price"]:
            diff_amt = rs["price"] - ts["price"]
            diff_pct = diff_amt / ts["price"] * 100
            cls_p = "down" if diff_amt < 0 else ("up" if diff_amt > 0 else "neutral")
            sign = "-" if diff_amt < 0 else "+"
            change_primary = (f'<div class="price-card-change {cls_p}">'
                              f'최고 대비 {sign}{fmt_price(abs(diff_amt))}({abs(diff_pct):.1f}%)</div>')
        html += (f'<div class="price-card primary">'
                 f'<div class="price-card-label">{label_recent}</div>'
                 f'<div class="price-card-value">{fmt_price(rs["price"])}</div>'
                 f'<div class="price-card-sub">{dt_rs} · 전용 {float(rs.get("excl_use_ar") or 0):.0f}㎡</div>'
                 f'{change_primary}</div>')
    else:
        html += (f'<div class="price-card secondary">'
                 f'<div class="price-card-label">{label_recent}</div>'
                 f'<div class="price-card-value">-</div></div>')
    if ts and ts.get("price"):
        dt_ts = fmt_deal_date_ymd(ts["deal_year"], ts["deal_month"], ts["deal_day"])
        html += (f'<div class="price-card secondary">'
                 f'<div class="price-card-label">{label_top}</div>'
                 f'<div class="price-card-value">{fmt_price(ts["price"])}</div>'
                 f'<div class="price-card-sub">{dt_ts}</div>'
                 f'</div>')
    else:
        html += (f'<div class="price-card secondary">'
                 f'<div class="price-card-label">{label_top}</div>'
                 f'<div class="price-card-value">-</div></div>')
    html += '</div>'
    return html


def _render_metrics_html(stats_area: dict) -> str:
    """3단계 폴백 — 1년 평균(4건+) → 5년 평균(10건+) → 칸 숨김.
    카드 구조: label(상) / value(중, 큼) / foot(하, 거래수). 카드 간 높이 균형.
    """
    sa = stats_area
    metrics = []  # (label, value_html, foot_text, tip)

    def _wol_value_html(dep, rent):
        if dep:
            return (f'<span style="font-size:13px;color:var(--sub);font-weight:500;">보증금</span> '
                    f'{esc(fmt_price(dep))} '
                    f'<span style="color:var(--sub);">/</span> '
                    f'<span style="font-size:13px;color:var(--sub);font-weight:500;">월</span> '
                    f'{rent:,}만')
        return f'월 {rent:,}만'

    # ── 1번 칸: 전세 평균 ─────────────────────────────────────────
    if sa.get("avg_jeon_1y") and sa.get("jeon_1y", 0) >= 4:
        metrics.append(("최근 1년 전세 평균", esc(fmt_price(sa["avg_jeon_1y"])),
                        f"거래 {sa['jeon_1y']}건",
                        f"최근 12개월 전세 거래 {sa['jeon_1y']}건의 보증금 단순 평균. 출처: 국토교통부."))
    elif sa.get("avg_jeon") and sa.get("jeon_5y", 0) >= 10:
        metrics.append(("5년 전세 평균", esc(fmt_price(sa["avg_jeon"])),
                        f"거래 {sa['jeon_5y']}건",
                        f"최근 5년 전세 거래 {sa['jeon_5y']}건의 보증금 단순 평균 (1년 거래 부족 시 fallback). 출처: 국토교통부."))

    # ── 2번 칸: 5년 가격 추세 (CAGR → 5년 매매 평균) ─────────────
    if sa.get("cagr5") is not None and sa.get("sale_5y", 0) >= 4:
        c = sa["cagr5"]
        cls = "up" if c > 0 else ("down" if c < 0 else "neutral")
        arrow = "↗" if c > 0 else ("↘" if c < 0 else "→")
        val = f'<span class="metric-change {cls}">{arrow} {c:+.1f}%/년</span>'
        metrics.append(("5년 가격 추세", val,
                        f"매매 {sa['sale_5y']}건 기준",
                        f"매매 거래 첫해 평균가→마지막해 평균가의 연복리 성장률 (CAGR). 매매 5년 {sa['sale_5y']}건 기준."))
    elif sa.get("avg_sale") and sa.get("sale_5y", 0) >= 4:
        metrics.append(("5년 매매 평균", esc(fmt_price(sa["avg_sale"])),
                        f"거래 {sa['sale_5y']}건",
                        f"최근 5년 매매 거래 {sa['sale_5y']}건의 가격 단순 평균. 출처: 국토교통부."))

    # ── 3번 칸: 월세 평균 ─────────────────────────────────────────
    if sa.get("avg_wol_rent_1y") and sa.get("wol_1y", 0) >= 4:
        metrics.append(("최근 1년 월세 평균",
                        _wol_value_html(sa.get("avg_wol_dep_1y"), sa["avg_wol_rent_1y"]),
                        f"거래 {sa['wol_1y']}건",
                        f"최근 12개월 월세 거래 {sa['wol_1y']}건의 보증금·월세금 단순 평균. 출처: 국토교통부."))
    elif sa.get("avg_wol_rent") and sa.get("wol_5y", 0) >= 10:
        metrics.append(("5년 월세 평균",
                        _wol_value_html(sa.get("avg_wol_dep"), sa["avg_wol_rent"]),
                        f"거래 {sa['wol_5y']}건",
                        f"최근 5년 월세 거래 {sa['wol_5y']}건의 보증금·월세금 단순 평균 (1년 거래 부족 시 fallback). 출처: 국토교통부."))

    if not metrics:
        return ""

    html = '<div class="metrics">'
    for label, value_html, foot, tip in metrics[:3]:
        foot_html = (f'<div class="metric-foot" style="font-size:11px;color:#94a3b8;'
                     f'font-weight:500;margin-top:4px;">{esc(foot)}</div>') if foot else ""
        html += (f'<div class="metric" title="{esc(tip)}" tabindex="0" style="cursor:help;">'
                 f'<div class="metric-label">{label}</div>'
                 f'<div class="metric-value">{value_html}</div>'
                 f'{foot_html}</div>')
    html += '</div>'
    return html


def _render_chart_data(stats: dict, kind: str) -> list[dict]:
    """scatter용 [{x: 날짜, y: 가격(만원), floor, area}]."""
    if kind == "매매":
        src = stats["trades_sale"]
    elif kind == "전세":
        src = stats["trades_jeon"]
    else:
        src = stats["trades_wol"]
    out = []
    for t in src[:500]:
        if not t.get("price"):
            continue
        dt = fmt_deal_date_ymd(t["deal_year"], t["deal_month"], t["deal_day"])
        out.append({
            "x": dt,
            "y": t["price"],
            "floor": t.get("floor"),
            "area": t.get("excl_use_ar"),
        })
    # x 오름차순 정렬 (x축 가독성)
    out.sort(key=lambda p: p["x"])
    return out


def _spec_section(o: dict) -> str:
    rows = []
    if o.get("build_year") and o.get("use_apr_day"):
        ua = str(o["use_apr_day"])
        if len(ua) == 8:
            ua = f"{ua[:4]}.{ua[4:6]}.{ua[6:8]}"
        rows.append(("준공 / 사용승인", f"{o['build_year']}년 / {ua}"))
    elif o.get("build_year"):
        rows.append(("준공", f"{o['build_year']}년"))

    if o.get("grnd_flr"):
        v = f"지상 {int(o['grnd_flr'])}층"
        if o.get("ugrnd_flr"):
            v += f" / 지하 {int(o['ugrnd_flr'])}층"
        rows.append(("층수", v))

    ho = o.get("ho_cnt") or o.get("hhld_cnt")
    if ho:
        rows.append(("호실", f"{int(ho):,}호"))

    if o.get("excl_area_min") is not None and o.get("excl_area_max") is not None:
        lo = float(o["excl_area_min"])
        hi = float(o["excl_area_max"])
        rows.append(("전용면적", f"{lo:.2f}㎡ ~ {hi:.2f}㎡"))

    if o.get("parking_total"):
        rows.append(("주차", f"{int(o['parking_total']):,}대"))

    if o.get("strct_name"):
        rows.append(("구조", esc(o["strct_name"])))

    if o.get("bc_ratio") is not None and o.get("vl_ratio") is not None:
        rows.append(("건폐율 / 용적률", f"{o['bc_ratio']}% / {o['vl_ratio']}%"))

    if o.get("earthquake_rating"):
        rows.append(("내진 등급", esc(o["earthquake_rating"])))

    if o.get("main_purps"):
        rows.append(("주용도", esc(o["main_purps"])))

    if not rows:
        return ""

    items = []
    for k, v in rows:
        items.append(f'<div class="info-row"><span class="info-label">{k}</span>'
                     f'<span class="info-value">{v}</span></div>')
    return ('<div class="section"><h2 class="section-title">단지 정보</h2>'
            '<div style="border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;">'
            + "".join(items) + '</div></div>')


def generate_page(o: dict, trades: list[dict], near: list[dict],
                  near_apt: list[dict] | None = None) -> str:
    slug = o["slug"]
    url_path = o["url"]  # /officetel/{slug}.html
    canonical = f"https://hwik.kr{url_path}"
    name = o.get("bld_nm") or ""
    name_e = esc(name)
    addr = _addr_full(o)
    addr_e = esc(addr)
    sido = esc(o.get("sido") or "")
    sgg = esc(o.get("sgg") or "")
    umd = esc(o.get("umd") or "")
    lat = o.get("road_lat") or o.get("jibun_lat")
    lng = o.get("road_lng") or o.get("jibun_lng")

    stats = summarize(trades)

    # 평형 캡슐 후보 + 평형별 stats (가격카드/보조지표 전환용)
    area_counts = extract_areas(trades, top_n=6)
    area_stats_map: dict[int, dict] = {}
    for ai, _cnt in area_counts:
        area_stats_map[ai] = summarize(filter_trades_by_area(trades, ai))
    # 기본 선택 평형: 거래수 가장 많은 정수 ㎡
    if area_counts:
        default_area = max(area_counts, key=lambda x: x[1])[0]
        stats_area = area_stats_map.get(default_area) or stats
    else:
        default_area = None
        stats_area = stats

    # 기본 선택 탭: 5년 거래 가장 많은 유형 (단지 특성 반영 — 시각 가장 풍부)
    _kind_counts = {
        "매매": stats.get("sale_5y", 0),
        "전세": stats.get("jeon_5y", 0),
        "월세": stats.get("wol_5y", 0),
    }
    default_tab = max(_kind_counts, key=_kind_counts.get) if any(_kind_counts.values()) else "월세"

    faqs = _build_faq(o, stats)
    jsonld = _build_jsonld(o, stats, canonical, faqs)

    # 메타 description — 핵심 정보만 컴팩트하게 (160자 이내 목표)
    rep_rs = stats_area["recent_sale"] if (stats_area.get("recent_sale") and stats_area["recent_sale"].get("price")) else None
    rep_rj = stats_area["recent_jeon"] if (stats_area.get("recent_jeon") and stats_area["recent_jeon"].get("price")) else None
    ho = o.get("ho_cnt") or o.get("hhld_cnt")
    desc_bits = [f"{sgg} {umd} {name}"]
    if o.get("build_year"):
        spec = f"{o['build_year']}년 준공"
        if ho:
            spec += f" {int(ho):,}호"
        desc_bits.append(spec + " 오피스텔.")
    elif ho:
        desc_bits.append(f"총 {int(ho):,}호 오피스텔.")
    if rep_rs:
        dt_rep = fmt_deal_date_ymd(rep_rs["deal_year"], rep_rs["deal_month"], rep_rs["deal_day"])
        area_str = f" 전용 {default_area}㎡" if default_area else ""
        desc_bits.append(f"최근 매매{area_str} {fmt_price(rep_rs['price'])}({dt_rep}).")
    elif rep_rj:
        dt_rep = fmt_deal_date_ymd(rep_rj["deal_year"], rep_rj["deal_month"], rep_rj["deal_day"])
        area_str = f" 전용 {default_area}㎡" if default_area else ""
        desc_bits.append(f"최근 전세{area_str} {fmt_price(rep_rj['price'])}({dt_rep}).")
    desc_bits.append("국토부 실거래.")
    desc = " ".join(desc_bits)
    desc_e = esc(desc)

    # Title — 80자 이내. {sido} {sgg} 까지만, umd 빼서 줄임. 휙 brand 끝에.
    title = f"{name} 시세 · {sido} {sgg} 오피스텔 | 휙"
    title_e = esc(title)

    # 헤더 지하철/학교 태그
    subway_tags = _render_subway_tags(o.get("nearby_subway") or [])
    school_tags = _render_school_tags(o.get("nearby_school") or [])

    # 가격카드/보조지표 — 선택 평형 + default_tab 기준
    # default_tab 이 매매면 매매 가격카드, 전세면 전세 가격카드, 월세면 가격카드 숨김
    pc_kind_for_default = default_tab if default_tab in ("매매", "전세") else "매매"
    pc_html = _render_price_cards_html(stats_area, pc_kind_for_default)
    metrics_html = _render_metrics_html(stats_area)
    pc_initial_display = "none" if default_tab == "월세" else ""

    # 평형 캡슐 (아파트 .pyeong-btn 클래스 재사용)
    if area_counts:
        _chips = []
        for ai, _cnt in area_counts:
            active_cls = " active" if ai == default_area else ""
            _chips.append(
                f'<button type="button" class="pyeong-btn{active_cls}" '
                f'data-area="{ai}">{ai}㎡</button>'
            )
        area_chips_html = (
            '<div style="padding:8px 16px 0;font-size:11px;color:var(--sub);">전용면적 기준</div>'
            '<div class="pyeong-wrap"><div class="pyeong-row">'
            + "".join(_chips) + '</div></div>'
        )
    else:
        area_chips_html = '<div style="padding:12px 16px 6px;font-size:11px;color:var(--sub);">전용면적 기준</div>'

    # 차트 데이터 — 선택 평형 기준 (기본)
    chart_sale = _render_chart_data(stats_area, "매매")
    chart_jeon = _render_chart_data(stats_area, "전세")
    chart_wol = _render_chart_data(stats_area, "월세")

    today = _date.today()
    years = list(range(today.year - 4, today.year + 1))
    def _vol_dict(sv: dict) -> dict:
        return {
            "years": years,
            "매매": [sv["vol_by_year"]["매매"].get(y, 0) for y in years],
            "전세": [sv["vol_by_year"]["전세"].get(y, 0) for y in years],
            "월세": [sv["vol_by_year"]["월세"].get(y, 0) for y in years],
        }
    chart_data = {
        "scatter": {"매매": chart_sale, "전세": chart_jeon, "월세": chart_wol},
        "volume": _vol_dict(stats_area),
    }

    # JSON script 안에서 </script> 조기종료 방지용 escape 함수
    _bs = "\\"
    def _safe_json(d):
        return json.dumps(d, ensure_ascii=False).replace("</", "<" + _bs + "/")

    area_data_map: dict[str, dict] = {}
    for ai, _cnt in area_counts:
        sa = area_stats_map[ai]
        area_data_map[str(ai)] = {
            "pc": _render_price_cards_html(sa, "매매"),
            "pc_by_kind": {
                "매매": _render_price_cards_html(sa, "매매"),
                "전세": _render_price_cards_html(sa, "전세"),
            },
            "metrics": _render_metrics_html(sa),
            "scatter": {
                "매매": _render_chart_data(sa, "매매"),
                "전세": _render_chart_data(sa, "전세"),
                "월세": _render_chart_data(sa, "월세"),
            },
            "volume": _vol_dict(sa),
            "trades": {
                "매매": _render_trade_items_fb(_fallback_trades(area_stats_map, ai, "매매"), area_stats_map),
                "전세": _render_trade_items_fb(_fallback_trades(area_stats_map, ai, "전세"), area_stats_map),
                "월세": _render_trade_items_fb(_fallback_trades(area_stats_map, ai, "월세"), area_stats_map),
            },
        }
    _chart_data_safe = _safe_json(chart_data)
    _area_data_safe = _safe_json(area_data_map)

    spec_html = _spec_section(o)

    # 최근 실거래 (기본 평형 기준 fallback 적용)
    if default_area is not None:
        sale_items = _render_trade_items_fb(_fallback_trades(area_stats_map, default_area, "매매"), area_stats_map)
        jeon_items = _render_trade_items_fb(_fallback_trades(area_stats_map, default_area, "전세"), area_stats_map)
        wol_items = _render_trade_items_fb(_fallback_trades(area_stats_map, default_area, "월세"), area_stats_map)
    else:
        sale_items = _render_trade_items(stats["trades_sale"])
        jeon_items = _render_trade_items(stats["trades_jeon"])
        wol_items = _render_trade_items(stats["trades_wol"])

    nearby_html = _render_nearby(near, near_apt)

    # FAQ 분할: 앞 4개 visible, 나머지 hidden
    def _colorize_lines(html: str) -> str:
        for line in sorted(SUBWAY_LINE_COLORS, key=len, reverse=True):  # 긴 이름 우선
            html = html.replace(line, f'<span style="color:{SUBWAY_LINE_COLORS[line]};font-weight:700;">{line}</span>')
        return html
    def _faq_answer_html(q: str, a: str) -> str:
        a_esc = esc(a)
        if "지하철" in q:
            a_esc = _colorize_lines(a_esc)
        return a_esc
    faq_vis = "".join(
        f'<div class="faq-item"><div class="faq-q">{esc(q)}</div>'
        f'<div class="faq-a">{_faq_answer_html(q, a)}</div></div>' for q, a in faqs[:4])
    faq_hid = "".join(
        f'<div class="faq-item"><div class="faq-q">{esc(q)}</div>'
        f'<div class="faq-a">{_faq_answer_html(q, a)}</div></div>' for q, a in faqs[4:])
    if faq_hid:
        faq_more_block = (
            '<div class="faq-list-hidden" id="faq-hidden">' + faq_hid + '</div>'
            '<div class="faq-more" onclick="'
            "document.getElementById('faq-hidden').classList.toggle('expanded');"
            "this.style.display='none';"
            '">더보기</div>'
        )
    else:
        faq_more_block = ""

    # SEO 본문 (구조: 표 + 시세단락 + 접힘(거래량+인프라) + 인터널 링크)
    _addr_for_link = (o.get("jibun_addr") or o.get("road_addr") or "")
    dong_url = f"/officetel/dong/{url_quote(make_dong_slug(o.get('sgg') or '', o.get('umd') or '', _addr_for_link), safe='')}.html"
    gu_url = f"/officetel/gu/{url_quote(gu_url_slug(o.get('sido') or '', o.get('sgg') or ''), safe='')}.html"
    _umd_raw = o.get("umd") or ""
    _sido_raw = o.get("sido") or ""
    _sgg_raw = o.get("sgg") or ""

    # ── 1) 단지 개요 표 (P1 → table) ───────────────────────────
    spec_rows: list[tuple[str, str]] = []
    spec_rows.append(("소재지", esc(addr)))
    if o.get("build_year"):
        yr = f"{o['build_year']}년"
        if o.get("main_purps"):
            yr += f" · {esc(o['main_purps'])}"
        spec_rows.append(("준공", yr))
    if ho:
        spec_rows.append(("호실", f"총 {int(ho):,}호"))
    if o.get("grnd_flr"):
        v = f"지상 {int(o['grnd_flr'])}층"
        if o.get("ugrnd_flr"):
            v += f" / 지하 {int(o['ugrnd_flr'])}층"
        spec_rows.append(("층수", v))
    if o.get("strct_name"):
        spec_rows.append(("구조", esc(o["strct_name"])))
    if o.get("bc_ratio") is not None and o.get("vl_ratio") is not None:
        spec_rows.append(("건폐 / 용적률", f"{o['bc_ratio']}% / {o['vl_ratio']}%"))
    if o.get("parking_total"):
        spec_rows.append(("주차", f"{int(o['parking_total']):,}대"))
    if area_counts:
        areas_str = " · ".join(f"{a}㎡" for a, _ in area_counts)
        spec_rows.append(("전용면적", areas_str))

    # 2열 그리드 (소재지·전용면적은 폭이 길 수 있으므로 전체폭 가능)
    WIDE_KEYS = {"소재지", "전용면적"}
    spec_items_html = []
    for k, v in spec_rows:
        is_wide = k in WIDE_KEYS
        col_style = "grid-column:1 / -1;" if is_wide else ""
        spec_items_html.append(
            f'<div style="{col_style}display:flex;gap:10px;align-items:baseline;padding:6px 0;border-bottom:1px solid #f1f3f5;">'
            f'<span style="color:var(--sub);font-size:12px;flex-shrink:0;width:70px;">{k}</span>'
            f'<span style="color:var(--dark);font-size:13px;line-height:1.5;">{v}</span>'
            f'</div>'
        )
    spec_table_html = (
        '<dl style="display:grid;grid-template-columns:1fr 1fr;column-gap:24px;row-gap:0;margin:0 0 16px;padding:0;">'
        + "".join(spec_items_html) +
        '</dl>'
    )

    # ── 2) 시세 요약 (P2 — 항상 노출, 라인 분리해 가독성 ↑) ─────
    p2_lines = []
    if rep_rs:
        dt_rs = fmt_deal_date_ymd(rep_rs["deal_year"], rep_rs["deal_month"], rep_rs["deal_day"])
        area_lbl = f"전용 {default_area}㎡ " if default_area else ""
        p2_lines.append(("최근 매매", f"{fmt_price(rep_rs['price'])} <span style='color:var(--sub);font-size:12px;'>({area_lbl}· {dt_rs})</span>"))
    if stats_area.get("top_sale") and stats_area["top_sale"].get("price"):
        ts = stats_area["top_sale"]
        dt_ts = fmt_deal_date_ymd(ts["deal_year"], ts["deal_month"], ts["deal_day"])
        p2_lines.append(("5년 최고", f"{fmt_price(ts['price'])} <span style='color:var(--sub);font-size:12px;'>({dt_ts})</span>"))
    if stats_area.get("avg_jeon"):
        p2_lines.append(("전세 평균", fmt_price(stats_area['avg_jeon'])))
    if stats_area.get("avg_wol_dep") and stats_area.get("avg_wol_rent"):
        p2_lines.append(("월세 평균", f"보증금 {fmt_price(stats_area['avg_wol_dep'])} / 월 {stats_area['avg_wol_rent']:,}만"))
    extra_bits = []
    if stats_area.get("jeonse_rate") is not None:
        extra_bits.append(f"전세가율 {stats_area['jeonse_rate']}%")
    if stats_area.get("cagr5") is not None:
        sign = "상승" if stats_area['cagr5'] > 0 else ("하락" if stats_area['cagr5'] < 0 else "보합")
        extra_bits.append(f"5년 연평균 {stats_area['cagr5']:+.1f}% {sign}")
    p2_html = ""
    if p2_lines or extra_bits:
        rows_html = "".join(
            f'<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;">'
            f'<span style="color:var(--sub);">{k}</span>'
            f'<span style="color:var(--dark);font-weight:500;">{v}</span>'
            f'</div>' for k, v in p2_lines
        )
        extra_html = ""
        if extra_bits:
            extra_html = (f'<div style="margin-top:6px;padding-top:8px;border-top:1px solid #f1f3f5;'
                          f'font-size:12px;color:var(--sub);">{" · ".join(extra_bits)}</div>')
        p2_html = (f'<div style="margin:0 0 14px;">{rows_html}{extra_html}</div>')

    # ── 3) 접힘: 거래 활성도 + 인근 인프라 (P3 + P4) ───────────
    p3_html = ""
    if stats["sale_5y"] or stats["jeon_5y"] or stats["wol_5y"]:
        total5 = stats["sale_5y"] + stats["jeon_5y"] + stats["wol_5y"]
        bd = []
        if stats["sale_5y"]:
            bd.append(f"매매 {stats['sale_5y']:,}건")
        if stats["jeon_5y"]:
            bd.append(f"전세 {stats['jeon_5y']:,}건")
        if stats["wol_5y"]:
            bd.append(f"월세 {stats['wol_5y']:,}건")
        p3_html = (f'<p style="font-size:13px;color:var(--sub);line-height:1.85;margin:0 0 10px;">'
                   f'최근 5년 동안 {esc(name)}에서는 총 {total5:,}건의 실거래가 집계되었으며, '
                   f'{", ".join(bd)}이 신고되었습니다.</p>')

    p4_bits = []
    sub = o.get("nearby_subway") or []
    sbits = []
    for s in sub[:3]:
        nm = s.get("name") or ""
        ln = s.get("line") or ""
        mm = max(1, int(round(float(s.get("distance") or 0) / 80)))
        if nm:
            sbits.append(f"{esc(ln)} {esc(nm)} 도보 {mm}분" if ln else f"{esc(nm)} 도보 {mm}분")
    if sbits:
        # 첫 역 강조 + 단지명 함께 → "X역 도보 Y분 오피스텔" 롱테일 매칭
        first = sub[0] if sub else None
        first_phrase = ""
        if first and first.get("name"):
            first_nm = esc(first.get("name") or "")
            first_ln = esc(first.get("line") or "")
            first_mm = max(1, int(round(float(first.get("distance") or 0) / 80)))
            ln_phrase = f"{first_ln} " if first_ln else ""
            first_phrase = f"{esc(name)}{josa(name,'은는')} {ln_phrase}{first_nm} 도보 {first_mm}분 거리의 역세권 오피스텔로, "
        p4_bits.append(f"{first_phrase}도보권에 {', '.join(sbits)} 등이 있어 출퇴근 접근성이 우수합니다.")
    sch = o.get("nearby_school") or []
    cbits = []
    for s in sch[:3]:
        nm = s.get("name") or ""
        mm = max(1, int(round(float(s.get("distance") or 0) / 80)))
        if nm:
            cbits.append(f"{esc(nm)} 도보 {mm}분")
    if cbits:
        p4_bits.append(f"통학·통근 환경으로는 {', '.join(cbits)} 등 학교가 인근에 위치합니다.")
    # 신축 키워드 (5년 이내 준공일 때 명시)
    if o.get("build_year"):
        try:
            yrs_old = _date.today().year - int(o["build_year"])
            if yrs_old <= 5:
                p4_bits.append(f"{o['build_year']}년 준공으로 {esc(o.get('umd') or '')} 일대의 신축 오피스텔에 해당합니다.")
        except Exception:
            pass
    p4_html = ""
    if p4_bits:
        p4_html = f'<p style="font-size:13px;color:var(--sub);line-height:1.85;margin:0;">{" ".join(p4_bits)}</p>'

    details_html = ""
    if p2_html or p3_html or p4_html:
        details_html = (
            '<details style="margin:0 0 12px;">'
            '<summary style="cursor:pointer;font-size:12px;color:var(--sub);padding:2px 0;list-style:none;'
            'display:inline-flex;align-items:center;gap:4px;">'
            '<span style="display:inline-block;transform:rotate(0deg);transition:transform .15s;">▸</span>'
            '시세 요약 · 거래 활성도 · 인근 인프라 자세히 보기</summary>'
            '<div style="margin-top:8px;">'
            f'{p2_html}{p3_html}{p4_html}'
            '</div></details>'
            '<style>details[open] > summary > span{transform:rotate(90deg) !important;}</style>'
        )

    # ── 4) 인터널 링크 (P5 — 항상 노출, 키워드 풍부 anchor) ─────
    p5_link_bits = []
    if near and len(near) >= 2:
        first2 = near[:2]
        for nb in first2:
            if nb.get("slug") and nb.get("name"):
                # anchor 풍부화: "{sgg} {umd} {name} 오피스텔" → 롱테일 ↑
                anchor = f"{nb.get('umd') or _umd_raw} {nb['name']} 오피스텔".strip()
                p5_link_bits.append(
                    f'<a href="/officetel/{esc(nb["slug"])}.html">{esc(anchor)}</a>'
                )
    nearby_link_str = ""
    if p5_link_bits:
        nearby_link_str = f"인근 단지로는 {', '.join(p5_link_bits)} 등이 있으며, "
    # 동/구 anchor 도 키워드 풍부하게
    dong_anchor = f"{_sido_raw} {_sgg_raw} {_umd_raw} 오피스텔".strip()
    gu_anchor = f"{_sido_raw} {_sgg_raw} 오피스텔 시세".strip()
    p5_html = (
        f'<p style="font-size:13px;color:var(--sub);line-height:1.85;margin:0;">'
        f'{nearby_link_str}'
        f'같은 {esc(_umd_raw)} 일대의 다른 단지는 <a href="{esc(dong_url)}">{esc(dong_anchor)}</a>, '
        f'시군구 단위 비교는 <a href="{esc(gu_url)}">{esc(gu_anchor)}</a>에서 확인할 수 있습니다.'
        f'</p>'
    )

    # p2_html 은 details_html 안에 포함됨 (중복 방지) — 밖에 또 붙이지 않음
    seo_text_html = spec_table_html + details_html + p5_html
    # 평문 fallback (메타·JSON-LD 외에서 사용 안하지만 변수 호환)
    seo_text = ""

    # ── 더 알아보기 (FAQ 직전 cross-link) ───────────────────────
    sido_rank_url = f"/officetel/ranking-{url_quote(_sido_raw, safe='')}.html" if _sido_raw else ""
    _lm_arrow = '<span class="learn-more-arrow">→</span>'
    _lm_items: list[str] = []
    if _umd_raw and dong_url:
        _lm_items.append(
            f'<a class="learn-more-card" href="{esc(dong_url)}" '
            f'aria-label="{esc(_umd_raw)} 다른 오피스텔 시세">'
            f'<span>{esc(_umd_raw)} 다른 오피스텔 시세</span>'
            f'{_lm_arrow}</a>'
        )
    if _sgg_raw and gu_url:
        _lm_items.append(
            f'<a class="learn-more-card" href="{esc(gu_url)}" '
            f'aria-label="{esc(_sgg_raw)} 전체 오피스텔 시세">'
            f'<span>{esc(_sgg_raw)} 전체 오피스텔 시세</span>'
            f'{_lm_arrow}</a>'
        )
    if _sido_raw and sido_rank_url:
        _lm_items.append(
            f'<a class="learn-more-card" href="{esc(sido_rank_url)}" '
            f'aria-label="{esc(_sido_raw)} 오피스텔 거래량 순위">'
            f'<span>{esc(_sido_raw)} 오피스텔 순위</span>'
            f'{_lm_arrow}</a>'
        )
    learn_more_html = ""
    if _lm_items:
        learn_more_html = (
            '<div class="divider"></div>'
            '<section class="section" aria-labelledby="learn-more-h2">'
            '<h2 id="learn-more-h2" class="section-title">더 알아보기</h2>'
            '<div style="display:flex;flex-direction:column;gap:8px;">'
            + "".join(_lm_items)
            + '</div></section>'
        )

    # 기본 탭: 전세 (이전 페이지와 동일 순서)
    return f'''<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_e}</title>
<meta name="description" content="{desc_e}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta property="article:modified_time" content="{BUILD_TIME_KST}">
<meta property="article:section" content="오피스텔 실거래">
<meta property="og:type" content="article"><meta property="og:site_name" content="휙"><meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{title_e}"><meta property="og:description" content="{desc_e}">
<meta property="og:image" content="https://hwik.kr/og-image.png"><meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{title_e}"><meta name="twitter:description" content="{desc_e}">
<link rel="stylesheet" href="/officetel/style.css">
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script defer src="/config.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
<style>
.info-row{{display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding:10px 14px;font-size:12px;}}
.info-row:last-child{{border-bottom:none;}}
.info-label{{color:var(--sub);}} .info-value{{font-weight:500;color:var(--dark);text-align:right;}}
.badge-trade{{display:inline-block;background:#dbeafe;color:#1e40af;font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;margin-left:6px;vertical-align:middle;}}
.badge-direct{{display:inline-block;background:#fef3c7;color:#92400e;font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;margin-left:6px;vertical-align:middle;}}
.faq-list-hidden{{max-height:0;overflow:hidden;transition:max-height .3s ease;}}
.faq-list-hidden.expanded{{max-height:3000px;}}
.faq-more{{margin-top:10px;text-align:center;font-size:12px;color:var(--sub);cursor:pointer;padding:8px;border:1px solid var(--border);border-radius:20px;}}
.header .tag-line{{flex-wrap:nowrap !important;overflow:hidden;position:relative;}}
.header .tag-line::after{{content:"";position:absolute;top:0;right:0;bottom:0;width:32px;background:linear-gradient(to right, rgba(26,26,46,0), rgba(26,26,46,1));pointer-events:none;}}
.sr-only{{position:absolute !important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;}}
table.trade-list{{display:block;width:100%;border-collapse:collapse;}}
table.trade-list tbody{{display:block;}}
table.trade-list tr.trade-item{{display:flex;}}
table.trade-list td{{display:block;}}
table.trade-list td.trade-info{{flex:1;min-width:0;}}
</style>
{DESIGN_D_BLOCK}
{jsonld}
</head>
<body>
<main class="wrap" role="main">
<article itemscope itemtype="https://schema.org/Residence">

<nav class="breadcrumb" aria-label="breadcrumb">
<a href="/">휙</a><span>›</span>
<a href="{esc(gu_url)}">{sido} {sgg}</a><span>›</span>
<a href="{esc(dong_url)}">{umd}</a><span>›</span>
<span>{name_e}</span>
</nav>

<header class="header">
<div class="header-top">
<a class="logo" href="/" style="text-decoration:none;">휙</a>
<div><h1 class="header-name" style="margin:0;">{name_e}</h1>
<div class="header-sub">{sgg} {umd}{f" · {o.get('build_year')}년" if o.get("build_year") else ""}</div></div>
</div>
{subway_tags}
{school_tags}
</header>

<div class="tabs">
<div class="tab{' active' if default_tab == '월세' else ''}" data-tab="월세">월세</div>
<div class="tab{' active' if default_tab == '전세' else ''}" data-tab="전세">전세</div>
<div class="tab{' active' if default_tab == '매매' else ''}" data-tab="매매">매매</div>
</div>

{area_chips_html}
<div id="area-price-cards" style="display:{pc_initial_display};">{pc_html}</div>

<div class="divider" id="divider-before-chart" style="display:{pc_initial_display};"></div>
<section class="chart-section" id="chart-section" aria-labelledby="chart-h2" style="display:{pc_initial_display};">
  <h2 id="chart-h2" class="section-title" style="padding:0 0 10px;font-size:15px;color:var(--dark);margin:0;">가격 추이</h2>
  <div class="chart-title">거래량 (최근 5년)</div>
  <div style="height:80px;position:relative;"><canvas id="volumeChart"></canvas></div>
  <div class="chart-title" style="margin-top:12px;">실거래가</div>
  <div class="chart-wrap"><canvas id="priceChart"></canvas></div>
</section>

<div class="divider"></div>
<div class="section"><h2 class="section-title" id="trade-section-title">최근 실거래</h2>
<table class="trade-list" id="trade-list-매매" style="display:{'' if default_tab == '매매' else 'none'};"><caption class="sr-only">{name_e} 매매 실거래</caption><thead class="sr-only"><tr><th scope="col">유형 및 가격</th><th scope="col">전용면적·층수</th><th scope="col">거래일</th></tr></thead><tbody>{sale_items}</tbody></table>
<table class="trade-list" id="trade-list-전세" style="display:{'' if default_tab == '전세' else 'none'};"><caption class="sr-only">{name_e} 전세 실거래</caption><thead class="sr-only"><tr><th scope="col">유형 및 가격</th><th scope="col">전용면적·층수</th><th scope="col">거래일</th></tr></thead><tbody>{jeon_items}</tbody></table>
<table class="trade-list" id="trade-list-월세" style="display:{'' if default_tab == '월세' else 'none'};"><caption class="sr-only">{name_e} 월세 실거래</caption><thead class="sr-only"><tr><th scope="col">유형 및 가격</th><th scope="col">전용면적·층수</th><th scope="col">거래일</th></tr></thead><tbody>{wol_items}</tbody></table>
</div>

<div class="divider"></div>
<div class="section" id="listing-section" data-officetel-id="{esc(o['id'])}">
<h2 class="section-title">휙 등록 매물</h2>
<div id="listing-content">
<div class="listing-empty">
<div class="listing-empty-text">이 단지에 등록된 매물이 아직 없습니다</div>
<a class="listing-empty-cta" href="/hub-new/" style="text-decoration:none;">중개사님, 매물을 등록해보세요 →</a>
</div>
</div>
</div>

<div class="divider"></div>
<div class="section"><h2 class="section-title">{esc(umd)} 주변 오피스텔</h2>
{nearby_html}
</div>

{('<div class="divider"></div>' '<div class="section" id="map-section"><h2 class="section-title">위치</h2>' '<div style="position:relative;cursor:pointer;" onclick="openOffMap()" role="button" tabindex="0" aria-label="' + esc(addr) + ' 지도 크게 보기">' '<div id="kakao-map" data-lat="' + str(lat) + '" data-lng="' + str(lng) + '" style="width:100%;height:240px;border-radius:8px;overflow:hidden;background:#e5e7eb;pointer-events:none;touch-action:pan-y;" aria-hidden="true"></div>' '<div style="position:absolute;right:10px;bottom:10px;background:rgba(10,10,18,0.85);color:#fff;font-size:11px;font-weight:600;padding:6px 10px;border-radius:18px;display:inline-flex;align-items:center;gap:4px;pointer-events:none;">⤢ 크게 보기</div>' '</div>' '<div style="margin-top:8px;font-size:11px;color:var(--sub);">' + esc(addr) + '</div>' '</div>') if (lat and lng) else ''}

<div class="divider"></div>
<section class="seo-intro" style="padding:0 16px 16px;">
<h2 class="section-title" style="padding:0 0 8px;font-size:15px;color:var(--dark);margin:0;">단지 소개</h2>
{seo_text_html}
</section>

{learn_more_html}

<section class="faq-section"><h2 class="section-title">자주 묻는 질문</h2>
<div class="faq-list-visible">{faq_vis}</div>
{faq_more_block}
</section>

<div class="seo-section" style="padding:16px;">
<details open style="font-size:12px;color:var(--sub);">
<summary style="cursor:pointer;">데이터 안내</summary>
<div style="margin-top:6px;line-height:1.8;">
<b>실거래가</b>: 국토교통부 실거래가 공개시스템 (<a href="https://rt.molit.go.kr/" target="_blank" rel="noopener nofollow">rt.molit.go.kr</a>) · 매일 자동 수집<br>
<b>건축정보</b>: 국토교통부 건축물대장 (전유부 · 총괄표제부)<br>
<b>호실 수</b>: 건축물대장 전유부 등기 기준 (분양 공급 수치와 다를 수 있음)<br>
오피스텔은 전용면적만 표시합니다 (공급면적 규정 없음)<br>
거래 취소·정정 건은 반영이 지연될 수 있습니다
</div>
</details>
<div class="seo-source" style="margin-top:8px;font-size:11px;color:var(--muted);">실거래가 출처: 국토교통부 · 최종 데이터 확인: <time datetime="{BUILD_DATE_KST}">{BUILD_DATE_KST}</time></div>
<div style="margin-top:14px;text-align:center;">
<button type="button" onclick="openReportModal()"
   style="background:none;border:1px solid var(--border,#e5e7eb);border-radius:20px;color:var(--sub,#6b7280);font-size:12px;cursor:pointer;padding:6px 16px;">
데이터 오류 신고
</button>
</div>
</div>

</article>
</main>

<!-- 풀스크린 지도 (agent.html 패턴) -->
<div id="offMapOverlay" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;z-index:9999;background:#0a0a12;flex-direction:column;">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 20px;background:rgba(10,10,18,0.95);flex-shrink:0;border-bottom:1px solid rgba(255,255,255,0.08);">
    <div id="offMapTitle" style="font-size:15px;font-weight:700;color:#fff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;gap:6px;">
      <span style="font-size:11px;font-weight:900;color:#0a0a12;background:#facc15;padding:3px 7px;border-radius:6px;flex-shrink:0;">휙</span>
      <span id="offMapTitleText"></span>
    </div>
    <button type="button" onclick="closeOffMap()" aria-label="닫기"
       style="background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.15);color:#fff;font-size:16px;width:40px;height:40px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;margin-left:12px;">✕</button>
  </div>
  <div id="offMapFull" style="flex:1;width:100%;"></div>
</div>

<footer style="max-width:600px;margin:24px auto 40px;padding:24px 16px 0;border-top:1px solid var(--border,#e5e7eb);text-align:center;font-size:11.5px;color:var(--sub,#6b7280);line-height:1.7;">
<div style="margin-bottom:8px;">
<a href="/about.html" style="color:var(--sub,#6b7280);text-decoration:none;margin:0 8px;">휙 소개</a>·
<a href="/privacy.html" style="color:var(--sub,#6b7280);text-decoration:none;margin:0 8px;">개인정보처리방침</a>·
<a href="/terms.html" style="color:var(--sub,#6b7280);text-decoration:none;margin:0 8px;">이용약관</a>
</div>
<div style="color:var(--muted,#9ca3af);">실거래가 출처: 국토교통부 · 휙(HWIK) · <a href="https://hwik.kr" style="color:var(--muted,#9ca3af);text-decoration:none;">hwik.kr</a></div>
</footer>

<script type="application/json" id="__chart_data">{_chart_data_safe}</script>
<script type="application/json" id="__area_data">{_area_data_safe}</script>
<script>
let CHART_DATA = JSON.parse(document.getElementById('__chart_data').textContent);
const AREA_DATA = JSON.parse(document.getElementById('__area_data').textContent);
const DEFAULT_TAB = {json.dumps(default_tab, ensure_ascii=False)};
let currentTab = DEFAULT_TAB;
let currentArea = null;
const ADDR = {json.dumps(addr, ensure_ascii=False)};
const LAT = {lat if lat else 'null'};
const LNG = {lng if lng else 'null'};

// 탭 전환 (document-level 이벤트 위임 — DOM 파싱 타이밍 무관하게 동작)
function switchTab(t) {{
  currentTab = t;
  document.querySelectorAll('.tabs .tab').forEach(x =>
    x.classList.toggle('active', x.dataset.tab === t));
  ['매매','전세','월세'].forEach(k => {{
    const el = document.getElementById('trade-list-' + k);
    if (el) el.style.display = (k === t) ? '' : 'none';
  }});
  // 월세 탭: 가격카드/보조지표/차트 섹션 숨김 (아파트 패리티)
  const isWol = (t === '월세');
  const pc = document.getElementById('area-price-cards');
  const mt = document.getElementById('area-metrics');
  const cs = document.getElementById('chart-section');
  const dv = document.getElementById('divider-before-chart');
  if (pc) pc.style.display = isWol ? 'none' : '';
  if (mt) mt.style.display = isWol ? 'none' : '';
  if (cs) cs.style.display = isWol ? 'none' : '';
  if (dv) dv.style.display = isWol ? 'none' : '';
  const tst = document.getElementById('trade-section-title');
  if (tst) tst.textContent = '최근 거래';
  // 가격카드를 탭(매매/전세)에 맞게 교체
  if (!isWol && pc && currentArea != null) {{
    const ad = AREA_DATA[String(currentArea)];
    if (ad && ad.pc_by_kind && ad.pc_by_kind[t]) pc.innerHTML = ad.pc_by_kind[t];
  }}
  if (!isWol) renderPriceChart(t);
}}

// 거래량 막대 차트 (3종 스택, 아파트 스타일 — 반투명/얇은 바/축 숨김)
function renderVolumeChart() {{
  const ctx = document.getElementById('volumeChart');
  if (!ctx || typeof Chart === 'undefined') return;
  volumeChart = new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: CHART_DATA.volume.years,
      datasets: [
        {{label: '매매', data: CHART_DATA.volume['매매'], backgroundColor: 'rgba(245,200,66,0.55)', borderRadius: 2, barPercentage: 0.6}},
        {{label: '전세', data: CHART_DATA.volume['전세'], backgroundColor: 'rgba(74,144,217,0.55)', borderRadius: 2, barPercentage: 0.6}},
        {{label: '월세', data: CHART_DATA.volume['월세'], backgroundColor: 'rgba(163,212,104,0.55)', borderRadius: 2, barPercentage: 0.6}},
      ],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{display: true, position: 'bottom', labels: {{boxWidth: 8, font: {{size: 10}}, color: '#6b7280'}}}},
        tooltip: {{callbacks: {{label: c => c.dataset.label + ' ' + c.parsed.y + '건'}}}},
      }},
      scales: {{
        x: {{stacked: true, grid: {{display: false}}, ticks: {{font: {{size: 10}}, color: '#6b7280'}}}},
        y: {{stacked: true, display: false}},
      }},
    }},
  }});
}}

// 실거래가 스캐터 차트 (아파트 스타일 통일)
let priceChart = null;
function _fmtKrwMan(v) {{
  if (v == null) return '-';
  const eok = Math.floor(v / 10000);
  const man = v - eok * 10000;
  if (eok > 0 && man > 0) return eok + '억 ' + man.toLocaleString() + '만';
  if (eok > 0) return eok + '억';
  return v.toLocaleString() + '만';
}}
function renderPriceChart(kind) {{
  const ctx = document.getElementById('priceChart');
  if (!ctx || typeof Chart === 'undefined') return;
  const wrap = ctx.parentElement;
  if (wrap && getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';
  let emptyEl = wrap && wrap.querySelector('.chart-empty');
  const points = (CHART_DATA.scatter[kind] || []);
  if (priceChart) {{ priceChart.destroy(); priceChart = null; }}
  if (!points.length) {{
    ctx.style.display = 'none';
    if (wrap) {{
      if (!emptyEl) {{
        emptyEl = document.createElement('div');
        emptyEl.className = 'chart-empty';
        emptyEl.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;color:var(--sub);';
        wrap.appendChild(emptyEl);
      }}
      emptyEl.textContent = '거래 데이터가 없습니다';
      emptyEl.style.display = '';
    }}
    return;
  }}
  ctx.style.display = '';
  if (emptyEl) emptyEl.style.display = 'none';
  const yVals = points.map(p => p.y);
  const yMin = Math.floor(Math.min(...yVals) * 0.92);
  const yMax = Math.ceil(Math.max(...yVals) * 1.05);
  priceChart = new Chart(ctx, {{
    type: 'scatter',
    data: {{
      datasets: [{{
        data: points.map(p => ({{x: p.x, y: p.y}})),
        backgroundColor: 'rgba(245,200,66,0.7)',
        borderColor: '#f5c842',
        borderWidth: 1,
        pointRadius: 5,
        pointHoverRadius: 7,
        pointHoverBackgroundColor: '#f5c842',
      }}],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      interaction: {{mode: 'nearest', axis: 'x', intersect: false}},
      onClick: (evt, els) => {{ if (els && els.length) hapticTap(15); }},
      plugins: {{
        legend: {{display: false}},
        tooltip: {{
          displayColors: false,
          callbacks: {{
            title: ctx => points[ctx[0].dataIndex].x,
            beforeBody: ctx => {{
              const p = points[ctx[0].dataIndex];
              const parts = [kind];
              if (p.area != null) parts.push(Math.round(p.area) + '㎡');
              if (p.floor != null && p.floor !== '') parts.push(p.floor + '층');
              return parts.join(' · ');
            }},
            label: ctx => _fmtKrwMan(points[ctx.dataIndex].y),
          }},
        }},
      }},
      scales: {{
        x: {{
          type: 'category',
          labels: [...new Set(points.map(p => p.x))],
          grid: {{display: false}},
          ticks: {{
            font: {{size: 10}}, color: '#aaa',
            maxTicksLimit: 8, maxRotation: 0,
            callback: function(val) {{
              const label = this.getLabelForValue(val);
              if (!label) return '';
              const p = label.split('-');
              return p.length >= 2 ? p[0].slice(2) + '.' + p[1] : label;
            }},
          }},
        }},
        y: {{
          grid: {{color: 'rgba(0,0,0,0.05)'}},
          ticks: {{
            font: {{size: 10}}, color: '#aaa',
            callback: v => (v / 10000).toFixed(v % 10000 === 0 ? 0 : 1) + '억',
          }},
          min: yMin, max: yMax,
        }},
      }},
    }},
  }});
}}

// 평형 캡슐 클릭 → 가격카드/지표/차트 모두 해당 평형 기준으로 교체
let volumeChart = null;
function applyArea(ai) {{
  const data = AREA_DATA[String(ai)];
  if (!data) return;
  currentArea = ai;
  document.querySelectorAll('.pyeong-row .pyeong-btn').forEach(x =>
    x.classList.toggle('active', x.dataset.area === String(ai)));
  const pc = document.getElementById('area-price-cards');
  const mt = document.getElementById('area-metrics');
  const pcHtml = (data.pc_by_kind && data.pc_by_kind[currentTab]) || data.pc;
  if (pc) pc.innerHTML = pcHtml;
  if (mt) mt.innerHTML = data.metrics;
  if (data.trades) {{
    ['매매','전세','월세'].forEach(k => {{
      const el = document.getElementById('trade-list-' + k);
      if (!el) return;
      const target = (el.tagName === 'TABLE') ? (el.querySelector('tbody') || el) : el;
      target.innerHTML = data.trades[k] || '';
    }});
  }}
  CHART_DATA = {{scatter: data.scatter, volume: data.volume}};
  if (volumeChart) {{ volumeChart.destroy(); volumeChart = null; }}
  renderVolumeChart();
  renderPriceChart(currentTab);
}}

// document-level 이벤트 위임 (모든 클릭을 한 리스너에서 처리)
document.addEventListener('click', (e) => {{
  const tab = e.target.closest('.tabs .tab');
  if (tab && tab.dataset.tab) {{
    switchTab(tab.dataset.tab);
    return;
  }}
  const chip = e.target.closest('.pyeong-row .pyeong-btn');
  if (chip && chip.dataset.area) {{
    hapticTap(10);
    applyArea(chip.dataset.area);
    return;
  }}
}});

// 모바일 햅틱 (Android Chrome) — iOS Safari 미지원이지만 silent fail
function hapticTap(ms) {{
  try {{ if (navigator.vibrate) navigator.vibrate(ms || 15); }} catch (e) {{}}
}}

window.addEventListener('load', () => {{
  const activeChip = document.querySelector('.pyeong-row .pyeong-btn.active');
  if (activeChip && activeChip.dataset.area) currentArea = activeChip.dataset.area;
  renderVolumeChart();
  switchTab(DEFAULT_TAB);
  setupMapLazyLoad();
}});

// ── 휙 등록 매물 (cards 테이블에서 officetel_id로 조회) ───────
// 아파트 단지와 동일 패턴 — 1슬롯 고정, 계약가능 매물만.
// 데이터 없으면 SSR 빈 상태 유지 (Googlebot이 보는 화면 동일).
function _esc(s) {{
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}
function _fmtPrice(v) {{
  if (v == null || v === '') return '';
  if (typeof v === 'string') return v;
  const n = Number(v); if (!isFinite(n) || n <= 0) return '';
  const eok = Math.floor(n / 10000); const man = n - eok * 10000;
  if (eok > 0 && man > 0) return eok + '억 ' + man.toLocaleString() + '만';
  if (eok > 0) return eok + '억';
  return n.toLocaleString() + '만';
}}
async function loadOfficetelListings() {{
  try {{
    const sec = document.getElementById('listing-section');
    if (!sec) return;
    const oid = sec.dataset.officetelId || '';
    if (!/^o\d/.test(oid.toLowerCase())) return;
    if (typeof window.HWIK_CONFIG === 'undefined' || typeof window.supabase === 'undefined') return;
    const sb = supabase.createClient(HWIK_CONFIG.SUPABASE_URL, HWIK_CONFIG.SUPABASE_KEY);
    // cards.kapt_code 에 officetel id (o-prefix) 가 저장된다는 가정 (아파트와 동일 패턴 확장)
    const {{ data, error }} = await sb.from('cards')
      .select('id,agent_id,property,photos,trade_status,created_at')
      .eq('kapt_code', oid.toLowerCase())
      .eq('trade_status', '계약가능')
      .order('created_at', {{ ascending: false }})
      .limit(20);
    if (error || !data || data.length === 0) return; // 빈 상태 유지

    // 중개사 정보 batch fetch
    const agentIds = [...new Set(data.map(c => c.agent_id).filter(Boolean))];
    const agentInfo = {{}};
    if (agentIds.length > 0) {{
      const ap = await sb.from('profiles')
        .select('id,agent_name,business_name,profile_photo,profile_photo_url')
        .in('id', agentIds);
      (ap.data || []).forEach(p => {{
        agentInfo[p.id] = {{
          agent_name: p.agent_name || '',
          business_name: p.business_name || '',
          photo: p.profile_photo_url || p.profile_photo || ''
        }};
      }});
    }}

    // 1슬롯 고정 (아파트와 동일: "한 카드 = 한 결정")
    const l = (() => {{
      const c = data[0];
      const p = c.property || {{}};
      const photos = Array.isArray(c.photos) ? c.photos : [];
      const thumb = (photos[0] && photos[0].url) || (typeof photos[0] === 'string' ? photos[0] : '');
      const info = agentInfo[c.agent_id] || {{}};
      return {{
        id: c.id, agent_id: c.agent_id,
        agent_name: info.agent_name || '', business_name: info.business_name || '',
        agent_photo: info.photo || '',
        type: p.type || '', price: p.price || '', floor: p.floor || '',
        area: p.area || '', room: p.room || '', move_in: p.move_in || '', thumb
      }};
    }})();

    const href = l.agent_id
      ? '/agent.html?id=' + encodeURIComponent(l.agent_id) + '&kapt_code=' + encodeURIComponent(oid) + '&type=' + encodeURIComponent(l.type || '')
      : '/property_view.html?id=' + encodeURIComponent(l.id);
    const TYPE_ICON = {{매매:'🏠', 전세:'🔑', 월세:'💰', 반전세:'🏡'}};
    const thumbHtml = l.thumb
      ? '<img src="' + _esc(l.thumb) + '" alt="매물" loading="lazy" decoding="async" style="width:80px;height:80px;object-fit:cover;border-radius:8px;flex-shrink:0;">'
      : '<div style="width:80px;height:80px;border-radius:8px;flex-shrink:0;background:#f5f5f5;display:flex;align-items:center;justify-content:center;font-size:28px;">' + (TYPE_ICON[l.type] || '🏠') + '</div>';
    const avatarInitial = (l.business_name || l.agent_name || '?').trim().charAt(0) || '?';
    const avatarHtml = l.agent_photo
      ? '<img src="' + _esc(l.agent_photo) + '" alt="중개사" loading="lazy" decoding="async" style="width:28px;height:28px;border-radius:50%;object-fit:cover;flex-shrink:0;">'
      : '<div style="width:28px;height:28px;border-radius:50%;background:#facc15;color:#1a1a1a;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;flex-shrink:0;">' + _esc(avatarInitial) + '</div>';
    const agentTitle = l.business_name || l.agent_name || '';
    const agentSub = l.business_name && l.agent_name ? l.agent_name + ' 공인중개사' : '';
    const agentHeader = agentTitle
      ? '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;min-width:0;">' + avatarHtml +
        '<div style="min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;">' +
        '<span style="font-size:13px;font-weight:600;">' + _esc(agentTitle) + '</span>' +
        (agentSub ? '<span style="font-size:12px;color:var(--sub);margin-left:6px;">' + _esc(agentSub) + '</span>' : '') +
        '</div></div>'
      : '';
    const tags = [];
    if (l.area) tags.push(/[㎡평]/.test(String(l.area)) ? l.area : l.area + '㎡');
    if (l.floor) tags.push(l.floor + '층');
    if (l.room) tags.push(l.room);
    if (l.move_in) tags.push(l.move_in);
    const tagsHtml = tags.length
      ? '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;">' +
        tags.slice(0, 4).map(t =>
          '<span style="font-size:11px;padding:3px 8px;background:#f5f5f5;border-radius:10px;color:var(--sub);white-space:nowrap;">' + _esc(t) + '</span>'
        ).join('') + '</div>'
      : '';

    const html = '<div class="trade-list">' +
      '<a href="' + href + '" class="listing-item" style="text-decoration:none;color:inherit;display:flex;justify-content:space-between;align-items:center;gap:10px;padding:14px;background:var(--surface);border-radius:var(--radius);box-shadow:0 1px 4px rgba(0,0,0,0.05);">' +
      '<div style="flex:1;min-width:0;">' + agentHeader +
      '<div class="trade-price" style="font-size:14px;">' + _esc(l.type) + ' ' + _esc(_fmtPrice(l.price)) + '</div>' +
      tagsHtml +
      '</div>' + thumbHtml + '</a></div>';

    const content = document.getElementById('listing-content');
    if (content) content.innerHTML = html;
  }} catch (e) {{
    // 실패 시 빈 상태 유지 — 사용자에게 에러 안 보임
    console.warn('loadOfficetelListings failed', e);
  }}
}}
window.addEventListener('load', () => {{ setTimeout(loadOfficetelListings, 0); }});

// ── 데이터 오류 신고 모달 (아파트 단지와 동일 패턴) ───────────
const REPORT_OFFICETEL_ID = {json.dumps(o["id"], ensure_ascii=False)};
const REPORT_OFFICETEL_NAME = {json.dumps(name, ensure_ascii=False)};
function openReportModal() {{
  if (document.getElementById('reportModal')) return;
  const overlay = document.createElement('div');
  overlay.id = 'reportModal';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:flex-end;justify-content:center;';
  const types = ['가격 오류', '면적 오류', '단지 정보 오류', '기타'];
  overlay.innerHTML =
    '<div style="background:var(--bg, #fff);border-radius:20px 20px 0 0;padding:24px 20px 40px;width:100%;max-width:480px;box-shadow:0 -4px 20px rgba(0,0,0,0.15);">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">' +
        '<span style="font-size:16px;font-weight:700;color:var(--text, #1a1a2e);">데이터 오류 신고</span>' +
        '<button onclick="closeReportModal()" style="background:none;border:none;font-size:22px;cursor:pointer;color:var(--sub, #9ca3af);line-height:1;">×</button>' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px;">' +
        types.map(t =>
          '<button onclick="selectReportType(this,\\'' + t + '\\')" data-type="' + t + '"' +
          ' style="padding:10px;border:1.5px solid var(--border, #e5e7eb);border-radius:10px;background:var(--card, #f8f9fa);font-size:14px;cursor:pointer;color:var(--text, #374151);transition:all .15s;">' +
          t + '</button>'
        ).join('') +
      '</div>' +
      '<textarea id="reportMemo" placeholder="추가 내용 (선택사항)" rows="3"' +
        ' style="width:100%;border:1.5px solid var(--border, #e5e7eb);border-radius:10px;padding:10px 12px;font-size:14px;background:var(--bg, #fff);color:var(--text, #374151);resize:none;box-sizing:border-box;"></textarea>' +
      '<button id="reportSubmitBtn" onclick="submitReport()" disabled' +
        ' style="width:100%;margin-top:12px;padding:13px;border:none;border-radius:12px;background:#d1d5db;color:#9ca3af;font-size:15px;font-weight:700;cursor:not-allowed;transition:all .2s;">' +
        '신고하기</button>' +
      '<p id="reportMsg" style="text-align:center;font-size:13px;margin-top:10px;min-height:18px;"></p>' +
    '</div>';
  overlay.addEventListener('click', (e) => {{ if (e.target === overlay) closeReportModal(); }});
  document.body.appendChild(overlay);
}}
function closeReportModal() {{
  const el = document.getElementById('reportModal');
  if (el) el.remove();
}}
function selectReportType(btn, type) {{
  document.querySelectorAll('#reportModal [data-type]').forEach(b => {{
    b.style.background = 'var(--card, #f8f9fa)';
    b.style.borderColor = 'var(--border, #e5e7eb)';
    b.style.color = 'var(--text, #374151)';
    b.style.fontWeight = '400';
  }});
  btn.style.background = '#ede9fe';
  btn.style.borderColor = '#7c3aed';
  btn.style.color = '#7c3aed';
  btn.style.fontWeight = '700';
  const submitBtn = document.getElementById('reportSubmitBtn');
  if (submitBtn) {{
    submitBtn.disabled = false;
    submitBtn.style.background = '#7c3aed';
    submitBtn.style.color = '#fff';
    submitBtn.style.cursor = 'pointer';
  }}
  window._reportType = type;
}}
async function submitReport() {{
  const type = window._reportType;
  if (!type) return;
  const memo = (document.getElementById('reportMemo')?.value || '').trim();
  const btn = document.getElementById('reportSubmitBtn');
  const msg = document.getElementById('reportMsg');
  if (btn) {{ btn.disabled = true; btn.textContent = '전송 중...'; }}
  try {{
    const res = await fetch('https://jqaxejgzkchxbfzgzyzi.supabase.co/functions/v1/report-danji', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        danji_id: REPORT_OFFICETEL_ID,
        danji_name: REPORT_OFFICETEL_NAME,
        report_type: type,
        memo: memo || null,
        page_url: location.href,
      }}),
    }});
    if (res.ok) {{
      if (msg) {{ msg.style.color = '#16a34a'; msg.textContent = '신고가 접수됐습니다. 감사합니다.'; }}
      setTimeout(closeReportModal, 1800);
    }} else {{
      throw new Error('서버 오류');
    }}
  }} catch (e) {{
    if (msg) {{ msg.style.color = '#dc2626'; msg.textContent = '전송 실패. 잠시 후 다시 시도해주세요.'; }}
    if (btn) {{ btn.disabled = false; btn.textContent = '신고하기'; }}
  }}
}}

// ── 카카오 지도 lazy load (스크롤 도달 시에만 SDK 다운) ───────
const KAKAO_JS_KEY = '124cd68b3419bde24e03efa4f1ca2830';
function _hwikMarker(position, map) {{
  const html =
    '<div style="display:flex;flex-direction:column;align-items:center;transform:translateY(-100%)">' +
    '<div style="background:#1a1a2e;color:#f5c518;font-size:12px;font-weight:900;padding:4px 10px;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.5);">휙</div>' +
    '<div style="width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-top:8px solid #1a1a2e;margin-top:-1px;"></div>' +
    '</div>';
  return new kakao.maps.CustomOverlay({{ position: position, content: html, map: map, yAnchor: 0 }});
}}
function _doInitMap() {{
  const el = document.getElementById('kakao-map');
  if (!el) return;
  const lat = parseFloat(el.dataset.lat);
  const lng = parseFloat(el.dataset.lng);
  if (!lat || !lng) return;
  const center = new kakao.maps.LatLng(lat, lng);
  const map = new kakao.maps.Map(el, {{ center: center, level: 4 }});
  _hwikMarker(center, map);
  map.setDraggable(false);
  map.setZoomable(false);
}}
let _offMapInst = null;
function openOffMap() {{
  const el = document.getElementById('kakao-map');
  if (!el) return;
  const lat = parseFloat(el.dataset.lat);
  const lng = parseFloat(el.dataset.lng);
  if (!lat || !lng) return;
  const overlay = document.getElementById('offMapOverlay');
  const titleEl = document.getElementById('offMapTitleText');
  if (titleEl) titleEl.textContent = (document.querySelector('h1') || {{textContent:''}}).textContent;
  overlay.style.display = 'flex';
  history.pushState({{ offMapOpen: true }}, '');
  function _make() {{
    const center = new kakao.maps.LatLng(lat, lng);
    _offMapInst = new kakao.maps.Map(document.getElementById('offMapFull'), {{ center: center, level: 4 }});
    _hwikMarker(center, _offMapInst);
  }}
  if (window.kakao && window.kakao.maps) {{ kakao.maps.load(_make); }}
  else {{ _loadKakaoSdk(); setTimeout(function(){{ if (window.kakao && window.kakao.maps) kakao.maps.load(_make); }}, 600); }}
}}
function closeOffMap() {{
  const overlay = document.getElementById('offMapOverlay');
  overlay.style.display = 'none';
  document.getElementById('offMapFull').innerHTML = '';
  _offMapInst = null;
}}
window.addEventListener('popstate', function() {{
  const overlay = document.getElementById('offMapOverlay');
  if (overlay && overlay.style.display === 'flex') closeOffMap();
}});
function _loadKakaoSdk() {{
  if (window.kakao && window.kakao.maps) {{ kakao.maps.load(_doInitMap); return; }}
  const s = document.createElement('script');
  s.src = '//dapi.kakao.com/v2/maps/sdk.js?appkey=' + KAKAO_JS_KEY + '&autoload=false';
  s.onload = function() {{ kakao.maps.load(_doInitMap); }};
  document.head.appendChild(s);
}}
function setupMapLazyLoad() {{
  const el = document.getElementById('kakao-map');
  if (!el) return;
  if (!('IntersectionObserver' in window)) {{ _loadKakaoSdk(); return; }}
  const obs = new IntersectionObserver(function(entries) {{
    if (entries[0].isIntersecting) {{
      obs.disconnect();
      _loadKakaoSdk();
    }}
  }}, {{ rootMargin: '200px' }});
  obs.observe(el);
}}
</script>
</body></html>
'''


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
    OFFI_DIR.mkdir(parents=True, exist_ok=True)

    one = os.environ.get("ONE_OFFI_ID", "").strip().lower()

    print("officetels 로딩...")
    officetels = fetch_all_officetels()
    print(f"  {len(officetels):,} 건")

    if one:
        # 프리뷰는 전체 officetels 필요 (nearby 계산용)
        target = [o for o in officetels if o["id"].lower() == one]
        if not target:
            print(f"[ONE_OFFI_ID={one}] 대상 없음", file=sys.stderr)
            return 1
        print(f"[프리뷰] 빌드 대상 1건, 전체 9,833건 참조")

        print("해당 단지 trades 로딩...")
        trades_map = defaultdict(list)
        trades_map[target[0]["id"]] = fetch_one_trades(target[0]["id"])
        print(f"  {len(trades_map[target[0]['id']]):,} 건")

        # nearby 구하려면 다른 단지의 '최근 매매' 만 알면 됨 → 샘플은 생략하고
        # 주변 단지는 빠른 쿼리로 한정: 같은 sgg 단지의 최근 매매 1건씩
        print("주변 단지 trades 로딩 (같은 sgg)...")
        same_sgg = [x for x in officetels
                    if x.get("sgg") == target[0].get("sgg") and x["id"] != target[0]["id"]]
        print(f"  {len(same_sgg):,} 단지")
        # 각 단지의 최근 거래 1건만 조회
        for x in same_sgg[:500]:  # 상한
            rows = _get("officetel_trades", {
                "select": ("officetel_id,deal_type,deal_year,deal_month,deal_day,"
                           "price,monthly_rent,excl_use_ar,floor,is_canceled,dealing_gbn"),
                "officetel_id": f"eq.{x['id']}",
                "order": "deal_year.desc,deal_month.desc,deal_day.desc",
                "limit": 1,
            })
            if rows and not rows[0].get("is_canceled"):
                trades_map[x["id"]] = rows
        officetels = target + same_sgg

    else:
        print("trades 로딩 (전체, 단지별 병렬)...")
        trades_map = fetch_all_trades(oids=[o["id"] for o in officetels])
        target = officetels

    print("apartments 로딩 (주변 아파트 보완용)...")
    apartments = fetch_all_apartments()
    print(f"  {len(apartments):,} 건")
    print("danji_pages.recent_trade 로딩...")
    apt_recent = fetch_apartment_recent_trades()
    print(f"  {len(apt_recent):,} 건 (recent_trade 보유)")

    OFFI_LIMIT = 10
    count = 0
    for o in target:
        trades = trades_map.get(o["id"], [])
        near = nearby_officetels(o, officetels, trades_map, top_n=OFFI_LIMIT)
        remain = OFFI_LIMIT - len(near)
        near_apt = nearby_apartments(o, apartments, apt_recent, top_n=remain) if remain > 0 else []
        page = generate_page(o, trades, near, near_apt)
        slug = o["slug"]
        path = OFFI_DIR / f"{slug}.html"
        path.write_text(page, encoding="utf-8")
        count += 1
        if one:
            print(f"[프리뷰] 생성: {path}  ({path.stat().st_size:,} bytes)")
        if count % 1000 == 0:
            print(f"  {count:,} 페이지 생성...", flush=True)
    print(f"완료: {count:,} 페이지 → {OFFI_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
