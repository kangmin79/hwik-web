#!/usr/bin/env python3
"""
build_gu_pages.py — 구/시 단위 정적 HTML 페이지 생성 (SEO)

Supabase danji_pages → gu/[구이름].html (정적 SEO 콘텐츠)
+ gu/index.html (전체 구 목록 페이지)

Usage:
  python build_gu_pages.py
"""

import os, sys, json, time, html as html_mod
from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))
from urllib.parse import quote as url_quote
import requests
from collections import defaultdict
from slug_utils import make_danji_slug, make_dong_slug, detect_region as slug_detect_region, extract_gu_from_address, gu_url_slug
from regions import REGIONS, METRO_KEYS, REGION_LABEL_TO_KEY, ALL_TWO_TOKEN_GU

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)


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

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://jqaxejgzkchxbfzgzyzi.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SB_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GU_DIR = os.path.join(BASE_DIR, "gu")
BUILD_TIME = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# REGIONS / METRO_KEYS / REGION_LABEL_TO_KEY 는 regions.py 단일 소스에서 import.


def gu_filename(region_key, gu_name):
    """구 페이지 파일명(슬러그) — slug_utils.gu_url_slug 에 위임.
    서울/인천/경기: {gu}.html  (기존 URL 유지)
    5대 광역시:   {label}-{gu}.html  (이름 충돌 방지)
    예외: 인천 중구는 서울 중구와 충돌하므로 "인천-중구" 로 분리
    """
    label = REGIONS[region_key]["label"]
    return gu_url_slug(label, gu_name)


# ── 유틸 ──────────────────────────────────────────────────
def esc(s):
    return html_mod.escape(str(s)) if s else ""

def format_price(manwon):
    if not manwon:
        return "-"
    try:
        manwon = int(manwon)
    except (ValueError, TypeError):
        return "-"
    if manwon <= 0:
        return "-"
    uk = manwon // 10000
    rest = manwon % 10000
    if uk > 0 and rest > 0:
        cheon = rest // 1000
        return f"{uk}억 {cheon}천" if cheon > 0 else f"{uk}억 {rest}"
    if uk > 0:
        return f"{uk}억"
    return f"{manwon:,}만"

def detect_region(gu_name):
    for key, r in REGIONS.items():
        if gu_name in r["list"]:
            return key
    return "seoul"


# ── Supabase 조회 ─────────────────────────────────────────
PAGE_LIMIT = 200


