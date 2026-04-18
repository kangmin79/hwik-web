# -*- coding: utf-8 -*-
"""
build_dong_index.py — /dong/ 폴더 인덱스 페이지 생성

dong/*.html 스캔 → 지역·구별로 묶어 dong/index.html 생성.
gu/index.html 과 동일한 스타일·구조.

단독 실행:
  python build_dong_index.py

빌드 파이프라인에서 build_dong_pages.py 완료 후 호출해도 됨.
"""
import os, sys, html as html_mod, json
from urllib.parse import quote as url_quote
from collections import defaultdict
from datetime import datetime, timezone

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

BASE = os.path.dirname(os.path.abspath(__file__))
DONG_DIR = os.path.join(BASE, "dong")

# 지역 라벨 → 풀네임 (OG/타이틀용)
REGION_FULL = {
    "서울": "서울특별시", "인천": "인천광역시", "경기": "경기도",
    "부산": "부산광역시", "대구": "대구광역시", "광주": "광주광역시",
    "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
}

# region 표시 순서
REGION_ORDER = ["서울", "인천", "경기", "부산", "대구", "광주", "대전", "울산", "세종",
                "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]


def parse_filename(fname):
    """
    파일명 → (region, group_label, dong_label, slug_without_ext)

    패턴:
      "서울-강남구-도곡동.html"             → ("서울", "서울 강남구", "도곡동")
      "인천-중구-신흥동3가.html"            → ("인천", "인천 중구", "신흥동3가")
      "경기-고양-덕양구-성사동.html"        → ("경기", "경기 고양시 덕양구", "성사동")
      "경기-가평-가평읍-대곡리.html"        → ("경기", "경기 가평", "가평읍 대곡리")
      "경기-과천-갈현동.html"               → ("경기", "경기 과천", "갈현동")
    """
    stem = fname[:-5] if fname.endswith(".html") else fname
    parts = stem.split("-")
    if len(parts) < 3:
        return None
    region = parts[0]

    # 1) 광역시 패턴: 3토큰 (region-gu-dong)
    if len(parts) == 3:
        return (region, f"{region} {parts[1]}", parts[2], stem)

    # 2) 4토큰 이상: 도 하위 (region-city-...-dong)
    # parts[2] 가 '구' 로 끝나면 2토큰 구 (경기 성남시 분당구)
    if parts[2].endswith("구"):
        group = f"{region} {parts[1]}시 {parts[2]}"
        dong = "-".join(parts[3:])
        return (region, group, dong, stem)

    # 3) 4토큰 이상이면서 parts[2] 가 읍/면: 군 하위
    group = f"{region} {parts[1]}"
    dong = " ".join(parts[2:])
    return (region, group, dong, stem)


def build_index():
    if not os.path.isdir(DONG_DIR):
        print(f"❌ dong 폴더 없음: {DONG_DIR}")
        return

    files = [f for f in os.listdir(DONG_DIR)
             if f.endswith(".html") and f != "index.html"]
    print(f"dong/*.html {len(files)}개 스캔")

    # region → group → list of (dong_label, slug)
    buckets = defaultdict(lambda: defaultdict(list))
    for f in files:
        parsed = parse_filename(f)
        if not parsed:
            continue
        region, group, dong, slug = parsed
        buckets[region][group].append((dong, slug))

    total_dong = sum(len(items) for regs in buckets.values() for items in regs.values())
    print(f"분류: {len(buckets)}개 지역, 총 {total_dong}개 동")

    # ── HTML 생성 ──
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    e = lambda s: html_mod.escape(str(s))

    lines = []
    lines.append('<!DOCTYPE html>')
    lines.append('<html lang="ko">')
    lines.append('<head>')
    lines.append('<meta charset="UTF-8">')
    lines.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    title = "전국 동별 아파트 시세 - 서울·인천·경기·5대 광역시 | 휙"
    desc = f"전국 {total_dong}개 동의 아파트 실거래가·시세를 동별로 확인하세요. 국토교통부 실거래가 공개시스템 기반."
    lines.append(f'<title>{e(title)}</title>')
    lines.append(f'<meta name="description" content="{e(desc)}">')
    lines.append('<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">')
    lines.append('<link rel="icon" href="/favicon.ico">')
    lines.append('<link rel="canonical" href="https://hwik.kr/dong/">')
    lines.append('<meta property="og:type" content="website">')
    lines.append('<meta property="og:site_name" content="휙">')
    lines.append('<meta property="og:locale" content="ko_KR">')
    lines.append(f'<meta property="og:title" content="{e(title)}">')
    lines.append(f'<meta property="og:description" content="{e(desc)}">')
    lines.append('<meta property="og:image" content="https://hwik.kr/og-image.png">')
    lines.append('<meta property="og:url" content="https://hwik.kr/dong/">')
    lines.append('<meta name="twitter:card" content="summary_large_image">')
    lines.append(f'<meta name="twitter:title" content="{e(title)}">')
    lines.append(f'<meta name="twitter:description" content="{e(desc)}">')
    lines.append('<meta name="google-site-verification" content="R2ye41AVVTRs8BxEXyEafFSTqMSiHKdb9zgTklrktSI">')
    lines.append('<meta name="naver-site-verification" content="367bd1e77a8ad48b74e345be3e4a0f8125c2c4e1">')
    lines.append('<script async src="https://www.googletagmanager.com/gtag/js?id=G-2DVQXMLC9J"></script>')
    lines.append("<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-2DVQXMLC9J');</script>")
    lines.append('<link rel="stylesheet" href="/danji/style.css">')
    lines.append('<style>')
    lines.append('.dong-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:8px; }')
    lines.append('.dong-item { padding:10px 12px; background:var(--card); border-radius:var(--radius); cursor:pointer; transition:all .15s; border-left:3px solid var(--yellow); text-decoration:none; color:inherit; display:block; }')
    lines.append('.dong-item:active { transform:scale(0.97); }')
    lines.append('.dong-name { font-size:13px; font-weight:500; }')
    lines.append('.group-heading { font-size:14px; font-weight:600; margin:16px 0 8px; color:var(--text); }')
    lines.append('.region-heading { font-size:16px; font-weight:700; margin:24px 0 12px; padding-bottom:6px; border-bottom:2px solid var(--yellow); }')
    lines.append('</style>')

    # 구조화 데이터 (BreadcrumbList + FAQPage + ItemList)
    # ItemList: 상위 20개 동 (서울 강남구 우선)
    il_items = []
    pos = 1
    for _r in REGION_ORDER:
        if _r not in buckets: continue
        for _g in sorted(buckets[_r].keys()):
            for _d, _s in sorted(buckets[_r][_g], key=lambda x: x[0]):
                il_items.append({"@type": "ListItem", "position": pos,
                                 "name": f"{_g} {_d}",
                                 "url": f"https://hwik.kr/dong/{url_quote(_s, safe='')}.html"})
                pos += 1
                if pos > 20: break
            if pos > 20: break
        if pos > 20: break
    schema = {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
            {"@type": "ListItem", "position": 2, "name": "동별 시세"}
        ]},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": "전국 동별 아파트 시세를 어디서 확인할 수 있나요?",
             "acceptedAnswer": {"@type": "Answer", "text": f"휙(hwik.kr/dong/)에서 서울·인천·경기·5대 광역시·지방 주요 도시 총 {total_dong}개 동의 아파트 실거래가 시세를 동별로 확인할 수 있습니다. 국토교통부 실거래가 공개시스템 데이터를 기반으로 합니다."}},
            {"@type": "Question", "name": "서울 동별 아파트 시세는 몇 개 동을 제공하나요?",
             "acceptedAnswer": {"@type": "Answer", "text": "서울은 강남구·강동구·강북구·강서구·관악구 등 25개 구, 192개 동의 아파트 시세를 제공합니다."}},
            {"@type": "Question", "name": "인천·경기 동별 아파트 시세도 볼 수 있나요?",
             "acceptedAnswer": {"@type": "Answer", "text": "네, 인천(연수구·남동구·부평구 등)과 경기도(수원·성남·고양·용인·화성 등) 전 지역의 동별 아파트 시세를 확인할 수 있습니다."}},
            {"@type": "Question", "name": "동별 아파트 시세 데이터는 얼마나 자주 업데이트되나요?",
             "acceptedAnswer": {"@type": "Answer", "text": "국토교통부 실거래가 공개시스템에서 매일 자동 동기화합니다. 최신 실거래 데이터를 반영합니다."}},
            {"@type": "Question", "name": "5대 광역시 동별 아파트 시세도 제공하나요?",
             "acceptedAnswer": {"@type": "Answer", "text": "부산·대구·광주·대전·울산 5대 광역시의 주요 동별 아파트 시세도 제공합니다."}}
        ]},
        {"@type": "ItemList", "name": f"전국 {total_dong}개 동별 아파트 시세",
         "numberOfItems": total_dong, "itemListElement": il_items}
    ]}
    lines.append(f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>')

    lines.append('</head>')
    lines.append('<body>')
    lines.append('<div class="wrap">')
    lines.append('<header class="header"><div class="header-top">')
    lines.append('  <a class="logo" href="/" style="text-decoration:none;">휙</a>')
    lines.append(f'  <div><div class="header-name">동별 아파트 시세</div><div class="header-sub">전국 {total_dong}개 동</div></div>')
    lines.append('</div></header>')
    lines.append('<nav class="breadcrumb"><a href="/">휙</a><span>&gt;</span>동별 시세</nav>')

    # 지역 순서대로 출력
    region_keys = sorted(buckets.keys(),
                         key=lambda r: REGION_ORDER.index(r) if r in REGION_ORDER else 999)

    for region in region_keys:
        groups = buckets[region]
        total_in_region = sum(len(items) for items in groups.values())
        lines.append(f'<div class="region-heading">{e(region)} · {total_in_region}개 동</div>')

        # 그룹(구/시) 정렬
        for group in sorted(groups.keys()):
            items = sorted(groups[group], key=lambda x: x[0])
            lines.append(f'<div class="group-heading">{e(group)} ({len(items)})</div>')
            lines.append('<div class="dong-grid">')
            for dong, slug in items:
                href = "/dong/" + url_quote(slug, safe="")
                lines.append(f'<a class="dong-item" href="{href}"><div class="dong-name">{e(dong)}</div></a>')
            lines.append('</div>')

    # 하단 네비
    lines.append('<div style="margin-top:40px; padding:20px; background:var(--card); border-radius:var(--radius); text-align:center;">')
    lines.append('  <a href="/gu/" style="display:inline-block; margin:0 8px; color:var(--yellow); font-weight:600; text-decoration:none;">구별 시세 →</a>')
    lines.append('  <a href="/ranking/" style="display:inline-block; margin:0 8px; color:var(--yellow); font-weight:600; text-decoration:none;">아파트 순위 →</a>')
    lines.append('</div>')
    lines.append(f'<div style="margin-top:20px; padding:12px; font-size:11px; color:var(--muted); text-align:center;">출처: 국토교통부 실거래가 공개시스템 · 마지막 갱신 {now[:10]}</div>')

    lines.append('</div></body></html>')

    out = os.path.join(DONG_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    size_kb = os.path.getsize(out) / 1024
    print(f"✅ 생성: {out} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    build_index()
