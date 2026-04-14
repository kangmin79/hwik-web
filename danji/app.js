const sb = supabase.createClient(HWIK_CONFIG.SUPABASE_URL, HWIK_CONFIG.SUPABASE_KEY);
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

let DATA = null;
let currentTab = '매매';
let currentPyeong = null;

// makeSlug → /makeSlug.js (외부 파일)
let chart = null;
let volumeChart = null;

// ── 유틸 ──
function esc(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

function formatPrice(manwon) {
  if (!manwon) return '-';
  const uk = Math.floor(manwon / 10000);
  const rest = manwon % 10000;
  if (uk > 0 && rest > 0) {
    const cheon = Math.floor(rest / 1000);
    return cheon > 0 ? `${uk}억 ${cheon}천` : `${uk}억 ${rest}`;
  }
  if (uk > 0) return `${uk}억`;
  return `${manwon.toLocaleString()}만`;
}

function distText(m) {
  if (!m) return '';
  return m >= 1000 ? (m/1000).toFixed(1) + 'km' : m + 'm';
}

// 거래유형 뱃지 (직거래: 주황 / 중개거래: 파랑)
function kindBadge(kind) {
  if (!kind) return '';
  const isDirect = kind === '직거래';
  const bg = isDirect ? '#fef3c7' : '#dbeafe';
  const fg = isDirect ? '#92400e' : '#1e40af';
  return `<span style="display:inline-block;background:${bg};color:${fg};font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;margin-left:6px;vertical-align:middle;line-height:1.4;">${kind}</span>`;
}

function walkMin(m) {
  if (!m) return '';
  return Math.round(m / 67) + '분'; // 도보 평균 80m/분 → 67m/분 보수적
}

// ── 404 처리 (진짜로 DB에 없는 경우만) ──
// 1) noindex 즉시 주입 (Google 1차 렌더링에서 색인 방지)
// 2) 404.html로 리다이렉트 (Google 2차 렌더링에서 HTTP 404 확인)
function markAsNotFound() {
  var robots = document.querySelector('meta[name="robots"]');
  if (!robots) { robots = document.createElement('meta'); robots.name = 'robots'; document.head.appendChild(robots); }
  robots.content = 'noindex,nofollow';
  document.title = '페이지를 찾을 수 없습니다 - 휙';
  location.replace('/404.html');
}

// ── 정적 HTML 의 주변 단지 href 캡처 (id → href) ──
// build_danji_pages.py 가 DB address 필드로 정확하게 생성한 정적 slug 를
// render() 재렌더링 과정에서 잃지 않도록, 로드 시점에 미리 수집.
// n.location 에 구(區)가 누락된 케이스(예: "수원시 정자동")에서 runtime makeSlug
// 가 구를 빠뜨려 404 URL 을 만드는 것을 방지.
const STATIC_NEARBY_HREF = {};
(function captureStaticNearbyHref() {
  try {
    document.querySelectorAll('.nearby-item, a[href^="/danji/"]').forEach(function(el) {
      var h = el.getAttribute('href') || '';
      if (!h.startsWith('/danji/')) return;
      // id 추출: -a숫자 또는 apt-/offi- 접미사
      var decoded = h;
      try { decoded = decodeURIComponent(h); } catch (e) {}
      var m1 = decoded.match(/-(a\d+)(?:\.html)?$/);
      var m2 = decoded.match(/((?:offi|apt)-[^/]+?)(?:\.html)?$/);
      var nid = (m1 && m1[1]) || (m2 && m2[1]);
      if (nid && !STATIC_NEARBY_HREF[nid]) STATIC_NEARBY_HREF[nid] = h;
    });
  } catch (e) {}
})();

// ── 데이터 로드 ──
async function loadData() {
  // location.pathname 은 한글이 percent-encoded 로 반환되므로 디코드 후 매칭
  // (apt-/offi- 접미사에 한글이 포함된 ID가 0 rows 로 귀결되는 것 방지)
  let _path = location.pathname;
  try { _path = decodeURIComponent(_path); } catch (e) {}
  const id = new URLSearchParams(location.search).get('id')
    || (_path.match(/-(a\d+)(?:\.html)?$/) || [])[1]
    || (_path.match(/((?:offi|apt)-[^/]+?)(?:\.html)?$/) || [])[1]
    || null;
  if (!id) { markAsNotFound(); return; }

  let data, error;
  try {
    const res = await sb.from('danji_pages').select('id,complex_name,location,address,build_year,total_units,categories,recent_trade,all_time_high,jeonse_rate,price_history,nearby_subway,nearby_school,nearby_complex,active_listings,lat,lng,top_floor,parking,heating,builder,mgmt_fee,pyeongs_map,seo_text,updated_at').eq('id', id).single();
    data = res.data;
    error = res.error;
  } catch (e) {
    // 네트워크 오류 등 → 멀쩡한 페이지를 noindex하지 않도록 일반 에러 표시
    showError('일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.');
    return;
  }

  // PGRST116 = "no rows returned" (진짜 없음) → 404
  if (error && error.code === 'PGRST116') { markAsNotFound(); return; }
  // 그 외 에러(네트워크/권한 등) → 일반 에러 (noindex 안 함)
  if (error) { showError('단지 정보를 불러올 수 없습니다.'); return; }
  // data가 빈 경우(이론상 .single()에선 안 나오지만 방어)
  if (!data) { markAsNotFound(); return; }

  DATA = data;

  // SEO 메타 업데이트
  document.title = `${data.complex_name} 실거래가 시세 - 휙`;
  const desc = `${data.complex_name} ${data.location} ${data.total_units}세대 ${data.build_year}년 아파트 실거래가, 전세가, 시세 추이`;
  document.getElementById('og-title').content = document.title;
  document.getElementById('og-desc').content = desc;
  document.getElementById('tw-title').content = document.title;
  document.getElementById('tw-desc').content = desc;
  document.querySelector('meta[name="description"]').content = desc;
  // slug 생성은 전역 makeSlug() 사용
  const danjiSlug = makeSlug(data.complex_name, data.location, id, data.address);
  const danjiCanonical = `https://hwik.kr/danji/${encodeURIComponent(danjiSlug)}`;
  // og:url 업데이트
  const ogUrl = document.getElementById('og-url');
  if (ogUrl) ogUrl.content = danjiCanonical;
  // canonical 재확인 (초기 inline script가 이미 주입했지만, 없으면 추가)
  let canonicalEl = document.getElementById('canonical');
  if (!canonicalEl) {
    canonicalEl = document.createElement('link');
    canonicalEl.rel = 'canonical';
    canonicalEl.id = 'canonical';
    document.head.appendChild(canonicalEl);
  }
  canonicalEl.href = danjiCanonical;

  // 거래 데이터 있는 면적 중 84㎡에 가장 가까운 것 선택
  const cats = data.categories || [];
  const rt = data.recent_trade || {};
  const catsWithTrade = cats.filter(c => rt[c] && rt[c].price);
  if (catsWithTrade.length > 0) {
    let best = catsWithTrade[0], bestDiff = 999;
    catsWithTrade.forEach(c => { const d = Math.abs(parseInt(c) - 84); if (d < bestDiff) { bestDiff = d; best = c; } });
    currentPyeong = best;
  } else if (cats.length > 0) {
    // 거래 데이터 없으면 전체 중 84㎡에 가장 가까운 것
    let best = cats[0], bestDiff = 999;
    cats.forEach(c => { const d = Math.abs(parseInt(c) - 84); if (d < bestDiff) { bestDiff = d; best = c; } });
    currentPyeong = best;
  }

  render();
  setupMapLazyLoad();
}

// ── 카카오 지도 lazy load (Intersection Observer) ──
// 사용자가 지도 영역에 스크롤했을 때만 SDK 400KB 로드
function _doInitMap() {
  const el = document.getElementById('danji-map');
  if (!el || !DATA.lat || !DATA.lng) return;
  const center = new kakao.maps.LatLng(DATA.lat, DATA.lng);
  const map = new kakao.maps.Map(el, { center, level: 4 });
  new kakao.maps.Marker({ map, position: center });
  map.setDraggable(false);
  map.setZoomable(false);
}
function _loadMapSdk() {
  if (window.kakao && window.kakao.maps) { kakao.maps.load(_doInitMap); return; }
  const s = document.createElement('script');
  s.src = `//dapi.kakao.com/v2/maps/sdk.js?appkey=${HWIK_CONFIG.KAKAO_JS_KEY}&autoload=false`;
  s.onload = () => kakao.maps.load(_doInitMap);
  document.head.appendChild(s);
}
function setupMapLazyLoad() {
  if (!DATA || !DATA.lat || !DATA.lng) return;
  const el = document.getElementById('danji-map');
  if (!el) return;
  if (!('IntersectionObserver' in window)) { _loadMapSdk(); return; } // 구형 브라우저 fallback
  const obs = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) {
      obs.disconnect();
      _loadMapSdk();
    }
  }, { rootMargin: '200px' }); // 200px 전에 미리 로드
  obs.observe(el);
}

