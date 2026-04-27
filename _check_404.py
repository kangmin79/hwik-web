"""오피스텔 페이지 404 전수 검사.

- sitemap_officetel_*.xml의 URL 전부 로컬 파일 실존 확인
- 빌드된 HTML의 internal href 추출 → 타겟 파일 실존 확인
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from collections import defaultdict

REPO = Path(__file__).resolve().parent
HOST = "https://hwik.kr"

# ── 1) sitemap URL 추출 ───────────────────────────────────
def extract_sitemap_urls(sitemap_path: Path) -> list[str]:
    txt = sitemap_path.read_text(encoding="utf-8")
    return re.findall(r"<loc>([^<]+)</loc>", txt)

# ── 2) URL → 로컬 파일 경로 매핑 ─────────────────────────
def url_to_local(url: str) -> Path | None:
    p = urlparse(url)
    if p.netloc and p.netloc != "hwik.kr":
        return None
    path = unquote(p.path)
    if path.endswith("/"):
        path += "index.html"
    return REPO / path.lstrip("/")

# ── 3) sitemap 검사 ───────────────────────────────────────
def check_sitemap(name: str) -> tuple[int, int, list[str]]:
    sm = REPO / name
    urls = extract_sitemap_urls(sm)
    missing: list[str] = []
    for u in urls:
        local = url_to_local(u)
        if not local or not local.exists():
            missing.append(u)
    return len(urls), len(missing), missing

# ── 4) 빌드된 HTML에서 internal href 추출 ────────────────
INT_HREF_RE = re.compile(r'href="(/[^"#?]*)["#?]')

def collect_internal_hrefs() -> dict[str, set[str]]:
    """{target_path: {referrer_paths...}}"""
    out: dict[str, set[str]] = defaultdict(set)
    # 검사 대상: officetel 관련 빌드 산출물만
    targets = []
    targets += list((REPO / "officetel").glob("*.html"))
    targets += list((REPO / "officetel" / "gu").glob("*.html"))
    targets += list((REPO / "officetel" / "dong").glob("*.html"))
    for f in targets:
        try:
            txt = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in INT_HREF_RE.finditer(txt):
            href = m.group(1)
            # 외부 도메인, 명백한 비페이지(#, ?, mailto) 제외 — 이미 정규식이 처리
            # data: 등 prefix는 / 시작 안 하니 제외됨
            out[href].add(str(f.relative_to(REPO)))
    return out

# ── 5) href 검사 ──────────────────────────────────────────
def check_internal_hrefs(href_map: dict[str, set[str]]) -> tuple[int, int, dict[str, set[str]]]:
    bad: dict[str, set[str]] = {}
    for href, refs in href_map.items():
        path = unquote(href)
        if path.endswith("/"):
            path += "index.html"
        # 핵심 자산 (CSS/JS) 제외
        if path.startswith("/danji/style.css"):
            continue  # 아파트 css — 오피스텔 페이지는 안 씀, 무시
        local = REPO / path.lstrip("/")
        if not local.exists():
            bad[href] = refs
    return len(href_map), len(bad), bad


def main() -> int:
    print("=" * 60)
    print("[1/2] Sitemap URL 전수 검사")
    print("=" * 60)
    grand_total, grand_missing = 0, 0
    for sm_name in ("sitemap_officetel_danji.xml", "sitemap_officetel_hubs.xml"):
        total, missing_n, missing = check_sitemap(sm_name)
        grand_total += total
        grand_missing += missing_n
        status = "OK" if missing_n == 0 else "FAIL"
        print(f"  {status} {sm_name}: {total:,} URL, missing={missing_n}")
        if missing:
            for u in missing[:10]:
                print(f"     - {u}")
            if len(missing) > 10:
                print(f"     ... ({len(missing)-10} more)")
    print(f"  ─ 합계: {grand_total:,} URL, missing={grand_missing}")

    print()
    print("=" * 60)
    print("[2/2] HTML 내부 href 전수 검사 (officetel 페이지)")
    print("=" * 60)
    href_map = collect_internal_hrefs()
    total, bad_n, bad = check_internal_hrefs(href_map)
    status = "OK" if bad_n == 0 else "FAIL"
    print(f"  {status} unique href={total:,}, broken={bad_n}")
    if bad:
        print()
        print("  깨진 링크 샘플 (최대 30개):")
        # 빈도순 정렬 (referrer 많은 것부터)
        sorted_bad = sorted(bad.items(), key=lambda x: -len(x[1]))
        for href, refs in sorted_bad[:30]:
            print(f"    [{len(refs):,}회] {href}")
            # 참조한 페이지 1~2개 샘플
            for r in list(refs)[:2]:
                print(f"        ← {r}")

    print()
    print("=" * 60)
    print(f"결과: sitemap missing={grand_missing}, href broken={bad_n}")
    print("=" * 60)
    return 0 if (grand_missing == 0 and bad_n == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
