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
from datetime import datetime, timezone
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
def fetch_all_danji():
    all_data = []
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            headers={**SB_HEADERS, "Prefer": ""},
            params={
                "select": "id,complex_name,location,address,categories,recent_trade,"
                          "jeonse_rate,total_units,build_year",
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

        result.append({
            "id": d["id"], "name": d["complex_name"],
            "location": loc, "address": d.get("address", ""),
            "region": region_key, "price": price, "area": area,
            "area_num": area_num,
            "sqm_price": round(price / area_num) if area_num > 0 else 0,
            "jr": d.get("jeonse_rate"), "build_year": d.get("build_year"),
            "units": d.get("total_units"),
        })
    return result


def build_ranking_html(region, rank_type, data):
    """랭킹 페이지 HTML 생성"""
    area_label = REGION_LABELS.get(region, "전체")
    type_label = TYPE_LABELS.get(rank_type, "매매가")
    slug = f"{region}-{rank_type}"
    canonical = f"https://hwik.kr/ranking/{slug}"

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
    title = f"{area_label} 아파트 {type_label} 순위 TOP 50 - 휙"
    top1_str = f" 1위 {top50[0]['name']} {format_price(top50[0]['price'])}." if top50 else ""
    desc = f"{area_label} 아파트 {type_label} 순위 TOP 50.{top1_str} 국토교통부 실거래가 기반 최신 데이터."

    lines = []

    # 헤더
    lines.append(f'<header class="header"><div class="header-top">')
    lines.append(f'  <a class="logo" href="/" style="text-decoration:none;">휙</a>')
    lines.append(f'  <div><h1 class="header-name">{esc(area_label)} 아파트 순위</h1>')
    lines.append(f'  <div class="header-sub">{esc(type_label)} TOP 50</div></div>')
    lines.append(f'</div></header>')

    # 브레드크럼
    lines.append(f'<nav class="breadcrumb"><a href="/">휙</a><span>&gt;</span><a href="/ranking/">순위</a><span>&gt;</span>{esc(area_label)} {esc(type_label)}</nav>')

    # 지역 탭
    lines.append(f'<div class="tabs" style="border-bottom:2px solid var(--border);">')
    for rk, rl in REGION_LABELS.items():
        active = " active" if rk == region else ""
        lines.append(f'<a class="tab{active}" style="text-decoration:none;color:inherit;" href="/ranking/{rk}-{rank_type}">{esc(rl)}</a>')
    lines.append(f'</div>')

    # 타입 탭
    lines.append(f'<div class="tabs">')
    for tk, tl in TYPE_LABELS.items():
        active = " active" if tk == rank_type else ""
        short_label = tl.replace(" 높은", "↑").replace(" 낮은", "↓")
        lines.append(f'<a class="tab{active}" style="text-decoration:none;color:inherit;" href="/ranking/{region}-{tk}">{esc(short_label)}</a>')
    lines.append(f'</div>')

    # 도입 텍스트 (SEO 콘텐츠)
    if top50:
        intro_parts = [f"{area_label} 아파트 {type_label} 순위입니다."]
        intro_parts.append(f"국토교통부 실거래가 공개시스템 기반으로 최신 데이터를 반영합니다.")
        if rank_type == "price":
            intro_parts.append(f"1위는 {top50[0]['name']}({top50[0]['location']})으로 {format_price(top50[0]['price'])}입니다.")
        elif rank_type == "sqm" and top50[0].get("sqm_price"):
            intro_parts.append(f"㎡당 가격 1위는 {top50[0]['name']}으로 {format_price(top50[0]['sqm_price'])}/㎡입니다.")
        elif rank_type in ("jeonse", "jeonse_low"):
            intro_parts.append(f"전세가율 1위는 {top50[0]['name']}({top50[0].get('jr', 0)}%)입니다.")
        lines.append(f'<p style="font-size:13px;color:var(--sub);padding:8px 16px 0;line-height:1.6;">{" ".join(intro_parts)}</p>')

    # 랭킹 목록
    lines.append(f'<div class="section"><div class="section-title">{esc(area_label)} {esc(type_label)} TOP 50</div>')
    lines.append(f'<div style="display:flex;flex-direction:column;gap:8px;">')
    for i, d in enumerate(top50):
        slug_d = make_danji_slug(d["name"], d["location"], d["id"], d["address"])
        if rank_type == "price":
            main_val = format_price(d["price"])
            sub_val = f'{format_price(d["sqm_price"])}/㎡' if d["sqm_price"] else ""
        elif rank_type == "sqm":
            main_val = f'{format_price(d["sqm_price"])}/㎡'
            sub_val = f'매매 {format_price(d["price"])} · {d["area"]}㎡'
        else:
            main_val = f'{d.get("jr", 0)}%'
            sub_val = f'매매 {format_price(d["price"])}'

        top3 = " top3" if i < 3 else ""
        lines.append(f'<a class="rank-item" style="text-decoration:none;color:inherit;" href="/danji/{url_quote(slug_d, safe="-")}">')
        lines.append(f'  <div class="rank-num{top3}">{i+1}</div>')
        lines.append(f'  <div class="rank-info"><div class="rank-name">{esc(d["name"])}</div>')
        lines.append(f'  <div class="rank-sub">{esc(d["location"])}{" · "+str(d["build_year"])+"년" if d.get("build_year") else ""}{" · 전용"+d["area"]+"㎡" if d.get("area") else ""}</div></div>')
        lines.append(f'  <div class="rank-price"><div class="rank-main">{main_val}</div><div class="rank-detail">{sub_val}</div></div>')
        lines.append(f'</a>')
    lines.append(f'</div></div>')
    lines.append(f'<div class="divider"></div>')

    # FAQ
    lines.append(f'<div class="faq-section"><div class="section-title">자주 묻는 질문</div>')
    if top50:
        lines.append(f'<div class="faq-item"><div class="faq-q">{esc(area_label)}에서 가장 비싼 아파트는?</div>')
        lines.append(f'<div class="faq-a">{esc(top50[0]["name"])} ({esc(top50[0]["location"])})이 {format_price(top50[0]["price"])}으로 1위입니다. 국토교통부 최신 실거래가 기준입니다.</div></div>')
        # 2위
        if len(top50) >= 2:
            lines.append(f'<div class="faq-item"><div class="faq-q">{esc(area_label)} 아파트 매매가 2위는?</div>')
            lines.append(f'<div class="faq-a">2위는 {esc(top50[1]["name"])} ({esc(top50[1]["location"])})으로 {format_price(top50[1]["price"])}입니다.</div></div>')
        # 3위
        if len(top50) >= 3:
            lines.append(f'<div class="faq-item"><div class="faq-q">{esc(area_label)} 아파트 매매가 3위는?</div>')
            lines.append(f'<div class="faq-a">3위는 {esc(top50[2]["name"])} ({esc(top50[2]["location"])})으로 {format_price(top50[2]["price"])}입니다.</div></div>')
        if rank_type == "sqm":
            lines.append(f'<div class="faq-item"><div class="faq-q">{esc(area_label)} ㎡당 가격 1위는?</div>')
            lines.append(f'<div class="faq-a">{esc(top50[0]["name"])}이 전용면적 기준 {format_price(top50[0]["sqm_price"])}/㎡으로 1위입니다.</div></div>')
        if rank_type in ("jeonse", "jeonse_low"):
            lines.append(f'<div class="faq-item"><div class="faq-q">{esc(area_label)} 전세가율 순위는?</div>')
            direction = "높은" if rank_type == "jeonse" else "낮은"
            lines.append(f'<div class="faq-a">전세가율 {direction} 1위는 {esc(top50[0]["name"])} ({top50[0].get("jr",0)}%)입니다.</div></div>')
    lines.append(f'</div>')

    # SEO
    seo = f'{esc(area_label)} 아파트 {esc(type_label)} 순위 TOP 50.'
    if top50:
        seo += f' {esc(top50[0]["name"])}({format_price(top50[0]["price"])})이 1위.'
    seo += ' 국토교통부 실거래가 기반.'
    lines.append(f'<div class="seo-section"><div class="seo-text">{seo}</div>')
    _today = datetime.now().strftime("%Y-%m-%d")
    lines.append(f'<div class="seo-source">실거래가 출처: 국토교통부 · 최종 데이터 확인: {_today}</div></div>')

    body = "\n".join(lines)

    # JSON-LD
    faq_items = []
    if top50:
        faq_items.append({"@type": "Question", "name": f"{area_label}에서 가장 비싼 아파트는?",
                          "acceptedAnswer": {"@type": "Answer", "text": f"{top50[0]['name']} ({top50[0]['location']})이 {format_price(top50[0]['price'])}으로 1위입니다."}})

    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "FAQPage", "mainEntity": faq_items} if faq_items else None,
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
                {"@type": "ListItem", "position": 2, "name": "순위"},
            ]},
            {"@type": "ItemList", "name": f"{area_label} 아파트 {type_label} 순위",
             "numberOfItems": len(top50),
             "itemListElement": [
                 {"@type": "ListItem", "position": i+1, "name": d["name"],
                  "url": f"https://hwik.kr/danji/{url_quote(make_danji_slug(d['name'], d['location'], d['id'], d['address']), safe='-')}"}
                 for i, d in enumerate(top50[:20])
             ]}
        ]
    }
    jsonld["@graph"] = [x for x in jsonld["@graph"] if x]

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
.tabs {{ display:flex; border-bottom:1px solid var(--border); overflow-x:auto; }}
.tabs::-webkit-scrollbar {{ display:none; }}
.tab {{ flex-shrink:0; padding:12px 16px; text-align:center; font-size:13px; color:var(--sub); cursor:pointer; border-bottom:2px solid transparent; transition:all .2s; white-space:nowrap; text-decoration:none; }}
.tab.active {{ color:var(--text); font-weight:500; border-bottom-color:var(--yellow); }}
.rank-item {{ display:flex; align-items:center; padding:14px; background:var(--surface); border-radius:var(--radius); cursor:pointer; transition:all .15s; box-shadow:0 1px 4px rgba(0,0,0,0.05); gap:12px; }}
.rank-item:active {{ transform:scale(0.98); }}
.rank-num {{ font-size:16px; font-weight:700; color:var(--yellow); min-width:28px; text-align:center; }}
.rank-num.top3 {{ color:var(--red); }}
.rank-info {{ flex:1; }}
.rank-name {{ font-size:13px; font-weight:600; }}
.rank-sub {{ font-size:11px; color:var(--sub); margin-top:2px; }}
.rank-price {{ text-align:right; }}
.rank-main {{ font-size:14px; font-weight:700; }}
.rank-detail {{ font-size:11px; color:var(--sub); margin-top:2px; }}
</style>
<script type="application/ld+json">{jsonld_str}</script>
</head>
<body>
<div class="wrap">
{body}
</div>
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

    _today = datetime.now().strftime("%Y-%m-%d")
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
                  "url": f"https://hwik.kr/ranking/{r}-price"}
                 for i, r in enumerate([x for x in region_order if x in REGION_LABELS])
             ]}
        ]
    }
    return wrap_html(title, desc, canonical, body, json.dumps(jsonld, ensure_ascii=False))


# ── 메인 ──────────────────────────────────────────────────
def main():
    os.makedirs(RANK_DIR, exist_ok=True)
    print("Supabase에서 단지 데이터 조회 중...")
    all_danji = fetch_all_danji()
    print(f"  {len(all_danji)}개 단지 로드 완료")

    data = process_data(all_danji)
    print(f"  {len(data)}개 단지 가격 데이터 가공 완료")

    count = 0
    for region in REGION_LABELS:
        for rank_type in TYPE_LABELS:
            html = build_ranking_html(region, rank_type, data)
            slug = f"{region}-{rank_type}"
            fpath = os.path.join(RANK_DIR, f"{slug}.html")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(html)
            count += 1

    # index.html → 자가 정규화 허브 (중복 콘텐츠 방지)
    index_html = build_hub_html()
    with open(os.path.join(RANK_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"\n{count}개 랭킹 페이지 생성 + index.html(허브)")
    print(f"출력: {RANK_DIR}")


if __name__ == "__main__":
    main()
