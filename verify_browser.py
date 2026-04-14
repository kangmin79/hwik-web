# -*- coding: utf-8 -*-
"""
verify_browser.py — 실제 브라우저(Playwright/Chromium) 기반 링크 검증

HEAD/GET 검사로는 못 잡는 버그(JS location.replace, meta refresh, defer
스크립트의 리다이렉트 등)를 실제 Chromium 으로 페이지 열고 JS 실행
완료 후 최종 URL 을 확인해 잡는다.

검사 대상:
  1) 허브/인덱스 페이지 (/, /gu/, /dong/, /ranking/)
  2) 지역 타입별 페이지 샘플 (gu/dong/danji/ranking 각 5~10개)
  3) 각 페이지에서 발견한 내부 <a> 중 3개까지 depth-1 클릭 검증
  4) 스트레스: 2토큰 구, 이름충돌, 리다이렉트 셸

판정:
  - final_url 이 원래 URL 과 디코딩 후 같아야 OK (홈 '/' 으로 튕기면 FAIL)
  - 리다이렉트 셸(gu.html, dong.html, danji.html, ranking.html)은 예외:
    타겟 경로로 도착하기만 하면 OK

Usage: python verify_browser.py
"""
import os, sys, random, time
from urllib.parse import unquote, urlparse
from playwright.sync_api import sync_playwright

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

BASE = os.path.dirname(os.path.abspath(__file__))
# HOST 는 env var 로도 덮어쓸 수 있음 — CI pre-push 검증에서
# localhost http.server 로 돌릴 때 사용 (VERIFY_HOST=http://localhost:8000)
HOST = os.environ.get("VERIFY_HOST", "https://hwik.kr").rstrip("/")
WAIT_MS = 1500   # JS defer 완료 대기
NAV_TIMEOUT = 15000

def norm(u):
    """URL 정규화: host 제거, path 디코딩, trailing slash 제거, .html 제거"""
    parsed = urlparse(u)
    path = unquote(parsed.path)
    if path.endswith(".html"):
        path = path[:-5]
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return path

