# -*- coding: utf-8 -*-
"""
crawl_googlebot.py — 구글봇 시뮬레이션 SEO 점검

실제 hwik.kr 페이지를 Googlebot UA + Playwright로 렌더링해서
구글이 실제로 보는 내용 기준으로 SEO 이슈를 점검한다.

verify_seo.py (로컬 파일 정적 분석) 와 다른 점:
  - 실제 live 서버 응답
  - JS 실행 후 렌더링 결과
  - 구글봇 UA로 접근 (UA에 따라 내용이 달라지는 경우 감지)
  - 렌더링 시간 측정

체크 항목:
  1. 타이틀: 존재, 60자 이하, 중복
  2. 메타 디스크립션: 존재, 160자 이하, 중복, 데이터 기반 여부 (danji)
  3. H1: 존재, 1개만
  4. Canonical URL: 현재 URL과 일치
  5. JSON-LD: JS 렌더링 후 유효성, 필수 @type 존재
  6. 렌더링 시간 (ms)
  7. 본문 텍스트 (빈 페이지 감지)
  8. 중복 타이틀 / 디스크립션

Usage:
  python crawl_googlebot.py              # 기본 샘플 (총 ~50개)
  python crawl_googlebot.py --full       # 더 많은 샘플 (~150개)
  python crawl_googlebot.py --url URL    # 특정 URL 하나만
"""

import os, sys, re, json, time, random, argparse
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, unquote
from collections import defaultdict

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

HOST   = "https://hwik.kr"
# 구글봇 렌더러는 Chrome 기반 — Googlebot UA 사용
GBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/W.X.Y.Z Mobile Safari/537.36 "
    "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
WAIT_MS      = 2000   # JS 완료 대기
NAV_TIMEOUT  = 20000

BASE = os.path.dirname(os.path.abspath(__file__))


# ── 샘플 URL 수집 ────────────────────────────────────────────

def load_sitemap_urls():
    """sitemap.xml 에서 URL 목록 로드"""
    path = os.path.join(BASE, "sitemap.xml")
    if not os.path.exists(path):
        return []
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [
        loc.text.strip()
        for loc in root.findall("sm:url/sm:loc", ns)
        if loc.text
    ]


