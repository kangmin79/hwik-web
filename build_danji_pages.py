#!/usr/bin/env python3
"""
build_danji_pages.py — 단지별 정적 HTML 페이지 생성 (SEO)

Supabase danji_pages → danji/[id].html (정적 SEO 콘텐츠 + 인터랙티브 JS)
GitHub Actions에서 매일 실행, 변경분만 커밋.

Usage:
  python build_danji_pages.py
"""

import os, json, re, time, html as html_mod
import requests

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
DANJI_DIR = os.path.join(BASE_DIR, "danji")


# ── 유틸 ──────────────────────────────────────────────────
def esc(s):
    return html_mod.escape(str(s)) if s else ""

REGION_MAP = {
    # 정식 명칭
    "서울특별시": "서울", "인천광역시": "인천", "부산광역시": "부산",
    "대구광역시": "대구", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북",
    "경상남도": "경남", "제주특별자치도": "제주",
    # 약칭 (DB에 혼재)
    "서울": "서울", "인천": "인천", "부산": "부산", "대구": "대구",
    "광주": "광주", "대전": "대전", "울산": "울산", "세종": "세종",
    "경기": "경기", "강원": "강원", "충북": "충북", "충남": "충남",
    "전북": "전북", "전남": "전남", "경북": "경북", "경남": "경남",
    "제주": "제주",
}
METRO_CITIES = {"서울", "인천", "부산", "대구", "광주", "대전", "울산"}

def detect_region(address):
    """도로명주소에서 지역 약칭 반환"""
    if not address:
        return ""
    for full, short in REGION_MAP.items():
        if address.strip().startswith(full):
            return short
    return ""

def _clean(s):
    s = re.sub(r'[^\w가-힣]', '-', s or "")
    return re.sub(r'-+', '-', s).strip('-')

def make_slug(name, location, did, address=""):
    """address 기반 전국 slug 생성
    광역시: 서울-강동구-둔촌현대4차-a13481802
    도:     경기-성남-분당구-아파트명-id
    """
    addr_parts = (address or "").split()
    region = ""
    if addr_parts:
        region = REGION_MAP.get(addr_parts[0], "")

    slug_parts = []

    if region:
        slug_parts.append(region)

        if region in METRO_CITIES:
            # 광역시: 바로 구 (addr_parts[1] = "강동구")
            if len(addr_parts) > 1 and addr_parts[1].endswith("구"):
                slug_parts.append(addr_parts[1])
        elif region == "세종":
            pass  # 구 없음
        else:
            # 도: 시/군 + 구(있으면)
            if len(addr_parts) > 1:
                city = re.sub(r'(시|군)$', '', addr_parts[1])
                slug_parts.append(city)
            if len(addr_parts) > 2 and addr_parts[2].endswith("구"):
                slug_parts.append(addr_parts[2])
    else:
        # address 없으면 location fallback (구만)
        loc_parts = (location or "").split(" ")
        if loc_parts and loc_parts[0]:
            slug_parts.append(_clean(loc_parts[0]))

    # offi-/apt- 형태는 ID에 이미 단지명 포함
    if did and (did.startswith("offi-") or did.startswith("apt-")):
        slug_parts.append(did)
    else:
        slug_parts.append(_clean(name))
        slug_parts.append(did or "")

    return "-".join([_clean(p) for p in slug_parts if p])

def format_price(manwon):
    if not manwon:
        return "-"
    manwon = int(manwon)
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
    return f"{round(m / 67)}분"


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
                          "nearby_subway,nearby_school,nearby_complex,"
                          "lat,lng,top_floor,parking,heating,builder,updated_at",
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


