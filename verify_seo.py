#!/usr/bin/env python3
"""verify_seo.py - SEO 페이지 전수 검증 (4가지 검증 통합)"""

import os
import sys
import io
import re
import json
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse
from collections import defaultdict
from pathlib import Path

# 콘솔 UTF-8 출력 (Windows 전용)
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = Path(__file__).parent.resolve()
DOMAIN = "https://hwik.kr"

# ── 정규식 ──────────────────────────────────────────────────
A_HREF_RE = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\']', re.IGNORECASE)
JSONLD_RE = re.compile(
    r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
SCRIPT_SRC_RE = re.compile(
    r'<script\b([^>]*)src=["\']([^"\']+)["\']([^>]*)>',
    re.IGNORECASE,
)
IMG_RE = re.compile(r'<img\b([^>]*)/?>', re.IGNORECASE | re.DOTALL)
GOOGLE_FONTS_RE = re.compile(r'fonts\.googleapis\.com', re.IGNORECASE)
CANONICAL_RE = re.compile(r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', re.I)
OGURL_RE = re.compile(r'<meta[^>]*property=["\']og:url["\'][^>]*content=["\']([^"\']+)["\']', re.I)


# ── Phase 0: 파일 인덱스 구축 ───────────────────────────────
def build_file_index():
    root_files = set()
    for f in BASE.iterdir():
        if f.is_file():
            root_files.add(f.name)

    danji_dir = BASE / "danji"
    dong_dir = BASE / "dong"

    danji_slugs = set()
    dong_slugs = set()
    all_html_paths = []

    if danji_dir.is_dir():
        for f in danji_dir.iterdir():
            if f.is_file() and f.suffix == '.html':
                danji_slugs.add(f.stem)
                all_html_paths.append(("danji", f))

    if dong_dir.is_dir():
        for f in dong_dir.iterdir():
            if f.is_file() and f.suffix == '.html':
                dong_slugs.add(f.stem)
                all_html_paths.append(("dong", f))

    for f in BASE.iterdir():
        if f.is_file() and f.suffix == '.html':
            all_html_paths.append(("root", f))

    return root_files, danji_slugs, dong_slugs, all_html_paths


# ── 유틸리티 ────────────────────────────────────────────────
def extract_urls_from_jsonld(obj):
    """JSON-LD 객체에서 모든 url/item 필드를 재귀 추출"""
    urls = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in ('url', 'item') and isinstance(val, str):
                urls.append(val)
            else:
                urls.extend(extract_urls_from_jsonld(val))
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(extract_urls_from_jsonld(item))
    return urls


def resolve_link(href, root_files, danji_slugs, dong_slugs):
    """링크가 내부인지, 대상 파일이 존재하는지 반환.
    Returns: (is_internal, exists, detail)
    """
    if not href or href.startswith('#') or href.startswith('javascript:') or href.startswith('mailto:') or href.startswith('tel:'):
        return False, True, None
    # JS 템플릿 변수 (동적 페이지 - danji.html, dong.html, gu.html 등)
    if '${' in href or '`' in href:
        return False, True, None
    # JS 문자열 연결 패턴: href="/danji/'+encodeURIComponent(...)
    if "'+encodeURIComponent" in href or "'+makeSlug" in href or "'+esc(" in href:
        return False, True, None
    # JS에서 잘린 경로 (/danji/ 로 끝나는 불완전 href)
    if href.rstrip('/') in ('/danji', '/dong'):
        return False, True, None

    # 절대 URL → 경로 추출
    if href.startswith('http://') or href.startswith('https://'):
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc not in ('hwik.kr', 'www.hwik.kr'):
            return False, True, None  # 외부
        path = parsed.path
    else:
        path = href.split('?')[0].split('#')[0]

    path = path.rstrip('/')
    if not path:
        path = '/'

    decoded = unquote(path)

    # /danji/SLUG
    if decoded.startswith('/danji/'):
        slug = decoded[7:]
        if slug in danji_slugs:
            return True, True, None
        return True, False, f"danji 없음: {slug[:60]}"

    # /dong/SLUG
    if decoded.startswith('/dong/'):
        slug = decoded[6:]
        if slug in dong_slugs:
            return True, True, None
        return True, False, f"dong 없음: {slug[:60]}"

    # /
    if decoded == '/':
        return True, 'index.html' in root_files, "index.html 없음"

    # 루트 파일 (/gu.html, /ranking.html 등)
    fname = decoded.lstrip('/')
    if fname in root_files:
        return True, True, None

    # 정적 리소스 (config.js, makeSlug.js, style.css 등)
    if (BASE / fname).is_file():
        return True, True, None

    # danji/ dong/ 하위 정적 파일
    full = BASE / fname
    if full.is_file():
        return True, True, None

    # hub-new/ 등 서브 디렉토리
    if (BASE / fname / "index.html").is_file():
        return True, True, None

    return True, False, f"파일 없음: {decoded[:60]}"


# ── 검증 1: 내부 링크 ──────────────────────────────────────
def check_links(category, fname, html, root_files, danji_slugs, dong_slugs, errors):
    total = 0
    checked = 0
    # <a href> 추출
    hrefs = A_HREF_RE.findall(html)

    # JSON-LD url 추출
    for block in JSONLD_RE.findall(html):
        try:
            data = json.loads(block)
            hrefs.extend(extract_urls_from_jsonld(data))
        except json.JSONDecodeError:
            pass

    # canonical, og:url
    m = CANONICAL_RE.search(html)
    if m:
        hrefs.append(m.group(1))
    m = OGURL_RE.search(html)
    if m:
        hrefs.append(m.group(1))

    total = len(hrefs)
    for href in hrefs:
        is_internal, exists, detail = resolve_link(href, root_files, danji_slugs, dong_slugs)
        if is_internal:
            checked += 1
            if not exists:
                errors["broken_links"].append((f"{category}/{fname}", href[:80], detail))

    return total, checked


# ── 검증 2: JSON-LD 유효성 ─────────────────────────────────
def check_jsonld(category, fname, html, errors):
    blocks = JSONLD_RE.findall(html)
    fid = f"{category}/{fname}"

    if not blocks and category in ("danji", "dong"):
        errors["no_jsonld"].append(fid)
        return

    graph_items = []
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError as e:
            errors["json_parse_error"].append((fid, str(e)[:80]))
            continue
        if isinstance(data, dict) and "@graph" in data:
            graph_items.extend(data["@graph"])
        elif isinstance(data, dict):
            graph_items.append(data)
        elif isinstance(data, list):
            graph_items.extend(data)

    type_map = {}
    for item in graph_items:
        if isinstance(item, dict) and "@type" in item:
            type_map[item["@type"]] = item

    # FAQPage 검사
    faq = type_map.get("FAQPage")
    if faq:
        for q in faq.get("mainEntity", []):
            qname = (q.get("name") or "").strip()
            atext = ((q.get("acceptedAnswer") or {}).get("text") or "").strip()
            if not qname:
                errors["faq_empty_question"].append(fid)
                break
            if not atext:
                errors["faq_empty_answer"].append((fid, qname[:40]))
                break
    elif category in ("danji", "dong"):
        errors["faq_missing"].append(fid)

    # BreadcrumbList 검사
    bc = type_map.get("BreadcrumbList")
    if bc:
        items = bc.get("itemListElement", [])
        for idx, li in enumerate(items):
            if li.get("position") != idx + 1:
                errors["breadcrumb_position"].append(
                    (fid, f"expected {idx+1}, got {li.get('position')}")
                )
                break
        if items and "item" in items[-1]:
            errors["breadcrumb_last_has_url"].append(fid)
    elif category in ("danji", "dong"):
        errors["breadcrumb_missing"].append(fid)

    # ItemList (dong 전용) URL 인코딩 검사
    il = type_map.get("ItemList")
    if il and category == "dong":
        for li in il.get("itemListElement", []):
            url = li.get("url", "")
            if url:
                path_part = urlparse(url).path
                try:
                    path_part.encode('ascii')
                except UnicodeEncodeError:
                    errors["itemlist_not_encoded"].append((fid, url[:60]))
                    break

    # danji 필수 타입 확인
    if category == "danji":
        if "ApartmentComplex" not in type_map:
            errors["missing_type"].append((fid, "ApartmentComplex"))
    if category == "dong":
        if "ItemList" not in type_map:
            errors["missing_type"].append((fid, "ItemList"))


# ── 검증 3: PageSpeed 핵심 지표 ────────────────────────────
def check_pagespeed(category, fname, html, errors):
    fid = f"{category}/{fname}"

    # Google Fonts
    if GOOGLE_FONTS_RE.search(html):
        errors["google_fonts"].append(fid)

    # head 내 동기 외부 스크립트
    head_match = re.search(r'<head[^>]*>(.*?)</head>', html, re.S | re.I)
    if head_match:
        head_html = head_match.group(1)
        for m in SCRIPT_SRC_RE.finditer(head_html):
            all_attrs = m.group(1) + m.group(3)
            src = m.group(2)
            if 'defer' not in all_attrs.lower() and 'async' not in all_attrs.lower():
                # gtag는 async이므로 여기 안 걸림
                errors["sync_script_in_head"].append((fid, src[:60]))

    # img 태그 속성 검사
    for img_match in IMG_RE.finditer(html):
        img_tag = img_match.group(0)
        if 'src=' not in img_tag.lower():
            continue
        missing = []
        if 'width=' not in img_tag.lower():
            missing.append('width')
        if 'height=' not in img_tag.lower():
            missing.append('height')
        if 'loading=' not in img_tag.lower():
            missing.append('loading')
        if missing:
            src_m = re.search(r'src=["\']([^"\']+)["\']', img_tag, re.I)
            src_val = src_m.group(1)[:50] if src_m else "?"
            errors["img_missing_attrs"].append((fid, src_val, ', '.join(missing)))


# ── 검증 4: sitemap.xml ↔ 실제 파일 ───────────────────────
def verify_sitemap(root_files, danji_slugs, dong_slugs):
    errors = defaultdict(list)
    sitemap_path = BASE / "sitemap.xml"
    if not sitemap_path.is_file():
        errors["sitemap_missing"].append("sitemap.xml 없음")
        return errors, 0

    tree = ET.parse(sitemap_path)
    root = tree.getroot()
    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

    sitemap_danji = set()
    sitemap_dong = set()
    url_count = 0

    for url_elem in root.findall('sm:url', ns):
        loc = url_elem.find('sm:loc', ns)
        lastmod = url_elem.find('sm:lastmod', ns)

        if loc is None or not loc.text:
            errors["sitemap_empty_loc"].append("empty <loc>")
            continue

        raw_url = loc.text.strip()
        url_count += 1

        # lastmod 형식 검사
        if lastmod is not None and lastmod.text:
            lm = lastmod.text.strip()
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', lm):
                errors["sitemap_lastmod_format"].append((raw_url[:60], lm))

        # URL → 파일 존재 검사
        parsed = urlparse(raw_url)
        path = unquote(parsed.path).rstrip('/')

        if path.startswith('/danji/'):
            slug = path[7:]
            sitemap_danji.add(slug)
            if slug not in danji_slugs:
                errors["sitemap_file_missing"].append(f"danji/{slug[:60]}")
        elif path.startswith('/dong/'):
            slug = path[6:]
            sitemap_dong.add(slug)
            if slug not in dong_slugs:
                errors["sitemap_file_missing"].append(f"dong/{slug[:60]}")
        elif path in ('', '/'):
            if 'index.html' not in root_files:
                errors["sitemap_file_missing"].append("/")
        else:
            fname = path.lstrip('/')
            if fname not in root_files and not (BASE / fname).is_file():
                errors["sitemap_file_missing"].append(fname[:60])

    # 역방향: 파일 → sitemap
    for slug in danji_slugs:
        if slug not in sitemap_danji:
            errors["file_not_in_sitemap"].append(f"danji/{slug[:60]}")

    for slug in dong_slugs:
        if slug not in sitemap_dong:
            errors["file_not_in_sitemap"].append(f"dong/{slug[:60]}")

    return errors, url_count


# ── 결과 출력 ───────────────────────────────────────────────
def print_errors(label, items, max_show=10):
    count = len(items)
    if count == 0:
        print(f"  ✓ {label}: 0건")
        return
    print(f"  ✗ {label}: {count}건")
    for item in items[:max_show]:
        if isinstance(item, tuple):
            print(f"    - {' | '.join(str(x) for x in item)}")
        else:
            print(f"    - {item}")
    if count > max_show:
        print(f"    ... 외 {count - max_show}건")


# ── main ────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  SEO 전수 검증 — 4가지 통합")
    print("=" * 70)

    # Phase 0
    root_files, danji_slugs, dong_slugs, all_html_paths = build_file_index()
    print(f"\n파일 인덱스: root HTML {sum(1 for c,_ in all_html_paths if c=='root')}개, "
          f"danji {len(danji_slugs)}개, dong {len(dong_slugs)}개, "
          f"총 HTML {len(all_html_paths)}개\n")

    # Phase 1-3: 단일 루프
    link_errors = defaultdict(list)
    jsonld_errors = defaultdict(list)
    speed_errors = defaultdict(list)
    total_links = 0
    checked_links = 0
    file_count = 0

    for category, fpath in all_html_paths:
        try:
            html = fpath.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            print(f"  [ERROR] {fpath}: {e}")
            continue

        fname = fpath.name
        file_count += 1

        # 검증 1
        t, c = check_links(category, fname, html, root_files, danji_slugs, dong_slugs, link_errors)
        total_links += t
        checked_links += c

        # 검증 2
        check_jsonld(category, fname, html, jsonld_errors)

        # 검증 3
        check_pagespeed(category, fname, html, speed_errors)

        if file_count % 2000 == 0:
            print(f"  ... {file_count}개 검사 완료")

    print(f"  ... {file_count}개 검사 완료\n")

    # ── 검증 1 결과 ──
    print("=" * 70)
    print("  검증 1: 내부 링크 전수 검사")
    print("=" * 70)
    print(f"  총 링크: {total_links:,}개 | 내부 링크 검사: {checked_links:,}개")
    broken = link_errors.get("broken_links", [])
    if not broken:
        print(f"  ✓ 깨진 링크: 0건 — 모든 내부 링크 정상!")
    else:
        print(f"  ✗ 깨진 링크: {len(broken)}건")
        for item in broken[:15]:
            print(f"    - {item[0]} → {item[2]}")
        if len(broken) > 15:
            print(f"    ... 외 {len(broken) - 15}건")

    # ── 검증 2 결과 ──
    print(f"\n{'=' * 70}")
    print("  검증 2: JSON-LD 유효성")
    print("=" * 70)
    print_errors("JSON 파싱 오류", jsonld_errors.get("json_parse_error", []))
    print_errors("JSON-LD 없음 (danji/dong)", jsonld_errors.get("no_jsonld", []))
    print_errors("FAQPage 없음", jsonld_errors.get("faq_missing", []))
    print_errors("FAQ 빈 질문", jsonld_errors.get("faq_empty_question", []))
    print_errors("FAQ 빈 답변", jsonld_errors.get("faq_empty_answer", []))
    print_errors("BreadcrumbList 없음", jsonld_errors.get("breadcrumb_missing", []))
    print_errors("BreadcrumbList position 오류", jsonld_errors.get("breadcrumb_position", []))
    print_errors("BreadcrumbList 마지막에 URL 있음", jsonld_errors.get("breadcrumb_last_has_url", []))
    print_errors("ItemList URL 미인코딩", jsonld_errors.get("itemlist_not_encoded", []))
    print_errors("필수 @type 누락", jsonld_errors.get("missing_type", []))

    # ── 검증 3 결과 ──
    print(f"\n{'=' * 70}")
    print("  검증 3: PageSpeed 핵심 지표")
    print("=" * 70)
    print_errors("Google Fonts 잔존", speed_errors.get("google_fonts", []))
    print_errors("head 동기 스크립트", speed_errors.get("sync_script_in_head", []))
    print_errors("img 속성 누락 (width/height/loading)", speed_errors.get("img_missing_attrs", []))

    # ── 검증 4 결과 ──
    print(f"\n{'=' * 70}")
    print("  검증 4: sitemap.xml ↔ 실제 파일")
    print("=" * 70)
    sitemap_errors, sitemap_count = verify_sitemap(root_files, danji_slugs, dong_slugs)
    print(f"  sitemap URL: {sitemap_count:,}개")
    print_errors("sitemap → 파일 없음", sitemap_errors.get("sitemap_file_missing", []))
    print_errors("파일 → sitemap 미등록", sitemap_errors.get("file_not_in_sitemap", []))
    print_errors("lastmod 형식 오류", sitemap_errors.get("sitemap_lastmod_format", []))
    print_errors("빈 loc", sitemap_errors.get("sitemap_empty_loc", []))

    # ── 종합 요약 ──
    print(f"\n{'=' * 70}")
    print("  종합 요약")
    print("=" * 70)
    total_errors = (
        len(broken)
        + sum(len(v) for v in jsonld_errors.values())
        + sum(len(v) for v in speed_errors.values())
        + sum(len(v) for v in sitemap_errors.values())
    )

    checks = [
        ("검증 1 내부 링크", len(broken)),
        ("검증 2 JSON-LD", sum(len(v) for v in jsonld_errors.values())),
        ("검증 3 PageSpeed", sum(len(v) for v in speed_errors.values())),
        ("검증 4 Sitemap", sum(len(v) for v in sitemap_errors.values())),
    ]
    for name, cnt in checks:
        status = "✓ PASS" if cnt == 0 else f"✗ FAIL ({cnt}건)"
        print(f"  {name}: {status}")

    print(f"\n  총 에러: {total_errors}건")
    if total_errors == 0:
        print("  🎉 모든 검증 통과!")

    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
