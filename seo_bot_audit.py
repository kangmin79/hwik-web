#!/usr/bin/env python3
"""
Googlebot 시점 SEO 감사 — dong/gu/ranking 샘플 170개를 hwik.kr에서 받아 점검.
산출: seo_audit_report.json (상세) + 콘솔 요약

체크 항목:
  A. 기술: HTTP 상태, 응답 시간, 크기, gzip
  B. 메타: title/desc 길이+유니크, canonical, lang, noindex, OG
  C. 콘텐츠: h1, 본문 텍스트량, JSON-LD, 내부/외부 링크 수
  D. JS 의존도: 초기 HTML의 본문 유무 (Googlebot은 렌더하되 예산 적음)
  E. UX: viewport, 이미지 alt 비율

실행: python seo_bot_audit.py [--limit-dong 50 --limit-gu 50 --limit-ranking 70]
"""
import json, random, re, sys, time, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from pathlib import Path
import requests

HOST = "https://hwik.kr"
UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
TIMEOUT = 15
THREADS = 8

# ── 점수 임계치 ────────────────────────────────────────────
TITLE_MIN, TITLE_MAX = 20, 70
DESC_MIN,  DESC_MAX  = 100, 170
BODY_MIN_CHARS       = 300   # 이보다 적으면 Thin content 의심
INTERNAL_LINK_MIN    = 5

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "ko-KR,ko;q=0.9",
})


def fetch(url):
    t0 = time.time()
    try:
        r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        dt = time.time() - t0
        return {
            "url": url,
            "status": r.status_code,
            "final_url": r.url,
            "elapsed_ms": int(dt * 1000),
            "bytes": len(r.content),
            "content_type": r.headers.get("Content-Type", ""),
            "encoding": r.headers.get("Content-Encoding", ""),
            "html": r.text if "text/html" in r.headers.get("Content-Type", "") else "",
            "error": "",
        }
    except Exception as e:
        return {"url": url, "status": -1, "error": str(e)[:120], "html": ""}


