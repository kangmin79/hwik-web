# -*- coding: utf-8 -*-
"""
check_links.py — 생성된 SEO 페이지의 내부 링크가 실제로 존재하는지 검증

검사 대상:
  - danji/*.html (샘플 200개)
  - dong/*.html (전체)
  - gu/*.html (전체)
  - sitemap.xml (있으면)
  - ranking/*.html (있으면 전체)

href="/..." 형식의 상대 링크 또는 https://hwik.kr/... 링크를
파일 시스템 경로로 매핑해서 존재 여부 확인.
"""
import os, re, sys, random
from collections import defaultdict
from urllib.parse import unquote

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

BASE = os.path.dirname(os.path.abspath(__file__))
HREF_RE = re.compile(r'href="([^"#]+)"')

# 링크를 파일 시스템 경로로 변환
def url_to_path(href):
    # https://hwik.kr/... → /...
    if href.startswith("https://hwik.kr"):
        href = href[len("https://hwik.kr"):]
    if href.startswith("http://") or href.startswith("https://"):
        return None  # 외부 링크
    if href.startswith("mailto:") or href.startswith("tel:"):
        return None
    if not href.startswith("/"):
        return None  # 상대 경로는 이번 검사에서 제외
    path = unquote(href.split("?")[0].split("#")[0])
    # /foo/ → /foo/index.html
    if path.endswith("/"):
        path = path + "index.html"
    # /foo (확장자 없음) → /foo/index.html 또는 /foo.html
    elif not os.path.splitext(path)[1]:
        # 우선 /foo/index.html 시도, 없으면 /foo.html
        cand1 = os.path.join(BASE, path.lstrip("/"), "index.html")
        cand2 = os.path.join(BASE, path.lstrip("/") + ".html")
        if os.path.exists(cand1):
            return cand1
        return cand2
    return os.path.join(BASE, path.lstrip("/"))

def extract_links(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return []
    return HREF_RE.findall(content)

def check_page(file_path):
    """페이지 하나 검사: (전체 내부 링크 수, 깨진 링크 리스트)"""
    links = extract_links(file_path)
    broken = []
    total_internal = 0
    for href in links:
        target = url_to_path(href)
        if target is None:
            continue
        total_internal += 1
        if not os.path.exists(target):
            broken.append(href)
    return total_internal, broken

def run_check(folder, label, sample=None):
    path = os.path.join(BASE, folder)
    if not os.path.isdir(path):
        print(f"[{label}] 폴더 없음: {folder}")
        return
    files = [f for f in os.listdir(path) if f.endswith(".html")]
    if sample and len(files) > sample:
        random.seed(42)
        files = random.sample(files, sample)
    total_pages = len(files)
    total_links = 0
    total_broken = 0
    broken_by_href = defaultdict(int)
    broken_sample_pages = defaultdict(list)
    for f in files:
        full = os.path.join(path, f)
        n, broken = check_page(full)
        total_links += n
        total_broken += len(broken)
        for href in broken:
            broken_by_href[href] += 1
            if len(broken_sample_pages[href]) < 3:
                broken_sample_pages[href].append(f)
    print(f"\n[{label}] {total_pages}개 페이지, 내부 링크 {total_links}개")
    print(f"  깨진 링크: {total_broken}개")
    if broken_by_href:
        # 빈도순 정렬
        sorted_broken = sorted(broken_by_href.items(), key=lambda x: -x[1])
        print(f"  고유 깨진 URL: {len(sorted_broken)}개")
        print(f"  상위 20개:")
        for href, count in sorted_broken[:20]:
            sample_pg = broken_sample_pages[href][0] if broken_sample_pages[href] else ""
            print(f"    ({count}회) {href}")
            print(f"           예: {sample_pg}")

def check_sitemap_all():
    """sitemap.xml + sitemap-*.xml 전부 검사 (서브 사이트맵 포함)"""
    files = []
    main = os.path.join(BASE, "sitemap.xml")
    if os.path.exists(main):
        files.append(main)
    for f in os.listdir(BASE):
        if f.startswith("sitemap") and f.endswith(".xml") and f != "sitemap.xml":
            files.append(os.path.join(BASE, f))
    if not files:
        print("\n[sitemap] 없음")
        return
    all_urls = []
    for fp in files:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        urls = re.findall(r"<loc>([^<]+)</loc>", content)
        all_urls.extend(urls)
        print(f"\n[{os.path.basename(fp)}] {len(urls)}개 URL")
    print(f"\n[sitemap 합계] {len(all_urls)}개 URL 전수검사")
    broken = []
    for u in all_urls:
        target = url_to_path(u)
        if target is None:
            continue
        if not os.path.exists(target):
            broken.append(u)
    print(f"  깨진 URL: {len(broken)}개")
    for u in broken[:30]:
        print(f"    {u}")

if __name__ == "__main__":
    print("=" * 60)
    print("SEO 페이지 링크 무결성 검사")
    print("=" * 60)
    run_check("danji", "danji (전체)")
    run_check("dong", "dong (전체)")
    run_check("gu", "gu (전체)")
    run_check("ranking", "ranking (전체)")
    check_sitemap_all()
    print("\n검사 완료")
