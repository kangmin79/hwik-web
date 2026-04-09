#!/usr/bin/env python3
"""
build_dong_pages.py — 동별 정적 HTML 페이지 생성 (SEO)

Supabase danji_pages → dong/[구-동].html (정적 SEO 콘텐츠)
거래 있는 단지 3개 이상인 동만 생성 (thin content 방지)

Usage:
  python build_dong_pages.py
"""

import os, sys, json, re, time, hashlib, html as html_mod
from datetime import datetime, timezone
import requests
from collections import defaultdict
from urllib.parse import quote as url_quote
from slug_utils import (
    REGION_MAP, METRO_CITIES, clean as _clean,
    detect_region, make_danji_slug, make_dong_slug,
)

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
def fetch_all_danji():
    all_data = []
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            headers={**SB_HEADERS, "Prefer": ""},
            params={
                "select": "id,complex_name,location,address,build_year,total_units,"
                          "categories,recent_trade,all_time_high,jeonse_rate,"
                          "nearby_subway,nearby_school,lat,lng,price_history,updated_at,builder",
                "order": "id",
                "offset": offset,
                "limit": 500,
            },
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else []
        if not data:
            break
        all_data.extend(data)
        offset += 500
        if len(data) < 500:
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
def build_dong_html(gu, dong, danji_list, region, same_gu_dongs):
    """동 페이지 정적 HTML 생성"""
    first_addr = danji_list[0].get("address", "") if danji_list else ""
    slug = make_dong_slug(gu, dong, first_addr)
    canonical = f"https://hwik.kr/dong/{slug}"

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

    title = f"{gu} {dong} 아파트 실거래가 시세 - 휙"
    desc = f"{gu} {dong} 아파트 {len(tradeable)}개 단지 실거래가, 시세를 확인하세요. 국토교통부 실거래가 공개시스템 기반."

    # ── fallback 콘텐츠 ──
    lines = []

    # breadcrumb
    region_link = "/gu.html" if region == "서울" else f"/gu.html?tab={'incheon' if region == '인천' else 'gyeonggi'}"
    lines.append(f'<nav style="font-size:11px;color:#6b7280;margin-bottom:12px;">')
    lines.append(f'  <a href="/" style="color:#6b7280;text-decoration:none;">휙</a> &gt;')
    lines.append(f'  <a href="{region_link}" style="color:#6b7280;text-decoration:none;">{esc(region)}</a> &gt;')
    lines.append(f'  <a href="/gu.html?name={url_quote(gu, safe="")}" style="color:#6b7280;text-decoration:none;">{esc(gu)}</a> &gt;')
    lines.append(f'  {esc(dong)}')
    lines.append(f'</nav>')

    lines.append(f'<h1 style="font-size:18px;font-weight:700;margin-bottom:4px;">{esc(gu)} {esc(dong)} 아파트 시세</h1>')
    lines.append(f'<p style="font-size:12px;color:#6b7280;margin-bottom:16px;">{len(tradeable)}개 단지 · 최근 매매가 높은 순</p>')

    # 인프라 태그
    tags = []
    for s in subways[:4]:
        tags.append(f'<span style="display:inline-block;padding:3px 8px;background:rgba(59,130,246,0.1);border-radius:12px;font-size:10px;color:#3b82f6;margin:0 4px 4px 0;">{esc(s.get("name",""))}({esc(s.get("line",""))}) 도보 {walk_min(s.get("distance"))}</span>')
    for s in schools[:3]:
        tags.append(f'<span style="display:inline-block;padding:3px 8px;background:rgba(99,153,34,0.1);border-radius:12px;font-size:10px;color:#639922;margin:0 4px 4px 0;">{esc(s.get("name",""))} 도보 {walk_min(s.get("distance"))}</span>')
    if tags:
        lines.append(f'<div style="margin-bottom:16px;">{"".join(tags)}</div>')

    # 동네 리포트
    most_expensive = tradeable[0] if tradeable else None  # 이미 가격순 정렬됨
    cheapest = tradeable[-1] if len(tradeable) > 1 else None
    most_units = max(tradeable, key=lambda x: (x.get("total_units") or 0), default=None)
    newest = max(tradeable, key=lambda x: (x.get("build_year") or 0), default=None)
    oldest = min(tradeable, key=lambda x: (x.get("build_year") or 9999), default=None)

    lines.append('<div style="margin-bottom:20px;padding:16px;background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;">')
    lines.append(f'<h2 style="font-size:14px;font-weight:700;margin-bottom:10px;">{esc(gu)} {esc(dong)} 부동산 요약</h2>')
    lines.append(f'<div style="font-size:12px;line-height:2;color:#374151;">')
    lines.append(f'아파트 단지: <strong>{len(tradeable)}개</strong><br>')
    if most_expensive:
        me_price = format_price(most_expensive["_best_trade"].get("price"))
        lines.append(f'최고 거래가: <strong>{esc(most_expensive.get("complex_name",""))}</strong> 전용 {most_expensive["_best_area"]}㎡ {me_price}<br>')
    if cheapest and cheapest != most_expensive:
        ch_price = format_price(cheapest["_best_trade"].get("price"))
        lines.append(f'최저 거래가: <strong>{esc(cheapest.get("complex_name",""))}</strong> 전용 {cheapest["_best_area"]}㎡ {ch_price}<br>')
    if most_units and (most_units.get("total_units") or 0) > 0:
        mu = most_units.get("total_units")
        mu_str = f"{mu:,}" if isinstance(mu, int) else str(mu)
        lines.append(f'최다 세대: <strong>{esc(most_units.get("complex_name",""))}</strong> {mu_str}세대<br>')
    if oldest and newest and oldest.get("build_year") and newest.get("build_year"):
        lines.append(f'준공년도 범위: {oldest.get("build_year")}년 ~ {newest.get("build_year")}년<br>')
    if subways:
        sw_names = ", ".join(f"{s.get('name','')}({s.get('line','')})" for s in subways[:3])
        lines.append(f'인근 지하철: {esc(sw_names)}<br>')
    if schools:
        sc_names = ", ".join(s.get("name", "") for s in schools[:3])
        lines.append(f'인근 학교: {esc(sc_names)}<br>')
    lines.append(f'데이터 기준: 국토교통부 실거래가 공개시스템, 매일 갱신<br>')
    # 준공년도 분류
    from datetime import datetime as _dt
    _cy = _dt.now().year
    new_count = sum(1 for x in tradeable if x.get("build_year") and (_cy - x["build_year"]) <= 10)
    old_count = sum(1 for x in tradeable if x.get("build_year") and (_cy - x["build_year"]) > 20)
    if new_count or old_count:
        age_parts = []
        if new_count:
            age_parts.append(f"10년 이내 신축 {new_count}개")
        if old_count:
            age_parts.append(f"20년 초과 {old_count}개")
        lines.append(f'준공년도: {", ".join(age_parts)}<br>')
    # 역세권 비율
    station_count = sum(1 for x in tradeable if any(
        (s.get("distance") or 9999) <= 800 for s in (x.get("nearby_subway") or [])
    ))
    if station_count:
        lines.append(f'역세권(지하철 도보권): 전체 {len(tradeable)}개 중 <strong>{station_count}개</strong><br>')
    # 가격 분포
    all_prices = [x["_best_trade"].get("price", 0) for x in tradeable if x.get("_best_trade")]
    valid_prices = [p for p in all_prices if p > 0]
    if len(valid_prices) >= 2:
        lines.append(f'가격 분포: {format_price(min(valid_prices))} ~ {format_price(max(valid_prices))}')
    lines.append(f'</div></div>')

    # 단지 간 비교 문장
    if most_expensive and cheapest and most_expensive != cheapest:
        me_p = most_expensive["_best_trade"].get("price", 0)
        ch_p = cheapest["_best_trade"].get("price", 0)
        if me_p and ch_p:
            diff = me_p - ch_p
            lines.append(
                f'<p style="font-size:12px;color:#6b7280;line-height:1.7;margin-bottom:16px;">'
                f'{esc(dong)}에서 가장 높은 거래가는 {esc(most_expensive.get("complex_name",""))} '
                f'전용 {most_expensive["_best_area"]}㎡ {format_price(me_p)}이고, '
                f'가장 낮은 거래가는 {esc(cheapest.get("complex_name",""))} '
                f'전용 {cheapest["_best_area"]}㎡ {format_price(ch_p)}입니다. '
                f'{format_price(diff)}의 차이가 있습니다.</p>'
            )

    # 단지 목록
    lines.append('<div style="display:flex;flex-direction:column;gap:8px;">')
    for i, d in enumerate(tradeable):
        name = esc(d.get("complex_name", ""))
        did = d.get("id", "")
        loc = d.get("location", "")
        danji_slug = make_danji_slug(d.get("complex_name", ""), loc, did, d.get("address", ""))
        area = d["_best_area"]
        trade = d["_best_trade"]
        price = format_price(trade.get("price"))
        date = trade.get("date", "")
        year = d.get("build_year", "")
        units = d.get("total_units", "")

        sub_parts = []
        if year:
            sub_parts.append(f"{year}년")
        if units:
            u = f"{units:,}" if isinstance(units, int) else str(units)
            sub_parts.append(f"{u}세대")
        sub_parts.append(f"전용 {area}㎡")
        sub_info = " · ".join(sub_parts)

        lines.append(
            f'<a href="/danji/{danji_slug}" style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:14px;background:#fff;border-radius:10px;text-decoration:none;color:#1a1a2e;'
            f'box-shadow:0 1px 4px rgba(0,0,0,0.05);border-left:3px solid #f5c842;">'
            f'<div><div style="font-size:13px;font-weight:600;">{i+1}. {name}</div>'
            f'<div style="font-size:11px;color:#6b7280;margin-top:2px;">{sub_info}</div></div>'
            f'<div style="text-align:right;"><div style="font-size:14px;font-weight:700;">{price}</div>'
            f'<div style="font-size:11px;color:#6b7280;margin-top:2px;">{esc(date)}</div></div></a>'
        )
    lines.append('</div>')

    # FAQ
    faq = []
    faq.append((
        f"{dong}에 아파트가 몇 개 있나요?",
        f"{gu} {dong}에는 {len(tradeable)}개 아파트 단지가 있습니다."
    ))
    if most_recent:
        mr_name = most_recent.get("complex_name", "")
        mr_area = most_recent["_best_area"]
        mr_trade = most_recent["_best_trade"]
        mr_price = format_price(mr_trade.get("price"))
        mr_date = mr_trade.get("date", "")
        faq.append((
            f"{dong}에서 최근 거래된 아파트는?",
            f"{mr_name} 전용 {mr_area}㎡가 {mr_price}에 거래되었습니다. ({mr_date})"
        ))
    if subways:
        subway_text = ", ".join(
            f"{s.get('name','')}({s.get('line','')}) 도보 {walk_min(s.get('distance'))}"
            for s in subways[:3]
        )
        faq.append((f"{dong} 근처 지하철역은?", subway_text))
    # 확장 FAQ
    if most_expensive:
        me_price = format_price(most_expensive["_best_trade"].get("price"))
        faq.append((
            f"{dong}에서 가장 비싼 아파트는?",
            f"{most_expensive.get('complex_name','')} 전용 {most_expensive['_best_area']}㎡, "
            f"최근 거래가 {me_price}입니다."
        ))
    if cheapest and cheapest != most_expensive:
        ch_price = format_price(cheapest["_best_trade"].get("price"))
        faq.append((
            f"{dong}에서 가장 저렴한 아파트는?",
            f"{cheapest.get('complex_name','')} 전용 {cheapest['_best_area']}㎡, "
            f"최근 거래가 {ch_price}입니다."
        ))
    if oldest and newest and oldest.get("build_year") and newest.get("build_year"):
        faq.append((
            f"{dong} 아파트 준공년도는?",
            f"가장 오래된 단지는 {oldest.get('complex_name','')}({oldest.get('build_year')}년), "
            f"가장 최신 단지는 {newest.get('complex_name','')}({newest.get('build_year')}년)입니다."
        ))
    if schools:
        sc_text = ", ".join(f"{s.get('name','')} 도보 {walk_min(s.get('distance'))}" for s in schools[:3])
        faq.append((f"{dong} 근처 학교는?", sc_text))
    # 추가 FAQ 3개
    if len(valid_prices) >= 2:
        faq.append((
            f"{dong} 아파트 가격 범위는?",
            f"최저 {format_price(min(valid_prices))}에서 최고 {format_price(max(valid_prices))} 사이에 분포합니다."
        ))
    station_danji = [x.get("complex_name","") for x in tradeable if any(
        (s.get("distance") or 9999) <= 800 for s in (x.get("nearby_subway") or [])
    )]
    if station_danji:
        faq.append((
            f"{dong}에서 역세권 아파트는?",
            f"지하철 도보권 단지: {', '.join(station_danji[:5])}{' 등' if len(station_danji) > 5 else ''} ({len(station_danji)}개)"
        ))
    biggest = max(tradeable, key=lambda x: (x.get("total_units") or 0), default=None)
    if biggest and (biggest.get("total_units") or 0) > 0:
        bu = biggest.get("total_units")
        bu_str = f"{bu:,}" if isinstance(bu, int) else str(bu)
        faq.append((
            f"{dong}에서 가장 큰 단지는?",
            f"{biggest.get('complex_name','')} ({bu_str}세대)"
        ))

    lines.append('<div style="margin-top:24px;">')
    lines.append('<h2 style="font-size:14px;font-weight:600;margin-bottom:12px;">자주 묻는 질문</h2>')
    for q, a in faq:
        lines.append(f'<div style="border-bottom:1px solid #e5e7eb;padding:10px 0;">')
        lines.append(f'<div style="font-size:13px;font-weight:500;margin-bottom:4px;">{esc(q)}</div>')
        lines.append(f'<div style="font-size:12px;color:#6b7280;line-height:1.6;">{esc(a)}</div>')
        lines.append('</div>')
    lines.append('</div>')

    # 같은 구 다른 동 링크
    other_dongs = [d2 for d2 in same_gu_dongs if d2 != dong][:10]
    if other_dongs:
        lines.append('<div style="margin-top:24px;">')
        lines.append(f'<h2 style="font-size:14px;font-weight:600;margin-bottom:8px;">{esc(gu)} 다른 동</h2>')
        lines.append('<div style="display:flex;flex-wrap:wrap;gap:6px;">')
        for od in other_dongs:
            od_slug = make_dong_slug(gu, od, first_addr)
            lines.append(
                f'<a href="/dong/{od_slug}" style="padding:8px 12px;background:#f3f4f6;border-radius:8px;'
                f'text-decoration:none;color:#1a1a2e;font-size:12px;">{esc(od)}</a>'
            )
        lines.append('</div></div>')

    # 내부 링크
    lines.append('<div style="margin-top:16px;display:flex;flex-direction:column;gap:8px;">')
    lines.append(f'<a href="/gu.html?name={url_quote(gu, safe="")}" style="padding:12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">{esc(gu)} 전체 시세 &rarr;</a>')
    lines.append('<a href="/ranking.html" style="padding:12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">아파트 순위 &rarr;</a>')
    lines.append('</div>')

    # SEO 서술 (풍부한 고유 콘텐츠) — 서두 다양화
    seo_parts = []
    if len(tradeable) >= 10 and station_count >= 5:
        seo_parts.append(f"{gu} {dong}{josa(dong,'은/는')} {station_count}개 단지가 역세권에 있는 주거 밀집 지역입니다.")
    elif new_count and new_count >= len(tradeable) // 2:
        seo_parts.append(f"{gu} {dong}{josa(dong,'은/는')} 10년 이내 신축이 {new_count}개로 새 아파트가 많은 지역입니다.")
    elif len(tradeable) >= 15:
        seo_parts.append(f"{gu} {dong}{josa(dong,'은/는')} {len(tradeable)}개 아파트 단지가 밀집한 대규모 주거지역입니다.")
    else:
        seo_parts.append(f"{gu} {dong}에는 {len(tradeable)}개 아파트 단지가 있습니다.")
    if most_expensive:
        me_price = format_price(most_expensive["_best_trade"].get("price"))
        seo_parts.append(f"최근 거래가가 가장 높은 단지는 {most_expensive.get('complex_name','')}(전용 {most_expensive['_best_area']}㎡, {me_price})입니다.")
    if cheapest and cheapest != most_expensive:
        ch_price = format_price(cheapest["_best_trade"].get("price"))
        seo_parts.append(f"가장 저렴한 단지는 {cheapest.get('complex_name','')}(전용 {cheapest['_best_area']}㎡, {ch_price})입니다.")
    if oldest and newest and oldest.get("build_year") and newest.get("build_year"):
        seo_parts.append(f"준공년도는 {oldest.get('build_year')}년부터 {newest.get('build_year')}년까지 분포합니다.")
    if subways:
        sw_names = ", ".join(f"{s.get('name','')}({s.get('line','')})" for s in subways[:2])
        seo_parts.append(f"인근 지하철역은 {sw_names}입니다.")
    seo_parts.append("모든 데이터는 국토교통부 실거래가 공개시스템 기반이며 매일 갱신됩니다.")
    lines.append(f'<p style="font-size:11px;color:#6b7280;line-height:1.7;margin-top:16px;">{esc(" ".join(seo_parts))}</p>')
    lines.append('<p style="font-size:10px;color:#6b7280;margin-top:8px;">실거래가 출처: 국토교통부 실거래가 공개시스템 &middot; 매일 업데이트</p>')

    fallback = "\n    ".join(lines)

    # ── JSON-LD ──
    faq_ld = []
    for q, a in faq:
        faq_ld.append({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a},
        })

    item_list = []
    for i, d in enumerate(tradeable[:20]):
        danji_slug = make_danji_slug(d.get("complex_name", ""), d.get("location", ""), d.get("id", ""), d.get("address", ""))
        item_list.append({
            "@type": "ListItem",
            "position": i + 1,
            "name": d.get("complex_name", ""),
            "url": f"https://hwik.kr/danji/{danji_slug}",
        })

    jsonld = json.dumps({"@context": "https://schema.org", "@graph": [
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
                {"@type": "ListItem", "position": 2, "name": region, "item": f"https://hwik.kr{region_link}"},
                {"@type": "ListItem", "position": 3, "name": gu, "item": f"https://hwik.kr/gu.html?name={url_quote(gu, safe='')}"},
                {"@type": "ListItem", "position": 4, "name": dong, "item": canonical},
            ],
        },
        {"@type": "FAQPage", "mainEntity": faq_ld},
        {
            "@type": "ItemList",
            "name": f"{gu} {dong} 아파트",
            "numberOfItems": len(tradeable),
            "itemListElement": item_list,
        },
    ]}, ensure_ascii=False)

    # 네이버 메타태그용 시간 — published_time은 데이터 시간, modified_time은 빌드 시점
    all_updated = [x.get("updated_at","") for x in tradeable if x.get("updated_at")]
    dong_published_time = ""
    if all_updated:
        latest = max(all_updated)
        if len(latest) >= 19:
            dong_published_time = latest[:19] + "+00:00"
    dong_naver_meta = ""
    if dong_published_time:
        dong_naver_meta = f'<meta property="article:published_time" content="{dong_published_time}">\n<meta property="article:modified_time" content="{BUILD_TIME}">'

    # ── 최종 HTML ──
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="휙">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="https://jqaxejgzkchxbfzgzyzi.supabase.co/storage/v1/object/public/og-images/dong/{hashlib.md5(slug.encode('utf-8')).hexdigest()}.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{canonical}">
<meta name="google-site-verification" content="R2ye41AVVTRs8BxEXyEafFSTqMSiHKdb9zgTklrktSI" />
<meta name="naver-site-verification" content="367bd1e77a8ad48b74e345be3e4a0f8125c2c4e1" />
{dong_naver_meta}
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2DVQXMLC9J"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-2DVQXMLC9J');</script>
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<script type="application/ld+json">{jsonld}</script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic','Noto Sans CJK KR',sans-serif;background:#f8f8fa;color:#1a1a2e}}
.wrap{{max-width:430px;margin:0 auto;background:#fff;min-height:100vh}}
.header{{background:#1a1a2e;padding:16px}}
.header-top{{display:flex;align-items:center;gap:12px}}
.logo{{width:36px;height:36px;background:#f5c842;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;color:#1a1a2e;text-decoration:none}}
.header h1{{font-size:17px;font-weight:500;color:#fff}}
.header-sub{{font-size:12px;color:rgba(255,255,255,0.6);margin-top:2px}}
.content{{padding:16px}}
</style>
</head>
<body>
<div class="wrap">
  <header class="header">
    <div class="header-top">
      <a class="logo" href="/">휙</a>
      <div>
        <h1>{esc(gu)} {esc(dong)} 아파트 시세</h1>
        <div class="header-sub">{len(tradeable)}개 단지 · 최근 매매가 높은 순</div>
      </div>
    </div>
  </header>
  <div class="content">
    {fallback}
  </div>
</div>
</body>
</html>"""


# ── 메인 ──────────────────────────────────────────────────
def main():
    os.makedirs(DONG_DIR, exist_ok=True)

    # 옛 HTML 파일 삭제 (고아 파일 방지)
    old_count = 0
    for f in os.listdir(DONG_DIR):
        if f.endswith(".html"):
            os.remove(os.path.join(DONG_DIR, f))
            old_count += 1
    if old_count:
        print(f"기존 {old_count}개 HTML 삭제")

    print("danji_pages 조회 중...")
    all_danji = fetch_all_danji()
    print(f"{len(all_danji)}개 단지 로드")

    # 동별 그룹화 (gu, dong) → [danji, ...]
    dong_groups = defaultdict(list)
    region_cache = {}  # gu → region

    for d in all_danji:
        loc = d.get("location", "")
        if not loc:
            continue
        parts = loc.split(" ", 1)
        if len(parts) < 2:
            continue
        gu, dong = parts[0], parts[1]
        dong_groups[(gu, dong)].append(d)

        # 지역 판별 (address 기반)
        if gu not in region_cache:
            region = detect_region(d.get("address", ""))
            if region:
                region_cache[gu] = region

    # 구별 동 목록 (같은 구 다른 동 링크용) — 거래 3개+ 동만
    gu_dongs = defaultdict(list)
    for (gu, dong), danji_list in dong_groups.items():
        trade_count = sum(1 for d in danji_list if has_trade_data(d))
        if trade_count >= MIN_DANJI_WITH_TRADE:
            gu_dongs[gu].append(dong)
    for gu in gu_dongs:
        gu_dongs[gu].sort()

    print(f"동 그룹: {len(dong_groups)}개, 생성 대상(거래 3개+): {sum(len(v) for v in gu_dongs.values())}개")

    count = 0
    skipped = 0

    for (gu, dong), danji_list in sorted(dong_groups.items()):
        region = region_cache.get(gu, "")
        same_gu = gu_dongs.get(gu, [])

        page = build_dong_html(gu, dong, danji_list, region, same_gu)
        if page is None:
            skipped += 1
            continue

        first_addr = danji_list[0].get("address", "") if danji_list else ""
        slug = make_dong_slug(gu, dong, first_addr)
        path = os.path.join(DONG_DIR, f"{slug}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        count += 1

        if count % 100 == 0:
            print(f"  {count}개 생성...")

    print(f"\n{count}개 동 페이지 생성, {skipped}개 스킵 (거래 단지 {MIN_DANJI_WITH_TRADE}개 미만)")
    print(f"출력: {DONG_DIR}/")


if __name__ == "__main__":
    main()
