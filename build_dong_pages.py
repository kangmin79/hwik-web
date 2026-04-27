#!/usr/bin/env python3
"""
build_dong_pages.py — 동별 정적 HTML 페이지 생성 (SEO)

Supabase danji_pages → dong/[구-동].html (정적 SEO 콘텐츠)
거래 있는 단지 3개 이상인 동만 생성 (thin content 방지)

Usage:
  python build_dong_pages.py
"""

import os, sys, json, re, time, hashlib, html as html_mod
from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))
import requests
from collections import defaultdict
from urllib.parse import quote as url_quote
from slug_utils import (
    REGION_MAP, METRO_CITIES, clean as _clean,
    detect_region, make_danji_slug, make_dong_slug,
    extract_gu_from_address, gu_url_slug,
)
from regions import REGION_LABEL_TO_KEY as _RLTK
_GU_PAGE_REGIONS = set(_RLTK.keys())  # 전국 17개 광역시도

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
SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DONG_DIR = os.path.join(BASE_DIR, "dong")

MIN_DANJI_WITH_TRADE = 3  # thin content 방지

BUILD_TIME = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


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


def walk_min(m):
    if not m:
        return ""
    try:
        return f"{round(float(m) / 67)}분"
    except (ValueError, TypeError):
        return ""


def clean_line(line):
    """지하철 노선명 정리: '수도권 경량도시철도 신림선' → '신림선'"""
    if not line:
        return ""
    s = re.sub(r'\s+', ' ', str(line)).strip()
    s = re.sub(r'^(수도권|서울|부산|대구|대전|광주|인천)?\s*(경량)?도시철도\s*', '', s).strip()
    s = re.sub(r'^수도권\s*광역철도\s*', '', s).strip()
    s = s.replace('인천국제공항선', '공항철도')
    s = s.replace('부산김해경전철', '김해경전철')
    return s or str(line).strip()


def josa(word, particle_pair="은/는"):
    """한글 받침 유무에 따라 올바른 조사 반환."""
    a, b = particle_pair.split("/")
    if not word:
        return b
    last = word.rstrip()[-1]
    if '가' <= last <= '힣':
        return a if (ord(last) - 0xAC00) % 28 != 0 else b
    return b


# REGION_MAP, METRO_CITIES, _clean, detect_region, make_danji_slug, make_dong_slug → slug_utils.py에서 import



# ── Supabase 조회 ─────────────────────────────────────────
# limit 500 → 200 축소 사유: 한 페이지 응답이 9MB 넘으면 프록시에서 JSON 잘림 사고 발생
PAGE_LIMIT = 200


def _get_page(url, params, max_attempts=3):
    """Supabase GET + JSON 파싱 + 재시도(2s, 4s, 6s). 최종 실패 시 raise."""
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
        raw = _get_page(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            {
                "select": "id,complex_name,location,address,build_year,total_units,"
                          "categories,recent_trade,all_time_high,jeonse_rate,"
                          "nearby_subway,nearby_school,lat,lng,price_history,updated_at,builder",
                "id": "not.like.offi-*",
                "order": "id",
                "offset": offset,
                "limit": PAGE_LIMIT,
            },
        )
        if not raw:
            break
        # apt- 구버전 단지 제외 (필터 전 길이로 종료 판정해야 조기 종료 방지)
        data = [d for d in raw if not d.get("id", "").startswith("apt-")]
        all_data.extend(data)
        offset += PAGE_LIMIT
        if len(raw) < PAGE_LIMIT:
            break
        time.sleep(0.2)
    return all_data


# ── 단지의 대표 거래 추출 ─────────────────────────────────
def safe_int(s, default=999):
    try:
        return int(s)
    except (ValueError, TypeError):
        return default


def best_trade(d):
    """84㎡에 가장 가까운 거래 있는 면적의 최근 거래 반환"""
    cats = d.get("categories") or []
    rt = d.get("recent_trade") or {}
    best, best_diff = None, 999
    for c in cats:
        if rt.get(c) and (rt[c].get("price") or 0) > 0:
            diff = abs(safe_int(c) - 84)
            if diff < best_diff:
                best_diff = diff
                best = c
    if not best:
        return None, None
    return best, rt[best]


