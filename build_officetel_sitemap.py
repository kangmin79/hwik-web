"""build_officetel_sitemap.py — 오피스텔 전용 sitemap 생성 (아파트와 분리).

산출:
  /sitemap_officetel.xml          ← 오피스텔 sitemapindex (단지+허브)
  /sitemap_officetel_danji.xml    ← 9,833 단지 페이지
  /sitemap_officetel_hubs.xml     ← gu/dong/ranking + officetel/index

URL 단일 소스 — slug_utils.make_dong_slug / gu_url_slug 사용.
빌드된 HTML 파일 실존 확인 후 sitemap 등록 (없는 URL 절대 등록 X).

루트 sitemap.xml 의 sitemapindex 에 sitemap_officetel.xml 항목 추가 필요.
"""
from __future__ import annotations

import html
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote as url_quote

# 아파트 slug_utils 재사용 — dong/gu URL 패턴 일치
sys.path.insert(0, str(Path(__file__).resolve().parent))
from slug_utils import make_dong_slug, gu_url_slug  # noqa: E402

import json
import urllib.request

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

REPO = Path(__file__).resolve().parent
OFFI_DIR = REPO / "officetel"

SB = "https://jqaxejgzkchxbfzgzyzi.supabase.co"


def _load_env() -> None:
    p = REPO / ".env"
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


def fetch_officetels() -> list[dict]:
    out: list[dict] = []
    offset = 0
    while True:
        url = (f"{REST}/officetels?select=id,sido,sgg,umd,url,jibun_addr,updated_at"
               f"&order=sido,sgg,umd,id&limit=1000&offset={offset}")
        req = urllib.request.Request(url, headers=H)
        rows = json.loads(urllib.request.urlopen(req, timeout=60).read())
        if not rows:
            break
        out += rows
        offset += 1000
    return out


def _xml_url(loc: str, lastmod: str, changefreq: str, priority: str) -> str:
    return (f"  <url><loc>{html.escape(loc)}</loc>"
            f"<lastmod>{lastmod}</lastmod>"
            f"<changefreq>{changefreq}</changefreq>"
            f"<priority>{priority}</priority></url>")


def write_xml(path: Path, urls: list[str]) -> None:
    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    body += "\n".join(urls)
    body += "\n</urlset>\n"
    path.write_text(body, encoding="utf-8")


def build_danji_sitemap(officetels: list[dict]) -> tuple[Path, int]:
    """9,833 단지 페이지. url 컬럼 신뢰 + 빌드 파일 실존 확인."""
    urls: list[str] = []
    skipped = 0
    for o in officetels:
        url_path = o.get("url") or ""
        if not url_path:
            skipped += 1
            continue
        # 파일 실존 검증 (sitemap에 깨진 URL 절대 등록 안 함)
        local = REPO / url_path.lstrip("/")
        if not local.exists():
            skipped += 1
            continue
        # sitemap URL은 percent-encoded 표기로 통일 (RFC 3986, 다른 sub sitemap 모두 동일)
        enc_path = "/".join(url_quote(seg) for seg in url_path.split("/"))
        loc = f"https://hwik.kr{enc_path}"
        lastmod = (o.get("updated_at") or TODAY)[:10]
        urls.append(_xml_url(loc, lastmod, "weekly", "0.7"))

    out = REPO / "sitemap_officetel_danji.xml"
    write_xml(out, urls)
    return out, skipped


