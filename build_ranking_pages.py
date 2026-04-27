#!/usr/bin/env python3
"""
build_ranking_pages.py — 랭킹 정적 HTML 페이지 생성 (SEO)

Supabase danji_pages → ranking/[지역]-[타입].html
서울/인천/경기/전체 × 매매가/㎡당가격/전세가율↑/전세가율↓ = 16페이지
+ ranking/index.html (기본 진입점)

Usage:
  python build_ranking_pages.py
"""

import os, sys, json, time, html as html_mod
from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))
from urllib.parse import quote as url_quote
import requests
from slug_utils import make_danji_slug, detect_region as slug_detect_region

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
RANK_DIR = os.path.join(BASE_DIR, "ranking")
BUILD_TIME = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

REGION_LABELS = {
    "all": "전체",
    "seoul": "서울", "incheon": "인천", "gyeonggi": "경기",
    "busan": "부산", "daegu": "대구", "gwangju": "광주", "daejeon": "대전", "ulsan": "울산",
    "chungbuk": "충북", "chungnam": "충남",
    "jeonbuk": "전북", "jeonnam": "전남",
    "gyeongbuk": "경북", "gyeongnam": "경남",
    "gangwon": "강원", "jeju": "제주", "sejong": "세종",
}
# slug_utils.detect_region() 반환 라벨 → region_key
REGION_LABEL_TO_KEY = {
    "서울": "seoul", "인천": "incheon", "경기": "gyeonggi",
    "부산": "busan", "대구": "daegu", "광주": "gwangju",
    "대전": "daejeon", "울산": "ulsan",
    "충북": "chungbuk", "충남": "chungnam",
    "전북": "jeonbuk", "전남": "jeonnam",
    "경북": "gyeongbuk", "경남": "gyeongnam",
    "강원": "gangwon", "제주": "jeju", "세종": "sejong",
}
TYPE_LABELS = {"price": "매매가", "sqm": "㎡당 가격", "jeonse": "전세가율 높은", "jeonse_low": "전세가율 낮은"}


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
                          "jeonse_rate,total_units,build_year,lat,lng,pyeongs_map",
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


def process_data(all_danji):
    """전체 데이터를 랭킹용으로 가공"""
    result = []
    for d in all_danji:
        if d.get("id", "").startswith(("offi-", "apt-")):
            continue
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []
        price, area = None, None
        for c in cats:
            t = rt.get(c)
            if t and t.get("price") and t["price"] > (price or 0):
                price = t["price"]
                area = c
        if not price:
            continue

        area_num = float(area) if area and area.replace(".", "").isdigit() else 0
        loc = d.get("location") or ""

        # address 기반 지역 판정 (광역시 구 이름 충돌 방지)
        region_label = slug_detect_region(d.get("address", ""))
        region_key = REGION_LABEL_TO_KEY.get(region_label, "all")

        # ㎡당 가격: 공급면적(supply) 우선 — 단지 페이지·gu 페이지와 일관
        pm_entry = (d.get("pyeongs_map") or {}).get(area) or {} if area else {}
        supply = pm_entry.get("supply")
        sqm_price = 0
        supply_area = None
        if supply and float(supply) > 0:
            supply_area = float(supply)
            sqm_price = round(price / supply_area)
        result.append({
            "id": d["id"], "name": d["complex_name"],
            "location": loc, "address": d.get("address", ""),
            "region": region_key, "price": price, "area": area,
            "area_num": area_num,
            "supply_area": supply_area,
            "sqm_price": sqm_price,
            "jr": d.get("jeonse_rate"), "build_year": d.get("build_year"),
            "units": d.get("total_units"),
            "lat": d.get("lat"), "lng": d.get("lng"),
        })
    return result


