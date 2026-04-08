#!/usr/bin/env python3
"""
build_danji_pages.py — 단지별 정적 HTML 페이지 생성 (SEO)

Supabase danji_pages → danji/[id].html (정적 SEO 콘텐츠 + 인터랙티브 JS)
GitHub Actions에서 매일 실행, 변경분만 커밋.

Usage:
  python build_danji_pages.py
"""

import os, json, re, time, html as html_mod
import requests
from slug_utils import REGION_MAP, METRO_CITIES, clean as _clean, detect_region, make_danji_slug as make_slug, make_dong_slug

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

# 동 페이지 slug 목록 (빌드 시 로드 — 동 파일 없는 곳은 링크 생략)
DONG_SLUGS = set()


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


# ── Supabase 조회 ─────────────────────────────────────────
def fetch_all_danji():
    all_data = []
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            headers={**SB_HEADERS, "Prefer": ""},
            params={
                "select": "id,complex_name,location,address,build_year,total_units,"
                          "categories,recent_trade,all_time_high,jeonse_rate,"
                          "price_history,"
                          "nearby_subway,nearby_school,nearby_complex,"
                          "lat,lng,top_floor,parking,heating,builder,updated_at",
                "order": "id",
                "offset": offset,
                "limit": 500,
            },
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else []
        if not data:
            break
        all_data.extend(data)
        offset += 500
        if len(data) < 500:
            break
        time.sleep(0.2)
    return all_data


