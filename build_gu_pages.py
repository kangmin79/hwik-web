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
from slug_utils import make_danji_slug, make_dong_slug

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

REGIONS = {
    "seoul": {
        "label": "서울", "sub": "25개 구",
        "list": ["종로구","중구","용산구","성동구","광진구","동대문구","중랑구","성북구","강북구","도봉구",
                 "노원구","은평구","서대문구","마포구","양천구","강서구","구로구","금천구","영등포구","동작구",
                 "관악구","서초구","강남구","송파구","강동구"]
    },
    "incheon": {
        "label": "인천", "sub": "10개 구·군",
        "list": ["중구","동구","미추홀구","연수구","남동구","부평구","계양구","서구","강화군","옹진군"]
    },
    "gyeonggi": {
        "label": "경기", "sub": "40개 시·구",
        "list": ["수원시 장안구","수원시 권선구","수원시 팔달구","수원시 영통구","성남시 수정구","성남시 중원구",
                 "성남시 분당구","의정부시","안양시 만안구","안양시 동안구","부천시","평택시","안산시 상록구",
                 "안산시 단원구","고양시 덕양구","고양시 일산동구","고양시 일산서구","과천시","구리시","남양주시",
                 "오산시","시흥시","군포시","의왕시","하남시","용인시 처인구","용인시 기흥구","용인시 수지구",
                 "파주시","이천시","안성시","김포시","화성시","광주시","양주시","포천시","여주시","연천군",
                 "가평군","양평군"]
    },
}


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
def fetch_all_danji():
    all_data = []
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            headers={**SB_HEADERS, "Prefer": ""},
            params={
                "select": "id,complex_name,location,address,categories,recent_trade,"
                          "all_time_high,jeonse_rate,total_units,build_year,nearby_subway",
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


def build_gu_detail_html(gu_name, danji_list):
    """구 상세 페이지 HTML 생성"""
    region_key = detect_region(gu_name)
    region_label = REGIONS[region_key]["label"]
    slug = gu_name.replace(" ", "-")
    canonical = f"https://hwik.kr/gu/{url_quote(slug, safe='-')}"

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

        # 동 분류
        parts = (d.get("location") or "").split(" ")
        dong = parts[1] if len(parts) >= 2 else ""
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
        max_price = max((rt[c].get("price", 0) for c in cats if rt.get(c) and rt[c].get("price")), default=0)
        if max_price > 0:
            price_top.append((d, max_price))
    price_top.sort(key=lambda x: x[1], reverse=True)
    price_top = price_top[:3]

    # 전세가율 TOP 3
    jr_top = sorted(
        [d for d in danji_list if d.get("jeonse_rate") and 30 < d["jeonse_rate"] < 150],
        key=lambda x: x["jeonse_rate"], reverse=True
    )[:3]

    title = f"{gu_name} 아파트 실거래가 시세 - 휙"
    desc = f"{region_label} {gu_name} 아파트 {len(danji_list)}개 단지 실거래가, 전세가, 시세 추이를 한눈에 확인하세요."

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
        lines.append(f'<div class="section"><div class="section-title">매매가 높은 단지</div>')
        lines.append(f'<div style="display:flex;flex-direction:column;gap:8px;">')
        for i, (d, mp) in enumerate(price_top):
            slug_d = make_danji_slug(d["complex_name"], d.get("location", ""), d["id"], d.get("address", ""))
            lines.append(f'<a class="danji-item" style="text-decoration:none;color:inherit;" href="/danji/{url_quote(slug_d, safe="-")}">')
            lines.append(f'  <div><div class="danji-name">{i+1}. {esc(d["complex_name"])}</div><div class="danji-sub">{esc(d.get("location",""))}</div></div>')
            lines.append(f'  <div><div class="danji-price">{format_price(mp)}</div><div class="danji-rate">최고가 기준</div></div>')
            lines.append(f'</a>')
        lines.append(f'</div></div><div class="divider"></div>')

    # 전세가율 높은 단지 TOP 3
    if jr_top:
        lines.append(f'<div class="section"><div class="section-title">전세가율 높은 단지</div>')
        lines.append(f'<div style="display:flex;flex-direction:column;gap:8px;">')
        for i, d in enumerate(jr_top):
            slug_d = make_danji_slug(d["complex_name"], d.get("location", ""), d["id"], d.get("address", ""))
            lines.append(f'<a class="danji-item" style="text-decoration:none;color:inherit;" href="/danji/{url_quote(slug_d, safe="-")}">')
            lines.append(f'  <div><div class="danji-name">{i+1}. {esc(d["complex_name"])}</div><div class="danji-sub">{esc(d.get("location",""))}</div></div>')
            lines.append(f'  <div><div class="danji-price">{d["jeonse_rate"]}%</div><div class="danji-rate">전세가율</div></div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')

    lines.append(f'<div class="divider"></div>')

    # 동별 단지
    if dong_list:
        lines.append(f'<div class="section"><div class="section-title">동별 단지</div>')
        lines.append(f'<div class="dong-grid">')
        for dong, info in dong_list:
            avg_p = format_price(round(sum(info["prices"]) / len(info["prices"]))) if info["prices"] else ""
            first_d = next((d for d in danji_list if d.get("location", "").split(" ")[1:2] == [dong]), None)
            addr = first_d.get("address", "") if first_d else ""
            dong_slug = make_dong_slug(gu_name, dong, addr)
            lines.append(f'<a class="dong-item" style="text-decoration:none;color:inherit;" href="/dong/{url_quote(dong_slug, safe="-")}">')
            lines.append(f'  <div class="dong-name">{esc(dong)}</div>')
            lines.append(f'  <div class="dong-count">{info["count"]}개 단지{" · 평균 "+avg_p if avg_p else ""}</div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    # ㎡당 가격 TOP 10
    if sqm_list:
        lines.append(f'<div class="section"><div class="section-title">㎡당 가격 TOP 10 <span style="font-size:10px;color:var(--muted);font-weight:400;">(전용면적 기준)</span></div>')
        lines.append(f'<div style="display:flex;flex-direction:column;gap:8px;">')
        for i, d in enumerate(sqm_list[:10]):
            slug_d = make_danji_slug(d["name"], d["location"], d["id"], d["address"])
            lines.append(f'<a class="danji-item" style="text-decoration:none;color:inherit;" href="/danji/{url_quote(slug_d, safe="-")}">')
            lines.append(f'  <div><div class="danji-name">{i+1}. {esc(d["name"])}</div><div class="danji-sub">{esc(d["location"])} · 전용{d["area"]}㎡</div></div>')
            lines.append(f'  <div><div class="danji-price">{format_price(d["price"])}</div><div class="danji-rate">{format_price(d["sqmPrice"])}/㎡</div></div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    # 최근 거래
    if trades:
        lines.append(f'<div class="section"><div class="section-title">최근 거래</div>')
        lines.append(f'<div style="display:flex;flex-direction:column;gap:8px;">')
        for t in trades[:10]:
            slug_d = make_danji_slug(t["name"], "", t["id"], t["address"])
            lines.append(f'<a class="trade-item" style="text-decoration:none;color:inherit;" href="/danji/{url_quote(slug_d, safe="-")}">')
            lines.append(f'  <div><div class="trade-price">{format_price(t["price"])}</div>')
            lines.append(f'  <div class="trade-detail">{esc(t["name"])} · {t["area"]}㎡{" · "+str(t["floor"])+"층" if t.get("floor") else ""}</div></div>')
            lines.append(f'  <div class="trade-date">{esc(t.get("date",""))}</div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')
        lines.append(f'<div class="divider"></div>')

    # FAQ
    lines.append(f'<div class="faq-section"><div class="section-title">자주 묻는 질문</div>')
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
    lines.append(f'<div class="seo-source">데이터 출처: 국토교통부 실거래가 공개시스템 · 매일 업데이트</div></div>')

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
                     "url": f"https://hwik.kr/danji/{url_quote(make_danji_slug(d['complex_name'], d.get('location',''), d['id'], d.get('address','')), safe='-')}"}
                    for i, d in enumerate(danji_list[:20])
                ]
            }
        ]
    }

    return wrap_html(title, desc, canonical, body, json.dumps(jsonld, ensure_ascii=False))


