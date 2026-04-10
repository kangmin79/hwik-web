"""
verify_live.py — 실제 서버(hwik.kr)에서 HTTP로 전수 검사
verify_seo.py는 로컬 파일 검사, 이 파일은 배포된 실제 페이지 검사.

검사 항목:
1. sitemap.xml 서버에서 다운로드
2. 모든 URL HTTP 200 응답 확인 (병렬)
3. 각 페이지 내용 추출 & 검증:
   - <title> 있음 + 비어있지 않음
   - <link rel=canonical> = 현재 URL
   - JSON-LD 블록 있음 + JSON 파싱 성공
   - 실거래가 숫자 패턴 존재 (단지 페이지만)
4. 랜덤 샘플 200개에서 내부 링크 추출 → 서버에서 200 응답하는지 확인
5. 통계 리포트
"""

import concurrent.futures
import urllib.request
import urllib.error
import re
import json
import random
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from urllib.parse import urlparse, unquote

BASE_URL = "https://hwik.kr"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
WORKERS = 20
TIMEOUT = 15
SAMPLE_LINK_CHECK = 200  # 내부 링크 샘플 체크 개수

TITLE_RE = re.compile(r'<title[^>]*>([^<]*)</title>', re.I)
CANONICAL_RE = re.compile(r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', re.I)
JSONLD_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
PRICE_RE = re.compile(r'[0-9]+억(\s*[0-9]+천?)?|[0-9]+,[0-9]{3}만')  # 2억 5천, 3,500만 등
A_HREF_RE = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\']', re.I)


def fetch(url, timeout=TIMEOUT, retries=2):
    """URL GET → (status, body, error). 일시적 5xx/네트워크 오류 자동 재시도."""
    last_err = None
    last_status = 0
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (hwik-verify/1.0)',
            'Accept': 'text/html,application/xml',
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode('utf-8', errors='replace')
                return r.status, body, None
        except urllib.error.HTTPError as e:
            last_status = e.code
            last_err = str(e)
            # 5xx만 재시도, 4xx는 즉시 포기
            if e.code < 500:
                return e.code, "", str(e)
        except Exception as e:
            last_err = str(e)
        if attempt < retries:
            time.sleep(1.0 + attempt * 0.5)  # 1초, 1.5초
    return last_status, "", last_err


def check_page(url):
    """한 URL 가져와서 상태 + 내용 검증 결과 반환"""
    status, body, err = fetch(url)
    result = {
        "url": url,
        "status": status,
        "error": err,
        "size": len(body),
        "title": None,
        "canonical": None,
        "canonical_mismatch": False,
        "jsonld_count": 0,
        "jsonld_parse_ok": 0,
        "jsonld_parse_fail": 0,
        "has_price": False,
        "is_danji": "/danji/" in url,
        "is_dong": "/dong/" in url,
        "is_gu": "/gu/" in url,
        "is_ranking": "/ranking" in url,
    }

    if status != 200 or not body:
        return result

    # title
    m = TITLE_RE.search(body)
    if m:
        result["title"] = m.group(1).strip()

    # canonical
    m = CANONICAL_RE.search(body)
    if m:
        result["canonical"] = m.group(1).strip()
        # canonical은 현재 URL과 같아야 함 (encoding 차이 허용)
        cur = unquote(url).rstrip('/')
        can = unquote(result["canonical"]).rstrip('/')
        # 단, 디렉토리 인덱스(/ranking/, /gu/)가 기본 탭(/ranking/seoul-price)으로
        # canonical을 지정하는 것은 의도된 SEO 설계이므로 허용
        is_index_redirect = (
            cur.endswith('/ranking') or cur.endswith('/gu')
        ) and can.startswith(cur + '/')
        if cur != can and not is_index_redirect:
            result["canonical_mismatch"] = True

    # JSON-LD
    blocks = JSONLD_RE.findall(body)
    result["jsonld_count"] = len(blocks)
    for b in blocks:
        try:
            json.loads(b.strip())
            result["jsonld_parse_ok"] += 1
        except json.JSONDecodeError:
            result["jsonld_parse_fail"] += 1

    # 실거래가 패턴 (danji 페이지만 필수)
    if PRICE_RE.search(body):
        result["has_price"] = True

    return result


def extract_internal_hrefs(body):
    """페이지 본문에서 내부 링크 추출"""
    hrefs = set()
    for h in A_HREF_RE.findall(body):
        if h.startswith('http://') or h.startswith('https://'):
            p = urlparse(h)
            if p.netloc in ('hwik.kr', 'www.hwik.kr'):
                hrefs.add(p.path)
        elif h.startswith('/'):
            hrefs.add(h.split('?')[0].split('#')[0])
    return hrefs