// ── 렌더링 ──
function render() {
  window._danjiHighlight = null; // 탭/평형 변경 시 하이라이트 초기화
  const d = DATA;
  if (!d) return;

  const cats = d.categories || [];
  const recent = d.recent_trade || {};
  const high = d.all_time_high || {};
  const subway = d.nearby_subway || [];
  const school = d.nearby_school || [];
  const nearby = d.nearby_complex || [];
  const listings = d.active_listings || [];

  // 지하철/학교 태그
  function shortSchool(n) { return n.replace(/서울/g,'').replace(/초등학교/g,'초').replace(/중학교/g,'중').replace(/고등학교/g,'고'); }
  function lineColor(line) {
    if (!line) return '#888';
    const l = line.replace(/수도권\s+도시철도\s*/,'').replace(/서울\s+도시철도\s*/,'').replace(/수도권\s+광역철도\s*/,'').replace(/수도권\s+경량도시철도\s*/,'');
    // 1~9호선
    const numColors = {'1호선':'#0052A4','2호선':'#00A84D','3호선':'#EF7C1C','4호선':'#00A5DE','5호선':'#996CAC','6호선':'#CD7C2F','7호선':'#747F00','8호선':'#E6186C','9호선':'#BDB092'};
    if (numColors[l]) return numColors[l];
    // 광역/신설 노선
    if (l.includes('경의') || l.includes('중앙')) return '#77C4A3';
    if (l.includes('분당') || l.includes('수인')) return '#F5A200';
    if (l.includes('신분당')) return '#D4003B';
    if (l.includes('우이')) return '#B7C452';
    if (l.includes('경춘')) return '#0C8E72';
    if (l.includes('공항') || l.includes('인천국제')) return '#0090D2';
    if (l.includes('신림')) return '#6789CA';
    if (l.includes('서해')) return '#8BC53F';
    if (l.includes('경강')) return '#0054A6';
    if (l.includes('김포')) return '#AD8602';
    if (l.includes('에버라인')) return '#56AD2D';
    if (l.includes('의정부')) return '#FDA600';
    if (l.includes('안산') || l.includes('과천')) return '#00A5DE';
    // KTX/일반철도
    if (l.includes('경부') || l.includes('경원') || l.includes('경인') || l.includes('코레일')) return '#144278';
    if (l.includes('동해') || l.includes('대경')) return '#144278';
    // 지방 도시철도
    if (l.includes('부산')) return '#F06A00';
    if (l.includes('대구')) return '#D93F5A';
    if (l.includes('대전')) return '#00B5B5';
    if (l.includes('광주')) return '#009088';
    if (l.includes('인천')) return '#7CA8D5';
    return '#888';
  }
  function shortLine(line) {
    if (!line) return '';
    return line.replace(/수도권\s+도시철도\s*/,'').replace(/서울\s+도시철도\s*/,'').replace(/수도권\s+광역철도\s*/,'').replace(/수도권\s+경량도시철도\s*/,'').replace(/부산\s+도시철도\s*/,'부산 ').replace(/대구\s+도시철도\s*/,'대구 ').replace(/대전\s+도시철도\s*/,'대전 ').replace(/광주도시철도\s*/,'광주 ').replace(/부산\s+경량도시철도\s*/,'부산 ').replace(/인천국제공항선/,'공항').replace('호선','');
  }
  let tagHtml = '';
  if (subway.length > 0) {
    const subwayItems = subway.map(s => {
      const ln = shortLine(s.line);
      const bg = lineColor(s.line);
      return `<span class="station-tag"><span class="line-badge" style="background:${bg}">${esc(ln)}</span><span class="station-name">${esc(s.name)}</span> <span class="station-time">${walkMin(s.distance)}</span></span>`;
    }).join('<span class="tag-sep">·</span>');
    tagHtml += `<div class="tag-line">${subwayItems}</div>`;
  }
  if (school.length > 0) {
    function schoolColor(type) {
      if (!type) return { bg: '#f3f4f6', text: '#6b7280' };
      if (type.includes('초등')) return { bg: '#dcfce7', text: '#16a34a' };
      if (type.includes('중학')) return { bg: '#dbeafe', text: '#2563eb' };
      if (type.includes('고등')) return { bg: '#ede9fe', text: '#7c3aed' };
      return { bg: '#f3f4f6', text: '#6b7280' };
    }
    function schoolLabel(type) {
      if (!type) return '학';
      if (type.includes('초등')) return '초';
      if (type.includes('중학')) return '중';
      if (type.includes('고등')) return '고';
      return '학';
    }
    const schoolItems = school.slice(0,3).map(s => {
      const bg = schoolColor(s.type);
      const label = schoolLabel(s.type);
      return `<span class="station-tag"><span class="line-badge" style="background:${bg.bg};color:${bg.text}">${label}</span><span class="station-name">${shortSchool(esc(s.name))}</span> <span class="station-time">${walkMin(s.distance)}</span></span>`;
    }).join('<span class="tag-sep">·</span>');
    tagHtml += `<div class="tag-line tag-school-line">${schoolItems}</div>`;
  }

  // 전용/공급 토글 + 면적 버튼
  const pm = d.pyeongs_map || {};
  const catsSet = new Set(cats);
  // pm 전체 키를 exclu 기준으로 정렬 (거래 없는 면적도 탭 표시)
  const allPmCats = Object.keys(pm).sort((a, b) => (pm[a].exclu || parseFloat(a)) - (pm[b].exclu || parseFloat(b)));
  const tabCats = allPmCats.length > 0 ? allPmCats : cats;
  const hasCurData = catsSet.has(currentPyeong);
  const hasSupplyData = tabCats.some(c => pm[c] && pm[c].supply && pm[c].supply > 0 && Math.abs((pm[c].exclu || 0) - parseFloat(c)) <= 10);
  const toggleRowHtml = hasSupplyData
    ? `<div style="font-size:11px;color:var(--sub);padding:6px 16px 0;">공급면적 기준</div>`
    : `<div style="font-size:11px;color:var(--sub);padding:6px 16px 0;">전용면적 기준</div>`;
  const pyeongHtml = tabCats.map(c => {
    const active = c === currentPyeong ? ' active' : '';
    const hasData = catsSet.has(c);
    let label;
    if (pm[c] && pm[c].supply && pm[c].supply > 0 && Math.abs((pm[c].exclu || 0) - parseFloat(c)) <= 10) {
      label = pm[c].supply.toFixed(1) + '㎡';
    } else {
      label = c + '㎡';
    }
    const dimStyle = !hasData ? ' style="opacity:0.4;"' : '';
    return `<div class="pyeong-btn${active}" data-cat="${esc(c)}"${dimStyle}>${esc(label)}</div>`;
  }).join('');

  // 현재 평형 기준 지표 (currentPyeong이 null이면 빈 키로 처리)
  const tradeKey = currentPyeong || '';
  const jeonseKey = currentPyeong ? currentPyeong + '_jeonse' : '';
  const wolseKey = currentPyeong ? currentPyeong + '_wolse' : '';

  let recentData, highData;
  if (currentTab === '매매') {
    recentData = recent[tradeKey];
    highData = high[tradeKey];
  } else if (currentTab === '전세') {
    recentData = recent[jeonseKey];
    highData = high[jeonseKey];
  } else {
    recentData = recent[wolseKey];
    highData = null;
  }

  const recentPrice = recentData ? recentData.price : null;
  const highPrice = highData ? highData.price : null;

  // 전세가율
  const jeonseData = recent[jeonseKey];
  const saleData = recent[tradeKey];
  let jeonseRate = d.jeonse_rate;
  if (jeonseData && saleData && saleData.price > 0) {
    jeonseRate = Math.round(jeonseData.price / saleData.price * 1000) / 10;
  }

  // 지표 변화량 (최근 5년 최고 대비 금액 + %)
  // 최근 거래가 직거래면 시장가 왜곡 가능성이 커서 하락률 대신 주의 문구만 표시
  let changeHtml = '';
  if (recentPrice && highPrice) {
    if (recentData && recentData.kind === '직거래') {
      changeHtml = `<div class="price-card-change neutral" style="color:#92400e;">최근 거래는 직거래 — 시세 해석 주의</div>`;
    } else {
      const diff = recentPrice - highPrice;
      const pct = Math.round(Math.abs(diff) / highPrice * 1000) / 10;
      if (diff < 0) changeHtml = `<div class="price-card-change down">최고 대비 -${formatPrice(Math.abs(diff))}(${pct}%)</div>`;
      else if (diff > 0) changeHtml = `<div class="price-card-change up">최고가 경신</div>`;
      else changeHtml = `<div class="price-card-change neutral">최고가 동일</div>`;
    }
  }

  // 최근 거래 목록 (현재 선택 평형 + 탭 기준)
  const tradeKeyFull = currentPyeong + (currentTab === '전세' ? '_jeonse' : (currentTab === '월세' ? '_wolse' : ''));
  const ph = (d.price_history || {})[tradeKeyFull] || [];
  let pyLabel = '';
  if (currentPyeong) {
    const _pm = pm[currentPyeong];
    if (_pm && _pm.supply && _pm.supply > 0 && Math.abs((_pm.exclu || 0) - parseFloat(currentPyeong)) <= 10) {
      pyLabel = '공급 ' + _pm.supply.toFixed(1) + '㎡';
    } else {
      pyLabel = '전용 ' + currentPyeong + '㎡';
    }
  }

  // price_history에 개별 거래가 있으면 그걸 사용
  let tradeItems = [];
  if (ph.length > 0 && ph[0].date) {
    tradeItems = ph.slice().sort((a,b) => (b.date||'').localeCompare(a.date||''));
  } else {
    // 폴백: recent_trade에서 현재 키만
    const val = recent[tradeKeyFull];
    if (val) tradeItems = [val];
  }

  const tradeListHtml = tradeItems.slice(0,5).map(t => {
    let priceDisplay;
    if (currentTab === '월세' && t.monthly) {
      priceDisplay = `보증금 ${formatPrice(t.price)} / 월 ${t.monthly}만`;
    } else {
      priceDisplay = formatPrice(t.price);
    }
    return `
    <div class="trade-item">
      <div>
        <div class="trade-price">${priceDisplay}</div>
        <div class="trade-detail">${pyLabel}${t.floor ? ' · ' + t.floor + '층' : ''}${kindBadge(t.kind || '')}</div>
      </div>
      <div class="trade-date">${esc(t.date || '')}</div>
    </div>`;
  }).join('');

  // 휙 매물
  const listingCount = {};
  listings.forEach(l => { listingCount[l.type] = (listingCount[l.type]||0) + 1; });
  const listingBadge = Object.entries(listingCount).map(([k,v]) => `${k} ${v}`).join(' · ');
  const listingHtml = listings.slice(0,3).map(l => `
    <div class="listing-item" style="display:flex;flex-direction:column;gap:6px;">
      <a href="/property_view.html?id=${encodeURIComponent(l.id)}" style="text-decoration:none;color:inherit;display:flex;justify-content:space-between;align-items:center;">
        <div>
          <div class="trade-price">${esc(l.type)} ${formatPrice(l.price)}</div>
          <div class="trade-detail">${l.floor ? l.floor+'층' : ''} ${l.area ? '· '+l.area+'㎡' : ''} ${l.move_in ? '· '+esc(l.move_in) : ''}</div>
        </div>
        <div class="listing-link">상세보기</div>
      </a>
      ${l.agent_id ? `<a href="/agent.html?id=${encodeURIComponent(l.agent_id)}" style="font-size:11px;color:var(--sub);text-decoration:none;display:flex;align-items:center;gap:4px;">${l.agent_name ? '담당: '+esc(l.agent_name) : '담당 중개사 보기'} →</a>` : ''}
    </div>
  `).join('');

  // 주변 단지 (현재 선택 평형 기준으로 비교)
  const curArea = currentPyeong ? parseInt(currentPyeong) : 84;
  // 주변 단지 slug용 주소: 부모 주소의 시(市) 부분 + 주변 단지 자체 location(구/동)
  // d.address 그대로 쓰면 부모의 "구"가 씌워져 잘못된 URL 생성됨 (예: 종로구 창신동 → 성북구 창신동)
  const parentMetro = (d.address || '').split(/\s+/)[0] || '';
  const nearbyHtml = nearby.map(n => {
    const prices = n.prices || {};
    // 현재 선택 평형에서 가장 가까운 가격 찾기 (±10㎡ 우선, 없으면 가장 가까운 면적)
    let bestKey = null, bestDiff = 999, bestPrice = null, bestExclu = null, bestSupply = null, bestDate = null;
    for (const k of Object.keys(prices)) {
      const diff = Math.abs(parseInt(k) - curArea);
      if (diff < bestDiff) {
        bestDiff = diff;
        bestKey = k;
        bestPrice = prices[k].price;
        bestExclu = prices[k].exclu || parseInt(k);
        bestSupply = prices[k].supply;
        bestDate = prices[k].date || null;
      }
    }
    // 면적 표시 (전용/공급 토글 반영)
    let areaLabel = '';
    if (bestKey) {
      areaLabel = '전용 ' + bestExclu + '㎡';
    }
    return `
    <a class="nearby-item" href="${STATIC_NEARBY_HREF[n.id] || ('/danji/' + encodeURIComponent(makeSlug(n.name, n.location, n.id, parentMetro && n.location ? (parentMetro + ' ' + n.location) : '')))}" style="text-decoration:none;color:inherit;">
      <div>
        <div class="nearby-name">${esc(n.name)}</div>
        <div class="nearby-sub">${esc(n.location)} ${n.distance ? '· '+distText(n.distance) : ''}${areaLabel ? ' · '+areaLabel : ''}</div>
      </div>
      <div style="text-align:right">
        <div class="nearby-price">${bestPrice ? formatPrice(bestPrice) : '-'}</div>
        ${bestDate ? '<div style="font-size:10px;color:var(--muted);margin-top:2px;">'+esc(bestDate)+'</div>' : ''}
      </div>
    </a>`;
  }).join('');

  // SEO 텍스트 — DB가 아닌 실제 데이터 기반으로 자동 생성
  const seoParts = [];
  // 기본 정보 (확실한 것만)
  const nm = d.complex_name || '';
  const lastCh = nm.charAt(nm.length - 1);
  const hasJong = lastCh >= '가' && lastCh <= '힣' && (lastCh.charCodeAt(0) - 0xAC00) % 28 !== 0;
  const seoBasic = [esc(d.complex_name), hasJong ? '은' : '는'];
  if (d.address) seoBasic.push(esc(d.address) + '에 위치한');
  if (d.build_year) seoBasic.push(d.build_year + '년 준공');
  seoBasic.push('아파트입니다.');
  if (d.total_units) seoBasic.push('총 ' + d.total_units.toLocaleString() + '세대 규모입니다.');
  seoParts.push(seoBasic.join(' '));

  // 단지 스펙 (확실한 것만)
  const specParts = [];
  if (d.top_floor) specParts.push('최고 ' + d.top_floor + '층');
  if (parseInt(d.parking || 0) > 0) {
    specParts.push('주차 ' + parseInt(d.parking).toLocaleString() + '대');
    if (d.total_units) specParts.push('(세대당 ' + (parseInt(d.parking) / d.total_units).toFixed(1) + '대)');
  }
  if (d.heating) specParts.push(d.heating);
  if (d.builder) specParts.push('시공 ' + d.builder);
  if (specParts.length > 0) seoParts.push(specParts.join(', ') + '.');
  if (d.mgmt_fee) seoParts.push('세대당 월 평균 관리비 약 ' + Math.round(d.mgmt_fee/10000) + '만원.');

  // 평형 (DB categories 기반)
  if (cats.length > 0) {
    seoParts.push('보유 면적(전용): ' + cats.join(', ') + '㎡.');
  }

  // 지하철 (DB nearby_subway 기반)
  if (subway.length > 0) {
    const subList = subway.map(s => esc(s.name) + (s.line ? '('+esc(s.line)+')' : '') + ' 도보 ' + walkMin(s.distance));
    seoParts.push('인근 지하철: ' + subList.join(', ') + '.');
  }

  // 학교 (DB nearby_school 기반)
  if (school.length > 0) {
    const schList = school.map(s => esc(s.name) + ' 도보 ' + walkMin(s.distance));
    seoParts.push('인근 학교: ' + schList.join(', ') + '.');
  }

  // 시세 (실제 거래 데이터 기반)
  if (recentPrice) {
    let priceText = '최근 매매 실거래가는 ' + formatPrice(recentPrice);
    if (recentData && recentData.date) priceText += ' (' + recentData.date + ' 기준)';
    priceText += '입니다.';
    seoParts.push(priceText);
  }
  if (highPrice && highData) {
    seoParts.push('최근 5년 최고가는 ' + formatPrice(highPrice) + (highData.date ? ' (' + highData.date + ')' : '') + '입니다.');
  }
  if (jeonseRate) {
    seoParts.push('전세가율은 ' + jeonseRate + '%입니다.');
  }

  const seoFull = seoParts.join(' ');
  const seoShort = seoFull.length > 120 ? seoFull.slice(0,120) : seoFull;
  const seoRest = seoFull.length > 120 ? seoFull.slice(120) : '';

  // 조합
  const locationParts = (d.location || '').split(' ');
  const dong = locationParts.length >= 2 ? locationParts.slice(1).join(' ') : d.location;
  const dongDisplay = locationParts[locationParts.length - 1] || d.location;

  // breadcrumb — 지역명 추출 (전국 17개 시도)
  const guName = locationParts[0] || '';
  const _addrCity = (d.address || '').split(' ')[0] || '';
  const _cityMap = {
    '서울특별시':'서울','인천광역시':'인천','경기도':'경기',
    '부산광역시':'부산','대구광역시':'대구','광주광역시':'광주','대전광역시':'대전','울산광역시':'울산',
    '세종특별자치시':'세종',
    '충청북도':'충북','충청남도':'충남',
    '전라북도':'전북','전라남도':'전남',
    '경상북도':'경북','경상남도':'경남',
    '강원특별자치도':'강원','강원도':'강원',
    '제주특별자치도':'제주','제주도':'제주',
  };
  const _cityLabel = _cityMap[_addrCity] || '';
  // slug 규칙: 서울/경기=접두사 없음, 인천=중구만 예외, 나머지 전체={지역}-{구}
  // _cityLabel 미인식 시 guName만 사용 (서울/경기와 동일 동작, 안전한 fallback)
  const _noPrefixSet = new Set(['서울','경기']);
  const _guSlugBase = guName.replace(/ /g, '-');
  const _guUrlSlug = (!_cityLabel || _noPrefixSet.has(_cityLabel)) ? _guSlugBase
    : (_cityLabel === '인천' && guName === '중구') ? '인천-중구'
    : _cityLabel === '인천' ? _guSlugBase
    : (_cityLabel + '-' + _guSlugBase);

  // FAQ 데이터
  const faqItems = [];
  if (currentTab !== '월세') {
    // 매매/전세: 가격 관련 FAQ
    if (recentPrice) {
      faqItems.push({ q: `${d.complex_name} 최근 실거래가는?`, a: `${d.complex_name} 최근 매매 실거래가는 ${formatPrice(recentPrice)}입니다.${recentData && recentData.date ? ' ('+recentData.date+' 기준)' : ''}` });
      const _supplyInfo = pm && currentPyeong && pm[currentPyeong];
      const _supplyArea = _supplyInfo && _supplyInfo.supply && _supplyInfo.supply > 0 ? _supplyInfo.supply : 0;
      const _excluArea = parseFloat(currentPyeong) || 0;
      if (_supplyArea > 0) {
        faqItems.push({ q: `${d.complex_name} ㎡당 가격은?`, a: `${d.complex_name} ㎡당 가격은 공급면적(${Math.round(_supplyArea)}㎡) 기준 ${formatPrice(Math.round(recentPrice / _supplyArea))}입니다.` });
      } else if (_excluArea > 0) {
        faqItems.push({ q: `${d.complex_name} ㎡당 가격은?`, a: `${d.complex_name} ㎡당 가격은 전용면적(${Math.round(_excluArea)}㎡) 기준 ${formatPrice(Math.round(recentPrice / _excluArea))}입니다.` });
      }
    }
    if (jeonseRate) faqItems.push({ q: `${d.complex_name} 전세가율은?`, a: `${d.complex_name}의 전세가율은 ${jeonseRate}%입니다.` });
    if (highPrice) faqItems.push({ q: `${d.complex_name} 최근 5년 최고가는?`, a: `최근 5년 최고가는 ${formatPrice(highPrice)}입니다.${highData && highData.date ? ' ('+highData.date+')' : ''}` });
  }
  // 매매/전세/월세 공통 FAQ
  if (subway.length > 0) faqItems.push({ q: `${d.complex_name} 근처 지하철역은?`, a: subway.map(s => `<span style="color:${lineColor(s.line)};font-weight:500;">${esc(s.name)}</span>(${esc(shortLine(s.line))}) 도보 ${walkMin(s.distance)}`).join(', '), html: true });
  if (parseInt(d.parking || 0) > 0 && d.total_units) {
    const _ratio = (parseInt(d.parking) / d.total_units).toFixed(1);
    faqItems.push({ q: `${d.complex_name} 주차 대수는?`, a: `총 ${parseInt(d.parking).toLocaleString()}대 (세대당 ${_ratio}대)입니다.` });
  }
  if (d.heating) faqItems.push({ q: `${d.complex_name} 난방 방식은?`, a: `${d.heating}입니다.` });
  if (d.builder) faqItems.push({ q: `${d.complex_name} 시공사는?`, a: `${esc(d.builder)}입니다.` });

  const faqHtml = faqItems.map(f => `
    <div class="faq-item">
      <div class="faq-q">${esc(f.q)}</div>
      <div class="faq-a">${f.html ? f.a : esc(f.a)}</div>
    </div>
  `).join('');

  $('#app').innerHTML = `
    <!-- Breadcrumb -->
    <nav class="breadcrumb" aria-label="breadcrumb">
      <a href="/">휙</a><span>&gt;</span><a href="/gu/${encodeURIComponent(_guUrlSlug)}">${esc(_cityLabel)} ${esc(guName)}</a><span>&gt;</span>${esc(d.complex_name)}
    </nav>

    <!-- 헤더 -->
    <header class="header">
      <div class="header-top">
        <div class="logo">휙</div>
        <div>
          <h1 class="header-name">${esc(d.complex_name)}</h1>
          <div class="header-sub">${esc(d.location)} · ${d.total_units ? d.total_units.toLocaleString()+'세대' : ''} · ${d.build_year || ''}년${d.builder ? ' · '+esc(d.builder) : ''}</div>
        </div>
      </div>
      <div class="tags">${tagHtml}</div>
    </header>

    <!-- 탭 -->
    <div class="tabs">
      <div class="tab${currentTab==='매매'?' active':''}" data-tab="매매">매매</div>
      <div class="tab${currentTab==='전세'?' active':''}" data-tab="전세">전세</div>
      <div class="tab${currentTab==='월세'?' active':''}" data-tab="월세">월세</div>
    </div>

    <!-- 평형 -->
    ${toggleRowHtml}
    <div class="pyeong-wrap"><div class="pyeong-row">${pyeongHtml}</div></div>

    <!-- 핵심 시세 카드 (월세 탭에서는 숨김) -->
    ${!hasCurData ? `<div style="margin:20px 16px;padding:20px;background:var(--card-bg);border-radius:12px;text-align:center;color:var(--sub);font-size:14px;line-height:1.6;">
      <div style="font-size:22px;margin-bottom:8px;">📭</div>
      <div style="font-weight:600;color:var(--text);margin-bottom:4px;">최근 5년 거래 내역 없음</div>
      <div>이 면적은 최근 5년간 실거래 데이터가 없습니다.</div>
    </div>` : ''}
    ${!hasCurData ? '' : currentTab !== '월세' ? `<div class="price-cards">
      <div class="price-card primary" onclick="highlightChartPoint('recent')" style="cursor:pointer;transition:transform .15s,background .15s;" ontouchstart="this.style.transform='scale(.97)';this.style.background='#dbeafe';" ontouchend="this.style.transform='';this.style.background='';">
        <div style="display:flex;justify-content:space-between;align-items:center;"><span class="price-card-label">최근 ${currentTab === '전세' ? '전세가' : '실거래가'}</span>${recentData ? kindBadge(recentData.kind || '') : ''}</div>
        <div class="price-card-value">${recentPrice ? formatPrice(recentPrice) : '-'}</div>
        <div class="price-card-sub">${recentData && recentData.floor ? recentData.floor + '층' : ''}${recentData && recentData.date ? ' · ' + recentData.date : ''}</div>
        ${changeHtml}
      </div>
      <div class="price-card secondary" onclick="highlightChartPoint('high')" style="cursor:pointer;transition:transform .15s,background .15s,border-color .15s;" ontouchstart="this.style.transform='scale(.97)';this.style.background='#fef2f2';this.style.borderColor='#f87171';" ontouchend="this.style.transform='';this.style.background='';this.style.borderColor='';">
        <div style="display:flex;justify-content:space-between;align-items:center;"><span class="price-card-label">최근 5년 최고${currentTab === '전세' ? ' 전세가' : '가'}</span>${highData ? kindBadge(highData.kind || '') : ''}</div>
        <div class="price-card-value">${highPrice ? formatPrice(highPrice) : '-'}</div>
        <div class="price-card-sub">${highData && highData.floor ? highData.floor + '층' : ''}${highData && highData.date ? ' · ' + highData.date : ''}</div>
      </div>
    </div>` : ''}
    ${hasCurData && currentTab !== '월세' ? (() => {
      const cells = [];
      if (jeonseRate) cells.push({label:'전세가율', value:jeonseRate+'%'});
      const supplyInfo = pm[currentPyeong];
      const hasSupply = supplyInfo && supplyInfo.supply && supplyInfo.supply > 0;
      if (hasSupply && recentPrice) {
        const sqmPrice = Math.round(recentPrice / supplyInfo.supply);
        cells.push({label:'㎡당 가격', value:formatPrice(sqmPrice), sub:'공급면적 기준'});
      } else if (d.total_units) {
        cells.push({label:'세대수', value:d.total_units.toLocaleString()+'세대'});
      }
      if (d.top_floor) cells.push({label:'최고층', value:d.top_floor+'층'});
      if (cells.length === 0) return '';
      const gridStyle = cells.length !== 3 ? ` style="grid-template-columns:repeat(${cells.length},1fr)"` : '';
      return `<div class="metrics"${gridStyle}>` + cells.map(c => {
        const fontSize = (c.value && c.value.length > 6) ? ' style="font-size:13px"' : '';
        return '<div class="metric"><div class="metric-label">'+esc(c.label)+'</div><div class="metric-value"'+fontSize+'>'+esc(c.value)+'</div>'+(c.sub ? '<div class="metric-change neutral">'+esc(c.sub)+'</div>' : '')+'</div>';
      }).join('') + '</div>';
    })() : ''}

    <!-- 거래량 + 그래프 (월세 탭 또는 데이터 없는 면적에서는 숨김) -->
    ${hasCurData && currentTab !== '월세' ? `
    <div class="chart-section">
      <div class="chart-title">거래량</div>
      <div style="height:40px;position:relative;"><canvas id="volumeChart"></canvas></div>
      <div class="chart-title" style="margin-top:8px;">실거래가</div>
      <div class="chart-wrap"><canvas id="priceChart"></canvas></div>
    </div>
    ` : ''}

    <!-- 최근 실거래 -->
    ${hasCurData ? `<div class="section">
      <div class="section-title">${currentTab === '월세' ? '최근 월세 거래' : '최근 실거래'}</div>
      <div class="trade-list">${tradeListHtml || '<div style="font-size:12px;color:var(--sub);padding:8px 0;">거래 내역이 없습니다</div>'}</div>
    </div>` : ''}

    <div class="divider"></div>

    <!-- 휙 매물 -->
    <div class="section">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <div class="section-title" style="margin-bottom:0;">휙 등록 매물</div>
        ${listingBadge ? '<div class="listing-badge">'+esc(listingBadge)+'</div>' : ''}
      </div>
      ${listingHtml
        ? '<div class="trade-list">' + listingHtml + '</div>'
        : '<div class="listing-empty"><div class="listing-empty-text">이 단지에 등록된 매물이 아직 없습니다</div><a class="listing-empty-cta" href="/card_generator_v2_auth.html" style="text-decoration:none;">중개사님, 매물을 등록해보세요 →</a></div>'
      }
    </div>

    <div class="divider"></div>

    <!-- 주변 단지 -->
    <div class="section" id="nearby-section">
      <div class="section-title">${esc(dongDisplay)} 주변 단지</div>
      <div style="font-size:11px;color:var(--sub);margin-bottom:12px;margin-top:-6px;" id="nearby-label">${currentTab === '월세' ? '매매가 기준 · ' : ''}전용 ${currentPyeong||'84'}㎡ ±10㎡ 기준</div>
      <div style="display:flex;flex-direction:column;gap:8px;" id="nearby-list">${nearbyHtml || ''}</div>
    </div>

    <!-- FAQ -->
    <div class="faq-section">
      <div class="section-title">자주 묻는 질문</div>
      ${faqHtml}
    </div>

    <div class="divider"></div>

    <!-- 위치 지도 -->
    ${d.lat && d.lng ? `<div class="section" id="map-section">
      <div class="section-title">${esc(d.complex_name)} 위치</div>
      <div id="danji-map" style="width:100%;height:200px;border-radius:8px;overflow:hidden;background:#e5e7eb;"></div>
      <a href="https://map.kakao.com/link/map/${encodeURIComponent(d.complex_name)},${d.lat},${d.lng}" target="_blank" rel="noopener" style="display:block;text-align:right;font-size:12px;color:var(--sub);margin-top:6px;text-decoration:none;">카카오맵에서 보기 →</a>
    </div>
    <div class="divider"></div>` : ''}

    <!-- 내부 링크 (SEO) -->
    <div class="section">
      <div class="section-title">더 알아보기</div>
      <div style="display:flex;flex-direction:column;gap:8px;">
        <a href="/dong/${encodeURIComponent(makeDongSlug(guName, dong, d.address||''))}" style="display:flex;justify-content:space-between;align-items:center;padding:12px 14px;background:var(--card);border-radius:var(--radius);text-decoration:none;color:var(--text);transition:all .15s;">
          <span style="font-size:13px;">${esc(dongDisplay)} 다른 단지 시세</span><span style="color:var(--sub);font-size:12px;">→</span>
        </a>
        <a href="/gu.html?name=${encodeURIComponent(guName)}" style="display:flex;justify-content:space-between;align-items:center;padding:12px 14px;background:var(--card);border-radius:var(--radius);text-decoration:none;color:var(--text);transition:all .15s;">
          <span style="font-size:13px;">${esc(guName)} 전체 시세</span><span style="color:var(--sub);font-size:12px;">→</span>
        </a>
        <a href="/ranking.html" style="display:flex;justify-content:space-between;align-items:center;padding:12px 14px;background:var(--card);border-radius:var(--radius);text-decoration:none;color:var(--text);transition:all .15s;">
          <span style="font-size:13px;">서울 아파트 순위</span><span style="color:var(--sub);font-size:12px;">→</span>
        </a>
      </div>
    </div>

    <div class="divider"></div>

    <!-- CTA -->
    <div class="cta-section">
      <a class="btn-primary" href="/mobile-v6.html" style="display:block;text-align:center;text-decoration:none;">이 단지 매물 전체보기</a>
      <a class="btn-secondary" href="/card_generator_v2_auth.html" style="display:block;text-align:center;text-decoration:none;">공인중개사 서비스 · 무료로 시작하기</a>
    </div>

    <!-- SEO -->
    <div class="seo-section">
      <div class="seo-text">
        ${esc(seoShort)}${seoRest ? '<span id="seoMore" style="display:none;">' + esc(seoRest) + '</span><span class="seo-more" onclick="document.getElementById(\'seoMore\').style.display=\'inline\';this.style.display=\'none\';"> 더보기</span>' : ''}
      </div>
      <details style="font-size:12px;color:var(--sub);margin-top:10px;">
        <summary style="cursor:pointer;">데이터 안내 ▼</summary>
        <div style="margin-top:6px;line-height:1.8;">
          <b>실거래가</b>: 국토교통부 실거래가 공개시스템 (매일 자동 수집)<br>
          <b>공급면적</b>: 국토교통부 건축물대장 (전용면적 + 주거공용면적)<br>
          공급면적이 확인되지 않은 단지는 전용면적만 표시합니다<br>
          같은 타입도 세대별 실측값 기준으로 면적이 미세하게 다를 수 있습니다<br>
          거래 취소·정정 건은 반영이 지연될 수 있습니다
        </div>
      </details>
      <div class="seo-source" style="margin-top:8px;">실거래가 출처: 국토교통부 · 최종 데이터 확인: ${d.updated_at ? d.updated_at.slice(0,10) : new Date().toISOString().slice(0,10)}</div>
      <div style="margin-top:14px;text-align:center;">
        <button onclick="openReportModal()" style="background:none;border:1px solid var(--border, #e5e7eb);border-radius:20px;color:var(--sub, #6b7280);font-size:12px;cursor:pointer;padding:6px 16px;">🚨 데이터 오류 신고</button>
      </div>
    </div>
  `;

  // 이벤트 바인딩
  $$('.tab').forEach(el => el.addEventListener('click', () => {
    currentTab = el.dataset.tab;
    // 탭 전환 시 현재 탭 기준 데이터 있는 면적으로 재선택
    const suffix = currentTab === '전세' ? '_jeonse' : (currentTab === '월세' ? '_wolse' : '');
    const cats = (DATA && DATA.categories) || [];
    const rt = (DATA && DATA.recent_trade) || {};
    const firstWithTrade = cats.find(c => rt[c + suffix] && (rt[c + suffix].price || rt[c + suffix].monthly));
    if (firstWithTrade) currentPyeong = firstWithTrade;
    render();
  }));
  $$('.pyeong-btn').forEach(el => el.addEventListener('click', () => {
    if (el.dataset.cat) {
      currentPyeong = el.dataset.cat;
      render();
    }
  }));

  // 차트
  drawChart();

  // 주변 단지 부족하면 라이브 쿼리로 채우기
  fillNearbyIfNeeded();
}