# ── CSS/JS 추출 ───────────────────────────────────────────
def extract_css_js():
    """danji.html에서 CSS와 메인 JS를 추출하여 외부 파일로 분리"""
    path = os.path.join(BASE_DIR, "danji.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # CSS
    css_m = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
    css = css_m.group(1).strip() if css_m else ""

    # 메인 JS (const sb = supabase.createClient 부터 마지막 </script> 전까지)
    js_m = re.search(
        r"<script>\s*\nconst sb = supabase\.createClient.*?</script>",
        content, re.DOTALL,
    )
    if js_m:
        js = js_m.group(0)
        js = js.replace("<script>", "", 1)
        js = js[:js.rfind("</script>")]
        js = js.strip()
    else:
        # 폴백: 가장 큰 script 블록
        blocks = re.findall(r"<script>(.*?)</script>", content, re.DOTALL)
        js = max(blocks, key=len) if blocks else ""

    # ── JS 수정: URL 경로에서도 ID 추출 (slug에서 맨 뒤 ID) ──
    js = js.replace(
        "const id = new URLSearchParams(location.search).get('id');",
        "const id = new URLSearchParams(location.search).get('id')"
        " || (location.pathname.match(/-(a\\d+)(?:\\.html)?$/) || [])[1]"
        " || (location.pathname.match(/((?:offi|apt)-[^/]+?)(?:\\.html)?$/) || [])[1]"
        " || null;",
        1,
    )

    # ── JS 수정: canonical/og:url을 새 경로에 맞게 ──
    js = js.replace(
        "canonicalEl.href = `https://hwik.kr/danji.html?id=${encodeURIComponent(id)}`;",
        "canonicalEl.href = location.pathname.includes('/danji/')"
        " ? `https://hwik.kr/danji/${encodeURIComponent(id)}`"
        " : `https://hwik.kr/danji.html?id=${encodeURIComponent(id)}`;",
    )
    js = js.replace(
        "if (ogUrl) ogUrl.content = `https://hwik.kr/danji.html?id=${encodeURIComponent(id)}`;",
        "if (ogUrl) ogUrl.content = location.pathname.includes('/danji/')"
        " ? `https://hwik.kr/danji/${encodeURIComponent(id)}`"
        " : `https://hwik.kr/danji.html?id=${encodeURIComponent(id)}`;",
    )

    # ── JS 수정: 404 리다이렉트도 경로 호환 ──
    js = js.replace(
        "var fullUrl = 'https://hwik.kr/danji.html?id=' + encodeURIComponent(id);",
        "var fullUrl = location.pathname.includes('/danji/')"
        " ? 'https://hwik.kr/danji/' + encodeURIComponent(id)"
        " : 'https://hwik.kr/danji.html?id=' + encodeURIComponent(id);",
    )

    return css, js


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


def build_intro_sentence(name, addr, year, units, builder, bc, rt, jr):
    """데이터 특성에 따라 다른 서두 문장 생성 — 콘텐츠 다양화"""
    from datetime import datetime as _dt
    current_year = _dt.now().year
    age = current_year - year if year else None
    unit_count = units if isinstance(units, int) else 0
    price = safe_int(rt[bc].get("price"), 0) if bc and rt.get(bc) else 0

    # 신축 대단지
    if age is not None and age <= 5 and unit_count >= 1000:
        return f"{name}은(는) {year}년 준공된 {unit_count:,}세대 규모의 신축 대단지로, {addr}에 있습니다."
    # 신축
    if age is not None and age <= 5:
        return f"{addr}에 위치한 {name}은(는) {year}년 준공된 신축 아파트입니다."
    # 대단지
    if unit_count >= 1000 and year:
        return f"{name}은(는) {addr}의 {unit_count:,}세대 대단지 아파트로, {year}년에 준공되었습니다."
    if unit_count >= 1000:
        return f"{name}은(는) {addr}의 {unit_count:,}세대 대단지 아파트입니다."
    # 전세 수요 높음
    try:
        jr_float = float(jr) if jr else 0
    except (ValueError, TypeError):
        jr_float = 0
    if jr_float >= 70:
        return f"{name}은(는) 전세가율 {jr}%로 전세가율이 높은 {addr} 소재 아파트입니다."
    # 고가
    if price >= 150000:
        return f"{addr}의 {name}은(는) 최근 전용 {bc}㎡가 {format_price(price)}에 거래된 아파트입니다."
    # 유명 시공사
    major = ["삼성물산", "현대건설", "대우건설", "GS건설", "포스코건설", "대림산업", "롯데건설", "HDC현대산업개발"]
    if builder and any(b in builder for b in major):
        if year:
            return f"{name}은(는) {builder} 시공의 아파트로, {addr}에 위치하며 {year}년 준공되었습니다."
        return f"{name}은(는) {builder} 시공의 아파트로, {addr}에 위치합니다."
    # 구축
    if age is not None and age >= 30:
        return f"{year}년 준공된 {name}은(는) {addr}에 위치한 아파트입니다."
    # 소형
    if 0 < unit_count < 300:
        return f"{addr} 소재 {name}은(는) 총 {unit_count:,}세대 규모의 아파트입니다."
    # 기본
    if year and addr:
        return f"{name}은(는) {addr}에 있는 {year}년 준공 아파트입니다."
    elif addr:
        return f"{name}은(는) {addr}에 위치한 아파트입니다."
    return f"{name} 아파트입니다."


def build_fallback_html(d):
    """Googlebot이 읽는 정적 SEO 콘텐츠"""
    name = esc(d.get("complex_name", ""))
    loc = esc(d.get("location", ""))
    loc_parts = (d.get("location") or "").split(" ")
    gu = esc(loc_parts[0]) if loc_parts else ""
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

    # 기본 정보
    info = f"{loc}"
    if units:
        info += f" · {units:,}세대" if isinstance(units, int) else f" · {units}세대"
    if year:
        info += f" · {year}년"
    if builder:
        info += f" · {builder}"
    lines.append(f'<p style="font-size:13px;color:#6b7280;margin-bottom:16px;">{info}</p>')

    # 시세
    if bc and rt.get(bc):
        r = rt[bc]
        txt = f"전용 {bc}㎡ 최근 매매가: {format_price(r.get('price'))}"
        if r.get("date"):
            txt += f" ({r['date']})"
        lines.append(f'<p style="font-size:15px;font-weight:600;margin-bottom:6px;">{txt}</p>')
    if bc and high.get(bc):
        h = high[bc]
        txt = f"역대 최고가: {format_price(h.get('price'))}"
        if h.get("date"):
            txt += f" ({h['date']})"
        lines.append(f'<p style="font-size:13px;color:#6b7280;margin-bottom:6px;">{txt}</p>')
    if jr:
        lines.append(f'<p style="font-size:13px;color:#6b7280;margin-bottom:6px;">전세가율: {jr}%</p>')

    # 시계열 비교 (1년 전 거래와 비교)
    year_ago = find_year_ago_trade(d, bc) if bc else None
    if year_ago and bc and rt.get(bc):
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
        lines.append(f'<p style="font-size:12px;color:#9ca3af;margin-bottom:12px;">면적: {area_list}</p>')

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
        items = [f"{esc(s.get('name',''))}({esc(s.get('line',''))}) 도보 {walk_min(s.get('distance'))}" for s in subway[:3]]
        lines.append(f'<p style="font-size:12px;color:#9ca3af;margin-bottom:4px;">인근 지하철: {", ".join(items)}</p>')

    # 학교
    school = d.get("nearby_school") or []
    if school:
        items = [f"{esc(s.get('name',''))} 도보 {walk_min(s.get('distance'))}" for s in school[:2]]
        lines.append(f'<p style="font-size:12px;color:#9ca3af;margin-bottom:12px;">인근 학교: {", ".join(items)}</p>')

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
        lines.append(f'<p style="font-size:12px;color:#9ca3af;margin-bottom:12px;">{", ".join(specs)}</p>')

    nearby = d.get("nearby_complex") or []
    # 주변 단지
    if nearby:
        lines.append('<h2 style="font-size:14px;font-weight:600;margin:16px 0 8px;">주변 단지</h2>')
        lines.append('<ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:6px;">')
        for n in nearby[:5]:
            prices = n.get("prices") or {}
            nbest = None
            ndiff = 999
            for k, v in prices.items():
                diff = abs(safe_int(k) - 84)
                if diff < ndiff:
                    ndiff = diff
                    nbest = v
            p = format_price(nbest.get("price")) if nbest and nbest.get("price") else "-"
            nid = n.get("id", "")
            nname_raw = n.get("name", "")
            nloc_raw = n.get("location", "")
            nslug = make_slug(nname_raw, nloc_raw, nid, d.get("address", ""))
            nname = esc(nname_raw)
            nloc = esc(nloc_raw)
            lines.append(
                f'<li><a href="/danji/{nslug}" style="display:flex;justify-content:space-between;'
                f'padding:10px 12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">'
                f'<span>{nname} <span style="color:#9ca3af;font-size:11px;">{nloc}</span></span>'
                f'<span style="font-weight:600;">{p}</span></a></li>'
            )
        lines.append("</ul>")

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
        a = f"역대 최고가는 {format_price(h.get('price'))}입니다."
        if h.get("date"):
            a += f" ({h['date']})"
        faq.append((f"{name} 역대 최고가는?", a))
    if subway:
        a = ", ".join(f"{esc(s.get('name',''))}({esc(s.get('line',''))}) 도보 {walk_min(s.get('distance'))}" for s in subway[:3])
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
        a = f"{name}은(는) {year}년 준공, 총 {u}세대 규모입니다."
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
    intro = build_intro_sentence(raw_name, raw_addr, year, units, raw_builder, bc, rt, jr)
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
        seo.append(f"전용 {bc}㎡ 역대 최고가는 {format_price(h.get('price'))}{h_date}입니다.")
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
        names = ", ".join(f"{s.get('name','')}({s.get('line','')})" for s in subway[:2])
        seo.append(f"인근 지하철역은 {names}입니다.")
    if school:
        names = ", ".join(s.get("name", "") for s in school[:2])
        seo.append(f"인근 학교로 {names}이(가) 있습니다.")
    if total_recent_trades >= 2:
        seo.append(f"최근 1년간 {total_recent_trades}건의 매매 거래가 있었습니다.")
    seo.append("모든 데이터는 국토교통부 실거래가 공개시스템 기반이며 매일 갱신됩니다.")
    seo_text = " ".join(s for s in seo if s)
    if seo_text:
        lines.append(f'<p style="font-size:11px;color:#9ca3af;line-height:1.7;margin-top:16px;">{esc(seo_text)}</p>')

    lines.append('<p style="font-size:10px;color:#9ca3af;margin-top:8px;">실거래가 출처: 국토교통부 실거래가 공개시스템 · 매일 업데이트</p>')

    # 내부 링크
    loc_parts_raw = (d.get("location") or "").split(" ", 1)
    dong_name = loc_parts_raw[1] if len(loc_parts_raw) >= 2 else ""
    gu_for_link = loc_parts_raw[0] if loc_parts_raw else ""
    dong_slug_str = ""
    if dong_name:
        dong_slug_str = make_dong_slug(gu_for_link, dong_name, d.get("address", ""))
    lines.append('<div style="margin-top:16px;display:flex;flex-direction:column;gap:8px;">')
    if dong_name and dong_slug_str and dong_slug_str in DONG_SLUGS:
        lines.append(f'<a href="/dong/{dong_slug_str}" style="padding:12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">{esc(dong_name)} 다른 단지 시세 →</a>')
    lines.append(f'<a href="/gu.html?name={gu}" style="padding:12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">{gu} 전체 시세 →</a>')
    lines.append('<a href="/ranking.html" style="padding:12px;background:#f3f4f6;border-radius:8px;text-decoration:none;color:#1a1a2e;font-size:13px;">아파트 순위 →</a>')
    lines.append("</div>")

    return "\n    ".join(lines)


def build_jsonld(d):
    """JSON-LD 구조화 데이터"""
    did = d.get("id", "")
    name = d.get("complex_name", "")
    loc_parts = (d.get("location") or "").split(" ")
    gu = loc_parts[0] if loc_parts else ""
    slug = make_slug(name, d.get("location", ""), did, d.get("address", ""))

    graph = [
        {
            "@type": "Residence",
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
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr"},
                {"@type": "ListItem", "position": 2, "name": f"{gu}", "item": f"https://hwik.kr/gu.html?name={gu}"},
                {"@type": "ListItem", "position": 3, "name": name, "item": f"https://hwik.kr/danji/{slug}"},
            ],
        },
    ]
    graph[0]["url"] = f"https://hwik.kr/danji/{slug}"
    if d.get("lat") and d.get("lng"):
        graph[0]["geo"] = {"@type": "GeoCoordinates", "latitude": d["lat"], "longitude": d["lng"]}
    if d.get("build_year"):
        graph[0]["yearBuilt"] = d["build_year"]
    if d.get("total_units"):
        graph[0]["numberOfRooms"] = d["total_units"]

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
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 최근 실거래가는?",
            "acceptedAnswer": {"@type": "Answer", "text": f"최근 매매 실거래가는 {format_price(rt[bc].get('price'))}입니다."},
        })
    if jr:
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 전세가율은?",
            "acceptedAnswer": {"@type": "Answer", "text": f"{name}의 전세가율은 {jr}%입니다."},
        })
    # 확장 FAQ (JSON-LD)
    high = d.get("all_time_high") or {}
    if bc and high.get(bc):
        h = high[bc]
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 역대 최고가는?",
            "acceptedAnswer": {"@type": "Answer", "text": f"전용 {bc}㎡ 역대 최고가는 {format_price(h.get('price'))}({h.get('date','')})입니다."},
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
                "acceptedAnswer": {"@type": "Answer", "text": f"전용 {bc}㎡ 1년 전 거래가는 {format_price(old_p)}이었으며, 현재 {format_price(cur_p)}으로 {format_price(abs(diff))} {direction}했습니다."},
            })
    subway = d.get("nearby_subway") or []
    if subway:
        a = ", ".join(f"{s.get('name','')}({s.get('line','')}) 도보 {walk_min(s.get('distance'))}" for s in subway[:3])
        faq_items.append({
            "@type": "Question",
            "name": f"{name} 근처 지하철역은?",
            "acceptedAnswer": {"@type": "Answer", "text": a},
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
        txt = f"{name}은(는) {d['build_year']}년 준공, 총 {u_str}세대입니다."
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
    if faq_items:
        graph.append({"@type": "FAQPage", "mainEntity": faq_items})

    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


# ── 페이지 생성 ───────────────────────────────────────────
def generate_page(d):
    did = d.get("id", "")
    raw_name = d.get("complex_name", "")
    raw_loc = d.get("location", "")
    slug = make_slug(raw_name, raw_loc, did, d.get("address", ""))
    name = esc(raw_name)
    loc = esc(raw_loc)
    loc_parts = raw_loc.split(" ")
    gu = esc(loc_parts[0]) if loc_parts else ""
    units = d.get("total_units", "")
    year = d.get("build_year", "")

    desc_parts = [raw_name, raw_loc]
    if units:
        desc_parts.append(f"{units}세대")
    if year:
        desc_parts.append(f"{year}년")
    desc_parts.append("아파트 실거래가, 전세가, 시세 추이")
    desc = " ".join(desc_parts)

    canonical = f"https://hwik.kr/danji/{slug}"
    jsonld = build_jsonld(d)
    fallback = build_fallback_html(d)

    # 네이버 메타태그용 시간
    updated_at = d.get("updated_at", "")
    meta_time = updated_at[:19] + "+00:00" if updated_at and len(updated_at) >= 19 else ""
    naver_meta = ""
    if meta_time:
        naver_meta = f'<meta property="article:published_time" content="{meta_time}">\n<meta property="article:modified_time" content="{meta_time}">'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} 실거래가 시세 - 휙</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="canonical" id="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="휙">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" id="og-title" content="{name} 실거래가 시세 - 휙">
<meta property="og:description" id="og-desc" content="{esc(desc)}">
<meta property="og:image" content="https://hwik.kr/og-image.png">
<meta property="og:url" id="og-url" content="{canonical}">
<meta name="google-site-verification" content="R2ye41AVVTRs8BxEXyEafFSTqMSiHKdb9zgTklrktSI" />
<meta name="naver-site-verification" content="367bd1e77a8ad48b74e345be3e4a0f8125c2c4e1" />
{naver_meta}
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2DVQXMLC9J"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-2DVQXMLC9J');</script>
<meta name="twitter:card" content="summary">
<meta name="twitter:title" id="tw-title" content="{name} 실거래가 시세 - 휙">
<meta name="twitter:description" id="tw-desc" content="{esc(desc)}">
<script type="application/ld+json">{jsonld}</script>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="wrap" id="app">
  <div class="loading" id="loading">
    <div class="loading-spinner"></div>
    <div class="loading-text">단지 정보 불러오는 중...</div>
  </div>
  <div id="fallback-content" style="padding:20px;">
    <nav style="font-size:11px;color:#9ca3af;margin-bottom:12px;">
      <a href="/" style="color:#6b7280;text-decoration:none;">휙</a> &gt;
      <a href="/gu.html?name={gu}" style="color:#6b7280;text-decoration:none;">{gu}</a> &gt;
      {name}
    </nav>
    <h1 style="font-size:18px;font-weight:700;margin-bottom:8px;">{name} 실거래가</h1>
    {fallback}
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script src="/config.js"></script>
<script src="/makeSlug.js"></script>
<script src="app.js?v={int(time.time())}"></script>
</body>
</html>"""


# ── 메인 ──────────────────────────────────────────────────
def main():
    import sys
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

    os.makedirs(DANJI_DIR, exist_ok=True)

    # 동 페이지 slug 목록 로드 (동 파일 없으면 링크 생략)
    global DONG_SLUGS
    if os.path.isdir(DONG_DIR):
        DONG_SLUGS = {os.path.splitext(f)[0] for f in os.listdir(DONG_DIR) if f.endswith(".html")}
    print(f"동 페이지 {len(DONG_SLUGS)}개 인식")

    # 옛 HTML 파일 삭제 (고아 파일 방지, style.css/app.js는 유지)
    old_count = 0
    for f in os.listdir(DANJI_DIR):
        if f.endswith(".html"):
            os.remove(os.path.join(DANJI_DIR, f))
            old_count += 1
    if old_count:
        print(f"기존 {old_count}개 HTML 삭제")

    print("danji_pages 조회 중...")
    all_danji = fetch_all_danji()
    print(f"{len(all_danji)}개 단지 로드")

    print("CSS/JS 추출 중...")
    css, js = extract_css_js()

    with open(os.path.join(DANJI_DIR, "style.css"), "w", encoding="utf-8") as f:
        f.write(css)
    print(f"  style.css ({len(css):,} bytes)")

    with open(os.path.join(DANJI_DIR, "app.js"), "w", encoding="utf-8") as f:
        f.write(js)
    print(f"  app.js ({len(js):,} bytes)")

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

        slug = make_slug(d.get("complex_name", ""), d.get("location", ""), did, d.get("address", ""))
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
