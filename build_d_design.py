# -*- coding: utf-8 -*-
"""
build_d_design.py — 단지 페이지 D 디자인 SSR 풀콘텐츠 빌더.

danji_test/_make_preview.py 에서 합의된 D 디자인 시각을 Python SSR 로 옮긴 모듈.
build_danji_pages.py 의 generate_page() 가 USE_D_DESIGN=1 환경변수일 때 호출.

클로킹 회피 원칙 (feedback_seo_cloaking_ssr_spa.md):
- SSR 출력과 SPA hydrated DOM 의 텍스트 콘텐츠가 일치해야 함
- B 단계에서 danji/app.js 가 같은 D 패턴으로 hydrate 하도록 함께 수정 필수
- JSON-LD FAQPage 의 모든 Q&A 는 화면에 visible

함수 인덱스:
- build_d_header(d, ctx)              — 헤더 (좌: 휙뱃지+H1+sub / 우: location-section)
- build_d_location_section(d)         — 우측 컬럼 (지하철·학교) — 호선 색 + 학교 종류 색
- build_d_tabs()                      — 매매/전세/월세 탭
- build_d_pyeongs(d, ctx)             — 평형 chip 영역
- build_d_price_cards(d, ctx)         — 최근/5년 최고 가격 카드
- build_d_metrics(d, ctx)             — 전세가율·㎡당·최고층 메트릭 카드
- build_d_chart_section()             — 차트 섹션 (canvas, JS lazy)
- build_d_trades(d, ctx)              — 최근 실거래 (탭별 table) + 거래유형 칩
- build_d_listings_placeholder()      — 휙 등록 매물 placeholder (JS fetch)
- build_d_nearby(d, ctx)              — 주변 단지 카드 (단지타입 뱃지 + 매매 칩)
- build_d_map(d)                      — 카카오 지도 (#danji-map, 클릭 시 풀화면)
- build_d_intro_section(d, ctx)       — 단지 소개 dl + 시세 토글 + 인근 단지 SEO 문단
- build_d_more_links(d, ctx)          — 더 알아보기 (dong/gu/ranking)
- build_d_faqs(d, ctx)                — FAQ (4 visible + 더보기, 보강 8~9개 포함)
- build_d_seo_section(d)              — 데이터 안내 + 신고 버튼
- build_d_footer()                    — footer
- build_fallback_html_d(d, ctx)       — 위 헬퍼들 합친 SSR 풀콘텐츠 (build_danji_pages.py 의 build_fallback_html 대체)
"""

# build_danji_pages.py 가 import 시 사용 — 모든 헬퍼·상수는 인자로 전달받음
# (모듈 간 순환 import 방지)


def build_d_header(d, esc, gu_raw, dong_raw, prop_type):
    """헤더 — 좌(휙 36×36 노란 뱃지 + H1 + sub) / 우(location-section)"""
    name = esc(d.get("complex_name", ""))
    loc = esc(d.get("location", ""))
    units = d.get("total_units", "")
    year = d.get("build_year", "")
    builder = esc(d.get("builder", ""))
    sub_parts = [loc] if loc else []
    if units:
        sub_parts.append(f"{units:,}세대" if isinstance(units, int) else f"{units}세대")
    if year:
        sub_parts.append(f"{year}년")
    if builder:
        sub_parts.append(builder)
    if prop_type:
        sub_parts.append(esc(prop_type))
    header_sub = " · ".join(sub_parts)
    location_html = build_d_location_section(d, esc)
    return f'''<header class="header" style="background:#fff;padding:22px 24px;border-bottom:1px solid #eef0f4;display:flex;align-items:flex-start;justify-content:space-between;gap:16px;">
  <div class="header-top" style="flex:1 1 auto;min-width:0;display:flex;align-items:center;gap:12px;">
    <div class="logo" style="flex:0 0 auto;width:36px;height:36px;display:inline-flex;align-items:center;justify-content:center;background:#facc15;color:#1a1a2e;font-weight:800;font-size:14px;border-radius:8px;line-height:1;">휙</div>
    <div style="flex:1;min-width:0;">
      <h1 class="header-name" style="font-size:24px;font-weight:700;color:#4338ca;letter-spacing:-0.03em;line-height:1.25;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</h1>
      <div class="header-sub" style="font-size:13px;color:#475569;font-weight:500;letter-spacing:-0.015em;margin-top:4px;">{esc(header_sub)}</div>
    </div>
  </div>
{location_html}
</header>'''


# 한국 지하철 공식 색상 (미리보기에서 확정 — _make_preview.py official_line_colors 와 동일)
LINE_COLORS = {
    '1호선': '#0052A4', '2호선': '#00A84D', '3호선': '#EF7C1C', '4호선': '#00A4E3',
    '5호선': '#996CAC', '6호선': '#CD7C2F', '7호선': '#747F00', '8호선': '#E6186C',
    '9호선': '#BDB092',
    '경의중앙선': '#77C4A3', '수인분당선': '#FABE00', '신분당선': '#D4003B',
    '공항철도': '#0090D2', 'GTX-A': '#9A6292', '우이신설선': '#B0CE18',
    '신림선': '#6789CA', '경춘선': '#0C8E72', '김포골드라인': '#A17E46',
    '인천1호선': '#7CA8D5', '인천2호선': '#ED8B00',
}


def _line_color(line):
    """SPA shortLine() 가 '9호선'→'9' 줄임 → 양방향 매칭 (미리보기와 동일)"""
    if not line:
        return '#94a3b8'
    for k, v in LINE_COLORS.items():
        if k in line or line in k:
            return v
    return '#94a3b8'


def _short_line(line):
    """SPA shortLine() 동일 — '서울 도시철도 9호선' → '9' """
    if not line:
        return ''
    s = line
    for prefix in ('수도권 도시철도 ', '서울 도시철도 ', '수도권 광역철도 ',
                   '수도권 경량도시철도 ', '부산 도시철도 ', '대구 도시철도 ',
                   '대전 도시철도 ', '광주도시철도 ', '부산 경량도시철도 '):
        s = s.replace(prefix, '' if not prefix.startswith(('부산','대구','대전','광주')) else prefix.split()[0] + ' ')
    s = s.replace('인천국제공항선', '공항').replace('호선', '')
    return s.strip()


def _walk_min(distance_m):
    """미터 → 분 (도보 67m/분 보수적, danji/app.js walkMin 와 동일)"""
    if not distance_m:
        return ''
    try:
        return f"{round(int(distance_m) / 67)}분"
    except (TypeError, ValueError):
        return ''