// ── 주변 단지 부족 시 위치 기반으로 채우기 ──
async function fillNearbyIfNeeded() {
  const listEl = document.getElementById('nearby-list');
  const labelEl = document.getElementById('nearby-label');
  if (!listEl || !DATA) return;
  const existing = listEl.querySelectorAll('a').length;
  const need = 5 - existing;
  if (need <= 0) return;

  const lat = DATA.lat, lng = DATA.lng;
  if (!lat || !lng) return;

  const R = 0.05; // ~5km 반경 (위도 기준)
  const existingIds = new Set((DATA.nearby_complex || []).map(n => n.id));
  existingIds.add(DATA.id);

  try {
    const res = await sb.from('danji_pages')
      .select('id,complex_name,location,lat,lng,recent_trade,categories')
      .gte('lat', lat - R).lte('lat', lat + R)
      .gte('lng', lng - R * 1.3).lte('lng', lng + R * 1.3)
      .not('id', 'like', 'apt-%').not('id', 'like', 'offi-%')
      .limit(30);

    if (!res.data || !res.data.length) return;

    // 거리 계산 후 정렬, 기존 항목 제외
    const candidates = res.data
      .filter(n => !existingIds.has(n.id) && n.lat && n.lng)
      .map(n => {
        const dlat = n.lat - lat, dlng = (n.lng - lng) * Math.cos(lat * Math.PI / 180);
        return { ...n, dist: Math.sqrt(dlat*dlat + dlng*dlng) * 111 };
      })
      .sort((a, b) => a.dist - b.dist)
      .slice(0, need);

    if (!candidates.length) {
      if (!existing) listEl.innerHTML = '<div style="font-size:12px;color:var(--sub);">주변 단지 정보가 없습니다</div>';
      return;
    }

    const parentMetro = (DATA.address || '').split(/\s+/)[0] || '';
    const html = candidates.map(n => {
      const rt = n.recent_trade || {};
      const cats = n.categories || [];
      // 가격: 어떤 면적이든 가장 최근 매매가
      let price = null, area = null;
      for (const c of cats) {
        if (rt[c] && rt[c].price) { price = rt[c].price; area = c; break; }
      }
      const distKm = n.dist < 1 ? Math.round(n.dist * 1000) + 'm' : n.dist.toFixed(1) + 'km';
      return `<a class="nearby-item" href="/danji/${encodeURIComponent(makeSlug(n.complex_name, n.location, n.id, parentMetro && n.location ? (parentMetro + ' ' + n.location) : ''))}" style="text-decoration:none;color:inherit;">
        <div>
          <div class="nearby-name">${esc(n.complex_name)}</div>
          <div class="nearby-sub">${esc(n.location)} · ${distKm}${area ? ' · 전용 '+area+'㎡' : ''}</div>
        </div>
        <div style="text-align:right"><div class="nearby-price">${price ? formatPrice(price) : '-'}</div></div>
      </a>`;
    }).join('');

    listEl.insertAdjacentHTML('beforeend', html);
    if (labelEl && !existing) labelEl.textContent = '거리순 (면적 무관)';
    else if (labelEl && existing) labelEl.textContent += ' + 거리순';
  } catch(e) {}
}