# 매일 다른 샘플 (하루 단위 시드)
_DAILY_SEED = int(time.time() // 86400)

def sample_from_folder(folder, count):
    path = os.path.join(BASE, folder)
    if not os.path.isdir(path):
        return []
    files = [f for f in os.listdir(path)
             if f.endswith(".html") and f != "index.html"]
    random.seed(_DAILY_SEED)
    if count and len(files) > count:
        files = random.sample(files, count)
    return [f"{HOST}/{folder}/{f[:-5]}" for f in files]

def sample_danji_by_region(count_per_region=1):
    """지역별 균등 샘플링 — 특정 지역만 깨지는 버그도 잡기 위해"""
    path = os.path.join(BASE, "danji")
    if not os.path.isdir(path):
        return []
    # 파일명 첫 토큰(지역)별로 그룹핑
    from collections import defaultdict
    groups = defaultdict(list)
    for f in os.listdir(path):
        if not f.endswith(".html") or f == "index.html":
            continue
        region = f.split("-")[0]  # 서울/경기/부산/강원 등
        groups[region].append(f)
    random.seed(_DAILY_SEED)
    result = []
    for region, files in sorted(groups.items()):
        sample = random.sample(files, min(count_per_region, len(files)))
        result.extend([f"{HOST}/danji/{f[:-5]}" for f in sample])
    return result

def is_404_page(page):
    """페이지가 404.html 로 튕겼거나 '찾을 수 없습니다' 타이틀이면 True."""
    try:
        if page.url.endswith("/404.html") or "/404.html" in page.url:
            return True
        title = (page.title() or "")
        if "찾을 수 없습니다" in title or "404" in title:
            return True
    except Exception:
        pass
    return False

def check_page(page, url, expected_path=None, label=""):
    """
    페이지 열고 JS 실행 완료 후 최종 URL 확인.
    expected_path 가 주어지면 그 경로로 도착해야 OK (리다이렉트 셸용).
    아니면 원래 URL 의 path 와 최종 path 가 같아야 OK.
    404.html 로 튕기면 FAIL.
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        page.wait_for_timeout(WAIT_MS)
        if is_404_page(page):
            return False, page.url, "404", "(404 튕김)"
        final = page.url
        final_path = norm(final)
        expected = norm(expected_path or url)
        ok = (final_path == expected)
        return ok, final, final_path, expected
    except Exception as e:
        return False, None, None, str(e)[:100]

def check_danji_runtime_nearby(page, url):
    """
    danji 페이지 열고 .nearby-item 링크의
      - getAttribute('href')  (정적 HTML)
      - el.href               (런타임 JS 덮어쓰기 후)
    두 개를 비교해 다르면 오염으로 판단.
    추가로 .nearby-sub 텍스트(구 동)와 href 경로의 구를 대조해
    구 오염(예: 종로구 창신동 단지가 /danji/서울-성북구-창신동-...로 찍힘) 감지.
    """
    from urllib.parse import unquote as _unq
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        page.wait_for_timeout(WAIT_MS + 1500)  # app.js 재렌더 여유
        if is_404_page(page):
            return [{"type": "404", "url": url, "detail": "페이지 자체가 404"}]
        items = page.eval_on_selector_all(
            ".nearby-item",
            "els => els.map(e => ({"
            "  static_href: e.getAttribute('href'),"
            "  runtime_href: e.href,"
            "  sub_text: (e.querySelector('.nearby-sub') ? e.querySelector('.nearby-sub').textContent : '')"
            "}))"
        )
    except Exception as e:
        return [{"type": "error", "url": url, "detail": str(e)[:120]}]
    issues = []
    for it in items:
        static_path = _unq(it.get("static_href") or "")
        runtime_path = _unq(it.get("runtime_href") or "")
        sub_text = (it.get("sub_text") or "").strip()
        # runtime_href는 full URL이라 path만 추출
        try:
            from urllib.parse import urlparse as _up
            runtime_path = _unq(_up(runtime_path).path)
        except Exception:
            pass
        if static_path and runtime_path and static_path != runtime_path:
            issues.append({
                "type": "static_vs_runtime",
                "url": url,
                "static": static_path,
                "runtime": runtime_path,
                "sub": sub_text,
            })
            continue
        # 구 오염 감지: sub_text 첫 단어(구/시/군)가 href 경로에 포함돼야 함
        # 슬러그 규칙: 군은 "군" 접미사 제거(울주군 → 울주), 시도 동일하게 제거
        if sub_text and runtime_path.startswith("/danji/"):
            sub_gu_raw = sub_text.split()[0] if sub_text.split() else ""
            if sub_gu_raw and ("구" in sub_gu_raw or "시" in sub_gu_raw or "군" in sub_gu_raw):
                # 군/시 접미사 제거한 정규화 형태로도 비교
                sub_gu_norm = sub_gu_raw
                if sub_gu_norm.endswith("군"):
                    sub_gu_norm = sub_gu_norm[:-1]
                elif sub_gu_norm.endswith("시"):
                    sub_gu_norm = sub_gu_norm[:-1]
                if sub_gu_raw not in runtime_path and sub_gu_norm not in runtime_path:
                    issues.append({
                        "type": "gu_mismatch",
                        "url": url,
                        "runtime": runtime_path,
                        "sub": sub_text,
                        "detail": f"표시된 구 '{sub_gu_raw}' / '{sub_gu_norm}' 둘 다 URL 에 없음",
                    })
    return issues

def report_batch(name, results):
    fails = [r for r in results if not r["ok"]]
    print(f"\n[{name}] {len(results)}개 검사")
    print(f"  ✅ {len(results)-len(fails)}  ❌ {len(fails)}")
    for r in fails[:15]:
        print(f"  ❌ {r['label']}")
        print(f"     goto:  {r['url']}")
        print(f"     final: {r['final']}")
        print(f"     expect:{r['expected']}")
    return len(fails)

def main():
    print("=" * 70)
    print(f"실제 브라우저 검증 (Playwright + Chromium, host={HOST})")
    print(f"JS 실행 대기: {WAIT_MS}ms")
    print("=" * 70)

    # 검사 대상 URL 수집
    targets = []

    # 1) 허브/인덱스
    for u in ["/", "/gu/", "/dong/", "/ranking/"]:
        targets.append(("허브", HOST + u, None))

    # 2) 정적 페이지 샘플
    for url in sample_from_folder("gu", 6):
        targets.append(("gu", url, None))
    for url in sample_from_folder("dong", 6):
        targets.append(("dong", url, None))
    for url in sample_danji_by_region(1):   # 지역별 균등 샘플 (17개 지역 × 1개)
        targets.append(("danji", url, None))
    for url in sample_from_folder("ranking", 6):
        targets.append(("ranking", url, None))

    # 3) 리다이렉트 셸 (expected path 지정)
    targets.append(("shell-gu",     f"{HOST}/gu.html?name=강남구",             f"{HOST}/gu/강남구"))
    targets.append(("shell-gu2tok", f"{HOST}/gu.html?name=수원시 장안구",      f"{HOST}/gu/수원시-장안구"))
    targets.append(("shell-rank",   f"{HOST}/ranking.html?region=seoul&type=price", f"{HOST}/ranking/seoul-price"))
    targets.append(("shell-rank2",  f"{HOST}/ranking.html",                   f"{HOST}/ranking/"))

    total_fails = 0
    collected_links = []   # depth-1 링크 수집용

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 hwik-browser-verify",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        # PASS 1: 페이지 직접 열기
        # flake 완화: 실패 시 1회 재시도. 두 번 연속 실패해야 진짜 FAIL.
        # (CDN miss, 네트워크 일시 장애 대비. localhost 에선 거의 재시도 안 걸림.)
        results_by_cat = {}
        for cat, url, expected in targets:
            ok, final, final_path, expected_or_err = check_page(page, url, expected, f"{cat}: {url}")
            if not ok:
                page.wait_for_timeout(500)
                ok, final, final_path, expected_or_err = check_page(page, url, expected, f"{cat}: {url}")
            results_by_cat.setdefault(cat, []).append({
                "ok": ok, "url": url, "final": final, "expected": expected_or_err, "label": f"{cat}",
            })
            # 정적 gu/dong/danji/ranking 페이지에서 내부 링크 샘플 수집
            # (.html?query 형태의 리다이렉트 셸 링크는 PASS 1 에서 따로 검증하므로 제외)
            if ok and cat in ("gu", "dong", "danji", "ranking"):
                try:
                    hrefs = page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => e.getAttribute('href')).filter(h => h && h.startsWith('/') && !h.startsWith('//') && !h.includes('.html?'))"
                    )
                    for h in hrefs[:3]:
                        collected_links.append((cat, url, HOST + h))
                except Exception:
                    pass

        # 결과 출력 (카테고리별)
        for cat in ["허브","gu","dong","danji","ranking","shell-gu","shell-gu2tok","shell-rank","shell-rank2"]:
            if cat in results_by_cat:
                total_fails += report_batch(cat, results_by_cat[cat])

        # PASS 2: depth-1 내부 링크 클릭 (중복 제거, 최대 30개)
        seen = set()
        depth1 = []
        for cat, parent, link in collected_links:
            if link in seen: continue
            seen.add(link)
            depth1.append((cat, parent, link))
        depth1 = depth1[:30]

        print(f"\n--- PASS 2: 부모 페이지에서 수집한 내부 링크 {len(depth1)}개 클릭 검증 ---")
        depth1_results = []
        for cat, parent, link in depth1:
            ok, final, final_path, expected_or_err = check_page(page, link, None, f"{cat}-child")
            depth1_results.append({
                "ok": ok, "url": link, "final": final,
                "expected": expected_or_err, "label": f"{cat}-child (from {parent})",
            })
        total_fails += report_batch("depth-1", depth1_results)

        # PASS 3: danji 페이지의 주변 단지 런타임 href 오염 검사 (depth-2 클릭 포함)
        # 정적 HTML의 href 와 JS 실행 후 DOM의 href 가 다르면 런타임 덮어쓰기 버그
        danji_sample = sample_danji_by_region(1)  # 지역별 균등 (17개 지역 × 1개)
        print(f"\n--- PASS 3: danji {len(danji_sample)}개 페이지의 주변 단지 런타임 href 검사 ---")
        pass3_issues = []
        for url in danji_sample:
            issues = check_danji_runtime_nearby(page, url)
            pass3_issues.extend(issues)
        print(f"  검사 페이지: {len(danji_sample)}개  이슈: {len(pass3_issues)}건")
        for iss in pass3_issues[:20]:
            print(f"  ❌ [{iss['type']}] parent={iss['url']}")
            if 'static' in iss:
                print(f"     static : {iss['static']}")
                print(f"     runtime: {iss['runtime']}")
            if 'sub' in iss:
                print(f"     sub    : {iss['sub']}")
            if 'detail' in iss:
                print(f"     detail : {iss['detail']}")
        total_fails += len(pass3_issues)

        # PASS 4: PASS 3 에서 수집한 주변 단지 런타임 href 를 실제 클릭 이동 (depth-2)
        # 도착 URL 이 404.html 이거나 "찾을 수 없습니다" 타이틀이면 FAIL
        print(f"\n--- PASS 4: 주변 단지 depth-2 클릭 도착 검증 ---")
        depth2_fails = 0
        depth2_checked = 0
        for url in danji_sample[:10]:  # 20개는 오래 걸려서 10개로
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                page.wait_for_timeout(WAIT_MS + 1500)
                if is_404_page(page):
                    continue
                nearby_links = page.eval_on_selector_all(
                    ".nearby-item",
                    "els => els.slice(0,2).map(e => e.href)"  # 각 부모에서 주변단지 2개만
                )
                for link in nearby_links:
                    try:
                        page.goto(link, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                        page.wait_for_timeout(WAIT_MS + 1000)
                        depth2_checked += 1
                        if is_404_page(page):
                            depth2_fails += 1
                            print(f"  ❌ 404 튕김: {link}")
                            print(f"     from parent: {url}")
                    except Exception as e:
                        depth2_fails += 1
                        print(f"  ❌ 탐색 오류: {link} — {str(e)[:60]}")
            except Exception:
                pass
        print(f"  검사 이동: {depth2_checked}개  404 튕김: {depth2_fails}건")
        total_fails += depth2_fails

        browser.close()

    print("\n" + "=" * 70)
    if total_fails == 0:
        print("✅ 전부 정상 — 리다이렉트 튕김 없음")
    else:
        print(f"❌ 총 {total_fails}개 문제")
    print("=" * 70)
    return total_fails

if __name__ == "__main__":
    sys.exit(1 if main() > 0 else 0)