def _short_school(name):
    """서울 prefix 제거 + 초등학교/중학교/고등학교 → 초/중/고 (app.js shortSchool 동일)"""
    if not name:
        return ''
    return name.replace('서울', '').replace('초등학교', '초').replace('중학교', '중').replace('고등학교', '고')


def _school_type(typ):
    """학교 type → 초/중/고"""
    if not typ:
        return ''
    if '초등' in typ:
        return '초'
    if '중학' in typ:
        return '중'
    if '고등' in typ:
        return '고'
    return ''


def _school_badge_color(typ):
    """학교 종류별 색상 (미리보기 합의)"""
    return {
        '초': {'bg': '#dcfce7', 'fg': '#166534', 'border': '#bbf7d0'},
        '중': {'bg': '#dbeafe', 'fg': '#1e40af', 'border': '#bfdbfe'},
        '고': {'bg': '#fef3c7', 'fg': '#92400e', 'border': '#fde68a'},
    }.get(typ, {'bg': 'transparent', 'fg': '#64748b', 'border': '#cbd5e1'})


def build_d_location_section(d, esc):
    """헤더 우측 컬럼: 지하철 + 학교 (도보 15분 이내, 호선 dedup)"""
    subway = d.get("nearby_subway") or []
    school = d.get("nearby_school") or []
    rows = []
    # 지하철: 도보 15분 이내, 같은 호선 중복 제거 (가까운 것 우선)
    seen_lines = set()
    sub_items = []
    for s in subway:
        line = s.get('line', '')
        time_str = _walk_min(s.get('distance'))
        try:
            mins = int(time_str.replace('분', '')) if time_str else 999
        except ValueError:
            mins = 999
        if mins > 15:
            continue
        if line in seen_lines:
            continue
        seen_lines.add(line)
        short = _short_line(line)
        color = _line_color(line)
        sub_items.append(
            f'<span class="loc-item" style="display:inline-flex;align-items:center;gap:5px;flex-shrink:0;">'
            f'<span class="line-badge" style="display:inline-block;padding:1px 5px;border-radius:3px;background:{color};color:#fff;font-size:9.5px;font-weight:600;line-height:1.3;letter-spacing:0.1px;">{esc(short)}</span>'
            f'<span class="nm" style="color:#334155;font-weight:500;font-size:11px;">{esc(s.get("name",""))}</span>'
            f'<span class="mn" style="color:#9ca3af;font-size:10.5px;font-weight:400;">{esc(time_str)}</span>'
            f'</span>'
        )
    if sub_items:
        sep = '<span style="color:#d1d5db;margin:0 6px;font-weight:500;">·</span>'
        joined = sep.join(sub_items)
        rows.append(f'<div class="loc-row" style="display:block;padding:2px 0;font-size:11px;"><div class="loc-items" style="display:flex;flex-wrap:nowrap;gap:0;color:#475569;align-items:center;white-space:nowrap;overflow:hidden;min-width:0;">{joined}</div></div>')
    # 학교: 도보 15분 이내, 같은 type+name 중복 제거. 초→중→고 순으로 정렬.
    _school_order = {'초': 0, '중': 1, '고': 2}
    school_sorted = sorted(
        school,
        key=lambda s: _school_order.get(_school_type(s.get('type', '')), 9)
    )
    seen_schools = set()
    sch_items = []
    for s in school_sorted:
        name = s.get('name', '')
        typ = _school_type(s.get('type', ''))
        time_str = _walk_min(s.get('distance'))
        try:
            mins = int(time_str.replace('분', '')) if time_str else 999
        except ValueError:
            mins = 999
        if mins > 15 or not typ:
            continue
        key = typ + ':' + name
        if key in seen_schools:
            continue
        seen_schools.add(key)
        c = _school_badge_color(typ)
        sch_items.append(
            f'<span class="loc-item" style="display:inline-flex;align-items:center;gap:5px;flex-shrink:0;">'
            f'<span class="type-badge" data-type="{typ}" style="display:inline-block;padding:0 5px;border-radius:3px;background:{c["bg"]};color:{c["fg"]};font-size:9.5px;font-weight:600;line-height:1.3;border:1px solid {c["border"]};">{typ}</span>'
            f'<span class="nm" style="color:#334155;font-weight:500;font-size:11px;">{esc(_short_school(name))}</span>'
            f'<span class="mn" style="color:#9ca3af;font-size:10.5px;font-weight:400;">{esc(time_str)}</span>'
            f'</span>'
        )
    if sch_items:
        sep = '<span style="color:#d1d5db;margin:0 6px;font-weight:500;">·</span>'
        joined = sep.join(sch_items)
        rows.append(f'<div class="loc-row" style="display:block;padding:2px 0;font-size:11px;margin-top:2px;"><div class="loc-items" style="display:flex;flex-wrap:nowrap;gap:0;color:#475569;align-items:center;white-space:nowrap;overflow:hidden;min-width:0;">{joined}</div></div>')
    if not rows:
        return ''
    return f'  <div class="location-section" style="flex:0 0 auto;width:220px;padding:0;background:transparent;border:none;align-self:flex-start;margin-top:4px;">{"".join(rows)}</div>'


def build_d_tabs(default_tab='매매'):
    """매매/전세/월세 탭 — default 활성 탭 색상별 (매매=주황 / 전세=파랑 / 월세=초록)"""
    tabs = []
    color_map = {'매매': '#ea580c', '전세': '#2563eb', '월세': '#059669'}
    for t in ('매매', '전세', '월세'):
        active = (t == default_tab)
        c = color_map[t]
        if active:
            tabs.append(
                f'<div class="tab active" data-tab="{t}" style="cursor:pointer;font-size:16px;font-weight:700;color:{c};padding:14px 20px;border-bottom:3px solid {c};letter-spacing:-0.015em;">{t}</div>'
            )
        else:
            tabs.append(
                f'<div class="tab" data-tab="{t}" style="cursor:pointer;font-size:15px;font-weight:600;color:#475569;padding:14px 20px;border-bottom:3px solid transparent;letter-spacing:-0.015em;">{t}</div>'
            )
    return f'<div class="tabs" style="display:flex;border-bottom:1px solid #eef0f4;padding:0 8px;">{"".join(tabs)}</div>'