def sample_urls(count_per_region=2, full=False):
    """지역별 균등 샘플링 + dong/gu/ranking 포함"""
    all_urls = load_sitemap_urls()
    if not all_urls:
        print("[WARN] sitemap.xml 없음 — 기본 URL로 대체")
        return [HOST + "/"]

    # 카테고리 분류
    cats = defaultdict(list)
    for u in all_urls:
        path = unquote(urlparse(u).path)
        if path.startswith("/danji/"):
            # 지역 prefix 추출 (서울/경기/부산 등)
            slug = path[7:]
            region = slug.split("-")[0] if "-" in slug else "etc"
            cats[f"danji_{region}"].append(u)
        elif path.startswith("/dong/"):
            cats["dong"].append(u)
        elif path.startswith("/gu/"):
            cats["gu"].append(u)
        elif path.startswith("/ranking/"):
            cats["ranking"].append(u)

    n = count_per_region if not full else count_per_region * 3
    rng = random.Random(int(time.time() // 86400))  # 매일 다른 샘플

    result = [HOST + "/"]  # 항상 홈 포함
    for cat, urls in sorted(cats.items()):
        sample = rng.sample(urls, min(n, len(urls)))
        result.extend(sample)

    return result


# ── 페이지 분석 ──────────────────────────────────────────────

def extract_jsonld(page):
    """JS 렌더링 후 DOM에서 JSON-LD 추출"""
    scripts = page.eval_on_selector_all(
        'script[type="application/ld+json"]',
        "els => els.map(e => e.textContent)"
    )
    result = []
    for s in scripts:
        try:
            result.append(json.loads(s))
        except Exception:
            result.append({"_parse_error": s[:80]})
    return result


def check_jsonld_types(ld_list, path):
    """JSON-LD에서 필요한 @type 확인"""
    all_types = set()
    errors = []
    for ld in ld_list:
        if "_parse_error" in ld:
            errors.append(f"JSON 파싱 오류: {ld['_parse_error']}")
            continue
        if isinstance(ld, dict):
            if "@graph" in ld:
                for item in ld["@graph"]:
                    if isinstance(item, dict) and "@type" in item:
                        all_types.add(item["@type"])
            elif "@type" in ld:
                all_types.add(ld["@type"])

    if path.startswith("/danji/"):
        for t in ["BreadcrumbList", "FAQPage"]:
            if t not in all_types:
                errors.append(f"@type {t} 누락")
    if path.startswith("/dong/"):
        if "BreadcrumbList" not in all_types:
            errors.append("@type BreadcrumbList 누락")

    return all_types, errors


def analyze_page(page, url):
    """한 페이지 분석 → 결과 dict 반환"""
    issues = []
    info = {}

    path = unquote(urlparse(url).path)

    # ── 타이틀 ──
    title = page.title() or ""
    info["title"] = title
    info["title_len"] = len(title)
    if not title:
        issues.append("타이틀 없음")
    elif len(title) > 60:
        issues.append(f"타이틀 너무 긺 ({len(title)}자 > 60자)")

    # ── 메타 디스크립션 ──
    desc = page.eval_on_selector(
        'meta[name="description"]',
        'el => el ? el.getAttribute("content") : ""'
    ) or ""
    info["desc"] = desc
    info["desc_len"] = len(desc)
    if not desc:
        issues.append("메타 디스크립션 없음")
    elif len(desc) > 160:
        issues.append(f"메타 디스크립션 너무 긺 ({len(desc)}자 > 160자)")

    # danji 페이지: 데이터 기반 여부 확인 (숫자 포함 여부)
    if path.startswith("/danji/") and desc:
        has_number = bool(re.search(r'\d', desc))
        if not has_number:
            issues.append("메타 디스크립션에 실거래 데이터 없음 (fallback)")
        else:
            info["desc_data_based"] = True

    # ── H1 ──
    h1_list = page.eval_on_selector_all("h1", "els => els.map(e => e.textContent.trim())")
    info["h1"] = h1_list
    if not h1_list:
        issues.append("H1 없음")
    elif len(h1_list) > 1:
        issues.append(f"H1 {len(h1_list)}개 (1개여야 함)")

    # ── Canonical ──
    canonical = page.eval_on_selector(
        'link[rel="canonical"]',
        'el => el ? el.getAttribute("href") : ""'
    ) or ""
    info["canonical"] = canonical
    final_url = page.url
    final_path = unquote(urlparse(final_url).path)
    canon_path = unquote(urlparse(canonical).path) if canonical else ""
    if not canonical:
        issues.append("Canonical 없음")
    elif canon_path != final_path:
        issues.append(f"Canonical 불일치: {canon_path[:60]}")

    # ── JSON-LD ──
    ld_list = extract_jsonld(page)
    ld_types, ld_errors = check_jsonld_types(ld_list, path)
    info["jsonld_types"] = sorted(ld_types)
    issues.extend(ld_errors)

    # ── 본문 텍스트 (렌더링 후 내용 있는지) ──
    body_text = page.eval_on_selector("body", "el => el ? el.innerText.trim() : ''") or ""
    info["body_len"] = len(body_text)
    if len(body_text) < 100:
        issues.append(f"본문 텍스트 너무 짧음 ({len(body_text)}자) — JS 렌더링 실패 가능성")

    info["issues"] = issues
    return info


# ── 메인 ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full",  action="store_true", help="더 많은 샘플")
    parser.add_argument("--url",   help="특정 URL만 점검")
    args = parser.parse_args()

    if args.url:
        urls = [args.url]
    else:
        urls = sample_urls(count_per_region=2, full=args.full)

    print("=" * 70)
    print(f"  구글봇 SEO 점검 — {HOST}")
    print(f"  UA: Googlebot/2.1 (Chrome 렌더러)")
    print(f"  대상: {len(urls)}개 페이지")
    print("=" * 70)

    results   = []
    all_titles = defaultdict(list)
    all_descs  = defaultdict(list)
    total_issues = 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            user_agent=GBOT_UA,
            viewport={"width": 375, "height": 812},  # 모바일 (구글봇 기본)
            java_script_enabled=True,
        )
        page = ctx.new_page()

        for i, url in enumerate(urls, 1):
            path = unquote(urlparse(url).path)
            print(f"\n[{i}/{len(urls)}] {path[:70]}")

            t0 = time.time()
            try:
                page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
                page.wait_for_timeout(WAIT_MS)
                elapsed = int((time.time() - t0) * 1000)

                info = analyze_page(page, url)
                info["url"]     = url
                info["elapsed"] = elapsed
                results.append(info)

                # 중복 추적
                if info.get("title"):
                    all_titles[info["title"]].append(path)
                if info.get("desc"):
                    all_descs[info["desc"]].append(path)

                # 결과 출력
                issues = info["issues"]
                status = "✓" if not issues else "✗"
                print(f"  {status} 렌더링 {elapsed}ms | 타이틀: {info['title'][:50]!r}")
                print(f"    디스크립션({info['desc_len']}자): {info['desc'][:80]!r}")
                if info.get("desc_data_based"):
                    print(f"    → 데이터 기반 디스크립션 ✓")
                if info["h1"]:
                    print(f"    H1: {info['h1'][0][:40]!r}")
                if info["jsonld_types"]:
                    print(f"    JSON-LD: {', '.join(info['jsonld_types'])}")
                for iss in issues:
                    print(f"    ⚠  {iss}")
                    total_issues += 1

            except Exception as e:
                print(f"  ✗ 오류: {e}")
                results.append({"url": url, "issues": [f"접근 오류: {e}"], "elapsed": -1})
                total_issues += 1

        browser.close()

    # ── 중복 검사 ──
    dup_titles = {t: paths for t, paths in all_titles.items() if len(paths) > 1}
    dup_descs  = {d: paths for d, paths in all_descs.items()  if len(paths) > 1}

    # ── 종합 리포트 ──
    print("\n" + "=" * 70)
    print("  종합 리포트")
    print("=" * 70)

    # 카테고리별 집계
    cat_counts = defaultdict(lambda: {"total": 0, "issues": 0})
    for r in results:
        path = unquote(urlparse(r["url"]).path)
        cat = path.split("/")[1] if "/" in path[1:] else "root"
        cat_counts[cat]["total"] += 1
        if r.get("issues"):
            cat_counts[cat]["issues"] += len(r["issues"])

    for cat, c in sorted(cat_counts.items()):
        status = "✓" if c["issues"] == 0 else f"✗ {c['issues']}건"
        print(f"  {cat:12s} {c['total']:3d}개 점검 — {status}")

    # 중복 타이틀
    if dup_titles:
        print(f"\n  중복 타이틀 {len(dup_titles)}건:")
        for t, paths in list(dup_titles.items())[:5]:
            print(f"    {t[:50]!r} → {len(paths)}개 페이지")
    else:
        print("\n  중복 타이틀: 없음 ✓")

    # 중복 디스크립션
    if dup_descs:
        print(f"  중복 디스크립션 {len(dup_descs)}건:")
        for d, paths in list(dup_descs.items())[:5]:
            print(f"    {d[:60]!r} → {len(paths)}개 페이지")
    else:
        print("  중복 디스크립션: 없음 ✓")

    # 평균 렌더링 시간
    times = [r["elapsed"] for r in results if r.get("elapsed", -1) > 0]
    if times:
        print(f"\n  평균 렌더링 시간: {sum(times)//len(times)}ms "
              f"(최소 {min(times)}ms / 최대 {max(times)}ms)")
        slow = [r for r in results if r.get("elapsed", 0) > 3000]
        if slow:
            print(f"  3초 초과 페이지 {len(slow)}개:")
            for r in slow[:5]:
                print(f"    {unquote(urlparse(r['url']).path)[:60]} — {r['elapsed']}ms")

    print(f"\n  총 이슈: {total_issues}건")
    if total_issues == 0:
        print("  모든 검증 통과!")

    return 1 if total_issues > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
