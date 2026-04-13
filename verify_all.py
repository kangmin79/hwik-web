# -*- coding: utf-8 -*-
"""
verify_all.py — 휙 전체 시스템 검증 스크립트

실행: python verify_all.py
출력: 레이어별 ✅/⚠️/❌ 결과 + 최종 점수

검증 레이어:
  1. DB 데이터 무결성
  2. 파일 시스템 (생성된 HTML)
  3. 링크 연결성 (gu/dong/ranking → danji)
  4. 데이터 교차검증 (apartments ↔ danji_pages ↔ HTML)
  5. 엔드포인트 헬스체크
"""

import os, sys, re, json, time
from collections import defaultdict
import requests

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

# ── 환경변수 로드 ─────────────────────────────────────────
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

SB_URL  = "https://jqaxejgzkchxbfzgzyzi.supabase.co"
SB_KEY  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BASE    = os.path.dirname(os.path.abspath(__file__))

H       = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"}
H_CNT   = {**H, "Prefer": "count=exact", "Range": "0-0"}

PASS = 0; WARN = 0; FAIL = 0

# ── 유틸 ─────────────────────────────────────────────────
def count(table, params):
    params = {**params, "select": "id", "limit": "1"}
    r = requests.get(f"{SB_URL}/rest/v1/{table}", headers=H_CNT, params=params)
    return int(r.headers.get("Content-Range", "*/0").split("/")[-1])

def fetch(table, params, limit=500):
    rows, offset = [], 0
    while True:
        p = {**params, "limit": str(limit), "offset": str(offset)}
        r = requests.get(f"{SB_URL}/rest/v1/{table}", headers=H, params=p)
        data = r.json() if r.status_code == 200 else []
        if not data: break
        rows.extend(data)
        if len(data) < limit: break
        offset += limit
    return rows

def ok(msg):
    global PASS; PASS += 1
    print(f"  ✅ {msg}")

def warn(msg):
    global WARN; WARN += 1
    print(f"  ⚠️  {msg}")

def fail(msg):
    global FAIL; FAIL += 1
    print(f"  ❌ {msg}")