// ── 차트 (scatter — 점 하나 = 실거래 1건) ──
function drawChart() {
  const canvas = document.getElementById('priceChart');
  if (!canvas) return;

  if (chart) { chart.destroy(); chart = null; }
  if (volumeChart) { volumeChart.destroy(); volumeChart = null; }

  const suffix = currentTab === '전세' ? '_jeonse' : (currentTab === '월세' ? '_wolse' : '');
  const key = currentPyeong + (suffix || '');
  const ph = (DATA.price_history || {})[key] || [];

  let points = [];

  if (ph.length > 0 && ph.some(p => p.date)) {
    points = ph.filter(p => p.date).map(p => ({
      x: p.date,
      y: Math.round(p.price / 100) / 100,
      floor: p.floor || '',
      date: p.date,
      price: p.price,
    }));
  } else if (ph.length > 0 && ph[0].month) {
    points = ph.map(p => ({
      x: p.month + '-15',
      y: Math.round(p.avg_price / 100) / 100,
      floor: '',
      date: p.month,
      price: p.avg_price,
    }));
  }

  if (points.length === 0) {
    const recent = DATA.recent_trade || {};
    for (const [k, v] of Object.entries(recent)) {
      if (k !== key) continue;
      if (v.price && v.date) {
        points.push({
          x: v.date,
          y: Math.round(v.price / 100) / 100,
          floor: v.floor || '',
          date: v.date,
          price: v.price,
        });
      }
    }
  }

  points.sort((a, b) => a.x.localeCompare(b.x));

  if (points.length === 0) {
    canvas.parentElement.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:12px;color:var(--sub);">거래 데이터가 없습니다</div>';
    return;
  }

  const yValues = points.map(p => p.y);
  const min = Math.floor(Math.min(...yValues) * 0.92);
  const max = Math.ceil(Math.max(...yValues) * 1.05);

  // 하이라이트 상태 유지 플러그인 (hover re-render 시 색상 초기화 방지)
  const highlightKeeperPlugin = {
    id: 'highlightKeeper',
    beforeDatasetsDraw(ch) {
      const h = window._danjiHighlight;
      if (!h) return;
      const ds = ch.data.datasets[0];
      ds.backgroundColor = h.colors;
      ds.borderColor = h.borders;
      ds.pointRadius = h.radii;
      ds.borderWidth = h.widths;
    }
  };

  chart = new Chart(canvas, {
    type: 'scatter',
    data: {
      datasets: [{
        data: points.map(p => ({ x: p.x, y: p.y })),
        backgroundColor: 'rgba(245,200,66,0.7)',
        borderColor: '#f5c842',
        borderWidth: 1,
        pointRadius: 5,
        pointHoverRadius: 7,
        pointHoverBackgroundColor: '#f5c842',
      }]
    },
    plugins: [highlightKeeperPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: {
            title: ctx => {
              const now = Date.now();
              if (navigator.vibrate && now - (window._lastVib||0) > 300) { navigator.vibrate(10); window._lastVib = now; }
              const i = ctx[0].dataIndex;
              return points[i].date;
            },
            beforeBody: ctx => {
              const p = points[ctx[0].dataIndex];
              const tabLabel = currentTab || '매매';
              const pyLabel = currentPyeong ? currentPyeong + '㎡' : '';
              const parts = [tabLabel];
              if (pyLabel) parts.push(pyLabel);
              if (p.floor) parts.push(p.floor + '층');
              return parts.join(' · ');
            },
            label: ctx => {
              const p = points[ctx.dataIndex];
              return formatPrice(p.price);
            }
          }
        }
      },
      scales: {
        x: {
          type: 'category',
          labels: [...new Set(points.map(p => p.x))],
          grid: { display: false },
          ticks: {
            font: { size: 10 },
            color: '#aaa',
            maxTicksLimit: 8,
            maxRotation: 0,
            callback: function(val, i) {
              const label = this.getLabelForValue(val);
              if (!label) return '';
              const parts = label.split('-');
              return parts.length >= 2 ? parts[0].slice(2) + '.' + parts[1] : label;
            }
          }
        },
        y: {
          grid: { color: 'rgba(0,0,0,0.05)' },
          ticks: { font: { size: 10 }, color: '#aaa', callback: v => v + '억' },
          min, max
        }
      }
    }
  });

  // ── 거래량 바 차트 ──
  const volCanvas = document.getElementById('volumeChart');
  if (volCanvas && points.length > 1) {
    const monthlyCounts = {};
    points.forEach(p => {
      const ym = p.x.slice(0, 7);
      monthlyCounts[ym] = (monthlyCounts[ym] || 0) + 1;
    });
    const volMonths = Object.keys(monthlyCounts).sort();
    const volCounts = volMonths.map(m => monthlyCounts[m]);
    const volLabels = volMonths.map(m => { const p = m.split('-'); return p[0].slice(2) + '.' + p[1]; });

    volumeChart = new Chart(volCanvas, {
      type: 'bar',
      data: {
        labels: volLabels,
        datasets: [{
          data: volCounts,
          backgroundColor: 'rgba(245,200,66,0.35)',
          borderRadius: 2,
          barPercentage: 0.6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ctx.parsed.y + '건' } }
        },
        scales: {
          x: { display: false },
          y: { display: false }
        }
      }
    });
  }
}