def build_gu_index_html():
    """전체 구 목록 인덱스 페이지"""
    title = "서울·인천·경기 아파트 시세 - 휙"
    desc = "서울·인천·경기 아파트 실거래가, 시세 추이를 구별로 확인하세요."
    canonical = "https://hwik.kr/gu/"

    lines = []
    lines.append(f'<header class="header"><div class="header-top">')
    lines.append(f'  <a class="logo" href="/" style="text-decoration:none;">휙</a>')
    lines.append(f'  <div><div class="header-name">아파트 시세</div><div class="header-sub">서울·인천·경기</div></div>')
    lines.append(f'</div></header>')
    lines.append(f'<nav class="breadcrumb"><a href="/">휙</a><span>&gt;</span>구별 시세</nav>')

    for key, r in REGIONS.items():
        lines.append(f'<div class="section"><div class="section-title">{esc(r["label"])} {esc(r["sub"])}</div>')
        lines.append(f'<div class="gu-grid">')
        for g in r["list"]:
            g_slug = g.replace(" ", "-")
            lines.append(f'<a class="gu-item" style="text-decoration:none;color:inherit;" href="/gu/{url_quote(g_slug, safe="-")}">')
            lines.append(f'  <div class="gu-name">{esc(g)}</div><div class="gu-info">아파트 시세 보기 →</div>')
            lines.append(f'</a>')
        lines.append(f'</div></div>')

    lines.append(f'<div class="seo-section"><div class="seo-text">서울·인천·경기 아파트 실거래가, 시세 추이를 구별로 확인하세요. 국토교통부 실거래가 공개시스템 데이터 기반.</div>')
    lines.append(f'<div class="seo-source">데이터 출처: 국토교통부 실거래가 공개시스템 · 매일 업데이트</div></div>')

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
<meta name="twitter:card" content="summary">
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
def main():
    os.makedirs(GU_DIR, exist_ok=True)
    print("Supabase에서 단지 데이터 조회 중...")
    all_danji = fetch_all_danji()
    print(f"  {len(all_danji)}개 단지 로드 완료")

    # 구별 분류
    gu_map = defaultdict(list)
    for d in all_danji:
        if d.get("id", "").startswith("offi-"):
            continue
        loc = d.get("location") or ""
        parts = loc.split(" ")
        gu = parts[0] if parts else ""
        if gu:
            gu_map[gu].append(d)

    # 인덱스 페이지
    index_html = build_gu_index_html()
    with open(os.path.join(GU_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # 각 구별 상세 페이지
    count = 0
    skip = 0
    for gu_name, danji_list in sorted(gu_map.items()):
        if len(danji_list) < 3:
            skip += 1
            continue
        html = build_gu_detail_html(gu_name, danji_list)
        slug = gu_name.replace(" ", "-")
        fpath = os.path.join(GU_DIR, f"{slug}.html")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(html)
        count += 1

    print(f"\n{count}개 구 페이지 생성, {skip}개 스킵 (단지 3개 미만)")
    print(f"출력: {GU_DIR}")


if __name__ == "__main__":
    main()