def _get_page(url, params, max_attempts=3):
    """Supabase GET + JSON 파싱 + 재시도(2s,4s,6s). 최종 실패 시 raise."""
    last_err = None
    for attempt in range(max_attempts):
        try:
            resp = requests.get(
                url,
                headers={**SB_HEADERS, "Prefer": ""},
                params=params,
                timeout=60,
            )
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            else:
                return resp.json()
        except (requests.exceptions.JSONDecodeError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < max_attempts - 1:
            wait = 2 * (attempt + 1)
            print(f"  ⚠️ Supabase 재시도 {attempt+1}/{max_attempts} ({wait}s 대기): {last_err}")
            time.sleep(wait)
    raise RuntimeError(f"Supabase fetch 실패 (params={params}): {last_err}")


def fetch_all_danji():
    all_data = []
    offset = 0
    while True:
        data = _get_page(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            {
                "select": "id,complex_name,location,address,categories,recent_trade,"
                          "all_time_high,jeonse_rate,total_units,build_year,nearby_subway,"
                          "lat,lng,pyeongs_map",
                "order": "id",
                "offset": offset,
                "limit": PAGE_LIMIT,
            },
        )
        if not data:
            break
        all_data.extend(data)
        offset += PAGE_LIMIT
        if len(data) < PAGE_LIMIT:
            break
        time.sleep(0.2)
    return all_data


# ── 구별 데이터 집계 ─────────────────────────────────────
def best_trade(d):
    cats = d.get("categories") or []
    rt = d.get("recent_trade") or {}
    best, best_diff = None, 999
    for c in cats:
        if rt.get(c) and (rt[c].get("price") or 0) > 0:
            diff = abs(int(c) - 84) if c.isdigit() else 999
            if diff < best_diff:
                best_diff = diff
                best = c
    if not best:
        return None, None
    return best, rt[best]


def build_gu_detail_html(gu_name, danji_list, region_key=None, sibling_gus=None,
                          sibling_meta=None):
    """구 상세 페이지 HTML 생성
    region_key: 지역 키 (없으면 detect_region으로 추정 — 광역시 충돌 주의)
    sibling_gus: [(gu_name, filename_slug), ...] 같은 지역의 다른 구 (상호 링크용)
    sibling_meta: {gu_name: {"slug":..., "lat":..., "lng":..., "count":..., "trades":...}} — 인접/Top5 정렬용
    """
    if region_key is None:
        region_key = detect_region(gu_name)
    region_label = REGIONS[region_key]["label"]
    slug = gu_filename(region_key, gu_name)
    canonical = f"https://hwik.kr/gu/{url_quote(slug, safe='-')}.html"

    # 집계
    total_units = 0
    price_sum, price_count = 0, 0
    jr_sum, jr_count = 0, 0
    trades = []
    dong_map = defaultdict(lambda: {"count": 0, "prices": []})
    sqm_list = []

    for d in danji_list:
        total_units += d.get("total_units") or 0
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []

        # 동 분류 (gu_name이 2토큰이면 dong은 parts[2])
        parts = (d.get("location") or "").split(" ")
        gu_tokens = len(gu_name.split(" "))
        dong = parts[gu_tokens] if len(parts) > gu_tokens else ""
        if dong:
            dong_map[dong]["count"] += 1

        # 가격
        for c in cats:
            t = rt.get(c)
            if t and t.get("price"):
                price_sum += t["price"]
                price_count += 1
                trades.append({
                    "name": d["complex_name"], "location": d.get("location", ""),
                    "address": d.get("address", ""), "id": d["id"],
                    "price": t["price"], "date": t.get("date", ""),
                    "floor": t.get("floor"), "area": c,
                })
                if dong:
                    dong_map[dong]["prices"].append(t["price"])
                # ㎡당 가격: 공급면적(supply) 우선, 없으면 sqm_list에서 제외 (단지 페이지와 일관)
                _pm_entry = (d.get("pyeongs_map") or {}).get(c) or {}
                _supply = _pm_entry.get("supply")
                if _supply and float(_supply) > 0:
                    sqm_list.append({
                        "name": d["complex_name"], "id": d["id"],
                        "location": d.get("location", ""), "address": d.get("address", ""),
                        "price": t["price"], "area": c, "supply_area": float(_supply),
                        "sqmPrice": round(t["price"] / float(_supply)),
                    })
                break

        # 전세가율
        jr = d.get("jeonse_rate")
        if jr and 0 < jr < 200:
            jr_sum += jr
            jr_count += 1

    avg_price = round(price_sum / price_count) if price_count > 0 else None
    avg_jr = round(jr_sum / jr_count * 10) / 10 if jr_count > 0 else None
    trades.sort(key=lambda t: t.get("date", ""), reverse=True)
    sqm_list.sort(key=lambda x: x["sqmPrice"], reverse=True)
    dong_list = sorted(dong_map.items(), key=lambda x: x[1]["count"], reverse=True)

    # 매매가 TOP 3
    price_top = []
    for d in danji_list:
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []
        best_c, best_p = None, 0
        for c in cats:
            p = rt[c].get("price", 0) if rt.get(c) else 0
            if p > best_p:
                best_p = p
                best_c = c
        if best_p > 0:
            price_top.append((d, best_p, best_c))
    price_top.sort(key=lambda x: x[1], reverse=True)
    price_top = price_top[:3]

    # 전세가율 TOP 3
    jr_top = sorted(
        [d for d in danji_list if d.get("jeonse_rate") and 30 < d["jeonse_rate"] < 150],
        key=lambda x: x["jeonse_rate"], reverse=True
    )[:3]

    # 구 평균 좌표 (AdministrativeArea geo)
    _lats = [d.get("lat") for d in danji_list if d.get("lat")]
    _lngs = [d.get("lng") for d in danji_list if d.get("lng")]
    geo_block = None
    if _lats and _lngs:
        geo_block = {
            "@type": "GeoCoordinates",
            "latitude": round(sum(_lats) / len(_lats), 6),
            "longitude": round(sum(_lngs) / len(_lngs), 6),
        }

    # 단지 수 상위 동 3개 (description / 인트로용)
    _top_dongs = [d for d, _ in dong_list[:3]]
    _top_dong_str = "·".join(_top_dongs)

    # 누적 거래 (단지별 best_trade 카운트로 근사)
    _trade_total = len(trades)

    title = f"{region_label} {gu_name} 아파트 실거래가 시세 · {len(danji_list):,}개 단지 | 휙"
    avg_str = f"평균 매매가 {format_price(avg_price)}" if avg_price else ""
    top_name = price_top[0][0].get("complex_name", "") if price_top else ""
    jr_top_name = jr_top[0].get("complex_name", "") if jr_top else ""
    # 풍부 description (~140자, 동 이름 + 숫자 fact + 출처)
    _focus = f"{_top_dong_str} 등 " if _top_dong_str else ""
    desc = (f"{region_label} {gu_name}의 아파트 {len(danji_list):,}개 단지 "
            f"매매·전세·월세 실거래가와 시세를 동별로 비교하세요. "
            f"{_focus}{avg_str + ', ' if avg_str else ''}"
            f"{('최고가 ' + top_name + ', ') if top_name else ''}"
            f"{('전세가율 최고 ' + jr_top_name + '. ') if jr_top_name else ''}"
            f"국토교통부 실거래가 공개시스템 기반.")

    # ── HTML 생성 ──
    lines = []

    # 헤더
    _today_hdr = datetime.now(KST).strftime("%Y-%m-%d")
    lines.append(f'<header class="header"><div class="header-top">')
    lines.append(f'  <a class="logo" href="/" style="text-decoration:none;">휙</a>')
    lines.append(f'  <div><h1 class="header-name">{esc(gu_name)} 아파트 시세</h1>')
    lines.append(f'  <div class="header-sub">{len(danji_list)}개 단지 · {total_units:,}세대 · 마지막 업데이트 {_today_hdr}</div></div>')
    lines.append(f'</div></header>')

    # 브레드크럼
    lines.append(f'<nav class="breadcrumb"><a href="/">휙</a><span>&gt;</span>')
    lines.append(f'<a href="/gu/">{esc(region_label)}</a><span>&gt;</span>{esc(gu_name)}</nav>')

    # 슬림 인트로 (한 줄)
    _intro_parts = [f"<b>{esc(gu_name)}</b> 아파트 {len(danji_list):,}개 단지"]
    if avg_price:
        _intro_parts.append(f"평균 {format_price(avg_price)}")
    if avg_jr:
        _intro_parts.append(f"전세가율 {avg_jr}%")
    if _top_dong_str:
        _intro_parts.append(f"{esc(_top_dong_str)} 중심")
    _intro_text = " · ".join(_intro_parts)
    lines.append(f'<p class="seo-text" style="font-size:13px;line-height:1.7;'
                 f'margin:14px 16px 4px;color:var(--sub);">{_intro_text}</p>')

    # 지표
    lines.append(f'<div class="metrics">')
    lines.append(f'  <div class="metric"><div class="metric-label">단지 수</div><div class="metric-value">{len(danji_list)}개</div></div>')
    lines.append(f'  <div class="metric"><div class="metric-label">평균 매매가</div><div class="metric-value">{format_price(avg_price) if avg_price else "-"}</div></div>')
    lines.append(f'  <div class="metric"><div class="metric-label">평균 전세가율</div><div class="metric-value">{str(avg_jr)+"%" if avg_jr else "-"}</div></div>')
    lines.append(f'</div>')
    lines.append(f'<div class="divider"></div>')

    # (자연어 인용 단락 제거 — hero 카드와 정보 중복)

    # 매매가 TOP 3 — 1위 hero + 2-3위 compact
    if price_top:
        lines.append(f'<div class="section">'
                     f'<h2 class="section-title">{esc(gu_name)}에서 가장 비싼 아파트는?</h2>')
        # 1위 hero
        d1, mp1, area1 = price_top[0]
        slug1 = make_danji_slug(d1["complex_name"], d1.get("location", ""), d1["id"], d1.get("address", ""))
        meta_bits1 = []
        if d1.get("location"):
            meta_bits1.append(esc(d1["location"]))
        if area1:
            meta_bits1.append(f"전용 {area1}㎡")
        if d1.get("build_year"):
            meta_bits1.append(f"{d1['build_year']}년 입주")
        if d1.get("total_units"):
            try:
                meta_bits1.append(f"{int(d1['total_units']):,}세대")
            except Exception:
                pass
        meta1 = " · ".join(meta_bits1)
        t1 = f'{esc(d1["complex_name"])} 실거래가 · {esc(gu_name)} 매매가 1위'
        lines.append(
            f'<a class="danji-hero" title="{t1}" style="text-decoration:none;display:block;" '
            f'href="/danji/{url_quote(slug1, safe="-")}.html">'
            f'<div class="hero-left">'
            f'<span class="rank-badge">매매가 1위</span>'
            f'<div class="hero-name">{esc(d1["complex_name"])}</div>'
            f'<div class="hero-meta">{meta1}</div>'
            f'</div>'
            f'<div class="hero-right">'
            f'<div class="hero-price">{format_price(mp1)}</div>'
            f'<div class="hero-price-label">최고가 기준</div>'
            f'</div></a>'
        )
        # 2-3위 compact
        if len(price_top) > 1:
            lines.append(f'<div style="margin-top:6px;">')
            for i, (d, mp, area) in enumerate(price_top[1:], start=2):
                slug_d = make_danji_slug(d["complex_name"], d.get("location", ""), d["id"], d.get("address", ""))
                cm_bits = []
                if d.get("location"):
                    cm_bits.append(esc(d["location"]))
                if area:
                    cm_bits.append(f"전용 {area}㎡")
                if d.get("build_year"):
                    cm_bits.append(f"{d['build_year']}년")
                cm_meta = " · ".join(cm_bits)
                _t = f'{esc(d["complex_name"])} 실거래가 · {esc(gu_name)} 매매가 {i}위'
                lines.append(
                    f'<a class="danji-compact" title="{_t}" '
                    f'style="text-decoration:none;color:inherit;" '
                    f'href="/danji/{url_quote(slug_d, safe="-")}.html">'
                    f'<div style="display:flex;align-items:center;flex:1;min-width:0;">'
                    f'<span class="danji-compact-rank">{i}</span>'
                    f'<div style="min-width:0;">'
                    f'<div class="danji-compact-name">{esc(d["complex_name"])}</div>'
                    f'<div class="danji-compact-meta">{cm_meta}</div>'
                    f'</div></div>'
                    f'<div class="danji-compact-price">{format_price(mp)}</div>'
                    f'</a>'
                )
            lines.append(f'</div>')
        lines.append(f'</div><div class="divider"></div>')

    # 전세가율 TOP 3 — 1위 hero + 2-3위 compact
    if jr_top:
        lines.append(f'<div class="section">'
                     f'<h2 class="section-title">전세가율이 높은 단지 (실거주 추천)</h2>')
        d1 = jr_top[0]
        slug1 = make_danji_slug(d1["complex_name"], d1.get("location", ""), d1["id"], d1.get("address", ""))
        rt1 = d1.get("recent_trade") or {}
        cats1 = d1.get("categories") or []
        best_c1 = next((c for c in cats1 if rt1.get(c) and rt1[c].get("price")), None)
        meta_bits1 = []
        if d1.get("location"):
            meta_bits1.append(esc(d1["location"]))
        if best_c1:
            meta_bits1.append(f"전용 {best_c1}㎡")
        if d1.get("build_year"):
            meta_bits1.append(f"{d1['build_year']}년 입주")
        if d1.get("total_units"):
            try:
                meta_bits1.append(f"{int(d1['total_units']):,}세대")
            except Exception:
                pass
        meta1 = " · ".join(meta_bits1)
        t1 = f'{esc(d1["complex_name"])} 실거래가 · {esc(gu_name)} 전세가율 1위'
        lines.append(
            f'<a class="danji-hero" title="{t1}" style="text-decoration:none;display:block;" '
            f'href="/danji/{url_quote(slug1, safe="-")}.html">'
            f'<div class="hero-left">'
            f'<span class="rank-badge">전세가율 1위</span>'
            f'<div class="hero-name">{esc(d1["complex_name"])}</div>'
            f'<div class="hero-meta">{meta1}</div>'
            f'</div>'
            f'<div class="hero-right">'
            f'<div class="hero-price">{d1["jeonse_rate"]}%</div>'
            f'<div class="hero-price-label">매매 대비 전세 비율</div>'
            f'</div></a>'
        )
        if len(jr_top) > 1:
            lines.append(f'<div style="margin-top:6px;">')
            for i, d in enumerate(jr_top[1:], start=2):
                slug_d = make_danji_slug(d["complex_name"], d.get("location", ""), d["id"], d.get("address", ""))
                rt = d.get("recent_trade") or {}
                cats = d.get("categories") or []
                best_c = next((c for c in cats if rt.get(c) and rt[c].get("price")), None)
                cm_bits = []
                if d.get("location"):
                    cm_bits.append(esc(d["location"]))
                if best_c:
                    cm_bits.append(f"전용 {best_c}㎡")
                if d.get("build_year"):
                    cm_bits.append(f"{d['build_year']}년")
                cm_meta = " · ".join(cm_bits)
                _t = f'{esc(d["complex_name"])} 실거래가 · {esc(gu_name)} 전세가율 {i}위'
                lines.append(
                    f'<a class="danji-compact" title="{_t}" '
                    f'style="text-decoration:none;color:inherit;" '
                    f'href="/danji/{url_quote(slug_d, safe="-")}.html">'
                    f'<div style="display:flex;align-items:center;flex:1;min-width:0;">'
                    f'<span class="danji-compact-rank">{i}</span>'
                    f'<div style="min-width:0;">'
                    f'<div class="danji-compact-name">{esc(d["complex_name"])}</div>'
                    f'<div class="danji-compact-meta">{cm_meta}</div>'
                    f'</div></div>'
                    f'<div class="danji-compact-price">{d["jeonse_rate"]}%</div>'
                    f'</a>'
                )
            lines.append(f'</div>')
        lines.append(f'</div>')

    lines.append(f'<div class="divider"></div>')

    # 동별 단지 (실제 생성된 dong 페이지만 링크)
    if dong_list:
        lines.append(f'<div class="section"><h2 class="section-title">{esc(gu_name)} 어느 동에 단지가 모여있나?</h2>')
        lines.append(f'<div class="dong-grid">')
        for dong, info in dong_list:
            avg_p = format_price(round(sum(info["prices"]) / len(info["prices"]))) if info["prices"] else ""
            first_d = next((d for d in danji_list if d.get("location", "").split(" ")[1:2] == [dong]), None)
            addr = first_d.get("address", "") if first_d else ""
            dong_slug = make_dong_slug(gu_name, dong, addr)
            if dong_slug in DONG_SLUG_SET:
                lines.append(f'<a class="dong-item" style="text-decoration:none;color:inherit;" href="/dong/{url_quote(dong_slug, safe="-")}.html">')
                lines.append(f'  <div class="dong-name">{esc(dong)}</div>')
                lines.append(f'  <div class="dong-count">{info["count"]}개 단지{" · 평균 "+avg_p if avg_p else ""}</div>')
                lines.append(f'</a>')
            else:
                # dong 페이지 없음 — 링크 없이 표시
                lines.append(f'<div class="dong-item">')
                lines.append(f'  <div class="dong-name">{esc(dong)}</div>')
                lines.append(f'  <div class="dong-count">{info["count"]}개 단지{" · 평균 "+avg_p if avg_p else ""}</div>')
                lines.append(f'</div>')
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    # ㎡당 가격 TOP — 1위 hero + 2~10위 compact (공급면적 기준 — 단지 페이지와 일관)
    if sqm_list:
        lines.append(f'<div class="section">'
                     f'<h2 class="section-title">㎡당 가격이 가장 비싼 단지는? '
                     f'<span style="font-size:10px;color:var(--muted);font-weight:400;">(공급면적 기준)</span></h2>')
        d1 = sqm_list[0]
        slug1 = make_danji_slug(d1["name"], d1["location"], d1["id"], d1["address"])
        _supply1 = d1.get("supply_area")
        _supply_str1 = f"공급 {_supply1:.1f}㎡" if _supply1 else f"전용 {d1['area']}㎡"
        meta1 = f'{esc(d1["location"])} · {_supply_str1} · 거래가 {format_price(d1["price"])}'
        t1 = f'{esc(d1["name"])} ㎡당 시세 · {esc(gu_name)} 1위'
        lines.append(
            f'<a class="danji-hero" title="{t1}" style="text-decoration:none;display:block;" '
            f'href="/danji/{url_quote(slug1, safe="-")}.html">'
            f'<div class="hero-left">'
            f'<span class="rank-badge">㎡당 1위</span>'
            f'<div class="hero-name">{esc(d1["name"])}</div>'
            f'<div class="hero-meta">{meta1}</div>'
            f'</div>'
            f'<div class="hero-right">'
            f'<div class="hero-price">{format_price(d1["sqmPrice"])}</div>'
            f'<div class="hero-price-label">/㎡ 공급면적 기준</div>'
            f'</div></a>'
        )
        if len(sqm_list) > 1:
            lines.append(f'<div style="margin-top:6px;">')
            for i, d in enumerate(sqm_list[1:10], start=2):
                slug_d = make_danji_slug(d["name"], d["location"], d["id"], d["address"])
                _supply = d.get("supply_area")
                _supply_str = f"공급 {_supply:.1f}㎡" if _supply else f"전용 {d['area']}㎡"
                _t = f'{esc(d["name"])} ㎡당 시세 · {esc(gu_name)} {i}위'
                lines.append(
                    f'<a class="danji-compact" title="{_t}" '
                    f'style="text-decoration:none;color:inherit;" '
                    f'href="/danji/{url_quote(slug_d, safe="-")}.html">'
                    f'<div style="display:flex;align-items:center;flex:1;min-width:0;">'
                    f'<span class="danji-compact-rank">{i}</span>'
                    f'<div style="min-width:0;">'
                    f'<div class="danji-compact-name">{esc(d["name"])}</div>'
                    f'<div class="danji-compact-meta">{esc(d["location"])} · {_supply_str}</div>'
                    f'</div></div>'
                    f'<div class="danji-compact-price">{format_price(d["sqmPrice"])}<span style="font-size:10px;color:var(--muted);font-weight:500;"> /㎡</span></div>'
                    f'</a>'
                )
            lines.append(f'</div>')
        lines.append(f'</div>')
        lines.append(f'<div class="divider"></div>')

    # 최근 거래된 단지 (좌:칩+이름+메타 / 우:가격+거래유형+날짜)
    if trades:
        lines.append(f'<div class="section"><h2 class="section-title">최근 거래된 단지</h2>')
        lines.append(f'<div style="display:flex;flex-direction:column;gap:10px;">')
        for t in trades[:10]:
            slug_d = make_danji_slug(t["name"], t.get("location", ""), t["id"], t["address"])
            _date = t.get("date", "")
            _date_html = (f'<time datetime="{esc(_date)}">{esc(_date)}</time>' if _date else "")
            _t_attr = f'{esc(t["name"])} · {esc(gu_name)} 최근 실거래'
            _meta_bits = []
            if t.get("location"):
                _meta_bits.append(esc(t["location"]))
            _meta_bits.append(f'전용 {t["area"]}㎡')
            if t.get("floor"):
                _meta_bits.append(f'{t["floor"]}층')
            _meta = " · ".join(_meta_bits)
            lines.append(
                f'<a class="trade-card" title="{_t_attr}" '
                f'style="text-decoration:none;color:inherit;" '
                f'href="/danji/{url_quote(slug_d, safe="-")}.html">'
                f'<div class="trade-card-left">'
                f'<div class="trade-card-head">'
                f'<span class="trade-cat-chip">아파트</span>'
                f'<span class="trade-card-name">{esc(t["name"])}</span>'
                f'</div>'
                f'<div class="trade-card-meta">{_meta}</div>'
                f'</div>'
                f'<div class="trade-card-right">'
                f'<div class="trade-card-price">{format_price(t["price"])}</div>'
                f'<div class="trade-card-foot">'
                f'<span class="trade-type-chip">매매</span>'
                f'<span class="trade-card-date">{_date_html}</span>'
                f'</div>'
                f'</div></a>'
            )
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    # 인접 구 / 같은 지역 거래량 Top — sibling_meta 기반
    _adjacent: list[tuple[str, str]] = []
    _top_by_count: list[tuple[str, str]] = []
    if sibling_meta:
        _others = [(name, m) for name, m in sibling_meta.items() if name != gu_name]
        # 인접 5개 (현재 구 좌표로부터 거리)
        if geo_block:
            _cur_lat = geo_block["latitude"]
            _cur_lng = geo_block["longitude"]
            _with_dist = []
            for name, m in _others:
                if m.get("lat") and m.get("lng"):
                    d2 = (m["lat"] - _cur_lat) ** 2 + (m["lng"] - _cur_lng) ** 2
                    _with_dist.append((d2, name, m["slug"]))
            _with_dist.sort()
            _adjacent = [(name, slug) for _, name, slug in _with_dist[:6]]
        # 거래량(=단지 수) Top 6 — 자기 자신 제외
        _by_count = sorted(_others, key=lambda x: -(x[1].get("count") or 0))
        _top_by_count = [(name, m["slug"]) for name, m in _by_count[:6]]

    if _adjacent:
        lines.append(f'<div class="section"><h2 class="section-title">{esc(gu_name)} 근처 구/시는?</h2>')
        lines.append(f'<div class="gu-grid">')
        for sib_name, sib_slug in _adjacent:
            _t = f'{esc(sib_name)} 아파트 실거래가 시세'
            lines.append(f'<a class="gu-item" title="{_t}" style="text-decoration:none;color:inherit;" href="/gu/{url_quote(sib_slug, safe="-")}.html">')
            lines.append(f'  <div class="gu-name">{esc(sib_name)}</div><div class="gu-info">시세 보기 →</div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    if _top_by_count:
        lines.append(f'<div class="section"><h2 class="section-title">{esc(region_label)}에서 단지가 많은 곳 TOP 6</h2>')
        lines.append(f'<div class="gu-grid">')
        for sib_name, sib_slug in _top_by_count:
            _t = f'{esc(sib_name)} 아파트 실거래가 시세'
            lines.append(f'<a class="gu-item" title="{_t}" style="text-decoration:none;color:inherit;" href="/gu/{url_quote(sib_slug, safe="-")}.html">')
            lines.append(f'  <div class="gu-name">{esc(sib_name)}</div><div class="gu-info">시세 보기 →</div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    # 같은 지역의 다른 구 (상호 링크 — 인접/Top5 없는 경우 fallback, 또는 추가 보강)
    if sibling_gus and not (_adjacent or _top_by_count):
        lines.append(f'<div class="section"><h2 class="section-title">{esc(region_label)} 다른 지역도 보세요</h2>')
        lines.append(f'<div class="gu-grid">')
        for sib_name, sib_slug in sibling_gus:
            _t = f'{esc(sib_name)} 아파트 실거래가 시세'
            lines.append(f'<a class="gu-item" title="{_t}" style="text-decoration:none;color:inherit;" href="/gu/{url_quote(sib_slug, safe="-")}.html">')
            lines.append(f'  <div class="gu-name">{esc(sib_name)}</div><div class="gu-info">시세 보기 →</div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    # 오피스텔 cross-link (같은 구의 오피스텔 페이지 존재 시)
    _offi_slug = gu_url_slug(region_label, gu_name)
    if _offi_slug in OFFICETEL_GU_SLUG_SET:
        lines.append(f'<div class="section">')
        lines.append(f'<h2 class="section-title">{esc(gu_name)} 오피스텔도 보세요</h2>')
        lines.append(
            f'<a class="gu-item" '
            f'title="{esc(gu_name)} 오피스텔 실거래가 시세" '
            f'style="text-decoration:none;color:inherit;display:block;" '
            f'href="/officetel/gu/{url_quote(_offi_slug, safe="-")}.html">'
            f'<div class="gu-name">{esc(gu_name)} 오피스텔 시세</div>'
            f'<div class="gu-info">매매·전세·월세 실거래가 →</div>'
            f'</a>'
        )
        lines.append(f'</div>')
        lines.append(f'<div class="divider"></div>')

    # FAQ
    lines.append(f'<div class="faq-section"><h2 class="section-title">자주 묻는 질문</h2>')
    lines.append(f'<div class="faq-item"><div class="faq-q">{esc(gu_name)} 아파트 평균 시세는?</div>')
    lines.append(f'<div class="faq-a">{esc(gu_name)} {len(danji_list)}개 단지 평균 매매가는 {format_price(avg_price) if avg_price else "정보 확인 중"}입니다.</div></div>')
    if avg_jr:
        lines.append(f'<div class="faq-item"><div class="faq-q">{esc(gu_name)} 전세가율은?</div>')
        lines.append(f'<div class="faq-a">{esc(gu_name)} 평균 전세가율은 {avg_jr}%입니다.</div></div>')
    if sqm_list:
        lines.append(f'<div class="faq-item"><div class="faq-q">{esc(gu_name)}에서 가장 비싼 아파트는?</div>')
        lines.append(f'<div class="faq-a">공급면적 ㎡당 가격 기준 {esc(sqm_list[0]["name"])}이(가) {format_price(sqm_list[0]["sqmPrice"])}/㎡으로 가장 높습니다.</div></div>')
    lines.append(f'<div class="faq-item"><div class="faq-q">{esc(gu_name)} 아파트 단지 수는?</div>')
    lines.append(f'<div class="faq-a">{esc(gu_name)}에는 총 {len(danji_list)}개 아파트 단지, {total_units:,}세대가 있습니다.</div></div>')
    lines.append(f'</div>')
    lines.append(f'<div class="divider"></div>')

    # CTA
    lines.append(f'<div class="cta-section">')
    lines.append(f'<a class="btn-primary" style="display:block;text-align:center;text-decoration:none;" href="https://hwik.kr">{esc(gu_name)} 매물 전체보기</a>')
    lines.append(f'</div>')

    # SEO + 데이터 안내 (오피스텔 D 디자인 동일 패턴)
    seo_text = f"{esc(gu_name)}의 아파트 실거래가, 전세가, 시세 추이를 확인하세요. {len(danji_list)}개 단지, {total_units:,}세대 규모."
    if avg_price:
        seo_text += f" 평균 매매가 {format_price(avg_price)}."
    if avg_jr:
        seo_text += f" 평균 전세가율 {avg_jr}%."
    seo_text += " 국토교통부 실거래가 공개시스템 데이터 기반."
    lines.append(f'<div class="seo-section" style="padding:16px;">')
    lines.append(f'<div class="seo-text">{seo_text}</div>')
    lines.append(f'<details class="data-notice" style="margin-top:14px;font-size:12px;color:var(--sub);">')
    lines.append(f'<summary style="cursor:pointer;">데이터 안내</summary>')
    lines.append(f'<div style="margin-top:6px;line-height:1.8;">')
    lines.append(f'<b>실거래가</b>: 국토교통부 실거래가 공개시스템 (<a href="https://rt.molit.go.kr/" target="_blank" rel="noopener nofollow">rt.molit.go.kr</a>) · 매일 자동 수집<br>')
    lines.append(f'<b>건축정보</b>: 국토교통부 건축물대장 (전유부 · 총괄표제부)<br>')
    lines.append(f'<b>세대 수</b>: 건축물대장 전유부 등기 기준 (분양 공급 수치와 다를 수 있음)<br>')
    lines.append(f'전용면적 ㎡ 기준 표기, 공급면적은 별도 표시<br>')
    lines.append(f'거래 취소·정정 건은 반영이 지연될 수 있습니다')
    lines.append(f'</div></details>')
    _today = datetime.now(KST).strftime("%Y-%m-%d")
    lines.append(f'<div class="seo-source" style="margin-top:8px;font-size:11px;color:var(--muted);">실거래가 출처: 국토교통부 · 최종 데이터 확인: <time datetime="{_today}">{_today}</time></div>')
    lines.append(f'</div>')

    body = "\n".join(lines)

    # ── JSON-LD 강화 ─────────────────────────────────────────
    place_block = {
        "@type": "AdministrativeArea",
        "name": f"{region_label} {gu_name}",
        "containedInPlace": {
            "@type": "AdministrativeArea",
            "name": region_label,
            "containedInPlace": {"@type": "Country", "name": "대한민국"},
        },
    }
    if geo_block:
        place_block["geo"] = geo_block

    jsonld_org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": "https://hwik.kr/#org",
        "name": "휙 (HWIK)",
        "url": "https://hwik.kr",
        "logo": {"@type": "ImageObject", "url": "https://hwik.kr/og-image.png",
                 "width": 1200, "height": 630},
        "sameAs": ["https://hwik.kr"],
    }

    item_list_elements = []
    for i, d in enumerate(danji_list[:100]):
        if not d.get("complex_name"):
            continue
        _slug = make_danji_slug(d["complex_name"], d.get("location", ""), d["id"], d.get("address", ""))
        bits = []
        loc_first = (d.get("location") or "").split(" ")
        if len(loc_first) > 1:
            bits.append(loc_first[1])
        if d.get("total_units"):
            try:
                bits.append(f"{int(d['total_units']):,}세대")
            except Exception:
                pass
        item = {
            "@type": "ListItem",
            "position": i + 1,
            "url": f"https://hwik.kr/danji/{url_quote(_slug, safe='-')}.html",
            "name": d["complex_name"],
        }
        if bits:
            item["description"] = " · ".join(bits)
        item_list_elements.append(item)

    today_iso = datetime.now(KST).strftime("%Y-%m-%d")
    jsonld_collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title.split(" | ")[0],
        "description": desc,
        "url": canonical,
        "inLanguage": "ko-KR",
        "datePublished": "2026-01-01",
        "dateModified": today_iso,
        "isPartOf": {"@type": "WebSite", "name": "휙", "url": "https://hwik.kr"},
        "publisher": {"@id": "https://hwik.kr/#org"},
        "about": place_block,
        "mainEntity": {
            "@type": "ItemList",
            "name": f"{gu_name} 아파트 시세",
            "numberOfItems": len(item_list_elements),
            "itemListElement": item_list_elements,
        },
    }
    jsonld_place = dict(place_block, **{"@context": "https://schema.org"})

    # FAQ — 핵심 4개로 축소 (가독성)
    faq_qas = [
        (f"{gu_name} 아파트 평균 매매가는?",
         f"{gu_name} {len(danji_list):,}개 단지 평균 매매가는 "
         f"{format_price(avg_price) if avg_price else '확인 중'}입니다."),
    ]
    if top_name and price_top:
        _mp1 = price_top[0][1]
        faq_qas.append((
            f"{gu_name}에서 가장 비싼 아파트는?",
            f"매매가 1위는 {top_name}로 {format_price(_mp1)}에 거래되었습니다."
        ))
    if _top_dong_str:
        faq_qas.append((
            f"{gu_name}에서 아파트 단지가 많은 동은?",
            f"{_top_dong_str} 일대에 아파트 단지가 가장 많이 분포합니다."
        ))
    faq_qas.append((
        f"{gu_name} 아파트 단지 수는?",
        f"총 {len(danji_list):,}개 아파트 단지, {total_units:,}세대."
    ))
    jsonld_faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq_qas
        ],
    }

    jsonld_breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
            {"@type": "ListItem", "position": 2, "name": f"{region_label} 구별 시세",
             "item": "https://hwik.kr/gu/"},
            {"@type": "ListItem", "position": 3, "name": gu_name},
        ],
    }

    jsonld_combined = {"@context": "https://schema.org", "@graph": [
        jsonld_org, jsonld_collection, jsonld_place, jsonld_faq, jsonld_breadcrumb
    ]}

    return wrap_html(title, desc, canonical, body, json.dumps(jsonld_combined, ensure_ascii=False),
                     modified_iso=today_iso)