def strip_tags(html):
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def audit(page):
    url, html, status = page["url"], page["html"], page["status"]
    out = {"url": url, "status": status, "fails": [], "warns": [], "info": {}}

    if status != 200 or not html:
        out["fails"].append(f"HTTP {status}")
        return out

    # A. 기술
    out["info"]["bytes"] = page["bytes"]
    out["info"]["elapsed_ms"] = page["elapsed_ms"]
    out["info"]["encoding"] = page["encoding"]
    if page["elapsed_ms"] > 3000:
        out["warns"].append(f"응답 느림 {page['elapsed_ms']}ms")
    if "gzip" not in page["encoding"] and "br" not in page["encoding"]:
        out["warns"].append(f"압축 없음 ({page['encoding'] or 'none'})")

    # B. 메타
    m = re.search(r"<title[^>]*>([^<]*)</title>", html, re.IGNORECASE)
    title = (m.group(1) if m else "").strip()
    out["info"]["title"] = title
    out["info"]["title_len"] = len(title)
    if not title:
        out["fails"].append("title 없음")
    elif len(title) < TITLE_MIN or len(title) > TITLE_MAX:
        out["warns"].append(f"title 길이 이상 {len(title)}자")

    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', html, re.IGNORECASE)
    desc = (m.group(1) if m else "").strip()
    out["info"]["description"] = desc
    out["info"]["desc_len"] = len(desc)
    if not desc:
        out["fails"].append("description 없음")
    elif len(desc) < DESC_MIN or len(desc) > DESC_MAX:
        out["warns"].append(f"description 길이 이상 {len(desc)}자")

    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', html, re.IGNORECASE)
    canonical = (m.group(1) if m else "").strip()
    out["info"]["canonical"] = canonical
    if not canonical:
        out["fails"].append("canonical 없음")
    else:
        canonical_path = canonical.replace(HOST, "")
        url_path = url.replace(HOST, "")
        if canonical_path.rstrip("/") != url_path.rstrip("/"):
            out["warns"].append(f"canonical 다른 URL 지목 → {canonical}")

    if re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', html, re.IGNORECASE):
        out["fails"].append("noindex 박힘")

    m = re.search(r'<html[^>]+lang=["\']([^"\']+)', html, re.IGNORECASE)
    lang = (m.group(1) if m else "").strip().lower()
    out["info"]["lang"] = lang
    if not lang:
        out["warns"].append("html lang 없음")
    elif not lang.startswith("ko"):
        out["warns"].append(f"html lang={lang} (한국어 아님)")

    # OpenGraph
    og_title = re.search(r'<meta[^>]+property=["\']og:title["\']', html, re.IGNORECASE)
    og_desc  = re.search(r'<meta[^>]+property=["\']og:description["\']', html, re.IGNORECASE)
    og_image = re.search(r'<meta[^>]+property=["\']og:image["\']', html, re.IGNORECASE)
    if not (og_title and og_desc and og_image):
        miss = [n for n, v in [("og:title", og_title), ("og:description", og_desc), ("og:image", og_image)] if not v]
        out["warns"].append(f"OG 태그 누락: {','.join(miss)}")

    # C. 콘텐츠
    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    out["info"]["h1_count"] = len(h1s)
    if len(h1s) == 0:
        out["fails"].append("h1 없음")
    elif len(h1s) > 1:
        out["warns"].append(f"h1 {len(h1s)}개 (권장 1개)")

    body_text = strip_tags(html)
    out["info"]["body_chars"] = len(body_text)
    if len(body_text) < BODY_MIN_CHARS:
        out["fails"].append(f"Thin content: 본문 {len(body_text)}자")

    jsonlds = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.IGNORECASE | re.DOTALL)
    parsed = 0
    for s in jsonlds:
        try:
            json.loads(s.strip())
            parsed += 1
        except Exception:
            out["warns"].append("JSON-LD 파싱 실패 블록 있음")
    out["info"]["jsonld_count"] = parsed
    if parsed == 0:
        out["warns"].append("JSON-LD 구조화 데이터 없음")

    # 링크 수
    anchors = re.findall(r'<a\b[^>]+href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    internal, external = 0, 0
    for href in anchors:
        if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
            continue
        if href.startswith("http"):
            if "hwik.kr" in href:
                internal += 1
            else:
                external += 1
        else:
            internal += 1
    out["info"]["internal_links"] = internal
    out["info"]["external_links"] = external
    if internal < INTERNAL_LINK_MIN:
        out["warns"].append(f"내부 링크 {internal}개 (고아 위험)")

    # D. JS 의존도 — noscript 안 보고, body_text에 실제 지역명/숫자 있는지
    # (랜딩은 렌더 전 빈 껍데기일 수 있음 — danji는 DATA 객체에서 렌더)
    if "데이터를 불러오는 중" in body_text or "Loading" in body_text:
        out["warns"].append("초기 HTML이 로딩 상태 (JS 렌더 의존 가능)")

    # E. UX
    if not re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.IGNORECASE):
        out["warns"].append("viewport 메타 없음")

    imgs = re.findall(r"<img\b([^>]*)>", html, re.IGNORECASE)
    with_alt = sum(1 for t in imgs if re.search(r'alt=["\']', t))
    out["info"]["img_total"] = len(imgs)
    out["info"]["img_alt"]   = with_alt
    if imgs and with_alt / len(imgs) < 0.5:
        out["warns"].append(f"이미지 alt 비율 {with_alt}/{len(imgs)}")

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-dong",    type=int, default=50)
    ap.add_argument("--limit-gu",      type=int, default=50)
    ap.add_argument("--limit-ranking", type=int, default=70)
    ap.add_argument("--limit-danji",   type=int, default=0)
    ap.add_argument("--only",          choices=["dong","gu","ranking","danji"], default=None,
                    help="특정 유형만 감사")
    args = ap.parse_args()

    random.seed(42)
    dong = json.loads(Path("dong-index.json").read_text(encoding="utf-8"))
    gu   = json.loads(Path("gu-index.json").read_text(encoding="utf-8"))
    rank = json.loads(Path("ranking-index.json").read_text(encoding="utf-8"))
    danji_stems = [f.stem for f in Path("danji").glob("*.html") if f.stem != "index"]

    dong_s  = random.sample(dong, min(args.limit_dong, len(dong)))
    gu_s    = random.sample(gu,   min(args.limit_gu, len(gu)))
    rank_s  = random.sample(rank, min(args.limit_ranking, len(rank)))
    danji_s = random.sample(danji_stems, min(args.limit_danji, len(danji_stems))) if args.limit_danji else []

    all_urls = {
        "dong":    [(f"{HOST}/dong/{s}.html", "dong") for s in dong_s],
        "gu":      [(f"{HOST}/gu/{s}.html",   "gu")   for s in gu_s],
        "ranking": [(f"{HOST}/ranking/{s}.html", "ranking") for s in rank_s],
        "danji":   [(f"{HOST}/danji/{s}.html", "danji") for s in danji_s],
    }
    if args.only:
        urls = all_urls[args.only]
    else:
        urls = all_urls["dong"] + all_urls["gu"] + all_urls["ranking"] + all_urls["danji"]

    print(f"대상: {len(urls)}개 (dong {len(dong_s)} / gu {len(gu_s)} / ranking {len(rank_s)} / danji {len(danji_s)})")
    print(f"UA: {UA[:60]}...")
    print()

    reports = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=THREADS) as ex:
        futs = {ex.submit(fetch, url): (url, kind) for url, kind in urls}
        for i, fu in enumerate(as_completed(futs), 1):
            url, kind = futs[fu]
            page = fu.result()
            rep = audit(page)
            rep["kind"] = kind
            reports.append(rep)
            if i % 30 == 0:
                print(f"  {i}/{len(urls)} 진행... ({time.time()-t0:.0f}s)")

    print(f"\n완료: {len(reports)}개 ({time.time()-t0:.0f}s)")

    # ── 유니크 체크 (title/desc) ────────────────────────────
    titles = Counter(r["info"].get("title", "") for r in reports if r["info"].get("title"))
    descs  = Counter(r["info"].get("description", "") for r in reports if r["info"].get("description"))
    dup_title = [t for t, n in titles.items() if n > 1 and t]
    dup_desc  = [d for d, n in descs.items()  if n > 1 and d]

    # ── 집계 ───────────────────────────────────────────────
    fail_counter = Counter()
    warn_counter = Counter()
    for r in reports:
        for f in r["fails"]: fail_counter[f.split(":")[0].split("(")[0].strip()] += 1
        for w in r["warns"]: warn_counter[w.split(":")[0].split("(")[0].strip()] += 1

    print("\n" + "=" * 70)
    print("  SEO 감사 요약 (Googlebot UA 기준)")
    print("=" * 70)
    print(f"\n[FAIL — 검색 유입 직접 영향]")
    if not fail_counter:
        print("  (없음)")
    for k, n in fail_counter.most_common():
        print(f"  {n:>4}건  {k}")

    print(f"\n[WARN — 개선 권장]")
    for k, n in warn_counter.most_common():
        print(f"  {n:>4}건  {k}")

    print(f"\n[유니크성]")
    print(f"  중복 title: {len(dup_title)}종")
    print(f"  중복 description: {len(dup_desc)}종")
    if dup_title[:3]:
        for t in dup_title[:3]:
            n = titles[t]
            print(f"    - '{t[:60]}...' × {n}")
    if dup_desc[:3]:
        for d in dup_desc[:3]:
            n = descs[d]
            print(f"    - '{d[:60]}...' × {n}")

    # 유형별 평균
    print(f"\n[유형별 본문 크기 평균]")
    for kind in ("dong", "gu", "ranking", "danji"):
        rs = [r for r in reports if r["kind"] == kind]
        if not rs: continue
        avg_body  = sum(r["info"].get("body_chars", 0) for r in rs) // len(rs)
        avg_ilink = sum(r["info"].get("internal_links", 0) for r in rs) // len(rs)
        avg_ms    = sum(r["info"].get("elapsed_ms", 0) for r in rs) // len(rs)
        print(f"  {kind:8s}: 본문 {avg_body:,}자 / 내부링크 {avg_ilink}개 / {avg_ms}ms")

    # 리포트 저장
    out = {
        "ts": int(time.time()),
        "host": HOST,
        "counts": {"total": len(reports), "fail_types": fail_counter, "warn_types": warn_counter},
        "dup_title_samples": dup_title[:10],
        "dup_desc_samples": dup_desc[:10],
        "reports": reports,
    }
    Path("seo_audit_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n상세 리포트: seo_audit_report.json ({Path('seo_audit_report.json').stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