# ── CSS/JS 추출 ───────────────────────────────────────────
def extract_css_js():
    """danji.html에서 CSS와 메인 JS를 추출하여 외부 파일로 분리"""
    path = os.path.join(BASE_DIR, "danji.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # CSS
    css_m = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
    css = css_m.group(1).strip() if css_m else ""

    # 메인 JS (const sb = supabase.createClient 부터 마지막 </script> 전까지)
    js_m = re.search(
        r"<script>\s*\nconst sb = supabase\.createClient.*?</script>",
        content, re.DOTALL,
    )
    if js_m:
        js = js_m.group(0)
        js = js.replace("<script>", "", 1)
        js = js[:js.rfind("</script>")]
        js = js.strip()
    else:
        # 폴백: 가장 큰 script 블록
        blocks = re.findall(r"<script>(.*?)</script>", content, re.DOTALL)
        js = max(blocks, key=len) if blocks else ""

    # ── JS 수정: URL 경로에서도 ID 추출 (slug에서 맨 뒤 ID) ──
    js = js.replace(
        "const id = new URLSearchParams(location.search).get('id');",
        "const id = new URLSearchParams(location.search).get('id')"
        " || (location.pathname.match(/-(a\\d+)(?:\\.html)?$/) || [])[1]"
        " || (location.pathname.match(/((?:offi|apt)-[^/]+?)(?:\\.html)?$/) || [])[1]"
        " || null;",
        1,
    )

    # ── JS 수정: canonical/og:url을 새 경로에 맞게 ──
    js = js.replace(
        "canonicalEl.href = `https://hwik.kr/danji.html?id=${encodeURIComponent(id)}`;",
        "canonicalEl.href = location.pathname.includes('/danji/')"
        " ? `https://hwik.kr/danji/${encodeURIComponent(id)}`"
        " : `https://hwik.kr/danji.html?id=${encodeURIComponent(id)}`;",
    )
    js = js.replace(
        "if (ogUrl) ogUrl.content = `https://hwik.kr/danji.html?id=${encodeURIComponent(id)}`;",
        "if (ogUrl) ogUrl.content = location.pathname.includes('/danji/')"
        " ? `https://hwik.kr/danji/${encodeURIComponent(id)}`"
        " : `https://hwik.kr/danji.html?id=${encodeURIComponent(id)}`;",
    )

    # ── JS 수정: 404 리다이렉트도 경로 호환 ──
    js = js.replace(
        "var fullUrl = 'https://hwik.kr/danji.html?id=' + encodeURIComponent(id);",
        "var fullUrl = location.pathname.includes('/danji/')"
        " ? 'https://hwik.kr/danji/' + encodeURIComponent(id)"
        " : 'https://hwik.kr/danji.html?id=' + encodeURIComponent(id);",
    )

    return css, js


# ── 단지별 SEO 콘텐츠 생성 ────────────────────────────────
def best_price_cat(d):
    """84㎡에 가장 가까운 거래 있는 면적 반환"""
    cats = d.get("categories") or []
    rt = d.get("recent_trade") or {}
    best, best_diff = None, 999
    for c in cats:
        if rt.get(c) and (rt[c].get("price") or 0) > 0:
            diff = abs(int(c) - 84)
            if diff < best_diff:
                best_diff = diff
                best = c
    return best


def build_fallback_html(d):
    """Googlebot이 읽는 정적 SEO 콘텐츠"""
    name = esc(d.get("complex_name", ""))
    loc = esc(d.get("location", ""))
    loc_parts = (d.get("location") or "").split(" ")
    gu = esc(loc_parts[0]) if loc_parts else ""
    addr = esc(d.get("address", ""))
    year = d.get("build_year", "")
    units = d.get("total_units", "")
    builder = esc(d.get("builder", ""))

    cats = d.get("categories") or []
    rt = d.get("recent_trade") or {}
    high = d.get("all_time_high") or {}
    jr = d.get("jeonse_rate")

    bc = best_price_cat(d)
    lines = []

    # 기본 정보
    info = f"{loc}"
    if units:
        info += f" · {units:,}세대" if isinstance(units, int) else f" · {units}세대"
    if year:
        info += f" · {year}년"
    if builder:
        info += f" · {builder}"
    lines.append(f'<p style="font-size:13px;color:#6b7280;margin-bottom:16px;">{info}</p>')

    # 시세
    if bc and rt.get(bc):
        r = rt[bc]
        txt = f"전용 {bc}㎡ 최근 매매가: {format_price(r.get('price'))}"
        if r.get("date"):
            txt += f" ({r['date']})"
        lines.append(f'<p style="font-size:15px;font-weight:600;margin-bottom:6px;">{txt}</p>')
    if bc and high.get(bc):
        h = high[bc]
        txt = f"역대 최고가: {format_price(h.get('price'))}"
        if h.get("date"):
            txt += f" ({h['date']})"
        lines.append(f'<p style="font-size:13px;color:#6b7280;margin-bottom:6px;">{txt}</p>')
    if jr:
        lines.append(f'<p style="font-size:13px;color:#6b7280;margin-bottom:6px;">전세가율: {jr}%</p>')

    # 면적 목록
    if cats:
        area_list = ", ".join(f"전용 {c}㎡" for c in cats)
        lines.append(f'<p style="font-size:12px;color:#9ca3af;margin-bottom:12px;">면적: {area_list}</p>')

    # 지하철
    subway = d.get("nearby_subway") or []
    if subway:
        items = [f"{esc(s.get('name',''))}({esc(s.get('line',''))}) 도보 {walk_min(s.get('distance'))}" for s in subway[:3]]
        lines.append(f'<p style="font-size:12px;color:#9ca3af;margin-bottom:4px;">인근 지하철: {", ".join(items)}</p>')

    # 학교
    school = d.get("nearby_school") or []
    if school:
        items = [f"{esc(s.get('name',''))} 도보 {walk_min(s.get('distance'))}" for s in school[:2]]
        lines.append(f'<p style="font-size:12px;color:#9ca3af;margin-bottom:12px;">인근 학교: {", ".join(items)}</p>')

    # 단지 스펙
    specs = []
    if d.get("top_floor"):
        specs.append(f"최고 {d['top_floor']}층")
    pk = int(d.get("parking") or 0)
    if pk > 0:
        specs.append(f"주차 {pk:,}대")
        if units and isinstance(units, int) and units > 0:
            specs.append(f"(세대당 {pk/units:.1f}대)")
    if d.get("heating"):
        specs.append(esc(d["heating"]))
    if specs:
        lines.append(f'<p style="font-size:12px;color:#9ca3af;margin-bottom:12px;">{", ".join(specs)}</p>')

    # 주변 단지
    nearby = d.get("nearby_complex") or []
    if nearby:
        lines.append('<h2 style="font-size:14px;font-weight:600;margin:16px 0 8px;">주변 단지</h2>')
        lines.append('<ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:6px;">')
        for n in nearby[:5]:
            prices = n.get("prices") or {}
            nbest = None
            ndiff = 999
            for k, v in prices.items():
                diff = abs(int(k) - 84)
                if diff < ndiff:
                    ndiff = diff
                    nbest = v
            p = format_price(nbest.get("price")) if nbest and nbest.get("price") else "-"
            nid = n.get("id", "")
            nname_raw = n.get("name", "")
            nloc_raw = n.get("location", "")
            nslug = make_slug(nname_raw, nloc_raw, nid, d.get("address", ""))
            nname = esc(nname_raw)
            nloc = esc(nloc_raw)
            lines.append(
                f'<li><a href="/danji/{nslug}" style="display:flex;justify-content:space-between;'
                f'padding:10px 12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">'
                f'<span>{nname} <span style="color:#9ca3af;font-size:11px;">{nloc}</span></span>'
                f'<span style="font-weight:600;">{p}</span></a></li>'
            )
        lines.append("</ul>")

    # FAQ
    faq = []
    if bc and rt.get(bc):
        r = rt[bc]
        a = f"최근 매매 실거래가는 {format_price(r.get('price'))}입니다."
        if r.get("date"):
            a += f" ({r['date']} 기준)"
        faq.append((f"{name} 최근 실거래가는?", a))
    if jr:
        faq.append((f"{name} 전세가율은?", f"{name}의 전세가율은 {jr}%입니다."))
    if bc and high.get(bc):
        h = high[bc]
        a = f"역대 최고가는 {format_price(h.get('price'))}입니다."
        if h.get("date"):
            a += f" ({h['date']})"
        faq.append((f"{name} 역대 최고가는?", a))
    if subway:
        a = ", ".join(f"{esc(s.get('name',''))}({esc(s.get('line',''))}) 도보 {walk_min(s.get('distance'))}" for s in subway[:3])
        faq.append((f"{name} 근처 지하철역은?", a))
    if faq:
        lines.append('<h2 style="font-size:14px;font-weight:600;margin:16px 0 8px;">자주 묻는 질문</h2>')
        for q, a in faq:
            lines.append(f'<div style="border-bottom:1px solid #e5e7eb;padding:10px 0;">')
            lines.append(f'<div style="font-size:13px;font-weight:500;margin-bottom:4px;">{esc(q)}</div>')
            lines.append(f'<div style="font-size:12px;color:#6b7280;line-height:1.6;">{a}</div>')
            lines.append("</div>")

    # SEO 서술형 텍스트
    seo = []
    seo.append(f"{name}은(는) {addr}에 위치한 {year}년 준공 아파트입니다." if addr and year else "")
    if units:
        u = f"{units:,}" if isinstance(units, int) else str(units)
        seo.append(f"총 {u}세대 규모입니다.")
    if bc and rt.get(bc):
        seo.append(f"최근 매매 실거래가는 {format_price(rt[bc].get('price'))}입니다.")
    seo_text = " ".join(s for s in seo if s)
    if seo_text:
        lines.append(f'<p style="font-size:11px;color:#9ca3af;line-height:1.7;margin-top:16px;">{esc(seo_text)}</p>')

    lines.append('<p style="font-size:10px;color:#9ca3af;margin-top:8px;">실거래가 출처: 국토교통부 실거래가 공개시스템 · 매일 업데이트</p>')

    # 내부 링크
    loc_parts_raw = (d.get("location") or "").split(" ", 1)
    dong_name = loc_parts_raw[1] if len(loc_parts_raw) >= 2 else ""
    if dong_name:
        dong_slug_str = f"{loc_parts_raw[0]}-{dong_name}"
        dong_slug_str = re.sub(r'[^\w가-힣]', '-', dong_slug_str)
        dong_slug_str = re.sub(r'-+', '-', dong_slug_str).strip('-')
    lines.append('<div style="margin-top:16px;display:flex;flex-direction:column;gap:8px;">')
    if dong_name:
        lines.append(f'<a href="/dong/{dong_slug_str}" style="padding:12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">{esc(dong_name)} 다른 단지 시세 →</a>')
    lines.append(f'<a href="/gu.html?name={gu}" style="padding:12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">{gu} 전체 시세 →</a>')
    lines.append('<a href="/ranking.html" style="padding:12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">아파트 순위 →</a>')
    lines.append("</div>")

    return "\n    ".join(lines)


def build_jsonld(d):
    """JSON-LD 구조화 데이터"""
    did = d.get("id", "")
    name = d.get("complex_name", "")
    loc_parts = (d.get("location") or "").split(" ")
    gu = loc_parts[0] if loc_parts else ""
    slug = make_slug(name, d.get("location", ""), did, d.get("address", ""))

    graph = [
        {
            "@type": "Residence",
            "name": name,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": d.get("location", ""),
                "streetAddress": d.get("address", ""),
                "addressCountry": "KR",
            },
        },
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
                {"@type": "ListItem", "position": 2, "name": f"{gu}", "item": f"https://hwik.kr/gu.html?name={gu}"},
                {"@type": "ListItem", "position": 3, "name": name, "item": f"https://hwik.kr/danji/{slug}"},
            ],
        },
    ]
    if d.get("lat") and d.get("lng"):
        graph[0]["geo"] = {"@type": "GeoCoordinates", "latitude": d["lat"], "longitude": d["lng"]}
    if d.get("build_year"):
        graph[0]["yearBuilt"] = d["build_year"]
    if d.get("total_units"):
        graph[0]["numberOfRooms"] = d["total_units"]

    # FAQ
    bc = best_price_cat(d)
    rt = d.get("recent_trade") or {}
    jr = d.get("jeonse_rate")
    faq_items = []
    if bc and rt.get(bc):
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 최근 실거래가는?",
            "acceptedAnswer": {"@type": "Answer", "text": f"최근 매매 실거래가는 {format_price(rt[bc].get('price'))}입니다."},
        })
    if jr:
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 전세가율은?",
            "acceptedAnswer": {"@type": "Answer", "text": f"{name}의 전세가율은 {jr}%입니다."},
        })
    if faq_items:
        graph.append({"@type": "FAQPage", "mainEntity": faq_items})

    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