def build_d_pyeongs(d, default_pyeong=None):
    """평형 chip — categories(전용면적) 기준. default 활성 chip 노란색."""
    cats = d.get("categories") or []
    if not cats:
        return ''
    # 정수 정렬
    try:
        cats_sorted = sorted(cats, key=lambda x: int(x))
    except (ValueError, TypeError):
        cats_sorted = list(cats)
    if default_pyeong is None and cats_sorted:
        # best_price_cat 같은 로직 — 가장 거래 많은 면적이 default. 단순화: 첫 번째.
        default_pyeong = cats_sorted[0]
    chips = []
    for c in cats_sorted:
        is_active = (str(c) == str(default_pyeong))
        if is_active:
            chips.append(
                f'<button type="button" class="pyeong-btn active" data-area="{c}" '
                f'style="cursor:pointer;background:#facc15;color:#1a1a2e;border:1px solid #facc15;border-radius:20px;padding:6px 14px;font-size:13px;font-weight:700;letter-spacing:-0.01em;">{c}㎡</button>'
            )
        else:
            chips.append(
                f'<button type="button" class="pyeong-btn" data-area="{c}" '
                f'style="cursor:pointer;background:#fff;color:#475569;border:1px solid #e2e8f0;border-radius:20px;padding:6px 14px;font-size:13px;font-weight:600;letter-spacing:-0.01em;">{c}㎡</button>'
            )
    return f'''<div style="padding:8px 16px 0;font-size:11px;color:#94a3b8;">전용면적 기준</div>
<div class="pyeong-wrap" style="padding:8px 16px 12px;"><div class="pyeong-row" style="display:flex;flex-wrap:wrap;gap:6px;">{"".join(chips)}</div></div>'''


def build_d_price_cards(d, format_price, default_pyeong=None, current_tab='매매'):
    """가격 카드 — 최근 / 5년 최고 (탭+평형 기준)"""
    cats = d.get("categories") or []
    if default_pyeong is None and cats:
        try:
            default_pyeong = sorted(cats, key=lambda x: int(x))[0]
        except (ValueError, TypeError):
            default_pyeong = cats[0]
    if not default_pyeong:
        return ''
    rt = d.get("recent_trade") or {}
    ath = d.get("all_time_high") or {}
    suffix = '' if current_tab == '매매' else ('_jeonse' if current_tab == '전세' else '_wolse')
    key = f"{default_pyeong}{suffix}"
    recent = rt.get(key) or {}
    high = ath.get(key) or {}
    label_recent = f"최근 {'전세가' if current_tab=='전세' else ('월세' if current_tab=='월세' else '실거래가')}"
    label_high = f"최근 5년 최고{' 전세가' if current_tab=='전세' else (' 월세' if current_tab=='월세' else '가')}"
    recent_price = format_price(recent.get('price')) if recent.get('price') else '-'
    high_price = format_price(high.get('price')) if high.get('price') else '-'
    recent_sub_parts = []
    if recent.get('floor'):
        recent_sub_parts.append(f"{recent['floor']}층")
    if recent.get('date'):
        recent_sub_parts.append(recent['date'])
    recent_sub = " · ".join(recent_sub_parts)
    high_sub_parts = []
    if high.get('floor'):
        high_sub_parts.append(f"{high['floor']}층")
    if high.get('date'):
        high_sub_parts.append(high['date'])
    high_sub = " · ".join(high_sub_parts)
    return f'''<div id="area-price-cards" style="padding:0 16px;"><div class="price-cards" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
  <div class="price-card primary" style="background:#fff;border:1px solid #dbeafe;border-radius:12px;padding:18px;">
    <div class="price-card-label" style="font-size:12px;color:#64748b;font-weight:500;">{label_recent}</div>
    <div class="price-card-value" style="font-weight:700;color:#0f172a;letter-spacing:-0.03em;font-feature-settings:'tnum' 1;font-variant-numeric:tabular-nums;font-size:24px;margin-top:4px;">{recent_price}</div>
    <div class="price-card-sub" style="font-size:11.5px;color:#94a3b8;font-weight:500;font-feature-settings:'tnum' 1;margin-top:2px;">{recent_sub}</div>
  </div>
  <div class="price-card secondary" style="background:#fef7f7;border:1px solid #fee2e2;border-radius:12px;padding:18px;">
    <div class="price-card-label" style="font-size:12px;color:#64748b;font-weight:500;">{label_high}</div>
    <div class="price-card-value" style="font-weight:700;color:#dc2626;letter-spacing:-0.03em;font-feature-settings:'tnum' 1;font-variant-numeric:tabular-nums;font-size:24px;margin-top:4px;">{high_price}</div>
    <div class="price-card-sub" style="font-size:11.5px;color:#94a3b8;font-weight:500;font-feature-settings:'tnum' 1;margin-top:2px;">{high_sub}</div>
  </div>
</div></div>'''


def build_d_metrics(d, format_price, default_pyeong=None):
    """메트릭 카드 — 전세가율, ㎡당 가격(공급면적 기준), 최고층"""
    cats = d.get("categories") or []
    if default_pyeong is None and cats:
        try:
            default_pyeong = sorted(cats, key=lambda x: int(x))[0]
        except (ValueError, TypeError):
            default_pyeong = cats[0]
    cells = []
    if d.get('jeonse_rate'):
        cells.append({'label': '전세가율', 'value': f"{d['jeonse_rate']}%", 'foot': ''})
    # ㎡당 가격 (공급면적 기준)
    pm = d.get('pyeongs_map') or {}
    rt = d.get('recent_trade') or {}
    if default_pyeong:
        recent = rt.get(default_pyeong) or {}
        sup_info = pm.get(default_pyeong) or {}
        supply = sup_info.get('supply') if isinstance(sup_info, dict) else None
        if supply and recent.get('price'):
            try:
                sqm = round(int(recent['price']) / float(supply))
                cells.append({'label': '㎡당 가격', 'value': format_price(sqm), 'foot': '공급면적 기준'})
            except (TypeError, ValueError, ZeroDivisionError):
                pass
    if d.get('top_floor'):
        cells.append({'label': '최고층', 'value': f"{d['top_floor']}층", 'foot': ''})
    if not cells:
        return ''
    n = len(cells)
    items = []
    for c in cells:
        foot = f'<div class="metric-foot" style="font-size:11px;color:#94a3b8;font-weight:500;margin-top:4px;">{c["foot"]}</div>' if c.get('foot') else ''
        items.append(
            f'<div class="metric" style="display:flex;flex-direction:column;justify-content:space-between;min-height:92px;padding:14px 16px;box-sizing:border-box;background:#f8fafc;border-radius:12px;">'
            f'<div class="metric-label" style="font-size:11.5px;color:#94a3b8;font-weight:500;line-height:1.3;">{c["label"]}</div>'
            f'<div class="metric-value" style="font-size:16px;font-weight:700;color:#0f172a;letter-spacing:-0.02em;font-feature-settings:\'tnum\' 1;line-height:1.4;margin-top:4px;flex:1 1 auto;display:flex;align-items:center;flex-wrap:wrap;">{c["value"]}</div>'
            f'{foot}'
            f'</div>'
        )
    return f'<div id="area-metrics" style="padding:8px 16px 0;"><div class="metrics" style="display:grid;grid-template-columns:repeat({n},1fr);gap:8px;align-items:stretch;">{"".join(items)}</div></div>'


