const sb = supabase.createClient(HWIK_CONFIG.SUPABASE_URL, HWIK_CONFIG.SUPABASE_KEY);
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

let DATA = null;
let currentTab = '매매';
let currentPyeong = null;
let complexType = '';
let nearbyComplexTypes = {};
let _guUrlSlug = '';
let _cityLabel = '';

// 현재 탭(매매/전세/월세)을 URL 파라미터로 반환
// 배너/링크에서 사용: buildUrlWithTab('https://hwik.kr/agent/홍길동')
// → 'https://hwik.kr/agent/홍길동?type=전세'
function buildUrlWithTab(baseUrl) {
  return `${baseUrl}?type=${encodeURIComponent(currentTab)}`;
}

// makeSlug → /makeSlug.js (외부 파일)
let chart = null;
let volumeChart = null;

// ── 유틸 ──
function esc(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

// 5년 전 ±6개월 범위에서 가장 가까운 거래 1건 반환
function find5yAgoTrade(tradeList, recentDate) {
  if (!Array.isArray(tradeList) || tradeList.length === 0) return null;
  if (!recentDate || recentDate.length < 10) return null;
  const ry = parseInt(recentDate.slice(0,4));
  const rm = parseInt(recentDate.slice(5,7));
  if (!ry || !rm) return null;
  const targetYm = (ry - 5) * 12 + rm;
  let best = null;
  let bestDiff = 999;
  for (const t of tradeList) {
    const td = t && t.date;
    if (!td || td.length < 7) continue;
    const ty = parseInt(td.slice(0,4));
    const tm = parseInt(td.slice(5,7));
    if (!ty || !tm) continue;
    const diff = Math.abs((ty * 12 + tm) - targetYm);
    if (diff <= 6 && diff < bestDiff) { bestDiff = diff; best = t; }
  }
  return best;
}

// 두 날짜(YYYY-MM-DD) 사이 연수 (소수 포함)
function calcYearsBetween(oldDate, newDate) {
  try {
    const oldT = Date.parse(oldDate);
    const newT = Date.parse(newDate);
    if (!oldT || !newT) return null;
    const diffDays = Math.abs(newT - oldT) / 86400000;
    if (diffDays <= 0) return null;
    return diffDays / 365.25;
  } catch (e) { return null; }
}

// 연평균 복리 상승률 (%). 소수점 1자리.
function calcCagr(oldPrice, newPrice, years) {
  if (!oldPrice || !newPrice || !years || years <= 0) return null;
  const ratio = newPrice / oldPrice;
  if (ratio <= 0) return null;
  const cagr = (Math.pow(ratio, 1 / years) - 1) * 100;
  if (!isFinite(cagr)) return null;
  return Math.round(cagr * 10) / 10;
}

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
// 404.html로 리다이렉트 → 브라우저/구글 모두 HTTP 404 확인
function markAsNotFound() {
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
  complexType = '';
  try {
    const res = await sb.from('danji_pages').select('id,complex_name,location,address,build_year,total_units,categories,recent_trade,all_time_high,jeonse_rate,price_history,nearby_subway,nearby_school,nearby_complex,active_listings,lat,lng,top_floor,parking,heating,builder,mgmt_fee,pyeongs_map,seo_text,updated_at').eq('id', id).single();
    data = res.data;
    error = res.error;
  } catch (e) {
    // 네트워크 오류 등 → 멀쩡한 페이지를 noindex하지 않도록 일반 에러 표시
    showError('일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.');
    return;
  }

  // apartments 쿼리는 실패해도 페이지 렌더링에 영향 없도록 별도 처리
  try {
    const aptRes = await sb.from('apartments').select('complex_type').eq('kapt_code', id.toUpperCase()).maybeSingle();
    const ct = aptRes.data?.complex_type || '';
    if (ct === '주상복합' || ct === '도시형 생활주택(주상복합)') complexType = '주상복합';
    else if (ct === '도시형 생활주택(아파트)') complexType = '도시형 생활주택';
  } catch (e) { /* 주상복합/도시형 태그 없이 정상 렌더링 */ }

  // PGRST116 = "no rows returned" (진짜 없음) → 404
  if (error && error.code === 'PGRST116') { markAsNotFound(); return; }
  // 그 외 에러(네트워크/권한 등) → 일반 에러 (noindex 안 함)
  if (error) { showError('단지 정보를 불러올 수 없습니다.'); return; }
  // data가 빈 경우(이론상 .single()에선 안 나오지만 방어)
  if (!data) { markAsNotFound(); return; }

  DATA = data;

  // SEO 메타(title/description/og/twitter/canonical) 및 JSON-LD는 정적 HTML에
  // build_danji_pages.py가 이미 완전히 주입했음. 런타임에서 덮어쓰면 실거래가
  // 수치가 날아가고 모든 단지가 같은 템플릿 문구로 색인됨 → SEO 손실.

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

  // 주변 단지 complex_type 배치 조회 (주상복합·도시형 태그용)
  nearbyComplexTypes = {};
  try {
    const nearbyList = data.nearby_complex || [];
    const ncIds = nearbyList
      .filter(function(n) { return n.id && !n.id.startsWith('offi-') && !n.id.startsWith('apt-'); })
      .map(function(n) { return n.id.toUpperCase(); });
    if (ncIds.length > 0) {
      const ncRes = await sb.from('apartments').select('kapt_code,complex_type').in('kapt_code', ncIds);
      (ncRes.data || []).forEach(function(row) {
        if (row.kapt_code && row.complex_type) {
          nearbyComplexTypes[row.kapt_code.toUpperCase()] = row.complex_type;
        }
      });
    }
  } catch (e) { /* 태그 없이 정상 렌더링 */ }

  // danji_pages.active_listings writer 없음 → cards 테이블 직접 조회 (플라이휠 복구)
  data.active_listings = await fetchActiveListings(id);

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

// ── cards 테이블에서 kapt_code로 계약가능 매물 조회 ──
// danji_pages.active_listings에 writer가 없어서 항상 비어있음 → 런타임에 cards 직접 조회.
async function fetchActiveListings(kaptCode) {
  try {
    const kc = (kaptCode || '').toLowerCase();
    if (!/^a\d/.test(kc)) return []; // apt-/offi- 접미사 ID는 danji 페이지 없음
    const { data, error } = await sb.from('cards')
      .select('id,agent_id,property,photos,trade_status,created_at')
      .eq('kapt_code', kc)
      .eq('trade_status', '계약가능')
      .order('created_at', { ascending: false })
      .limit(20);
    if (error || !data || data.length === 0) return [];

    const agentIds = [...new Set(data.map(c => c.agent_id).filter(Boolean))];
    const agentInfo = {};
    if (agentIds.length > 0) {
      const ap = await sb.from('profiles').select('id,agent_name,business_name,profile_photo,profile_photo_url').in('id', agentIds);
      (ap.data || []).forEach(p => {
        agentInfo[p.id] = {
          agent_name: p.agent_name || '',
          business_name: p.business_name || '',
          photo: p.profile_photo_url || p.profile_photo || ''
        };
      });
    }

    return data.map(c => {
      const p = c.property || {};
      const photos = Array.isArray(c.photos) ? c.photos : [];
      const thumb = photos[0]?.url || (typeof photos[0] === 'string' ? photos[0] : '');
      const info = agentInfo[c.agent_id] || {};
      return {
        id: c.id,
        agent_id: c.agent_id,
        agent_name: info.agent_name || '',
        business_name: info.business_name || '',
        agent_photo: info.photo || '',
        type: p.type || '',
        price: p.price || '',
        floor: p.floor || '',
        area: p.area || '',
        room: p.room || '',
        move_in: p.move_in || '',
        thumb
      };
    });
  } catch (e) {
    console.warn('fetchActiveListings failed', e);
    return [];
  }
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
  // D 디자인 공식 호선 색상 (build_d_design.py LINE_COLORS 와 동일)
  function lineColor(line) {
    if (!line) return '#94a3b8';
    const l = line.replace(/수도권\s+도시철도\s*/,'').replace(/서울\s+도시철도\s*/,'').replace(/수도권\s+광역철도\s*/,'').replace(/수도권\s+경량도시철도\s*/,'');
    const LC = {
      '1호선':'#0052A4','2호선':'#00A84D','3호선':'#EF7C1C','4호선':'#00A4E3',
      '5호선':'#996CAC','6호선':'#CD7C2F','7호선':'#747F00','8호선':'#E6186C',
      '9호선':'#BDB092',
      '경의중앙선':'#77C4A3','수인분당선':'#FABE00','신분당선':'#D4003B',
      '공항철도':'#0090D2','GTX-A':'#9A6292','우이신설선':'#B0CE18',
      '신림선':'#6789CA','경춘선':'#0C8E72','김포골드라인':'#A17E46',
      '인천1호선':'#7CA8D5','인천2호선':'#ED8B00',
    };
    // 양방향 매칭: shortLine() 가 '9호선' → '9' 로 줄여도 매칭되도록 (l.includes(k) || k.includes(l))
    for (const k in LC) {
      if (l.includes(k) || k.includes(l)) return LC[k];
    }
    // 지방 도시철도 (LC 미포함분)
    if (l.includes('부산')) return '#F06A00';
    if (l.includes('대구')) return '#D93F5A';
    if (l.includes('대전')) return '#00B5B5';
    if (l.includes('광주')) return '#009088';
    return '#94a3b8';
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
    // 초→중→고 순으로 정렬
    const _schoolOrder = { '초': 0, '중': 1, '고': 2 };
    const _schoolSorted = school.slice().sort((a, b) =>
      (_schoolOrder[schoolLabel(a.type)] ?? 9) - (_schoolOrder[schoolLabel(b.type)] ?? 9)
    );
    const schoolItems = _schoolSorted.slice(0,3).map(s => {
      const bg = schoolColor(s.type);
      const label = schoolLabel(s.type);
      return `<span class="station-tag"><span class="line-badge" style="background:${bg.bg};color:${bg.text}">${label}</span><span class="station-name">${shortSchool(esc(s.name))}</span> <span class="station-time">${walkMin(s.distance)}</span></span>`;
    }).join('<span class="tag-sep">·</span>');
    tagHtml += `<div class="tag-line tag-school-line">${schoolItems}</div>`;
  }

  // 전용/공급 토글 + 면적 버튼
  const pm = d.pyeongs_map || {};
  const catsSet = new Set(cats);
  // 실거래 있는 평형(categories)만 버튼으로 표시
  // 최근 5년 내 매매·전세·월세 거래가 없는 면적은 표시하지 않음
  const tabCats = cats; // categories = 실거래 존재하는 평형만
  const hasCurData = catsSet.has(currentPyeong);
  const hasSupplyData = tabCats.some(c => pm[c] && pm[c].supply && pm[c].supply > 0 && Math.abs((pm[c].exclu || 0) - parseFloat(c)) <= 10);
  const toggleRowHtml = hasSupplyData
    ? `<div style="font-size:11px;color:var(--sub);padding:6px 16px 0;">공급면적 기준</div>`
    : `<div style="font-size:11px;color:var(--sub);padding:6px 16px 0;">전용면적 기준</div>`;
  const pyeongHtml = tabCats.map(c => {
    const active = c === currentPyeong ? ' active' : '';
    let label;
    if (pm[c] && pm[c].supply && pm[c].supply > 0 && Math.abs((pm[c].exclu || 0) - parseFloat(c)) <= 10) {
      label = pm[c].supply.toFixed(1) + '㎡';
    } else {
      label = c + '㎡';
    }
    return `<div class="pyeong-btn${active}" data-cat="${esc(c)}">${esc(label)}</div>`;
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

  // 5년 CAGR 배지 — 직거래 양쪽 제외, 선택 평형·탭 기준
  let cagrBadgeHtml = '';
  const _tkfBadge = (currentPyeong || '') + (currentTab === '전세' ? '_jeonse' : (currentTab === '월세' ? '_wolse' : ''));
  if (recentPrice && recentData && recentData.date && currentPyeong && currentTab !== '월세' && recentData.kind !== '직거래') {
    const _phCagr = (d.price_history || {})[_tkfBadge] || [];
    const _old5Badge = find5yAgoTrade(_phCagr, recentData.date);
    if (_old5Badge && _old5Badge.price && _old5Badge.kind !== '직거래') {
      const _yrsBadge = calcYearsBetween(_old5Badge.date, recentData.date);
      const _cagrBadge = calcCagr(_old5Badge.price, recentPrice, _yrsBadge);
      if (_cagrBadge !== null && _cagrBadge !== 0) {
        const _cls = _cagrBadge > 0 ? 'up' : 'down';
        const _sign = _cagrBadge > 0 ? '+' : '-';
        cagrBadgeHtml = `<div class="price-card-change ${_cls}">5년 연평균 ${_sign}${Math.abs(_cagrBadge).toFixed(1)}%</div>`;
      }
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
  // 카드 전체를 중개사 페이지로 연결 (손님 유입 → 중개사 연락 플라이휠)
  // 1슬롯 고정: "한 카드 = 한 결정" 원칙. 여러 중개사 생기면 라운드로빈으로 1명만 노출.
  const listingHtml = listings.slice(0,1).map(l => {
    // 매물 실제 거래유형으로 필터 (danji 탭과 다를 수 있음 — 예: 매매 탭에서 월세 매물 클릭)
    const typeParam = l.type || currentTab;
    const href = l.agent_id
      ? `/agent.html?id=${encodeURIComponent(l.agent_id)}&kapt_code=${encodeURIComponent(d.id)}&type=${encodeURIComponent(typeParam)}`
      : `/property_view.html?id=${encodeURIComponent(l.id)}`;
    const thumbHtml = l.thumb
      ? `<img src="${esc(l.thumb)}" alt="매물" loading="lazy" decoding="async" style="width:80px;height:80px;object-fit:cover;border-radius:8px;flex-shrink:0;">`
      : `<div style="width:80px;height:80px;border-radius:8px;flex-shrink:0;background:var(--hover, #f5f5f5);display:flex;align-items:center;justify-content:center;font-size:28px;">${{매매:'🏠',전세:'🔑',월세:'💰',반전세:'🏡'}[l.type]||'🏠'}</div>`;
    const avatarInitial = (l.business_name || l.agent_name || '?').trim().charAt(0) || '?';
    const avatarHtml = l.agent_photo
      ? `<img src="${esc(l.agent_photo)}" alt="중개사" loading="lazy" decoding="async" style="width:28px;height:28px;border-radius:50%;object-fit:cover;flex-shrink:0;">`
      : `<div style="width:28px;height:28px;border-radius:50%;background:var(--accent, #facc15);color:#1a1a1a;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;flex-shrink:0;">${esc(avatarInitial)}</div>`;
    const agentTitle = l.business_name || l.agent_name || '';
    const agentSub = l.business_name && l.agent_name ? `${l.agent_name} 공인중개사` : '';
    const agentHeader = agentTitle
      ? `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;min-width:0;">
          ${avatarHtml}
          <div style="min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;">
            <span style="font-size:13px;font-weight:600;">${esc(agentTitle)}</span>${agentSub ? `<span style="font-size:12px;color:var(--sub);margin-left:6px;">${esc(agentSub)}</span>` : ''}
          </div>
        </div>`
      : '';
    return `
    <a href="${href}" class="listing-item" style="text-decoration:none;color:inherit;display:flex;justify-content:space-between;align-items:center;gap:10px;">
      <div style="flex:1;min-width:0;">
        ${agentHeader}
        <div class="trade-price" style="font-size:14px;">${esc(l.type)} ${formatPrice(l.price)}</div>
        ${(() => {
          const tags = [];
          if (l.area) tags.push(/[㎡평]/.test(String(l.area)) ? l.area : l.area + '㎡');
          if (l.floor) tags.push(l.floor + '층');
          if (l.room) tags.push(l.room);
          if (l.move_in) tags.push(l.move_in);
          if (!tags.length) return '';
          return `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;">${tags.slice(0,4).map(t => `<span style="font-size:11px;padding:3px 8px;background:var(--hover,#f5f5f5);border-radius:10px;color:var(--sub);white-space:nowrap;">${esc(t)}</span>`).join('')}</div>`;
        })()}
      </div>
      ${thumbHtml}
    </a>`;
  }).join('');

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
    // 오피스텔(offi-)·비아파트(apt-) = 페이지 미생성 → 스킵 (404 방지)
    if (n.id && (n.id.startsWith('offi-') || n.id.startsWith('apt-'))) return '';
    // 임대단지 = 정적 HTML 미생성 → 스킵 (404 방지)
    if (/임대/.test(n.name || '')) return '';
    // 거래 없는 단지 = 페이지 미생성 → 스킵 (404 방지)
    if (!bestPrice) return '';
    // 면적 표시 (전용/공급 토글 반영)
    let areaLabel = '';
    if (bestKey) {
      areaLabel = '전용 ' + bestExclu + '㎡';
    }
    const _nct = nearbyComplexTypes[n.id ? n.id.toUpperCase() : ''] || '';
    let _nctLabel = '';
    if (_nct === '주상복합' || _nct === '도시형 생활주택(주상복합)') _nctLabel = '주상복합';
    else if (_nct === '도시형 생활주택(아파트)') _nctLabel = '도시형';
    const _nctTag = _nctLabel ? `<span style="display:inline-block;background:#ede9fe;color:#5b21b6;font-size:10px;font-weight:600;padding:1px 6px;border-radius:3px;margin-left:4px;vertical-align:middle;">${_nctLabel}</span>` : '';
    // URL 우선순위: n.slug (DB SSOT) → 정적 HTML에 박힌 href → 런타임 makeSlug fallback
    const nHref = n.slug
      ? ('/danji/' + encodeURIComponent(n.slug) + '.html')
      : (STATIC_NEARBY_HREF[n.id]
         || ('/danji/' + encodeURIComponent(makeSlug(n.name, n.location, n.id, parentMetro && n.location ? (parentMetro + ' ' + n.location) : '')) + '.html'));
    return `
    <a class="nearby-item" href="${nHref}" style="text-decoration:none;color:inherit;">
      <div>
        <div class="nearby-name">${esc(n.name)}${_nctTag}</div>
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
  // 5년 CAGR SEO 문장 — 직거래 양쪽 제외
  if (recentPrice && recentData && recentData.date && currentPyeong && currentTab !== '월세') {
    const _phListSeo = (d.price_history || {})[tradeKeyFull] || [];
    const _old5seo = find5yAgoTrade(_phListSeo, recentData.date);
    if (_old5seo && _old5seo.price && recentData.kind !== '직거래' && _old5seo.kind !== '직거래') {
      const _yrsSeo = calcYearsBetween(_old5seo.date, recentData.date);
      const _cagrSeo = calcCagr(_old5seo.price, recentPrice, _yrsSeo);
      if (_cagrSeo !== null && _cagrSeo !== 0 && recentPrice !== _old5seo.price) {
        const _dirSeo = _cagrSeo > 0 ? '상승' : '하락';
        seoParts.push('최근 5년간 전용 ' + currentPyeong + '㎡ 실거래가는 연평균 ' + Math.abs(_cagrSeo).toFixed(1) + '% ' + _dirSeo + '했습니다.');
      }
    }
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
  _cityLabel = _cityMap[_addrCity] || '';
  // slug 규칙: 서울/경기=접두사 없음, 인천=중구만 예외, 나머지 전체={지역}-{구}
  // _cityLabel 미인식 시 guName만 사용 (서울/경기와 동일 동작, 안전한 fallback)
  const _noPrefixSet = new Set(['서울','경기']);
  const _guSlugBase = guName.replace(/ /g, '-');
  _guUrlSlug = (!_cityLabel || _noPrefixSet.has(_cityLabel)) ? _guSlugBase
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
      if (_supplyArea > 0) {
        faqItems.push({ q: `${d.complex_name} ㎡당 가격은?`, a: `${d.complex_name} ㎡당 가격은 공급면적(${Math.round(_supplyArea)}㎡) 기준 ${formatPrice(Math.round(recentPrice / _supplyArea))}입니다.` });
      }
    }
    if (jeonseRate) faqItems.push({ q: `${d.complex_name} 전세가율은?`, a: `${d.complex_name}의 전세가율은 ${jeonseRate}%입니다.` });
    if (highPrice) faqItems.push({ q: `${d.complex_name} 최근 5년 최고가는?`, a: `최근 5년 최고가는 ${formatPrice(highPrice)}입니다.${highData && highData.date ? ' ('+highData.date+')' : ''}` });
    // 5년 CAGR FAQ — 직거래 양쪽 제외
    if (recentPrice && recentData && recentData.date && currentPyeong) {
      const _phList = (d.price_history || {})[tradeKeyFull] || [];
      const _old5 = find5yAgoTrade(_phList, recentData.date);
      if (_old5 && _old5.price && recentData.kind !== '직거래' && _old5.kind !== '직거래') {
        const _yrs = calcYearsBetween(_old5.date, recentData.date);
        const _cagr = calcCagr(_old5.price, recentPrice, _yrs);
        if (_cagr !== null && _cagr !== 0 && recentPrice !== _old5.price) {
          const _dir = _cagr > 0 ? '상승' : '하락';
          faqItems.push({
            q: `${d.complex_name} 5년간 가격 변동은?`,
            a: `전용 ${currentPyeong}㎡ 기준 5년 전 거래가(${_old5.date})는 ${formatPrice(_old5.price)}이었고, 현재 ${formatPrice(recentPrice)}(${recentData.date})으로 연평균 ${Math.abs(_cagr).toFixed(1)}% ${_dir}했습니다.`
          });
        }
      }
    }
  }
  // 매매/전세/월세 공통 FAQ
  if (subway.length > 0) faqItems.push({ q: `${d.complex_name} 근처 지하철역은?`, a: subway.map(s => `<span style="color:${lineColor(s.line)};font-weight:500;">${esc(s.name)}</span>(${esc(shortLine(s.line))}) 도보 ${walkMin(s.distance)}`).join(', '), html: true });
  if (parseInt(d.parking || 0) > 0 && d.total_units) {
    const _parkingNum = parseInt(d.parking);
    const _ratioNum = _parkingNum / d.total_units;
    // 세대당 0.5대 미만은 DB 원본 오류 가능성 높음 (법정 최소 주차도 이 이상) → FAQ 생략
    if (_ratioNum >= 0.5) {
      faqItems.push({ q: `${d.complex_name} 주차 대수는?`, a: `총 ${_parkingNum.toLocaleString()}대 (세대당 ${_ratioNum.toFixed(1)}대)입니다.` });
    }
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
          <h1 class="header-name">${esc(d.complex_name)}${complexType ? `<span style="display:inline-block;background:#ede9fe;color:#5b21b6;font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;margin-left:6px;vertical-align:middle;">${complexType}</span>` : ''}</h1>
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
        ${cagrBadgeHtml}
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
        : '<div class="listing-empty"><div class="listing-empty-text">이 단지에 등록된 매물이 아직 없습니다</div><a class="listing-empty-cta" href="/hub-new/" style="text-decoration:none;">중개사님, 매물을 등록해보세요 →</a></div>'
      }
    </div>

    <div class="divider"></div>

    <!-- 주변 단지 -->
    <div class="section" id="nearby-section">
      <div class="section-title">${esc(dongDisplay)} 주변 단지</div>
      <div style="font-size:11px;color:var(--sub);margin-bottom:12px;margin-top:-6px;" id="nearby-label">${currentTab === '월세' ? '매매가 기준 · ' : ''}전용 ${currentPyeong||'84'}㎡ ±10㎡ 기준</div>
      <div style="display:flex;flex-direction:column;gap:8px;" id="nearby-list">${nearbyHtml || ''}</div>
    </div>

    <!-- 요약 문단 (구글 스니펫용 + 사용자 정보) -->
    ${(() => {
      const parts = [];
      const addr = d.address || '';
      const nm = d.complex_name || '';
      const yr = d.build_year ? d.build_year + '년 준공' : '';
      const ut = d.total_units ? d.total_units.toLocaleString() + '세대' : '';
      const loc = addr || d.location || '';
      if (loc) parts.push(`${esc(nm)}은(는) ${esc(loc)}에 위치한 아파트입니다.`);
      if (yr && ut) parts.push(`${yr}, 총 ${ut} 규모입니다.`);
      else if (yr) parts.push(`${yr} 준공되었습니다.`);
      else if (ut) parts.push(`총 ${ut} 규모입니다.`);
      if (recentPrice && currentPyeong) parts.push(`전용 ${currentPyeong}㎡ 최근 매매가는 ${formatPrice(recentPrice)}입니다.`);
      if (jeonseRate) parts.push(`전세가율은 ${jeonseRate}%입니다.`);
      parts.push('모든 데이터는 국토교통부 실거래가 공개시스템 기반입니다.');
      return parts.length > 1
        ? `<p style="font-size:12px;color:var(--sub);line-height:1.8;margin:0 16px 16px;">${parts.join(' ')}</p>`
        : '';
    })()}

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
        <a href="/gu/${encodeURIComponent(_guUrlSlug)}" style="display:flex;justify-content:space-between;align-items:center;padding:12px 14px;background:var(--card);border-radius:var(--radius);text-decoration:none;color:var(--text);transition:all .15s;">
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
      <a class="btn-secondary" href="/hub-new/" style="display:block;text-align:center;text-decoration:none;">공인중개사 서비스 · 무료로 시작하기</a>
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
      <div class="seo-source" style="margin-top:8px;">실거래가 출처: 국토교통부 · 최종 데이터 확인: ${new Date(Date.now() + 9*3600*1000).toISOString().slice(0,10)}</div>
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

  // D 디자인 변환 (SSR fallback과 visible text 일치 — 클로킹 회피)
  // body dataset flag 들 reset (render 재호출 시 중복 변환 방지)
  delete document.body.dataset.faqEnriched;
  delete document.body.dataset.faqSplit;
  delete document.body.dataset.faqMoved;
  delete document.body.dataset.mapPatched;
  delete document.body.dataset.seoPatched;
  applyDDesign(d);
}

// ── 가격 포맷 (D 변환에서 공통 사용) ──
function _dFmtPrice(n) {
  if (!n) return '-';
  const eok = Math.floor(n / 10000);
  const man = Math.round(n % 10000);
  if (eok && man) return eok + '억 ' + man.toLocaleString() + '만';
  if (eok) return eok + '억';
  return man.toLocaleString() + '만';
}

// ── D 변환: 거래 항목에 거래유형 칩 inject (활성 탭 기준) ──
const _D_KIND_COLOR = {
  '매매': { bg: '#fff1e7', fg: '#c2410c' },
  '전세': { bg: '#eaf2ff', fg: '#1d4ed8' },
  '월세': { bg: '#e8f6ee', fg: '#047857' }
};
function _dInjectTradeKindBadge() {
  const activeTab = document.querySelector('.tabs .tab.active');
  const kind = activeTab && activeTab.dataset.tab;
  const c = _D_KIND_COLOR[kind];
  if (!c) return;
  document.querySelectorAll('.trade-list .trade-item .trade-price').forEach(el => {
    if (el.querySelector('.kind-badge-d')) return;
    const span = document.createElement('span');
    span.className = 'kind-badge-d';
    span.textContent = kind;
    span.style.cssText = 'display:inline-block;padding:2px 7px;border-radius:4px;background:' + c.bg + ';color:' + c.fg + ';font-size:10.5px;font-weight:700;letter-spacing:0.2px;line-height:1.4;margin-right:8px;vertical-align:middle;';
    el.insertBefore(span, el.firstChild);
  });
}

// ── D 변환: 주변 단지 카드 — 단지명 앞 단지타입 보라 뱃지 + 가격 주황 + 매매 칩 ──
function _dInjectNearbyStyle() {
  document.querySelectorAll('.nearby-item').forEach(el => {
    if (el.dataset.dStyled) return;
    el.dataset.dStyled = '1';
    const nameEl = el.querySelector('.nearby-name');
    if (nameEl) {
      const existing = nameEl.querySelector('span');
      if (existing) {
        nameEl.insertBefore(existing, nameEl.firstChild);
        existing.style.marginLeft = '0';
        existing.style.marginRight = '6px';
      } else {
        const tag = document.createElement('span');
        tag.textContent = '아파트';
        tag.style.cssText = 'display:inline-block;padding:1px 6px;margin-right:6px;border-radius:4px;background:#eef2ff;color:#4338ca;font-size:10px;font-weight:600;vertical-align:middle;';
        nameEl.insertBefore(tag, nameEl.firstChild);
      }
    }
    const priceEl = el.querySelector('.nearby-price');
    if (priceEl) priceEl.style.color = '#ea580c';
    const dateContainer = priceEl ? priceEl.nextElementSibling : null;
    if (dateContainer && !dateContainer.querySelector('.nearby-kind-d')) {
      const kindSpan = document.createElement('span');
      kindSpan.className = 'nearby-kind-d';
      kindSpan.textContent = '매매';
      kindSpan.style.cssText = 'display:inline-block;padding:2px 7px;border-radius:4px;background:#fff1e7;color:#c2410c;font-size:10.5px;font-weight:700;letter-spacing:0.2px;line-height:1.4;margin-right:8px;vertical-align:middle;';
      dateContainer.insertBefore(kindSpan, dateContainer.firstChild);
    }
  });
}

// ── D 변환: '단지 소개' info-row 섹션 inject (#map-section 다음) ──
function _dInjectDanjiInfo(d) {
  if (document.querySelector('#danji-info-d')) return;
  const mapSec = document.querySelector('#map-section');
  if (!mapSec) return;
  const rowMap = {};
  if (d.address) rowMap['소재지'] = esc(d.address);
  if (d.build_year) rowMap['준공'] = d.build_year + '년 · 공동주택';
  if (d.total_units) rowMap['세대수'] = d.total_units.toLocaleString() + '세대';
  if (d.top_floor) rowMap['최고층'] = '지상 ' + d.top_floor + '층';
  if (d.parking) {
    const pk = parseInt(d.parking, 10);
    if (pk > 0) {
      const ratio = d.total_units ? (pk / parseInt(d.total_units, 10)) : 0;
      const ratioStr = ratio > 0 ? ' (세대당 ' + ratio.toFixed(2) + '대)' : '';
      rowMap['주차'] = pk.toLocaleString() + '대' + ratioStr;
    }
  }
  if (d.heating) rowMap['난방'] = esc(d.heating);
  if (d.builder) rowMap['시공사'] = esc(d.builder);
  if (d.pyeongs_map && typeof d.pyeongs_map === 'object') {
    const exclus = Object.keys(d.pyeongs_map)
      .map(k => Math.round(parseFloat((d.pyeongs_map[k] || {}).exclu || k)))
      .filter(v => v > 0)
      .sort((a, b) => a - b);
    const uniq = [...new Set(exclus)];
    if (uniq.length) rowMap['전용면적'] = uniq.join('㎡, ') + '㎡';
  }
  if (Object.keys(rowMap).length === 0) return;

  const _row = (label, value, full) =>
    '<div style="' + (full ? 'grid-column:1 / -1;' : '') +
    'display:flex;gap:10px;align-items:baseline;padding:6px 0;border-bottom:1px solid #f1f3f5;">' +
    '<span style="color:#94a3b8;font-size:12px;flex-shrink:0;width:70px;">' + label + '</span>' +
    '<span style="color:#0a0e1a;font-size:13px;line-height:1.5;">' + value + '</span>' +
    '</div>';

  const html = [
    '<h2 class="section-title" style="padding:0 0 8px;font-size:15px;font-weight:700;color:#0a0e1a;margin:0;">단지 소개</h2>',
    '<dl style="display:grid;grid-template-columns:1fr 1fr;column-gap:24px;row-gap:0;margin:0 0 16px;padding:0;">',
  ];
  if (rowMap['소재지']) html.push(_row('소재지', rowMap['소재지'], true));
  ['준공', '세대수', '최고층', '주차', '난방', '시공사'].forEach(k => {
    if (rowMap[k]) html.push(_row(k, rowMap[k], false));
  });
  if (rowMap['전용면적']) html.push(_row('전용면적', rowMap['전용면적'], true));
  html.push('</dl>');

  // 시세 요약 토글
  const rt = d.recent_trade || {};
  const ath = d.all_time_high || {};
  const cats = d.categories || [];
  const bestCat = cats.find(c => rt[c] && rt[c].price) || cats[0] || '';
  const recentSale = bestCat ? rt[bestCat] : null;
  const highSale = bestCat ? ath[bestCat] : null;
  const summaryRows = [];
  if (recentSale && recentSale.price) {
    summaryRows.push('<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;"><span style="color:#94a3b8;">최근 매매</span><span style="color:#0a0e1a;font-weight:500;">' + _dFmtPrice(recentSale.price) + ' <span style=\'color:#94a3b8;font-size:12px;\'>(전용 ' + bestCat + '㎡' + (recentSale.date ? ' · ' + recentSale.date : '') + ')</span></span></div>');
  }
  if (highSale && highSale.price) {
    summaryRows.push('<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;"><span style="color:#94a3b8;">5년 최고</span><span style="color:#0a0e1a;font-weight:500;">' + _dFmtPrice(highSale.price) + (highSale.date ? ' <span style=\'color:#94a3b8;font-size:12px;\'>(' + highSale.date + ')</span>' : '') + '</span></div>');
  }
  const footParts = [];
  if (d.jeonse_rate) footParts.push('전세가율 ' + d.jeonse_rate + '%');
  const footStr = footParts.length ? '<div style="margin-top:6px;padding-top:8px;border-top:1px solid #f1f3f5;font-size:12px;color:#94a3b8;">' + footParts.join(' · ') + '</div>' : '';

  // 거래 통계
  const ph = d.price_history || {};
  let saleN = 0, jeonseN = 0, monthlyN = 0;
  for (const k in ph) {
    if (!Array.isArray(ph[k])) continue;
    const cnt = ph[k].length;
    if (k.endsWith('_jeonse')) jeonseN += cnt;
    else if (k.endsWith('_wolse')) monthlyN += cnt;
    else saleN += cnt;
  }
  const totalN = saleN + jeonseN + monthlyN;
  const tradeStat = totalN > 0
    ? '<p style="font-size:13px;color:#94a3b8;line-height:1.85;margin:0 0 10px;">최근 5년 동안 ' + esc(d.complex_name || '') + '에서는 총 ' + totalN.toLocaleString() + '건의 실거래가 집계되었으며, 매매 ' + saleN + '건, 전세 ' + jeonseN + '건, 월세 ' + monthlyN + '건이 신고되었습니다.</p>'
    : '';
  if (summaryRows.length || tradeStat) {
    html.push('<details style="margin:0 0 12px;"><summary style="cursor:pointer;font-size:12px;color:#94a3b8;padding:2px 0;list-style:none;display:inline-flex;align-items:center;gap:4px;"><span style="display:inline-block;transform:rotate(0deg);transition:transform .15s;">▸</span>시세 요약 · 거래 활성도 · 인근 인프라 자세히 보기</summary><div style="margin-top:8px;">' +
      (summaryRows.length ? '<div style="margin:0 0 14px;">' + summaryRows.join('') + footStr + '</div>' : '') +
      tradeStat +
      '</div></details><style>details[open] > summary > span{transform:rotate(90deg) !important;}</style>');
  }

  // 인근 단지 SEO 링크 문단
  const dongA = document.querySelector('.section a[href*="/dong/"]');
  const guA = document.querySelector('.section a[href*="/gu/"]');
  const dongHref = dongA ? dongA.getAttribute('href') : '';
  const guHref = guA ? guA.getAttribute('href') : '';
  const dongName = (d.location || '').split(' ').pop() || '';
  const guName = ((d.address || '').split(' ').find(t => t.endsWith('구'))) || ((d.location || '').split(' ')[0]) || '';
  const nearbyArr = (d.nearby_complex || []).filter(n => n.id && !n.id.startsWith('offi-') && !n.id.startsWith('apt-') && n.slug);
  const nearbyLinks = nearbyArr.slice(0, 2).map(n => {
    const nDong = (n.location || '').split(' ').pop();
    return '<a href="/danji/' + encodeURIComponent(n.slug) + '.html">' + (nDong ? esc(nDong) + ' ' : '') + esc(n.name) + ' 아파트</a>';
  }).join(', ');
  if (nearbyLinks && dongHref && dongName && guHref && guName) {
    html.push('<p style="font-size:13px;color:#94a3b8;line-height:1.85;margin:0;">인근 단지로는 ' + nearbyLinks + ' 등이 있으며, 같은 ' + esc(dongName) + ' 일대의 다른 단지는 <a href="' + dongHref + '">' + esc(guName) + ' ' + esc(dongName) + ' 아파트</a>, 시군구 단위 비교는 <a href="' + guHref + '">' + esc(guName) + ' 아파트 시세</a>에서 확인할 수 있습니다.</p>');
  }

  const sec = document.createElement('section');
  sec.id = 'danji-info-d';
  sec.className = 'seo-intro';
  sec.style.padding = '0 16px 16px';
  sec.innerHTML = html.join('');
  mapSec.insertAdjacentElement('afterend', sec);
}

// ── D 변환: FAQ 보강 (개수 늘림) — _enrichFaq from _make_preview.py ──
function _dEnrichFaq(d) {
  if (document.body.dataset.faqEnriched) return;
  const faqSec = document.querySelector('.faq-section');
  if (!faqSec) return;
  const nm = d.complex_name || '';
  const items = [];
  if (d.build_year && d.total_units) {
    items.push({ q: nm + '는 몇 년 준공, 몇 세대?', a: nm + '는 ' + d.build_year + '년 준공, 총 ' + d.total_units.toLocaleString() + '세대 규모입니다.' });
  }
  const ph = d.price_history || {};
  let saleN = 0, jeonseN = 0, monthlyN = 0;
  let jeonseSum = 0, jeonseCnt = 0;
  let monthlyDepositSum = 0, monthlyMonthlySum = 0, monthlyCnt = 0;
  for (const k in ph) {
    if (!Array.isArray(ph[k])) continue;
    const list = ph[k];
    if (k.endsWith('_jeonse')) {
      jeonseN += list.length;
      list.forEach(t => { if (t.price) { jeonseSum += t.price; jeonseCnt++; } });
    } else if (k.endsWith('_wolse')) {
      monthlyN += list.length;
      list.forEach(t => { if (t.price) { monthlyDepositSum += t.price; monthlyMonthlySum += (t.monthly || 0); monthlyCnt++; } });
    } else {
      saleN += list.length;
    }
  }
  if (saleN > 0) items.push({ q: nm + ' 매매 거래는 얼마나 활발?', a: '최근 5년 매매 ' + saleN + '건이 집계되었습니다.' });
  if (jeonseCnt > 0) {
    const avg = Math.round(jeonseSum / jeonseCnt);
    items.push({ q: nm + ' 전세 시세는?', a: '최근 5년 전세 실거래 ' + jeonseN + '건 평균 보증금은 ' + _dFmtPrice(avg) + '입니다.' });
  }
  if (monthlyCnt > 0) {
    const avgD = Math.round(monthlyDepositSum / monthlyCnt);
    const avgM = Math.round(monthlyMonthlySum / monthlyCnt);
    items.push({ q: nm + ' 월세 평균은?', a: '최근 5년 월세 실거래 ' + monthlyN + '건 평균은 보증금 ' + _dFmtPrice(avgD) + ' / 월세 ' + avgM + '만입니다.' });
  }
  if (d.top_floor) items.push({ q: nm + ' 최고층은?', a: '지상 ' + d.top_floor + '층 규모입니다.' });
  if (d.build_year) {
    const age = (new Date().getFullYear() - d.build_year);
    if (age >= 0 && age <= 5) items.push({ q: nm + ' 신축 아파트인가요?', a: nm + '는 ' + d.build_year + '년 준공으로 ' + (age + 1) + '년차 신축 아파트입니다.' });
    else if (age > 25) items.push({ q: nm + ' 노후 아파트인가요?', a: nm + '는 ' + d.build_year + '년 준공으로 ' + age + '년차 단지입니다.' });
  }
  if (d.jeonse_rate) {
    const rt2 = d.recent_trade || {};
    const cats2 = d.categories || [];
    const bc2 = cats2.find(c => rt2[c] && rt2[c].price) || cats2[0];
    const sale = bc2 ? rt2[bc2] : null;
    const jeo = bc2 ? rt2[bc2 + '_jeonse'] : null;
    if (sale && sale.price && jeo && jeo.price) {
      items.push({ q: nm + ' 전세가가 매매가 대비 얼마나?', a: '최근 매매가 ' + _dFmtPrice(sale.price) + ', 최근 전세가 ' + _dFmtPrice(jeo.price) + '로, 전세가율은 약 ' + d.jeonse_rate + '%입니다.' });
    }
  }
  const locParts = (d.location || '').split(' ');
  const dongName = locParts[locParts.length - 1] || '';
  const guName = ((d.address || '').split(' ').find(t => t.endsWith('구'))) || (locParts[0] || '');
  if (dongName && guName) {
    items.push({ q: dongName + ' 아파트 중에 ' + nm + '만한 단지가 있나요?', a: dongName + '에는 ' + nm + ' 외에도 여러 단지가 있습니다. ' + guName + ' ' + dongName + ' 아파트 전체 목록과 시세 비교가 가능합니다.' });
  }
  if (!items.length) return;
  const html = items.map(it => '<div class="faq-item"><div class="faq-q">' + esc(it.q) + '</div><div class="faq-a">' + esc(it.a) + '</div></div>').join('');
  const last = faqSec.querySelectorAll('.faq-item');
  if (last.length) last[last.length - 1].insertAdjacentHTML('afterend', html);
  else faqSec.insertAdjacentHTML('beforeend', html);
  document.body.dataset.faqEnriched = '1';
}

// ── D 변환: 가격 카드 onclick 제거 (smooth scroll 트리거 차단) ──
function _dDisableCardClick() {
  document.querySelectorAll('.price-card').forEach(c => {
    if (c.dataset.dDisabled) return;
    c.removeAttribute('onclick');
    c.removeAttribute('ontouchstart');
    c.removeAttribute('ontouchend');
    c.style.cursor = 'default';
    c.dataset.dDisabled = '1';
  });
}

// ── D 변환: 지도 — 카카오맵 링크 제거 + 지도 자체 클릭 → 풀화면 새창 ──
function _dPatchMap() {
  if (document.body.dataset.mapPatched) return;
  const mapSec = document.getElementById('map-section');
  if (!mapSec) return;
  const mapEl = mapSec.querySelector('#danji-map');
  const link = mapSec.querySelector('a[href*="map.kakao.com"]');
  if (!mapEl || !link) return;
  const href = link.getAttribute('href');
  link.remove();
  mapEl.style.cursor = 'pointer';
  mapEl.title = '카카오맵에서 자세히 보기';
  mapEl.addEventListener('click', () => window.open(href, '_blank', 'noopener'));
  document.body.dataset.mapPatched = '1';
}

// ── D 변환: 하단 SEO 영역 정리 (CTA 제거 + .seo-text 제거 + 데이터 안내 펼침 + 신고 버튼) ──
function _dPatchSeo() {
  if (document.body.dataset.seoPatched) return;
  document.querySelectorAll('.cta-section').forEach(e => e.remove());
  const seoSec = document.querySelector('.seo-section');
  if (!seoSec) return;
  const seoText = seoSec.querySelector('.seo-text');
  if (seoText) seoText.remove();
  const details = seoSec.querySelector('details');
  if (details) {
    details.setAttribute('open', '');
    details.style.fontSize = '12px';
    details.style.color = 'var(--sub)';
    details.innerHTML =
      '<summary style="cursor:pointer;">데이터 안내</summary>' +
      '<div style="margin-top:6px;line-height:1.8;">' +
      '<b>실거래가</b>: 국토교통부 실거래가 공개시스템 (<a href="https://rt.molit.go.kr/" target="_blank" rel="noopener nofollow">rt.molit.go.kr</a>) · 매일 자동 수집<br>' +
      '<b>건축정보</b>: 국토교통부 건축물대장 (전유부 · 총괄표제부)<br>' +
      '<b>세대 수</b>: 건축물대장 전유부 등기 기준 (분양 공급 수치와 다를 수 있음)<br>' +
      '공급면적이 확인되지 않은 단지는 전용면적만 표시합니다<br>' +
      '거래 취소·정정 건은 반영이 지연될 수 있습니다' +
      '</div>';
  }
  const reportBtn = seoSec.querySelector('button[onclick*="openReportModal"]');
  if (reportBtn) {
    reportBtn.textContent = '데이터 오류 신고';
    reportBtn.style.cssText = 'background:none;border:1px solid var(--border,#e5e7eb);border-radius:20px;color:var(--sub,#6b7280);font-size:12px;cursor:pointer;padding:6px 16px;';
  }
  document.body.dataset.seoPatched = '1';
}

// ── D 변환: FAQ split (visible 4 + hidden + 더보기) ──
function _dSplitFaq() {
  if (document.body.dataset.faqSplit) return;
  const faqSec = document.querySelector('.faq-section');
  if (!faqSec) return;
  const items = Array.from(faqSec.querySelectorAll('.faq-item'));
  if (items.length <= 4) return;
  items.forEach(it => it.parentNode && it.parentNode.removeChild(it));
  faqSec.querySelectorAll('.faq-list-visible, .faq-list-hidden, .faq-more').forEach(e => e.remove());
  const visible = document.createElement('div');
  visible.className = 'faq-list-visible';
  const hidden = document.createElement('div');
  hidden.className = 'faq-list-hidden';
  hidden.id = 'faq-hidden';
  items.forEach((it, i) => {
    if (i < 4) visible.appendChild(it);
    else hidden.appendChild(it);
  });
  const title = faqSec.querySelector('.section-title');
  if (title) {
    title.insertAdjacentElement('afterend', hidden);
    title.insertAdjacentElement('afterend', visible);
  } else {
    faqSec.appendChild(visible);
    faqSec.appendChild(hidden);
  }
  const more = document.createElement('div');
  more.className = 'faq-more';
  more.textContent = '더보기';
  more.onclick = () => { hidden.classList.toggle('expanded'); more.style.display = 'none'; };
  faqSec.appendChild(more);
  document.body.dataset.faqSplit = '1';
}

// ── D 변환: 자주 묻는 질문을 '더 알아보기' 다음으로 이동 ──
function _dReorderFaq() {
  if (document.body.dataset.faqMoved) return;
  const faqSec = document.querySelector('.faq-section');
  if (!faqSec) return;
  const moreSec = Array.from(document.querySelectorAll('.section')).find(s => {
    const t = s.querySelector('.section-title');
    return t && t.textContent.trim() === '더 알아보기';
  });
  if (!moreSec) return;
  moreSec.insertAdjacentElement('afterend', faqSec);
  document.body.dataset.faqMoved = '1';
}

// ── D 변환: footer inject (#app 끝, 또는 body 끝) ──
function _dInjectFooter() {
  if (document.querySelector('#hwik-d-footer')) return;
  const footer = document.createElement('footer');
  footer.id = 'hwik-d-footer';
  footer.style.cssText = 'max-width:600px;margin:24px auto 40px;padding:24px 16px 0;border-top:1px solid var(--border,#e5e7eb);text-align:center;font-size:11.5px;color:var(--sub,#6b7280);line-height:1.7;';
  footer.innerHTML =
    '<div style="margin-bottom:8px;">' +
    '<a href="/about.html" style="color:var(--sub,#6b7280);text-decoration:none;margin:0 8px;">휙 소개</a>·' +
    '<a href="/privacy.html" style="color:var(--sub,#6b7280);text-decoration:none;margin:0 8px;">개인정보처리방침</a>·' +
    '<a href="/terms.html" style="color:var(--sub,#6b7280);text-decoration:none;margin:0 8px;">이용약관</a>' +
    '</div>' +
    '<div style="color:var(--muted,#9ca3af);">실거래가 출처: 국토교통부 · 휙(HWIK) · ' +
    '<a href="https://hwik.kr" style="color:var(--muted,#9ca3af);text-decoration:none;">hwik.kr</a></div>';
  const app = document.getElementById('app');
  if (app && app.parentNode) app.parentNode.insertBefore(footer, app.nextSibling);
  else document.body.appendChild(footer);
}

// ── D 변환: SPA 의 .tags → D 의 .location-section 으로 변환 (헤더 우측 컬럼) ──
function _dExtractLocationSection() {
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
        if (name) subway.push({ line, name, time });
      });
    } else {
      // SPA 는 학교에도 .station-tag 클래스 재사용 (app.js render())
      tl.querySelectorAll('.station-tag').forEach(s => {
        const spans = s.querySelectorAll('span');
        const typ = spans[0]?.textContent?.trim() || '';
        const name = spans[1]?.textContent?.trim() || '';
        const time = spans[2]?.textContent?.trim() || '';
        if (name) school.push({ typ, name, time });
      });
    }
  });
  function walkMinNum(s) {
    const m = (s || '').match(/(\d+)\s*분/);
    return m ? parseInt(m[1], 10) : 999;
  }
  // 지하철 도보 15분 이내 + 호선 중복 제거
  const seenLines = new Set();
  const subwayFinal = [];
  for (const s of subway) {
    if (walkMinNum(s.time) > 15) continue;
    if (seenLines.has(s.line)) continue;
    seenLines.add(s.line);
    subwayFinal.push(s);
  }
  // 학교 도보 15분 + 중복 제거
  const seenSchools = new Set();
  const schoolFinal = [];
  for (const s of school) {
    if (walkMinNum(s.time) > 15) continue;
    const key = s.typ + ':' + s.name;
    if (seenSchools.has(key)) continue;
    seenSchools.add(key);
    schoolFinal.push(s);
  }
  if (!subwayFinal.length && !schoolFinal.length) return;
  const sec = document.createElement('div');
  sec.className = 'location-section';
  const rows = [];
  // 호선 색상 (D 디자인 공식 — render() 의 lineColor 와 동일 로직)
  const _LC = {
    '1호선':'#0052A4','2호선':'#00A84D','3호선':'#EF7C1C','4호선':'#00A4E3',
    '5호선':'#996CAC','6호선':'#CD7C2F','7호선':'#747F00','8호선':'#E6186C',
    '9호선':'#BDB092',
    '경의중앙선':'#77C4A3','수인분당선':'#FABE00','신분당선':'#D4003B',
    '공항철도':'#0090D2','GTX-A':'#9A6292','우이신설선':'#B0CE18',
    '신림선':'#6789CA','경춘선':'#0C8E72','김포골드라인':'#A17E46',
    '인천1호선':'#7CA8D5','인천2호선':'#ED8B00',
  };
  const _lineColor = (line) => {
    if (!line) return '#94a3b8';
    for (const k in _LC) { if (line.includes(k) || k.includes(line)) return _LC[k]; }
    return '#94a3b8';
  };
  if (subwayFinal.length) {
    const items = subwayFinal.map(s => {
      const c = _lineColor(s.line);
      const tip = `${s.line} ${s.name} 도보 ${s.time}`.replace(/"/g, '&quot;');
      return `<span class="loc-item" title="${tip}"><span class="line-badge" style="background:${c};">${esc(s.line)}</span><span class="nm">${esc(s.name)}</span><span class="mn">${esc(s.time)}</span></span>`;
    }).join('');
    rows.push(`<div class="loc-row"><div class="loc-items">${items}</div></div>`);
  }
  if (schoolFinal.length) {
    const items = schoolFinal.map(s => {
      const tip = `${s.typ} ${s.name} 도보 ${s.time}`.replace(/"/g, '&quot;');
      return `<span class="loc-item" title="${tip}"><span class="type-badge" data-type="${esc(s.typ)}">${esc(s.typ)}</span><span class="nm">${esc(s.name)}</span><span class="mn">${esc(s.time)}</span></span>`;
    }).join('');
    rows.push(`<div class="loc-row"><div class="loc-items">${items}</div></div>`);
  }
  sec.innerHTML = rows.join('');
  // 데스크톱(≥768px): 헤더 우측 컬럼 / 모바일: 헤더 뒤
  if (window.matchMedia('(min-width: 768px)').matches) {
    header.appendChild(sec);
  } else {
    header.insertAdjacentElement('afterend', sec);
  }
}

// ── D 디자인 변환 통합 함수 (render() 끝에서 호출) ──
// 각 변환 함수를 try-catch 로 격리 — 한 함수가 throw 해도 나머지 진행, 페이지 깨짐 방지
function applyDDesign(d) {
  if (!d) return;
  const _safe = (name, fn) => { try { fn(); } catch (e) { console.error('[applyDDesign]', name, e); } };
  _safe('extractLocationSection', () => _dExtractLocationSection());
  _safe('disableCardClick',       () => _dDisableCardClick());
  _safe('injectTradeKindBadge',   () => _dInjectTradeKindBadge());
  _safe('injectNearbyStyle',      () => _dInjectNearbyStyle());
  _safe('injectDanjiInfo',        () => _dInjectDanjiInfo(d));
  _safe('enrichFaq',              () => _dEnrichFaq(d));
  _safe('reorderFaq',             () => _dReorderFaq());
  _safe('patchMap',               () => _dPatchMap());
  _safe('splitFaq',               () => _dSplitFaq());
  _safe('patchSeo',               () => _dPatchSeo());
  _safe('injectFooter',           () => _dInjectFooter());
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
      // 가격 + 거래일: 어떤 면적이든 가장 최근 매매가
      let price = null, area = null, date = null;
      for (const c of cats) {
        if (rt[c] && rt[c].price) { price = rt[c].price; area = c; date = rt[c].date || null; break; }
      }
      if (!price) return '';
      const distKm = n.dist < 1 ? Math.round(n.dist * 1000) + 'm' : n.dist.toFixed(1) + 'km';
      return `<a class="nearby-item" href="/danji/${encodeURIComponent(makeSlug(n.complex_name, n.location, n.id, parentMetro && n.location ? (parentMetro + ' ' + n.location) : ''))}" style="text-decoration:none;color:inherit;">
        <div>
          <div class="nearby-name">${esc(n.complex_name)}</div>
          <div class="nearby-sub">${esc(n.location)} · ${distKm}${area ? ' · 전용 '+area+'㎡' : ''}</div>
        </div>
        <div style="text-align:right">
          <div class="nearby-price">${formatPrice(price)}</div>
          <div style="font-size:10px;color:var(--muted);margin-top:2px;">${date ? esc(date) : ''}</div>
        </div>
      </a>`;
    }).join('');

    listEl.insertAdjacentHTML('beforeend', html);
    if (labelEl && !existing) labelEl.textContent = '거리순 (면적 무관)';
    else if (labelEl && existing) labelEl.textContent += ' + 거리순';
    // 추가된 nearby-item 들에도 D 디자인 (보라 뱃지 + 매매 칩) 적용
    try { _dInjectNearbyStyle(); } catch (e) { console.error('[fillNearbyIfNeeded] inject', e); }
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
loadData().catch(() => { showError('일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.'); });