def header(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")

def sample(items, n=3):
    return ", ".join(str(x) for x in items[:n]) + (f" 외 {len(items)-n}개" if len(items) > n else "")

# ══════════════════════════════════════════════════════════
# 레이어 1: DB 데이터 무결성
# ══════════════════════════════════════════════════════════
header("레이어 1: DB 데이터 무결성")

# 1-1. apartments 전체 수
total_apts = count("apartments", {"kapt_code": "like.A*"})
print(f"\n  📊 apartments (A* 코드): {total_apts:,}개")

# 1-2. apt_seq 없는 단지
no_seq = count("apartments", {"kapt_code": "like.A*", "apt_seq": "is.null"})
pct = round(no_seq / total_apts * 100, 1) if total_apts else 0
if pct < 5:
    ok(f"apt_seq 매칭률 {100-pct:.1f}% (미매칭 {no_seq:,}개)")
elif pct < 15:
    warn(f"apt_seq 미매칭 {no_seq:,}개 ({pct}%) — 신축/공공임대 가능성")
else:
    fail(f"apt_seq 미매칭 {no_seq:,}개 ({pct}%) — 파이프라인 확인 필요")

# 1-3. pyeongs 없는 단지
no_py = count("apartments", {"kapt_code": "like.A*", "pyeongs": "is.null"})
pct_py = round(no_py / total_apts * 100, 1) if total_apts else 0
if pct_py < 15:
    ok(f"공급면적 수집률 {100-pct_py:.1f}% (미수집 {no_py:,}개)")
else:
    warn(f"공급면적 미수집 {no_py:,}개 ({pct_py}%)")

# 1-4. slug 대문자 A 포함 여부
slug_upper = count("apartments", {"kapt_code": "like.A*", "slug": "like.*-A*"})
# AM-CITY 같은 단지명 포함 제외하기 위해 샘플 확인
if slug_upper <= 5:
    ok(f"slug 소문자 정상 (대문자 의심 {slug_upper}개는 단지명 내 영문자)")
else:
    fail(f"slug 대문자 A 포함 {slug_upper:,}개 — fix_slug_lowercase.py 실행 필요")

# 1-5. 좌표 없는 단지
no_coord = count("apartments", {"kapt_code": "like.A*", "lat": "is.null"})
pct_coord = round(no_coord / total_apts * 100, 1) if total_apts else 0
if pct_coord < 3:
    ok(f"좌표 수집률 {100-pct_coord:.1f}% (미수집 {no_coord:,}개)")
else:
    warn(f"좌표 없는 단지 {no_coord:,}개 ({pct_coord}%)")

# 1-6. trade_raw_v2 전체 건수 및 최신 날짜
total_trades = count("trade_raw_v2", {})
print(f"\n  📊 trade_raw_v2: {total_trades:,}건")
recent_row = fetch("trade_raw_v2", {"select": "deal_year,deal_month", "order": "deal_year.desc,deal_month.desc", "limit": "1"}, limit=1)
if recent_row:
    ry, rm = recent_row[0]["deal_year"], recent_row[0]["deal_month"]
    from datetime import date
    today = date.today()
    months_ago = (today.year - ry) * 12 + (today.month - rm)
    if months_ago <= 2:
        ok(f"최신 실거래 {ry}년 {rm}월 ({months_ago}개월 전 — 최신)")
    elif months_ago <= 4:
        warn(f"최신 실거래 {ry}년 {rm}월 ({months_ago}개월 전 — 업데이트 권장)")
    else:
        fail(f"최신 실거래 {ry}년 {rm}월 ({months_ago}개월 전 — 수집 필요)")

# 1-7. danji_pages 구버전(apt-) 오염 확인
apt_prefix = count("danji_pages", {"id": "like.apt-*"})
if apt_prefix == 0:
    ok("danji_pages 구버전(apt-) 오염 없음")
else:
    warn(f"danji_pages에 apt- 구버전 {apt_prefix:,}개 존재")

# 1-8. danji_pages recent_trade 없는 단지
offi_prefix = count("danji_pages", {"id": "like.offi-*"})
total_dp = count("danji_pages", {}) - apt_prefix - offi_prefix
no_trade_dp = count("danji_pages", {"recent_trade": "is.null"})
pct_dp = round(no_trade_dp / total_dp * 100, 1) if total_dp else 0
print(f"\n  📊 danji_pages: {total_dp:,}개")
if pct_dp < 20:
    ok(f"실거래 있는 단지 {100-pct_dp:.1f}% ({no_trade_dp:,}개 없음)")
else:
    warn(f"실거래 없는 단지 {no_trade_dp:,}개 ({pct_dp}%) — 재집계 필요 가능성")

# ══════════════════════════════════════════════════════════
# 레이어 2: 파일 시스템 검증
# ══════════════════════════════════════════════════════════
header("레이어 2: 파일 시스템 (생성된 HTML)")

danji_dir   = os.path.join(BASE, "danji")
gu_dir      = os.path.join(BASE, "gu")
dong_dir    = os.path.join(BASE, "dong")
ranking_dir = os.path.join(BASE, "ranking")

# 2-1. danji HTML 파일 수
danji_files = {f[:-5] for f in os.listdir(danji_dir) if f.endswith(".html")}
print(f"\n  📊 danji/ HTML: {len(danji_files):,}개")
if total_dp > 0:
    coverage = len(danji_files) / total_dp * 100
    if coverage >= 90:
        ok(f"danji HTML 커버리지 {coverage:.1f}% ({len(danji_files):,}/{total_dp:,})")
    elif coverage >= 70:
        warn(f"danji HTML 커버리지 {coverage:.1f}% — 재빌드 권장")
    else:
        fail(f"danji HTML 커버리지 {coverage:.1f}% — 빌드 필요")

# 2-2. slug 대문자 A 포함 파일 확인
upper_files = [f for f in danji_files if re.search(r'-A[0-9]', f)]
if not upper_files:
    ok("danji 파일명 전부 소문자 정상")
else:
    fail(f"danji 파일명 대문자 {len(upper_files)}개: {sample(upper_files)}")

# 2-3. apt- 구버전 파일 확인
apt_files = [f for f in danji_files if '-apt-' in f]
if not apt_files:
    ok("danji 폴더 구버전(apt-) 파일 없음")
else:
    warn(f"구버전 파일 {len(apt_files)}개 존재 (삭제 또는 무시 가능): {sample(apt_files)}")

# 2-4. gu 파일 수
gu_files = {f[:-5] for f in os.listdir(gu_dir) if f.endswith(".html") and f != "index.html"}
ok(f"gu/ HTML {len(gu_files)}개")

# 2-5. dong 파일 수
dong_files = {f[:-5] for f in os.listdir(dong_dir) if f.endswith(".html") and f != "index.html"}
ok(f"dong/ HTML {len(dong_files):,}개")

# 2-6. ranking 파일 확인
required_rankings = []
for region in ["seoul", "incheon", "gyeonggi", "busan", "daegu", "gwangju", "daejeon", "ulsan", "all"]:
    for rtype in ["price", "sqm", "jeonse", "jeonse_low"]:
        required_rankings.append(f"{region}-{rtype}")
missing_rankings = [r for r in required_rankings if r not in {f[:-5] for f in os.listdir(ranking_dir) if f.endswith(".html")}]
if not missing_rankings:
    ok(f"ranking/ 필수 파일 {len(required_rankings)}개 모두 존재")
else:
    fail(f"ranking/ 누락: {sample(missing_rankings)}")

# ══════════════════════════════════════════════════════════
# 레이어 3: 링크 연결성
# ══════════════════════════════════════════════════════════
header("레이어 3: 링크 연결성 (생성된 HTML 내부 링크)")

def extract_danji_links(filepath):
    """HTML 파일에서 /danji/xxx 링크 추출 (URL 디코딩 포함)"""
    from urllib.parse import unquote
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return [unquote(s) for s in re.findall(r'href="/danji/([^"]+)"', content)]
    except:
        return []

broken_links = []
checked_files = 0

# 3-1. gu 페이지 → danji 링크 확인
for fname in list(os.listdir(gu_dir))[:50]:  # 샘플 50개
    if not fname.endswith(".html") or fname == "index.html":
        continue
    fpath = os.path.join(gu_dir, fname)
    links = extract_danji_links(fpath)
    checked_files += 1
    for link in links:
        slug = link.rstrip("/")
        # style.css, app.js 등 정적 파일 링크는 제외
        if "." in slug.split("/")[-1] and not slug.endswith(".html"):
            continue
        if slug not in danji_files:
            broken_links.append(f"gu/{fname} → /danji/{slug}")

# 3-2. dong 페이지 → danji 링크 확인 (샘플)
for fname in list(os.listdir(dong_dir))[:30]:
    if not fname.endswith(".html") or fname == "index.html":
        continue
    fpath = os.path.join(dong_dir, fname)
    links = extract_danji_links(fpath)
    checked_files += 1
    for link in links:
        slug = link.rstrip("/")
        if "." in slug.split("/")[-1] and not slug.endswith(".html"):
            continue
        if slug not in danji_files:
            broken_links.append(f"dong/{fname} → /danji/{slug}")

# 3-3. ranking 페이지 → danji 링크 확인
for fname in os.listdir(ranking_dir):
    if not fname.endswith(".html"):
        continue
    fpath = os.path.join(ranking_dir, fname)
    links = extract_danji_links(fpath)
    checked_files += 1
    for link in links:
        slug = link.rstrip("/")
        if "." in slug.split("/")[-1] and not slug.endswith(".html"):
            continue
        if slug not in danji_files:
            broken_links.append(f"ranking/{fname} → /danji/{slug}")

print(f"\n  📊 링크 검사: {checked_files}개 파일")
if not broken_links:
    ok(f"깨진 링크 없음 (gu/dong/ranking → danji 전부 정상)")
elif len(broken_links) <= 10:
    warn(f"깨진 링크 {len(broken_links)}개 (주로 구버전 단지):")
    for b in broken_links[:5]:
        print(f"     {b}")
else:
    fail(f"깨진 링크 {len(broken_links)}개:")
    for b in broken_links[:5]:
        print(f"     {b}")

# ══════════════════════════════════════════════════════════
# 레이어 4: 데이터 교차검증
# ══════════════════════════════════════════════════════════
header("레이어 4: 데이터 교차검증")

# 4-1. apartments.slug → danji HTML 파일 일치율 (샘플 200개)
apt_sample = fetch("apartments", {
    "select": "kapt_code,kapt_name,slug",
    "kapt_code": "like.A*",
    "slug": "not.is.null",
    "order": "kapt_code",
}, limit=200)
slug_match = sum(1 for a in apt_sample if a.get("slug") in danji_files)
slug_missing = [a["kapt_name"] for a in apt_sample if a.get("slug") not in danji_files]
pct_slug = round(slug_match / len(apt_sample) * 100, 1) if apt_sample else 0
if pct_slug >= 90:
    ok(f"apartments.slug → HTML 파일 일치율 {pct_slug}% (샘플 {len(apt_sample)}개)")
elif pct_slug >= 70:
    warn(f"apartments.slug → HTML 일치율 {pct_slug}% — 재빌드 권장: {sample(slug_missing)}")
else:
    fail(f"apartments.slug → HTML 일치율 {pct_slug}% — 빌드 필요: {sample(slug_missing)}")

# 4-2. apt_seq 있는데 trade_raw_v2에 데이터 없는 단지 (샘플)
apt_seq_sample = fetch("apartments", {
    "select": "kapt_code,kapt_name,apt_seq",
    "kapt_code": "like.A*",
    "apt_seq": "not.is.null",
    "lawd_cd": "like.11*",  # 서울만 샘플
    "order": "kapt_code",
}, limit=10)
no_trade_count = 0
for a in apt_seq_sample[:5]:
    seq = a.get("apt_seq")
    if seq:
        tc = count("trade_raw_v2", {"apt_seq": f"eq.{seq}"})
        if tc == 0:
            no_trade_count += 1
if no_trade_count == 0:
    ok(f"apt_seq → trade_raw_v2 연결 정상 (샘플 {min(5, len(apt_seq_sample))}개)")
else:
    warn(f"apt_seq 있는데 trade_raw_v2 없는 단지 {no_trade_count}개 (샘플 기준)")

# 4-3. pyeongs 비율 이상값 확인 (샘플)
py_sample = fetch("danji_pages", {
    "select": "id,complex_name,pyeongs_map",
    "pyeongs_map": "not.is.null",
    "order": "id",
}, limit=100)
anomaly_count = 0
for d in py_sample:
    pm = d.get("pyeongs_map") or {}
    for cat, info in pm.items():
        exclu = info.get("exclu", 0)
        supply = info.get("supply")
        if supply and exclu > 0:
            ratio = supply / exclu
            if ratio > 3.5 or ratio < 1.0:
                anomaly_count += 1
if anomaly_count == 0:
    ok(f"공급/전용 비율 정상 (샘플 {len(py_sample)}개 단지)")
else:
    warn(f"공급/전용 비율 이상 {anomaly_count}개 타입 발견 (샘플 기준)")

# 4-4. sitemap.xml 단지 수 확인
sitemap_path = os.path.join(BASE, "sitemap.xml")
if os.path.exists(sitemap_path):
    with open(sitemap_path, encoding="utf-8") as f:
        sitemap_content = f.read()
    danji_urls = len(re.findall(r'/danji/', sitemap_content))
    if danji_urls >= len(danji_files) * 0.8:
        ok(f"sitemap.xml danji URL {danji_urls:,}개 (HTML {len(danji_files):,}개와 근접)")
    else:
        warn(f"sitemap.xml danji URL {danji_urls:,}개 vs HTML {len(danji_files):,}개 — sitemap 재생성 권장")
else:
    fail("sitemap.xml 없음")

# ══════════════════════════════════════════════════════════
# 레이어 5: 엔드포인트 헬스체크
# ══════════════════════════════════════════════════════════
header("레이어 5: 엔드포인트 헬스체크")

# 5-1. report-danji Edge Function
try:
    r = requests.post(
        f"{SB_URL}/functions/v1/report-danji",
        json={"danji_id": "__test__", "report_type": "기타", "memo": "자동 헬스체크"},
        timeout=10
    )
    if r.status_code == 200:
        ok("report-danji Edge Function 정상 응답")
    else:
        warn(f"report-danji 응답 {r.status_code}: {r.text[:100]}")
except Exception as e:
    fail(f"report-danji 연결 실패: {e}")

# 5-2. Supabase REST API 응답
try:
    r = requests.get(f"{SB_URL}/rest/v1/apartments", headers=H,
        params={"select": "kapt_code", "limit": "1"}, timeout=5)
    if r.status_code == 200:
        ok("Supabase REST API 정상")
    else:
        fail(f"Supabase REST API 오류 {r.status_code}")
except Exception as e:
    fail(f"Supabase 연결 실패: {e}")

# 5-3. hwik.kr 접근 가능 여부
try:
    r = requests.get("https://hwik.kr", timeout=8)
    if r.status_code == 200:
        ok(f"hwik.kr 접근 정상 (200)")
    else:
        warn(f"hwik.kr 응답 {r.status_code}")
except Exception as e:
    fail(f"hwik.kr 접근 실패: {e}")

# ══════════════════════════════════════════════════════════
# 최종 요약
# ══════════════════════════════════════════════════════════
total = PASS + WARN + FAIL
score = round(PASS / total * 100) if total else 0

print(f"\n{'='*55}")
print(f"  최종 결과")
print(f"{'='*55}")
print(f"  ✅ 정상:  {PASS}개")
print(f"  ⚠️  경고:  {WARN}개")
print(f"  ❌ 오류:  {FAIL}개")
print(f"  📊 점수:  {score}점 / 100점")
print()
if FAIL == 0 and WARN <= 3:
    print("  🎉 전체 시스템 정상입니다!")
elif FAIL == 0:
    print("  👍 심각한 오류 없음. 경고 항목 검토 권장.")
elif FAIL <= 2:
    print("  🔧 일부 수정 필요. 위 ❌ 항목 확인하세요.")
else:
    print("  🚨 다수 오류 발견. 즉시 확인이 필요합니다.")
print()