def build_gu_index_html():
    """전체 구 목록 인덱스 페이지"""
    title = "전국 아파트 시세 - 서울·인천·경기·5대 광역시 | 휙"
    desc = "서울·인천·경기·부산·대구·광주·대전·울산 아파트 실거래가, 시세 추이를 구별로 확인하세요."
    canonical = "https://hwik.kr/gu/"

    lines = []
    lines.append(f'<header class="header"><div class="header-top">')
    lines.append(f'  <a class="logo" href="/" style="text-decoration:none;">휙</a>')
    lines.append(f'  <div><div class="header-name">아파트 시세</div><div class="header-sub">서울·인천·경기·5대 광역시</div></div>')
    lines.append(f'</div></header>')
    lines.append(f'<nav class="breadcrumb"><a href="/">휙</a><span>&gt;</span>구별 시세</nav>')

    for key, r in REGIONS.items():
        # 해당 지역에 생성된 구가 1개라도 있어야 섹션 출력
        visible = [(g, gu_filename(key, g)) for g in r["list"] if gu_filename(key, g) in GU_SLUG_SET]
        if not visible:
            continue
        lines.append(f'<div class="section"><h2 class="section-title">{esc(r["label"])} {esc(r["sub"])}</h2>')
        lines.append(f'<div class="gu-grid">')
        for g, g_slug in visible:
            lines.append(f'<a class="gu-item" style="text-decoration:none;color:inherit;" href="/gu/{url_quote(g_slug, safe="-")}.html">')
            lines.append(f'  <div class="gu-name">{esc(g)}</div><div class="gu-info">아파트 시세 보기 →</div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')

    lines.append(f'<div class="seo-section"><div class="seo-text">서울·인천·경기·부산·대구·광주·대전·울산 아파트 실거래가, 시세 추이를 구별로 확인하세요. 국토교통부 실거래가 공개시스템 데이터 기반.</div>')
    _today_idx = datetime.now(KST).strftime("%Y-%m-%d")
    lines.append(f'<div class="seo-source">실거래가 출처: 국토교통부 · 최종 데이터 확인: {_today_idx}</div></div>')

    body = "\n".join(lines)

    jsonld = {
        "@context": "https://schema.org",
        "@graph": [{
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
                {"@type": "ListItem", "position": 2, "name": "구별 시세"},
            ]
        }]
    }

    return wrap_html(title, desc, canonical, body, json.dumps(jsonld, ensure_ascii=False))


