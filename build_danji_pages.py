#!/usr/bin/env python3
"""
build_danji_pages.py — 단지별 정적 HTML 페이지 생성 (SEO)

Supabase danji_pages → danji/[id].html (정적 SEO 콘텐츠 + 인터랙티브 JS)
GitHub Actions에서 매일 실행, 변경분만 커밋.

Usage:
  python build_danji_pages.py
"""

import os, json, re, time, hashlib, html as html_mod
from datetime import datetime, timezone
from urllib.parse import quote as url_quote
import requests
from slug_utils import REGION_MAP, METRO_CITIES, clean as _clean, detect_region, make_danji_slug as make_slug, make_dong_slug, extract_gu_from_address, gu_url_slug

BUILD_TIME = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

def _load_env():
    for fname in (".env", "env"):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://jqaxejgzkchxbfzgzyzi.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DANJI_DIR = os.path.join(BASE_DIR, "danji")
DONG_DIR = os.path.join(BASE_DIR, "dong")
GU_DIR = os.path.join(BASE_DIR, "gu")

# 동/구 페이지 slug 목록 (빌드 시 로드 — 파일 없는 곳은 링크 생략)
DONG_SLUGS = set()
GU_SLUGS = set()  # 실제 생성된 gu 파일 목록 — 지역 라벨만 체크하면 404 발생

# apartments.slug — DB에 저장된 고정 slug (URL 안정성 보장)
APT_SLUG_MAP: dict = {}

OG_IMAGE_URL = "https://hwik.kr/og-image.png"

# /gu/ 페이지가 존재하는 지역 (전국 17개 광역시도 모두 생성)
from regions import REGION_LABEL_TO_KEY as _RLTK
GU_PAGE_REGIONS = set(_RLTK.keys())  # "서울","충남","경상북도" 등 모든 형태 포함


def _has_gu_page(address, gu_url=None):
    """해당 주소의 /gu/ 페이지가 실제로 존재하는지 확인.

    GU_SLUGS(빌드 시 로드된 실제 파일 목록)로 검증한다.
    gu_url 미지정 시 지역 라벨만 체크 (하위 호환, 빌드 초기에만 사용).
    """
    if not (detect_region(address or "") in GU_PAGE_REGIONS):
        return False
    if gu_url and GU_SLUGS:
        return gu_url in GU_SLUGS
    return True


# ── 관련 검색어 섹션 (GSC 데이터 기반 내부 링크) ───────────
# GSC(2026-04-19) 쿼리 분석 결과에 근거한 앵커 텍스트만 사용한다.
# 검증되지 않은 패턴은 링크 무덤이 되므로 추가 금지.
#
# 상위생활권 화이트리스트: 구글 autocomplete에서 "{상위} {동} 아파트 시세"
# 패턴이 실재하는 지역만 prefix를 붙인다. 나머지는 동/구 단위만 사용.
LIVING_AREA_PREFIX = {
    # (region_key, gu_or_city) → prefix
    ("gyeonggi", "성남시 분당구"): "분당",
    ("gyeonggi", "고양시 일산동구"): "일산",
    ("gyeonggi", "고양시 일산서구"): "일산",
    ("gyeonggi", "성남시 수정구"): "판교",  # 판교신도시 일부
    ("gyeonggi", "수원시 영통구"): "광교",  # 광교 일부
    ("gyeonggi", "용인시 수지구"): "수지",
    ("gyeonggi", "화성시"): "동탄",         # 동탄신도시 (화성시 포함)
    ("gyeonggi", "하남시"): "미사",         # 미사지구 (하남시 일부)
    ("gyeonggi", "시흥시"): "배곧",         # 배곧신도시 일부
    ("incheon", "연수구"): "송도",          # 송도국제도시
    ("seoul",   "강서구"): "마곡",          # 마곡지구 일부
}


def _is_upper_living_area(region_key, gu_raw):
    """해당 단지가 상위생활권 prefix 대상인지."""
    if not region_key or not gu_raw:
        return None
    key = (region_key, gu_raw)
    return LIVING_AREA_PREFIX.get(key)


