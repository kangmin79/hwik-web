#!/usr/bin/env python3
"""
build_gu_pages.py — 구/시 단위 정적 HTML 페이지 생성 (SEO)

Supabase danji_pages → gu/[구이름].html (정적 SEO 콘텐츠)
+ gu/index.html (전체 구 목록 페이지)

Usage:
  python build_gu_pages.py
"""

import os, sys, json, time, html as html_mod
from datetime import datetime, timezone
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
                          "all_time_high,jeonse_rate,total_units,build_year,nearby_subway",
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


def build_gu_detail_html(gu_name, danji_list, region_key=None, sibling_gus=None):
    """구 상세 페이지 HTML 생성
    region_key: 지역 키 (없으면 detect_region으로 추정 — 광역시 충돌 주의)
    sibling_gus: [(gu_name, filename_slug), ...] 같은 지역의 다른 구 (상호 링크용)
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
                area_num = float(c) if c.replace(".", "").isdigit() else 0
                if area_num > 0:
                    sqm_list.append({
                        "name": d["complex_name"], "id": d["id"],
                        "location": d.get("location", ""), "address": d.get("address", ""),
                        "price": t["price"], "area": c,
                        "sqmPrice": round(t["price"] / area_num),
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

    title = f"{region_label} {gu_name} 아파트 실거래가 시세 - 휙"
    avg_str = f"평균 매매가 {format_price(avg_price)}" if avg_price else ""
    top_name = price_top[0][0].get("complex_name", "") if price_top else ""
    jr_top_name = jr_top[0].get("complex_name", "") if jr_top else ""
    _parts = [
        f"{region_label} {gu_name} 아파트 {len(danji_list)}개 단지 실거래가·전세가 시세",
        avg_str,
        "매매·전세·월세 면적별 가격",
        f"최고가 {top_name}" if top_name else "",
        f"전세가율 최고 {jr_top_name}" if jr_top_name else "",
        "국토교통부 공개시스템 기반",
    ]
    desc = ". ".join(p for p in _parts if p) + "."

    # ── HTML 생성 ──
    lines = []

    # 헤더
    lines.append(f'<header class="header"><div class="header-top">')
    lines.append(f'  <a class="logo" href="/" style="text-decoration:none;">휙</a>')
    lines.append(f'  <div><h1 class="header-name">{esc(gu_name)} 아파트 시세</h1>')
    lines.append(f'  <div class="header-sub">{len(danji_list)}개 단지 · {total_units:,}세대</div></div>')
    lines.append(f'</div></header>')

    # 브레드크럼
    lines.append(f'<nav class="breadcrumb"><a href="/">휙</a><span>&gt;</span>')
    lines.append(f'<a href="/gu/">{esc(region_label)}</a><span>&gt;</span>{esc(gu_name)}</nav>')

    # 지표
    lines.append(f'<div class="metrics">')
    lines.append(f'  <div class="metric"><div class="metric-label">단지 수</div><div class="metric-value">{len(danji_list)}개</div></div>')
    lines.append(f'  <div class="metric"><div class="metric-label">평균 매매가</div><div class="metric-value">{format_price(avg_price) if avg_price else "-"}</div></div>')
    lines.append(f'  <div class="metric"><div class="metric-label">평균 전세가율</div><div class="metric-value">{str(avg_jr)+"%" if avg_jr else "-"}</div></div>')
    lines.append(f'</div>')
    lines.append(f'<div class="divider"></div>')

    # 매매가 높은 단지 TOP 3
    if price_top:
        lines.append(f'<div class="section"><h2 class="section-title">매매가 높은 단지</h2>')
        lines.append(f'<div style="display:flex;flex-direction:column;gap:8px;">')
        for i, (d, mp, area) in enumerate(price_top):
            slug_d = make_danji_slug(d["complex_name"], d.get("location", ""), d["id"], d.get("address", ""))
            area_txt = f'전용 {area}㎡' if area else ''
            lines.append(f'<a class="danji-item" style="text-decoration:none;color:inherit;" href="/danji/{url_quote(slug_d, safe="-")}.html">')
            lines.append(f'  <div><div class="danji-name">{i+1}. {esc(d["complex_name"])}</div><div class="danji-sub">{esc(d.get("location",""))}{(" · " + area_txt) if area_txt else ""}</div></div>')
            lines.append(f'  <div><div class="danji-price">{format_price(mp)}</div><div class="danji-rate">최고가 기준</div></div>')
            lines.append(f'</a>')
        lines.append(f'</div></div><div class="divider"></div>')

    # 전세가율 높은 단지 TOP 3
    if jr_top:
        lines.append(f'<div class="section"><h2 class="section-title">전세가율 높은 단지</h2>')
        lines.append(f'<div style="display:flex;flex-direction:column;gap:8px;">')
        for i, d in enumerate(jr_top):
            slug_d = make_danji_slug(d["complex_name"], d.get("location", ""), d["id"], d.get("address", ""))
            rt = d.get("recent_trade") or {}
            cats = d.get("categories") or []
            best_c = next((c for c in cats if rt.get(c) and rt[c].get("price")), None)
            area_txt = f'전용 {best_c}㎡' if best_c else ''
            lines.append(f'<a class="danji-item" style="text-decoration:none;color:inherit;" href="/danji/{url_quote(slug_d, safe="-")}.html">')
            lines.append(f'  <div><div class="danji-name">{i+1}. {esc(d["complex_name"])}</div><div class="danji-sub">{esc(d.get("location",""))}{(" · " + area_txt) if area_txt else ""}</div></div>')
            lines.append(f'  <div><div class="danji-price">{d["jeonse_rate"]}%</div><div class="danji-rate">전세가율</div></div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')

    lines.append(f'<div class="divider"></div>')

    # 동별 단지 (실제 생성된 dong 페이지만 링크)
    if dong_list:
        lines.append(f'<div class="section"><h2 class="section-title">동별 단지</h2>')
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

    # ㎡당 가격 TOP 10
    if sqm_list:
        lines.append(f'<div class="section"><h2 class="section-title">㎡당 가격 TOP 10 <span style="font-size:10px;color:var(--muted);font-weight:400;">(전용면적 기준)</span></h2>')
        lines.append(f'<div style="display:flex;flex-direction:column;gap:8px;">')
        for i, d in enumerate(sqm_list[:10]):
            slug_d = make_danji_slug(d["name"], d["location"], d["id"], d["address"])
            lines.append(f'<a class="danji-item" style="text-decoration:none;color:inherit;" href="/danji/{url_quote(slug_d, safe="-")}.html">')
            lines.append(f'  <div><div class="danji-name">{i+1}. {esc(d["name"])}</div><div class="danji-sub">{esc(d["location"])} · 전용{d["area"]}㎡</div></div>')
            lines.append(f'  <div><div class="danji-price">{format_price(d["price"])}</div><div class="danji-rate">{format_price(d["sqmPrice"])}/㎡</div></div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    # 최근 거래
    if trades:
        lines.append(f'<div class="section"><h2 class="section-title">최근 거래</h2>')
        lines.append(f'<div style="display:flex;flex-direction:column;gap:8px;">')
        for t in trades[:10]:
            slug_d = make_danji_slug(t["name"], t.get("location", ""), t["id"], t["address"])
            lines.append(f'<a class="trade-item" style="text-decoration:none;color:inherit;" href="/danji/{url_quote(slug_d, safe="-")}.html">')
            lines.append(f'  <div><div class="trade-price">{format_price(t["price"])}</div>')
            lines.append(f'  <div class="trade-detail">{esc(t["name"])} · {t["area"]}㎡{" · "+str(t["floor"])+"층" if t.get("floor") else ""}</div></div>')
            lines.append(f'  <div class="trade-date">{esc(t.get("date",""))}</div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    # 같은 지역의 다른 구 (상호 링크)
    if sibling_gus:
        lines.append(f'<div class="section"><h2 class="section-title">{esc(region_label)}의 다른 구/시</h2>')
        lines.append(f'<div class="gu-grid">')
        for sib_name, sib_slug in sibling_gus:
            lines.append(f'<a class="gu-item" style="text-decoration:none;color:inherit;" href="/gu/{url_quote(sib_slug, safe="-")}.html">')
            lines.append(f'  <div class="gu-name">{esc(sib_name)}</div><div class="gu-info">시세 보기 →</div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')
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
        lines.append(f'<div class="faq-a">전용면적 ㎡당 가격 기준 {esc(sqm_list[0]["name"])}이(가) {format_price(sqm_list[0]["sqmPrice"])}/㎡으로 가장 높습니다.</div></div>')
    lines.append(f'<div class="faq-item"><div class="faq-q">{esc(gu_name)} 아파트 단지 수는?</div>')
    lines.append(f'<div class="faq-a">{esc(gu_name)}에는 총 {len(danji_list)}개 아파트 단지, {total_units:,}세대가 있습니다.</div></div>')
    lines.append(f'</div>')
    lines.append(f'<div class="divider"></div>')

    # CTA
    lines.append(f'<div class="cta-section">')
    lines.append(f'<a class="btn-primary" style="display:block;text-align:center;text-decoration:none;" href="/mobile-v6.html">{esc(gu_name)} 매물 전체보기</a>')
    lines.append(f'</div>')

    # SEO
    seo_text = f"{esc(gu_name)}의 아파트 실거래가, 전세가, 시세 추이를 확인하세요. {len(danji_list)}개 단지, {total_units:,}세대 규모."
    if avg_price:
        seo_text += f" 평균 매매가 {format_price(avg_price)}."
    if avg_jr:
        seo_text += f" 평균 전세가율 {avg_jr}%."
    seo_text += " 국토교통부 실거래가 공개시스템 데이터 기반."
    lines.append(f'<div class="seo-section"><div class="seo-text">{seo_text}</div>')
    _today = datetime.now().strftime("%Y-%m-%d")
    lines.append(f'<div class="seo-source">실거래가 출처: 국토교통부 · 최종 데이터 확인: {_today}</div></div>')

    body = "\n".join(lines)

    # JSON-LD
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": f"{gu_name} 아파트 평균 매매가는?",
                     "acceptedAnswer": {"@type": "Answer", "text": f"{gu_name} 아파트 실거래가 기반 평균 매매가는 {format_price(avg_price) if avg_price else '확인 중'}입니다."}},
                    {"@type": "Question", "name": f"{gu_name} 아파트 전세가율은?",
                     "acceptedAnswer": {"@type": "Answer", "text": f"{gu_name} 평균 전세가율은 {avg_jr if avg_jr else '확인 중'}%입니다."}},
                ]
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
                    {"@type": "ListItem", "position": 2, "name": f"{region_label} 구별 시세", "item": "https://hwik.kr/gu/"},
                    {"@type": "ListItem", "position": 3, "name": gu_name},
                ]
            },
            {
                "@type": "ItemList",
                "name": f"{gu_name} 아파트 시세",
                "numberOfItems": len(danji_list),
                "itemListElement": [
                    {"@type": "ListItem", "position": i+1, "name": d["complex_name"],
                     "url": f"https://hwik.kr/danji/{url_quote(make_danji_slug(d['complex_name'], d.get('location',''), d['id'], d.get('address','')), safe='-')}.html"}
                    for i, d in enumerate(danji_list[:50])
                ]
            }
        ]
    }

    return wrap_html(title, desc, canonical, body, json.dumps(jsonld, ensure_ascii=False))


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
    _today_idx = datetime.now().strftime("%Y-%m-%d")
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


def wrap_html(title, desc, canonical, body, jsonld_str):
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
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="google-site-verification" content="R2ye41AVVTRs8BxEXyEafFSTqMSiHKdb9zgTklrktSI">
<meta name="naver-site-verification" content="367bd1e77a8ad48b74e345be3e4a0f8125c2c4e1">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2DVQXMLC9J"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-2DVQXMLC9J');</script>
<link rel="stylesheet" href="/danji/style.css">
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
</style>
<script type="application/ld+json">{jsonld_str}</script>
</head>
<body>
<div class="wrap">
{body}
</div>
</body>
</html>"""


