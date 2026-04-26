"""officetel_design_d.py — 오피스텔 단지 페이지 D 디자인 JS 보강 단일 소스.

- 베이스 CSS는 /officetel/style.css 로 분리 (2026-04-26).
- 이 파일은 Pretendard preload + JS 보강만 담당.
  * enrichHeaderSub: 헤더 sub 풍부화 (준공년·세대수·층수)
  * extractLocationSection: tag-line → location-section (지하철/학교 카드)
  * patchPriceChart / applyHighlights: 차트 최고/최근점 하이라이트
  * bindCardHover: 가격카드 호버 → 차트 연동
"""

DESIGN_D_BLOCK = r"""
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" as="style" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<script>
(function(){
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
  function patchPriceChart() {
    if (!window.renderPriceChart || window.__patched_price_chart) return;
    window.__patched_price_chart = true;
    const orig = window.renderPriceChart;
    window.renderPriceChart = function(kind) {
      orig.call(this, kind);
      requestAnimationFrame(() => applyHighlights(null));
    };
  }
  function applyHighlights(pulseTarget = null) {
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
    function walkMin(s) {
      const m = (s || '').match(/(\d+)\s*분/);
      return m ? parseInt(m[1], 10) : 999;
    }
    const subwayNear = subway.filter(s => walkMin(s.time) <= 15);
    const seenLines = new Set();
    const subwayDedup = [];
    for (const s of subwayNear) {
      if (seenLines.has(s.line)) continue;
      seenLines.add(s.line);
      subwayDedup.push(s);
    }
    const schoolNear = school.filter(s => walkMin(s.time) <= 15);
    const seenNames = new Set();
    const schoolDedup = [];
    for (const s of schoolNear) {
      const key = s.typ + ':' + s.name;
      if (seenNames.has(key)) continue;
      seenNames.add(key);
      schoolDedup.push(s);
    }
    subway.length = 0; subway.push(...subwayDedup);
    school.length = 0; school.push(...schoolDedup);
    if (!subway.length && !school.length) return;
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