def _page_seed(danji_id):
    """단지 ID 기반 결정적 시드 (빌드 재현성 보장)."""
    h = hashlib.md5((danji_id or "").encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _weighted_ranking_pick(danji_id, jeonse_rate, price_delta_ratio):
    """3종 랭킹 중 단지 성격에 맞는 1개 선택 (결정적 가중치 랜덤).

    규칙:
      - 전세가율 ≥ 75% → 전세:매매:㎡당 = 60:20:20
      - 1년 가격 변동 절대값 ≥ 10% → 매매:전세:㎡당 = 60:20:20
      - 기본 → 매매:전세:㎡당 = 34:33:33
    """
    if jeonse_rate is not None and jeonse_rate >= 75:
        weights = [("jeonse", 60), ("price", 20), ("sqm", 20)]
    elif price_delta_ratio is not None and abs(price_delta_ratio) >= 10:
        weights = [("price", 60), ("jeonse", 20), ("sqm", 20)]
    else:
        weights = [("price", 34), ("jeonse", 33), ("sqm", 33)]
    seed = _page_seed(danji_id)
    total = sum(w for _, w in weights)
    pick = seed % total
    acc = 0
    for key, w in weights:
        acc += w
        if pick < acc:
            return key
    return weights[-1][0]


_R_LABEL_MAP = {"seoul":"서울","incheon":"인천","gyeonggi":"경기","busan":"부산","daegu":"대구","gwangju":"광주","daejeon":"대전","ulsan":"울산","sejong":"세종","chungbuk":"충북","chungnam":"충남","jeonbuk":"전북","jeonnam":"전남","gyeongbuk":"경북","gyeongnam":"경남","gangwon":"강원","jeju":"제주"}


def build_related_anchors(d, rt, jr, bc, year_ago):
    """관련 검색어 섹션의 앵커 리스트 생성 — HTML과 JSON-LD에서 공유.

    반환: [(href, text), ...]
    GSC 쿼리 데이터(2026-04-19)에 근거한 패턴만 사용한다.
    """
    did = d.get("id", "")
    loc_parts_raw = (d.get("location") or "").split(" ", 1)
    dong_name = loc_parts_raw[1] if len(loc_parts_raw) >= 2 else ""
    gu_raw = extract_gu_from_address(d.get("address", "")) or (loc_parts_raw[0] if loc_parts_raw else "")
    gu_esc = esc(gu_raw)
    dong_slug_str = make_dong_slug(gu_raw, dong_name, d.get("address", "")) if dong_name else ""
    region_label = detect_region(d.get("address", "") or "")
    gu_url = gu_url_slug(region_label, gu_raw)
    region_key = _RLTK.get(region_label) if region_label else None
    r_label = _R_LABEL_MAP.get(region_key, region_key) if region_key else ""
    living_prefix = _is_upper_living_area(region_key, gu_raw)

    # 가중치 계산
    delta_ratio = None
    if year_ago and bc and rt.get(bc):
        cur_p_w = rt[bc].get("price", 0)
        old_p_w = year_ago.get("price", 0)
        if cur_p_w and old_p_w:
            delta_ratio = (cur_p_w - old_p_w) / old_p_w * 100
    jr_num = None
    try:
        jr_num = float(jr) if jr else None
    except (ValueError, TypeError):
        pass
    ranking_pri = _weighted_ranking_pick(did, jr_num, delta_ratio)
    ranking_alt_order = {"price": "jeonse", "jeonse": "sqm", "sqm": "price"}
    ranking_sec = ranking_alt_order[ranking_pri]
    seed = _page_seed(did)

    anchors = []
    if dong_name and dong_slug_str and dong_slug_str in DONG_SLUGS:
        dong_href = f'/dong/{url_quote(dong_slug_str, safe="-")}.html'
        if living_prefix and (seed % 3 != 0):
            dong_text = f"{living_prefix} {esc(dong_name)} 아파트 시세"
        elif seed % 2 == 0:
            dong_text = f"{esc(dong_name)} 아파트 시세"
        else:
            dong_text = f"{esc(dong_name)} 아파트"
        anchors.append((dong_href, dong_text))
    if _has_gu_page(d.get("address", ""), gu_url):
        gu_href = f'/gu/{url_quote(gu_url, safe="-")}.html'
        gu_text = f"{gu_esc} 아파트 시세" if (seed % 2 == 0) else f"{gu_esc} 집값"
        anchors.append((gu_href, gu_text))
    if region_key:
        rank_labels = {
            "price":  f"{r_label} 아파트 매매가 순위",
            "jeonse": f"{r_label} 전세 시세 순위",
            "sqm":    f"{r_label} 평당 가격 순위",
        }
        anchors.append((f"/ranking/{region_key}-{ranking_pri}.html", rank_labels[ranking_pri]))
        anchors.append((f"/ranking/{region_key}-{ranking_sec}.html", rank_labels[ranking_sec]))
    return anchors


# ── 유틸 ──────────────────────────────────────────────────
def esc(s):
    return html_mod.escape(str(s)) if s else ""


# REGION_MAP, METRO_CITIES, _clean, detect_region, make_slug → slug_utils.py에서 import

def format_price(manwon):
    if not manwon:
        return "-"
    try:
        manwon = int(manwon)
    except (ValueError, TypeError):
        return "-"
    if manwon <= 0:
        return "-"
    uk = manwon // 10000
    rest = manwon % 10000
    if uk > 0 and rest > 0:
        cheon = rest // 1000
        return f"{uk}억 {cheon}천" if cheon > 0 else f"{uk}억 {rest}"
    if uk > 0:
        return f"{uk}억"
    return f"{manwon:,}만"

def walk_min(m):
    if not m:
        return ""
    try:
        return f"{round(float(m) / 67)}분"
    except (ValueError, TypeError):
        return ""


def clean_line(line):
    """지하철 노선명 정리: '수도권 경량도시철도 신림선' → '신림선'"""
    if not line:
        return ""
    s = re.sub(r'\s+', ' ', str(line)).strip()
    # 접두어 제거: 수도권/서울/부산/대구/대전/광주/인천 + 도시철도/경량도시철도/광역철도
    s = re.sub(r'^(수도권|서울|부산|대구|대전|광주|인천)?\s*(경량)?도시철도\s*', '', s).strip()
    s = re.sub(r'^수도권\s*광역철도\s*', '', s).strip()
    # 특수 케이스
    s = s.replace('인천국제공항선', '공항철도')
    s = s.replace('부산김해경전철', '김해경전철')
    return s or str(line).strip()


def josa(word, particle_pair="은/는"):
    """한글 받침 유무에 따라 올바른 조사 반환. 예: josa("아파트","은/는") → "는" """
    a, b = particle_pair.split("/")
    if not word:
        return b
    last = word.rstrip()[-1]
    if '가' <= last <= '힣':
        return a if (ord(last) - 0xAC00) % 28 != 0 else b
    return b  # 숫자·영문 등은 받침 없음 취급


# ── Supabase 조회 ─────────────────────────────────────────
PAGE_LIMIT = 200


def _get_page(url, params, max_attempts=3):
    """Supabase GET + JSON 파싱 + 재시도(2s,4s,6s). 최종 실패 시 raise."""
    last_err = None
    for attempt in range(max_attempts):
        try:
            resp = requests.get(
                url,
                headers={**SB_HEADERS, "Prefer": ""},
                params=params,
                timeout=60,
            )
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            else:
                return resp.json()
        except (requests.exceptions.JSONDecodeError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < max_attempts - 1:
            wait = 2 * (attempt + 1)
            print(f"  ⚠️ Supabase 재시도 {attempt+1}/{max_attempts} ({wait}s 대기): {last_err}")
            time.sleep(wait)
    raise RuntimeError(f"Supabase fetch 실패 (params={params}): {last_err}")


def fetch_all_danji():
    all_data = []
    offset = 0
    while True:
        raw = _get_page(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            {
                "select": "id,complex_name,location,address,build_year,total_units,"
                          "categories,recent_trade,all_time_high,jeonse_rate,"
                          "price_history,"
                          "nearby_subway,nearby_school,nearby_complex,"
                          "lat,lng,top_floor,parking,heating,builder,updated_at",
                "id": "not.like.offi-*",
                "order": "id",
                "offset": offset,
                "limit": PAGE_LIMIT,
            },
        )
        if not raw:
            break
        # apt- 구버전 단지 제외
        data = [d for d in raw if not d.get("id", "").startswith("apt-")]
        all_data.extend(data)
        offset += PAGE_LIMIT
        if len(raw) < PAGE_LIMIT:
            break
        time.sleep(0.2)
    return all_data


# ── extract_css_js() 삭제됨 (2026-04-12) ──────────────────
# danji.html 에서 <style>/<script> 를 뽑아 danji/style.css, danji/app.js 에
# 쓰던 로직. danji.html 이 레거시 리다이렉트 셸로 축소된 뒤 2일 연속
# (사고 42e191ed77 / Day1 app.js, Day2 style.css) 빈 껍데기로 13,000개
# 단지 페이지를 덮어쓰는 회귀가 발생해 통째로 제거. danji/app.js 와
# danji/style.css 는 수동 관리 파일이며 빌드가 절대 만지지 않는다.
# 복원 금지. 복원이 필요해 보이면 먼저 이 주석과
# memory/feedback_long_session_regressions.md 를 읽을 것.
# git log --all -S "extract_css_js" 로 이전 구현 추적 가능.


# ── 단지별 SEO 콘텐츠 생성 ────────────────────────────────
def safe_int(s, default=999):
    try:
        return int(s)
    except (ValueError, TypeError):
        return default


def best_price_cat(d):
    """84㎡에 가장 가까운 거래 있는 면적 반환"""
    cats = d.get("categories") or []
    rt = d.get("recent_trade") or {}
    best, best_diff = None, 999
    for c in cats:
        if rt.get(c) and (rt[c].get("price") or 0) > 0:
            diff = abs(safe_int(c) - 84)
            if diff < best_diff:
                best_diff = diff
                best = c
    return best


def find_year_ago_trade(d, cat):
    """price_history에서 1년 전 ±2개월 범위의 거래를 찾아 반환"""
    ph = d.get("price_history") or {}
    trades = ph.get(cat) or []
    if not trades:
        return None
    rt = (d.get("recent_trade") or {}).get(cat) or {}
    recent_date = rt.get("date", "")
    if not recent_date or len(recent_date) < 10:
        return None
    try:
        ry, rm = int(recent_date[:4]), int(recent_date[5:7])
        target_y = ry - 1
        # 1년 전 ±2개월 범위
        best = None
        best_diff = 999
        for t in trades:
            td = t.get("date", "")
            if not td or len(td) < 7:
                continue
            ty, tm = int(td[:4]), int(td[5:7])
            if ty == target_y:
                diff = abs(tm - rm)
                if diff <= 2 and diff < best_diff:
                    best_diff = diff
                    best = t
        return best
    except (ValueError, IndexError):
        return None


# kapt_code(소문자) → complex_type 맵 (빌드 시 로드)
COMPLEX_TYPE_MAP: dict = {}


def fetch_complex_type_map():
    """apartments 테이블에서 kapt_code → complex_type 맵 로드.
    danji_pages 뷰에 complex_type이 없어서 별도 조회.
    """
    result = {}
    offset = 0
    BATCH = 500
    while True:
        batch = _get_page(
            f"{SUPABASE_URL}/rest/v1/apartments",
            {"select": "kapt_code,complex_type", "limit": BATCH, "offset": offset},
        )
        if not isinstance(batch, list) or not batch:
            break
        for row in batch:
            code = (row.get("kapt_code") or "").lower()
            ctype = row.get("complex_type")
            if code and ctype:
                result[code] = ctype
        offset += BATCH
        if len(batch) < BATCH:
            break
    return result


def get_prop_type(did):
    """건물 유형 반환. COMPLEX_TYPE_MAP 로드 후에는 실제 유형 반환.
    미로드 시(빌드 초기)에는 '아파트'로 fallback — 안전.
    """
    if did.startswith("offi-"):
        return "오피스텔"
    ctype = COMPLEX_TYPE_MAP.get(did.lower(), "")
    if ctype in ("주상복합", "도시형 생활주택(주상복합)"):
        return "주상복합"
    if ctype == "도시형 생활주택(아파트)":
        return "도시형 생활주택"
    return "아파트"


def get_complex_type_tag(did):
    """주상복합·도시형 생활주택에만 태그 HTML 반환. 일반 아파트는 빈 문자열."""
    ctype = COMPLEX_TYPE_MAP.get(did.lower(), "")
    if not ctype or ctype == "아파트":
        return ""
    # 표시 텍스트 정리
    label = ctype.replace("도시형 생활주택(주상복합)", "도시형·주상복합") \
                 .replace("도시형 생활주택(아파트)", "도시형 생활주택")
    return (
        f'<span style="display:inline-block;background:#ede9fe;color:#5b21b6;'
        f'font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;'
        f'margin-left:6px;vertical-align:middle;">{label}</span>'
    )


def _pt_ro(pt):
    """'아파트로' / '주상복합으로' — 받침 유무에 따라 로/으로 결정."""
    last = pt.rstrip()[-1]
    code = ord(last) - 0xAC00
    batchim = code % 28
    return pt + ("으로" if batchim not in (0, 8) else "로")  # ㄹ받침(8)도 '로'


def build_intro_sentence(name, addr, year, units, builder, bc, rt, jr, prop_type="아파트"):
    """데이터 특성에 따라 다른 서두 문장 생성 — 콘텐츠 다양화"""
    from datetime import datetime as _dt
    current_year = _dt.now().year
    age = current_year - year if year else None
    unit_count = units if isinstance(units, int) else 0
    price = safe_int(rt[bc].get("price"), 0) if bc and rt.get(bc) else 0

    pt = prop_type
    pt_ro = _pt_ro(pt)  # 받침 고려한 '로/으로'
    # 신축 대단지
    if age is not None and age <= 5 and unit_count >= 1000:
        return f"{name}{josa(name,'은/는')} {year}년 준공된 {unit_count:,}세대 규모의 신축 대단지로, {addr}에 있습니다."
    # 신축
    if age is not None and age <= 5:
        return f"{addr}에 위치한 {name}{josa(name,'은/는')} {year}년 준공된 신축 {pt}입니다."
    # 대단지
    if unit_count >= 1000 and year:
        return f"{name}{josa(name,'은/는')} {addr}의 {unit_count:,}세대 대단지 {pt_ro}, {year}년에 준공되었습니다."
    if unit_count >= 1000:
        return f"{name}{josa(name,'은/는')} {addr}의 {unit_count:,}세대 대단지 {pt}입니다."
    # 전세 수요 높음
    try:
        jr_float = float(jr) if jr else 0
    except (ValueError, TypeError):
        jr_float = 0
    if jr_float >= 70:
        return f"{name}{josa(name,'은/는')} 전세가율 {jr}%로 전세가율이 높은 {addr} 소재 {pt}입니다."
    # 고가
    if price >= 150000:
        return f"{addr}의 {name}{josa(name,'은/는')} 최근 전용 {bc}㎡가 {format_price(price)}에 거래된 {pt}입니다."
    # 유명 시공사
    major = ["삼성물산", "현대건설", "대우건설", "GS건설", "포스코건설", "대림산업", "롯데건설", "HDC현대산업개발"]
    if builder and any(b in builder for b in major):
        if year:
            return f"{name}{josa(name,'은/는')} {builder} 시공의 {pt_ro}, {addr}에 위치하며 {year}년 준공되었습니다."
        return f"{name}{josa(name,'은/는')} {builder} 시공의 {pt_ro}, {addr}에 위치합니다."
    # 구축
    if age is not None and age >= 30:
        return f"{year}년 준공된 {name}{josa(name,'은/는')} {addr}에 위치한 {pt}입니다."
    # 소형
    if 0 < unit_count < 300:
        return f"{addr} 소재 {name}{josa(name,'은/는')} 총 {unit_count:,}세대 규모의 {pt}입니다."
    # 기본
    if year and addr:
        return f"{name}{josa(name,'은/는')} {addr}에 있는 {year}년 준공 {pt}입니다."
    elif addr:
        return f"{name}{josa(name,'은/는')} {addr}에 위치한 {pt}입니다."
    return f"{name} {pt}입니다."


def build_fallback_html(d):
    """Googlebot이 읽는 정적 SEO 콘텐츠"""
    did = d.get("id", "")
    prop_type = get_prop_type(did)
    name = esc(d.get("complex_name", ""))
    loc = esc(d.get("location", ""))
    loc_parts = (d.get("location") or "").split(" ")
    # gu: address 우선 (경기 "수원시 장안구" 2토큰 정확히 인식), 실패 시 location fallback
    gu_raw = extract_gu_from_address(d.get("address", "")) or (loc_parts[0] if loc_parts else "")
    gu = esc(gu_raw)
    addr = esc(d.get("address", ""))
    year = d.get("build_year", "")
    units = d.get("total_units", "")
    builder = esc(d.get("builder", ""))

    cats = d.get("categories") or []
    rt = d.get("recent_trade") or {}
    high = d.get("all_time_high") or {}
    jr = d.get("jeonse_rate")

    bc = best_price_cat(d)
    lines = []

    # H2: 실거래가 섹션 (SEO — 구글봇이 콘텐츠 구조 파악)
    ctype_tag = get_complex_type_tag(did)
    lines.append(f'<h2 style="font-size:16px;font-weight:700;margin-bottom:8px;">{name} 실거래가 시세{ctype_tag}</h2>')

    # 기본 정보
    info = f"{loc}"
    if units:
        info += f" · {units:,}세대" if isinstance(units, int) else f" · {units}세대"
    if year:
        info += f" · {year}년"
    if builder:
        info += f" · {builder}"
    lines.append(f'<p style="font-size:13px;color:#6b7280;margin-bottom:16px;">{info}</p>')

    # 시세 (직거래/중개거래 뱃지 포함)
    def _kind_badge(kind):
        if kind not in ("직거래", "중개거래"):
            return ""
        is_direct = (kind == "직거래")
        bg = "#fef3c7" if is_direct else "#dbeafe"
        fg = "#92400e" if is_direct else "#1e40af"
        return (f'<span style="display:inline-block;background:{bg};color:{fg};'
                f'font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;'
                f'margin-left:6px;vertical-align:middle;">{kind}</span>')

    if bc and rt.get(bc):
        r = rt[bc]
        txt = f"전용 {bc}㎡ 최근 매매가: {format_price(r.get('price'))}"
        if r.get("date"):
            txt += f" ({r['date']})"
        lines.append(f'<p style="font-size:15px;font-weight:600;margin-bottom:6px;">{txt}{_kind_badge(r.get("kind",""))}</p>')
    if bc and high.get(bc):
        h = high[bc]
        txt = f"최근 5년 최고가: {format_price(h.get('price'))}"
        if h.get("date"):
            txt += f" ({h['date']})"
        lines.append(f'<p style="font-size:13px;color:#6b7280;margin-bottom:6px;">{txt}{_kind_badge(h.get("kind",""))}</p>')
    if jr:
        lines.append(f'<p style="font-size:13px;color:#6b7280;margin-bottom:6px;">전세가율: {jr}%</p>')

    # 시계열 비교 (1년 전 거래와 비교) — 어느 한쪽이 직거래면 왜곡 가능성이 커 비교 생략
    year_ago = find_year_ago_trade(d, bc) if bc else None
    _cur_kind = (rt.get(bc, {}) or {}).get("kind") if bc else ""
    _old_kind = (year_ago or {}).get("kind") if year_ago else ""
    if year_ago and bc and rt.get(bc) and _cur_kind != "직거래" and _old_kind != "직거래":
        cur_price = rt[bc].get("price", 0)
        old_price = year_ago.get("price", 0)
        if cur_price and old_price and cur_price != old_price:
            diff = cur_price - old_price
            direction = "상승" if diff > 0 else "하락"
            lines.append(
                f'<div style="margin:12px 0;padding:12px;background:#f0f9ff;border-radius:8px;font-size:13px;line-height:1.7;">'
                f'<strong>1년 전 비교</strong><br>'
                f'전용 {bc}㎡ 1년 전 거래가: {format_price(old_price)} ({year_ago.get("date","")})<br>'
                f'현재 거래가: {format_price(cur_price)} ({rt[bc].get("date","")})<br>'
                f'<span style="color:{"#dc2626" if diff > 0 else "#2563eb"};font-weight:600;">'
                f'{format_price(abs(diff))} {direction}</span>'
                f'</div>'
            )

    # 거래 활발도 (최근 1년간 거래 건수)
    from datetime import date as _date, timedelta as _td
    one_year_ago_str = (_date.today() - _td(days=365)).strftime("%Y-%m")
    ph = d.get("price_history") or {}
    total_recent_trades = 0
    for _ck, _tlist in ph.items():
        if not isinstance(_tlist, list):
            continue
        for _t in _tlist:
            _td2 = _t.get("date", "")
            if _td2 and _td2[:7] >= one_year_ago_str:
                total_recent_trades += 1
    if total_recent_trades >= 2:
        lines.append(f'<p style="font-size:12px;color:#6b7280;margin-bottom:12px;">최근 1년간 {total_recent_trades}건 거래</p>')

    # 면적 목록
    if cats:
        area_list = ", ".join(f"전용 {c}㎡" for c in cats)
        lines.append(f'<p style="font-size:12px;color:#6b7280;margin-bottom:12px;">면적: {area_list}</p>')

    # 면적별 가격 비교 (2개 이상 면적에 거래가 있을 때)
    traded_areas = [(c, rt[c]) for c in sorted(cats, key=lambda x: int(x) if isinstance(x, str) and x.isdigit() else 999) if rt.get(c) and (rt[c].get("price") or 0) > 0]
    if len(traded_areas) >= 2:
        ap = ", ".join(f"전용 {a}㎡ {format_price(t.get('price'))}" for a, t in traded_areas)
        lines.append(
            f'<div style="margin:12px 0;padding:12px;background:#fefce8;border-radius:8px;font-size:13px;line-height:1.7;">'
            f'<strong>면적별 거래가</strong><br>{ap}</div>'
        )

    # 지하철
    subway = d.get("nearby_subway") or []
    if subway:
        items = [f"{esc(s.get('name',''))}({esc(clean_line(s.get('line','')))}) 도보 {walk_min(s.get('distance'))}" for s in subway[:3]]
        lines.append(f'<p style="font-size:12px;color:#6b7280;margin-bottom:4px;">인근 지하철: {", ".join(items)}</p>')

    # 학교
    school = d.get("nearby_school") or []
    if school:
        items = [f"{esc(s.get('name',''))} 도보 {walk_min(s.get('distance'))}" for s in school[:2]]
        lines.append(f'<p style="font-size:12px;color:#6b7280;margin-bottom:12px;">인근 학교: {", ".join(items)}</p>')

    # 단지 스펙
    specs = []
    if d.get("top_floor"):
        specs.append(f"최고 {d['top_floor']}층")
    pk = safe_int(d.get("parking"), 0)
    if pk > 0:
        specs.append(f"주차 {pk:,}대")
    if d.get("heating"):
        specs.append(esc(d["heating"]))
    if specs:
        lines.append(f'<p style="font-size:12px;color:#6b7280;margin-bottom:12px;">{", ".join(specs)}</p>')

    nearby = d.get("nearby_complex") or []
    # 주변 단지 대비 순위
    if nearby and len(nearby) >= 3 and bc and rt.get(bc):
        my_price = rt[bc].get("price", 0)
        if my_price > 0:
            all_prices = [my_price]
            for n in nearby:
                np = n.get("prices") or {}
                for k, v in np.items():
                    if abs(safe_int(k) - safe_int(bc)) <= 10 and v.get("price"):
                        all_prices.append(v["price"])
                        break
            all_prices_sorted = sorted(set(all_prices), reverse=True)
            rank = all_prices_sorted.index(my_price) + 1 if my_price in all_prices_sorted else 0
            total = len(all_prices_sorted)
            if rank > 0 and total >= 3:
                lines.append(
                    f'<p style="font-size:12px;color:#6b7280;margin-bottom:8px;">'
                    f'주변 {total}개 단지 중 거래가 <strong>{rank}위</strong></p>'
                )
    # 주변 단지
    if nearby:
        lines.append('<h2 style="font-size:14px;font-weight:600;margin:16px 0 8px;">주변 단지</h2>')
        lines.append('<ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:6px;">')
        shown = 0
        for n in nearby:
            if shown >= 5:
                break
            nid = n.get("id", "")
            if nid not in DANJI_SLUG_MAP:
                continue  # 페이지 미생성 단지 스킵
            prices = n.get("prices") or {}
            nbest = None
            ndiff = 999
            for k, v in prices.items():
                diff = abs(safe_int(k) - 84)
                if diff < ndiff:
                    ndiff = diff
                    nbest = v
            p = format_price(nbest.get("price")) if nbest and nbest.get("price") else "-"
            nname_raw = n.get("name", "")
            nloc_raw = n.get("location", "")
            nslug = DANJI_SLUG_MAP[nid]
            nname = esc(nname_raw)
            nloc = esc(nloc_raw)
            shown += 1
            lines.append(
                f'<li><a href="/danji/{url_quote(nslug, safe="-")}.html" style="display:flex;justify-content:space-between;'
                f'padding:10px 12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">'
                f'<span>{nname} <span style="color:#6b7280;font-size:11px;">{nloc}</span></span>'
                f'<span style="font-weight:600;">{p}</span></a></li>'
            )
        lines.append("</ul>")

    # 요약 문단 (FAQ 위 — 구글 스니펫 + 본문 텍스트 신호)
    _intro = build_intro_sentence(
        d.get("complex_name", ""), d.get("address", ""),
        year, units, d.get("builder", ""),
        bc, rt, jr, get_prop_type(did)
    )
    if _intro:
        lines.append(
            f'<p style="font-size:12px;color:#6b7280;line-height:1.8;margin:16px 0 12px;">'
            f'{esc(_intro)}</p>'
        )

    # FAQ
    faq = []
    if bc and rt.get(bc):
        r = rt[bc]
        a = f"최근 매매 실거래가는 {format_price(r.get('price'))}입니다."
        if r.get("date"):
            a += f" ({r['date']} 기준)"
        faq.append((f"{name} 최근 실거래가는?", a))
    if jr:
        faq.append((f"{name} 전세가율은?", f"{name}의 전세가율은 {jr}%입니다."))
    if bc and high.get(bc):
        h = high[bc]
        a = f"최근 5년 최고가는 {format_price(h.get('price'))}입니다."
        if h.get("date"):
            a += f" ({h['date']})"
        faq.append((f"{name} 최근 5년 최고가는?", a))
    if subway:
        a = ", ".join(f"{esc(s.get('name',''))}({esc(clean_line(s.get('line','')))}) 도보 {walk_min(s.get('distance'))}" for s in subway[:3])
        faq.append((f"{name} 근처 지하철역은?", a))
    # 확장 FAQ
    if year_ago and bc and rt.get(bc):
        cur_p = rt[bc].get("price", 0)
        old_p = year_ago.get("price", 0)
        if cur_p and old_p and cur_p != old_p:
            diff = cur_p - old_p
            direction = "상승" if diff > 0 else "하락"
            faq.append((f"{name} 1년 전 가격은?",
                f"전용 {bc}㎡ 기준 1년 전 거래가는 {format_price(old_p)}({year_ago.get('date','')})이었으며, "
                f"현재 {format_price(cur_p)}으로 {format_price(abs(diff))} {direction}했습니다."))
    if school:
        items = ", ".join(f"{esc(s.get('name',''))} 도보 {walk_min(s.get('distance'))}" for s in school[:3])
        faq.append((f"{name} 주변 학교는?", items))
    if units and year:
        u = f"{units:,}" if isinstance(units, int) else str(units)
        a = f"{name}{josa(name,'은/는')} {year}년 준공, 총 {u}세대 규모입니다."
        if builder:
            a += f" 시공사는 {builder}입니다."
        faq.append((f"{name} 몇 세대인가요?", a))
    # 거래 활발도 FAQ
    if total_recent_trades >= 2:
        faq.append((f"{name} 거래가 활발한가요?", f"최근 1년간 {total_recent_trades}건의 매매 거래가 있었습니다."))
    # 면적별 가격 FAQ
    if len(traded_areas) >= 2:
        parts = [f"전용 {a}㎡ {format_price(t.get('price'))}" for a, t in traded_areas]
        faq.append((f"{name} 면적별 가격은?", ", ".join(parts) + " (최근 거래가 기준)"))

    # ── 신규 FAQ (2026-04-19): 5년 최저가 / 주력 평형 / 주차 대수 ──
    # price_history 키: "85"=매매, "85_jeonse"=전세, "85_wolse"=월세
    # 매매만 사용 (혼재 시 월세 보증금이 최저가로 잡혀 오류)
    _pha = d.get("price_history") or {}
    _min_trade = None  # {"price", "date", "cat"}
    _cat_counts = {}   # {cat: 거래수} — 매매만
    for _cat_k, _trades in _pha.items():
        if not isinstance(_trades, list):
            continue
        if "_" in str(_cat_k):  # 전세/월세 제외
            continue
        _cat_counts[_cat_k] = _cat_counts.get(_cat_k, 0) + len(_trades)
        for _tr in _trades:
            _pr = _tr.get("price")
            if not _pr:
                continue
            if _min_trade is None or _pr < _min_trade["price"]:
                _min_trade = {"price": _pr, "date": _tr.get("date", ""), "cat": _cat_k}
    # 5년 최저가 FAQ (최고가와 다를 때만)
    _min_faq_added = False
    if _min_trade and bc and high.get(bc):
        _high_p = high[bc].get("price", 0)
        if _min_trade["price"] and _high_p and _min_trade["price"] < _high_p:
            _min_a = f"최근 5년 최저가는 {format_price(_min_trade['price'])}입니다."
            if _min_trade.get("date"):
                _min_a += f" ({_min_trade['date']}, 전용 {_min_trade['cat']}㎡)"
            faq.append((f"{name} 최근 5년 최저가는?", _min_a))
            _min_faq_added = True
    # 주력 평형 FAQ (2개 이상 평형 거래, 5건 이상일 때)
    _main_cat = None
    _main_share = 0
    _total_cat_trades = sum(_cat_counts.values())
    if _cat_counts and _total_cat_trades >= 5:
        _main_cat, _main_cnt = max(_cat_counts.items(), key=lambda x: x[1])
        _main_share = round(_main_cnt / _total_cat_trades * 100)
        if len(_cat_counts) >= 2 and _main_share >= 30:
            faq.append((
                f"{name} 주력 평형은?",
                f"거래가 가장 많은 평형은 전용 {_main_cat}㎡로, 최근 거래의 약 {_main_share}%를 차지합니다.",
            ))
    # 주차 대수 FAQ (세대당 0.3대 이상일 때만 — 품질 필터)
    _pk_n = safe_int(d.get("parking"), 0)
    _units_n = units if isinstance(units, int) else 0
    if _pk_n > 0 and _units_n > 0:
        _per_unit = _pk_n / _units_n
        if _per_unit >= 0.3:
            faq.append((
                f"{name} 주차 대수는?",
                f"총 주차 {_pk_n:,}대로 세대당 약 {_per_unit:.2f}대 수준입니다.",
            ))

    if faq:
        lines.append('<h2 style="font-size:14px;font-weight:600;margin:16px 0 8px;">자주 묻는 질문</h2>')
        for q, a in faq:
            lines.append(f'<div style="border-bottom:1px solid #e5e7eb;padding:10px 0;">')
            lines.append(f'<div style="font-size:13px;font-weight:500;margin-bottom:4px;">{q}</div>')
            lines.append(f'<div style="font-size:12px;color:#6b7280;line-height:1.6;">{a}</div>')
            lines.append("</div>")

    # SEO 서술형 텍스트 (풍부한 고유 콘텐츠)
    seo = []
    # 원본 값으로 호출 (esc()는 seo_text 전체에서 적용)
    raw_name = d.get("complex_name", "")
    raw_addr = d.get("address", "")
    raw_builder = d.get("builder", "")
    intro = build_intro_sentence(raw_name, raw_addr, year, units, raw_builder, bc, rt, jr, prop_type)
    seo.append(intro)
    if len(traded_areas) >= 2:
        parts = [f"전용 {a}㎡ {format_price(t.get('price'))}" for a, t in traded_areas[:4]]
        seo.append(f"면적별 최근 거래가는 {', '.join(parts)}입니다.")
    if bc and rt.get(bc):
        r = rt[bc]
        date_str = f" ({r['date']})" if r.get("date") else ""
        seo.append(f"전용 {bc}㎡ 최근 매매 실거래가는 {format_price(r.get('price'))}{date_str}입니다.")
    if bc and high.get(bc):
        h = high[bc]
        h_date = f" ({h['date']})" if h.get("date") else ""
        seo.append(f"전용 {bc}㎡ 최근 5년 최고가는 {format_price(h.get('price'))}{h_date}입니다.")
    if jr:
        seo.append(f"전세가율은 {jr}%입니다.")
    if year_ago and bc and rt.get(bc):
        cur_p = rt[bc].get("price", 0)
        old_p = year_ago.get("price", 0)
        if cur_p and old_p and cur_p != old_p:
            diff = cur_p - old_p
            direction = "상승" if diff > 0 else "하락"
            seo.append(f"1년 전 같은 면적 거래가 대비 {format_price(abs(diff))} {direction}했습니다.")
    if subway:
        names = ", ".join(f"{s.get('name','')}({clean_line(s.get('line',''))})" for s in subway[:2])
        seo.append(f"인근 지하철역은 {names}입니다.")
    if school:
        names = ", ".join(s.get("name", "") for s in school[:2])
        last_name = school[min(1, len(school)-1)].get("name", "")
        seo.append(f"인근 학교로 {names}{josa(last_name, '이/가')} 있습니다.")
    if total_recent_trades >= 2:
        seo.append(f"최근 1년간 {total_recent_trades}건의 매매 거래가 있었습니다.")
    # 신규 서술형 (2026-04-19): 5년 최저가 변동폭
    if _min_faq_added and bc and high.get(bc):
        _high_p_seo = high[bc].get("price", 0)
        _min_p_seo = _min_trade["price"]
        if _min_p_seo and _high_p_seo and _high_p_seo > _min_p_seo:
            _swing = _high_p_seo - _min_p_seo
            seo.append(f"최근 5년간 최저 {format_price(_min_p_seo)}에서 최고 {format_price(_high_p_seo)}까지 {format_price(_swing)} 범위에서 거래되었습니다.")
    # 신규 서술형: 주력 평형 점유율
    if _main_cat and _main_share >= 30 and len(_cat_counts) >= 2:
        seo.append(f"거래가 가장 많은 평형은 전용 {_main_cat}㎡이며, 최근 거래 중 약 {_main_share}%를 차지합니다.")
    _today = datetime.now().strftime('%Y-%m-%d')
    seo.append(f"모든 데이터는 국토교통부 실거래가 공개시스템 기반입니다. 최종 데이터 확인: {_today}.")
    seo_text = " ".join(s for s in seo if s)
    if seo_text:
        lines.append(f'<h2 style="font-size:13px;font-weight:600;margin-top:20px;margin-bottom:6px;color:#374151;">{name} 단지 정보</h2>')
        lines.append(f'<p style="font-size:11px;color:#6b7280;line-height:1.7;">{esc(seo_text)}</p>')

    lines.append(f'<p style="font-size:10px;color:#6b7280;margin-top:8px;">실거래가 출처: 국토교통부 · 최종 데이터 확인: {_today}</p>')

    # ── 관련 검색어 섹션 (GSC 데이터 기반 내부 링크) ──
    _anchors = build_related_anchors(d, rt, jr, bc, year_ago)

    if _anchors:
        lines.append('<nav aria-label="관련 검색어" style="margin-top:20px;">')
        lines.append('<h2 style="font-size:14px;font-weight:600;margin:0 0 8px;">관련 검색어</h2>')
        lines.append('<ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:8px;">')
        for _href, _text in _anchors:
            lines.append(
                f'<li><a href="{_href}" style="display:block;padding:12px;background:#f3f4f6;'
                f'border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">{_text}</a></li>'
            )
        lines.append('</ul>')
        lines.append('</nav>')

    return "\n    ".join(lines)


def build_jsonld(d):
    """JSON-LD 구조화 데이터"""
    did = d.get("id", "")
    name = d.get("complex_name", "")
    loc_parts = (d.get("location") or "").split(" ", 1)
    # gu: address 우선 (경기 "수원시 장안구" 2토큰 정확히 인식), 실패 시 location fallback
    gu = extract_gu_from_address(d.get("address", "")) or (loc_parts[0] if loc_parts else "")
    dong_name = loc_parts[1] if len(loc_parts) >= 2 else ""
    dong_slug_str = make_dong_slug(gu, dong_name, d.get("address", "")) if dong_name else ""
    slug = APT_SLUG_MAP.get(did) or make_slug(name, d.get("location", ""), did, d.get("address", ""))

    _gu_region_label = detect_region(d.get("address", "") or "")
    _gu_url_str = gu_url_slug(_gu_region_label, gu)
    has_gu = _has_gu_page(d.get("address", ""), _gu_url_str)
    has_dong = dong_name and dong_slug_str and dong_slug_str in DONG_SLUGS

    breadcrumb_items = [{"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"}]
    pos = 2
    if has_gu:
        breadcrumb_items.append({"@type": "ListItem", "position": pos, "name": f"{gu}", "item": f"https://hwik.kr/gu/{url_quote(_gu_url_str, safe='-')}.html"})
        pos += 1
    elif gu:
        breadcrumb_items.append({"@type": "ListItem", "position": pos, "name": f"{gu}"})
        pos += 1
    if has_dong:
        breadcrumb_items.append({"@type": "ListItem", "position": pos, "name": dong_name, "item": f"https://hwik.kr/dong/{url_quote(dong_slug_str, safe='-')}.html"})
        pos += 1
    breadcrumb_items.append({"@type": "ListItem", "position": pos, "name": name})

    graph = [
        {
            "@type": "ApartmentComplex",
            "name": name,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": d.get("location", ""),
                "streetAddress": d.get("address", ""),
                "addressCountry": "KR",
            },
        },
        {
            "@type": "BreadcrumbList",
            "itemListElement": breadcrumb_items,
        },
    ]
    graph[0]["url"] = f"https://hwik.kr/danji/{url_quote(slug, safe='-')}.html"
    if d.get("lat") and d.get("lng"):
        graph[0]["geo"] = {"@type": "GeoCoordinates", "latitude": d["lat"], "longitude": d["lng"]}
    if d.get("build_year"):
        graph[0]["yearBuilt"] = d["build_year"]
    if d.get("total_units"):
        pass  # numberOfRooms는 방 수 의미 — 세대수에 사용하면 오해 소지

    # priceRange — 실거래 데이터 기반
    rt = d.get("recent_trade") or {}
    cats = d.get("categories") or []
    prices = [rt[c].get("price", 0) for c in cats if rt.get(c) and rt[c].get("price")]
    if prices:
        min_p = min(prices)
        max_p = max(prices)
        graph[0]["pricingCurrency"] = "KRW"
        if min_p == max_p:
            graph[0]["priceRange"] = format_price(min_p)
        else:
            graph[0]["priceRange"] = f"{format_price(min_p)} ~ {format_price(max_p)}"

    # FAQ
    bc = best_price_cat(d)
    rt = d.get("recent_trade") or {}
    jr = d.get("jeonse_rate")
    faq_items = []
    if bc and rt.get(bc):
        _r = rt[bc]
        _a = f"최근 매매 실거래가는 {format_price(_r.get('price'))}입니다."
        if _r.get("date"):
            _a += f" ({_r['date']} 기준)"
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 최근 실거래가는?",
            "acceptedAnswer": {"@type": "Answer", "text": _a},
        })
    if jr:
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 전세가율은?",
            "acceptedAnswer": {"@type": "Answer", "text": f"{name}의 전세가율은 {jr}%입니다."},
        })
    # 확장 FAQ (JSON-LD) — HTML faq 섹션과 텍스트/순서 동일하게
    high = d.get("all_time_high") or {}
    if bc and high.get(bc):
        h = high[bc]
        a_text = f"최근 5년 최고가는 {format_price(h.get('price'))}입니다."
        if h.get("date"):
            a_text += f" ({h['date']})"
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 최근 5년 최고가는?",
            "acceptedAnswer": {"@type": "Answer", "text": a_text},
        })
    subway = d.get("nearby_subway") or []
    if subway:
        a = ", ".join(f"{s.get('name','')}({clean_line(s.get('line',''))}) 도보 {walk_min(s.get('distance'))}" for s in subway[:3])
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 근처 지하철역은?",
            "acceptedAnswer": {"@type": "Answer", "text": a},
        })
    year_ago_jl = find_year_ago_trade(d, bc) if bc else None
    if year_ago_jl and bc and rt.get(bc):
        cur_p = rt[bc].get("price", 0)
        old_p = year_ago_jl.get("price", 0)
        if cur_p and old_p and cur_p != old_p:
            diff = cur_p - old_p
            direction = "상승" if diff > 0 else "하락"
            faq_items.append({
                "@type": "Question",
                "name": f"{name} 1년 전 가격은?",
                "acceptedAnswer": {"@type": "Answer", "text": f"전용 {bc}㎡ 기준 1년 전 거래가는 {format_price(old_p)}({year_ago_jl.get('date','')})이었으며, 현재 {format_price(cur_p)}으로 {format_price(abs(diff))} {direction}했습니다."},
            })
    school = d.get("nearby_school") or []
    if school:
        a = ", ".join(f"{s.get('name','')} 도보 {walk_min(s.get('distance'))}" for s in school[:3])
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 주변 학교는?",
            "acceptedAnswer": {"@type": "Answer", "text": a},
        })
    if d.get("total_units") and d.get("build_year"):
        u = d["total_units"]
        u_str = f"{u:,}" if isinstance(u, int) else str(u)
        txt = f"{name}{josa(name,'은/는')} {d['build_year']}년 준공, 총 {u_str}세대 규모입니다."
        if d.get("builder"):
            txt += f" 시공사는 {d['builder']}입니다."
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 몇 세대인가요?",
            "acceptedAnswer": {"@type": "Answer", "text": txt},
        })
    # 거래 활발도 FAQ (JSON-LD)
    ph_jl = d.get("price_history") or {}
    from datetime import date as _d2, timedelta as _td2
    _one_yr = (_d2.today() - _td2(days=365)).strftime("%Y-%m")
    _trc = sum(1 for _ck in ph_jl.values() if isinstance(_ck, list) for _t in _ck if _t.get("date","")[:7] >= _one_yr)
    if _trc >= 2:
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 거래가 활발한가요?",
            "acceptedAnswer": {"@type": "Answer", "text": f"최근 1년간 {_trc}건의 매매 거래가 있었습니다."},
        })
    # 면적별 가격 FAQ (JSON-LD)
    cats = d.get("categories") or []
    ta = [(c, rt[c]) for c in sorted(cats, key=lambda x: int(x) if isinstance(x, str) and x.isdigit() else 999) if rt.get(c) and (rt[c].get("price") or 0) > 0]
    if len(ta) >= 2:
        parts = [f"전용 {a}㎡ {format_price(t.get('price'))}" for a, t in ta]
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 면적별 가격은?",
            "acceptedAnswer": {"@type": "Answer", "text": ", ".join(parts) + " (최근 거래가 기준)"},
        })

    # ── 신규 FAQ (JSON-LD, HTML과 동기화): 5년 최저가 / 주력 평형 / 주차 대수 ──
    # 매매만 사용 (price_history 키 "_" 포함은 전세/월세)
    _pha_jl = d.get("price_history") or {}
    _min_trade_jl = None
    _cat_counts_jl = {}
    for _cat_kk, _trades_jl in _pha_jl.items():
        if not isinstance(_trades_jl, list):
            continue
        if "_" in str(_cat_kk):
            continue
        _cat_counts_jl[_cat_kk] = _cat_counts_jl.get(_cat_kk, 0) + len(_trades_jl)
        for _trjl in _trades_jl:
            _prjl = _trjl.get("price")
            if not _prjl:
                continue
            if _min_trade_jl is None or _prjl < _min_trade_jl["price"]:
                _min_trade_jl = {"price": _prjl, "date": _trjl.get("date", ""), "cat": _cat_kk}
    _high_jl = d.get("all_time_high") or {}
    if _min_trade_jl and bc and _high_jl.get(bc):
        _high_p_jl = _high_jl[bc].get("price", 0)
        if _min_trade_jl["price"] and _high_p_jl and _min_trade_jl["price"] < _high_p_jl:
            _min_a_jl = f"최근 5년 최저가는 {format_price(_min_trade_jl['price'])}입니다."
            if _min_trade_jl.get("date"):
                _min_a_jl += f" ({_min_trade_jl['date']}, 전용 {_min_trade_jl['cat']}㎡)"
            faq_items.append({
                "@type": "Question",
                "name": f"{name} 최근 5년 최저가는?",
                "acceptedAnswer": {"@type": "Answer", "text": _min_a_jl},
            })
    _total_cat_jl = sum(_cat_counts_jl.values())
    if _cat_counts_jl and _total_cat_jl >= 5 and len(_cat_counts_jl) >= 2:
        _main_cat_jl, _main_cnt_jl = max(_cat_counts_jl.items(), key=lambda x: x[1])
        _main_share_jl = round(_main_cnt_jl / _total_cat_jl * 100)
        if _main_share_jl >= 30:
            faq_items.append({
                "@type": "Question",
                "name": f"{name} 주력 평형은?",
                "acceptedAnswer": {"@type": "Answer", "text": f"거래가 가장 많은 평형은 전용 {_main_cat_jl}㎡로, 최근 거래의 약 {_main_share_jl}%를 차지합니다."},
            })
    _pk_jl = d.get("parking") or 0
    try:
        _pk_n_jl = int(_pk_jl)
    except (ValueError, TypeError):
        _pk_n_jl = 0
    _units_jl = d.get("total_units") or 0
    _units_n_jl = _units_jl if isinstance(_units_jl, int) else 0
    if _pk_n_jl > 0 and _units_n_jl > 0:
        _per_unit_jl = _pk_n_jl / _units_n_jl
        if _per_unit_jl >= 0.3:
            faq_items.append({
                "@type": "Question",
                "name": f"{name} 주차 대수는?",
                "acceptedAnswer": {"@type": "Answer", "text": f"총 주차 {_pk_n_jl:,}대로 세대당 약 {_per_unit_jl:.2f}대 수준입니다."},
            })

    if faq_items:
        graph.append({"@type": "FAQPage", "mainEntity": faq_items})

    # ItemList — 관련 검색어 섹션 구조화 (HTML의 <nav>와 동일한 앵커)
    year_ago_rl = find_year_ago_trade(d, bc) if bc else None
    rel_anchors = build_related_anchors(d, rt, jr, bc, year_ago_rl)
    if rel_anchors:
        graph.append({
            "@type": "ItemList",
            "name": f"{name} 관련 검색어",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "name": text,
                    "url": f"https://hwik.kr{href}",
                }
                for i, (href, text) in enumerate(rel_anchors)
            ],
        })

    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