# ── 메인 ──────────────────────────────────────────────────
# 생성될 슬러그 집합 (링크 유효성 체크용)
GU_SLUG_SET = set()
DONG_SLUG_SET = set()
DANJI_SLUG_SET = set()


def main():
    global GU_SLUG_SET, DONG_SLUG_SET, DANJI_SLUG_SET
    os.makedirs(GU_DIR, exist_ok=True)

    # dong/danji 폴더에 이미 존재하는 슬러그 로드 (gu 페이지에서 링크 필터용)
    DONG_DIR = os.path.join(BASE_DIR, "dong")
    if os.path.isdir(DONG_DIR):
        DONG_SLUG_SET = {os.path.splitext(f)[0] for f in os.listdir(DONG_DIR) if f.endswith(".html")}
    print(f"동 슬러그 {len(DONG_SLUG_SET)}개 인식")

    DANJI_DIR = os.path.join(BASE_DIR, "danji")
    if os.path.isdir(DANJI_DIR):
        DANJI_SLUG_SET = {os.path.splitext(f)[0] for f in os.listdir(DANJI_DIR) if f.endswith(".html")}
    print(f"단지 슬러그 {len(DANJI_SLUG_SET)}개 인식")

    # ── 데이터 먼저 확보 (실패 시 기존 파일 보존) ──
    print("Supabase에서 단지 데이터 조회 중...")
    all_danji = fetch_all_danji()
    if not all_danji:
        print("❌ 데이터 0건 — 중단 (기존 gu 페이지 유지)")
        sys.exit(1)
    print(f"  {len(all_danji)}개 단지 로드 완료")

    # ── 데이터 확보 후 기존 gu HTML 전부 삭제 ──
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
    for (region_key, gu_name), danji_list in gu_map.items():
        if len(danji_list) >= 3:
            siblings_by_region[region_key].append((gu_name, gu_filename(region_key, gu_name)))
    for region_key in siblings_by_region:
        siblings_by_region[region_key].sort(key=lambda x: x[0])

    # 각 구별 상세 페이지
    count = 0
    skip = 0
    for (region_key, gu_name), danji_list in sorted(gu_map.items()):
        if len(danji_list) < 3:
            skip += 1
            continue
        # 같은 지역의 다른 구 (자기 자신 제외, 최대 20개)
        sibs = [s for s in siblings_by_region[region_key] if s[0] != gu_name][:20]
        html = build_gu_detail_html(gu_name, danji_list, region_key=region_key, sibling_gus=sibs)
        slug = gu_filename(region_key, gu_name)
        fpath = os.path.join(GU_DIR, f"{slug}.html")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(html)
        count += 1

    # 인덱스 페이지 (구 슬러그 집합 기반으로 링크 필터)
    index_html = build_gu_index_html()
    with open(os.path.join(GU_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"\n{count}개 구 페이지 생성, {skip}개 스킵 (단지 3개 미만)")
    print(f"출력: {GU_DIR}")


if __name__ == "__main__":
    main()