// ── 에러 ──
function showError(msg) {
  $('#app').innerHTML = `
    <div class="error">
      <div class="error-icon">🏠</div>
      <div class="error-msg">${esc(msg)}</div>
      <a class="btn-secondary" href="/" style="display:inline-block;margin-top:16px;padding:10px 24px;text-decoration:none;">홈으로</a>
    </div>
  `;
}


// ── 차트 포인트 하이라이트 ──
function highlightChartPoint(type) {
  if (!chart || !DATA) return;

  const d = DATA;
  const suffix = currentTab === '전세' ? '_jeonse' : (currentTab === '월세' ? '_wolse' : '');
  const key = currentPyeong + (suffix || '');
  const rt = d.recent_trade || {};
  const high = d.all_time_high || {};

  let targetDate = null;
  if (type === 'recent') {
    targetDate = (rt[key] || {}).date;
  } else {
    targetDate = (high[key] || {}).date;
  }
  if (!targetDate) return;

  const dataset = chart.data.datasets[0];

  // 날짜 + 가격 동시 매칭 (같은 날 여러 거래 중 정확한 1건만 하이라이트)
  const targetKey = currentPyeong + (currentTab === '전세' ? '_jeonse' : currentTab === '월세' ? '_wolse' : '');
  const targetData = type === 'recent'
    ? (d.recent_trade || {})[targetKey]
    : (d.all_time_high || {})[targetKey];
  const targetPrice = targetData ? Math.round(targetData.price / 100) / 100 : null;

  const matchFn = (px, py) => {
    const dateOk = String(px) === targetDate || String(px).slice(0, 7) === targetDate.slice(0, 7);
    if (!dateOk) return false;
    if (targetPrice === null) return true;
    return Math.abs(py - targetPrice) < 0.1; // 1000만원 오차 허용
  };

  const colors = dataset.data.map(p => {
    if (!matchFn(p.x, p.y)) return 'rgba(245,200,66,0.4)';
    return type === 'recent' ? '#f5c842' : '#f87171';
  });
  const radii = dataset.data.map(p => matchFn(p.x, p.y) ? 10 : 4);
  const borders = dataset.data.map(p => {
    if (!matchFn(p.x, p.y)) return 'rgba(245,200,66,0.2)';
    return type === 'recent' ? '#fff' : '#fca5a5';
  });

  const widths = radii.map(r => r > 4 ? 2 : 1);
  // 전역에 하이라이트 상태 저장 → highlightKeeperPlugin이 hover re-render에서 재적용
  window._danjiHighlight = { colors, borders, radii, widths };
  dataset.backgroundColor = colors;
  dataset.borderColor = borders;
  dataset.pointRadius = radii;
  dataset.borderWidth = widths;
  chart.update('none');

  // 차트 섹션으로 부드럽게 스크롤
  const chartEl = document.getElementById('priceChart');
  if (chartEl) chartEl.closest('.chart-section')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── JSON-LD 구조화 데이터 (SEO) ──
function injectJsonLd() {
  if (!DATA) return;
  const d = DATA;
  const locParts = (d.location || '').split(' ');
  const guName = locParts[0] || '';
  const canonUrl = `https://hwik.kr/danji/${encodeURIComponent(new URLSearchParams(location.search).get('id') || DATA.id)}`;

  const subway = d.nearby_subway || [];
  const recentFirst = d.categories && d.categories[0] ? (d.recent_trade || {})[d.categories[0]] : null;
  const highFirst = d.categories && d.categories[0] ? (d.all_time_high || {})[d.categories[0]] : null;
  const jeonseFirst = d.categories && d.categories[0] ? (d.recent_trade || {})[d.categories[0] + '_jeonse'] : null;
  let jr = d.jeonse_rate;
  if (jeonseFirst && recentFirst && recentFirst.price > 0) jr = Math.round(jeonseFirst.price / recentFirst.price * 1000) / 10;

  const faq = [
    { q: `${d.complex_name} 최근 실거래가는?`, a: recentFirst ? `${d.complex_name} 최근 매매 실거래가는 ${formatPrice(recentFirst.price)}입니다.${recentFirst.date ? ' ('+recentFirst.date+' 기준)' : ''}` : '최근 거래 내역을 확인 중입니다.' },
    { q: `${d.complex_name} 전세가율은?`, a: jr ? `${d.complex_name}의 전세가율은 약 ${jr}%입니다.` : '전세가율 정보를 확인 중입니다.' },
    { q: `${d.complex_name} 근처 지하철역은?`, a: subway.length > 0 ? subway.map(s => `${s.name}(${s.line || ''}) 도보 ${walkMin(s.distance)}`).join(', ') : '주변 지하철 정보를 확인 중입니다.' },
    { q: `${d.complex_name} 최근 5년 최고가는?`, a: highFirst ? `${d.complex_name} 최근 5년 최고가는 ${formatPrice(highFirst.price)}입니다.${highFirst.date ? ' ('+highFirst.date+')' : ''}` : '최근 5년 최고가 정보를 확인 중입니다.' },
  ];

  const ld = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Residence",
        "name": d.complex_name,
        "address": { "@type": "PostalAddress", "addressLocality": d.location, "streetAddress": d.address, "addressRegion": (d.address || '').split(' ')[0] || "서울특별시", "addressCountry": "KR" },
        "geo": { "@type": "GeoCoordinates", "latitude": d.lat, "longitude": d.lng },
        "description": d.seo_text || '',
        "numberOfRooms": d.total_units,
        "yearBuilt": d.build_year,
      },
      {
        "@type": "BreadcrumbList",
        "itemListElement": [
          { "@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr" },
          { "@type": "ListItem", "position": 2, "name": `${_cityLabel} ${guName}`, "item": `https://hwik.kr/gu/${encodeURIComponent(_guUrlSlug)}` },
          { "@type": "ListItem", "position": 3, "name": d.complex_name, "item": canonUrl },
        ]
      },
      {
        "@type": "FAQPage",
        "mainEntity": faq.map(f => ({
          "@type": "Question",
          "name": f.q,
          "acceptedAnswer": { "@type": "Answer", "text": f.a }
        }))
      }
    ]
  };
  const script = document.createElement('script');
  script.type = 'application/ld+json';
  script.textContent = JSON.stringify(ld);
  document.head.appendChild(script);
}

