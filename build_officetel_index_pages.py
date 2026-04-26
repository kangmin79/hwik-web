"""build_officetel_index_pages.py — gu/dong/ranking 페이지 빌드.

URL 패턴 (아파트와 정렬):
  /officetel/gu/{gu_url_slug(sido, sgg)}.html        ← 예: /officetel/gu/고양덕양구.html
  /officetel/dong/{make_dong_slug(sgg, umd, addr)}.html ← 예: /officetel/dong/경기-고양-덕양구-원흥동.html
  /officetel/ranking.html                            ← 전국 거래수 랭킹
  /officetel/ranking-{sido}.html                     ← 시도별 랭킹
  /officetel/                                        ← 전체 목차 (시도 리스트)

모든 스타일은 /danji/style.css 재사용. Chart.js 불필요.
"""
from __future__ import annotations

import html
import json
import os
import sys
import urllib.request
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 아파트 slug_utils 재사용 — dong/gu URL 패턴 일치
sys.path.insert(0, str(Path(__file__).resolve().parent))
from slug_utils import make_dong_slug, gu_url_slug  # noqa: E402

KST = timezone(timedelta(hours=9))
SB = "https://jqaxejgzkchxbfzgzyzi.supabase.co"

# .env 로드 (build_officetel_pages.py와 동일)
def _load_env() -> None:
    here = Path(__file__).resolve().parent
    p = here / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()
SK = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
H = {"apikey": SK, "Authorization": f"Bearer {SK}"}
REST = f"{SB}/rest/v1"

REPO = Path(__file__).resolve().parent
OFFI_ROOT = REPO / "officetel"
GU_DIR = OFFI_ROOT / "gu"
DONG_DIR = OFFI_ROOT / "dong"
BUILD_DATE = datetime.now(KST).strftime("%Y-%m-%d")

for d in (OFFI_ROOT, GU_DIR, DONG_DIR):
    d.mkdir(parents=True, exist_ok=True)


def esc(s):
    return html.escape(s or "", quote=True)


def url_quote(s):
    return urllib.parse.quote(s or "", safe="-")


def _get_all() -> list[dict]:
    out = []
    offset = 0
    while True:
        url = (f"{REST}/officetels?select=id,bld_nm,sido,sgg,umd,slug,url,"
               f"trade_count,build_year,ho_cnt,grnd_flr,jibun_addr,"
               f"road_lat,road_lng,jibun_lat,jibun_lng"
               f"&order=sido,sgg,umd,bld_nm&limit=1000&offset={offset}")
        req = urllib.request.Request(url, headers=H)
        rows = json.loads(urllib.request.urlopen(req, timeout=60).read())
        if not rows:
            break
        out += rows
        offset += 1000
    return out