def has_trade_data(d):
    """거래 데이터가 있는지"""
    rt = d.get("recent_trade") or {}
    cats = d.get("categories") or []
    return any(rt.get(c) and (rt[c].get("price") or 0) > 0 for c in cats)


# ── 동별 HTML 생성 ────────────────────────────────────────
def build_dong_html(gu, dong, danji_list, region, same_gu_dongs, dong_slug_map=None,
                     adjacent_dongs=None):
    """동 페이지 정적 HTML 생성 (D 디자인: 모바일 다크 + PC 라이트, SEO 강화)"""
    # 첫 번째 non-empty address 선택
    first_addr = ""
    for _d in danji_list:
        _a = _d.get("address", "") or ""
        if _a:
            first_addr = _a
            break
    slug = make_dong_slug(gu, dong, first_addr)
    canonical = f"https://hwik.kr/dong/{url_quote(slug, safe='-')}.html"

    # /gu/ 페이지 존재 여부: 전국 17개 광역시도
    has_gu_page = region in _GU_PAGE_REGIONS
    gu_page_slug = gu_url_slug(region, gu) if has_gu_page else ""

    # 거래 있는 단지만 필터 + 가격순 정렬
    tradeable = []
    for d in danji_list:
        area, trade = best_trade(d)
        if area and trade:
            tradeable.append({**d, "_best_area": area, "_best_trade": trade})
    tradeable.sort(key=lambda x: x["_best_trade"].get("price", 0), reverse=True)

    if len(tradeable) < MIN_DANJI_WITH_TRADE:
        return None

    # 지하철/학교: 단지 3개+ 등장 & 도보 10분(800m) 이내만
    from collections import Counter
    MAX_WALK_M = 800
    MIN_DANJI_COUNT = 3

    subway_count = Counter()
    subway_best = {}
    for d in danji_list:
        seen_in_danji = set()
        for s in (d.get("nearby_subway") or []):
            name = s.get("name", "")
            dist = s.get("distance") or 9999
            if not name or dist > MAX_WALK_M or name in seen_in_danji:
                continue
            seen_in_danji.add(name)
            subway_count[name] += 1
            if name not in subway_best or dist < subway_best[name].get("distance", 9999):
                subway_best[name] = s
    subways = sorted(
        [subway_best[n] for n, c in subway_count.items() if c >= MIN_DANJI_COUNT],
        key=lambda s: s.get("distance", 9999)
    )

    school_count = Counter()
    school_best = {}
    for d in danji_list:
        seen_in_danji = set()
        for s in (d.get("nearby_school") or []):
            name = s.get("name", "")
            dist = s.get("distance") or 9999
            if not name or dist > MAX_WALK_M or name in seen_in_danji:
                continue
            seen_in_danji.add(name)
            school_count[name] += 1
            if name not in school_best or dist < school_best[name].get("distance", 9999):
                school_best[name] = s
    schools = sorted(
        [school_best[n] for n, c in school_count.items() if c >= MIN_DANJI_COUNT],
        key=lambda s: s.get("distance", 9999)
    )

    # 가장 최근 거래 단지 (FAQ용)
    most_recent = max(tradeable, key=lambda x: x["_best_trade"].get("date", ""), default=None)

    today = datetime.now(KST).strftime('%Y-%m-%d')
    _prices = [x["_best_trade"].get("price", 0) for x in tradeable if x.get("_best_trade")]
    _valid = [p for p in _prices if p > 0]
    _price_range = f"{format_price(min(_valid))}~{format_price(max(_valid))}" if len(_valid) >= 2 else ""
    _recent_name = most_recent.get("complex_name", "") if most_recent else ""
    _recent_date = most_recent["_best_trade"].get("date", "") if most_recent else ""

    # 동 평균 좌표 (AdministrativeArea geo)
    _lats = [d.get("lat") for d in danji_list if d.get("lat")]
    _lngs = [d.get("lng") for d in danji_list if d.get("lng")]
    geo_block = None
    if _lats and _lngs:
        geo_block = {
            "@type": "GeoCoordinates",
            "latitude": round(sum(_lats) / len(_lats), 6),
            "longitude": round(sum(_lngs) / len(_lngs), 6),
        }

    # 풍부 description (~140자)
    title = f"{region} {gu} {dong} 아파트 실거래가 시세 · {len(tradeable)}개 단지 | 휙"
    _focus_subway = (subways[0].get("name", "") if subways else "")
    desc_bits = [
        f"{region} {gu} {dong}의 아파트 {len(tradeable)}개 단지 매매·전세·월세 실거래가와 시세를 한 번에 확인하세요.",
    ]
    if _price_range:
        desc_bits.append(f"가격 {_price_range}")
    if most_expensive_name := (most_expensive.get('complex_name') if (most_expensive := tradeable[0]) else ''):
        desc_bits.append(f"최고가 {most_expensive_name}")
    if _focus_subway:
        desc_bits.append(f"인근 {_focus_subway}")
    desc_bits.append("국토교통부 실거래가 공개시스템 기반.")
    desc = ", ".join(desc_bits[:-1]) + ". " + desc_bits[-1]

    # ── 통계 변수 (이전 fallback 위치에서 미리 계산) ──
    most_expensive = tradeable[0] if tradeable else None
    cheapest = tradeable[-1] if len(tradeable) > 1 else None
    most_units = max(tradeable, key=lambda x: (x.get("total_units") or 0), default=None)
    newest = max(tradeable, key=lambda x: (x.get("build_year") or 0), default=None)
    oldest = min(tradeable, key=lambda x: (x.get("build_year") or 9999), default=None)
    region_link = "/gu/"

    # ── 본문 (D 디자인 — gu와 동일 패턴) ──
    lines = []

    # 헤더
    lines.append(f'<header class="header"><div class="header-top">')
    lines.append(f'  <a class="logo" href="/" style="text-decoration:none;">휙</a>')
    lines.append(f'  <div><h1 class="header-name">{esc(gu)} {esc(dong)} 아파트 시세</h1>')
    lines.append(f'  <div class="header-sub">{len(tradeable)}개 단지'
                 + (f" · 가격 {_price_range}" if _price_range else "")
                 + f' · 마지막 업데이트 {today}</div></div>')
    lines.append(f'</div></header>')

    # 브레드크럼
    lines.append(f'<nav class="breadcrumb">')
    lines.append(f'<a href="/">휙</a><span>&gt;</span>')
    if has_gu_page:
        lines.append(f'<a href="{region_link}">{esc(region)}</a><span>&gt;</span>')
        lines.append(f'<a href="/gu/{url_quote(gu_page_slug, safe="-")}.html">{esc(gu)}</a><span>&gt;</span>')
    else:
        if region:
            lines.append(f'<span>{esc(region)}</span><span>&gt;</span>')
        lines.append(f'<span>{esc(gu)}</span><span>&gt;</span>')
    lines.append(f'{esc(dong)}</nav>')

    # 슬림 인트로 (한 줄)
    intro_bits = [f"<b>{esc(dong)}</b> 아파트 {len(tradeable)}개 단지"]
    if _price_range:
        intro_bits.append(f"가격 {_price_range}")
    if subways:
        intro_bits.append(f"{esc(subways[0].get('name',''))} 도보권")
    intro_text = " · ".join(intro_bits)
    lines.append(f'<p class="seo-text" style="font-size:13px;line-height:1.7;'
                 f'margin:14px 16px 4px;color:var(--sub);">{intro_text}</p>')

    # 인프라 칩 (지하철/학교)
    if subways or schools:
        chip_html = []
        for s in subways[:4]:
            chip_html.append(
                f'<span class="info-chip info-chip-subway">'
                f'{esc(s.get("name",""))}'
                f'{(" " + esc(clean_line(s.get("line","")))) if s.get("line") else ""}'
                f' · 도보 {walk_min(s.get("distance"))}</span>'
            )
        for s in schools[:3]:
            chip_html.append(
                f'<span class="info-chip info-chip-school">'
                f'{esc(s.get("name",""))} · 도보 {walk_min(s.get("distance"))}</span>'
            )
        lines.append(f'<div class="info-chips">{" ".join(chip_html)}</div>')

    # (자연어 인용 단락 제거 — hero 카드와 정보 중복)

    # 단지 1위 hero
    lines.append(f'<div class="section">'
                 f'<h2 class="section-title">{esc(dong)}에서 가장 비싼 아파트는?</h2>')
    d1 = tradeable[0]
    slug1 = make_danji_slug(d1.get("complex_name",""), d1.get("location",""), d1.get("id",""), d1.get("address",""))
    area1 = d1["_best_area"]
    trade1 = d1["_best_trade"]
    price1 = format_price(trade1.get("price"))
    date1 = trade1.get("date", "")
    meta_bits1 = []
    if d1.get("location"):
        meta_bits1.append(esc(d1["location"]))
    meta_bits1.append(f"전용 {area1}㎡")
    if d1.get("build_year"):
        meta_bits1.append(f"{d1['build_year']}년 입주")
    if d1.get("total_units"):
        try:
            meta_bits1.append(f"{int(d1['total_units']):,}세대")
        except Exception:
            pass
    meta1 = " · ".join(meta_bits1)
    t1 = f'{esc(d1.get("complex_name",""))} 실거래가 · {esc(dong)} 매매가 1위'
    lines.append(
        f'<a class="danji-hero" title="{t1}" style="text-decoration:none;display:block;" '
        f'href="/danji/{url_quote(slug1, safe="-")}.html">'
        f'<div class="hero-left">'
        f'<span class="rank-badge">매매가 1위</span>'
        f'<div class="hero-name">{esc(d1.get("complex_name",""))}</div>'
        f'<div class="hero-meta">{meta1}</div>'
        f'</div>'
        f'<div class="hero-right">'
        f'<div class="hero-price">{price1}</div>'
        + (f'<div class="hero-price-label">최근 거래 <time datetime="{esc(date1)}">{esc(date1)}</time></div>' if date1 else '')
        + f'</div></a>'
    )

    # 2~ 컴팩트
    if len(tradeable) > 1:
        lines.append(f'<div style="margin-top:6px;">')
        for i, d in enumerate(tradeable[1:], start=2):
            slug_d = make_danji_slug(d.get("complex_name",""), d.get("location",""), d.get("id",""), d.get("address",""))
            area = d["_best_area"]
            trade = d["_best_trade"]
            price = format_price(trade.get("price"))
            cm_bits = []
            cm_bits.append(f"전용 {area}㎡")
            if d.get("build_year"):
                cm_bits.append(f"{d['build_year']}년")
            if d.get("total_units"):
                try:
                    cm_bits.append(f"{int(d['total_units']):,}세대")
                except Exception:
                    pass
            cm_meta = " · ".join(cm_bits)
            _t = f'{esc(d.get("complex_name",""))} 실거래가 · {esc(dong)} 아파트 {i}위'
            lines.append(
                f'<a class="danji-compact" title="{_t}" '
                f'style="text-decoration:none;color:inherit;" '
                f'href="/danji/{url_quote(slug_d, safe="-")}.html">'
                f'<div style="display:flex;align-items:center;flex:1;min-width:0;">'
                f'<span class="danji-compact-rank">{i}</span>'
                f'<div style="min-width:0;">'
                f'<div class="danji-compact-name">{esc(d.get("complex_name",""))}</div>'
                f'<div class="danji-compact-meta">{cm_meta}</div>'
                f'</div></div>'
                f'<div class="danji-compact-price">{price}</div>'
                f'</a>'
            )
        lines.append(f'</div>')
    lines.append(f'</div><div class="divider"></div>')

    # 통계 사전 계산
    from datetime import datetime as _dt
    _cy = _dt.now().year
    new_count = sum(1 for x in tradeable if x.get("build_year") and (_cy - x["build_year"]) <= 10)
    old_count = sum(1 for x in tradeable if x.get("build_year") and (_cy - x["build_year"]) > 20)
    station_count = sum(1 for x in tradeable if any(
        (s.get("distance") or 9999) <= 800 for s in (x.get("nearby_subway") or [])
    ))
    all_prices = [x["_best_trade"].get("price", 0) for x in tradeable if x.get("_best_trade")]
    valid_prices = [p for p in all_prices if p > 0]
    biggest = max(tradeable, key=lambda x: (x.get("total_units") or 0), default=None)

    # FAQ — 핵심 4개로 축소 (가독성)
    faq = []
    faq.append((
        f"{dong} 아파트 단지는 몇 개?",
        f"{region} {gu} {dong}에는 {len(tradeable):,}개 아파트 단지가 거래 데이터를 갖추고 있습니다."
    ))
    if most_expensive:
        me_price = format_price(most_expensive["_best_trade"].get("price"))
        faq.append((
            f"{dong}에서 가장 비싼 아파트는?",
            f"{most_expensive.get('complex_name','')} 전용 {most_expensive['_best_area']}㎡, 최근 거래가 {me_price}."
        ))
    if cheapest and cheapest != most_expensive:
        ch_price = format_price(cheapest["_best_trade"].get("price"))
        faq.append((
            f"{dong}에서 가장 저렴한 아파트는?",
            f"{cheapest.get('complex_name','')} 전용 {cheapest['_best_area']}㎡, 최근 거래가 {ch_price}."
        ))
    if subways:
        subway_text = ", ".join(
            f"{s.get('name','')}({clean_line(s.get('line',''))}) 도보 {walk_min(s.get('distance'))}"
            for s in subways[:3]
        )
        faq.append((f"{dong} 근처 지하철역은?", subway_text))

    # FAQ 섹션
    lines.append('<div class="faq-section"><h2 class="section-title">자주 묻는 질문</h2>')
    for q, a in faq:
        lines.append(f'<div class="faq-item">')
        lines.append(f'<div class="faq-q">{esc(q)}</div>')
        lines.append(f'<div class="faq-a">{esc(a)}</div>')
        lines.append('</div>')
    lines.append('</div><div class="divider"></div>')

    # 같은 구 다른 동 (grid 6개)
    other_dongs = [d2 for d2 in same_gu_dongs if d2 != dong][:6]
    if other_dongs:
        lines.append(f'<div class="section"><h2 class="section-title">{esc(gu)} 다른 동도 보세요</h2>')
        lines.append(f'<div class="gu-grid">')
        for od in other_dongs:
            od_slug = (dong_slug_map or {}).get((region, gu, od)) or make_dong_slug(gu, od, first_addr)
            _t = f'{esc(gu)} {esc(od)} 아파트 실거래가 시세'
            lines.append(
                f'<a class="gu-item" title="{_t}" style="text-decoration:none;color:inherit;" '
                f'href="/dong/{url_quote(od_slug, safe="-")}.html">'
                f'<div class="gu-name">{esc(od)}</div>'
                f'<div class="gu-info">시세 보기 →</div>'
                f'</a>'
            )
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    # 내부 링크
    if has_gu_page:
        lines.append(f'<div class="section">')
        lines.append(f'<h2 class="section-title">{esc(gu)} 전체 시세도 확인</h2>')
        lines.append(
            f'<a class="gu-item" title="{esc(gu)} 아파트 실거래가 시세" '
            f'style="text-decoration:none;color:inherit;display:block;" '
            f'href="/gu/{url_quote(gu_page_slug, safe="-")}.html">'
            f'<div class="gu-name">{esc(gu)} 아파트 시세</div>'
            f'<div class="gu-info">매매·전세·월세 면적별 가격 →</div>'
            f'</a>'
        )
        lines.append(f'</div>')
        lines.append(f'<div class="divider"></div>')

    # SEO 본문 + 데이터 안내
    seo_lead = []
    if len(tradeable) >= 10 and station_count >= 5:
        seo_lead.append(f"{gu} {dong}{josa(dong,'은/는')} {station_count}개 단지가 역세권에 있는 주거 밀집 지역입니다.")
    elif new_count and new_count >= len(tradeable) // 2:
        seo_lead.append(f"{gu} {dong}{josa(dong,'은/는')} 10년 이내 신축이 {new_count}개로 새 아파트가 많은 지역입니다.")
    elif len(tradeable) >= 15:
        seo_lead.append(f"{gu} {dong}{josa(dong,'은/는')} {len(tradeable)}개 아파트 단지가 밀집한 대규모 주거지역입니다.")
    else:
        seo_lead.append(f"{gu} {dong}에는 {len(tradeable)}개 아파트 단지가 있습니다.")
    if most_expensive:
        seo_lead.append(f"최근 거래가가 가장 높은 단지는 {most_expensive.get('complex_name','')}(전용 {most_expensive['_best_area']}㎡, {format_price(most_expensive['_best_trade'].get('price'))})입니다.")
    if cheapest and cheapest != most_expensive:
        seo_lead.append(f"가장 저렴한 단지는 {cheapest.get('complex_name','')}(전용 {cheapest['_best_area']}㎡, {format_price(cheapest['_best_trade'].get('price'))})입니다.")
    if oldest and newest and oldest.get("build_year") and newest.get("build_year"):
        seo_lead.append(f"준공년도는 {oldest.get('build_year')}년부터 {newest.get('build_year')}년까지 분포합니다.")
    if subways:
        sw_names = ", ".join(f"{s.get('name','')}({clean_line(s.get('line',''))})" for s in subways[:2])
        seo_lead.append(f"인근 지하철역은 {sw_names}입니다.")

    lines.append(f'<div class="seo-section" style="padding:16px;">')
    lines.append(f'<div class="seo-text">{esc(" ".join(seo_lead))} 모든 데이터는 국토교통부 실거래가 공개시스템 기반입니다.</div>')
    lines.append(f'<details class="data-notice" style="margin-top:14px;font-size:12px;color:var(--sub);">')
    lines.append(f'<summary style="cursor:pointer;">데이터 안내</summary>')
    lines.append(f'<div style="margin-top:6px;line-height:1.8;">')
    lines.append(f'<b>실거래가</b>: 국토교통부 실거래가 공개시스템 (<a href="https://rt.molit.go.kr/" target="_blank" rel="noopener nofollow">rt.molit.go.kr</a>) · 매일 자동 수집<br>')
    lines.append(f'<b>건축정보</b>: 국토교통부 건축물대장<br>')
    lines.append(f'<b>지하철·학교</b>: 단지별 도보 800m 이내, 단지 3개 이상 등장한 시설만 표시<br>')
    lines.append(f'전용면적 ㎡ 기준 표기<br>')
    lines.append(f'거래 취소·정정 건은 반영이 지연될 수 있습니다')
    lines.append(f'</div></details>')
    lines.append(f'<div class="seo-source" style="margin-top:8px;font-size:11px;color:var(--muted);">'
                 f'실거래가 출처: 국토교통부 · 최종 데이터 확인: <time datetime="{today}">{today}</time></div>')
    lines.append(f'</div>')

    body = "\n".join(lines)

    # ── JSON-LD 강화 (Organization + CollectionPage + AdministrativeArea + FAQ + ItemList + Breadcrumb) ──
    place_block = {
        "@type": "AdministrativeArea",
        "name": f"{region} {gu} {dong}",
        "containedInPlace": {
            "@type": "AdministrativeArea",
            "name": f"{region} {gu}",
            "containedInPlace": {
                "@type": "AdministrativeArea",
                "name": region,
                "containedInPlace": {"@type": "Country", "name": "대한민국"},
            },
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
        "logo": {"@type": "ImageObject", "url": "https://hwik.kr/og-image.png", "width": 1200, "height": 630},
        "sameAs": ["https://hwik.kr"],
    }

    item_list = []
    for i, d in enumerate(tradeable[:50]):
        danji_slug = make_danji_slug(d.get("complex_name", ""), d.get("location", ""), d.get("id", ""), d.get("address", ""))
        bits = []
        if d.get("build_year"):
            bits.append(f"{d['build_year']}년")
        if d.get("total_units"):
            try:
                bits.append(f"{int(d['total_units']):,}세대")
            except Exception:
                pass
        item = {
            "@type": "ListItem",
            "position": i + 1,
            "name": d.get("complex_name", ""),
            "url": f"https://hwik.kr/danji/{url_quote(danji_slug, safe='-')}.html",
        }
        if bits:
            item["description"] = " · ".join(bits)
        item_list.append(item)

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
            "name": f"{gu} {dong} 아파트",
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
    }
    _bc = [{"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"}]
    _pos = 2
    if has_gu_page:
        _bc.append({"@type": "ListItem", "position": _pos, "name": region, "item": f"https://hwik.kr{region_link}"})
        _pos += 1
        _bc.append({"@type": "ListItem", "position": _pos, "name": gu,
                    "item": f"https://hwik.kr/gu/{url_quote(gu_page_slug, safe='-')}.html"})
        _pos += 1
    else:
        if region:
            _bc.append({"@type": "ListItem", "position": _pos, "name": region})
            _pos += 1
        _bc.append({"@type": "ListItem", "position": _pos, "name": gu})
        _pos += 1
    _bc.append({"@type": "ListItem", "position": _pos, "name": dong})
    jsonld_breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": _bc,
    }

    jsonld = json.dumps({"@context": "https://schema.org", "@graph": [
        jsonld_org, jsonld_collection, jsonld_place, jsonld_faq, jsonld_breadcrumb,
    ]}, ensure_ascii=False)

    # 네이버 published_time
    all_updated = [x.get("updated_at","") for x in tradeable if x.get("updated_at")]
    dong_published_time = ""
    if all_updated:
        latest = max(all_updated)
        if len(latest) >= 19:
            dong_published_time = latest[:19] + "+00:00"
    dong_naver_meta = ""
    if dong_published_time:
        dong_naver_meta = f'<meta property="article:published_time" content="{dong_published_time}">'

    # ── 최종 HTML (gu D 디자인 동일 패턴) ──
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="icon" href="/favicon.ico">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="휙">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="https://hwik.kr/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{canonical}">
<meta property="article:modified_time" content="{esc(today)}">
<meta name="google-site-verification" content="R2ye41AVVTRs8BxEXyEafFSTqMSiHKdb9zgTklrktSI" />
<meta name="naver-site-verification" content="367bd1e77a8ad48b74e345be3e4a0f8125c2c4e1" />
{dong_naver_meta}
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2DVQXMLC9J"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-2DVQXMLC9J');</script>
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="https://hwik.kr/og-image.png">
<link rel="stylesheet" href="/danji/style.css">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" as="style" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css" media="(min-width: 768px)">
<style>
.gu-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
.gu-item {{ padding:14px; background:var(--card); border-radius:var(--radius); cursor:pointer; transition:all .15s; border-left:3px solid var(--yellow); }}
.gu-item:active {{ transform:scale(0.97); }}
.gu-name {{ font-size:14px; font-weight:600; }}
.gu-info {{ font-size:11px; color:var(--sub); margin-top:4px; }}
/* 인프라 칩 */
.info-chips {{ display:flex; flex-wrap:wrap; gap:6px; padding:0 16px 16px; }}
.info-chip {{ display:inline-block; padding:4px 10px; border-radius:14px; font-size:11px; font-weight:600; }}
.info-chip-subway {{ background:rgba(59,130,246,0.15); color:#60a5fa; }}
.info-chip-school {{ background:rgba(99,153,34,0.15); color:#84cc16; }}
/* 1위 hero — 모바일 (세로) */
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

/* ── PC ≥768px D 디자인 라이트 (gu와 동일) ── */
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
  .header .header-name {{
    font-size: 22px !important;
    font-weight: 700 !important;
    color: #4338ca !important;
    letter-spacing: -0.03em !important;
    line-height: 1.25 !important;
    margin: 0 !important;
  }}
  .header .header-sub {{ font-size: 12.5px !important; color: #64748b !important; margin-top: 2px !important; }}
  .divider {{ display: none !important; }}
  .section {{ padding: 20px 14px !important; }}
  .section-title {{
    font-size: 16px !important; font-weight: 700 !important;
    color: #0f172a !important; letter-spacing: -0.025em !important;
    margin: 0 0 14px !important;
  }}
  /* 인프라 칩 */
  .info-chip-subway {{ background:#dbeafe !important; color:#1e40af !important; }}
  .info-chip-school {{ background:#dcfce7 !important; color:#166534 !important; }}
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
    margin-bottom: 8px !important;
  }}
  .danji-hero .hero-name {{ font-size: 18px !important; font-weight: 800 !important; color: #1e293b !important; }}
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
  /* 다른 동/구 카드 */
  .gu-item {{
    background: #f8fafc !important;
    border: 1px solid #eef0f4 !important;
    border-left: 3px solid #4338ca !important;
    border-radius: 10px !important;
  }}
  .gu-item:hover {{
    background: #eef2ff !important;
    border-color: #c7d2fe !important;
    transform: translateX(2px) !important;
  }}
  .gu-name {{ color: #1e293b !important; font-weight: 700 !important; }}
  .gu-item:hover .gu-name {{ color: #4338ca !important; }}
  .gu-info {{ color: #64748b !important; }}
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
<script type="application/ld+json">{jsonld}</script>
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
def main():
    os.makedirs(DONG_DIR, exist_ok=True)

    ONE_DONG_SLUG = os.environ.get("ONE_DONG_SLUG", "").strip()
    if ONE_DONG_SLUG:
        print(f"[ONE_DONG_SLUG={ONE_DONG_SLUG}] 단일 동만 빌드 — 기존 파일 유지, 인덱스 미갱신")

    # ── 데이터 먼저 확보 (실패 시 기존 파일 보존) ──
    print("danji_pages 조회 중...")
    all_danji = fetch_all_danji()
    if not all_danji:
        print("❌ 데이터 0건 — 중단 (기존 dong 페이지 유지)")
        sys.exit(1)
    print(f"{len(all_danji)}개 단지 로드")

    # ── 데이터 확보 후 옛 HTML 파일 삭제 (ONE_DONG_SLUG 모드는 보존) ──
    if not ONE_DONG_SLUG:
        old_count = 0
        for f in os.listdir(DONG_DIR):
            if f.endswith(".html"):
                os.remove(os.path.join(DONG_DIR, f))
                old_count += 1
        if old_count:
            print(f"기존 {old_count}개 HTML 삭제")

    # 동별 그룹화 (region, gu, dong) → [danji, ...]
    # region을 키에 포함하여 동일 (gu, dong)의 지역 충돌 방지
    # 예: 대전 서구 둔산동 vs 전북 익산 둔산동 (이전엔 병합됐음)
    dong_groups = defaultdict(list)

    for d in all_danji:
        loc = d.get("location", "")
        if not loc:
            continue
        parts = loc.split(" ", 1)
        if len(parts) < 2:
            continue
        dong = parts[1]
        address = d.get("address", "") or ""
        region = detect_region(address)
        if not region:
            # address 비어있음 → 그룹 키에 region 없음 → 슬러그가 "gu-dong" 형태로 생성됨
            # 이런 고아 row는 skip (데이터 정합성 이슈)
            continue
        # gu: address 우선 (경기 "수원시 장안구" 2토큰 정확히 인식), 실패 시 location fallback
        gu = extract_gu_from_address(address) or parts[0]
        dong_groups[(region, gu, dong)].append(d)

    # 구별 동 목록 (같은 구 다른 동 링크용) — 거래 3개+ 동만
    gu_dongs = defaultdict(list)  # (region, gu) → [dong, ...]
    for (region, gu, dong), danji_list in dong_groups.items():
        trade_count = sum(1 for d in danji_list if has_trade_data(d))
        if trade_count >= MIN_DANJI_WITH_TRADE:
            gu_dongs[(region, gu)].append(dong)
    for k in gu_dongs:
        gu_dongs[k].sort()

    # 동별 slug 사전 계산 (다른 동 링크에 올바른 slug 사용)
    dong_slug_map = {}  # (region, gu, dong) → slug
    for (region, gu, dong), danji_list in dong_groups.items():
        # 첫 번째 non-empty address 선택 (더 안정적)
        first_addr = ""
        for d in danji_list:
            a = d.get("address", "") or ""
            if a:
                first_addr = a
                break
        dong_slug_map[(region, gu, dong)] = make_dong_slug(gu, dong, first_addr)

    print(f"동 그룹: {len(dong_groups)}개, 생성 대상(거래 3개+): {sum(len(v) for v in gu_dongs.values())}개")

    count = 0
    skipped = 0

    for (region, gu, dong), danji_list in sorted(dong_groups.items()):
        same_gu = gu_dongs.get((region, gu), [])

        first_addr = ""
        for d in danji_list:
            a = d.get("address", "") or ""
            if a:
                first_addr = a
                break
        slug = make_dong_slug(gu, dong, first_addr)
        if ONE_DONG_SLUG and slug != ONE_DONG_SLUG:
            continue

        page = build_dong_html(gu, dong, danji_list, region, same_gu, dong_slug_map)
        if page is None:
            skipped += 1
            continue

        path = os.path.join(DONG_DIR, f"{slug}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        count += 1

        if count % 100 == 0:
            print(f"  {count}개 생성...")

    print(f"\n{count}개 동 페이지 생성, {skipped}개 스킵 (거래 단지 {MIN_DANJI_WITH_TRADE}개 미만)")
    print(f"출력: {DONG_DIR}/")

    # /dong/ 인덱스 페이지 자동 생성 (ONE_DONG_SLUG 모드는 스킵)
    if not ONE_DONG_SLUG:
        try:
            from build_dong_index import build_index as _build_dong_index
            _build_dong_index()
        except Exception as _e:
            print(f"⚠️ dong/index.html 생성 실패: {_e}")


if __name__ == "__main__":
    main()