# ── 페이지 생성 ───────────────────────────────────────────
def generate_page(d):
    did = d.get("id", "")
    raw_name = d.get("complex_name", "")
    raw_loc = d.get("location", "")
    slug = APT_SLUG_MAP.get(did) or make_slug(raw_name, raw_loc, did, d.get("address", ""))
    name = esc(raw_name)
    loc = esc(raw_loc)
    loc_parts = raw_loc.split(" ", 1)
    # gu: address 우선 (경기 "수원시 장안구" 2토큰 정확히 인식), 실패 시 location fallback
    gu_raw = extract_gu_from_address(d.get("address", "")) or (loc_parts[0] if loc_parts else "")
    gu = esc(gu_raw)
    dong_raw = loc_parts[1] if len(loc_parts) >= 2 else ""
    dong_slug_nav = make_dong_slug(gu_raw, dong_raw, d.get("address", "")) if dong_raw else ""
    dong_nav = f'<a href="/dong/{url_quote(dong_slug_nav, safe="-")}.html" style="color:#6b7280;text-decoration:none;">{esc(dong_raw)}</a> &gt;\n      ' if dong_raw and dong_slug_nav and dong_slug_nav in DONG_SLUGS else ""
    _region_label_nav = detect_region(d.get("address", "") or "")
    _gu_url_nav = gu_url_slug(_region_label_nav, gu_raw)
    _has_gu = _has_gu_page(d.get("address", ""), _gu_url_nav)
    gu_nav = (
        f'<a href="/gu/{url_quote(_gu_url_nav, safe="-")}.html" style="color:#6b7280;text-decoration:none;">{gu}</a> &gt;'
        if _has_gu and gu else (f'<span style="color:#6b7280;">{gu}</span> &gt;' if gu else "")
    )
    units = d.get("total_units", "")
    year = d.get("build_year", "")
    # title용 위치 (중복 타이틀 방지 — 구+동)
    dong_short = dong_raw.split(" ")[0] if dong_raw else ""
    title_loc = f" ({gu} {esc(dong_short)})" if gu and dong_short else (f" ({gu})" if gu else "")
    # SEO title용 위치 접미어: " · 여의도동" 또는 " · 영통구 망포동"
    title_loc_seo = f" · {gu} {esc(dong_short)}" if gu and dong_short else (f" · {gu}" if gu else "")

    prop_type = get_prop_type(did)
    # 데이터 기반 메타 디스크립션 — 120~160자 타겟 (SERP 키워드 매칭 확대)
    _rt  = d.get("recent_trade") or {}
    _jr  = d.get("jeonse_rate")
    _bc  = best_price_cat(d)
    _bc_price = (_rt.get(_bc) or {}).get("price") if _bc else None
    # 위치 접두어 (구 동)
    _dong_first = dong_raw.split(" ")[0] if dong_raw else ""
    _loc_pref = f"{gu_raw} {_dong_first} " if gu_raw and _dong_first else (f"{gu_raw} " if gu_raw else "")
    # 면적 범위 (전용)
    _pm = d.get("pyeongs_map") or {}
    _exclu_vals = []
    for _v in _pm.values():
        if isinstance(_v, dict) and _v.get("exclu"):
            try: _exclu_vals.append(int(float(_v["exclu"])))
            except Exception: pass
    _area_str = ""
    if _exclu_vals:
        _mn, _mx = min(_exclu_vals), max(_exclu_vals)
        _area_str = f"전용 {_mn}㎡" if _mn == _mx else f"전용 {_mn}~{_mx}㎡"
    # 전세가 (매매 면적과 같은 카테고리)
    _jeonse_price = None
    if _bc:
        _jkey = f"{_bc}_jeonse"
        _jv = _rt.get(_jkey) or {}
        _jeonse_price = _jv.get("price")

    if _bc_price:
        _dp = [f"{_loc_pref}{raw_name}".strip()]
        _unit_year = []
        if units: _unit_year.append(f"{units:,}세대" if isinstance(units, int) else f"{units}세대")
        if year:  _unit_year.append(f"{year}년 입주")
        if _unit_year: _dp.append(" ".join(_unit_year))
        if _area_str: _dp.append(_area_str)
        _sale_date = (_rt.get(_bc) or {}).get("date", "")
        _dp.append(f"최근 매매 {format_price(_bc_price)}" + (f"({_sale_date})" if _sale_date else ""))
        if _jeonse_price:
            _dp.append(f"전세 {format_price(_jeonse_price)}")
        if _jr:
            _dp.append(f"전세가율 {_jr}%")
        _dp.append("국토교통부 공개시스템 실시간 기반")
        desc = ". ".join(_dp) + "."
    else:
        _dp = [f"{_loc_pref}{raw_name}".strip()]
        _unit_year = []
        if units: _unit_year.append(f"{units:,}세대" if isinstance(units, int) else f"{units}세대")
        if year:  _unit_year.append(f"{year}년 입주")
        if _unit_year: _dp.append(" ".join(_unit_year))
        if _area_str: _dp.append(_area_str)
        _dp.append(f"{prop_type} 실거래가·전세가·시세 추이")
        _dp.append("국토교통부 공개시스템 기반")
        desc = ". ".join(_dp) + "."

    canonical = f"https://hwik.kr/danji/{url_quote(slug, safe='-')}.html"
    jsonld = build_jsonld(d)
    fallback = build_fallback_html(d)

    # 네이버 메타태그용 시간 — published_time은 최초 데이터 시간, modified_time은 빌드 시점
    # modified_time >= published_time 보장
    updated_at = d.get("updated_at", "")
    pub_time = updated_at[:19] + "+00:00" if updated_at and len(updated_at) >= 19 else ""
    mod_time = BUILD_TIME
    # published가 modified보다 미래이면 swap
    if pub_time and mod_time and pub_time > mod_time:
        pub_time, mod_time = mod_time, pub_time
    naver_meta = ""
    if pub_time:
        naver_meta = f'<meta property="article:published_time" content="{pub_time}">\n<meta property="article:modified_time" content="{mod_time}">'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} 실거래가 시세{title_loc_seo} | 휙</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="icon" href="/favicon.ico">