def build_hubs_sitemap(officetels: list[dict]) -> tuple[Path, dict]:
    """허브 페이지 — gu / dong / ranking / officetel index."""
    from collections import defaultdict

    gu_keys: set[tuple[str, str]] = set()
    dong_groups: dict[tuple[str, str, str], str] = {}  # key → first jibun_addr
    sidos: set[str] = set()

    for o in officetels:
        sido = o.get("sido") or ""
        sgg = o.get("sgg") or ""
        umd = o.get("umd") or ""
        if sido:
            sidos.add(sido)
        if sido and sgg:
            gu_keys.add((sido, sgg))
        if sido and sgg and umd:
            key = (sido, sgg, umd)
            if key not in dong_groups:
                dong_groups[key] = o.get("jibun_addr") or ""

    urls: list[str] = []

    # 루트 인덱스
    if (OFFI_DIR / "index.html").exists():
        urls.append(_xml_url("https://hwik.kr/officetel/", TODAY, "daily", "0.9"))

    # gu 페이지
    gu_count = 0
    for (sido, sgg) in sorted(gu_keys):
        slug = gu_url_slug(sido, sgg)
        if not slug:
            continue
        local = OFFI_DIR / "gu" / f"{slug}.html"
        if not local.exists():
            continue
        loc = f"https://hwik.kr/officetel/gu/{url_quote(slug)}.html"
        urls.append(_xml_url(loc, TODAY, "weekly", "0.6"))
        gu_count += 1

    # dong 페이지
    dong_count = 0
    for (sido, sgg, umd), addr in dong_groups.items():
        slug = make_dong_slug(sgg, umd, addr)
        if not slug:
            continue
        local = OFFI_DIR / "dong" / f"{slug}.html"
        if not local.exists():
            continue
        loc = f"https://hwik.kr/officetel/dong/{url_quote(slug)}.html"
        urls.append(_xml_url(loc, TODAY, "weekly", "0.6"))
        dong_count += 1

    # ranking
    rk_count = 0
    if (OFFI_DIR / "ranking.html").exists():
        urls.append(_xml_url("https://hwik.kr/officetel/ranking.html", TODAY, "weekly", "0.5"))
        rk_count += 1
    for sido in sorted(sidos):
        local = OFFI_DIR / f"ranking-{sido}.html"
        if not local.exists():
            continue
        loc = f"https://hwik.kr/officetel/ranking-{url_quote(sido)}.html"
        urls.append(_xml_url(loc, TODAY, "weekly", "0.5"))
        rk_count += 1

    out = REPO / "sitemap_officetel_hubs.xml"
    write_xml(out, urls)
    return out, {"gu": gu_count, "dong": dong_count, "ranking": rk_count, "total": len(urls)}


def build_index() -> Path:
    """오피스텔 sitemapindex — 두 sub sitemap 묶음."""
    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for name in ("sitemap_officetel_danji.xml", "sitemap_officetel_hubs.xml"):
        body += (f"  <sitemap><loc>https://hwik.kr/{name}</loc>"
                 f"<lastmod>{TODAY}</lastmod></sitemap>\n")
    body += "</sitemapindex>\n"
    out = REPO / "sitemap_officetel.xml"
    out.write_text(body, encoding="utf-8")
    return out


def update_root_sitemap_index() -> bool:
    """루트 sitemap.xml 의 sitemapindex 에 sitemap_officetel.xml 항목 추가 (중복 방지)."""
    root = REPO / "sitemap.xml"
    if not root.exists():
        return False
    src = root.read_text(encoding="utf-8")
    if "sitemap_officetel.xml" in src:
        return False  # 이미 등록
    # </sitemapindex> 직전에 삽입
    needle = "</sitemapindex>"
    line = (f"  <sitemap><loc>https://hwik.kr/sitemap_officetel.xml</loc>"
            f"<lastmod>{TODAY}</lastmod></sitemap>\n")
    new_src = src.replace(needle, line + needle)
    root.write_text(new_src, encoding="utf-8")
    return True


def main() -> int:
    print("officetels 로드...")
    officetels = fetch_officetels()
    print(f"  {len(officetels):,}건")

    print("\nsitemap_officetel_danji.xml 빌드...")
    p_danji, skipped = build_danji_sitemap(officetels)
    print(f"  → {p_danji.name}  ({len(officetels)-skipped:,}/{len(officetels):,} 등록, {skipped:,} 스킵=빌드파일없음)")

    print("\nsitemap_officetel_hubs.xml 빌드...")
    p_hubs, stat = build_hubs_sitemap(officetels)
    print(f"  → {p_hubs.name}  (gu={stat['gu']}, dong={stat['dong']}, ranking={stat['ranking']}, total={stat['total']})")

    print("\nsitemap_officetel.xml (인덱스) 빌드...")
    p_idx = build_index()
    print(f"  → {p_idx.name}")

    print("\n루트 sitemap.xml 업데이트...")
    added = update_root_sitemap_index()
    print(f"  → {'추가됨' if added else '이미 등록'}")

    print("\n완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
