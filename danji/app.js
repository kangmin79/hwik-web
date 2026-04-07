const sb = supabase.createClient(HWIK_CONFIG.SUPABASE_URL, HWIK_CONFIG.SUPABASE_KEY);
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

let DATA = null;
let currentTab = '매매';
let currentPyeong = null;
let showSupply = false; // 전용/공급 토글

// slug 생성 (build_danji_pages.py의 make_slug와 동일 로직)
const REGION_MAP = {
  '서울특별시':'서울','인천광역시':'인천','부산광역시':'부산',
  '대구광역시':'대구','광주광역시':'광주','대전광역시':'대전',
  '울산광역시':'울산','세종특별자치시':'세종','경기도':'경기',
  '강원특별자치도':'강원','충청북도':'충북','충청남도':'충남',
  '전북특별자치도':'전북','전라남도':'전남','경상북도':'경북',
  '경상남도':'경남','제주특별자치도':'제주',
  '서울':'서울','인천':'인천','부산':'부산','대구':'대구',
  '광주':'광주','대전':'대전','울산':'울산','세종':'세종',
  '경기':'경기','강원':'강원','충북':'충북','충남':'충남',
  '전북':'전북','전남':'전남','경북':'경북','경남':'경남','제주':'제주'
};
const METRO_CITIES = new Set(['서울','인천','부산','대구','광주','대전','울산']);
function _clean(s) { return (s||'').replace(/[^\w가-힣]/g,'-').replace(/-+/g,'-').replace(/^-|-$/g,''); }
function makeSlug(name, location, did, address) {
  const addrParts = (address||'').split(/\s+/);
  const region = addrParts[0] ? (REGION_MAP[addrParts[0]]||'') : '';
  const parts = [];
  if (region) {
    parts.push(region);
    if (METRO_CITIES.has(region)) {
      if (addrParts[1] && (addrParts[1].endsWith('구') || addrParts[1].endsWith('군'))) parts.push(addrParts[1].endsWith('군') ? addrParts[1].replace(/군$/,'') : addrParts[1]);
    } else if (region !== '세종') {
      if (addrParts[1]) parts.push(addrParts[1].replace(/(시|군)$/,''));
      if (addrParts[2] && addrParts[2].endsWith('구')) parts.push(addrParts[2]);
    }
  } else {
    const locParts = (location||'').split(' ');
    if (locParts[0]) parts.push(_clean(locParts[0]));
  }
  // 동 추가 (location에서 구/시 제외한 나머지)
  const locSplit = (location||'').split(' ');
  if (locSplit.length >= 2) locSplit.slice(1).forEach(d => parts.push(_clean(d)));
  if (did && (did.startsWith('offi-') || did.startsWith('apt-'))) {
    parts.push(did);
  } else {
    parts.push(_clean(name));
    if (did) parts.push(did);
  }
  return parts.filter(Boolean).map(p => _clean(p)).join('-');
}
let chart = null;
let volumeChart = null;
let RANK_INFO = null;

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

// ── 데이터 로드 ──
async function loadData() {
  const id = new URLSearchParams(location.search).get('id')
    || (location.pathname.match(/-(a\d+)(?:\.html)?$/) || [])[1]
    || (location.pathname.match(/((?:offi|apt)-[^/]+?)(?:\.html)?$/) || [])[1]
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
}