def build_d_chart_section():
    """차트 섹션 — canvas placeholder (JS 가 나중에 그림)"""
    return '''<section class="chart-section" id="chart-section" aria-labelledby="chart-h2" style="padding:16px;">
  <h2 id="chart-h2" class="section-title" style="padding:0 0 10px;font-size:15px;font-weight:700;color:#0f172a;letter-spacing:-0.025em;margin:0;">가격 추이</h2>
  <div class="chart-title" style="font-size:11px;color:#94a3b8;">거래량</div>
  <div style="height:40px;position:relative;"><canvas id="volumeChart"></canvas></div>
  <div class="chart-title" style="font-size:11px;color:#94a3b8;margin-top:8px;">실거래가</div>
  <div class="chart-wrap" style="height:200px;position:relative;"><canvas id="priceChart"></canvas></div>
</section>'''


# 거래유형 칩 색상 (미리보기 _kindColor 와 동일)
_KIND_COLOR = {
    '매매': {'bg': '#fff1e7', 'fg': '#c2410c'},
    '전세': {'bg': '#eaf2ff', 'fg': '#1d4ed8'},
    '월세': {'bg': '#e8f6ee', 'fg': '#047857'},
}


def _kind_chip(kind):
    c = _KIND_COLOR.get(kind)
    if not c:
        return ''
    return (f'<span style="display:inline-block;padding:2px 7px;border-radius:4px;background:{c["bg"]};color:{c["fg"]};'
            f'font-size:10.5px;font-weight:700;letter-spacing:0.2px;line-height:1.4;margin-right:8px;vertical-align:middle;">{kind}</span>')


def build_d_trades(d, esc, format_price, default_pyeong=None, current_tab='매매'):
    """최근 실거래 (탭별 table) + 거래유형 칩 — 5건"""
    cats = d.get("categories") or []
    if default_pyeong is None and cats:
        try:
            default_pyeong = sorted(cats, key=lambda x: int(x))[0]
        except (ValueError, TypeError):
            default_pyeong = cats[0]
    name = esc(d.get("complex_name", ""))
    ph = d.get("price_history") or {}
    tables = []
    for tab, suffix in (('매매', ''), ('전세', '_jeonse'), ('월세', '_wolse')):
        key = f"{default_pyeong}{suffix}" if default_pyeong else ''
        items = ph.get(key) or []
        # 최근순 정렬, 5건
        try:
            items_sorted = sorted(items, key=lambda x: x.get('date', ''), reverse=True)[:5]
        except (TypeError, AttributeError):
            items_sorted = list(items)[:5]
        rows = []
        for t in items_sorted:
            price = format_price(t.get('price'))
            if tab == '월세' and t.get('monthly'):
                price = f"보증금 {price} / 월 {t['monthly']}만"
            detail_parts = []
            if t.get('exclu') or default_pyeong:
                detail_parts.append(f"전용 {t.get('exclu', default_pyeong)}㎡")
            if t.get('floor'):
                detail_parts.append(f"{t['floor']}층")
            detail = " · ".join(detail_parts)
            kind_badge = ''
            kind = t.get('kind', '')
            if kind in ('직거래', '중개거래'):
                bg = '#fef3c7' if kind == '직거래' else '#dbeafe'
                fg = '#92400e' if kind == '직거래' else '#1e40af'
                tag = '직거래' if kind == '직거래' else '중개'
                kind_badge = (f'<span style="display:inline-block;background:{bg};color:{fg};font-size:10px;'
                              f'font-weight:600;padding:2px 6px;border-radius:4px;margin-left:6px;vertical-align:middle;">{tag}</span>')
            rows.append(
                f'<tr class="trade-item" style="display:flex;background:#fff;border:1px solid transparent;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.05);padding:14px;margin-bottom:8px;">'
                f'<td class="trade-info" style="display:block;flex:1;min-width:0;">'
                f'<div class="trade-price" style="font-size:15px;font-weight:700;color:#0f172a;letter-spacing:-0.02em;font-feature-settings:\'tnum\' 1;">{_kind_chip(tab)}{price}{kind_badge}</div>'
                f'<div class="trade-detail" style="font-size:12px;color:#64748b;font-weight:500;margin-top:4px;font-feature-settings:\'tnum\' 1;">{esc(detail)}</div>'
                f'</td>'
                f'<td class="trade-date" style="display:block;font-size:12.5px;color:#475569;font-weight:600;font-feature-settings:\'tnum\' 1;">{esc(t.get("date", ""))}</td>'
                f'</tr>'
            )
        body = "".join(rows) if rows else f'<tr><td style="padding:8px 0;color:#64748b;font-size:12px;">{tab} 거래 내역이 없습니다</td></tr>'
        display = '' if tab == current_tab else 'display:none;'
        tables.append(
            f'<table class="trade-list" id="trade-list-{tab}" style="display:flex;flex-direction:column;gap:8px;width:100%;border-collapse:collapse;{display}">'
            f'<caption class="sr-only">{name} {tab} 실거래</caption>'
            f'<thead class="sr-only"><tr><th scope="col">유형 및 가격</th><th scope="col">전용면적·층수</th><th scope="col">거래일</th></tr></thead>'
            f'<tbody style="display:flex;flex-direction:column;gap:8px;width:100%;">{body}</tbody>'
            f'</table>'
        )
    return f'<div class="section" style="padding:20px 24px;"><h2 class="section-title" id="trade-section-title" style="font-size:16px;font-weight:700;color:#0f172a;letter-spacing:-0.025em;margin:0 0 12px;">최근 실거래</h2>{"".join(tables)}</div>'


def build_d_listings_placeholder(d):
    """휙 등록 매물 placeholder — JS 가 cards 테이블에서 fetch 해서 채움"""
    did = d.get("id", "")
    return f'''<div class="section" id="listing-section" data-danji-id="{did}" style="padding:20px 24px;">
  <h2 class="section-title" style="font-size:16px;font-weight:700;color:#0f172a;letter-spacing:-0.025em;margin:0 0 12px;">휙 등록 매물</h2>
  <div id="listing-content" style="font-size:12px;color:#94a3b8;padding:8px 0;">매물 정보 불러오는 중...</div>
</div>'''