def main():
    print("=" * 70)
    print("  verify_live.py — hwik.kr 서버 전수 검사")
    print("=" * 70)

    # Phase 0: sitemap 다운로드
    print(f"\n[Phase 0] sitemap.xml 다운로드")
    status, body, err = fetch(SITEMAP_URL)
    if status != 200:
        print(f"  ❌ 실패: status={status} err={err}")
        sys.exit(1)

    root = ET.fromstring(body)
    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls = [loc.text.strip() for loc in root.findall('.//sm:loc', ns) if loc.text]
    print(f"  ✓ {len(urls)}개 URL 로드")

    # Phase 1: 전수 HTTP 체크
    print(f"\n[Phase 1] 전체 URL HTTP 응답 체크 (workers={WORKERS})")
    results = []
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(check_page, u): u for u in urls}
        done = 0
        for f in concurrent.futures.as_completed(futures):
            r = f.result()
            results.append(r)
            done += 1
            if done % 500 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(urls) - done) / rate
                print(f"  {done}/{len(urls)} ({rate:.1f} req/s, ETA {eta:.0f}s)")
    elapsed = time.time() - t0
    print(f"  ✓ 완료 ({elapsed:.1f}s, 평균 {len(urls)/elapsed:.1f} req/s)")

    # Phase 2: 통계
    print(f"\n[Phase 2] 통계")
    ok = [r for r in results if r["status"] == 200]
    fail = [r for r in results if r["status"] != 200]
    print(f"  ✓ 200 OK: {len(ok)}개")
    print(f"  ✗ 실패: {len(fail)}개")
    if fail:
        by_status = defaultdict(int)
        for r in fail:
            by_status[r["status"]] += 1
        for s, c in sorted(by_status.items()):
            print(f"    status {s}: {c}건")
        for r in fail[:10]:
            print(f"    - {r['url'][:80]} | {r['status']} | {(r['error'] or '')[:40]}")
        if len(fail) > 10:
            print(f"    ... 외 {len(fail) - 10}건")

    # Phase 3: 페이지 내용 검증
    print(f"\n[Phase 3] 페이지 내용 검증")
    no_title = [r for r in ok if not r["title"]]
    no_canonical = [r for r in ok if not r["canonical"]]
    canonical_mismatch = [r for r in ok if r["canonical_mismatch"]]
    no_jsonld = [r for r in ok if r["jsonld_count"] == 0]
    jsonld_fail = [r for r in ok if r["jsonld_parse_fail"] > 0]
    danji_ok = [r for r in ok if r["is_danji"]]
    danji_no_price = [r for r in danji_ok if not r["has_price"]]

    def report(label, items, max_show=5):
        if not items:
            print(f"  ✓ {label}: 0건")
        else:
            print(f"  ✗ {label}: {len(items)}건")
            for r in items[:max_show]:
                print(f"    - {r['url'][:80]}")
            if len(items) > max_show:
                print(f"    ... 외 {len(items) - max_show}건")

    report("title 없음", no_title)
    report("canonical 없음", no_canonical)
    report("canonical 불일치", canonical_mismatch)
    report("JSON-LD 없음", no_jsonld)
    report("JSON-LD 파싱 실패", jsonld_fail)
    report(f"단지 페이지({len(danji_ok)}개) 중 실거래가 패턴 없음", danji_no_price)

    # 사이즈 통계
    sizes = [r["size"] for r in ok]
    if sizes:
        print(f"\n  페이지 크기: 평균 {sum(sizes)//len(sizes):,}B, 최소 {min(sizes):,}B, 최대 {max(sizes):,}B")
        tiny = [r for r in ok if r["size"] < 1000]
        if tiny:
            print(f"  ⚠ 1KB 미만 페이지: {len(tiny)}건 (빈 페이지 가능성)")
            for r in tiny[:5]:
                print(f"    - {r['url'][:80]} ({r['size']}B)")

    # Phase 4: 랜덤 샘플 페이지의 내부 링크 서버 체크
    print(f"\n[Phase 4] 랜덤 샘플 {SAMPLE_LINK_CHECK}개 페이지 내부 링크 서버 응답 체크")
    sample = random.sample(ok, min(SAMPLE_LINK_CHECK, len(ok)))

    # 각 샘플 페이지 재다운로드해서 link 추출
    # (body를 results에 저장해두지 않았으니 한 번 더 GET)
    all_internal_hrefs = set()
    print(f"  링크 추출 중...")
    for r in sample:
        _, body, _ = fetch(r["url"])
        if body:
            hrefs = extract_internal_hrefs(body)
            all_internal_hrefs.update(hrefs)
    print(f"  총 고유 내부 경로: {len(all_internal_hrefs)}개")

    # 중복 제거하고 서버에서 실제 200 응답 체크
    check_urls = [f"{BASE_URL}{p}" for p in all_internal_hrefs]
    link_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(fetch, u) for u in check_urls]
        for i, f in enumerate(concurrent.futures.as_completed(futures)):
            s, _, e = f.result()
            link_results.append((check_urls[i] if i < len(check_urls) else "?", s, e))

    link_fail = [(u, s, e) for u, s, e in link_results if s != 200]
    print(f"  ✓ 200 OK: {len(link_results) - len(link_fail)}개")
    if link_fail:
        print(f"  ✗ 실패: {len(link_fail)}개")
        for u, s, e in link_fail[:10]:
            print(f"    - {u[:80]} | {s} | {(e or '')[:40]}")

    # 종합
    print("\n" + "=" * 70)
    print("  종합 결과")
    print("=" * 70)
    total_issues = (
        len(fail)
        + len(no_title)
        + len(no_canonical)
        + len(canonical_mismatch)
        + len(no_jsonld)
        + len(jsonld_fail)
        + len(danji_no_price)
        + len(link_fail)
    )
    print(f"  sitemap URL: {len(urls)}개")
    print(f"  검사 완료: {len(results)}개")
    print(f"  총 이슈: {total_issues}건")
    if total_issues == 0:
        print(f"  ✅ PASS — 모든 페이지 정상")
    else:
        print(f"  ⚠ 이슈 있음 — 상세 내용은 위 리포트 참고")

    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