def wrap_html(title, desc, canonical, body, jsonld_str, modified_iso=None):
    _mod = modified_iso or datetime.now(KST).strftime("%Y-%m-%d")
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="휙">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="https://hwik.kr/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{canonical}">
<meta property="article:modified_time" content="{esc(_mod)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="https://hwik.kr/og-image.png">
<meta name="google-site-verification" content="R2ye41AVVTRs8BxEXyEafFSTqMSiHKdb9zgTklrktSI">
<meta name="naver-site-verification" content="367bd1e77a8ad48b74e345be3e4a0f8125c2c4e1">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2DVQXMLC9J"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-2DVQXMLC9J');</script>
<link rel="stylesheet" href="/danji/style.css">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" as="style" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css" media="(min-width: 768px)">
<style>
.dong-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
.dong-item {{ padding:12px; background:var(--card); border-radius:var(--radius); cursor:pointer; transition:all .15s; }}
.dong-item:active {{ transform:scale(0.97); }}
.dong-name {{ font-size:13px; font-weight:500; }}
.dong-count {{ font-size:11px; color:var(--sub); margin-top:2px; }}
.gu-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
.gu-item {{ padding:14px; background:var(--card); border-radius:var(--radius); cursor:pointer; transition:all .15s; border-left:3px solid var(--yellow); }}
.gu-item:active {{ transform:scale(0.97); }}
.gu-name {{ font-size:14px; font-weight:600; }}
.gu-info {{ font-size:11px; color:var(--sub); margin-top:4px; }}
.danji-item {{ display:flex; justify-content:space-between; align-items:center; padding:14px; background:var(--surface); border-radius:var(--radius); cursor:pointer; transition:all .15s; box-shadow:0 1px 4px rgba(0,0,0,0.05); border-left:3px solid var(--yellow); }}
.danji-item:active {{ transform:scale(0.98); }}
.danji-name {{ font-size:13px; font-weight:600; }}
.danji-sub {{ font-size:11px; color:var(--sub); margin-top:2px; }}
.danji-price {{ font-size:14px; font-weight:700; text-align:right; }}
.danji-rate {{ font-size:11px; color:var(--sub); text-align:right; margin-top:2px; }}
.trade-item {{ display:flex; justify-content:space-between; padding:12px 14px; background:var(--surface); border-radius:var(--radius); border-left:3px solid var(--yellow); box-shadow:0 1px 4px rgba(0,0,0,0.06); }}
.trade-price {{ font-size:16px; font-weight:700; }}
.trade-detail {{ font-size:11px; color:var(--sub); margin-top:3px; }}
.trade-date {{ font-size:11px; color:var(--muted); align-self:center; }}
/* 최근 거래 카드 — 좌:이름+메타 / 우:가격+칩+날짜 */
.trade-card {{ display:flex; justify-content:space-between; align-items:center; gap:12px; padding:14px 16px; background:var(--card); border-radius:12px; cursor:pointer; transition:all .15s; }}
.trade-card:active {{ transform:scale(0.99); }}
.trade-card-left {{ flex:1; min-width:0; }}
.trade-card-head {{ display:flex; align-items:center; gap:8px; }}
.trade-cat-chip {{ display:inline-block; padding:2px 8px; background:rgba(99,102,241,0.15); color:#a5b4fc; border-radius:6px; font-size:10.5px; font-weight:700; }}
.trade-card-name {{ font-size:14px; font-weight:700; color:var(--text); letter-spacing:-0.015em; }}
.trade-card-meta {{ font-size:11.5px; color:var(--sub); margin-top:5px; }}
.trade-card-right {{ flex-shrink:0; text-align:right; }}
.trade-card-price {{ font-size:18px; font-weight:800; color:var(--yellow); letter-spacing:-0.02em; }}
.trade-card-foot {{ display:flex; align-items:center; justify-content:flex-end; gap:8px; margin-top:5px; }}
.trade-type-chip {{ display:inline-block; padding:2px 7px; background:rgba(234,88,12,0.15); color:#fb923c; border-radius:5px; font-size:10px; font-weight:700; }}
.trade-card-date {{ font-size:11px; color:var(--muted); }}
/* Hero 박스 — 모바일 다크 기본 */
.hero-box {{ margin:12px 14px; padding:12px 14px; background:var(--card); border-radius:var(--radius); border-left:3px solid var(--yellow); }}
.hero-meta {{ font-size:11.5px; color:var(--sub); line-height:1.6; }}
.hero-tag {{ display:inline-block; padding:1px 6px; background:var(--yellow); color:#0a0a12; border-radius:4px; font-size:10px; font-weight:700; margin-right:4px; }}
.hero-cite {{ font-size:13px; color:var(--text); margin-top:6px; line-height:1.5; }}
.hero-cite a {{ color:var(--yellow); text-decoration:none; font-weight:600; }}
/* 1위 강조 카드 — 모바일 다크 (세로) */
.danji-hero {{ display:block; position:relative; padding:18px 16px; background:linear-gradient(135deg, #2a2820 0%, #2a2515 100%); border:1px solid #3a3525; border-left:4px solid var(--yellow); border-radius:14px; margin-bottom:8px; cursor:pointer; transition:all .15s; }}
.danji-hero:active {{ transform:scale(0.99); }}
.danji-hero .hero-left {{ display:block; }}
.danji-hero .hero-right {{ display:block; margin-top:10px; }}
.danji-hero .rank-badge {{ display:inline-block; padding:3px 9px; background:var(--yellow); color:#0a0a12; border-radius:6px; font-size:10.5px; font-weight:800; margin-bottom:8px; letter-spacing:0.02em; }}
.danji-hero .hero-name {{ font-size:17px; font-weight:700; color:var(--text); letter-spacing:-0.02em; }}
.danji-hero .hero-meta {{ font-size:12px; color:var(--sub); margin-top:6px; line-height:1.6; }}
.danji-hero .hero-price {{ font-size:22px; font-weight:800; color:var(--yellow); letter-spacing:-0.02em; }}
.danji-hero .hero-price-label {{ font-size:11px; color:var(--muted); font-weight:500; margin-top:2px; }}
/* 2-3위 컴팩트 카드 */
.danji-compact {{ display:flex; justify-content:space-between; align-items:center; padding:11px 13px; background:var(--card); border-radius:10px; cursor:pointer; transition:all .15s; }}
.danji-compact:active {{ transform:scale(0.98); }}
.danji-compact-rank {{ display:inline-block; min-width:18px; font-size:12px; font-weight:700; color:var(--muted); margin-right:8px; }}
.danji-compact-name {{ font-size:13px; font-weight:600; color:var(--text); }}
.danji-compact-meta {{ font-size:11px; color:var(--sub); margin-top:2px; }}
.danji-compact-price {{ font-size:14px; font-weight:700; text-align:right; color:var(--text); }}
/* 데이터 안내 details */
.data-notice summary {{ font-weight:600; color:var(--text); }}
.data-notice a {{ color:var(--yellow); text-decoration:none; }}
/* 페이지 푸터 */
.hwik-footer {{ max-width:600px; margin:24px auto 40px; padding:24px 16px 0; border-top:1px solid var(--border, #2a2a3e); text-align:center; font-size:11.5px; color:var(--sub); line-height:1.7; }}
.hwik-footer-links {{ margin-bottom:8px; }}
.hwik-footer-links a {{ color:var(--sub); text-decoration:none; margin:0 8px; }}
.hwik-footer-copy a {{ color:var(--muted); text-decoration:none; }}

/* ── D 디자인 PC 라이트 (≥768px) — 오피스텔 동일 ── */
@media (min-width: 768px) {{
  html, body {{
    background: #F0EEE6 !important;
    font-family: Pretendard, -apple-system, BlinkMacSystemFont,
                 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans CJK KR', sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
    -moz-osx-font-smoothing: grayscale !important;
    text-rendering: optimizeLegibility !important;
    color: #0f172a !important;
  }}
  .wrap, .wrap * {{
    font-family: Pretendard, -apple-system, BlinkMacSystemFont,
                 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans CJK KR', sans-serif !important;
  }}
  .wrap {{
    max-width: 720px !important;
    margin: 32px auto !important;
    background: #fff !important;
    border-radius: 20px !important;
    box-shadow: 0 10px 40px rgba(0,0,0,0.08), 0 2px 8px rgba(0,0,0,0.04) !important;
    overflow: hidden !important;
    padding: 0 !important;
  }}
  .breadcrumb {{
    background: #fff !important;
    padding: 18px 14px 0 !important;
    font-size: 12.5px !important;
    color: #94a3b8 !important;
  }}
  .breadcrumb a {{
    color: #64748b !important; text-decoration: none !important;
    transition: color 0.15s ease !important;
  }}
  .breadcrumb a:hover {{ color: #4338ca !important; }}
  .breadcrumb span {{ color: #cbd5e1 !important; }}
  .header {{
    background: #fff !important;
    padding: 14px 14px 22px !important;
    border-bottom: 1px solid #eef0f4 !important;
  }}
  .header .header-top {{
    display: flex !important; align-items: center !important; gap: 12px !important;
    background: transparent !important; padding: 0 !important;
  }}
  .header .logo {{
    background: #facc15 !important; color: #0a0a12 !important;
    width: 32px !important; height: 32px !important;
    border-radius: 8px !important;
    display: flex !important; align-items: center !important; justify-content: center !important;
    font-weight: 900 !important; font-size: 16px !important;
    flex-shrink: 0 !important;
  }}
  .header .header-name {{
    font-size: 22px !important;
    font-weight: 700 !important;
    color: #4338ca !important;
    letter-spacing: -0.03em !important;
    line-height: 1.25 !important;
    margin: 0 !important;
  }}
  .header .header-sub {{
    font-size: 12.5px !important; color: #64748b !important;
    margin-top: 2px !important;
  }}
  .divider {{ display: none !important; }}
  /* Hero 박스 PC 라이트 */
  .hero-box {{
    margin: 16px 14px 4px !important;
    padding: 14px 16px !important;
    background: linear-gradient(135deg, #fefce8 0%, #fef3c7 100%) !important;
    border: 1px solid #fde68a !important;
    border-left: 3px solid #facc15 !important;
    border-radius: 12px !important;
  }}
  .hero-meta {{ color: #78716c !important; font-size: 12px !important; }}
  .hero-tag {{
    background: #facc15 !important; color: #0a0a12 !important;
    padding: 2px 7px !important; border-radius: 4px !important;
    font-size: 10.5px !important; font-weight: 800 !important;
    letter-spacing: 0.02em !important;
  }}
  .hero-cite {{ color: #1e293b !important; font-size: 13.5px !important; margin-top: 8px !important; }}
  .hero-cite a {{ color: #4338ca !important; font-weight: 700 !important; }}
  .hero-cite a:hover {{ text-decoration: underline !important; }}
  .section {{ padding: 20px 14px !important; }}
  .section-title {{
    font-size: 16px !important; font-weight: 700 !important;
    color: #0f172a !important; letter-spacing: -0.025em !important;
    margin: 0 0 14px !important;
  }}
  /* 지표 박스 */
  .metrics {{
    display: grid !important; grid-template-columns: repeat(3, 1fr) !important;
    gap: 8px !important; padding: 16px 14px 0 !important;
  }}
  .metric {{
    background: #f8fafc !important;
    border: 1px solid #eef0f4 !important;
    border-radius: 10px !important;
    padding: 12px 10px !important; text-align: center !important;
  }}
  .metric-label {{ font-size: 11px !important; color: #64748b !important; }}
  .metric-value {{
    font-size: 16px !important; font-weight: 700 !important;
    color: #0f172a !important; margin-top: 4px !important;
  }}
  /* 단지/거래/구/동 카드 — 라이트 */
  .danji-item, .trade-item, .gu-item, .dong-item {{
    background: #f8fafc !important;
    border: 1px solid #eef0f4 !important;
    border-left: 3px solid #4338ca !important;
    border-radius: 10px !important;
    box-shadow: none !important;
    transition: all 0.15s ease !important;
  }}
  .danji-item:hover, .trade-item:hover, .gu-item:hover, .dong-item:hover {{
    background: #eef2ff !important;
    border-color: #c7d2fe !important;
    border-left-color: #4338ca !important;
    transform: translateX(2px) !important;
    box-shadow: 0 4px 12px rgba(67,56,202,0.08) !important;
  }}
  .danji-name, .gu-name, .dong-name {{
    color: #1e293b !important; font-weight: 700 !important;
    letter-spacing: -0.015em !important;
  }}
  .danji-item:hover .danji-name,
  .gu-item:hover .gu-name,
  .dong-item:hover .dong-name {{ color: #4338ca !important; }}
  .danji-sub, .gu-info, .dong-count {{
    color: #64748b !important; font-weight: 500 !important;
  }}
  .danji-price, .trade-price {{ color: #0f172a !important; }}
  .danji-rate, .trade-detail {{ color: #64748b !important; }}
  .trade-date {{ color: #94a3b8 !important; }}
  /* 최근 거래 카드 — PC 라이트 */
  .trade-card {{
    background: #fff !important;
    border: 1px solid #eef0f4 !important;
    border-radius: 12px !important;
    padding: 14px 18px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
    transition: all 0.15s ease !important;
  }}
  .trade-card:hover {{
    border-color: #c7d2fe !important;
    box-shadow: 0 6px 16px rgba(67,56,202,0.08) !important;
    transform: translateY(-1px) !important;
  }}
  .trade-cat-chip {{
    background: #ede9fe !important; color: #6d28d9 !important;
    padding: 3px 9px !important; border-radius: 6px !important;
    font-size: 10.5px !important; font-weight: 700 !important;
  }}
  .trade-card-name {{ color: #1e293b !important; font-size: 14.5px !important; font-weight: 700 !important; }}
  .trade-card:hover .trade-card-name {{ color: #4338ca !important; }}
  .trade-card-meta {{ color: #64748b !important; font-size: 12px !important; }}
  .trade-card-price {{ color: #ea580c !important; font-size: 19px !important; font-weight: 800 !important; }}
  .trade-type-chip {{
    background: #fff7ed !important; color: #c2410c !important;
    padding: 2px 8px !important; border-radius: 5px !important;
    font-size: 10px !important; font-weight: 700 !important;
  }}
  .trade-card-date {{ color: #94a3b8 !important; font-size: 11.5px !important; }}
  /* 1위 강조 카드 — PC 라이트 (좌우 flex) */
  .danji-hero {{
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 20px !important;
    background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%) !important;
    border: 1px solid #fde68a !important;
    border-left: 4px solid #facc15 !important;
    padding: 18px 22px !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 14px rgba(250,204,21,0.12) !important;
    transition: all 0.18s ease !important;
  }}
  .danji-hero:hover {{
    transform: translateY(-1px) !important;
    box-shadow: 0 8px 22px rgba(250,204,21,0.18) !important;
  }}
  .danji-hero .hero-left {{ flex: 1; min-width: 0; }}
  .danji-hero .hero-right {{ flex-shrink: 0; text-align: right; }}
  .danji-hero .rank-badge {{
    background: #facc15 !important; color: #0a0a12 !important;
    padding: 3px 10px !important; border-radius: 6px !important;
    font-size: 11px !important; font-weight: 800 !important;
    letter-spacing: 0.04em !important;
    margin-bottom: 8px !important;
  }}
  .danji-hero .hero-name {{
    font-size: 18px !important; font-weight: 800 !important;
    color: #1e293b !important; letter-spacing: -0.025em !important;
  }}
  .danji-hero .hero-meta {{ color: #78716c !important; font-size: 12.5px !important; line-height: 1.7 !important; margin-top: 4px !important; }}
  .danji-hero .hero-price {{
    color: #ca8a04 !important; font-size: 26px !important;
    font-weight: 900 !important; letter-spacing: -0.025em !important;
    margin: 0 !important;
  }}
  .danji-hero .hero-price-label {{ color: #a8a29e !important; font-weight: 600 !important; font-size: 11px !important; margin-top: 4px !important; }}
  /* 2-3위 컴팩트 — PC */
  .danji-compact {{
    background: transparent !important;
    border: none !important;
    border-left: 3px solid transparent !important;
    border-bottom: 1px solid #f1f5f9 !important;
    border-radius: 0 !important;
    padding: 12px 12px !important;
    transition: all 0.15s ease !important;
  }}
  .danji-compact:hover {{
    background: #eef2ff !important;
    border-left-color: #4338ca !important;
    transform: translateX(2px) !important;
    border-bottom-color: transparent !important;
    box-shadow: 0 4px 12px rgba(67,56,202,0.08) !important;
  }}
  .danji-compact:last-child {{ border-bottom: none !important; }}
  .danji-compact-rank {{ color: #cbd5e1 !important; font-weight: 800 !important; font-size: 13px !important; }}
  .danji-compact:hover .danji-compact-rank {{ color: #4338ca !important; }}
  .danji-compact-name {{ color: #1e293b !important; font-weight: 600 !important; }}
  .danji-compact:hover .danji-compact-name {{ color: #4338ca !important; font-weight: 700 !important; }}
  .danji-compact-meta {{ color: #64748b !important; }}
  .danji-compact:hover .danji-compact-meta {{ color: #475569 !important; }}
  .danji-compact-price {{ color: #ca8a04 !important; font-weight: 800 !important; letter-spacing: -0.015em !important; }}
  .danji-compact:hover .danji-compact-price {{ color: #4338ca !important; }}
  /* FAQ */
  .faq-section {{ padding: 20px 14px !important; }}
  .faq-item {{
    background: #f8fafc !important; border: 1px solid #eef0f4 !important;
    border-radius: 10px !important; padding: 14px 16px !important;
    margin-bottom: 8px !important;
  }}
  .faq-q {{ color: #1e293b !important; font-weight: 700 !important; }}
  .faq-a {{ color: #475569 !important; margin-top: 6px !important; line-height: 1.7 !important; }}
  /* CTA */
  .cta-section {{ padding: 16px 14px !important; }}
  .btn-primary {{
    background: #4338ca !important; color: #fff !important;
    border-radius: 12px !important; padding: 14px !important;
    font-weight: 700 !important;
    transition: background 0.15s ease, transform 0.15s ease !important;
  }}
  .btn-primary:hover {{ background: #3730a3 !important; transform: translateY(-1px) !important; }}
  /* SEO 영역 */
  .seo-section {{
    background: #fafafa !important; padding: 16px 14px !important;
  }}
  .seo-text {{
    color: #475569 !important;
    font-size: 13px !important; line-height: 1.85 !important;
  }}
  .seo-source {{ color: #94a3b8 !important; font-size: 11px !important; margin-top: 8px !important; }}
  /* 데이터 안내 details */
  .data-notice {{ color: #64748b !important; font-size: 12px !important; }}
  .data-notice summary {{
    cursor: pointer !important; font-weight: 700 !important; color: #1e293b !important;
    padding: 4px 0 !important;
  }}
  .data-notice a {{ color: #4338ca !important; text-decoration: none !important; }}
  .data-notice a:hover {{ text-decoration: underline !important; }}
  /* 페이지 푸터 */
  .hwik-footer {{
    max-width: 720px !important;
    margin: 24px auto 40px !important;
    padding: 24px 16px 0 !important;
    border-top: 1px solid #e5e7eb !important;
    text-align: center !important;
    font-size: 11.5px !important;
    color: #6b7280 !important;
    line-height: 1.7 !important;
  }}
  .hwik-footer-links a {{ color: #6b7280 !important; text-decoration: none !important; margin: 0 8px !important; }}
  .hwik-footer-links a:hover {{ color: #4338ca !important; }}
  .hwik-footer-copy {{ color: #9ca3af !important; }}
  .hwik-footer-copy a {{ color: #9ca3af !important; text-decoration: none !important; }}
}}
</style>
<script type="application/ld+json">{jsonld_str}</script>
</head>
<body>
<div class="wrap">
{body}
</div>
<footer class="hwik-footer">
<div class="hwik-footer-links">
<a href="/about.html">휙 소개</a>·
<a href="/privacy.html">개인정보처리방침</a>·
<a href="/terms.html">이용약관</a>
</div>
<div class="hwik-footer-copy">실거래가 출처: 국토교통부 · 휙(HWIK) · <a href="https://hwik.kr">hwik.kr</a></div>
</footer>
</body>
</html>"""


# ── 메인 ──────────────────────────────────────────────────
# 생성될 슬러그 집합 (링크 유효성 체크용)
GU_SLUG_SET = set()
DONG_SLUG_SET = set()
DANJI_SLUG_SET = set()
OFFICETEL_GU_SLUG_SET = set()  # cross-link 용


def main():
    global GU_SLUG_SET, DONG_SLUG_SET, DANJI_SLUG_SET
    os.makedirs(GU_DIR, exist_ok=True)

    ONE_GU = os.environ.get("ONE_GU", "").strip()
    if ONE_GU:
        print(f"[ONE_GU={ONE_GU}] 단일 구만 빌드 — 기존 파일 유지, 인덱스 미갱신")

    # dong/danji 폴더에 이미 존재하는 슬러그 로드 (gu 페이지에서 링크 필터용)
    DONG_DIR = os.path.join(BASE_DIR, "dong")
    if os.path.isdir(DONG_DIR):
        DONG_SLUG_SET = {os.path.splitext(f)[0] for f in os.listdir(DONG_DIR) if f.endswith(".html")}
    print(f"동 슬러그 {len(DONG_SLUG_SET)}개 인식")

    DANJI_DIR = os.path.join(BASE_DIR, "danji")
    if os.path.isdir(DANJI_DIR):
        DANJI_SLUG_SET = {os.path.splitext(f)[0] for f in os.listdir(DANJI_DIR) if f.endswith(".html")}
    print(f"단지 슬러그 {len(DANJI_SLUG_SET)}개 인식")

    # 오피스텔 gu 슬러그 (cross-link 유효성 체크)
    global OFFICETEL_GU_SLUG_SET
    OFFICETEL_GU_DIR = os.path.join(BASE_DIR, "officetel", "gu")
    if os.path.isdir(OFFICETEL_GU_DIR):
        OFFICETEL_GU_SLUG_SET = {os.path.splitext(f)[0] for f in os.listdir(OFFICETEL_GU_DIR) if f.endswith(".html")}
    print(f"오피스텔 gu 슬러그 {len(OFFICETEL_GU_SLUG_SET)}개 인식")

    # ── 데이터 먼저 확보 (실패 시 기존 파일 보존) ──
    print("Supabase에서 단지 데이터 조회 중...")
    all_danji = fetch_all_danji()
    if not all_danji:
        print("❌ 데이터 0건 — 중단 (기존 gu 페이지 유지)")
        sys.exit(1)
    print(f"  {len(all_danji)}개 단지 로드 완료")

    # ── 데이터 확보 후 기존 gu HTML 전부 삭제 (ONE_GU 모드에선 보존) ──
    if not ONE_GU:
        for f in os.listdir(GU_DIR):
            if f.endswith(".html"):
                os.remove(os.path.join(GU_DIR, f))

    # 2토큰 구/시 목록 (경기+충북+충남+전북+경북+경남 하위 구) — regions.py 단일 소스
    two_token_gu = ALL_TWO_TOKEN_GU

    # 구별 분류 (실제 생성된 danji 페이지가 있는 단지만 포함)
    # 서울/인천/경기/5대 광역시 모두 지원. 이름 충돌은 (region_key, gu_name) 튜플 키로 해결.
    gu_map = defaultdict(list)  # key: (region_key, gu_name)
    for d in all_danji:
        if d.get("id", "").startswith(("offi-", "apt-")):
            continue
        # 지역 판정: address → "서울"/"부산"/... → region_key
        region_label = slug_detect_region(d.get("address", ""))
        region_key = REGION_LABEL_TO_KEY.get(region_label)
        if not region_key:
            continue  # 지원하지 않는 지역
        # 생성된 danji 페이지가 없으면 제외 (rental-only 등)
        slug_d = make_danji_slug(d.get("complex_name", ""), d.get("location", ""), d.get("id", ""), d.get("address", ""))
        if slug_d not in DANJI_SLUG_SET:
            continue
        # gu 추출: address 우선 (경기 2토큰 "수원시 장안구" 정확히 인식),
        # address 없으면 location 에서 fallback
        address = d.get("address") or ""
        gu = extract_gu_from_address(address, two_token_gu)
        if not gu:
            loc = d.get("location") or ""
            parts = loc.split(" ")
            if not parts:
                continue
            if len(parts) >= 2:
                two = parts[0] + " " + parts[1]
                if two in two_token_gu:
                    gu = two
            if not gu:
                raw = parts[0]
                # 알려진 잘못된 location 접두어 정규화 (공백 없이 시+구가 붙은 경우)
                # 예: "청주청원구" → "청주시 청원구"
                LOCATION_GU_FIX = {
                    "청주청원구": "청주시 청원구",
                    "청주상당구": "청주시 상당구",
                    "청주서원구": "청주시 서원구",
                    "청주흥덕구": "청주시 흥덕구",
                    "수원장안구": "수원시 장안구",
                    "수원권선구": "수원시 권선구",
                    "수원팔달구": "수원시 팔달구",
                    "수원영통구": "수원시 영통구",
                    "성남분당구": "성남시 분당구",
                    "성남수정구": "성남시 수정구",
                    "성남중원구": "성남시 중원구",
                    "안양만안구": "안양시 만안구",
                    "안양동안구": "안양시 동안구",
                    "고양덕양구": "고양시 덕양구",
                    "고양일산동구": "고양시 일산동구",
                    "고양일산서구": "고양시 일산서구",
                    "용인처인구": "용인시 처인구",
                    "용인기흥구": "용인시 기흥구",
                    "용인수지구": "용인시 수지구",
                    "창원의창구": "창원시 의창구",
                    "창원성산구": "창원시 성산구",
                    "창원마산합포구": "창원시 마산합포구",
                    "창원마산회원구": "창원시 마산회원구",
                    "창원진해구": "창원시 진해구",
                    "포항남구": "포항시 남구",
                    "포항북구": "포항시 북구",
                    "전주완산구": "전주시 완산구",
                    "전주덕진구": "전주시 덕진구",
                    "천안동남구": "천안시 동남구",
                    "천안서북구": "천안시 서북구",
                }
                gu = LOCATION_GU_FIX.get(raw, raw)
        if gu:
            gu_map[(region_key, gu)].append(d)

    # 생성될 구 슬러그 집합 미리 계산 (인덱스가 올바른 링크만 표시하도록)
    for (region_key, gu_name), danji_list in gu_map.items():
        if len(danji_list) >= 3:
            GU_SLUG_SET.add(gu_filename(region_key, gu_name))
    print(f"생성 예정 구 {len(GU_SLUG_SET)}개")

    # 지역별 sibling 맵 (상호 링크용): region_key → [(gu_name, filename_slug), ...]
    siblings_by_region = defaultdict(list)
    # 지역별 sibling 메타: region_key → {gu_name: {slug, lat, lng, count}}
    sibling_meta_by_region: dict = defaultdict(dict)
    for (region_key, gu_name), danji_list in gu_map.items():
        if len(danji_list) >= 3:
            slug = gu_filename(region_key, gu_name)
            siblings_by_region[region_key].append((gu_name, slug))
            lats = [d.get("lat") for d in danji_list if d.get("lat")]
            lngs = [d.get("lng") for d in danji_list if d.get("lng")]
            sibling_meta_by_region[region_key][gu_name] = {
                "slug": slug,
                "lat": (sum(lats) / len(lats)) if lats else None,
                "lng": (sum(lngs) / len(lngs)) if lngs else None,
                "count": len(danji_list),
            }
    for region_key in siblings_by_region:
        siblings_by_region[region_key].sort(key=lambda x: x[0])

    # 각 구별 상세 페이지
    count = 0
    skip = 0
    for (region_key, gu_name), danji_list in sorted(gu_map.items()):
        if len(danji_list) < 3:
            skip += 1
            continue
        if ONE_GU and gu_name != ONE_GU:
            continue
        # 같은 지역의 다른 구 (자기 자신 제외, 최대 20개)
        sibs = [s for s in siblings_by_region[region_key] if s[0] != gu_name][:20]
        sib_meta = sibling_meta_by_region.get(region_key, {})
        html = build_gu_detail_html(gu_name, danji_list, region_key=region_key,
                                    sibling_gus=sibs, sibling_meta=sib_meta)
        slug = gu_filename(region_key, gu_name)
        fpath = os.path.join(GU_DIR, f"{slug}.html")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(html)
        count += 1

    # 인덱스 페이지 (ONE_GU 모드에선 갱신 안 함)
    if not ONE_GU:
        index_html = build_gu_index_html()
        with open(os.path.join(GU_DIR, "index.html"), "w", encoding="utf-8") as f:
            f.write(index_html)

    print(f"\n{count}개 구 페이지 생성, {skip}개 스킵 (단지 3개 미만)")
    print(f"출력: {GU_DIR}")


if __name__ == "__main__":
    main()