def build_d_nearby(d, esc, format_price, dong_raw, nearby_complex_types_map=None):
    """주변 단지 카드 — 단지명 앞 [아파트/주상복합/도시형] 보라 뱃지 + 매매 가격 주황 + '매매' 칩"""
    nearby = d.get("nearby_complex") or []
    if not nearby:
        return ''
    items = []
    for n in nearby:
        nid = n.get('id', '') or ''
        if nid.startswith('offi-') or nid.startswith('apt-'):
            continue
        if not n.get('slug'):
            continue
        if '임대' in (n.get('name') or ''):
            continue
        prices = n.get('prices') or {}
        if not prices:
            continue
        # 가장 가까운 면적 (84 기준)
        best = None
        best_diff = 999
        for k, v in prices.items():
            try:
                diff = abs(int(k) - 84)
            except (ValueError, TypeError):
                continue
            if diff < best_diff:
                best_diff = diff
                best = (k, v)
        if not best or not best[1].get('price'):
            continue
        k, v = best
        price_txt = format_price(v.get('price'))
        # 단지타입 (주상복합/도시형/아파트)
        nct = (nearby_complex_types_map or {}).get(nid.upper(), '') if nearby_complex_types_map else ''
        if nct in ('주상복합', '도시형 생활주택(주상복합)'):
            tag_label, tag_bg, tag_fg = '주상복합', '#ede9fe', '#5b21b6'
        elif nct == '도시형 생활주택(아파트)':
            tag_label, tag_bg, tag_fg = '도시형', '#ede9fe', '#5b21b6'
        else:
            tag_label, tag_bg, tag_fg = '아파트', '#eef2ff', '#4338ca'
        tag = (f'<span style="display:inline-block;padding:1px 6px;margin-right:6px;border-radius:4px;'
               f'background:{tag_bg};color:{tag_fg};font-size:10px;font-weight:600;vertical-align:middle;">{tag_label}</span>')
        # 거리 텍스트
        dist = n.get('distance') or 0
        if dist >= 1000:
            dist_txt = f"{dist/1000:.2f}km".rstrip('0').rstrip('.')
        else:
            dist_txt = f"{int(dist)}m" if dist else ''
        loc_txt = esc(n.get('location', ''))
        sub_parts = [loc_txt] if loc_txt else []
        if dist_txt:
            sub_parts.append(dist_txt)
        try:
            ex = int(v.get('exclu') or k)
            sub_parts.append(f"전용 {ex}㎡")
        except (ValueError, TypeError):
            pass
        sub = " · ".join(sub_parts)
        items.append(
            f'<a class="nearby-item" href="/danji/{n["slug"]}.html" style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:14px;background:#f8fafc;border-radius:8px;text-decoration:none;color:inherit;border:1px solid transparent;">'
            f'<div><div class="nearby-name" style="font-size:14px;font-weight:700;color:#0f172a;letter-spacing:-0.015em;">{tag}{esc(n.get("name", ""))}</div>'
            f'<div class="nearby-sub" style="font-size:12px;color:#64748b;font-weight:500;margin-top:3px;font-feature-settings:\'tnum\' 1;">{sub}</div></div>'
            f'<div style="text-align:right;">'
            f'<div class="nearby-price" style="font-size:15px;font-weight:700;color:#ea580c;letter-spacing:-0.02em;font-feature-settings:\'tnum\' 1;">{price_txt}</div>'
            f'<div style="font-size:11px;color:#94a3b8;margin-top:2px;">{_kind_chip("매매")}{esc(v.get("date", ""))}</div>'
            f'</div></a>'
        )
    if not items:
        return ''
    return f'''<div class="section" style="padding:20px 24px;">
  <h2 class="section-title" style="font-size:16px;font-weight:700;color:#0f172a;letter-spacing:-0.025em;margin:0 0 12px;">{esc(dong_raw)} 주변 단지</h2>
  <div style="display:flex;flex-direction:column;gap:8px;">{"".join(items)}</div>
</div>'''


def build_d_map(d, esc):
    """카카오 지도 — #danji-map placeholder, 클릭 시 풀화면 새창 (JS 처리)"""
    if not d.get('lat') or not d.get('lng'):
        return ''
    addr = esc(d.get('address', ''))
    name_q = (d.get('complex_name', '') or '').replace('"', '')
    return f'''<div class="divider" style="height:1px;background:#eef0f4;margin:0;"></div>
<div class="section" id="map-section" style="padding:20px 24px;">
  <h2 class="section-title" style="font-size:16px;font-weight:700;color:#0f172a;letter-spacing:-0.025em;margin:0 0 12px;">위치</h2>
  <div id="danji-map" data-lat="{d["lat"]}" data-lng="{d["lng"]}" data-name="{esc(name_q)}" style="width:100%;height:240px;border-radius:8px;overflow:hidden;background:#e5e7eb;cursor:pointer;" aria-label="{addr} 지도" title="카카오맵에서 자세히 보기"></div>
  <div style="margin-top:8px;font-size:11px;color:#94a3b8;">{addr}</div>
</div>'''


def _info_row(label, value, full=False):
    """단지 소개 dl 안 행 — full=True면 grid-column:1/-1 (소재지·전용면적용)"""
    full_css = 'grid-column:1 / -1;' if full else ''
    return (f'<div style="{full_css}display:flex;gap:10px;align-items:baseline;padding:6px 0;border-bottom:1px solid #f1f3f5;">'
            f'<span style="color:#94a3b8;font-size:12px;flex-shrink:0;width:70px;">{label}</span>'
            f'<span style="color:#0a0e1a;font-size:13px;line-height:1.5;">{value}</span></div>')


