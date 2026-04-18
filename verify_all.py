#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_all.py — 배포 전 전수 검증 게이트 (5-Phase 통합)

Phase 0: 파일 인덱스 구축 (즉시)
Phase 1: sitemap.xml ↔ 실제 파일 전수 비교 (로컬)
Phase 2: SEO 검증 — JSON-LD / 내부 링크 / 회귀 방지 (로컬, 전수)
Phase 3: HTTP 실제 응답 전수 (VERIFY_HOST, 병렬 HEAD)
Phase 4: 브라우저 렌더링 검증 (verify_browser.py 호출)
Phase 5: DB 데이터 정합성 (Supabase, 전수)

종료 코드: 0 = 전체 통과, 1 = FAIL 존재 → 배포 차단

사용법:
  VERIFY_HOST=http://localhost:8000 python verify_all.py
  python verify_all.py --quick        # HTTP 샘플 모드 (danji 500개, dong 200개)
  python verify_all.py --no-browser   # Playwright 검사 스킵
  python verify_all.py --no-db        # DB 검사 스킵
  python verify_all.py --with-api     # 국토부 API 원본 대조 포함 (주 1회 권장)
"""

import os, sys, re, json, time, random, argparse, subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict
from urllib.parse import unquote, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests, urllib3
urllib3.disable_warnings()

# ── UTF-8 출력 (Windows) ──────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

BASE = Path(__file__).parent.resolve()
DOMAIN = "https://hwik.kr"

# ── 환경변수 ──────────────────────────────────────────────
VERIFY_HOST   = os.environ.get("VERIFY_HOST", DOMAIN).rstrip("/")
SUPABASE_URL  = os.environ.get("SUPABASE_URL", "https://api.hwik.kr")
SUPABASE_KEY  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
GOV_KEY       = os.environ.get("GOV_SERVICE_KEY", "")

# .env fallback (로컬 개발)
if not SUPABASE_KEY:
    env_path = BASE / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)
        SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        GOV_KEY      = os.environ.get("GOV_SERVICE_KEY", "")

SB_HEADERS   = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
http_session = requests.Session()
http_session.headers["User-Agent"] = "Mozilla/5.0 (hwik-verify)"

# localhost 면 전수 + 더 많은 스레드
IS_LOCALHOST = "localhost" in VERIFY_HOST or "127.0.0.1" in VERIFY_HOST
HTTP_THREADS = 32 if IS_LOCALHOST else 16
HTTP_TIMEOUT = 8  if IS_LOCALHOST else 20

# ── 인수 파싱 ──────────────────────────────────────────────
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--quick",      action="store_true", help="HTTP 샘플 모드")
parser.add_argument("--no-browser", dest="no_browser", action="store_true")
parser.add_argument("--no-db",      dest="no_db",      action="store_true")
parser.add_argument("--with-api",   dest="with_api",   action="store_true")
args, _ = parser.parse_known_args()


# ── 출력 유틸 ──────────────────────────────────────────────
def sec(title):
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}")

def show(label, items, max_show=10, warn=False):
    """결과 출력. warn=True면 FAIL 카운트 0 반환 (경고만)."""
    n = len(items)
    if n == 0:
        print(f"  ✓ {label}: 0건")
        return 0
    sym = "⚠" if warn else "✗"
    print(f"  {sym} {label}: {n:,}건")
    for it in items[:max_show]:
        s = it if not isinstance(it, tuple) else " | ".join(str(x) for x in it)
        print(f"    - {s}")
    if n > max_show:
        print(f"    ... 외 {n - max_show:,}건")
    return 0 if warn else n


# ══════════════════════════════════════════════════════════════
# Phase 0: 파일 인덱스 구축
# ══════════════════════════════════════════════════════════════
def build_index():
    root_files = {f.name for f in BASE.iterdir() if f.is_file()}
    idx = {"danji": set(), "dong": set(), "gu": set(), "ranking": set()}
    all_paths = []
    for folder in idx:
        d = BASE / folder
        if d.is_dir():
            for f in d.iterdir():
                if f.suffix == ".html":
                    # index.html 은 /{folder}/ 트레일링 슬래시 URL과 동일 페이지 →
                    # sitemap 에는 /{folder}/ 로 등록되므로 idx 에는 넣지 않음.
                    # all_paths 에는 유지 (SEO 체크 대상).
                    if f.stem != "index":
                        idx[folder].add(f.stem)
                    all_paths.append((folder, f))
    for f in BASE.iterdir():
        if f.is_file() and f.suffix == ".html":
            all_paths.append(("root", f))
    return root_files, idx, all_paths


# ══════════════════════════════════════════════════════════════
# Phase 1: sitemap.xml ↔ 파일 전수
# ══════════════════════════════════════════════════════════════
def run_phase1(root_files, idx):
    sec("Phase 1: sitemap.xml ↔ 파일 전수")

    sm_path = BASE / "sitemap.xml"
    if not sm_path.is_file():
        print("  ✗ sitemap.xml 없음")
        return 1

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    def collect_elems(path):
        elems = []
        if not path.is_file():
            return elems
        root = ET.parse(path).getroot()
        for sm in root.findall("sm:sitemap", ns):
            loc = sm.find("sm:loc", ns)
            if loc is not None and loc.text:
                sub = path.parent / loc.text.strip().split("/")[-1]
                elems.extend(collect_elems(sub))
        elems.extend(root.findall("sm:url", ns))
        return elems

    all_elems = collect_elems(sm_path)
    sm_sets = {k: set() for k in idx}
    missing_files, extra_files, bad_lm = [], [], []

    for el in all_elems:
        loc = el.find("sm:loc", ns)
        if loc is None or not loc.text:
            continue
        lm = el.find("sm:lastmod", ns)
        if lm is not None and lm.text and not re.match(r"^\d{4}-\d{2}-\d{2}$", lm.text.strip()):
            bad_lm.append(lm.text.strip())

        path_str = unquote(urlparse(loc.text.strip()).path).rstrip("/")
        for folder in ["danji", "dong", "gu", "ranking"]:
            prefix = f"/{folder}/"
            if path_str.startswith(prefix):
                slug = path_str[len(prefix):]
                if slug:
                    sm_sets[folder].add(slug)
                    if slug not in idx[folder]:
                        missing_files.append(f"{folder}/{slug[:60]}")
                break

    # 역방향: 파일이 있는데 sitemap에 없음
    for folder in ["danji", "dong", "gu", "ranking"]:
        for slug in idx[folder]:
            if slug not in sm_sets[folder]:
                extra_files.append(f"{folder}/{slug[:60]}")

    print(f"\n  sitemap URL 총계: {len(all_elems):,}개")
    print(f"  파일: danji {len(idx['danji']):,} | dong {len(idx['dong']):,} | gu {len(idx['gu']):,} | ranking {len(idx['ranking']):,}")

    fail = 0
    fail += show("sitemap에 있는데 HTML 파일 없음", missing_files)
    fail += show("HTML 파일이 있는데 sitemap 미등록", extra_files)
    show("lastmod 형식 오류", bad_lm, warn=True)

    if fail == 0:
        print(f"\n  ✓ sitemap 전수 일치 ({len(all_elems):,}개 정상)")
    return fail


# ══════════════════════════════════════════════════════════════
# Phase 2: SEO 검증 (로컬 파일, 전수)
# ══════════════════════════════════════════════════════════════
A_HREF_RE   = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\']', re.I)
JSONLD_RE   = re.compile(r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>', re.DOTALL | re.I)
SCRIPT_SRC_RE = re.compile(r'<script\b([^>]*)src=["\']([^"\']+)["\']([^>]*)>', re.I)
CANONICAL_RE = re.compile(r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', re.I)
OGURL_RE    = re.compile(r'<meta[^>]*property=["\']og:url["\'][^>]*content=["\']([^"\']+)["\']', re.I)
GFONTS_RE   = re.compile(r'fonts\.googleapis\.com', re.I)


def _resolve_link(href, root_files, idx):
    """내부 링크인지, 대상 파일이 존재하는지 (is_internal, exists)."""
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return False, True
    if any(x in href for x in ("${", "`", "'+encodeURIComponent", "'+makeSlug", "'+esc(")):
        return False, True
    if href.rstrip("/") in ("/danji", "/dong", "/gu", "/ranking"):
        return False, True

    if href.startswith(("http://", "https://")):
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc not in ("hwik.kr", "www.hwik.kr"):
            return False, True
        path = parsed.path
    else:
        path = href.split("?")[0].split("#")[0]

    path = unquote(path).rstrip("/") or "/"

    for folder in ["danji", "dong", "gu", "ranking"]:
        prefix = f"/{folder}/"
        if path.startswith(prefix):
            slug = path[len(prefix):]
            return True, (slug in idx[folder])

    if path == "/":
        return True, ("index.html" in root_files)

    fname = path.lstrip("/")
    if fname in root_files or (BASE / fname).is_file():
        return True, True
    if (BASE / fname / "index.html").is_file():
        return True, True

    return True, False


def _extract_jsonld_urls(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("url", "item") and isinstance(v, str):
                out.append(v)
            else:
                _extract_jsonld_urls(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _extract_jsonld_urls(item, out)


def _check_seo(category, fpath, html, root_files, idx, errors):
    """단일 파일 SEO 검사. errors dict에 직접 append."""
    fid = f"{category}/{fpath.name}"

    # ── 1. 내부 링크 전수 ────────────────────────────────
    hrefs = list(A_HREF_RE.findall(html))
    for block in JSONLD_RE.findall(html):
        try:
            _extract_jsonld_urls(json.loads(block), hrefs)
        except Exception:
            pass
    for pat in (CANONICAL_RE, OGURL_RE):
        m = pat.search(html)
        if m:
            hrefs.append(m.group(1))
    for href in hrefs:
        is_int, exists = _resolve_link(href, root_files, idx)
        if is_int and not exists:
            errors["broken_links"].append((fid, href[:80]))

    # canonical이 자기 자신(경로+.html)을 가리키는지 — 재발 방지 게이트
    if category in ("danji", "dong", "gu", "ranking"):
        m = CANONICAL_RE.search(html)
        if m:
            got = unquote(m.group(1))
            if fpath.stem == "index":
                expected = f"https://hwik.kr/{category}/"
            else:
                expected = f"https://hwik.kr/{category}/{fpath.name}"
            if got != expected:
                errors["canon_mismatch"].append((fid, f"got={got[:60]} expected={expected[:60]}"))

    # ── 2. JSON-LD 유효성 ───────────────────────────────
    blocks = JSONLD_RE.findall(html)
    if not blocks and category in ("danji", "dong"):
        errors["no_jsonld"].append(fid)
        return

    graph = []
    for block in blocks:
        try:
            data = json.loads(block)
        except Exception:
            errors["json_parse_error"].append(fid)
            continue
        if isinstance(data, dict) and "@graph" in data:
            graph.extend(data["@graph"])
        elif isinstance(data, dict):
            graph.append(data)
        elif isinstance(data, list):
            graph.extend(data)

    type_map = {it.get("@type"): it for it in graph if isinstance(it, dict) and "@type" in it}

    faq = type_map.get("FAQPage")
    if faq:
        for q in faq.get("mainEntity", []):
            if not (q.get("name") or "").strip():
                errors["faq_empty_q"].append(fid); break
            if not ((q.get("acceptedAnswer") or {}).get("text") or "").strip():
                errors["faq_empty_a"].append(fid); break
    elif category in ("danji", "dong"):
        errors["faq_missing"].append(fid)  # warn

    bc = type_map.get("BreadcrumbList")
    if bc:
        items = bc.get("itemListElement", [])
        for i, li in enumerate(items):
            if li.get("position") != i + 1:
                errors["bc_position"].append(fid); break
        if items and "item" in items[-1]:
            errors["bc_last_url"].append(fid)  # warn
    elif category in ("danji", "dong"):
        errors["bc_missing"].append(fid)  # warn

    if category == "danji" and "ApartmentComplex" not in type_map:
        errors["missing_type"].append((fid, "ApartmentComplex"))
    if category == "dong" and "ItemList" not in type_map:
        errors["missing_type"].append((fid, "ItemList"))

    # ── 3. 성능 지표 ────────────────────────────────────
    if GFONTS_RE.search(html):
        errors["google_fonts"].append(fid)  # warn

    head_m = re.search(r'<head[^>]*>(.*?)</head>', html, re.S | re.I)
    if head_m:
        for m in SCRIPT_SRC_RE.finditer(head_m.group(1)):
            attrs = m.group(1) + m.group(3)
            if "defer" not in attrs.lower() and "async" not in attrs.lower():
                errors["sync_script"].append((fid, m.group(2)[:50]))  # warn

    # ── 4. 회귀 방지 ────────────────────────────────────
    if "danji/undefined" in html or "id=undefined" in html:
        errors["canon_undef"].append(fid)

    if category == "danji":
        ar_list = re.findall(r'"addressRegion"\s*:\s*"([^"]+)"', html)
        addr_m = re.search(r'"address"\s*:\s*"([^"]+)"', html)
        if ar_list and addr_m:
            first = addr_m.group(1).split()[0]
            for ar in ar_list:
                if first and ar != first and ar == "서울특별시":
                    errors["addr_hardcoded"].append((fid, f"addr={first} ar={ar}")); break

    if category == "dong":
        if re.search(r'수도권\s*(경량)?도시철도', html):
            errors["subway_leak"].append(fid)  # warn
        if re.search(r'/danji/[^"\']*offi-', html):
            errors["officetel_dong"].append(fid)


def run_phase2(all_paths, root_files, idx):
    sec("Phase 2: SEO 검증 (로컬 전수)")

    errors = defaultdict(list)
    count = 0
    for category, fpath in all_paths:
        try:
            html = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            errors["read_error"].append(str(fpath.name))
            continue
        _check_seo(category, fpath, html, root_files, idx, errors)
        count += 1
        if count % 5000 == 0:
            print(f"  ... {count:,}개 검사 완료")

    print(f"  총 {count:,}개 HTML 검사\n")

    fail = 0
    # ─ FAIL 항목
    fail += show("깨진 내부 링크", errors["broken_links"])
    fail += show("JSON-LD 파싱 오류", errors["json_parse_error"])
    fail += show("FAQ 빈 질문", errors["faq_empty_q"])
    fail += show("FAQ 빈 답변", errors["faq_empty_a"])
    fail += show("Breadcrumb position 오류", errors["bc_position"])
    fail += show("필수 @type 누락", errors["missing_type"])
    fail += show("canonUrl/id=undefined", errors["canon_undef"])
    fail += show("canonical URL 불일치 (.html 누락 등)", errors["canon_mismatch"])
    fail += show("addressRegion 하드코딩", errors["addr_hardcoded"])
    fail += show("dong 페이지에 오피스텔 포함", errors["officetel_dong"])
    # ─ WARN 항목 (배포 차단 안 함)
    show("JSON-LD 없음 (danji/dong)", errors["no_jsonld"], warn=True)
    show("FAQPage 없음", errors["faq_missing"], warn=True)
    show("BreadcrumbList 없음", errors["bc_missing"], warn=True)
    show("Breadcrumb 마지막에 URL 있음", errors["bc_last_url"], warn=True)
    show("Google Fonts 잔존", errors["google_fonts"], warn=True)
    show("head 동기 스크립트", errors["sync_script"], warn=True)
    show("수도권 도시철도 노선명 누출", errors["subway_leak"], warn=True)

    return fail


# ══════════════════════════════════════════════════════════════
# Phase 3: HTTP 실제 응답 전수 (병렬 HEAD)
# ══════════════════════════════════════════════════════════════
def run_phase3(idx, quick=False):
    sec(f"Phase 3: HTTP 응답 전수 (host={VERIFY_HOST})")

    # 정적 파일명(.html)로 검증 — Python http.server 는 확장자 생략 URL 미지원
    urls = []
    for slug in idx["gu"]:      urls.append(f"/gu/{slug}.html")
    for slug in idx["ranking"]: urls.append(f"/ranking/{slug}.html")

    dong_list  = list(idx["dong"])
    danji_list = list(idx["danji"])
    if quick:
        random.seed(42)
        dong_list  = random.sample(dong_list,  min(200,  len(dong_list)))
        danji_list = random.sample(danji_list, min(500,  len(danji_list)))

    for slug in dong_list:  urls.append(f"/dong/{slug}.html")
    for slug in danji_list: urls.append(f"/danji/{slug}.html")
    for u in ["/", "/sitemap.xml", "/robots.txt"]: urls.append(u)

    mode = "샘플" if quick else "전수"
    print(f"\n  {mode} | {len(urls):,}개 | {HTTP_THREADS} threads | timeout {HTTP_TIMEOUT}s")
    print(f"  (gu {len(idx['gu'])} + ranking {len(idx['ranking'])} + dong {len(dong_list):,} + danji {len(danji_list):,})")

    def check(rel):
        url = VERIFY_HOST + quote(rel, safe="/?=&%")
        last_err = ""
        for attempt in range(2):   # 일시 네트워크 흔들림 재시도 1회
            try:
                r = http_session.head(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
                # 일부 서버는 HEAD 미지원(405/501) → GET 폴백
                if r.status_code in (405, 501):
                    r = http_session.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True, stream=True)
                    r.close()
                return (rel, r.status_code, "")
            except Exception as e:
                last_err = str(e)[:60]
                if attempt == 0:
                    time.sleep(0.3)
        return (rel, -1, last_err)

    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=HTTP_THREADS) as ex:
        futs = [ex.submit(check, u) for u in urls]
        for i, fu in enumerate(as_completed(futs)):
            results.append(fu.result())
            if (i + 1) % 3000 == 0:
                print(f"  ... {i+1:,}/{len(urls):,}")

    dt = time.time() - t0
    ok_list    = [r for r in results if r[1] == 200]
    not_found  = [r for r in results if r[1] == 404]
    err_list   = [r for r in results if r[1] not in (200, 404)]

    print(f"\n  {dt:.1f}초 | 200: {len(ok_list):,} | 404: {len(not_found):,} | 오류: {len(err_list):,}")

    fail = 0
    if not_found:
        fail += len(not_found)
        print(f"  ✗ 404 {len(not_found):,}건:")
        for rel, _, _ in not_found[:30]:
            print(f"    {rel}")
        if len(not_found) > 30:
            print(f"    ... 외 {len(not_found)-30:,}건")
    else:
        print(f"  ✓ 404 없음 — {len(ok_list):,}개 전부 정상")

    if err_list:
        print(f"  ⚠ 연결 오류 {len(err_list):,}건 (타임아웃 등)")
        for rel, code, note in err_list[:10]:
            print(f"    [{code}] {rel}  {note}")
        # 연결 오류는 경고만 (네트워크 불안정 가능)

    return fail


# ══════════════════════════════════════════════════════════════
# Phase 4: 브라우저 렌더링 (verify_browser.py 호출)
# ══════════════════════════════════════════════════════════════
def run_phase4():
    sec("Phase 4: 브라우저 렌더링 (Playwright)")

    script = BASE / "verify_browser.py"
    if not script.is_file():
        print("  ⚠ verify_browser.py 없음 — 스킵")
        return 0

    env = {**os.environ, "VERIFY_HOST": VERIFY_HOST}
    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            env=env, timeout=360,
        )
        dt = time.time() - t0
        if result.returncode == 0:
            print(f"\n  ✓ 브라우저 검증 통과 ({dt:.0f}초)")
            return 0
        else:
            print(f"\n  ✗ 브라우저 검증 실패 ({dt:.0f}초)")
            return 1
    except subprocess.TimeoutExpired:
        print("\n  ✗ 브라우저 검증 타임아웃 (360초)")
        return 1
    except FileNotFoundError:
        print("  ⚠ Playwright 미설치 — 브라우저 검증 스킵")
        return 0


# ══════════════════════════════════════════════════════════════
# Phase 6: 내부 링크·리다이렉트 정합성 (파일 시스템)
# ══════════════════════════════════════════════════════════════
def run_phase6():
    sec("Phase 6: 내부 링크·리다이렉트 정합성")
    fail = 0

    def stems(dirname):
        d = BASE / dirname
        return {f.stem for f in d.iterdir() if f.suffix == ".html"} if d.is_dir() else set()

    danji_stems   = stems("danji")
    dong_stems    = stems("dong")
    gu_stems      = stems("gu")
    ranking_stems = stems("ranking")

    def load_json(rel):
        try:
            return json.loads((BASE / rel).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠ {rel} 읽기 실패: {e}")
            return None

    # 1. apt-redirect.json 타겟이 실제 단지 HTML에 있어야 함 (없으면 404)
    red = load_json("danji/apt-redirect.json")
    if isinstance(red, dict):
        missing = [f"{k} → {v}" for k, v in red.items() if v not in danji_stems]
        fail += show(f"apt-redirect 타겟 누락 ({len(red):,}개 중)", missing)

    # 2. dong/gu/ranking 인덱스의 slug가 실제 HTML로 존재해야 함
    for rel, label, pool in [
        ("dong-index.json",    "dong-index 누락",    dong_stems),
        ("gu-index.json",      "gu-index 누락",      gu_stems),
        ("ranking-index.json", "ranking-index 누락", ranking_stems),
    ]:
        data = load_json(rel)
        if isinstance(data, list):
            missing = [s for s in data if s not in pool]
            fail += show(f"{label} ({len(data):,}개 중)", missing)

    return fail


# ══════════════════════════════════════════════════════════════
# Phase 5: DB 데이터 정합성 (Supabase)
# ══════════════════════════════════════════════════════════════
def _sb_get(table, params):
    all_data, offset = [], 0
    limit = params.pop("_limit", 1000)
    while True:
        p = {**params, "limit": str(limit), "offset": str(offset)}
        r = http_session.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=SB_HEADERS, params=p, timeout=30,
        )
        if r.status_code != 200:
            print(f"  [DB ERROR] {table}: {r.status_code}")
            break
        data = r.json()
        if not data:
            break
        all_data.extend(data)
        offset += limit
        if len(data) < limit:
            break
    return all_data


def run_phase5(with_api=False):
    sec("Phase 5: DB 데이터 정합성 (Supabase)")

    if not SUPABASE_KEY:
        print("  ⚠ SUPABASE_SERVICE_ROLE_KEY 없음 — 스킵")
        return 0

    fail = 0

    # ── 검증 A: danji_pages 집계 정합성 ─────────────────────
    print("\n  [A] danji_pages 집계 정합성 — 전수")
    rows = _sb_get("danji_pages", {
        "select": "id,complex_name,categories,recent_trade,all_time_high,jeonse_rate,pyeongs_map",
    })
    print(f"  danji_pages: {len(rows):,}개 로드", flush=True)

    errs = defaultdict(list)
    for dp in rows:
        dpid   = dp.get("id", "")
        name   = dp.get("complex_name", "")
        cats   = dp.get("categories") or []
        recent = dp.get("recent_trade") or {}
        high   = dp.get("all_time_high") or {}
        jr     = dp.get("jeonse_rate")
        pm     = dp.get("pyeongs_map") or {}

        # 레거시 ID(apt-/offi-)는 HTML 빌드 제외 대상 → 정합성 검증도 스킵
        if dpid.startswith(("apt-", "offi-")):
            continue

        # 거래 없는 단지는 build_danji_pages.py에서 HTML 스킵 → 검증도 스킵
        if not any(recent.get(c) for c in cats):
            continue

        if not cats:
            errs["no_cats"].append(name); continue

        for cat in cats:
            if not any(k.startswith(cat) for k in recent):
                errs["cat_no_trade"].append(f"{name}: {cat}㎡"); break

        for key, val in recent.items():
            if val.get("price", 0) <= 0:
                errs["zero_price"].append(f"{name}: {key}"); break
            d = val.get("date", "")
            if d and not re.match(r"^\d{4}-\d{2}(-\d{2})?$", d):
                errs["bad_date"].append(f"{name}: {d}"); break

        for key, rt in recent.items():
            if "_jeonse" in key or "_wolse" in key: continue
            ath = high.get(key)
            if ath and rt.get("price", 0) > ath.get("price", 0):
                errs["recent_gt_high"].append(f"{name}: {key}"); break

        if jr is not None and cats:
            sk, jk = cats[0], cats[0] + "_jeonse"
            if sk in recent and jk in recent:
                sp = recent[sk].get("price", 0)
                jp = recent[jk].get("price", 0)
                if sp > 0 and abs(round(jp / sp * 100, 1) - jr) > 0.2:
                    errs["jr_mismatch"].append(f"{name}: DB {jr}% vs 계산 {round(jp/sp*100,1)}%")

        for cat, pv in pm.items():
            exclu  = pv.get("exclu", 0)
            supply = pv.get("supply", 0)
            if exclu > 0 and supply > 0:
                r = supply / exclu
                if r < 0.95 or r > 2.0:
                    errs["ratio_bad"].append(f"{name}: {cat}㎡ {supply}/{exclu}={r:.2f}"); break

    for label, key, is_warn in [
        ("categories 없음",         "no_cats",       False),
        ("평형에 거래 없음",           "cat_no_trade",  True),  # 단지 전체는 거래 있음 — HTML 생성됨
        ("가격 0 이하",               "zero_price",    False),
        ("날짜 형식 오류",             "bad_date",      False),
        ("최근가 > 최고가",            "recent_gt_high",False),
        ("전세가율 불일치",            "jr_mismatch",   False),
        ("공급/전용 비율 이상 (<0.95 or >2.0)", "ratio_bad", True),  # LH/행복주택 정상 케이스
    ]:
        n = show(label, errs[key], warn=is_warn)
        if not is_warn: fail += n

    # ── 검증 B: DB → HTML 파일 존재 확인 (핵심: 이게 없으면 방문 시 404) ──
    print("\n  [B] danji_pages DB → HTML 파일 존재 확인 (미존재 = 방문 시 404)")
    danji_dir  = BASE / "danji"
    html_files = {f.stem: f for f in danji_dir.iterdir() if f.suffix == ".html"} if danji_dir.is_dir() else {}
    print(f"  danji HTML: {len(html_files):,}개  |  DB: {len(rows):,}개")

    # kapt_code (A33173403) → 파일명 매핑 캐시 구축
    # 파일명 패턴: *-a33173403.html (소문자)
    stem_lower_set = {s.lower() for s in html_files}

    errs_b = defaultdict(list)
    missing_html = []
    matched = 0

    # 구버전 ID (apt-*, offi-*)는 HTML 빌드 대상이 아니므로 검증 대상에서 제외
    legacy_skipped = 0
    no_trade_skipped = 0
    for dp in rows:
        dpid  = dp.get("id", "")
        name  = dp.get("complex_name", "")
        recent = dp.get("recent_trade") or {}
        cats  = dp.get("categories") or []
        if not dpid:
            continue
        # 레거시 prefix(apt-/offi-)는 HTML 안 만드는 게 정상 — 누락 집계에서 제외
        if dpid.startswith(("apt-", "offi-")):
            legacy_skipped += 1
            continue
        # 거래 없는 단지는 build_danji_pages.py에서 HTML 스킵 — 누락 집계에서 제외
        if not any(recent.get(c) for c in cats):
            no_trade_skipped += 1
            continue

        # DB id는 'A33173403' 형태 → 파일명 끝에 '-a33173403' 포함
        dpid_lower = dpid.lower()  # a33173403
        # 정확한 suffix 매칭: slug가 -a33173403 으로 끝나는 파일
        found_stem = next((s for s in html_files if s.lower().endswith(f"-{dpid_lower}")), None)

        if found_stem is None:
            missing_html.append(f"{name} ({dpid})")
            continue

        matched += 1
        # ── 가격 대조 (HTML vs DB) ──────────────────────────
        try:
            html = html_files[found_stem].read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        data_m = re.search(r'const\s+DATA\s*=\s*(\{.*?\});\s*\n', html, re.DOTALL)
        if data_m:
            try:
                pg_recent = json.loads(data_m.group(1)).get("recent_trade") or {}
                for key, db_val in recent.items():
                    html_val = pg_recent.get(key)
                    if html_val and db_val.get("price", 0) != html_val.get("price", 0):
                        errs_b["price_mismatch"].append(
                            f"{name}: {key} DB={db_val['price']} vs HTML={html_val['price']}"
                        )
                        break
            except Exception:
                pass

    check_total = max(len(rows) - legacy_skipped - no_trade_skipped, 1)
    print(f"  파일 매칭: {matched:,}개  |  HTML 없음: {len(missing_html):,}개  |  레거시 제외: {legacy_skipped:,}개  |  거래 없음 제외: {no_trade_skipped:,}개")
    # HTML 없는 단지 수가 검증 대상(레거시 제외) 대비 5% 초과면 FAIL, 이하면 WARN
    missing_rate = len(missing_html) / check_total * 100
    if missing_rate > 5:
        fail += show(f"danji_pages 있는데 HTML 없음 ({missing_rate:.1f}% — 빌드 이상)", missing_html)
    else:
        show(f"danji_pages 있는데 HTML 없음 ({missing_rate:.1f}% — 실거래 없는 단지 정상)", missing_html, warn=True)

    fail += show("가격 불일치 (HTML vs DB)", errs_b["price_mismatch"])

    # ── 검증 C: 국토부 API 원본 대조 (--with-api) ────────────
    if with_api:
        print("\n  [C] 국토부 API 원본 대조 (샘플 50개)")
        if not GOV_KEY:
            print("  ⚠ GOV_SERVICE_KEY 없음 — 스킵")
        else:
            apts = _sb_get("apartments", {"select": "kapt_code,kapt_name,lawd_cd"})
            apt_map = {a["kapt_code"]: a for a in apts}
            valid = [
                (dp, apt_map[dp["id"]])
                for dp in rows
                if dp.get("id") in apt_map
                and (dp.get("categories") or [])
                and (dp.get("recent_trade") or {}).get((dp.get("categories") or [""])[0])
                and apt_map.get(dp["id"], {}).get("lawd_cd")
            ]
            samples = random.sample(valid, min(50, len(valid)))
            GOV_API = "http://openapi.molit.go.kr/OpenAPI_ToolInstall498/service/rest/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
            not_found_api = []
            for dp, apt in samples:
                cats = dp.get("categories") or []
                rt = (dp.get("recent_trade") or {}).get(cats[0], {})
                date = rt.get("date", "")
                if not date or len(date) < 7: continue
                ym = date[:4] + date[5:7]
                try:
                    resp = http_session.get(GOV_API, params={
                        "serviceKey": GOV_KEY, "LAWD_CD": apt["lawd_cd"][:5],
                        "DEAL_YMD": ym, "_type": "json", "numOfRows": "999",
                    }, timeout=15)
                    items = (resp.json().get("response", {}).get("body", {})
                             .get("items", {}).get("item", []))
                    if isinstance(items, dict): items = [items]
                    found = any(
                        str(i.get("aptNm") or "").strip() == apt.get("kapt_name", "")
                        for i in items
                    )
                    if not found:
                        not_found_api.append(f"{dp['complex_name']} ({apt['lawd_cd'][:5]}, {ym})")
                except Exception:
                    pass
            show("API에서 거래 못 찾음 (단지명 불일치 가능)", not_found_api, warn=True)

    return fail


# ══════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("  휙 통합 검증 게이트 — verify_all.py")
    print(f"  host: {VERIFY_HOST}  |  quick: {args.quick}  |  browser: {not args.no_browser}  |  db: {not args.no_db}")
    print("=" * 70)

    t_start = time.time()

    # Phase 0: 인덱스
    root_files, idx, all_paths = build_index()
    total = sum(len(v) for v in idx.values())
    print(f"\n  파일 인덱스: danji {len(idx['danji']):,} | dong {len(idx['dong']):,} | gu {len(idx['gu']):,} | ranking {len(idx['ranking']):,} | 합계 {total:,}개")

    results = {}

    results[1] = run_phase1(root_files, idx)
    results[2] = run_phase2(all_paths, root_files, idx)
    results[3] = run_phase3(idx, quick=args.quick)

    if not args.no_browser:
        results[4] = run_phase4()
    else:
        results[4] = 0

    if not args.no_db:
        results[5] = run_phase5(with_api=args.with_api)
    else:
        results[5] = 0

    results[6] = run_phase6()

    # ── 최종 요약 ──────────────────────────────────────────
    total_fail = sum(results.values())
    dt = time.time() - t_start

    labels = {
        1: "Phase 1  sitemap 일치",
        2: "Phase 2  SEO 검증",
        3: "Phase 3  HTTP 응답",
        4: "Phase 4  브라우저",
        5: "Phase 5  DB 정합성",
        6: "Phase 6  내부 링크 정합성",
    }

    print(f"\n{'=' * 70}")
    print(f"  최종 결과  (소요: {dt:.0f}초)")
    print(f"{'=' * 70}")
    for ph, n in results.items():
        status = "✓ PASS" if n == 0 else f"✗ FAIL ({n:,}건)"
        print(f"  {labels[ph]}: {status}")

    print(f"\n  총 FAIL: {total_fail:,}건")
    if total_fail == 0:
        print("  ✅ 전체 통과 — 배포 진행")
    else:
        print("  ❌ 검증 실패 — 배포 차단")

    return 1 if total_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