// ── 데이터 오류 신고 ──
function openReportModal() {
  if (document.getElementById('reportModal')) return;

  const overlay = document.createElement('div');
  overlay.id = 'reportModal';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:flex-end;justify-content:center;';

  const types = ['가격 오류', '면적 오류', '단지 정보 오류', '기타'];

  overlay.innerHTML = `
    <div style="background:var(--bg, #fff);border-radius:20px 20px 0 0;padding:24px 20px 40px;width:100%;max-width:480px;box-shadow:0 -4px 20px rgba(0,0,0,0.15);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
        <span style="font-size:16px;font-weight:700;color:var(--text, #1a1a2e);">데이터 오류 신고</span>
        <button onclick="closeReportModal()" style="background:none;border:none;font-size:22px;cursor:pointer;color:var(--sub, #9ca3af);line-height:1;">×</button>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px;">
        ${types.map(t => `
          <button onclick="selectReportType(this,'${t}')" data-type="${t}"
            style="padding:10px;border:1.5px solid var(--border, #e5e7eb);border-radius:10px;background:var(--card, #f8f9fa);font-size:14px;cursor:pointer;color:var(--text, #374151);transition:all .15s;">
            ${t}
          </button>`).join('')}
      </div>
      <textarea id="reportMemo" placeholder="추가 내용 (선택사항)" rows="3"
        style="width:100%;border:1.5px solid var(--border, #e5e7eb);border-radius:10px;padding:10px 12px;font-size:14px;background:var(--bg, #fff);color:var(--text, #374151);resize:none;box-sizing:border-box;"></textarea>
      <button id="reportSubmitBtn" onclick="submitReport()" disabled
        style="width:100%;margin-top:12px;padding:13px;border:none;border-radius:12px;background:#d1d5db;color:#9ca3af;font-size:15px;font-weight:700;cursor:not-allowed;transition:all .2s;">
        신고하기
      </button>
      <p id="reportMsg" style="text-align:center;font-size:13px;margin-top:10px;min-height:18px;"></p>
    </div>`;

  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeReportModal(); });
  document.body.appendChild(overlay);
}