def build_d_intro_section(d, esc, format_price, gu_raw, dong_raw, dong_href=None, gu_href=None):
    """단지 소개 dl + 시세 요약 토글 + 인근 단지 SEO 링크 문단"""
    name_raw = d.get('complex_name', '')
    name = esc(name_raw)
    addr = d.get('address', '')
    units = d.get('total_units', '')
    year = d.get('build_year', '')
    builder_raw = d.get('builder', '')
    # ── 1) info-row 데이터 수집 ──
    rows = {}
    if addr:
        rows['소재지'] = esc(addr)
    if year:
        rows['준공'] = f"{year}년 · 공동주택"
    if units:
        rows['세대수'] = f"{units:,}세대" if isinstance(units, int) else f"{units}세대"
    if d.get('top_floor'):
        rows['최고층'] = f"지상 {d['top_floor']}층"
    pk_raw = d.get('parking')
    try:
        pk = int(pk_raw) if pk_raw else 0
    except (ValueError, TypeError):
        pk = 0
    tu = 0
    try:
        tu = int(units) if isinstance(units, (int, str)) and str(units).isdigit() else (units if isinstance(units, int) else 0)
    except (ValueError, TypeError):
        tu = 0
    if pk > 0 and (tu == 0 or (pk / tu) >= 0.5):
        ratio_str = f" (세대당 {pk/tu:.2f}대)" if tu > 0 else ''
        rows['주차'] = f"{pk:,}대{ratio_str}"
    if d.get('heating'):
        rows['난방'] = esc(d['heating'])
    if builder_raw:
        rows['시공사'] = esc(builder_raw)
    # 전용면적
    pm = d.get('pyeongs_map') or {}
    exclus = []
    if isinstance(pm, dict):
        for k, v in pm.items():
            try:
                exclus.append(int(round(float((v or {}).get('exclu') or k))))
            except (ValueError, TypeError):
                pass
    if not exclus:
        cats = d.get('categories') or []
        for c in cats:
            try:
                exclus.append(int(c))
            except (ValueError, TypeError):
                pass
    if exclus:
        exclus_uniq = sorted(set([e for e in exclus if e > 0]))
        if exclus_uniq:
            rows['전용면적'] = "㎡, ".join(str(e) for e in exclus_uniq) + "㎡"
    # 순서: 소재지(풀) → 준공/세대수/최고층/주차/난방/시공사 → 전용면적(풀)
    dl_html = ['<dl style="display:grid;grid-template-columns:1fr 1fr;column-gap:24px;row-gap:0;margin:0 0 16px;padding:0;">']
    if '소재지' in rows:
        dl_html.append(_info_row('소재지', rows['소재지'], True))
    for k in ('준공', '세대수', '최고층', '주차', '난방', '시공사'):
        if k in rows:
            dl_html.append(_info_row(k, rows[k], False))
    if '전용면적' in rows:
        dl_html.append(_info_row('전용면적', rows['전용면적'], True))
    dl_html.append('</dl>')
    # ── 2) 시세 요약 토글 ──
    cats = d.get('categories') or []
    rt = d.get('recent_trade') or {}
    ath = d.get('all_time_high') or {}
    bc = next((c for c in cats if rt.get(c) and rt[c].get('price')), cats[0] if cats else '')
    summary_rows = []
    if bc and rt.get(bc) and rt[bc].get('price'):
        rs = rt[bc]
        date = f" · {rs['date']}" if rs.get('date') else ''
        summary_rows.append(
            f'<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;">'
            f'<span style="color:#94a3b8;">최근 매매</span>'
            f'<span style="color:#0a0e1a;font-weight:500;">{format_price(rs["price"])} '
            f"<span style='color:#94a3b8;font-size:12px;'>(전용 {bc}㎡{date})</span></span></div>")
    if bc and ath.get(bc) and ath[bc].get('price'):
        hs = ath[bc]
        date = f"<span style='color:#94a3b8;font-size:12px;'> ({hs['date']})</span>" if hs.get('date') else ''
        summary_rows.append(
            f'<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;">'
            f'<span style="color:#94a3b8;">5년 최고</span>'
            f'<span style="color:#0a0e1a;font-weight:500;">{format_price(hs["price"])}{date}</span></div>')
    foot_parts = []
    if d.get('jeonse_rate'):
        foot_parts.append(f"전세가율 {d['jeonse_rate']}%")
    foot_str = (f'<div style="margin-top:6px;padding-top:8px;border-top:1px solid #f1f3f5;font-size:12px;color:#94a3b8;">'
                f'{" · ".join(foot_parts)}</div>') if foot_parts else ''
    # 거래 통계
    ph = d.get('price_history') or {}
    sale_n = jeonse_n = monthly_n = 0
    for k, v in ph.items():
        if not isinstance(v, list):
            continue
        cnt = len(v)
        if k.endswith('_jeonse'):
            jeonse_n += cnt
        elif k.endswith('_wolse'):
            monthly_n += cnt
        else:
            sale_n += cnt
    total_n = sale_n + jeonse_n + monthly_n
    trade_stat = ''
    if total_n > 0:
        trade_stat = (f'<p style="font-size:13px;color:#94a3b8;line-height:1.85;margin:0 0 10px;">'
                      f'최근 5년 동안 {name}에서는 총 {total_n:,}건의 실거래가 집계되었으며, '
                      f'매매 {sale_n}건, 전세 {jeonse_n}건, 월세 {monthly_n}건이 신고되었습니다.</p>')
    details_html = ''
    if summary_rows or trade_stat:
        details_html = (
            '<details style="margin:0 0 12px;">'
            '<summary style="cursor:pointer;font-size:12px;color:#94a3b8;padding:2px 0;list-style:none;display:inline-flex;align-items:center;gap:4px;">'
            '<span style="display:inline-block;transform:rotate(0deg);transition:transform .15s;">▸</span>'
            '시세 요약 · 거래 활성도 · 인근 인프라 자세히 보기'
            '</summary>'
            '<div style="margin-top:8px;">'
            + (f'<div style="margin:0 0 14px;">{"".join(summary_rows)}{foot_str}</div>' if summary_rows else '')
            + trade_stat + '</div></details>'
            '<style>details[open] > summary > span{transform:rotate(90deg) !important;}</style>'
        )
    # ── 3) 인근 단지 SEO 링크 문단 ──
    nearby = d.get('nearby_complex') or []
    nearby_safe = [n for n in nearby if n.get('id') and not n['id'].startswith(('offi-', 'apt-')) and n.get('slug')]
    nearby_links = []
    for n in nearby_safe[:2]:
        nloc = (n.get('location') or '').split(' ')
        nd = nloc[-1] if nloc else ''
        nearby_links.append(f'<a href="/danji/{n["slug"]}.html">{esc(nd + " " if nd else "") + esc(n.get("name", ""))} 아파트</a>')
    seo_p = ''
    if nearby_links and dong_href and dong_raw and gu_href and gu_raw:
        seo_p = (f'<p style="font-size:13px;color:#94a3b8;line-height:1.85;margin:0;">'
                 f'인근 단지로는 {", ".join(nearby_links)} 등이 있으며, 같은 {esc(dong_raw)} 일대의 다른 단지는 '
                 f'<a href="{dong_href}">{esc(gu_raw)} {esc(dong_raw)} 아파트</a>, 시군구 단위 비교는 '
                 f'<a href="{gu_href}">{esc(gu_raw)} 아파트 시세</a>에서 확인할 수 있습니다.</p>')
    return (f'<div class="divider" style="height:1px;background:#eef0f4;margin:0;"></div>'
            f'<section class="seo-intro" style="padding:0 16px 16px;">'
            f'<h2 class="section-title" style="padding:0 0 8px;font-size:15px;font-weight:700;color:#0a0e1a;margin:0;">단지 소개</h2>'
            f'{"".join(dl_html)}{details_html}{seo_p}</section>')