def _header_html(title: str, desc: str, canonical: str, h1: str,
                 breadcrumb_items: list[tuple[str, str | None]],
                 extra_jsonld: list[dict] | None = None,
                 modified_date: str | None = None) -> str:
    bc = []
    for i, (name, href) in enumerate(breadcrumb_items):
        if href:
            bc.append(f'<a href="{esc(href)}">{esc(name)}</a>')
        else:
            bc.append(f"<span>{esc(name)}</span>")
        if i < len(breadcrumb_items) - 1:
            bc.append("<span>›</span>")
    bc_html = "\n".join(bc)
    jsonld_bc = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1,
             "name": name, **({"item": f"https://hwik.kr{href}"} if href else {})}
            for i, (name, href) in enumerate(breadcrumb_items)
        ],
    }
    jsonld_blocks = (
        f'<script type="application/ld+json">{json.dumps(jsonld_bc, ensure_ascii=False)}</script>\n'
        + "\n".join(
            f'<script type="application/ld+json">{json.dumps(d, ensure_ascii=False)}</script>'
            for d in (extra_jsonld or [])
        )
    )
    mod_iso = modified_date or BUILD_DATE
    return f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="휙">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="https://hwik.kr/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="article:modified_time" content="{esc(mod_iso)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="https://hwik.kr/og-image.png">
<link rel="stylesheet" href="/danji/style.css">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" as="style" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css" media="(min-width: 768px)">
<style>
@media (min-width: 768px) {{
  html, body {{
    background: #F0EEE6 !important;
    font-family: Pretendard, -apple-system, BlinkMacSystemFont,
                 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans CJK KR', sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
    -moz-osx-font-smoothing: grayscale !important;
    text-rendering: optimizeLegibility !important;
  }}
  main.wrap, .breadcrumb, .header, .header *,
  .section, .section *, .nearby-item, .nearby-item *, .seo-text {{
    font-family: Pretendard, -apple-system, BlinkMacSystemFont,
                 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans CJK KR', sans-serif !important;
  }}
  main.wrap {{
    max-width: 720px !important;
    margin: 32px auto !important;
    background: #fff !important;
    border-radius: 20px !important;
    box-shadow: 0 10px 40px rgba(0,0,0,0.08), 0 2px 8px rgba(0,0,0,0.04) !important;
    overflow: hidden !important;
  }}
  .breadcrumb {{
    background: #fff !important;
    padding: 18px 14px 0 !important;
    font-size: 12.5px !important;
    color: #94a3b8 !important;
    display: flex !important; flex-wrap: wrap !important; gap: 4px !important;
  }}
  .breadcrumb a {{
    color: #64748b !important; text-decoration: none !important;
    transition: color 0.15s ease !important;
  }}
  .breadcrumb a:hover {{ color: #4338ca !important; }}
  .header {{
    background: #fff !important;
    padding: 14px 14px 22px !important;
    border-bottom: 1px solid #eef0f4 !important;
    display: block !important;
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
    font-size: 24px !important;
    font-weight: 700 !important;
    color: #4338ca !important;
    letter-spacing: -0.03em !important;
    line-height: 1.25 !important;
  }}
  .seo-text {{
    color: #475569 !important; padding: 16px 14px 0 !important;
    font-size: 13px !important; line-height: 1.85 !important; margin: 0 !important;
  }}
  .divider {{ display: none !important; }}
  .section {{ padding: 20px 4px !important; }}
  .section-title {{
    font-size: 16px !important; font-weight: 700 !important;
    color: #0f172a !important; letter-spacing: -0.025em !important;
    margin: 0 0 14px !important; padding-left: 10px !important;
  }}
  .section ul {{ gap: 8px !important; }}
  .nearby-item {{
    background: #f8fafc !important;
    border: 1px solid #eef0f4 !important;
    border-radius: 10px !important;
    padding: 12px 16px !important;
    transition: all 0.15s ease !important;
  }}
  .nearby-item:hover {{
    background: #eef2ff !important;
    border-color: #c7d2fe !important;
    transform: translateX(2px) !important;
    box-shadow: 0 4px 12px rgba(67,56,202,0.08) !important;
  }}
  .nearby-item > span:first-child,
  .nearby-item span:first-child > span:first-child {{
    color: #1e293b !important; font-size: 14px !important;
    font-weight: 700 !important; letter-spacing: -0.015em !important;
    transition: color 0.15s ease !important;
  }}
  .nearby-item:hover > span:first-child,
  .nearby-item:hover span:first-child > span:first-child {{
    color: #4338ca !important;
  }}
  .nearby-item span:first-child > span:nth-child(2),
  .nearby-item > span:nth-child(2) {{
    color: #64748b !important; font-size: 12px !important; font-weight: 500 !important;
  }}
  .seo-section {{ background: #fafafa !important; padding: 16px 14px !important; }}
  .seo-source {{ color: #94a3b8 !important; font-size: 11px !important; }}
}}
</style>
{jsonld_blocks}
</head>
<body>
<main class="wrap" role="main">

<nav class="breadcrumb" aria-label="breadcrumb">
{bc_html}
</nav>

<header class="header">
<div class="header-top">
<a class="logo" href="/" style="text-decoration:none;">휙</a>
<div><h1 class="header-name" style="font-size:22px;font-weight:700;color:#fff;margin:0;letter-spacing:-0.02em;">{esc(h1)}</h1></div>
</div>
</header>
"""


def _card_link(o: dict, show_sgg: bool = False) -> str:
    url = o.get("url") or ""
    if not url:
        return ""
    sub_bits = []
    if show_sgg and o.get("sgg"):
        sub_bits.append(esc(o["sgg"]) + (" " + esc(o.get("umd") or "") if o.get("umd") else ""))
    elif o.get("umd"):
        sub_bits.append(esc(o["umd"]))
    if o.get("build_year"):
        sub_bits.append(f"{o['build_year']}년")
    if o.get("ho_cnt"):
        try:
            sub_bits.append(f"{int(o['ho_cnt']):,}호")
        except Exception:
            pass
    if o.get("trade_count"):
        try:
            sub_bits.append(f"거래 {int(o['trade_count']):,}건")
        except Exception:
            pass
    sub = " · ".join(sub_bits)
    name = esc(o.get("bld_nm") or "")
    # SEO anchor 풍부화: title 속성에 컨텍스트 + 키워드
    umd_for_title = esc(o.get("umd") or "")
    title_attr = f"{name} 실거래가 시세"
    if umd_for_title:
        title_attr = f"{name} 실거래가 시세 · {umd_for_title} 오피스텔"
    return (f'<li><a class="nearby-item" href="{esc(url)}" title="{title_attr}" '
            f'style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:10px 12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;gap:12px;">'
            f'<span style="display:flex;flex-direction:column;gap:4px;min-width:0;">'
            f'<span style="font-weight:600;">{name}</span>'
            f'<span style="color:#6b7280;font-size:11px;">{sub}</span>'
            f'</span></a></li>')


def _footer_html() -> str:
    return f"""
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
<div class="seo-source" style="margin-top:8px;font-size:11px;color:var(--muted);">실거래가 출처: 국토교통부 · 최종 데이터 확인: <time datetime="{BUILD_DATE}">{BUILD_DATE}</time></div>
</div>

</main>

<footer style="max-width:720px;margin:24px auto 40px;padding:24px 16px 0;border-top:1px solid var(--border,#e5e7eb);text-align:center;font-size:11.5px;color:var(--sub,#6b7280);line-height:1.7;">
<div style="margin-bottom:8px;">
<a href="/about.html" style="color:var(--sub,#6b7280);text-decoration:none;margin:0 8px;">휙 소개</a>·
<a href="/privacy.html" style="color:var(--sub,#6b7280);text-decoration:none;margin:0 8px;">개인정보처리방침</a>·
<a href="/terms.html" style="color:var(--sub,#6b7280);text-decoration:none;margin:0 8px;">이용약관</a>
</div>
<div style="color:var(--muted,#9ca3af);">실거래가 출처: 국토교통부 · 휙(HWIK) · <a href="https://hwik.kr" style="color:var(--muted,#9ca3af);text-decoration:none;">hwik.kr</a></div>
</footer>

</body></html>
"""


def _intro(text: str) -> str:
    return (f'<p class="seo-text" style="font-size:12px;color:var(--sub);'
            f'line-height:1.8;margin:12px 16px;">{esc(text)}</p>')


def _list_section(title: str, rows: list[dict], show_sgg: bool = False) -> str:
    if not rows:
        return ""
    items = "".join(_card_link(o, show_sgg=show_sgg) for o in rows if (o.get("url")))
    if not items:
        return ""
    return (f'<div class="divider"></div>'
            f'<div class="section" style="padding:16px;">'
            f'<h2 class="section-title">{esc(title)}</h2>'
            f'<ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:6px;">'
            f'{items}</ul></div>')


def _dong_links_section(gu_offis: list[dict]) -> str:
    # 동별 그룹 링크
    dmap = defaultdict(list)
    for o in gu_offis:
        key = (o.get("sido"), o.get("sgg"), o.get("umd"))
        if all(key):
            dmap[key].append(o)
    if not dmap:
        return ""
    items = []
    for (sido, sgg, umd), lst in sorted(dmap.items(), key=lambda x: -len(x[1])):
        first_addr = (lst[0].get("jibun_addr") or "")
        slug = make_dong_slug(sgg, umd, first_addr)
        href = f"/officetel/dong/{url_quote(slug)}.html"
        # SEO anchor: title 속성으로 키워드 + 컨텍스트
        title_attr = f"{esc(sido)} {esc(sgg)} {esc(umd)} 오피스텔 {len(lst)}개 단지 시세"
        items.append(
            f'<li><a class="nearby-item" href="{esc(href)}" title="{title_attr}" '
            f'aria-label="{title_attr}" '
            f'style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:10px 12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">'
            f'<span style="font-weight:600;">{esc(umd)}</span>'
            f'<span style="color:#6b7280;font-size:11px;">{len(lst)}개 단지</span>'
            f'</a></li>'
        )
    return (f'<div class="divider"></div>'
            f'<div class="section" style="padding:16px;">'
            f'<h2 class="section-title">동 선택</h2>'
            f'<ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:6px;">'
            + "".join(items) + '</ul></div>')


_APARTMENT_GU_SET = None
_APARTMENT_DONG_SET = None


def _apt_gu_url(sido: str, sgg: str) -> str | None:
    """아파트 gu 페이지 URL 매핑 (존재하는 파일만 반환)."""
    global _APARTMENT_GU_SET
    if _APARTMENT_GU_SET is None:
        from pathlib import Path as _P
        apt_dir = _P(__file__).parent / "gu"
        if apt_dir.exists():
            _APARTMENT_GU_SET = {p.stem for p in apt_dir.glob("*.html")}
        else:
            _APARTMENT_GU_SET = set()
    candidates = [sgg, f"{sido}-{sgg}"]
    for c in candidates:
        if c in _APARTMENT_GU_SET:
            return f"/gu/{c}.html"
    return None


def _apt_dong_url(slug: str) -> str | None:
    """아파트 dong 페이지 URL 매핑 (존재하는 파일만 반환)."""
    global _APARTMENT_DONG_SET
    if _APARTMENT_DONG_SET is None:
        from pathlib import Path as _P
        apt_dir = _P(__file__).parent / "dong"
        if apt_dir.exists():
            _APARTMENT_DONG_SET = {p.stem for p in apt_dir.glob("*.html")}
        else:
            _APARTMENT_DONG_SET = set()
    if slug in _APARTMENT_DONG_SET:
        return f"/dong/{slug}.html"
    return None


def build_gu_page(sido: str, sgg: str, offis: list[dict],
                  gu_map: dict[tuple[str, str], list[dict]] | None = None) -> Path:
    gu_slug = gu_url_slug(sido, sgg)
    h1 = f"{sido} {sgg} 오피스텔 실거래"
    title = f"{sido} {sgg} 오피스텔 실거래가 시세 · {len(offis):,}개 단지 | 휙"
    canonical = f"https://hwik.kr/officetel/gu/{url_quote(gu_slug)}.html"
    bc = [("휙", "/"), (sido, None), (f"{sido} {sgg}", None)]

    # 단지 수 상위 동 3개 자동 추출
    _local_dong: dict[str, int] = {}
    for o in offis:
        ud = o.get("umd")
        if ud:
            _local_dong[ud] = _local_dong.get(ud, 0) + 1
    _top_dongs = sorted(_local_dong.items(), key=lambda x: -x[1])[:3]
    _top_dong = "·".join(d for d, _ in _top_dongs)
    _focus = f"{_top_dong} 등 " if _top_dong else ""

    # 거래량 합계 (E-E-A-T 신호)
    _total_trades = sum((o.get("trade_count") or 0) for o in offis)

    # 풍부 description (롱테일 키워드 포함, ~130자)
    desc = (f"{sido} {sgg}의 오피스텔 매매·전세·월세 실거래가와 시세를 동별로 비교하세요. "
            f"{_focus}{len(offis):,}개 단지, 국토교통부 공개시스템 기반.")

    # 거래 상위 20개 단지 (ItemList용 + 본문)
    top = sorted(offis, key=lambda o: -(o.get("trade_count") or 0))[:20]

    # ── 강남구 중심 좌표 (단지 좌표 평균) ───────────────────────
    _lats = [o.get("road_lat") or o.get("jibun_lat") for o in offis]
    _lngs = [o.get("road_lng") or o.get("jibun_lng") for o in offis]
    _lats = [x for x in _lats if x]
    _lngs = [x for x in _lngs if x]
    geo_block = None
    if _lats and _lngs:
        geo_block = {
            "@type": "GeoCoordinates",
            "latitude": round(sum(_lats) / len(_lats), 6),
            "longitude": round(sum(_lngs) / len(_lngs), 6),
        }

    # ── JSON-LD: Organization (publisher) ──────────────────────
    jsonld_org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": "https://hwik.kr/#org",
        "name": "휙 (HWIK)",
        "url": "https://hwik.kr",
        "logo": {
            "@type": "ImageObject",
            "url": "https://hwik.kr/og-image.png",
            "width": 1200,
            "height": 630,
        },
        "sameAs": ["https://hwik.kr"],
    }

    # ── JSON-LD: CollectionPage + ItemList ─────────────────────
    item_list_elements = []
    for i, o in enumerate(top):
        if not (o.get("url") and o.get("bld_nm")):
            continue
        bits = []
        if o.get("umd"):
            bits.append(o["umd"])
        if o.get("trade_count"):
            bits.append(f"실거래 {int(o['trade_count']):,}건")
        item_list_elements.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": f"https://hwik.kr{o['url']}",
            "name": o["bld_nm"],
            "description": " · ".join(bits) if bits else None,
        })
    # None 값 제거
    for it in item_list_elements:
        if it.get("description") is None:
            del it["description"]

    place_block = {
        "@type": "AdministrativeArea",
        "name": f"{sido} {sgg}",
        "containedInPlace": {
            "@type": "AdministrativeArea",
            "name": sido,
            "containedInPlace": {"@type": "Country", "name": "대한민국"},
        },
    }
    if geo_block:
        place_block["geo"] = geo_block

    jsonld_collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title.split(" | ")[0],
        "description": desc,
        "url": canonical,
        "inLanguage": "ko-KR",
        "datePublished": "2026-01-01",
        "dateModified": BUILD_DATE,
        "isPartOf": {"@type": "WebSite", "name": "휙", "url": "https://hwik.kr"},
        "publisher": {"@id": "https://hwik.kr/#org"},
        "about": place_block,
        "mainEntity": {
            "@type": "ItemList",
            "name": f"{sgg} 오피스텔 거래 상위 단지",
            "numberOfItems": len(item_list_elements),
            "itemListElement": item_list_elements,
        },
    }
    jsonld_place = dict(place_block, **{"@context": "https://schema.org"})
    faq_qas = [
        (f"{sido} {sgg} 오피스텔 단지 수는 몇 개인가요?",
         f"{sido} {sgg}에는 최근 5년 실거래 10건 이상의 오피스텔 {len(offis):,}개 단지가 있습니다. "
         f"국토교통부 실거래가 공개시스템 기준으로 집계됩니다."),
    ]
    if _top_dong:
        faq_qas.append((
            f"{sgg}에서 오피스텔 단지가 많은 동은 어디인가요?",
            f"{sgg}에서는 {_top_dong} 일대에 오피스텔이 가장 많이 분포합니다. "
            f"각 동 페이지에서 단지별 실거래가·시세를 확인할 수 있습니다."
        ))
    if _total_trades:
        faq_qas.append((
            f"{sgg} 오피스텔 실거래는 얼마나 많이 발생하나요?",
            f"최근 5년간 {sgg} 오피스텔 단지에서 총 {_total_trades:,}건의 실거래(매매·전세·월세 합산)가 신고되었습니다."
        ))
    faq_qas.append((
        f"{sgg} 오피스텔 실거래가 데이터 출처는 어디인가요?",
        f"국토교통부 실거래가 공개시스템(rt.molit.go.kr) 데이터를 매일 자동 수집하여 반영합니다."
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

    html_out = _header_html(title, desc, canonical, h1, bc,
                            extra_jsonld=[jsonld_org, jsonld_collection, jsonld_place, jsonld_faq])
    html_out += _intro(
        f"{sido} {sgg}의 오피스텔 {len(offis):,}개 단지 시세를 한 번에 확인하세요. "
        f"최근 5년 실거래 10건 이상 단지만 모았으며, {_focus}{sgg} 핵심 입지의 "
        f"오피스텔 매매·전세·월세 실거래가와 평형별 시세, 주변 단지 비교까지 제공합니다. "
        + (f"단지 전체 누적 실거래는 {_total_trades:,}건. " if _total_trades else "")
        + f"모든 데이터는 국토교통부 실거래가 공개시스템 기반입니다."
    )
    html_out += _dong_links_section(offis)

    # 거래 상위 3개 단지를 본문 인용 (인터널 링크 + 통계 fact → E-E-A-T)
    top3 = [o for o in top[:3] if o.get("url") and o.get("bld_nm") and o.get("trade_count")]
    if top3:
        bits = []
        for rank, o in enumerate(top3, start=1):
            anchor = (f'<a href="{esc(o["url"])}" '
                      f'style="color:#4338ca;text-decoration:none;font-weight:600;">'
                      f'{esc(o["bld_nm"])}</a>')
            tc = int(o.get("trade_count") or 0)
            umd_e = esc(o.get("umd") or "")
            if rank == 1:
                bits.append(f"거래량 1위는 {umd_e}의 {anchor}로 누적 실거래 {tc:,}건")
            else:
                bits.append(f"{rank}위 {anchor} ({umd_e} · {tc:,}건)")
        top_text = (
            f'<p class="seo-text" style="font-size:12px;color:var(--sub);'
            f'line-height:1.85;margin:12px 16px;">'
            f'{esc(sgg)} 오피스텔 중 {", ".join(bits)} 입니다. '
            f'아래 거래 상위 단지 목록에서 평형·실거래가·주변 단지 비교를 확인하세요.'
            f'</p>'
        )
        html_out += top_text

    html_out += _list_section(f"{sgg} 거래 상위 20개", top)

    # ── 관련 페이지: 시도 랭킹 + 아파트 + 인접 구 + 시도 인기 구 ──
    sido_slug = url_quote(sido)

    # 1) 같은 시도 다른 구 좌표/거래량 집계
    other_gus_in_sido: list[dict] = []
    if gu_map:
        for (sd, sg), lst in gu_map.items():
            if sd != sido or sg == sgg:
                continue
            lats = [o.get("road_lat") or o.get("jibun_lat") for o in lst]
            lngs = [o.get("road_lng") or o.get("jibun_lng") for o in lst]
            lats = [x for x in lats if x]
            lngs = [x for x in lngs if x]
            if not lats or not lngs:
                continue
            other_gus_in_sido.append({
                "sido": sd, "sgg": sg, "count": len(lst),
                "trades": sum((o.get("trade_count") or 0) for o in lst),
                "lat": sum(lats) / len(lats),
                "lng": sum(lngs) / len(lngs),
            })

    # 2) 인접 구 5개 (현재 구 중심으로부터 거리)
    adjacent: list[dict] = []
    if other_gus_in_sido and geo_block:
        cur_lat = geo_block["latitude"]
        cur_lng = geo_block["longitude"]
        for g in other_gus_in_sido:
            g["dist"] = ((g["lat"] - cur_lat) ** 2 + (g["lng"] - cur_lng) ** 2) ** 0.5
        adjacent = sorted(other_gus_in_sido, key=lambda g: g["dist"])[:5]

    # 3) 같은 시도 거래량 TOP 5 구
    top5_by_trades = sorted(other_gus_in_sido, key=lambda g: -g["trades"])[:5]

    # 4) 아파트 cross-link
    apt_url = _apt_gu_url(sido, sgg)

    # ── HTML 빌드 ─────────────────────────────────────────────
    def _link_row(href: str, label: str, hint: str = "") -> str:
        hint_html = (f'<span style="color:#64748b;font-size:11px;">{esc(hint)}</span>'
                     if hint else "")
        return (
            f'<li><a class="nearby-item" href="{esc(href)}" '
            f'style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:10px 12px;background:#f3f4f6;border-radius:8px;'
            f'text-decoration:none;color:#0f172a;font-size:13px;">'
            f'<span style="font-weight:600;">{esc(label)}</span>'
            f'{hint_html}'
            f'</a></li>'
        )

    related_blocks: list[str] = []

    # 4a) 시도 랭킹 + 아파트 (한 묶음)
    primary_items = [
        _link_row(f"/officetel/ranking-{sido_slug}.html",
                  f"{sido} 오피스텔 거래량 랭킹 TOP 100", "시도 비교"),
    ]
    if apt_url:
        primary_items.append(
            _link_row(apt_url, f"{sido} {sgg} 아파트 시세", "아파트 보기")
        )
    related_blocks.append(
        f'<h3 style="font-size:13px;color:#475569;font-weight:600;margin:0 0 8px;">'
        f'전체 보기</h3>'
        f'<ul style="list-style:none;padding:0;margin:0 0 16px;'
        f'display:flex;flex-direction:column;gap:6px;">'
        + "".join(primary_items) + '</ul>'
    )

    # 4b) 인접 구
    if adjacent:
        adj_items = []
        for g in adjacent:
            href = f"/officetel/gu/{url_quote(gu_url_slug(g['sido'], g['sgg']))}.html"
            hint = f"{g['count']:,}개 단지"
            adj_items.append(_link_row(href, f"{g['sgg']} 오피스텔", hint))
        related_blocks.append(
            f'<h3 style="font-size:13px;color:#475569;font-weight:600;margin:0 0 8px;">'
            f'📍 {esc(sgg)} 인접 구</h3>'
            f'<ul style="list-style:none;padding:0;margin:0 0 16px;'
            f'display:flex;flex-direction:column;gap:6px;">'
            + "".join(adj_items) + '</ul>'
        )

    # 4c) 시도 거래량 TOP 5 구
    if top5_by_trades:
        top_items = []
        for g in top5_by_trades:
            href = f"/officetel/gu/{url_quote(gu_url_slug(g['sido'], g['sgg']))}.html"
            hint = f"실거래 {g['trades']:,}건"
            top_items.append(_link_row(href, f"{g['sgg']} 오피스텔", hint))
        related_blocks.append(
            f'<h3 style="font-size:13px;color:#475569;font-weight:600;margin:0 0 8px;">'
            f'🏆 {esc(sido)} 인기 구 TOP 5</h3>'
            f'<ul style="list-style:none;padding:0;margin:0;'
            f'display:flex;flex-direction:column;gap:6px;">'
            + "".join(top_items) + '</ul>'
        )

    cross_html = (
        f'<div class="section" style="padding:20px 14px;">'
        f'<h2 class="section-title">관련 페이지</h2>'
        + "".join(related_blocks)
        + '</div>'
    )
    html_out += cross_html
    html_out += _footer_html()
    path = GU_DIR / f"{gu_slug}.html"
    path.write_text(html_out, encoding="utf-8")
    return path


def build_dong_page(sido: str, sgg: str, umd: str, offis: list[dict],
                    gu_offis: list[dict] | None = None) -> Path:
    first_addr = (offis[0].get("jibun_addr") if offis else "") or ""
    dong_slug = make_dong_slug(sgg, umd, first_addr)
    gu_slug = gu_url_slug(sido, sgg)
    h1 = f"{sido} {sgg} {umd} 오피스텔"
    title = f"{sido} {sgg} {umd} 오피스텔 실거래가 · {len(offis):,}개 | 휙"
    canonical = f"https://hwik.kr/officetel/dong/{url_quote(dong_slug)}.html"
    bc = [
        ("휙", "/"),
        (f"{sido} {sgg}", f"/officetel/gu/{url_quote(gu_slug)}.html"),
        (umd, None),
    ]
    sorted_ = sorted(offis, key=lambda o: -(o.get("trade_count") or 0))
    total_trades = sum((o.get("trade_count") or 0) for o in offis)

    desc = (f"{sido} {sgg} {umd} 오피스텔 {len(offis):,}개 단지 실거래가·시세. "
            f"누적 실거래 {total_trades:,}건, 국토교통부 공개시스템 기반.")

    # ── 동 좌표 (dong center) ─────────────────────────────────
    _lats = [o.get("road_lat") or o.get("jibun_lat") for o in offis]
    _lngs = [o.get("road_lng") or o.get("jibun_lng") for o in offis]
    _lats = [x for x in _lats if x]
    _lngs = [x for x in _lngs if x]
    geo_block = None
    if _lats and _lngs:
        geo_block = {
            "@type": "GeoCoordinates",
            "latitude": round(sum(_lats) / len(_lats), 6),
            "longitude": round(sum(_lngs) / len(_lngs), 6),
        }

    # ── JSON-LD ─────────────────────────────────────────────
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
    for i, o in enumerate(sorted_[:20]):
        if not (o.get("url") and o.get("bld_nm")):
            continue
        bits = []
        if o.get("trade_count"):
            bits.append(f"실거래 {int(o['trade_count']):,}건")
        item_list_elements.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": f"https://hwik.kr{o['url']}",
            "name": o["bld_nm"],
            **({"description": " · ".join(bits)} if bits else {}),
        })
    place_block = {
        "@type": "AdministrativeArea",
        "name": f"{sido} {sgg} {umd}",
        "containedInPlace": {
            "@type": "AdministrativeArea",
            "name": f"{sido} {sgg}",
            "containedInPlace": {
                "@type": "AdministrativeArea",
                "name": sido,
                "containedInPlace": {"@type": "Country", "name": "대한민국"},
            },
        },
    }
    if geo_block:
        place_block["geo"] = geo_block
    jsonld_collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title.split(" | ")[0],
        "description": desc,
        "url": canonical,
        "inLanguage": "ko-KR",
        "datePublished": "2026-01-01",
        "dateModified": BUILD_DATE,
        "isPartOf": {"@type": "WebSite", "name": "휙", "url": "https://hwik.kr"},
        "publisher": {"@id": "https://hwik.kr/#org"},
        "about": place_block,
        "mainEntity": {
            "@type": "ItemList",
            "name": f"{umd} 오피스텔 거래 상위 단지",
            "numberOfItems": len(item_list_elements),
            "itemListElement": item_list_elements,
        },
    }
    jsonld_place = dict(place_block, **{"@context": "https://schema.org"})
    faq_qas = [
        (f"{umd} 오피스텔 단지 수는 몇 개인가요?",
         f"{sido} {sgg} {umd}에는 최근 5년 실거래 10건 이상의 오피스텔 {len(offis):,}개 단지가 있습니다. "
         f"국토교통부 실거래가 공개시스템 기준입니다."),
    ]
    if total_trades:
        faq_qas.append((
            f"{umd} 오피스텔 실거래는 얼마나 발생하나요?",
            f"최근 5년간 {umd} 오피스텔 단지에서 총 {total_trades:,}건의 실거래(매매·전세·월세 합산)가 신고되었습니다."
        ))
    faq_qas.append((
        f"{umd} 오피스텔 데이터 출처는 어디인가요?",
        f"국토교통부 실거래가 공개시스템(rt.molit.go.kr)을 매일 자동 수집하여 반영합니다."
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

    html_out = _header_html(title, desc, canonical, h1, bc,
                            extra_jsonld=[jsonld_org, jsonld_collection, jsonld_place, jsonld_faq])

    # 풍부 인트로
    intro = (
        f"{sido} {sgg} {umd}의 오피스텔 {len(offis):,}개 단지 시세를 한 곳에서 확인하세요. "
        f"최근 5년 실거래 10건 이상 단지만 모았으며, "
        f"단지 전체 누적 실거래는 {total_trades:,}건. "
        f"각 단지를 클릭하면 평형별 실거래가, 주변 단지 비교, 교통·학교 정보를 볼 수 있습니다."
    )
    html_out += _intro(intro)

    # 거래 상위 3개 단지 본문 인용
    top3 = [o for o in sorted_[:3] if o.get("url") and o.get("bld_nm") and o.get("trade_count")]
    if top3:
        bits = []
        for rank, o in enumerate(top3, start=1):
            anchor = (f'<a href="{esc(o["url"])}" '
                      f'style="color:#4338ca;text-decoration:none;font-weight:600;">'
                      f'{esc(o["bld_nm"])}</a>')
            tc = int(o.get("trade_count") or 0)
            if rank == 1:
                bits.append(f"거래 1위는 {anchor} ({tc:,}건)")
            else:
                bits.append(f"{rank}위 {anchor} ({tc:,}건)")
        html_out += (
            f'<p class="seo-text" style="font-size:12px;color:var(--sub);'
            f'line-height:1.85;margin:12px 16px;">'
            f'{umd} 오피스텔 중 {", ".join(bits)} 입니다.'
            f'</p>'
        )

    html_out += _list_section(f"{umd} 오피스텔 전체 ({len(sorted_):,})", sorted_)

    # ── 관련 페이지 ─────────────────────────────────────────────
    def _link_row(href: str, label: str, hint: str = "") -> str:
        hint_html = (f'<span style="color:#64748b;font-size:11px;">{esc(hint)}</span>'
                     if hint else "")
        return (
            f'<li><a class="nearby-item" href="{esc(href)}" '
            f'style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:10px 12px;background:#f3f4f6;border-radius:8px;'
            f'text-decoration:none;color:#0f172a;font-size:13px;">'
            f'<span style="font-weight:600;">{esc(label)}</span>'
            f'{hint_html}'
            f'</a></li>'
        )

    related_blocks: list[str] = []

    # 같은 sgg 내 다른 동들 (인접/TOP 계산용)
    other_dongs: list[dict] = []
    if gu_offis:
        _by_umd: dict[str, list[dict]] = defaultdict(list)
        for o in gu_offis:
            ud = o.get("umd")
            if not ud or ud == umd:
                continue
            _by_umd[ud].append(o)
        for od_name, lst in _by_umd.items():
            lats = [o.get("road_lat") or o.get("jibun_lat") for o in lst]
            lngs = [o.get("road_lng") or o.get("jibun_lng") for o in lst]
            lats = [x for x in lats if x]
            lngs = [x for x in lngs if x]
            if not lats or not lngs:
                continue
            first = (lst[0].get("jibun_addr") or "")
            slug = make_dong_slug(sgg, od_name, first)
            other_dongs.append({
                "umd": od_name, "slug": slug,
                "count": len(lst),
                "trades": sum((o.get("trade_count") or 0) for o in lst),
                "lat": sum(lats) / len(lats),
                "lng": sum(lngs) / len(lngs),
            })

    # 인접 동 (현재 동 중심으로부터 거리)
    adjacent: list[dict] = []
    if other_dongs and geo_block:
        cur_lat = geo_block["latitude"]
        cur_lng = geo_block["longitude"]
        for d in other_dongs:
            d["dist"] = ((d["lat"] - cur_lat) ** 2 + (d["lng"] - cur_lng) ** 2) ** 0.5
        adjacent = sorted(other_dongs, key=lambda d: d["dist"])[:5]

    # 같은 구 인기 동 TOP 5 (단지 수 기준)
    top5_dongs = sorted(other_dongs, key=lambda d: -d["count"])[:5]

    # 전체 보기: 상위 구 + 시도 랭킹 + 아파트 동 cross-link
    primary_items = [
        _link_row(f"/officetel/gu/{url_quote(gu_slug)}.html",
                  f"{sido} {sgg} 전체 오피스텔", "구 전체"),
        _link_row(f"/officetel/ranking-{url_quote(sido)}.html",
                  f"{sido} 오피스텔 거래량 랭킹 TOP 100", "시도 비교"),
    ]
    apt_dong = _apt_dong_url(dong_slug)
    if apt_dong:
        primary_items.append(_link_row(apt_dong, f"{sido} {sgg} {umd} 아파트 시세", "아파트 보기"))
    related_blocks.append(
        f'<h3 style="font-size:13px;color:#475569;font-weight:600;margin:0 0 8px;">'
        f'전체 보기</h3>'
        f'<ul style="list-style:none;padding:0;margin:0 0 16px;'
        f'display:flex;flex-direction:column;gap:6px;">'
        + "".join(primary_items) + '</ul>'
    )

    # 인접 동
    if adjacent:
        adj_items = []
        for d in adjacent:
            href = f"/officetel/dong/{url_quote(d['slug'])}.html"
            adj_items.append(_link_row(href, f"{d['umd']} 오피스텔", f"{d['count']:,}개 단지"))
        related_blocks.append(
            f'<h3 style="font-size:13px;color:#475569;font-weight:600;margin:0 0 8px;">'
            f'📍 {esc(umd)} 인접 동</h3>'
            f'<ul style="list-style:none;padding:0;margin:0 0 16px;'
            f'display:flex;flex-direction:column;gap:6px;">'
            + "".join(adj_items) + '</ul>'
        )

    # 같은 구 인기 동 TOP 5
    if top5_dongs:
        top_items = []
        for d in top5_dongs:
            href = f"/officetel/dong/{url_quote(d['slug'])}.html"
            top_items.append(_link_row(href, f"{d['umd']} 오피스텔", f"{d['count']:,}개 단지"))
        related_blocks.append(
            f'<h3 style="font-size:13px;color:#475569;font-weight:600;margin:0 0 8px;">'
            f'🏆 {esc(sgg)} 인기 동 TOP 5</h3>'
            f'<ul style="list-style:none;padding:0;margin:0;'
            f'display:flex;flex-direction:column;gap:6px;">'
            + "".join(top_items) + '</ul>'
        )

    cross_html = (
        f'<div class="section" style="padding:20px 14px;">'
        f'<h2 class="section-title">관련 페이지</h2>'
        + "".join(related_blocks)
        + '</div>'
    )
    html_out += cross_html
    html_out += _footer_html()
    path = DONG_DIR / f"{dong_slug}.html"
    path.write_text(html_out, encoding="utf-8")
    return path


def build_ranking_page(offis: list[dict], sido: str | None = None) -> Path:
    scope = sido or "전국"
    h1 = f"{scope} 오피스텔 거래량 랭킹"
    title = f"{scope} 오피스텔 거래량 랭킹 TOP 100 | 휙"
    canonical_path = (f"/officetel/ranking.html" if not sido else
                      f"/officetel/ranking-{url_quote(sido)}.html")
    canonical = f"https://hwik.kr{canonical_path}"
    file_name = "ranking.html" if not sido else f"ranking-{sido}.html"
    bc = [("휙", "/"), ("오피스텔 랭킹", None)]
    if sido:
        bc = [("휙", "/"), ("오피스텔 랭킹", "/officetel/ranking.html"), (sido, None)]
    pool = offis if not sido else [o for o in offis if o.get("sido") == sido]
    top = sorted(pool, key=lambda o: -(o.get("trade_count") or 0))[:100]

    # ── E-E-A-T enrichment ──────────────────────────────────────
    total_units = len(pool)
    total_trades = sum((o.get("trade_count") or 0) for o in pool)
    # 시도/구 그룹 카운트 (전국이면 시도별, 시도면 구별)
    if sido:
        _sub_map: dict[str, list[dict]] = defaultdict(list)
        for o in pool:
            if o.get("sgg"):
                _sub_map[o["sgg"]].append(o)
        _sub_top = sorted(_sub_map.items(), key=lambda x: -sum((o.get("trade_count") or 0) for o in x[1]))[:5]
        sub_label = "구"
    else:
        _sub_map = defaultdict(list)
        for o in pool:
            if o.get("sido"):
                _sub_map[o["sido"]].append(o)
        _sub_top = sorted(_sub_map.items(), key=lambda x: -sum((o.get("trade_count") or 0) for o in x[1]))[:5]
        sub_label = "시도"

    desc = (f"{scope} 오피스텔 거래량 TOP 100 단지. "
            f"최근 5년 실거래 누적 {total_trades:,}건, {total_units:,}개 단지 대상. "
            f"국토교통부 공개시스템 기반.")

    # ── JSON-LD ─────────────────────────────────────────────────
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
    for i, o in enumerate(top):
        if not (o.get("url") and o.get("bld_nm")):
            continue
        bits = []
        if o.get("sgg"):
            bits.append(o["sgg"] + (f" {o['umd']}" if o.get("umd") else ""))
        if o.get("trade_count"):
            bits.append(f"실거래 {int(o['trade_count']):,}건")
        item_list_elements.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": f"https://hwik.kr{o['url']}",
            "name": o["bld_nm"],
            **({"description": " · ".join(bits)} if bits else {}),
        })
    jsonld_collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title.split(" | ")[0],
        "description": desc,
        "url": canonical,
        "inLanguage": "ko-KR",
        "datePublished": "2026-01-01",
        "dateModified": BUILD_DATE,
        "isPartOf": {"@type": "WebSite", "name": "휙", "url": "https://hwik.kr"},
        "publisher": {"@id": "https://hwik.kr/#org"},
        "mainEntity": {
            "@type": "ItemList",
            "name": f"{scope} 오피스텔 거래량 TOP 100",
            "numberOfItems": len(item_list_elements),
            "itemListElement": item_list_elements,
        },
    }
    if sido:
        jsonld_collection["about"] = {
            "@type": "AdministrativeArea",
            "name": sido,
            "containedInPlace": {"@type": "Country", "name": "대한민국"},
        }

    faq_qas = [
        (f"{scope} 오피스텔 거래량 TOP 100은 어떻게 집계되나요?",
         f"국토교통부 실거래가 공개시스템(매매·전세·월세) 기준 최근 5년 실거래 건수가 가장 많은 단지를 정렬했습니다. "
         f"거래가 활발할수록 시세 신뢰도가 높고 환금성도 좋습니다."),
        (f"{scope} 오피스텔 단지는 총 몇 개인가요?",
         f"{scope}에는 최근 5년 실거래 10건 이상의 오피스텔 {total_units:,}개 단지가 있으며, "
         f"누적 실거래는 {total_trades:,}건입니다."),
    ]
    if _sub_top:
        names = "·".join(s for s, _ in _sub_top[:3])
        faq_qas.append((
            f"{scope}에서 오피스텔 거래가 가장 많은 {sub_label}는 어디인가요?",
            f"{scope}에서는 {names} 순으로 거래가 많이 발생합니다. "
            f"각 {sub_label} 페이지에서 단지별 실거래가와 평형별 시세를 확인할 수 있습니다."
        ))
    faq_qas.append((
        f"{scope} 오피스텔 실거래 데이터 출처는?",
        f"국토교통부 실거래가 공개시스템(rt.molit.go.kr) 데이터를 매일 자동 수집하여 반영합니다."
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

    html_out = _header_html(title, desc, canonical, h1, bc,
                            extra_jsonld=[jsonld_org, jsonld_collection, jsonld_faq])

    # 풍부 인트로 (Top 1·2·3 인용)
    intro_text = (
        f"{scope} 오피스텔 중 최근 5년 실거래 건수 기준 상위 100개 단지입니다. "
        f"전체 {total_units:,}개 단지의 누적 실거래는 {total_trades:,}건. "
        f"거래가 활발할수록 시세 신뢰도가 높고 환금성이 좋습니다. "
        f"모든 데이터는 국토교통부 공개시스템 기반입니다."
    )
    html_out += _intro(intro_text)

    # 거래 상위 3개 단지 본문 인용 (E-E-A-T)
    top3 = [o for o in top[:3] if o.get("url") and o.get("bld_nm") and o.get("trade_count")]
    if top3:
        bits = []
        for rank, o in enumerate(top3, start=1):
            anchor = (f'<a href="{esc(o["url"])}" '
                      f'style="color:#4338ca;text-decoration:none;font-weight:600;">'
                      f'{esc(o["bld_nm"])}</a>')
            tc = int(o.get("trade_count") or 0)
            sgg_e = esc(o.get("sgg") or "")
            umd_e = esc(o.get("umd") or "")
            loc = (f"{sgg_e} {umd_e}".strip() or "")
            if rank == 1:
                bits.append(f"거래 1위는 {loc}의 {anchor} ({tc:,}건)")
            else:
                bits.append(f"{rank}위 {anchor} ({loc} · {tc:,}건)")
        html_out += (
            f'<p class="seo-text" style="font-size:12px;color:var(--sub);'
            f'line-height:1.85;margin:12px 16px;">'
            f'{scope} 오피스텔 중 {", ".join(bits)} 입니다. '
            f'각 단지를 클릭하면 평형별 실거래가, 주변 단지 비교, 교통·학교 정보를 볼 수 있습니다.'
            f'</p>'
        )

    html_out += _list_section(f"{scope} 거래량 TOP 100", top, show_sgg=True)

    # ── 관련 페이지 ─────────────────────────────────────────────
    def _link_row(href: str, label: str, hint: str = "") -> str:
        hint_html = (f'<span style="color:#64748b;font-size:11px;">{esc(hint)}</span>'
                     if hint else "")
        return (
            f'<li><a class="nearby-item" href="{esc(href)}" '
            f'style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:10px 12px;background:#f3f4f6;border-radius:8px;'
            f'text-decoration:none;color:#0f172a;font-size:13px;">'
            f'<span style="font-weight:600;">{esc(label)}</span>'
            f'{hint_html}'
            f'</a></li>'
        )

    related_blocks: list[str] = []

    # 전체 보기: 전국 ↔ 시도, 아파트 cross-link
    primary_items = []
    if sido:
        primary_items.append(_link_row("/officetel/ranking.html",
                                       "전국 오피스텔 거래량 랭킹 TOP 100", "전국 비교"))
    else:
        primary_items.append(_link_row("/officetel/",
                                       "시도별 오피스텔 시세 모아보기", "전국 목차"))
    # 아파트 ranking은 단일 (전국)
    primary_items.append(_link_row("/ranking.html",
                                   "아파트 거래량 랭킹", "아파트 보기"))
    related_blocks.append(
        f'<h3 style="font-size:13px;color:#475569;font-weight:600;margin:0 0 8px;">'
        f'전체 보기</h3>'
        f'<ul style="list-style:none;padding:0;margin:0 0 16px;'
        f'display:flex;flex-direction:column;gap:6px;">'
        + "".join(primary_items) + '</ul>'
    )

    # 인기 시도/구 TOP 5
    if _sub_top:
        sub_items = []
        for name, lst in _sub_top:
            tc = sum((o.get("trade_count") or 0) for o in lst)
            if sido:
                href = f"/officetel/gu/{url_quote(gu_url_slug(sido, name))}.html"
                label = f"{name} 오피스텔"
            else:
                href = f"/officetel/ranking-{url_quote(name)}.html"
                label = f"{name} 오피스텔 랭킹"
            sub_items.append(_link_row(href, label, f"실거래 {tc:,}건"))
        emoji = "🏆"
        title_label = (f"{scope} 인기 구 TOP 5" if sido else f"인기 시도 TOP 5")
        related_blocks.append(
            f'<h3 style="font-size:13px;color:#475569;font-weight:600;margin:0 0 8px;">'
            f'{emoji} {esc(title_label)}</h3>'
            f'<ul style="list-style:none;padding:0;margin:0;'
            f'display:flex;flex-direction:column;gap:6px;">'
            + "".join(sub_items) + '</ul>'
        )

    cross_html = (
        f'<div class="section" style="padding:20px 14px;">'
        f'<h2 class="section-title">관련 페이지</h2>'
        + "".join(related_blocks)
        + '</div>'
    )
    html_out += cross_html
    html_out += _footer_html()
    path = OFFI_ROOT / file_name
    path.write_text(html_out, encoding="utf-8")
    return path


def build_root_index(offis: list[dict]) -> Path:
    # 시도별 그룹
    smap = defaultdict(list)
    for o in offis:
        if o.get("sido"):
            smap[o["sido"]].append(o)
    h1 = "전국 오피스텔 실거래가"
    title = "전국 오피스텔 실거래가 시세 | 휙"
    desc = (f"전국 오피스텔 {len(offis):,}개 단지 실거래가. "
            f"국토교통부 공개시스템 기반 시도별 목차.")
    canonical = "https://hwik.kr/officetel/"
    bc = [("휙", "/"), ("오피스텔", None)]
    html_out = _header_html(title, desc, canonical, h1, bc)
    html_out += _intro(
        f"전국 17개 시도에 걸쳐 최근 5년 실거래 10건 이상의 오피스텔 {len(offis):,}개 단지를 제공합니다. "
        f"국토교통부 실거래가 공개시스템과 건축물대장을 기반으로 정확한 시세·평형·주차·교통·학교 정보를 확인하세요."
    )
    # 시도별 카드
    items = []
    for sido, lst in sorted(smap.items(), key=lambda x: -len(x[1])):
        href = f"/officetel/ranking-{url_quote(sido)}.html"
        items.append(
            f'<li><a href="{esc(href)}" '
            f'style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:12px 14px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:14px;">'
            f'<span style="font-weight:600;">{esc(sido)}</span>'
            f'<span style="color:#6b7280;font-size:12px;">{len(lst):,}개 단지</span>'
            f'</a></li>'
        )
    ranking_link = (
        '<div style="padding:16px;"><a href="/officetel/ranking.html" '
        'style="display:block;padding:14px;background:#fef3c7;border-radius:8px;'
        'text-decoration:none;color:#1a1a2e;font-size:14px;font-weight:600;text-align:center;">'
        '🏆 전국 거래량 랭킹 TOP 100 →</a></div>'
    )
    html_out += ranking_link
    html_out += (
        '<div class="divider"></div>'
        '<div class="section" style="padding:16px;">'
        '<h2 class="section-title">시도별 오피스텔</h2>'
        '<ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:6px;">'
        + "".join(items) + '</ul></div>'
    )
    html_out += _footer_html()
    path = OFFI_ROOT / "index.html"
    path.write_text(html_out, encoding="utf-8")
    return path


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
    print("officetels 로드 (for index 빌드)...")
    all_offis = _get_all()
    print(f"  {len(all_offis):,} 건")

    one_gu = os.environ.get("ONE_GU", "").strip()
    one_dong = os.environ.get("ONE_DONG", "").strip()
    one_sido = os.environ.get("ONE_SIDO", "").strip()

    # gu 그룹 빌드
    gu_map: dict[tuple[str, str], list[dict]] = defaultdict(list)
    dong_map: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    sidos: set[str] = set()
    for o in all_offis:
        sd = o.get("sido"); sg = o.get("sgg"); ud = o.get("umd")
        if sd:
            sidos.add(sd)
        if sd and sg:
            gu_map[(sd, sg)].append(o)
        if sd and sg and ud:
            dong_map[(sd, sg, ud)].append(o)

    if one_gu or one_dong or one_sido:
        # 미리보기 모드: 지정한 페이지만 빌드
        if one_gu:
            matches = [(sd, sg) for (sd, sg) in gu_map if sg == one_gu]
            if not matches:
                print(f"[ONE_GU={one_gu}] 매칭 구 없음", file=sys.stderr); return 1
            for (sd, sg) in matches:
                p = build_gu_page(sd, sg, gu_map[(sd, sg)], gu_map=gu_map)
                print(f"[프리뷰 gu] {p}")
        if one_dong:
            matches = [(sd, sg, ud) for (sd, sg, ud) in dong_map if ud == one_dong]
            if not matches:
                print(f"[ONE_DONG={one_dong}] 매칭 동 없음", file=sys.stderr); return 1
            for (sd, sg, ud) in matches:
                p = build_dong_page(sd, sg, ud, dong_map[(sd, sg, ud)],
                                    gu_offis=gu_map.get((sd, sg)))
                print(f"[프리뷰 dong] {p}")
        if one_sido:
            p = build_ranking_page(all_offis, sido=one_sido)
            print(f"[프리뷰 ranking] {p}")
        print("\n[프리뷰] 완료")
        return 0

    print(f"\n구 페이지 {len(gu_map):,}개 빌드...")
    for (sd, sg), lst in gu_map.items():
        build_gu_page(sd, sg, lst, gu_map=gu_map)
    print(f"  → {GU_DIR}")

    print(f"\n동 페이지 {len(dong_map):,}개 빌드...")
    for (sd, sg, ud), lst in dong_map.items():
        build_dong_page(sd, sg, ud, lst, gu_offis=gu_map.get((sd, sg)))
    print(f"  → {DONG_DIR}")

    print(f"\n전국 랭킹 + 시도별 랭킹 {len(sidos)+1}개 빌드...")
    build_ranking_page(all_offis)
    for sd in sorted(sidos):
        build_ranking_page(all_offis, sido=sd)

    print("\n루트 인덱스 빌드...")
    build_root_index(all_offis)

    print("\n완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