# ── 페이지 생성 ───────────────────────────────────────────
def generate_page(d):
    did = d.get("id", "")
    raw_name = d.get("complex_name", "")
    raw_loc = d.get("location", "")
    slug = make_slug(raw_name, raw_loc, did, d.get("address", ""))
    name = esc(raw_name)
    loc = esc(raw_loc)
    loc_parts = raw_loc.split(" ")
    gu = esc(loc_parts[0]) if loc_parts else ""
    units = d.get("total_units", "")
    year = d.get("build_year", "")

    desc_parts = [name, loc]
    if units:
        desc_parts.append(f"{units}세대")
    if year:
        desc_parts.append(f"{year}년")
    desc_parts.append("아파트 실거래가, 전세가, 시세 추이")
    desc = " ".join(desc_parts)

    canonical = f"https://hwik.kr/danji/{slug}"
    jsonld = build_jsonld(d)
    fallback = build_fallback_html(d)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>{name} 실거래가 시세 - 휙</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="canonical" id="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="휙">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" id="og-title" content="{name} 실거래가 시세 - 휙">
<meta property="og:description" id="og-desc" content="{esc(desc)}">
<meta property="og:image" content="https://hwik.kr/og-image.png">
<meta property="og:url" id="og-url" content="{canonical}">
<meta name="google-site-verification" content="R2ye41AVVTRs8BxEXyEafFSTqMSiHKdb9zgTklrktSI" />
<meta name="naver-site-verification" content="367bd1e77a8ad48b74e345be3e4a0f8125c2c4e1" />
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2DVQXMLC9J"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-2DVQXMLC9J');</script>
<meta name="twitter:card" content="summary">
<meta name="twitter:title" id="tw-title" content="{name} 실거래가 시세 - 휙">
<meta name="twitter:description" id="tw-desc" content="{esc(desc)}">
<script type="application/ld+json">{jsonld}</script>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="wrap" id="app">
  <div class="loading" id="loading">
    <div class="loading-spinner"></div>
    <div class="loading-text">단지 정보 불러오는 중...</div>
  </div>
  <div id="fallback-content" style="padding:20px;">
    <nav style="font-size:11px;color:#9ca3af;margin-bottom:12px;">
      <a href="/" style="color:#6b7280;text-decoration:none;">휙</a> &gt;
      <a href="/gu.html?name={gu}" style="color:#6b7280;text-decoration:none;">{gu}</a> &gt;
      {name}
    </nav>
    <h1 style="font-size:18px;font-weight:700;margin-bottom:8px;">{name} 실거래가</h1>
    {fallback}
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script src="/config.js"></script>
<script src="app.js?v={int(time.time())}"></script>
</body>
</html>"""


# ── 메인 ──────────────────────────────────────────────────
def main():
    import sys
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

    os.makedirs(DANJI_DIR, exist_ok=True)

    print("danji_pages 조회 중...")
    all_danji = fetch_all_danji()
    print(f"{len(all_danji)}개 단지 로드")

    print("CSS/JS 추출 중...")
    css, js = extract_css_js()

    with open(os.path.join(DANJI_DIR, "style.css"), "w", encoding="utf-8") as f:
        f.write(css)
    print(f"  style.css ({len(css):,} bytes)")

    with open(os.path.join(DANJI_DIR, "app.js"), "w", encoding="utf-8") as f:
        f.write(js)
    print(f"  app.js ({len(js):,} bytes)")

    count = 0
    skipped = 0
    for d in all_danji:
        did = d.get("id", "")
        if not did:
            continue
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []
        has_trade = any(rt.get(c) for c in cats)
        if not has_trade:
            skipped += 1
            continue

        slug = make_slug(d.get("complex_name", ""), d.get("location", ""), did, d.get("address", ""))
        page = generate_page(d)
        path = os.path.join(DANJI_DIR, f"{slug}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        count += 1
        if count % 1000 == 0:
            print(f"  {count}개 생성...")

    print(f"\n{count}개 페이지 생성, {skipped}개 스킵 (거래 없음)")
    print(f"출력: {DANJI_DIR}/")


if __name__ == "__main__":
    main()