def build_ranking_html(region, rank_type, data):
    """랭킹 페이지 HTML 생성 — D 디자인 (모바일 다크 + PC 라이트)"""
    area_label = REGION_LABELS.get(region, "전체")
    type_label = TYPE_LABELS.get(rank_type, "매매가")
    slug = f"{region}-{rank_type}"
    canonical = f"https://hwik.kr/ranking/{slug}.html"
    today = datetime.now(KST).strftime("%Y-%m-%d")

    # 필터
    if region != "all":
        filtered = [d for d in data if d["region"] == region]
    else:
        filtered = data

    # 정렬
    if rank_type == "price":
        sorted_data = sorted(filtered, key=lambda x: x["price"], reverse=True)
    elif rank_type == "sqm":
        sorted_data = sorted([d for d in filtered if d["sqm_price"] > 0], key=lambda x: x["sqm_price"], reverse=True)
    elif rank_type == "jeonse":
        sorted_data = sorted([d for d in filtered if d.get("jr") and d["jr"] > 0], key=lambda x: x["jr"], reverse=True)
    elif rank_type == "jeonse_low":
        sorted_data = sorted([d for d in filtered if d.get("jr") and d["jr"] > 0], key=lambda x: x["jr"])
    else:
        sorted_data = sorted(filtered, key=lambda x: x["price"], reverse=True)

    top50 = sorted_data[:50]

    # 자연어 섹션 제목 + 단위 라벨
    if rank_type == "price":
        section_q = f"{area_label}에서 가장 비싼 아파트는?"
        unit_label = ""
        rank_label = "매매가 1위"
    elif rank_type == "sqm":
        section_q = f"{area_label}에서 ㎡당 가격이 가장 비싼 아파트는?"
        unit_label = "/㎡ 공급면적 기준"
        rank_label = "㎡당 1위"
    elif rank_type == "jeonse":
        section_q = f"{area_label}에서 전세가율이 가장 높은 아파트는?"
        unit_label = "% 전세/매매 비율"
        rank_label = "전세가율 1위"
    else:  # jeonse_low
        section_q = f"{area_label}에서 전세가율이 가장 낮은 아파트는?"
        unit_label = "% 전세/매매 비율"
        rank_label = "전세가율 최하위"

    title = f"{area_label} 아파트 {type_label} TOP 50 · {today} | 휙"
    desc_bits = [f"{area_label} 아파트 {type_label} 순위 TOP 50."]
    if top50:
        if rank_type == "price":
            desc_bits.append(f"1위 {top50[0]['name']} {format_price(top50[0]['price'])}")
        elif rank_type == "sqm":
            desc_bits.append(f"1위 {top50[0]['name']} {format_price(top50[0]['sqm_price'])}/㎡(공급)")
        else:
            desc_bits.append(f"1위 {top50[0]['name']} {top50[0].get('jr',0)}%")
        if len(top50) >= 3:
            desc_bits.append(f"2위 {top50[1]['name']}, 3위 {top50[2]['name']}")
    desc_bits.append("국토교통부 실거래가 공개시스템 기반.")
    desc = " ".join(desc_bits)

    # 지역 평균 좌표 (AdministrativeArea geo)
    _lats = [d.get("lat") for d in filtered if d.get("lat")]
    _lngs = [d.get("lng") for d in filtered if d.get("lng")]
    geo_block = None
    if _lats and _lngs:
        geo_block = {
            "@type": "GeoCoordinates",
            "latitude": round(sum(_lats) / len(_lats), 6),
            "longitude": round(sum(_lngs) / len(_lngs), 6),
        }

    lines = []

    # 헤더
    lines.append(f'<header class="header"><div class="header-top">')
    lines.append(f'  <a class="logo" href="/" style="text-decoration:none;">휙</a>')
    lines.append(f'  <div><h1 class="header-name">{esc(area_label)} 아파트 {esc(type_label)} TOP 50</h1>')
    lines.append(f'  <div class="header-sub">{len(top50)}개 단지 · 마지막 업데이트 {today}</div></div>')
    lines.append(f'</div></header>')

    # 브레드크럼
    lines.append(f'<nav class="breadcrumb"><a href="/">휙</a><span>&gt;</span><a href="/ranking/">아파트 순위</a><span>&gt;</span>{esc(area_label)} {esc(type_label)}</nav>')

    # 지역 탭
    lines.append(f'<div class="tabs" style="border-bottom:2px solid var(--border);">')
    for rk, rl in REGION_LABELS.items():
        active = " active" if rk == region else ""
        lines.append(f'<a class="tab{active}" style="text-decoration:none;color:inherit;" href="/ranking/{rk}-{rank_type}.html">{esc(rl)}</a>')
    lines.append(f'</div>')

    # 타입 탭
    lines.append(f'<div class="tabs">')
    for tk, tl in TYPE_LABELS.items():
        active = " active" if tk == rank_type else ""
        short_label = tl.replace(" 높은", "↑").replace(" 낮은", "↓")
        lines.append(f'<a class="tab{active}" style="text-decoration:none;color:inherit;" href="/ranking/{region}-{tk}.html">{esc(short_label)}</a>')
    lines.append(f'</div>')

    # 슬림 인트로 (한 줄)
    if top50:
        intro_bits = [f"<b>{esc(area_label)}</b> 아파트 {esc(type_label)} TOP {len(top50)}"]
        if rank_type == "price":
            intro_bits.append(f"1위 {format_price(top50[0]['price'])}")
        elif rank_type == "sqm":
            intro_bits.append(f"1위 {format_price(top50[0]['sqm_price'])}/㎡")
        else:
            intro_bits.append(f"1위 {top50[0].get('jr',0)}%")
        lines.append(f'<p class="seo-text" style="font-size:13px;line-height:1.7;'
                     f'margin:14px 16px 4px;color:var(--sub);">{" · ".join(intro_bits)}</p>')

    # 1위 hero + 2~50위 컴팩트
    if top50:
        lines.append(f'<div class="section"><h2 class="section-title">{esc(section_q)}</h2>')
        d1 = top50[0]
        slug1 = make_danji_slug(d1["name"], d1["location"], d1["id"], d1["address"])

        # hero meta
        meta_bits1 = []
        if d1.get("location"):
            meta_bits1.append(esc(d1["location"]))
        if rank_type == "sqm" and d1.get("supply_area"):
            meta_bits1.append(f"공급 {d1['supply_area']:.1f}㎡")
        elif d1.get("area"):
            meta_bits1.append(f"전용 {d1['area']}㎡")
        if d1.get("build_year"):
            meta_bits1.append(f"{d1['build_year']}년 입주")
        if d1.get("units"):
            try:
                meta_bits1.append(f"{int(d1['units']):,}세대")
            except Exception:
                pass
        if rank_type in ("jeonse", "jeonse_low"):
            meta_bits1.append(f"매매 {format_price(d1['price'])}")
        meta1 = " · ".join(meta_bits1)

        # hero price
        if rank_type == "price":
            hero_price = format_price(d1["price"])
            hero_label = "최고가 거래"
        elif rank_type == "sqm":
            hero_price = format_price(d1["sqm_price"])
            hero_label = unit_label
        else:
            hero_price = f"{d1.get('jr', 0)}%"
            hero_label = unit_label

        t1 = f'{esc(d1["name"])} 실거래가 시세 · {esc(area_label)} {esc(type_label)} 1위'
        lines.append(
            f'<a class="danji-hero" title="{t1}" style="text-decoration:none;display:block;" '
            f'href="/danji/{url_quote(slug1, safe="-")}.html">'
            f'<div class="hero-left">'
            f'<span class="rank-badge">{esc(rank_label)}</span>'
            f'<div class="hero-name">{esc(d1["name"])}</div>'
            f'<div class="hero-meta">{meta1}</div>'
            f'</div>'
            f'<div class="hero-right">'
            f'<div class="hero-price">{hero_price}</div>'
            f'<div class="hero-price-label">{esc(hero_label)}</div>'
            f'</div></a>'
        )

        if len(top50) > 1:
            lines.append(f'<div style="margin-top:6px;">')
            for i, d in enumerate(top50[1:], start=2):
                slug_d = make_danji_slug(d["name"], d["location"], d["id"], d["address"])
                cm_bits = []
                if d.get("location"):
                    cm_bits.append(esc(d["location"]))
                if rank_type == "sqm" and d.get("supply_area"):
                    cm_bits.append(f"공급 {d['supply_area']:.1f}㎡")
                elif d.get("area"):
                    cm_bits.append(f"전용 {d['area']}㎡")
                if d.get("build_year"):
                    cm_bits.append(f"{d['build_year']}년")
                cm_meta = " · ".join(cm_bits)
                if rank_type == "price":
                    main_price = format_price(d["price"])
                    suffix = ""
                elif rank_type == "sqm":
                    main_price = format_price(d["sqm_price"])
                    suffix = '<span style="font-size:10px;color:var(--muted);font-weight:500;"> /㎡</span>'
                else:
                    main_price = f'{d.get("jr", 0)}%'
                    suffix = ""
                _t = f'{esc(d["name"])} 실거래가 시세 · {esc(area_label)} {esc(type_label)} {i}위'
                lines.append(
                    f'<a class="danji-compact" title="{_t}" '
                    f'style="text-decoration:none;color:inherit;" '
                    f'href="/danji/{url_quote(slug_d, safe="-")}.html">'
                    f'<div style="display:flex;align-items:center;flex:1;min-width:0;">'
                    f'<span class="danji-compact-rank">{i}</span>'
                    f'<div style="min-width:0;">'
                    f'<div class="danji-compact-name">{esc(d["name"])}</div>'
                    f'<div class="danji-compact-meta">{cm_meta}</div>'
                    f'</div></div>'
                    f'<div class="danji-compact-price">{main_price}{suffix}</div>'
                    f'</a>'
                )
            lines.append(f'</div>')
        lines.append(f'</div>')
        lines.append(f'<div class="divider"></div>')

    # FAQ — 핵심 4-5개
    faq = []
    if top50:
        if rank_type == "price":
            faq.append((f"{area_label}에서 가장 비싼 아파트는?",
                        f"{top50[0]['name']} ({top50[0]['location']})이 {format_price(top50[0]['price'])}으로 1위입니다."))
            if len(top50) >= 2:
                faq.append((f"{area_label} 매매가 2위는?",
                            f"{top50[1]['name']} ({top50[1]['location']}) {format_price(top50[1]['price'])}."))
            if len(top50) >= 3:
                faq.append((f"{area_label} 매매가 3위는?",
                            f"{top50[2]['name']} ({top50[2]['location']}) {format_price(top50[2]['price'])}."))
        elif rank_type == "sqm":
            faq.append((f"{area_label} ㎡당 가격 1위는?",
                        f"{top50[0]['name']}이 공급면적 기준 {format_price(top50[0]['sqm_price'])}/㎡으로 1위입니다."))
            if len(top50) >= 2:
                faq.append((f"{area_label} ㎡당 가격 2위는?",
                            f"{top50[1]['name']} ({format_price(top50[1]['sqm_price'])}/㎡)."))
        else:
            direction = "높은" if rank_type == "jeonse" else "낮은"
            faq.append((f"{area_label} 전세가율이 가장 {direction} 아파트는?",
                        f"{top50[0]['name']}이 {top50[0].get('jr',0)}%로 1위입니다."))
            if len(top50) >= 2:
                faq.append((f"{area_label} 전세가율 2위는?",
                            f"{top50[1]['name']} ({top50[1].get('jr',0)}%)."))
        faq.append((f"이 순위는 어떤 데이터를 기반으로 하나요?",
                    f"국토교통부 실거래가 공개시스템(rt.molit.go.kr) 데이터를 매일 자동 수집한 결과입니다."))

    if faq:
        lines.append(f'<div class="faq-section"><h2 class="section-title">자주 묻는 질문</h2>')
        for q, a in faq:
            lines.append(f'<div class="faq-item">')
            lines.append(f'<div class="faq-q">{esc(q)}</div>')
            lines.append(f'<div class="faq-a">{esc(a)}</div>')
            lines.append(f'</div>')
        lines.append(f'</div><div class="divider"></div>')

    # SEO + 데이터 안내
    seo_text = f"{esc(area_label)} 아파트 {esc(type_label)} TOP {len(top50)}."
    if top50:
        if rank_type == "price":
            seo_text += f" 1위 {esc(top50[0]['name'])}({format_price(top50[0]['price'])})."
        elif rank_type == "sqm":
            seo_text += f" 1위 {esc(top50[0]['name'])}({format_price(top50[0]['sqm_price'])}/㎡)."
        else:
            seo_text += f" 1위 {esc(top50[0]['name'])}({top50[0].get('jr',0)}%)."
    seo_text += " 국토교통부 실거래가 공개시스템 기반."

    lines.append(f'<div class="seo-section" style="padding:16px;">')
    lines.append(f'<div class="seo-text">{seo_text}</div>')
    lines.append(f'<details class="data-notice" style="margin-top:14px;font-size:12px;color:var(--sub);">')
    lines.append(f'<summary style="cursor:pointer;">데이터 안내</summary>')
    lines.append(f'<div style="margin-top:6px;line-height:1.8;">')
    lines.append(f'<b>실거래가</b>: 국토교통부 실거래가 공개시스템 (<a href="https://rt.molit.go.kr/" target="_blank" rel="noopener nofollow">rt.molit.go.kr</a>) · 매일 자동 수집<br>')
    lines.append(f'<b>건축정보</b>: 국토교통부 건축물대장<br>')
    lines.append(f'<b>㎡당 가격</b>: 공급면적 기준 (단지 페이지와 동일)<br>')
    lines.append(f'전세가율 = 전세가 ÷ 매매가 × 100<br>')
    lines.append(f'거래 취소·정정 건은 반영이 지연될 수 있습니다')
    lines.append(f'</div></details>')
    lines.append(f'<div class="seo-source" style="margin-top:8px;font-size:11px;color:var(--muted);">'
                 f'실거래가 출처: 국토교통부 · 최종 데이터 확인: <time datetime="{today}">{today}</time></div>')
    lines.append(f'</div>')

    body = "\n".join(lines)

    # ── JSON-LD 강화 ──
    place_block = {
        "@type": "AdministrativeArea",
        "name": area_label if region != "all" else "대한민국",
        "containedInPlace": {"@type": "Country", "name": "대한민국"},
    }
    if geo_block:
        place_block["geo"] = geo_block

    jsonld_org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": "https://hwik.kr/#org",
        "name": "휙 (HWIK)",
        "url": "https://hwik.kr",
        "logo": {"@type": "ImageObject", "url": "https://hwik.kr/og-image.png", "width": 1200, "height": 630},
        "sameAs": ["https://hwik.kr"],
    }
    item_list = [
        {"@type": "ListItem", "position": i + 1, "name": d["name"],
         "url": f"https://hwik.kr/danji/{url_quote(make_danji_slug(d['name'], d['location'], d['id'], d['address']), safe='-')}.html"}
        for i, d in enumerate(top50)
    ]
    jsonld_collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title.split(" | ")[0],
        "description": desc,
        "url": canonical,
        "inLanguage": "ko-KR",
        "datePublished": "2026-01-01",
        "dateModified": today,
        "isPartOf": {"@type": "WebSite", "name": "휙", "url": "https://hwik.kr"},
        "publisher": {"@id": "https://hwik.kr/#org"},
        "about": place_block,
        "mainEntity": {
            "@type": "ItemList",
            "name": f"{area_label} 아파트 {type_label} 순위",
            "numberOfItems": len(item_list),
            "itemListElement": item_list,
        },
    }
    jsonld_place = dict(place_block, **{"@context": "https://schema.org"})
    jsonld_faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq
        ],
    } if faq else None
    jsonld_breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
            {"@type": "ListItem", "position": 2, "name": "아파트 순위", "item": "https://hwik.kr/ranking/"},
            {"@type": "ListItem", "position": 3, "name": f"{area_label} {type_label}"},
        ],
    }

    graph = [jsonld_org, jsonld_collection, jsonld_place, jsonld_breadcrumb]
    if jsonld_faq:
        graph.append(jsonld_faq)
    jsonld_combined = {"@context": "https://schema.org", "@graph": graph}

    return wrap_html(title, desc, canonical, body, json.dumps(jsonld_combined, ensure_ascii=False),
                     modified_iso=today)


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
.tabs {{ display:flex; border-bottom:1px solid var(--border); overflow-x:auto; }}
.tabs::-webkit-scrollbar {{ display:none; }}
.tab {{ flex-shrink:0; padding:12px 16px; text-align:center; font-size:13px; color:var(--sub); cursor:pointer; border-bottom:2px solid transparent; transition:all .2s; white-space:nowrap; text-decoration:none; }}
.tab.active {{ color:var(--text); font-weight:500; border-bottom-color:var(--yellow); }}
/* 1위 hero — 모바일 다크 (세로) */
.danji-hero {{ display:block; position:relative; padding:18px 16px; background:linear-gradient(135deg, #2a2820 0%, #2a2515 100%); border:1px solid #3a3525; border-left:4px solid var(--yellow); border-radius:14px; margin-bottom:8px; cursor:pointer; transition:all .15s; }}
.danji-hero:active {{ transform:scale(0.99); }}
.danji-hero .hero-left {{ display:block; }}
.danji-hero .hero-right {{ display:block; margin-top:10px; }}
.danji-hero .rank-badge {{ display:inline-block; padding:3px 9px; background:var(--yellow); color:#0a0a12; border-radius:6px; font-size:10.5px; font-weight:800; margin-bottom:8px; letter-spacing:0.02em; }}
.danji-hero .hero-name {{ font-size:17px; font-weight:700; color:var(--text); letter-spacing:-0.02em; }}
.danji-hero .hero-meta {{ font-size:12px; color:var(--sub); margin-top:6px; line-height:1.6; }}
.danji-hero .hero-price {{ font-size:22px; font-weight:800; color:var(--yellow); letter-spacing:-0.02em; }}
.danji-hero .hero-price-label {{ font-size:11px; color:var(--muted); font-weight:500; margin-top:2px; }}
/* 2~ 컴팩트 */
.danji-compact {{ display:flex; justify-content:space-between; align-items:center; padding:11px 13px; background:var(--card); border-radius:10px; cursor:pointer; transition:all .15s; }}
.danji-compact:active {{ transform:scale(0.98); }}
.danji-compact-rank {{ display:inline-block; min-width:18px; font-size:12px; font-weight:700; color:var(--muted); margin-right:8px; }}
.danji-compact-name {{ font-size:13px; font-weight:600; color:var(--text); }}
.danji-compact-meta {{ font-size:11px; color:var(--sub); margin-top:2px; }}
.danji-compact-price {{ font-size:14px; font-weight:700; text-align:right; color:var(--text); }}
/* 데이터 안내 + 푸터 */
.data-notice summary {{ font-weight:600; color:var(--text); }}
.data-notice a {{ color:var(--yellow); text-decoration:none; }}
.hwik-footer {{ max-width:600px; margin:24px auto 40px; padding:24px 16px 0; border-top:1px solid var(--border, #2a2a3e); text-align:center; font-size:11.5px; color:var(--sub); line-height:1.7; }}
.hwik-footer-links {{ margin-bottom:8px; }}
.hwik-footer-links a {{ color:var(--sub); text-decoration:none; margin:0 8px; }}
.hwik-footer-copy a {{ color:var(--muted); text-decoration:none; }}

/* ── PC ≥768px D 디자인 라이트 ── */
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
    display: flex !important; flex-wrap: wrap !important; gap: 4px !important;
  }}
  .breadcrumb a {{ color: #64748b !important; text-decoration: none !important; }}
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
  .header .header-name {{ font-size: 22px !important; font-weight: 700 !important; color: #4338ca !important; letter-spacing: -0.03em !important; line-height: 1.25 !important; margin: 0 !important; }}
  .header .header-sub {{ font-size: 12.5px !important; color: #64748b !important; margin-top: 2px !important; }}
  .divider {{ display: none !important; }}
  .section {{ padding: 20px 14px !important; }}
  .section-title {{ font-size: 16px !important; font-weight: 700 !important; color: #0f172a !important; letter-spacing: -0.025em !important; margin: 0 0 14px !important; }}
  /* 탭 */
  .tabs {{ background: #fff !important; padding: 0 14px !important; border-bottom-color: #eef0f4 !important; }}
  .tab {{
    color: #475569 !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    padding: 12px 16px !important;
    border-bottom: 2px solid transparent !important;
    transition: all 0.15s ease !important;
    border-radius: 8px 8px 0 0 !important;
    letter-spacing: -0.01em !important;
  }}
  .tab.active {{
    color: #4338ca !important;
    font-weight: 700 !important;
    border-bottom-color: #facc15 !important;
  }}
  .tab:hover:not(.active) {{
    color: #4338ca !important;
    font-weight: 600 !important;
    background: #fefce8 !important;
    border-bottom-color: #fde68a !important;
  }}
  /* 1위 hero — PC (좌우 flex) */
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
  .danji-hero .hero-name {{ font-size: 18px !important; font-weight: 800 !important; color: #1e293b !important; letter-spacing: -0.025em !important; }}
  .danji-hero .hero-meta {{ color: #78716c !important; font-size: 12.5px !important; line-height: 1.7 !important; margin-top: 4px !important; }}
  .danji-hero .hero-price {{ color: #ca8a04 !important; font-size: 26px !important; font-weight: 900 !important; letter-spacing: -0.025em !important; margin: 0 !important; }}
  .danji-hero .hero-price-label {{ color: #a8a29e !important; font-weight: 600 !important; font-size: 11px !important; margin-top: 4px !important; }}
  /* 2~ compact PC */
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
  .danji-compact-rank {{ color: #cbd5e1 !important; font-weight: 800 !important; }}
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
  /* SEO */
  .seo-section {{ background: #fafafa !important; padding: 16px 14px !important; }}
  .seo-text {{ color: #475569 !important; font-size: 13px !important; line-height: 1.85 !important; }}
  .seo-source {{ color: #94a3b8 !important; font-size: 11px !important; }}
  .data-notice {{ color: #64748b !important; font-size: 12px !important; }}
  .data-notice summary {{ cursor: pointer !important; font-weight: 700 !important; color: #1e293b !important; padding: 4px 0 !important; }}
  .data-notice a {{ color: #4338ca !important; text-decoration: none !important; }}
  .data-notice a:hover {{ text-decoration: underline !important; }}
  /* 푸터 */
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
  .hwik-footer-links a {{ color: #6b7280 !important; }}
  .hwik-footer-links a:hover {{ color: #4338ca !important; }}
  .hwik-footer-copy {{ color: #9ca3af !important; }}
  .hwik-footer-copy a {{ color: #9ca3af !important; }}
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


def build_hub_html():
    """/ranking/ 허브 페이지 — self-canonical, 9개 지역 × 4개 타입 전체 링크.
    중복 콘텐츠 방지를 위해 seoul-price.html 과 다른 본문/메타 사용."""
    title = "전국 아파트 순위 - 서울·경기·부산·충청·경상·전라·강원·제주 | 휙"
    desc = "서울·인천·경기·부산·대구·광주·대전·울산·충북·충남·전북·전남·경북·경남·강원·제주·세종 아파트 매매가·㎡당·전세가율 순위 TOP 50. 국토교통부 실거래가 기반."
    canonical = "https://hwik.kr/ranking/"

    # 본문
    lines = []
    lines.append('<header class="header"><div class="header-top">')
    lines.append('  <a class="logo" href="/" style="text-decoration:none;">휙</a>')
    lines.append('  <div><div class="header-name">전국 아파트 순위</div><div class="header-sub">서울·경기·인천·부산·충청·경상·전라·강원·제주</div></div>')
    lines.append('</div></header>')
    lines.append('<nav class="breadcrumb"><a href="/">휙</a><span>&gt;</span>순위</nav>')

    # 스토리텔링용 H2 섹션 (얇은 콘텐츠 방지)
    lines.append('<div class="section"><h2 style="font-size:16px;margin:8px 0 12px;">무엇을 볼 수 있나요?</h2>')
    lines.append('<p style="font-size:13px;color:var(--sub);line-height:1.7;">국토교통부 실거래가 공개시스템을 기반으로 전국 17개 시도 아파트 매매가·㎡당 가격·전세가율 순위를 지역별로 확인할 수 있습니다. 각 지역별로 최근 실거래가 있는 아파트만 집계하며, 매일 새벽 자동 갱신됩니다.</p>')
    lines.append('</div>')

    # 지역 × 타입 링크 그리드
    region_order = [
        "all", "seoul", "incheon", "gyeonggi",
        "busan", "daegu", "gwangju", "daejeon", "ulsan",
        "chungbuk", "chungnam", "jeonbuk", "jeonnam",
        "gyeongbuk", "gyeongnam", "gangwon", "jeju", "sejong",
    ]
    type_order = [("price", "매매가"), ("sqm", "㎡당 가격"), ("jeonse", "전세가율 높은"), ("jeonse_low", "전세가율 낮은")]

    for region in region_order:
        if region not in REGION_LABELS:
            continue
        label = REGION_LABELS[region]
        lines.append(f'<div class="section"><h2 style="font-size:15px;margin:16px 0 10px;border-left:3px solid var(--yellow);padding-left:8px;">{esc(label)} 아파트 순위</h2>')
        lines.append('<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">')
        for tk, tl in type_order:
            href = f"/ranking/{region}-{tk}"
            desc_short = {"price": "매매가 높은 순", "sqm": "㎡당 가격 높은 순",
                          "jeonse": "전세가율 높은 순", "jeonse_low": "전세가율 낮은 순"}[tk]
            lines.append(
                f'<a href="{href}" style="display:block;padding:12px;background:var(--card);border-radius:var(--radius);text-decoration:none;color:inherit;border-left:3px solid var(--yellow);">'
                f'<div style="font-size:13px;font-weight:600;">{esc(tl)} TOP 50</div>'
                f'<div style="font-size:11px;color:var(--sub);margin-top:3px;">{esc(label)} {desc_short}</div>'
                f'</a>'
            )
        lines.append('</div></div>')

    # 하단 네비
    lines.append('<div style="margin-top:32px;padding:20px;background:var(--card);border-radius:var(--radius);text-align:center;">')
    lines.append('  <a href="/gu/" style="display:inline-block;margin:0 8px;color:var(--yellow);font-weight:600;text-decoration:none;">구별 시세 →</a>')
    lines.append('  <a href="/dong/" style="display:inline-block;margin:0 8px;color:var(--yellow);font-weight:600;text-decoration:none;">동별 시세 →</a>')
    lines.append('</div>')

    _today = datetime.now(KST).strftime("%Y-%m-%d")
    lines.append(f'<div style="margin-top:20px;padding:12px;font-size:11px;color:var(--muted);text-align:center;">출처: 국토교통부 실거래가 공개시스템 · 마지막 갱신 {_today}</div>')

    body = "\n".join(lines)

    # JSON-LD: BreadcrumbList + ItemList (지역 허브)
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
                {"@type": "ListItem", "position": 2, "name": "순위"},
            ]},
            {"@type": "ItemList", "name": "전국 아파트 순위",
             "itemListElement": [
                 {"@type": "ListItem", "position": i + 1,
                  "name": f"{REGION_LABELS[r]} 아파트 순위",
                  "url": f"https://hwik.kr/ranking/{r}-price.html"}
                 for i, r in enumerate([x for x in region_order if x in REGION_LABELS])
             ]}
        ]
    }
    return wrap_html(title, desc, canonical, body, json.dumps(jsonld, ensure_ascii=False))


# ── 메인 ──────────────────────────────────────────────────
def main():
    os.makedirs(RANK_DIR, exist_ok=True)

    ONE_RANK_SLUG = os.environ.get("ONE_RANK_SLUG", "").strip()
    if ONE_RANK_SLUG:
        print(f"[ONE_RANK_SLUG={ONE_RANK_SLUG}] 단일 랭킹만 빌드 — 기존 파일 유지, 인덱스 미갱신")

    print("Supabase에서 단지 데이터 조회 중...")
    all_danji = fetch_all_danji()
    print(f"  {len(all_danji)}개 단지 로드 완료")

    data = process_data(all_danji)
    print(f"  {len(data)}개 단지 가격 데이터 가공 완료")

    count = 0
    for region in REGION_LABELS:
        for rank_type in TYPE_LABELS:
            slug = f"{region}-{rank_type}"
            if ONE_RANK_SLUG and slug != ONE_RANK_SLUG:
                continue
            html = build_ranking_html(region, rank_type, data)
            fpath = os.path.join(RANK_DIR, f"{slug}.html")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(html)
            count += 1

    # index.html → 자가 정규화 허브 (ONE_RANK_SLUG 모드는 미갱신)
    if not ONE_RANK_SLUG:
        index_html = build_hub_html()
        with open(os.path.join(RANK_DIR, "index.html"), "w", encoding="utf-8") as f:
            f.write(index_html)

    print(f"\n{count}개 랭킹 페이지 생성")
    print(f"출력: {RANK_DIR}")


if __name__ == "__main__":
    main()
