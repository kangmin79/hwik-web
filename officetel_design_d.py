"""officetel_design_d.py — 오피스텔 단지 페이지 D 디자인 (PC ≥768px) 단일 소스.

- preview_desktop_designs.py (로컬 비교용)
- build_officetel_pages.py (본 빌드)
양쪽에서 import 하여 동일한 CSS+JS 블록을 사용한다.

PC만 적용. 모바일(<768px)은 기존 /danji/style.css 그대로 유지.
"""

DESIGN_D_BLOCK = r"""
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" as="style" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<style id="design-override">
@media (min-width: 1px) {
  html, body {
    background: #F0EEE6 !important;
    font-family: Pretendard, -apple-system, BlinkMacSystemFont,
                 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans CJK KR', sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
    -moz-osx-font-smoothing: grayscale !important;
    text-rendering: optimizeLegibility !important;
  }
  /* 모든 텍스트 요소에 Pretendard 강제 (style.css의 inherit 끊기는 부분 대비) */
  article, article *, .breadcrumb, .header, .header *, .tabs, .tab,
  .pyeong-btn, .price-card, .price-card *, .metric, .metric *,
  .chart-section, .chart-title, .trade-item, .trade-item *,
  .nearby-item, .nearby-item *, .faq-item, .faq-q, .faq-a,
  .seo-text, .section-title, .seo-section, .seo-section *,
  .location-section, .location-section *, .seo-intro, .seo-intro * {
    font-family: Pretendard, -apple-system, BlinkMacSystemFont,
                 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans CJK KR', sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
    -moz-osx-font-smoothing: grayscale !important;
  }

  /* ── 타이포 위계 강화 (가독성 ↑) ─────────────────────────── */
  /* H1 단지명 — 가장 강함 (휙 브랜드 인디고) */
  article > .header > .header-top .header-name {
    font-size: 24px !important;
    font-weight: 700 !important;
    color: #4338ca !important;
    letter-spacing: -0.03em !important;
    line-height: 1.25 !important;
  }
  /* 헤더 sub (위치·준공 등) */
  article > .header .header-sub {
    font-size: 13px !important;
    color: #475569 !important;
    font-weight: 500 !important;
    letter-spacing: -0.015em !important;
  }
  /* breadcrumb — 더 옅게, 작게 */
  article > .breadcrumb { font-size: 12px !important; color: #94a3b8 !important; }
  article > .breadcrumb a { color: #64748b !important; }

  /* H2 section-title — 진하고 큼직 */
  article .section-title,
  article #chart-h2.section-title,
  article #trade-section-title {
    font-size: 16px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
    letter-spacing: -0.025em !important;
  }

  /* 탭 활성 — 더 굵게 */
  article > .tabs .tab.active { font-weight: 700 !important; font-size: 16px !important; }
  article > .tabs .tab { letter-spacing: -0.015em !important; }

  /* 평형 chip 활성 — 굵게 */
  article .pyeong-btn { font-weight: 600 !important; letter-spacing: -0.01em !important; }
  article .pyeong-btn.active { font-weight: 700 !important; }

  /* 가격 카드 숫자 — 가장 큰 시각 강조 */
  article .price-card-value {
    font-weight: 700 !important;
    color: #0f172a !important;
    letter-spacing: -0.03em !important;
    font-feature-settings: "tnum" 1 !important;
    font-variant-numeric: tabular-nums !important;
  }
  article .price-card-label {
    font-size: 12px !important; color: #64748b !important; font-weight: 500 !important;
  }
  article .price-card-sub {
    font-size: 11.5px !important; color: #94a3b8 !important; font-weight: 500 !important;
    font-feature-settings: "tnum" 1 !important;
  }

  /* 보조지표 카드 — 카드 간 높이 균형 + 안쪽 3행 (label/value/foot) 정렬 */
  article .metrics { align-items: stretch !important; }
  article .metric {
    display: flex !important;
    flex-direction: column !important;
    justify-content: space-between !important;
    min-height: 92px !important;
    padding: 14px 16px !important;
    box-sizing: border-box !important;
  }
  article .metric-label {
    font-size: 11.5px !important; color: #94a3b8 !important; font-weight: 500 !important;
    line-height: 1.3 !important;
  }
  article .metric-value {
    font-size: 16px !important; font-weight: 700 !important; color: #0f172a !important;
    letter-spacing: -0.02em !important;
    font-feature-settings: "tnum" 1 !important;
    line-height: 1.4 !important;
    margin-top: 4px !important;
    flex: 1 1 auto !important;
    display: flex !important; align-items: center !important;
    flex-wrap: wrap !important;
  }
  article .metric-foot {
    font-size: 11px !important; color: #94a3b8 !important; font-weight: 500 !important;
    margin-top: 4px !important;
  }

  /* 거래 항목 — 가격 진하게, 메타 옅게 */
  article .trade-item .trade-price {
    font-size: 15px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
    letter-spacing: -0.02em !important;
    font-feature-settings: "tnum" 1 !important;
  }
  article .trade-item .trade-detail {
    font-size: 12px !important;
    color: #64748b !important;
    font-weight: 500 !important;
    margin-top: 4px !important;
    font-feature-settings: "tnum" 1 !important;
  }
  article .trade-item .trade-date {
    font-size: 12.5px !important;
    color: #475569 !important;
    font-weight: 600 !important;
    font-feature-settings: "tnum" 1 !important;
  }

  /* 주변 단지 — 가격 진하게 */
  article .nearby-item .nearby-name {
    font-size: 14px !important; font-weight: 700 !important; color: #0f172a !important;
    letter-spacing: -0.015em !important;
  }
  article .nearby-item .nearby-sub {
    font-size: 12px !important; color: #64748b !important; font-weight: 500 !important;
    margin-top: 3px !important;
    font-feature-settings: "tnum" 1 !important;
  }
  article .nearby-item .nearby-price {
    font-size: 15px !important; font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    font-feature-settings: "tnum" 1 !important;
  }

  /* FAQ */
  article .faq-q { font-size: 14px !important; font-weight: 600 !important; color: #0f172a !important; letter-spacing: -0.015em !important; }
  article .faq-a { font-size: 13px !important; color: #475569 !important; line-height: 1.75 !important; }

  /* 모든 숫자 영역에 tabular-nums (가격 정렬) */
  article .price-card *, article .metric *, article .trade-item *,
  article .nearby-price, article .nearby-sub, article .trade-date,
  article .pyeong-btn { font-variant-numeric: tabular-nums !important; }
  main.wrap {
    max-width: 600px !important;
    margin: 32px auto !important;
    background: var(--surface) !important;
    border-radius: 20px !important;
    box-shadow: 0 10px 40px rgba(0,0,0,0.08), 0 2px 8px rgba(0,0,0,0.04) !important;
    min-height: 0 !important;
    overflow: hidden;
  }
  /* 헤더를 라이트 톤으로 (Richgo 참고) + 좌(이름) / 우(역·학교) 2열 */
  article > .header {
    background: #fff !important;
    padding: 22px 24px !important;
    border-bottom: 1px solid #eef0f4 !important;
    display: flex !important;
    align-items: flex-start !important;
    justify-content: space-between !important;
    gap: 16px !important;
  }
  article > .header > .header-top {
    flex: 1 1 auto !important; min-width: 0 !important;
  }
  /* H1 한 줄 고정 + 넘치면 말줄임 */
  article > .header > .header-top .header-name {
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    max-width: 100% !important;
  }
  /* 헤더 안으로 들어온 location-section: 우측 컬럼화 */
  article > .header > .location-section {
    flex: 0 0 auto !important;
    width: 220px !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
    border-bottom: none !important;
    align-self: flex-start;
    margin-top: 4px !important;
  }
  article > .header > .location-section .loc-row {
    display: block !important; padding: 2px 0 !important; font-size: 11px !important;
  }
  article > .header > .location-section .loc-row + .loc-row {
    margin-top: 2px !important;
  }
  article > .header > .location-section .loc-row::after {
    background: linear-gradient(to right, rgba(255,255,255,0), rgba(255,255,255,1)) !important;
    width: 24px !important;
  }
  /* 우측 컬럼 안에서는 호선/학교 라벨 더 컴팩트 */
  article > .header > .location-section .loc-item .line-badge,
  article > .header > .location-section .loc-item .type-badge {
    font-size: 9.5px !important; padding: 1px 4px !important;
  }
  article > .header > .location-section .loc-item .nm { font-size: 11px !important; }
  article > .header > .location-section .loc-item .mn { font-size: 10.5px !important; }
  article > .header > .location-section .loc-item + .loc-item::before {
    margin: 0 6px !important;
  }
  article > .header .header-name {
    font-size: 22px !important; font-weight: 700 !important; color: #4338ca !important;
  }
  article > .header .header-sub {
    font-size: 14px !important; margin-top: 4px !important; color: #64748b !important;
  }
  /* 로고는 브랜드 컬러(노란 "휙") 유지 — 라이트 배경에 포인트 */
  /* 지하철/학교 태그: 라이트 톤 */
  article > .header .tag-line {
    color: #334155 !important;
    background: transparent !important;
  }
  article > .header .tag-line::after {
    background: linear-gradient(to right, rgba(255,255,255,0), rgba(255,255,255,1)) !important;
  }
  article > .header .station-name,
  article > .header .station-time { color: #334155 !important; }
  article > .header .school-tag { color: #334155 !important; }
  article > .header .school-tag span[style*="rgba(255,255,255"] { color: #334155 !important; }
  article > .header .school-type {
    background: #dcfce7 !important; color: #166534 !important;
  }
  article > .header .tag-sep { color: #cbd5e1 !important; }

  /* 헤더 좌정렬 (Richgo 스타일) */
  article > .header .header-top {
    display: flex !important; align-items: center !important; gap: 12px !important;
  }
  article > .header .header-top > div:nth-of-type(1) { flex: 1; min-width: 0; }
  article > .header .header-sub {
    font-size: 13px !important; color: #64748b !important; margin-top: 4px !important;
    line-height: 1.5 !important;
  }

  /* 헤더: 심플 좌정렬. 지하철/학교는 JS 로 별도 섹션으로 빠짐 */
  article > .header .tag-line { display: none !important; }

  /* 새 섹션: 교통·학교 (헤더 바로 아래) — 시선 무게 낮춤 */
  .location-section {
    padding: 6px 24px 8px !important;
    background: transparent;
    border-bottom: 1px solid #eef0f4;
  }
  .location-section .loc-row {
    display: flex; align-items: center; padding: 5px 0; font-size: 12.5px;
    position: relative; overflow: hidden;
  }
  .location-section .loc-row + .loc-row { border-top: none; }
  .location-section .loc-row::after {
    content: ''; position: absolute; right: 0; top: 0; bottom: 0; width: 32px;
    background: linear-gradient(to right, rgba(255,255,255,0), rgba(255,255,255,1));
    pointer-events: none;
  }
  .location-section .loc-items {
    display: flex; flex-wrap: nowrap; gap: 0; color: #475569; align-items: center;
    white-space: nowrap; overflow: hidden; min-width: 0;
  }
  .location-section .loc-item { flex-shrink: 0; }
  .location-section .loc-item { display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0; }
  .location-section .loc-item + .loc-item::before {
    content: '·'; color: #d1d5db; margin: 0 8px; font-weight: 500;
  }
  /* 호선 뱃지: 채도 낮춤 — 큰 칠 대신 작은 점 + 텍스트 */
  .location-section .loc-item .line-badge {
    display: inline-block; padding: 1px 5px; border-radius: 3px;
    background: #94a3b8; color: #fff; font-size: 10px; font-weight: 600;
    line-height: 1.3; letter-spacing: 0.1px; opacity: 0.78;
  }
  /* 학교 뱃지: 은은한 태그 톤 (초/중/고 구분) */
  .location-section .loc-item .type-badge {
    display: inline-block; padding: 0 5px; border-radius: 3px;
    background: transparent; color: #64748b; font-size: 10px; font-weight: 600;
    line-height: 1.3; border: 1px solid #cbd5e1;
  }
  .location-section .loc-item .type-badge.type-elem {
    background: #d1fae5 !important; color: #047857 !important; border-color: #6ee7b7 !important;
  }
  .location-section .loc-item .type-badge.type-mid {
    background: #dbeafe !important; color: #1d4ed8 !important; border-color: #93c5fd !important;
  }
  .location-section .loc-item .type-badge.type-high {
    background: #fef3c7 !important; color: #b45309 !important; border-color: #fcd34d !important;
  }
  .location-section .loc-item .nm { color: #334155; font-weight: 500; }
  .location-section .loc-item .mn { color: #9ca3af; font-size: 11px; font-weight: 400; }

  /* 탭 가독성 강화 */
  article > .tabs {
    border-bottom: 1px solid #eef0f4 !important;
    padding: 0 8px !important;
  }
  article > .tabs .tab {
    cursor: pointer !important;
    font-size: 15px !important; font-weight: 600 !important;
    color: #475569 !important;
    padding: 14px 20px !important;
    position: relative !important;
    border-bottom: 3px solid transparent !important;
    transition: color .15s ease, border-color .15s ease, background .15s ease;
  }
  article > .tabs .tab:not(.active):hover {
    color: #1e293b !important; background: #f8fafc !important;
  }
  /* 활성 탭: 유형별 색상 (월세=초록, 전세=파랑, 매매=주황) */
  article > .tabs .tab.active {
    font-size: 16px !important; font-weight: 700 !important;
    background: transparent !important;
  }
  article > .tabs .tab.active[data-tab="월세"] {
    color: #059669 !important; border-bottom-color: #059669 !important;
  }
  article > .tabs .tab.active[data-tab="전세"] {
    color: #2563eb !important; border-bottom-color: #2563eb !important;
  }
  article > .tabs .tab.active[data-tab="매매"] {
    color: #ea580c !important; border-bottom-color: #ea580c !important;
  }

  /* 평형 칩 호버 */
  article > .pyeong-wrap .pyeong-btn {
    cursor: pointer !important;
    transition: background .15s ease, border-color .15s ease, transform .12s ease;
  }
  article > .pyeong-wrap .pyeong-btn:not(.active):hover {
    background: #eef2ff !important;
    border-color: #c7d2fe !important;
    transform: translateY(-1px);
  }

  /* 주변 단지 카드 호버 — 강화 */
  article .nearby-item {
    transition: background .18s ease, transform .18s ease, box-shadow .18s ease, border-color .18s ease !important;
    cursor: pointer;
  }
  article .nearby-item:hover {
    background: #ffffff !important;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(15,23,42,0.10);
    border-color: #c7d2fe !important;
  }

  /* 실거래 거래 목록 — 주변 단지와 100% 동일 (카드 + 호버) */
  /* display 는 !important 빼야 인라인 style="display:none" (탭 숨김) 가 동작 */
  article table.trade-list { display: flex; flex-direction: column; gap: 8px; }
  article table.trade-list tbody { display: flex; flex-direction: column; gap: 8px; width: 100%; }
  article .trade-item {
    background: var(--surface) !important;
    border: 1px solid transparent !important;
    border-left: none !important;
    border-bottom: none !important;
    border-radius: var(--radius) !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important;
    padding: 14px !important;
    transition: background .18s ease, transform .18s ease, box-shadow .18s ease, border-color .18s ease !important;
    cursor: default;
  }
  article .trade-item:hover {
    background: #ffffff !important;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(15,23,42,0.10);
    border-color: #c7d2fe !important;
  }
  article .trade-item .trade-price {
    font-size: 14px !important; font-weight: 600 !important;
  }
  article .trade-item .trade-detail {
    font-size: 11.5px !important; color: #94a3b8 !important;
  }
  article .trade-item .trade-date {
    font-size: 11.5px !important; color: #94a3b8 !important;
  }

  /* 가격카드: 우측(5년 최고)은 빨강 강조 + 호버 인터랙션 */
  article .price-card {
    transition: border-color .15s ease, background .15s ease, box-shadow .15s ease, transform .12s ease !important;
    cursor: default;
  }
  /* 왼쪽 primary: 호버 시 파란 border 살짝 강조 */
  article .price-card.primary:hover {
    box-shadow: 0 4px 12px rgba(99,102,241,0.12);
    transform: translateY(-1px);
  }
  /* 오른쪽 secondary: 빨강 수치 + 호버 시 빨강 border 강조 */
  article .price-card.secondary .price-card-value {
    color: #dc2626 !important;
  }
  article .price-card.secondary {
    border: 1px solid #fee2e2 !important;
    background: #fef7f7 !important;
  }
  article .price-card.secondary:hover {
    border-color: #dc2626 !important;
    background: #fef2f2 !important;
    box-shadow: 0 4px 12px rgba(220,38,38,0.12);
    transform: translateY(-1px);
  }
  article > .tabs { font-size: 15px !important; }
  article > #area-price-cards .price-card-value { font-size: 24px !important; }
  article > .chart-section { padding: 0 8px; }
  article > .section { padding: 20px 8px !important; }
  article > p.seo-text { margin: 0 24px 16px !important; font-size: 13px !important; line-height: 1.85 !important; }
  article > .seo-section { padding: 24px !important; }
  body { padding-bottom: 40px; }
}
</style>
<script>
(function(){
  // PC + 모바일 모두 D 디자인 JS 적용 (미디어 가드 해제)
  function enrichHeaderSub() {
    const sub = document.querySelector('header.header .header-sub');
    if (!sub || sub.dataset.enriched) return;
    const bodyText = (document.querySelector('p.seo-text')?.textContent || '') +
                     ' ' + (document.querySelector('.faq-section')?.textContent || '');
    const year = bodyText.match(/(\d{4})년 준공/)?.[1];
    const units = bodyText.match(/총 (\d[\d,]*)호/)?.[1];
    const floors = bodyText.match(/지상 (\d+)층/)?.[1] || bodyText.match(/최고 (\d+)층/)?.[1];
    const parts = [sub.textContent.trim().replace(/· \d{4}년$/, '').trim(), '오피스텔'];
    if (year) parts.push(`${year}년 준공`);
    if (units) parts.push(`${units}세대`);
    if (floors) parts.push(`지상 ${floors}층`);
    sub.textContent = parts.filter(Boolean).join(' · ');
    sub.dataset.enriched = '1';
  }
  // 헤더 오른쪽 "최근 매매" 가격 하이라이트
  function injectHeaderPrice() {
    const ht = document.querySelector('header.header .header-top');
    if (!ht || ht.querySelector('.header-price')) return;
    const pcEl = document.querySelector('#area-price-cards .price-card.primary');
    if (!pcEl) return;
    const label = pcEl.querySelector('.price-card-label')?.textContent?.trim() || '최근 매매';
    const value = pcEl.querySelector('.price-card-value')?.textContent?.trim();
    const sub = pcEl.querySelector('.price-card-sub')?.textContent?.trim();
    if (!value || value === '-') return;
    const box = document.createElement('div');
    box.className = 'header-price';
    const valCls = label.includes('전세') ? 'jeonse' : '';
    box.innerHTML = `
      <div class="header-price-label">${label}</div>
      <div class="header-price-value ${valCls}">${value}</div>
      ${sub ? `<div class="header-price-sub">${sub}</div>` : ''}
    `;
    ht.appendChild(box);
  }
  // 실거래가 차트: 최고점(빨강) + 최근점(파랑) 하이라이트 + 카드 호버 연동
  function patchPriceChart() {
    if (!window.renderPriceChart || window.__patched_price_chart) return;
    window.__patched_price_chart = true;
    const orig = window.renderPriceChart;
    window.renderPriceChart = function(kind) {
      orig.call(this, kind);
      // 차트 초기화 완료 후 적용 (requestAnimationFrame 으로 Chart.getChart 준비 보장)
      requestAnimationFrame(() => applyHighlights(null));
    };
  }
  function applyHighlights(pulseTarget = null) {
    // pulseTarget: 'max' | 'recent' | null
    // Chart.js의 getChart(canvas) 사용 — 전역 let priceChart 는 window 에 안 붙어있음
    const canvas = document.getElementById('priceChart');
    const chart = canvas && (typeof Chart !== 'undefined') ? Chart.getChart(canvas) : null;
    if (!chart || !chart.data || !chart.data.datasets || !chart.data.datasets[0]) return;
    const ds = chart.data.datasets[0];
    if (!ds.data.length) return;
    let maxIdx = 0, recentIdx = 0;
    ds.data.forEach((p, i) => {
      if (Number(p.y) > Number(ds.data[maxIdx].y)) maxIdx = i;
      if (String(p.x) > String(ds.data[recentIdx].x)) recentIdx = i;
    });
    const defaultBg = 'rgba(245,200,66,0.7)';
    ds.backgroundColor = ds.data.map((_, i) =>
      i === maxIdx ? '#dc2626' : i === recentIdx ? '#6366f1' : defaultBg);
    ds.borderColor = ds.data.map((_, i) =>
      (i === maxIdx || i === recentIdx) ? '#fff' : '#f5c842');
    ds.borderWidth = ds.data.map((_, i) =>
      (i === maxIdx || i === recentIdx) ? 2 : 1);
    // 고정 크기: 최고/최근 8px, 나머지 5px — 펄스 없음
    ds.pointRadius = ds.data.map((_, i) =>
      (i === maxIdx || i === recentIdx) ? 8 : 5);
    chart.update('none');
  }
  function bindCardHover() {
    document.addEventListener('mouseenter', (e) => {
      const card = e.target.closest && e.target.closest('.price-card');
      if (!card) return;
      const target = card.classList.contains('secondary') ? 'max' :
                     card.classList.contains('primary') ? 'recent' : null;
      applyHighlights(target);
    }, true);
    document.addEventListener('mouseleave', (e) => {
      const card = e.target.closest && e.target.closest('.price-card');
      if (!card) return;
      applyHighlights(null);
    }, true);
  }
  // 지하철/학교 태그를 헤더에서 꺼내 별도 섹션으로 재조립
  function extractLocationSection() {
    const header = document.querySelector('header.header');
    if (!header || document.querySelector('.location-section')) return;
    const tagLines = header.querySelectorAll('.tag-line');
    if (!tagLines.length) return;
    const subway = [], school = [];
    tagLines.forEach((tl, idx) => {
      if (idx === 0) {
        tl.querySelectorAll('.station-tag').forEach(t => {
          const line = t.querySelector('.line-badge')?.textContent?.trim() || '';
          const name = t.querySelector('.station-name')?.textContent?.trim() || '';
          const time = t.querySelector('.station-time')?.textContent?.trim() || '';
          if (name) subway.push({line, name, time});
        });
      } else {
        tl.querySelectorAll('.school-tag').forEach(s => {
          const spans = s.querySelectorAll('span');
          const typ = spans[0]?.textContent?.trim() || '';
          const name = spans[1]?.textContent?.trim() || '';
          const time = spans[2]?.textContent?.trim() || '';
          if (name) school.push({typ, name, time});
        });
      }
    });
    // 도보 15분(약 1.2km) 이내만 — "N분" 텍스트에서 int 파싱
    function walkMin(s) {
      const m = (s || '').match(/(\d+)\s*분/);
      return m ? parseInt(m[1], 10) : 999;
    }
    const subwayNear = subway.filter(s => walkMin(s.time) <= 15);
    // 지하철: 같은 호선 중복 제거 (가까운 것 우선)
    const seenLines = new Set();
    const subwayDedup = [];
    for (const s of subwayNear) {
      if (seenLines.has(s.line)) continue;
      seenLines.add(s.line);
      subwayDedup.push(s);
    }
    const subwayFinal = subwayDedup;
    // 학교: 도보 15분 이내 + 완전 중복 제거
    const schoolNear = school.filter(s => walkMin(s.time) <= 15);
    const seenNames = new Set();
    const schoolDedup = [];
    for (const s of schoolNear) {
      const key = s.typ + ':' + s.name;
      if (seenNames.has(key)) continue;
      seenNames.add(key);
      schoolDedup.push(s);
    }
    subway.length = 0; subway.push(...subwayFinal);
    school.length = 0; school.push(...schoolDedup);
    if (!subway.length && !school.length) return;
    // 서울·수도권 지하철 호선별 색 — 톤다운 (채도 ↓, 명도 ↑)
    const LINE_COLORS = {
      '1호선': '#5A85B8', '2호선': '#5BB87E', '3호선': '#E8A06A', '4호선': '#5DAFCC',
      '5호선': '#A693B5', '6호선': '#C49679', '7호선': '#9AA053', '8호선': '#D87099',
      '9호선': '#C5BDA5',
      '경의중앙선': '#9DCDB6', '수인분당선': '#D4B370', '신분당선': '#C57085',
      '공항철도': '#6FA9C8', 'GTX-A': '#A56BA5', '우이신설선': '#C4D26C',
      '신림선': '#8FA6C6', '경춘선': '#6BA897', '김포골드라인': '#B89866',
      '인천1호선': '#A0BCD3', '인천2호선': '#E0A06A',
    };
    function lineColor(line) {
      if (!line) return '#64748b';
      for (const k of Object.keys(LINE_COLORS)) {
        if (line.includes(k)) return LINE_COLORS[k];
      }
      return '#64748b';
    }
    const sec = document.createElement('div');
    sec.className = 'location-section';
    const rows = [];
    if (subway.length) {
      const items = subway.map(s => {
        const tip = `${s.line} ${s.name} 도보 ${s.time}`.replace(/"/g, '&quot;');
        return `<span class="loc-item" title="${tip}"><span class="line-badge" style="background:${lineColor(s.line)};">${s.line}</span><span class="nm">${s.name}</span><span class="mn">${s.time}</span></span>`;
      }).join('');
      rows.push(`<div class="loc-row"><div class="loc-items">${items}</div></div>`);
    }
    if (school.length) {
      const items = school.map(s => {
        const tip = `${s.typ} ${s.name} 도보 ${s.time}`.replace(/"/g, '&quot;');
        const cls = s.typ === '초' ? ' type-elem' : s.typ === '중' ? ' type-mid' : s.typ === '고' ? ' type-high' : '';
        return `<span class="loc-item" title="${tip}"><span class="type-badge${cls}">${s.typ}</span><span class="nm">${s.name}</span><span class="mn">${s.time}</span></span>`;
      }).join('');
      rows.push(`<div class="loc-row"><div class="loc-items">${items}</div></div>`);
    }
    sec.innerHTML = rows.join('');
    // PC/모바일 통일: 헤더 우측 컬럼으로 (D 디자인)
    header.appendChild(sec);
  }

  function run() {
    enrichHeaderSub();
    extractLocationSection();
    patchPriceChart();
    bindCardHover();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else { run(); }
})();
</script>
"""