<link rel="canonical" id="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="휙">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" id="og-title" content="{name} 실거래가 시세{title_loc_seo} | 휙">
<meta property="og:description" id="og-desc" content="{esc(desc)}">
<meta property="og:image" content="{OG_IMAGE_URL}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" id="og-url" content="{canonical}">
<meta name="google-site-verification" content="R2ye41AVVTRs8BxEXyEafFSTqMSiHKdb9zgTklrktSI" />
<meta name="naver-site-verification" content="367bd1e77a8ad48b74e345be3e4a0f8125c2c4e1" />
{naver_meta}
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2DVQXMLC9J"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-2DVQXMLC9J');</script>
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" id="tw-title" content="{name} 실거래가 시세 | 휙">
<meta name="twitter:description" id="tw-desc" content="{esc(desc)}">
<script type="application/ld+json">{jsonld}</script>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="wrap" id="app">
  <div class="loading" id="loading">
    <div class="loading-spinner"></div>
    <div class="loading-text">단지 정보 불러오는 중...</div>
  </div>
</div>
<!--
  SEO 보강 콘텐츠 (2026-04-19 클로킹 수정):
  이전: id="fallback-content" 가 #app 안에 있고 display:none. app.js가 #app innerHTML을
  덮어쓰면서 DOM에서 사라짐 → bot은 보고 사용자는 못 보는 구조 = Google 클로킹 위반.
  변경: #app 밖으로 이동 + display:none 제거. JSON-LD FAQPage 11개와 화면 콘텐츠 일치.
  h1은 app.js가 그리므로 여기서는 h2 사용 (중복 방지). nav/og-image는 SPA가 처리하므로 제거.