function closeReportModal() {
  const el = document.getElementById('reportModal');
  if (el) el.remove();
}

function selectReportType(btn, type) {
  document.querySelectorAll('#reportModal [data-type]').forEach(b => {
    b.style.background = 'var(--card, #f8f9fa)';
    b.style.borderColor = 'var(--border, #e5e7eb)';
    b.style.color = 'var(--text, #374151)';
    b.style.fontWeight = '400';
  });
  btn.style.background = '#ede9fe';
  btn.style.borderColor = '#7c3aed';
  btn.style.color = '#7c3aed';
  btn.style.fontWeight = '700';

  const submitBtn = document.getElementById('reportSubmitBtn');
  if (submitBtn) {
    submitBtn.disabled = false;
    submitBtn.style.background = '#7c3aed';
    submitBtn.style.color = '#fff';
    submitBtn.style.cursor = 'pointer';
  }
  window._reportType = type;
}

async function submitReport() {
  const type = window._reportType;
  if (!type || !DATA) return;

  const memo = (document.getElementById('reportMemo')?.value || '').trim();
  const btn = document.getElementById('reportSubmitBtn');
  const msg = document.getElementById('reportMsg');

  if (btn) { btn.disabled = true; btn.textContent = '전송 중...'; }

  try {
    const res = await fetch('https://jqaxejgzkchxbfzgzyzi.supabase.co/functions/v1/report-danji', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        danji_id: DATA.id,
        danji_name: DATA.complex_name,
        report_type: type,
        memo: memo || null,
        page_url: location.href,
      }),
    });

    if (res.ok) {
      if (msg) { msg.style.color = '#16a34a'; msg.textContent = '신고가 접수됐습니다. 감사합니다 🙏'; }
      setTimeout(closeReportModal, 1800);
    } else {
      throw new Error('서버 오류');
    }
  } catch (e) {
    if (msg) { msg.style.color = '#dc2626'; msg.textContent = '전송 실패. 잠시 후 다시 시도해주세요.'; }
    if (btn) { btn.disabled = false; btn.textContent = '신고하기'; }
  }
}

// ── 실행 ──
loadData().then(() => { injectJsonLd(); });