// ── 렌더링 ──
function render() {
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
    const schoolText = school.slice(0,2).map(s => shortSchool(esc(s.name)) + ' ' + walkMin(s.distance)).join(' <span class="tag-sep">·</span> ');
    tagHtml += `<div class="tag-line tag-school-line"><span class="tag-icon">🏫</span>${schoolText}</div>`;
  }

  // 전용/공급 토글 + 면적 버튼
  const pm = d.pyeongs_map || {};
  // 실제 매핑된 항목(exclu ±5㎡ 이내)이 하나라도 있을 때만 공급 토글 표시
  const hasSupply = cats.some(c => pm[c] && pm[c].supply && Math.abs((pm[c].exclu || 0) - parseFloat(c)) <= 5);
  const toggleRowHtml = hasSupply ? `<div style="display:flex;align-items:center;padding:8px 16px 0;gap:8px;">
    <div onclick="showSupply=false;render();" style="display:flex;align-items:center;gap:4px;cursor:pointer;padding:5px 12px;border-radius:16px;font-size:12px;font-weight:500;${!showSupply?'background:var(--dark);color:#fff;':'background:var(--card);color:var(--sub);'}">${!showSupply?'●':'○'} 전용</div>
    <div onclick="showSupply=true;render();" style="display:flex;align-items:center;gap:4px;cursor:pointer;padding:5px 12px;border-radius:16px;font-size:12px;font-weight:500;${showSupply?'background:#3b82f6;color:#fff;':'background:var(--card);color:var(--sub);'}">${showSupply?'●':'○'} 공급</div>
  </div>` : '';
  const pyeongHtml = cats.map(c => {
    const active = c === currentPyeong ? ' active' : '';
    let label = c + '㎡';
    // fallback 매핑(exclu가 실제 면적과 5㎡ 이상 차이)은 공급 라벨 표시 안 함
    if (showSupply && pm[c] && pm[c].supply && Math.abs((pm[c].exclu || 0) - parseFloat(c)) <= 5) {
      const supplyVal = Math.round(pm[c].supply);
      const pyeong = Math.round(supplyVal / 3.3058);
      label = pyeong + '평(' + supplyVal + '㎡)';
    }
    return `<div class="pyeong-btn${active}" data-cat="${esc(c)}">${esc(label)}</div>`;
  }).join('');

  // 현재 평형 기준 지표
  const tradeKey = currentPyeong;
  const jeonseKey = currentPyeong + '_jeonse';
  const wolseKey = currentPyeong + '_wolse';

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

  // 지표 변화량 (최근 3년 최고 대비 금액 + %)
  let changeHtml = '';
  if (recentPrice && highPrice) {
    const diff = recentPrice - highPrice;
    const pct = Math.round(Math.abs(diff) / highPrice * 1000) / 10;
    if (diff < 0) changeHtml = `<div class="price-card-change down">최고 대비 -${formatPrice(Math.abs(diff))}(${pct}%)</div>`;
    else if (diff > 0) changeHtml = `<div class="price-card-change up">최고가 경신</div>`;
    else changeHtml = `<div class="price-card-change neutral">최고가 동일</div>`;
  }

  // 최근 거래 목록 (현재 선택 평형 + 탭 기준)
  const tradeKeyFull = currentPyeong + (currentTab === '전세' ? '_jeonse' : (currentTab === '월세' ? '_wolse' : ''));
  const ph = (d.price_history || {})[tradeKeyFull] || [];
  let pyLabel = '';
  if (currentPyeong) {
    if (showSupply && pm[currentPyeong] && pm[currentPyeong].supply && Math.abs((pm[currentPyeong].exclu || 0) - parseFloat(currentPyeong)) <= 5) {
      const sv = Math.round(pm[currentPyeong].supply);
      pyLabel = '공급 ' + sv + '㎡(' + Math.round(sv/3.3058) + '평)';
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
        <div class="trade-detail">${pyLabel}${t.floor ? ' · ' + t.floor + '층' : ''}</div>
      </div>
      <div class="trade-date">${esc(t.date || '')}</div>
    </div>`;
  }).join('');

  // 휙 매물
  const listingCount = {};
  listings.forEach(l => { listingCount[l.type] = (listingCount[l.type]||0) + 1; });
  const listingBadge = Object.entries(listingCount).map(([k,v]) => `${k} ${v}`).join(' · ');
  const listingHtml = listings.slice(0,3).map(l => `
    <a class="listing-item" href="/property_view.html?id=${encodeURIComponent(l.id)}" style="text-decoration:none;color:inherit;">
      <div>
        <div class="trade-price">${esc(l.type)} ${formatPrice(l.price)}</div>
        <div class="trade-detail">${l.floor ? l.floor+'층' : ''} ${l.area ? '· '+l.area+'㎡' : ''} ${l.move_in ? '· '+esc(l.move_in) : ''}</div>
      </div>
      <div class="listing-link">상세보기</div>
    </a>
  `).join('');

  // 주변 단지 (현재 선택 평형 기준으로 비교)
  const curArea = currentPyeong ? parseInt(currentPyeong) : 84;
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
      if (showSupply && bestSupply) areaLabel = '공급 ' + Math.round(bestSupply) + '㎡';
      else areaLabel = '전용 ' + bestExclu + '㎡';
    }
    return `
    <a class="nearby-item" href="/danji/${encodeURIComponent(makeSlug(n.name, n.location, n.id, d.address))}" style="text-decoration:none;color:inherit;">
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
  const seoBasic = [esc(d.complex_name), '은(는)'];
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
    const pyList = cats.map(c => '전용 ' + c + '㎡');
    seoParts.push(pyList.join(', ') + ' 면적이 있습니다.');
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
    seoParts.push('최근 3년 최고가는 ' + formatPrice(highPrice) + (highData.date ? ' (' + highData.date + ')' : '') + '입니다.');
  }
  if (jeonseRate) {
    seoParts.push('전세가율은 ' + jeonseRate + '%입니다.');
  }

  const seoFull = seoParts.join(' ');
  const seoShort = seoFull.length > 120 ? seoFull.slice(0,120) : seoFull;
  const seoRest = seoFull.length > 120 ? seoFull.slice(120) : '';

  // 조합
  const locationParts = (d.location || '').split(' ');
  const dong = locationParts[locationParts.length - 1] || d.location;

  // breadcrumb
  const guName = locationParts[0] || '';

  // FAQ 데이터
  const faqItems = [];
  if (currentTab !== '월세') {
    // 매매/전세: 가격 관련 FAQ
    if (recentPrice) {
      faqItems.push({ q: `${d.complex_name} 최근 실거래가는?`, a: `${d.complex_name} 최근 매매 실거래가는 ${formatPrice(recentPrice)}입니다.${recentData && recentData.date ? ' ('+recentData.date+' 기준)' : ''}` });
      const _areaNum = currentPyeong ? parseFloat(currentPyeong) : 0;
      if (_areaNum > 0) faqItems.push({ q: `${d.complex_name} ㎡당 가격은?`, a: `전용 ${currentPyeong}㎡ 기준 ㎡당 ${formatPrice(Math.round(recentPrice / _areaNum))}입니다.` });
    }
    if (jeonseRate) faqItems.push({ q: `${d.complex_name} 전세가율은?`, a: `${d.complex_name}의 전세가율은 ${jeonseRate}%입니다.` });
    if (highPrice) faqItems.push({ q: `${d.complex_name} 최근 3년 최고가는?`, a: `최근 3년 최고가는 ${formatPrice(highPrice)}입니다.${highData && highData.date ? ' ('+highData.date+')' : ''}` });
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
      <a href="/">휙</a><span>&gt;</span><a href="/gu.html?name=${encodeURIComponent(guName)}">서울 ${esc(guName)}</a><span>&gt;</span>${esc(d.complex_name)}
    </nav>

    <!-- 헤더 -->
    <header class="header">
      <div class="header-top">
        <div class="logo">휙</div>
        <div>
          <h1 class="header-name">${esc(d.complex_name)}</h1>
          <div class="header-sub">${esc(d.location)} · ${d.total_units ? d.total_units.toLocaleString()+'세대' : ''} · ${d.build_year || ''}년${d.builder ? ' · '+esc(d.builder) : ''}</div>
          <div id="rank-badge" style="display:none;margin-top:5px;font-size:11px;padding:2px 9px;background:rgba(245,200,66,0.2);border-radius:20px;color:#f5c842;font-weight:500;width:fit-content;"></div>
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
    ${currentTab !== '월세' ? `<div class="price-cards">
      <div class="price-card primary">
        <div class="price-card-label">최근 ${currentTab === '전세' ? '전세가' : '실거래가'}</div>
        <div class="price-card-value">${recentPrice ? formatPrice(recentPrice) : '-'}</div>
        <div class="price-card-sub">${recentData && recentData.floor ? recentData.floor + '층' : ''}${recentData && recentData.date ? ' · ' + recentData.date : ''}</div>
        ${changeHtml}
      </div>
      <div class="price-card secondary">
        <div class="price-card-label">최근 3년 최고${currentTab === '전세' ? ' 전세가' : '가'}</div>
        <div class="price-card-value">${highPrice ? formatPrice(highPrice) : '-'}</div>
        <div class="price-card-sub">${highData && highData.floor ? highData.floor + '층' : ''}${highData && highData.date ? ' · ' + highData.date : ''}</div>
      </div>
    </div>
    ${jeonseRate ? `<div class="metrics"><div class="metric" style="grid-column:span 3;text-align:center;">
      <div class="metric-label">전세가율</div>
      <div class="metric-value" style="font-size:18px;font-weight:600;">${jeonseRate}%</div>
    </div></div>` : ''}` : ''}
    <!-- 지표 2행: ㎡당 가격 + 주차 + 최고층/세대수 (월세 탭에서는 숨김) -->
    ${currentTab === '월세' ? '' : (() => {
      const cells = [];
      // ㎡당 가격 (전용/공급 토글 반영)
      let sqmArea = currentPyeong ? parseFloat(currentPyeong) : 0;
      let sqmBasis = '전용면적 기준';
      if (showSupply && pm[currentPyeong] && pm[currentPyeong].supply && Math.abs((pm[currentPyeong].exclu || 0) - parseFloat(currentPyeong)) <= 5) {
        sqmArea = pm[currentPyeong].supply;
        sqmBasis = '공급면적 기준';
      }
      const sqmPrice = (recentPrice && sqmArea > 0) ? Math.round(recentPrice / sqmArea) : null;
      if (sqmPrice) cells.push({label:'㎡당 가격', value:formatPrice(sqmPrice), sub:sqmBasis});
      // 주차
      const pk = parseInt(d.parking || 0);
      const hh = parseInt(d.total_units || 0);
      if (pk > 0) cells.push({label:'주차', value:pk.toLocaleString()+'대', sub: hh > 0 ? '세대당 '+(pk/hh).toFixed(1)+'대' : ''});
      // 최고층 또는 세대수
      if (d.top_floor) cells.push({label:'최고층', value:d.top_floor+'층'});
      else if (d.total_units) cells.push({label:'세대수', value:d.total_units.toLocaleString()+'세대'});

      if (cells.length === 0) return '';
      return '<div class="metrics">' + cells.map(c => {
        const fontSize = (c.value && c.value.length > 6) ? ' style="font-size:13px"' : '';
        return '<div class="metric"><div class="metric-label">'+esc(c.label)+'</div><div class="metric-value"'+fontSize+'>'+esc(c.value)+'</div>'+(c.sub ? '<div class="metric-change neutral">'+esc(c.sub)+'</div>' : '')+'</div>';
      }).join('') + '</div>';
    })()}

    <!-- 거래량 + 그래프 (월세 탭에서는 숨김) -->
    ${currentTab !== '월세' ? `
    <div class="chart-section">
      <div class="chart-title">거래량</div>
      <div style="height:40px;position:relative;"><canvas id="volumeChart"></canvas></div>
      <div class="chart-title" style="margin-top:8px;">실거래가</div>
      <div class="chart-wrap"><canvas id="priceChart"></canvas></div>
    </div>
    ` : ''}

    <!-- 최근 실거래 -->
    <div class="section">
      <div class="section-title">${currentTab === '월세' ? '최근 월세 거래' : '최근 실거래'}</div>
      <div class="trade-list">${tradeListHtml || '<div style="font-size:12px;color:var(--sub);padding:8px 0;">거래 내역이 없습니다</div>'}</div>
    </div>

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
    <div class="section">
      <div class="section-title">${esc(dong)} 주변 단지</div>
      <div style="font-size:11px;color:var(--sub);margin-bottom:12px;margin-top:-6px;">${currentTab === '월세' ? '매매가 기준 · ' : ''}${showSupply && pm[currentPyeong] && pm[currentPyeong].supply && Math.abs((pm[currentPyeong].exclu||0)-parseFloat(currentPyeong))<=5 ? '공급 '+Math.round(pm[currentPyeong].supply)+'㎡' : '전용 '+(currentPyeong||'84')+'㎡'} ±10㎡ 기준</div>
      <div style="display:flex;flex-direction:column;gap:8px;">${nearbyHtml || '<div style="font-size:12px;color:var(--sub);">주변 단지 정보가 없습니다</div>'}</div>
    </div>

    <!-- FAQ -->
    <div class="faq-section">
      <div class="section-title">자주 묻는 질문</div>
      ${faqHtml}
    </div>

    <div class="divider"></div>

    <!-- 내부 링크 (SEO) -->
    <div class="section">
      <div class="section-title">더 알아보기</div>
      <div style="display:flex;flex-direction:column;gap:8px;">
        <a href="/dong/${encodeURIComponent((guName+'-'+dong).replace(/[^\w가-힣]/g,'-').replace(/-+/g,'-').replace(/^-|-$/g,''))}" style="display:flex;justify-content:space-between;align-items:center;padding:12px 14px;background:var(--card);border-radius:var(--radius);text-decoration:none;color:var(--text);transition:all .15s;">
          <span style="font-size:13px;">${esc(dong)} 다른 단지 시세</span><span style="color:var(--sub);font-size:12px;">→</span>
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
      <div class="seo-source">실거래가 출처: 국토교통부 실거래가 공개시스템 · 매일 업데이트</div>
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
  // render() 재호출 시에도 배지 복원
  renderRankBadge();
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

  // price_history: [{date:"2024-03-15", price:131000, floor:12}, ...]
  // 또는 이전 포맷: [{month:"2024-03", avg_price:131000, count:2}, ...]
  let points = [];

  if (ph.length > 0 && ph[0].date) {
    // 신규 포맷: 개별 거래
    points = ph.map(p => ({
      x: p.date,
      y: Math.round(p.price / 100) / 100, // 억 단위
      floor: p.floor || '',
      date: p.date,
      price: p.price,
    }));
  } else if (ph.length > 0 && ph[0].month) {
    // 이전 포맷(월평균) 호환: 점 1개로 표시
    points = ph.map(p => ({
      x: p.month + '-15',
      y: Math.round(p.avg_price / 100) / 100,
      floor: '',
      date: p.month,
      price: p.avg_price,
    }));
  }

  // 폴백: price_history 없으면 현재 평형의 recent_trade만
  if (points.length === 0) {
    const recent = DATA.recent_trade || {};
    const targetKey = key; // currentPyeong + suffix
    for (const [k, v] of Object.entries(recent)) {
      // 현재 선택한 평형+탭에 해당하는 키만
      if (k !== targetKey) continue;
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
    // 월별 거래 건수 집계
    const monthlyCounts = {};
    points.forEach(p => {
      const ym = p.x.slice(0, 7); // "2025-03"
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

// ── 구 내 랭킹 배지 ──
function renderRankBadge() {
  if (!RANK_INFO) return;
  const badge = document.getElementById('rank-badge');
  if (!badge) return;
  const { rank, total, guName } = RANK_INFO;
  const medal = rank === 1 ? '🥇 ' : rank === 2 ? '🥈 ' : rank === 3 ? '🥉 ' : '';
  const topPct = Math.round(rank / total * 100);
  const topText = topPct <= 10 ? ` · 상위 ${topPct}%` : '';
  badge.textContent = `${medal}${guName} ${rank}위 / ${total}개 단지${topText}`;
  badge.style.display = 'block';
}

async function loadRankInfo() {
  if (!DATA || !currentPyeong) return;
  const guName = (DATA.location || '').split(' ')[0];
  if (!guName) return;
  try {
    const { data, error } = await sb.from('danji_pages')
      .select('id, recent_trade, categories')
      .ilike('location', guName + ' %');
    if (error || !data || data.length < 2) return;
    const curArea = parseInt(currentPyeong);
    const priceList = data.map(row => {
      const rt = row.recent_trade || {};
      const cats = row.categories || [];
      let bestKey = null, bestDiff = 999;
      for (const k of cats) {
        const diff = Math.abs(parseInt(k) - curArea);
        if (diff < bestDiff && diff <= 20) { bestDiff = diff; bestKey = k; }
      }
      const price = bestKey && rt[bestKey] ? rt[bestKey].price : null;
      return { id: row.id, price };
    }).filter(r => r.price);
    priceList.sort((a, b) => b.price - a.price);
    const idx = priceList.findIndex(r => r.id === DATA.id);
    if (idx === -1) return;
    RANK_INFO = { rank: idx + 1, total: priceList.length, guName };
    renderRankBadge();
  } catch(e) { /* 랭킹 로드 실패해도 메인 기능에 영향 없음 */ }
}

// ── JSON-LD 구조화 데이터 (SEO) ──
function injectJsonLd() {
  if (!DATA) return;
  const d = DATA;
  const locParts = (d.location || '').split(' ');
  const guName = locParts[0] || '';
  const canonUrl = `https://hwik.kr/danji/${encodeURIComponent(new URLSearchParams(location.search).get('id') || id)}`;

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
    { q: `${d.complex_name} 최근 3년 최고가는?`, a: highFirst ? `${d.complex_name} 최근 3년 최고가는 ${formatPrice(highFirst.price)}입니다.${highFirst.date ? ' ('+highFirst.date+')' : ''}` : '최근 3년 최고가 정보를 확인 중입니다.' },
  ];

  const ld = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Residence",
        "name": d.complex_name,
        "address": { "@type": "PostalAddress", "addressLocality": d.location, "streetAddress": d.address, "addressRegion": "서울특별시", "addressCountry": "KR" },
        "geo": { "@type": "GeoCoordinates", "latitude": d.lat, "longitude": d.lng },
        "description": d.seo_text || '',
        "numberOfRooms": d.total_units,
        "yearBuilt": d.build_year,
      },
      {
        "@type": "BreadcrumbList",
        "itemListElement": [
          { "@type": "ListItem", "position": 1, "name": "휙", "item": "https://hwik.kr" },
          { "@type": "ListItem", "position": 2, "name": `서울 ${guName}`, "item": `https://hwik.kr/gu.html?name=${encodeURIComponent(guName)}` },
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

// ── 실행 ──
loadData().then(() => { injectJsonLd(); loadRankInfo(); });