-->
<div class="wrap" id="fallback-content" style="padding:0 20px 20px;">
  <h2 style="font-size:16px;font-weight:700;margin:24px 0 12px;color:#374151;border-top:1px solid #e5e7eb;padding-top:24px;">{name} 상세 정보</h2>
  {fallback}
</div>
<script defer src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script defer src="/config.js"></script>
<script defer src="/makeSlug.js"></script>
<script defer src="app.js?v={app_js_hash}"></script>
</body>
</html>"""


# ── 메인 ──────────────────────────────────────────────────
def main():
    import sys
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

    os.makedirs(DANJI_DIR, exist_ok=True)

    # complex_type 맵 로드 (주상복합·도시형 태그용)
    global COMPLEX_TYPE_MAP
    COMPLEX_TYPE_MAP = fetch_complex_type_map()
    print(f"complex_type 맵 {len(COMPLEX_TYPE_MAP)}개 로드 (주상복합·도시형 포함)")

    # apartments.slug 로드 — DB 고정 slug 우선 사용 (URL 안정성)
    global APT_SLUG_MAP
    APT_SLUG_MAP = {}
    apt_offset = 0
    APT_BATCH = 500
    while True:
        rows = _get_page(
            f"{SUPABASE_URL}/rest/v1/apartments",
            {"select": "kapt_code,slug", "slug": "not.is.null",
             "order": "kapt_code", "offset": apt_offset, "limit": APT_BATCH},
        )
        if not rows:
            break
        for r in rows:
            if r.get("kapt_code") and r.get("slug"):
                APT_SLUG_MAP[r["kapt_code"]] = r["slug"]
        apt_offset += APT_BATCH
        if len(rows) < APT_BATCH:
            break
    print(f"apartments.slug 맵 {len(APT_SLUG_MAP)}개 로드")

    # 동/구 페이지 slug 목록 로드 (파일 없으면 링크 생략 — 404 방지)
    global DONG_SLUGS, GU_SLUGS
    if os.path.isdir(DONG_DIR):
        DONG_SLUGS = {os.path.splitext(f)[0] for f in os.listdir(DONG_DIR) if f.endswith(".html")}
    print(f"동 페이지 {len(DONG_SLUGS)}개 인식")
    if os.path.isdir(GU_DIR):
        GU_SLUGS = {os.path.splitext(f)[0] for f in os.listdir(GU_DIR) if f.endswith(".html")}
    print(f"구 페이지 {len(GU_SLUGS)}개 인식")

    # ── 데이터 먼저 확보 (실패 시 기존 파일 보존) ──
    print("danji_pages 조회 중...")

    # 기존 HTML 수 미리 파악 (급감 가드용)
    existing_html_count = len([f for f in os.listdir(DANJI_DIR) if f.endswith(".html")])
    print(f"기존 HTML {existing_html_count}개 확인")

    all_danji = fetch_all_danji()
    if not all_danji:
        print("❌ 데이터 0건 — 중단 (기존 페이지 유지)")
        sys.exit(1)

    # 급감 가드: 기존 파일 수 대비 99% 미만이면 중단
    # (Supabase 네트워크 오류로 일부만 받은 경우 전체 HTML 삭제 방지)
    if existing_html_count > 1000 and len(all_danji) < existing_html_count * 0.99:
        print(f"❌ 급감 감지 — DB {len(all_danji)}건 vs 기존 HTML {existing_html_count}개 "
              f"(비율 {len(all_danji)/existing_html_count:.1%}, 99% 미만) — 중단 (기존 페이지 유지)")
        sys.exit(1)

    print(f"{len(all_danji)}개 단지 로드 (기존 대비 {len(all_danji)/existing_html_count:.1%})" if existing_html_count else f"{len(all_danji)}개 단지 로드")

    # ── 단일 단지 모드 체크 (테스트용): ONE_DANJI_ID=a14077902 환경변수 ──
    # 필터링은 SLUG_MAP 생성 후로 미룸 (주변 단지 링크는 전체 데이터 기준)
    one_id = os.environ.get("ONE_DANJI_ID", "").strip()

    # ── 데이터 확보 후 기존 HTML 삭제 (단일 모드는 스킵 — 다른 페이지 보호) ──
    if not one_id:
        old_count = 0
        skip_count = 0
        for f in os.listdir(DANJI_DIR):
            if f.endswith(".html"):
                try:
                    os.remove(os.path.join(DANJI_DIR, f))
                    old_count += 1
                except PermissionError:
                    skip_count += 1  # VS Code 등이 파일 잠금 중 — 덮어쓰기로 처리됨
        if old_count:
            print(f"기존 {old_count}개 HTML 삭제" + (f" ({skip_count}개 잠금으로 스킵)" if skip_count else ""))

    # app.js 캐시 버전 — 오늘 날짜(KST) 기준으로 매일 자동 갱신
    global app_js_hash
    from datetime import timezone, timedelta
    kst = datetime.now(timezone(timedelta(hours=9)))
    app_js_hash = kst.strftime("%Y%m%d")

    # id → slug 맵 (주변 단지 링크용 — 거래 있는 단지만, 전체 데이터 기준)
    global DANJI_SLUG_MAP
    DANJI_SLUG_MAP = {}
    for d in all_danji:
        did = d.get("id", "")
        if not did:
            continue
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []
        if any(rt.get(c) for c in cats):
            DANJI_SLUG_MAP[did] = APT_SLUG_MAP.get(did) or make_slug(d.get("complex_name", ""), d.get("location", ""), did, d.get("address", ""))
    print(f"slug 맵: {len(DANJI_SLUG_MAP)}개 (거래 있는 단지만)")

    # ── 단일 단지 모드: SLUG_MAP 생성 후 필터 적용 ──
    if one_id:
        all_danji = [d for d in all_danji if d.get("id") == one_id]
        print(f"⚡ 단일 단지 모드: {one_id} ({len(all_danji)}개 매칭)")
        if not all_danji:
            print(f"❌ id={one_id} 단지를 DB에서 찾을 수 없음")
            sys.exit(1)

    count = 0
    skipped = 0
    for d in all_danji:
        did = d.get("id", "")
        if not did:
            continue
        rt = d.get("recent_trade") or {}
        cats = d.get("categories") or []
        has_trade = any(rt.get(c) for c in cats)
        if not has_trade:
            skipped += 1
            continue

        slug = DANJI_SLUG_MAP.get(did, make_slug(d.get("complex_name", ""), d.get("location", ""), did, d.get("address", "")))
        page = generate_page(d)
        path = os.path.join(DANJI_DIR, f"{slug}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        count += 1
        if count % 1000 == 0:
            print(f"  {count}개 생성...")

    print(f"\n{count}개 페이지 생성, {skipped}개 스킵 (거래 없음)")
    print(f"출력: {DANJI_DIR}/")


if __name__ == "__main__":
    main()