def build_d_more_links(esc, dong_raw, dong_href, gu_raw, gu_href, region_key=None):
    """더 알아보기 — dong/gu/ranking 3 링크"""
    if not (dong_href or gu_href):
        return ''
    items = []
    if dong_href and dong_raw:
        items.append(
            f'<a href="{dong_href}" style="display:flex;justify-content:space-between;align-items:center;padding:12px 14px;background:#f8fafc;border-radius:8px;text-decoration:none;color:#0f172a;">'
            f'<span style="font-size:13px;">{esc(dong_raw)} 다른 단지 시세</span>'
            f'<span style="color:#94a3b8;font-size:12px;">→</span></a>')
    if gu_href and gu_raw:
        items.append(
            f'<a href="{gu_href}" style="display:flex;justify-content:space-between;align-items:center;padding:12px 14px;background:#f8fafc;border-radius:8px;text-decoration:none;color:#0f172a;">'
            f'<span style="font-size:13px;">{esc(gu_raw)} 전체 시세</span>'
            f'<span style="color:#94a3b8;font-size:12px;">→</span></a>')
    if region_key:
        label_map = {'seoul': '서울', 'incheon': '인천', 'gyeonggi': '경기', 'busan': '부산',
                     'daegu': '대구', 'gwangju': '광주', 'daejeon': '대전', 'ulsan': '울산',
                     'sejong': '세종', 'chungbuk': '충북', 'chungnam': '충남', 'jeonbuk': '전북',
                     'jeonnam': '전남', 'gyeongbuk': '경북', 'gyeongnam': '경남',
                     'gangwon': '강원', 'jeju': '제주'}
        rl = label_map.get(region_key, region_key)
        items.append(
            f'<a href="/ranking/{region_key}-price.html" style="display:flex;justify-content:space-between;align-items:center;padding:12px 14px;background:#f8fafc;border-radius:8px;text-decoration:none;color:#0f172a;">'
            f'<span style="font-size:13px;">{rl} 아파트 매매가 순위 TOP 50</span>'
            f'<span style="color:#94a3b8;font-size:12px;">→</span></a>')
    if not items:
        return ''
    return (f'<div class="section" style="padding:20px 24px;">'
            f'<h2 class="section-title" style="font-size:16px;font-weight:700;color:#0f172a;letter-spacing:-0.025em;margin:0 0 12px;">더 알아보기</h2>'
            f'<div style="display:flex;flex-direction:column;gap:8px;">{"".join(items)}</div></div>')


def build_d_faqs(d, esc, format_price):
    """FAQ — 4 visible + hidden + 더보기. 미리보기에서 보강된 8~9개 포함."""
    name = esc(d.get('complex_name', ''))
    cats = d.get('categories') or []
    rt = d.get('recent_trade') or {}
    ath = d.get('all_time_high') or {}
    jr = d.get('jeonse_rate')
    bc = next((c for c in cats if rt.get(c) and rt[c].get('price')), cats[0] if cats else '')
    items = []
    # 1) 최근 실거래가
    if bc and rt.get(bc) and rt[bc].get('price'):
        date = f" ({rt[bc]['date']} 기준)" if rt[bc].get('date') else ''
        items.append((f"{name} 최근 실거래가는?", f"{name} 최근 매매 실거래가는 {format_price(rt[bc]['price'])}입니다.{date}"))
    # 2) 5년 최고
    if bc and ath.get(bc) and ath[bc].get('price'):
        date = f" ({ath[bc]['date']})" if ath[bc].get('date') else ''
        items.append((f"{name} 최근 5년 최고가는?", f"최근 5년 최고가는 {format_price(ath[bc]['price'])}입니다.{date}"))
    # 3) 전세가율
    if jr:
        items.append((f"{name} 전세가율은?", f"{name}의 전세가율은 {jr}%입니다."))
    # 4) 준공·세대수
    if d.get('build_year') and d.get('total_units'):
        u = d['total_units']
        items.append((f"{name}는 몇 년 준공, 몇 세대?",
                      f"{name}는 {d['build_year']}년 준공, 총 {u:,}세대 규모입니다."))
    # 5) 거래 활발도
    ph = d.get('price_history') or {}
    sale_n = jeonse_n = monthly_n = 0
    jeonse_sum = jeonse_cnt = 0
    deposit_sum = monthly_sum = monthly_cnt = 0
    for k, v in ph.items():
        if not isinstance(v, list):
            continue
        if k.endswith('_jeonse'):
            jeonse_n += len(v)
            for t in v:
                if t.get('price'):
                    jeonse_sum += t['price']
                    jeonse_cnt += 1
        elif k.endswith('_wolse'):
            monthly_n += len(v)
            for t in v:
                if t.get('price'):
                    deposit_sum += t['price']
                    monthly_sum += (t.get('monthly') or 0)
                    monthly_cnt += 1
        else:
            sale_n += len(v)
    if sale_n > 0:
        items.append((f"{name} 매매 거래는 얼마나 활발?", f"최근 5년 매매 {sale_n}건이 집계되었습니다."))
    # 6) 전세 시세
    if jeonse_cnt > 0:
        avg = round(jeonse_sum / jeonse_cnt)
        items.append((f"{name} 전세 시세는?",
                      f"최근 5년 전세 실거래 {jeonse_n}건 평균 보증금은 {format_price(avg)}입니다."))
    # 7) 월세 평균
    if monthly_cnt > 0:
        avg_d = round(deposit_sum / monthly_cnt)
        avg_m = round(monthly_sum / monthly_cnt)
        items.append((f"{name} 월세 평균은?",
                      f"최근 5년 월세 실거래 {monthly_n}건 평균은 보증금 {format_price(avg_d)} / 월세 {avg_m}만입니다."))
    # 8) 최고층
    if d.get('top_floor'):
        items.append((f"{name} 최고층은?", f"지상 {d['top_floor']}층 규모입니다."))
    # 9) 신축/노후
    if d.get('build_year'):
        from datetime import datetime as _dt
        age = _dt.now().year - int(d['build_year'])
        if 0 <= age <= 5:
            items.append((f"{name} 신축 아파트인가요?",
                          f"{name}는 {d['build_year']}년 준공으로 {age + 1}년차 신축 아파트입니다."))
        elif age > 25:
            items.append((f"{name} 노후 아파트인가요?",
                          f"{name}는 {d['build_year']}년 준공으로 {age}년차 단지입니다."))
    # 10) 전세가가 매매가 대비
    if jr and bc and rt.get(bc) and rt[bc].get('price'):
        jeo = rt.get(f"{bc}_jeonse")
        if jeo and jeo.get('price'):
            items.append((f"{name} 전세가가 매매가 대비 얼마나?",
                          f"최근 매매가 {format_price(rt[bc]['price'])}, 최근 전세가 {format_price(jeo['price'])}로, "
                          f"전세가율은 약 {jr}%입니다."))
    if not items:
        return ''
    # visible (4) + hidden (rest) + 더보기
    visible_html = "".join(
        f'<div class="faq-item"><div class="faq-q">{esc(q)}</div><div class="faq-a">{esc(a)}</div></div>'
        for q, a in items[:4])
    hidden_html = ''
    more_html = ''
    if len(items) > 4:
        hidden_html = ('<div class="faq-list-hidden" id="faq-hidden">' + "".join(
            f'<div class="faq-item"><div class="faq-q">{esc(q)}</div><div class="faq-a">{esc(a)}</div></div>'
            for q, a in items[4:]) + '</div>')
        more_html = ('<div class="faq-more" onclick="document.getElementById(\'faq-hidden\').classList.toggle(\'expanded\');this.style.display=\'none\';">'
                     '더보기</div>')
    return (f'<section class="faq-section" style="padding:20px 24px;">'
            f'<h2 class="section-title" style="font-size:16px;font-weight:700;color:#0f172a;letter-spacing:-0.025em;margin:0 0 12px;">자주 묻는 질문</h2>'
            f'<div class="faq-list-visible">{visible_html}</div>{hidden_html}{more_html}</section>')


def build_d_seo_section(today_str):
    """데이터 안내 + 신고 버튼 (오피스텔 D 패턴)"""
    return f'''<div class="seo-section" style="padding:20px 24px;">
  <details open style="font-size:12px;color:#94a3b8;">
    <summary style="cursor:pointer;">데이터 안내</summary>
    <div style="margin-top:6px;line-height:1.8;">
      <b>실거래가</b>: 국토교통부 실거래가 공개시스템 (<a href="https://rt.molit.go.kr/" target="_blank" rel="noopener nofollow">rt.molit.go.kr</a>) · 매일 자동 수집<br>
      <b>건축정보</b>: 국토교통부 건축물대장 (전유부 · 총괄표제부)<br>
      <b>세대 수</b>: 건축물대장 전유부 등기 기준 (분양 공급 수치와 다를 수 있음)<br>
      공급면적이 확인되지 않은 단지는 전용면적만 표시합니다<br>
      거래 취소·정정 건은 반영이 지연될 수 있습니다
    </div>
  </details>
  <div class="seo-source" style="margin-top:8px;font-size:11px;color:#9ca3af;">실거래가 출처: 국토교통부 · 최종 데이터 확인: <time datetime="{today_str}">{today_str}</time></div>
  <div style="margin-top:14px;text-align:center;">
    <button type="button" onclick="openReportModal && openReportModal()"
       style="background:none;border:1px solid #e5e7eb;border-radius:20px;color:#6b7280;font-size:12px;cursor:pointer;padding:6px 16px;">데이터 오류 신고</button>
  </div>
</div>'''


def build_d_footer():
    """footer (오피스텔 D 동일)"""
    return ('<footer style="max-width:600px;margin:24px auto 40px;padding:24px 16px 0;border-top:1px solid #e5e7eb;'
            'text-align:center;font-size:11.5px;color:#6b7280;line-height:1.7;">'
            '<div style="margin-bottom:8px;">'
            '<a href="/about.html" style="color:#6b7280;text-decoration:none;margin:0 8px;">휙 소개</a>·'
            '<a href="/privacy.html" style="color:#6b7280;text-decoration:none;margin:0 8px;">개인정보처리방침</a>·'
            '<a href="/terms.html" style="color:#6b7280;text-decoration:none;margin:0 8px;">이용약관</a>'
            '</div>'
            '<div style="color:#9ca3af;">실거래가 출처: 국토교통부 · 휙(HWIK) · '
            '<a href="https://hwik.kr" style="color:#9ca3af;text-decoration:none;">hwik.kr</a></div>'
            '</footer>')


def build_fallback_html_d(d, ctx):
    """
    D SSR 풀콘텐츠 — build_danji_pages.py 의 build_fallback_html 대체.

    ctx 인자 (build_danji_pages.py 가 전달):
      - esc, format_price, prop_type, gu_raw, dong_raw, dong_href, gu_href, region_key,
        nearby_complex_types_map (옵션), today_str
    """
    esc = ctx['esc']
    format_price = ctx['format_price']
    return "\n".join([
        build_d_header(d, esc, ctx['gu_raw'], ctx['dong_raw'], ctx.get('prop_type', '아파트')),
        build_d_tabs(default_tab='매매'),
        build_d_pyeongs(d),
        build_d_price_cards(d, format_price, current_tab='매매'),
        build_d_metrics(d, format_price),
        build_d_chart_section(),
        build_d_trades(d, esc, format_price, current_tab='매매'),
        build_d_listings_placeholder(d),
        build_d_nearby(d, esc, format_price, ctx.get('dong_raw', ''),
                       ctx.get('nearby_complex_types_map')),
        build_d_map(d, esc),
        build_d_intro_section(d, esc, format_price, ctx.get('gu_raw', ''),
                              ctx.get('dong_raw', ''), ctx.get('dong_href'), ctx.get('gu_href')),
        build_d_more_links(esc, ctx.get('dong_raw', ''), ctx.get('dong_href'),
                           ctx.get('gu_raw', ''), ctx.get('gu_href'), ctx.get('region_key')),
        build_d_faqs(d, esc, format_price),
        build_d_seo_section(ctx.get('today_str', '')),
        build_d_footer(),
    ])
    """카카오 지도 — #danji-map placeholder, 클릭 시 풀화면 새창 (JS 처리)"""
    if not d.get('lat') or not d.get('lng'):
        return ''
    addr = esc(d.get('address', ''))
    name_q = d.get('complex_name', '').replace('"', '')
    return f'''<div class="divider" style="height:1px;background:#eef0f4;margin:0;"></div>
<div class="section" id="map-section" style="padding:20px 24px;">
  <h2 class="section-title" style="font-size:16px;font-weight:700;color:#0f172a;letter-spacing:-0.025em;margin:0 0 12px;">위치</h2>
  <div id="danji-map" data-lat="{d["lat"]}" data-lng="{d["lng"]}" data-name="{esc(name_q)}" style="width:100%;height:240px;border-radius:8px;overflow:hidden;background:#e5e7eb;cursor:pointer;" aria-label="{addr} 지도" title="카카오맵에서 자세히 보기"></div>
  <div style="margin-top:8px;font-size:11px;color:#94a3b8;">{addr}</div>
</div>'''
