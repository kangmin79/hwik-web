import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// ========== 좌표 사전: 서울시 구/동 중심좌표 ==========
const DISTRICT_COORDS: Record<string, { lat: number; lng: number; radius: number }> = {
  // 구 단위 (반경 2.5km)
  '강남': { lat: 37.497, lng: 127.028, radius: 2.5 },
  '서초': { lat: 37.483, lng: 127.009, radius: 2.5 },
  '마포': { lat: 37.554, lng: 126.910, radius: 2.5 },
  '용산': { lat: 37.532, lng: 126.979, radius: 2.5 },
  '성동': { lat: 37.563, lng: 127.037, radius: 2.5 },
  '송파': { lat: 37.514, lng: 127.106, radius: 2.5 },
  '영등포': { lat: 37.526, lng: 126.896, radius: 2.5 },
  '강서': { lat: 37.551, lng: 126.849, radius: 2.5 },
  '노원': { lat: 37.654, lng: 127.056, radius: 2.5 },
  '관악': { lat: 37.478, lng: 126.951, radius: 2.5 },
  '동작': { lat: 37.497, lng: 126.939, radius: 2.5 },
  '광진': { lat: 37.538, lng: 127.082, radius: 2.5 },
  '종로': { lat: 37.573, lng: 126.979, radius: 2.5 },
  '중구': { lat: 37.563, lng: 126.997, radius: 2.5 },
  '강동': { lat: 37.530, lng: 127.124, radius: 2.5 },
  '강북': { lat: 37.640, lng: 127.011, radius: 2.5 },
  '구로': { lat: 37.495, lng: 126.858, radius: 2.5 },
  '금천': { lat: 37.457, lng: 126.895, radius: 2.5 },
  '도봉': { lat: 37.669, lng: 127.032, radius: 2.5 },
  '동대문': { lat: 37.574, lng: 127.040, radius: 2.5 },
  '서대문': { lat: 37.579, lng: 126.937, radius: 2.5 },
  '성북': { lat: 37.589, lng: 127.017, radius: 2.5 },
  '양천': { lat: 37.517, lng: 126.867, radius: 2.5 },
  '은평': { lat: 37.603, lng: 126.929, radius: 2.5 },
  '중랑': { lat: 37.607, lng: 127.093, radius: 2.5 },
  // 동/유명지역 단위 (반경 1.2km)
  '역삼': { lat: 37.500, lng: 127.036, radius: 1.2 },
  '삼성': { lat: 37.509, lng: 127.063, radius: 1.2 },
  '청담': { lat: 37.520, lng: 127.048, radius: 1.2 },
  '대치': { lat: 37.494, lng: 127.058, radius: 1.2 },
  '논현': { lat: 37.511, lng: 127.022, radius: 1.2 },
  '신사': { lat: 37.524, lng: 127.023, radius: 1.2 },
  '압구정': { lat: 37.527, lng: 127.028, radius: 1.2 },
  '개포': { lat: 37.478, lng: 127.052, radius: 1.2 },
  '도곡': { lat: 37.488, lng: 127.042, radius: 1.2 },
  '잠실': { lat: 37.513, lng: 127.100, radius: 1.5 },
  '가락': { lat: 37.497, lng: 127.118, radius: 1.2 },
  '문정': { lat: 37.486, lng: 127.122, radius: 1.2 },
  '석촌': { lat: 37.506, lng: 127.107, radius: 1.2 },
  '여의도': { lat: 37.525, lng: 126.924, radius: 1.5 },
  '당산': { lat: 37.534, lng: 126.902, radius: 1.2 },
  '합정': { lat: 37.549, lng: 126.914, radius: 1.2 },
  '망원': { lat: 37.556, lng: 126.905, radius: 1.2 },
  '연남': { lat: 37.560, lng: 126.921, radius: 1.2 },
  '서교': { lat: 37.551, lng: 126.919, radius: 1.2 },
  '상수': { lat: 37.548, lng: 126.923, radius: 1.2 },
  '공덕': { lat: 37.544, lng: 126.952, radius: 1.2 },
  '성수': { lat: 37.544, lng: 127.056, radius: 1.2 },
  '옥수': { lat: 37.540, lng: 127.017, radius: 1.2 },
  '왕십리': { lat: 37.561, lng: 127.037, radius: 1.2 },
  '이태원': { lat: 37.534, lng: 126.994, radius: 1.2 },
  '한남': { lat: 37.534, lng: 127.003, radius: 1.2 },
  '반포': { lat: 37.508, lng: 127.000, radius: 1.2 },
  '방배': { lat: 37.481, lng: 126.988, radius: 1.2 },
  '양재': { lat: 37.472, lng: 127.013, radius: 1.2 },
  '잠원': { lat: 37.515, lng: 127.005, radius: 1.2 },
  // 서초는 구 단위(2.5km)로 이미 등록 — 동 단위 중복 제거
  '노량진': { lat: 37.513, lng: 126.942, radius: 1.2 },
  '상도': { lat: 37.503, lng: 126.953, radius: 1.2 },
  '흑석': { lat: 37.508, lng: 126.963, radius: 1.2 },
  '사당': { lat: 37.476, lng: 126.982, radius: 1.2 },
  '신림': { lat: 37.484, lng: 126.930, radius: 1.2 },
  '봉천': { lat: 37.482, lng: 126.942, radius: 1.2 },
  '화곡': { lat: 37.541, lng: 126.839, radius: 1.2 },
  '마곡': { lat: 37.560, lng: 126.827, radius: 1.2 },
  '발산': { lat: 37.549, lng: 126.838, radius: 1.2 },
  '등촌': { lat: 37.551, lng: 126.856, radius: 1.2 },
  '상계': { lat: 37.659, lng: 127.068, radius: 1.2 },
  '중계': { lat: 37.648, lng: 127.068, radius: 1.2 },
  '천호': { lat: 37.538, lng: 127.124, radius: 1.2 },
  '길동': { lat: 37.533, lng: 127.140, radius: 1.2 },
  '둔촌': { lat: 37.524, lng: 127.136, radius: 1.2 },
  '고덕': { lat: 37.556, lng: 127.154, radius: 1.2 },
  '혜화': { lat: 37.582, lng: 127.002, radius: 1.2 },
  '명동': { lat: 37.564, lng: 126.982, radius: 1.2 },
  '목동': { lat: 37.527, lng: 126.875, radius: 1.5 },
  '구의': { lat: 37.538, lng: 127.086, radius: 1.2 },
  '자양': { lat: 37.535, lng: 127.073, radius: 1.2 },
};

// 하버사인 거리 계산 (km)
function haversineDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ========== 0. 로컬 빠른 파서 (Claude 없이 즉시 처리) ==========
function localParseQuery(query: string) {
  const q = query.trim();
  const filters: Record<string, any> = {};
  let semantic: string | null = null;
  let features: string[] | null = null;
  let remaining = q;

  // 거래유형
  const tradeTypes: Record<string, string> = { '매매': '매매', '전세': '전세', '월세': '월세' };
  for (const [keyword, value] of Object.entries(tradeTypes)) {
    if (q.includes(keyword)) { filters.trade_type = value; remaining = remaining.replace(keyword, ''); break; }
  }

  // 매물 카테고리
  const categoryMap: Record<string, string> = {
    '아파트': 'apartment', 'apt': 'apartment',
    '오피스텔': 'officetel',
    '원룸': 'room', '투룸': 'room', '쓰리룸': 'room', '빌라': 'room', '주택': 'room',
    '상가': 'commercial', '점포': 'commercial', '매장': 'commercial',
    '사무실': 'office', '오피스': 'office',
  };
  for (const [keyword, value] of Object.entries(categoryMap)) {
    if (q.includes(keyword)) { filters.property_type = value; remaining = remaining.replace(keyword, ''); break; }
  }

  // 방 수
  const roomMatch = q.match(/(원룸|1룸|스튜디오|투룸|2룸|쓰리룸|3룸|방\s*(\d))/);
  if (roomMatch) {
    if (roomMatch[0].includes('원') || roomMatch[0].includes('1') || roomMatch[0].includes('스튜')) filters.rooms = 1;
    else if (roomMatch[0].includes('투') || roomMatch[0].includes('2')) filters.rooms = 2;
    else if (roomMatch[0].includes('쓰리') || roomMatch[0].includes('3')) filters.rooms = 3;
    else if (roomMatch[2]) filters.rooms = parseInt(roomMatch[2]);
  }

  // 지역 (구/동/역/유명지역)
  const guList = [
    '강남','서초','마포','용산','성동','송파','영등포','강서','노원','관악',
    '동작','광진','종로','중구','강동','강북','구로','금천','도봉','동대문',
    '서대문','성북','양천','은평','중랑'
  ];
  // 유명 지역명 (동이 안 붙는 이름들)
  const knownPlaces: Record<string, string> = {
    '잠실': '잠실', '여의도': '여의도', '성수': '성수', '합정': '합정', '망원': '망원',
    '연남': '연남', '이태원': '이태원', '한남': '한남', '청담': '청담', '압구정': '압구정',
    '삼성': '삼성', '대치': '대치', '역삼': '역삼', '논현': '논현', '신사': '신사',
    '반포': '반포', '방배': '방배', '양재': '양재', '잠원': '잠원',
    '서교': '서교', '상수': '상수', '공덕': '공덕', '옥수': '옥수', '왕십리': '왕십리',
    '가락': '가락', '문정': '문정', '석촌': '석촌', '당산': '당산',
    '화곡': '화곡', '마곡': '마곡', '발산': '발산', '등촌': '등촌',
    '상계': '상계', '중계': '중계', '신림': '신림', '봉천': '봉천',
    '노량진': '노량진', '상도': '상도', '흑석': '흑석', '사당': '사당',
    '구의': '구의', '자양': '자양', '천호': '천호', '길동': '길동', '둔촌': '둔촌', '고덕': '고덕',
    '혜화': '혜화', '평창': '평창', '명동': '명동', '신당': '신당',
    '개포': '개포', '도곡': '도곡', '목동': '목동',
  };
  // 동 단위 (XX동) — 구 이름(성동, 강동 등)은 제외
  const dongMatch = q.match(/([\uAC00-\uD7A3]{1,4})동(?:\s|$)/);
  if (dongMatch) {
    const dongBase = dongMatch[1]; // "성" from "성동", "역삼" from "역삼동"
    const fullText = dongBase + '동'; // "성동", "역삼동"
    // Skip if this is a 구 name (성동구, 강동구 etc.)
    if (!guList.includes(fullText)) {
      filters.location = dongBase;
      remaining = remaining.replace(dongMatch[0], '');
    }
  }
  // 유명 지역명
  if (!filters.location) {
    for (const [place, locName] of Object.entries(knownPlaces)) {
      if (q.includes(place)) {
        filters.location = locName;
        remaining = remaining.replace(place, '');
        break;
      }
    }
  }
  // 구 단위
  if (!filters.location) {
    for (const gu of guList) {
      const guRegex = new RegExp(gu + '(?:구)?(?:\\s|$)');
      if (guRegex.test(q) || q.includes(gu)) {
        filters.location = gu;
        remaining = remaining.replace(new RegExp(gu + '구?'), '');
        break;
      }
    }
  }

  // 역/학교 근처
  const nearbyMatch = q.match(/([\uAC00-\uD7A3]+)(역|대학교|대학|학교|초등|중학|고등)\s*(근처|주변|앞)?/);
  if (nearbyMatch) {
    filters.nearby = nearbyMatch[1] + nearbyMatch[2];
    filters.nearby_type = nearbyMatch[2] === '역' ? 'subway' : 'school';
    if (!filters.location) filters.location = nearbyMatch[1];
  }

  // 가격 파싱
  const isWolse = filters.trade_type === '월세';
  const pricePatterns = [
    // "3억5천" / "3억" / "5천" / "1000" / "2000만원"
    { regex: /(\d+)\s*억\s*(\d+)?\s*천?/, parse: (m: RegExpMatchArray) => (parseInt(m[1]) * 10000) + (m[2] ? parseInt(m[2]) * 1000 : 0) },
    { regex: /(\d+)\s*천\s*만?\s*원?/, parse: (m: RegExpMatchArray) => parseInt(m[1]) * 1000 },
    { regex: /(\d{3,})(?:\s*만?\s*원?)?/, parse: (m: RegExpMatchArray) => parseInt(m[1]) },
    // 소액 (월세금): "80", "50", "100" (만원 단위, 1~999)
    { regex: /(\d{1,3})(?:\s*만?\s*원?)?\s*(?:이하|이상|미만|초과)/, parse: (m: RegExpMatchArray) => parseInt(m[1]) },
  ];

  let priceValue: number | null = null;
  for (const pp of pricePatterns) {
    const pm = q.match(pp.regex);
    if (pm) { priceValue = pp.parse(pm); break; }
  }

  if (priceValue !== null) {
    if (/이하|미만|아래|까지/.test(q)) {
      filters.max_price = priceValue;
    } else if (/이상|초과|넘는|부터/.test(q)) {
      filters.min_price = priceValue;
    } else if (/정도|쯤|근처|내외/.test(q) && !/역|학교|대학/.test(q)) {
      filters.min_price = Math.round(priceValue * 0.85);
      filters.max_price = Math.round(priceValue * 1.15);
    } else {
      // 가격만 단독이면 max_price로 처리
      filters.max_price = priceValue;
    }
  }

  // 범위 가격: "1억 이상 3억 이하" / "5억~7억"
  const rangeMatch = q.match(/(\d+)\s*억?\s*~\s*(\d+)\s*억/);
  if (rangeMatch) {
    filters.min_price = parseInt(rangeMatch[1]) * 10000;
    filters.max_price = parseInt(rangeMatch[2]) * 10000;
  }
  const rangeMatch2 = q.match(/(\d+)\s*억.*이상.*(\d+)\s*억.*이하/);
  if (rangeMatch2) {
    filters.min_price = parseInt(rangeMatch2[1]) * 10000;
    filters.max_price = parseInt(rangeMatch2[2]) * 10000;
  }

  // 면적 - only apply 이하/이상 to area if there's no price keyword nearby
  const areaMatch = q.match(/(\d+)\s*평/);
  if (areaMatch) {
    const pyeong = parseInt(areaMatch[1]);
    const afterArea = q.slice(q.indexOf(areaMatch[0]) + areaMatch[0].length);
    const hasPrice = /\d+\s*억|천|만원|\d{3,}/.test(q.replace(areaMatch[0], ''));
    if (/대/.test(afterArea.slice(0, 3))) {
      filters.min_area = pyeong;
      filters.max_area = pyeong + 9;
    } else if (/이상/.test(afterArea.slice(0, 5)) && !hasPrice) {
      filters.min_area = pyeong;
    } else if (/이하/.test(afterArea.slice(0, 5)) && !hasPrice) {
      filters.max_area = pyeong;
    } else {
      // Default: ±3평 range
      filters.min_area = pyeong - 3;
      filters.max_area = pyeong + 3;
    }
  }

  // 특징 (features)
  const featureKeywords: Record<string, string> = {
    '올수리': '올수리', '풀옵션': '풀옵션', '풀옵': '풀옵션',
    '남향': '남향', '동향': '동향', '서향': '서향', '북향': '북향', '남동향': '남동향', '남서향': '남서향',
    '역세권': '역세권', '주차': '주차가능', '주차가능': '주차가능',
    '한강뷰': '한강뷰', '시티뷰': '시티뷰', '공원뷰': '공원뷰',
    '신축': '신축', '복층': '복층', '루프탑': '루프탑', '옥상': '루프탑',
    '테라스': '테라스', '베란다확장': '베란다확장',
    '애견가능': '애견가능', '반려동물': '애견가능', '강아지': '애견가능', '펫': '애견가능',
    '즉시입주': '즉시입주', '바로입주': '즉시입주', '빠른입주': '즉시입주',
    '학군': '학군', '학교': '학군', '교육': '학군',
    '엘리베이터': '엘리베이터', '고층': '고층', '저층': '저층',
  };
  const foundFeatures: string[] = [];
  for (const [keyword, tag] of Object.entries(featureKeywords)) {
    if (q.includes(keyword) && !foundFeatures.includes(tag)) {
      foundFeatures.push(tag);
      remaining = remaining.replace(keyword, '');
    }
  }
  if (foundFeatures.length > 0) features = foundFeatures;

  // 단지명 (아파트 브랜드)
  const aptBrands = ['래미안','자이','힐스테이트','푸르지오','더샵','아이파크','롯데캐슬',
    'e편한세상','SK뷰','엘크루','포레나','트리지움','리센츠','헬리오시티','파크리오',
    '센트레빌','두산위브','한화포레나','금호어울림'];
  for (const brand of aptBrands) {
    if (q.includes(brand)) {
      if (!filters.property_type) filters.property_type = 'apartment';
      semantic = brand;
      break;
    }
  }

  // 거래상태
  if (/계약가능|거래가능/.test(q)) filters.trade_status = '계약가능';
  else if (/계약중|거래중|진행중/.test(q)) filters.trade_status = '계약중';
  else if (/완료|거래완료|계약완료/.test(q)) filters.trade_status = '완료';

  // 정렬
  if (/최신|최근|새로운/.test(q)) filters.sort = 'newest';
  else if (/싼|저렴|낮은/.test(q)) filters.sort = 'price_asc';
  else if (/비싼|높은/.test(q)) filters.sort = 'price_desc';

  // 날짜
  if (/오늘/.test(q)) filters.date_filter = 'today';
  else if (/어제/.test(q)) filters.date_filter = 1;
  else if (/이번\s?주|금주/.test(q)) filters.date_filter = 'week';
  else if (/이번\s?달|이달/.test(q)) filters.date_filter = 'month';
  else { const dayMatch = q.match(/최근\s*(\d+)\s*일/); if (dayMatch) filters.date_filter = parseInt(dayMatch[1]); }

  // semantic 텍스트 (남은 의미 키워드를 벡터 검색에 사용)
  remaining = remaining.replace(/[이하이상미만초과근처주변앞까지부터정도쯤내외]/g, '').replace(/\d+억?\s*천?\s*만?\s*원?/g, '').trim();
  if (!semantic && remaining.length >= 2) semantic = remaining;

  // 필터가 하나라도 있으면 로컬 파싱 성공
  const hasFilters = Object.keys(filters).length > 0 || features !== null;

  return hasFilters ? { semantic, filters, features, _local: true } : null;
}

// ========== 1. Claude Haiku로 검색어 파싱 ==========
async function parseSearchQuery(query, anthropicKey) {
  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': anthropicKey,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: 'claude-3-5-haiku-20241022',
        max_tokens: 512,
        messages: [{
          role: 'user',
          content: `부동산 매물 검색어를 분석해서 JSON으로 반환해주세요.

■ 중요: 반드시 JSON만 반환하고, 다른 설명은 하지 마세요.

■ 분석할 항목:
1. semantic: 벡터 검색이 필요한 의미적 키워드
2. filters: SQL 필터로 정확히 처리할 조건들
3. features: 정확 매칭이 필요한 매물 특성 태그들

■ 가격 변환 (만원 단위): "3억"→30000, "3억5천"→35000, "1000만원"→1000
■ "3억 정도/쯤/근처" → min_price: 25000, max_price: 35000 (±15% 범위)
■ "5억~7억" → min_price: 50000, max_price: 70000
■ "3억 이하/미만/아래/까지" → max_price: 30000 (min_price는 null)
■ "3억 이상/초과/넘는/부터" → min_price: 30000 (max_price는 null)

■ 월세 가격:
- "월세 50만원 이하" → trade_type: "월세", max_price: 50 (월세금 기준)
- "보증금 1억 월세 100" → trade_type: "월세", deposit: 10000, max_price: 100
- 일반 매매/전세는 기존대로 처리

■ 거래유형: "매매", "전세", "월세"
■ 매물유형: "apartment", "officetel", "room", "commercial", "office"

■ 거래상태 (trade_status):
- "계약가능/계약가능한/거래가능/활성/available" → "계약가능"
- "계약중/거래중/진행중" → "계약중"
- "완료/거래완료/계약완료" → "완료"
- 언급 없으면 null (전체)

■ 날짜 필터 (date_filter):
- "오늘/오늘 등록" → "today"
- "어제/어제 등록" → 1
- "이번주/이번 주/금주" → "week"
- "이번달/이번 달/이달" → "month"
- "최근 3일/3일 이내" → 3 (숫자)
- "최근 일주일" → 7
- "최근 한달" → 30
- 언급 없으면 null

■ 면적 필터:
- "20평대" → min_area: 20, max_area: 29
- "30평 이상" → min_area: 30
- "10~20평" → min_area: 10, max_area: 20
- 언급 없으면 null

■ 방 수 필터:
- "원룸/1룸/스튜디오" → rooms: 1, property_type도 "room"으로
- "투룸/2룸" → rooms: 2
- "쓰리룸/3룸/방3개" → rooms: 3
- 언급 없으면 null

■ 정렬 (sort):
- "최신순/최근/새로운" → "newest"
- "가격 낮은순/싼순/저렴한" → "price_asc"
- "가격 높은순/비싼" → "price_desc"
- "조회 많은/인기순/많이 본" → "views"
- 언급 없으면 null (유사도 기본)

■ features 태그: 애견가능, 풀옵션, 올수리, 루프탑, 테라스, 남향, 동향, 서향, 북향, 남동향, 남서향, 한강뷰, 시티뷰, 주차가능, 신축, 복층, 고층, 저층, 1층, 정원, 학군, 역세권, 즉시입주, 엘리베이터, 베란다확장
■ "강아지/반려동물/펫" → ["애견가능"]
■ "옥상" → ["루프탑"], "풀옵" → ["풀옵션"]
■ "바로 입주/즉시/빠른입주" → ["즉시입주"]
■ "학교/학군/학교근처/교육/학원가" → features에 ["학군"] 추가하고, semantic에도 "학군좋은" 포함
■ "역 근처/역세권/지하철" → ["역세권"]
■ "핫플/핫한/인기/뜨는" 같은 추상어는 무시하고 지역명만 location에 추출

■ location 추출 규칙:
- "성수동" → "성수", "합정동" → "합정", "잠실동" → "잠실" ("동" 제거)
- "강남역 근처" → "강남", "여의도역" → "여의도" ("역" 제거)
- "마포구" → "마포", "서초구" → "서초" ("구" 제거)
- 단, 동탄/구리/구로/동대문 등 지명 자체인 경우는 그대로 유지

■ nearby (근처 검색 - 역/학교/대학 등):
- "합정역 근처" → nearby: "합정역", nearby_type: "subway"
- "서울대 근처" → nearby: "서울대", nearby_type: "school"
- "강남역" → nearby: "강남역", nearby_type: "subway"
- "~~역", "~~역 근처/주변/앞" → subway
- "~~대/~~대학/~~학교/~~초등/~~중학/~~고등" → school
- 역이나 학교가 아니면 null
- nearby가 있으면 location도 같이 추출

{
  "semantic": "의미 검색 키워드 (없으면 null)",
  "filters": {
    "property_type": null,
    "trade_type": null,
    "min_price": null,
    "max_price": null,
    "location": null,
    "nearby": null,
    "nearby_type": null,
    "trade_status": null,
    "date_filter": null,
    "min_area": null,
    "max_area": null,
    "rooms": null,
    "sort": null
  },
  "features": null
}

검색어: ${query}`
        }]
      })
    });

    const data = await response.json();
    if (data.error) {
      console.error('Anthropic API 에러:', JSON.stringify(data.error));
      throw new Error('파싱 실패');
    }

    let jsonText = data.content[0].text || '';
    jsonText = jsonText.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
    const firstBrace = jsonText.indexOf('{');
    const lastBrace = jsonText.lastIndexOf('}');
    if (firstBrace !== -1 && lastBrace !== -1) jsonText = jsonText.slice(firstBrace, lastBrace + 1);

    return JSON.parse(jsonText);
  } catch (e) {
    // ★ 파싱 실패 시 폴백: 원본 쿼리를 semantic으로 사용
    console.warn('파싱 폴백:', e.message);
    return {
      semantic: query,
      filters: {},
      features: null
    };
  }
}

// ========== 2. OpenAI 임베딩 ==========
async function generateEmbedding(text, openaiKey) {
  try {
    const response = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${openaiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'text-embedding-3-small', input: text }),
    });
    const data = await response.json();
    return data.data?.[0]?.embedding || null;
  } catch (e) { return null; }
}

// ========== 3. 날짜 필터 → 날짜 계산 ==========
function getDateCutoff(dateFilter) {
  if (!dateFilter) return null;
  const now = new Date();

  if (dateFilter === 'today') {
    const cutoff = new Date(now);
    cutoff.setHours(0, 0, 0, 0);
    return cutoff.toISOString();
  } else if (dateFilter === 'week') {
    const cutoff = new Date(now);
    cutoff.setDate(cutoff.getDate() - 7);
    return cutoff.toISOString();
  } else if (dateFilter === 'month') {
    const cutoff = new Date(now);
    cutoff.setDate(cutoff.getDate() - 30);
    return cutoff.toISOString();
  } else if (typeof dateFilter === 'number' && dateFilter > 0) {
    const cutoff = new Date(now);
    cutoff.setDate(cutoff.getDate() - dateFilter);
    return cutoff.toISOString();
  }
  return null;
}

// ========== 4. 면적에서 숫자 추출 ==========
function extractAreaNumber(areaStr) {
  if (!areaStr) return null;
  const match = areaStr.match(/(\d+)/);
  return match ? parseInt(match[1]) : null;
}

function extractAreaNumbers(areaStr: string): { pyeong: number | null; sqm: number | null } {
  if (!areaStr) return { pyeong: null, sqm: null };
  const sqmMatch = areaStr.match(/(\d+)㎡/);
  const pyeongMatch = areaStr.match(/(\d+)평/);
  return {
    sqm: sqmMatch ? parseInt(sqmMatch[1]) : null,
    pyeong: pyeongMatch ? parseInt(pyeongMatch[1]) : null
  };
}

// ========== 5. 정렬 함수 ==========
function sortResults(results, sortType) {
  if (!sortType) return results; // 기본: 유사도순 (DB에서 이미 정렬됨)

  const sorted = [...results];
  switch (sortType) {
    case 'newest':
      sorted.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
      break;
    case 'price_asc':
      sorted.sort((a, b) => (a.price_number || 999999999) - (b.price_number || 999999999));
      break;
    case 'price_desc':
      sorted.sort((a, b) => (b.price_number || 0) - (a.price_number || 0));
      break;
    case 'views':
      sorted.sort((a, b) => (b.view_count || 0) - (a.view_count || 0));
      break;
  }
  return sorted;
}

// ========== 6. 손님 카드 검색 (client 모드) ==========
async function searchClientCards(supabase, agentId, embedding, query, limit) {
  try {
    if (embedding) {
      const { data, error } = await supabase.rpc('search_client_cards', {
        p_agent_id: agentId,
        p_embedding: embedding,
        p_limit: limit
      });
      if (!error && data && data.length > 0) {
        return data.map(r => ({ ...r, _cat: 'client' }));
      }
    }

    const { data, error } = await supabase
      .from('cards_view')
      .select('id, property, created_at, agent_id, trade_status, search_text')
      .eq('agent_id', agentId)
      .eq('property->>type', '손님')
      .order('created_at', { ascending: false })
      .limit(limit * 2);

    if (error || !data) return [];

    const q = query.toLowerCase();
    const filtered = data.filter(r => {
      const st = (r.search_text || '').toLowerCase();
      const p = r.property || {};
      const combined = [st, p.location, p.price, p.area, ...(p.features || [])].filter(Boolean).join(' ').toLowerCase();
      return combined.includes(q) || q.split(' ').some(w => w.length > 1 && combined.includes(w));
    });

    return (filtered.length > 0 ? filtered : data.slice(0, limit)).map(r => ({ ...r, _cat: 'client' }));
  } catch (e) {
    console.error('손님 검색 오류:', e);
    return [];
  }
}

// ========== 메인 ==========
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY');
    const OPENAI_API_KEY = Deno.env.get('OPENAI_API_KEY');
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL');
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');

    if (!ANTHROPIC_API_KEY) throw new Error('서버 설정 오류');

    const { query, agent_id, limit = 10, search_mode = 'my', trade_type = null, property_type = null, min_price = null, max_price = null } = await req.json();
    if (!query) throw new Error('검색어가 필요합니다');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const startTime = Date.now();

    // ★ 손님 모드 — 별도 처리
    if (search_mode === 'client') {
      const embedding = OPENAI_API_KEY ? await generateEmbedding(query, OPENAI_API_KEY) : null;
      const results = await searchClientCards(supabase, agent_id, embedding, query, limit);
      console.log(`손님 검색: ${Date.now() - startTime}ms | ${results.length}건`);
      return new Response(JSON.stringify({
        success: true, query, results, count: results.length, search_mode
      }), { headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    }

    // ★ 1단계: 로컬 빠른 파서 시도 (0ms)
    const clientParsedPrice = min_price !== null || max_price !== null;
    let parsed: any = { semantic: null, filters: {}, features: null };
    let embedding = null;

    const localResult = localParseQuery(query);

    if (localResult) {
      // 로컬 파서 성공 → Claude 불필요 (빠름!)
      parsed = localResult;
      // 클라이언트가 보낸 가격이 있으면 덮어쓰기
      if (clientParsedPrice) {
        if (min_price !== null) parsed.filters.min_price = min_price;
        if (max_price !== null) parsed.filters.max_price = max_price;
      }
      // ★ 구조화된 필터가 2개 이상이면 임베딩 생략 (SQL만으로 충분)
      const structuredFilterCount = [
        parsed.filters.trade_type, parsed.filters.property_type,
        parsed.filters.min_price || parsed.filters.max_price,
        parsed.filters.location
      ].filter(Boolean).length;
      if (structuredFilterCount >= 2) {
        embedding = null; // SQL 직접 검색 모드
        console.log(`SQL 직접 검색: ${Date.now() - startTime}ms | filters: ${JSON.stringify(parsed.filters)} (임베딩 생략)`);
      } else {
        embedding = OPENAI_API_KEY ? await generateEmbedding(parsed.semantic || query, OPENAI_API_KEY) : null;
        console.log(`로컬 파싱 + 벡터: ${Date.now() - startTime}ms | filters: ${JSON.stringify(parsed.filters)}`);
      }
    } else if (!clientParsedPrice && query.length >= 6) {
      // 로컬 파서 실패 + 긴 쿼리 → Claude에게 맡기기
      const [parsedResult, earlyEmbedding] = await Promise.all([
        parseSearchQuery(query, ANTHROPIC_API_KEY),
        OPENAI_API_KEY ? generateEmbedding(query, OPENAI_API_KEY) : Promise.resolve(null)
      ]);
      parsed = parsedResult;
      embedding = earlyEmbedding;
      if (parsed.semantic && parsed.semantic !== query && OPENAI_API_KEY) {
        embedding = await generateEmbedding(parsed.semantic, OPENAI_API_KEY);
      }
      console.log(`Claude 파싱: ${Date.now() - startTime}ms | filters: ${JSON.stringify(parsed.filters)}`);
    } else {
      // 짧은 미인식 쿼리 → 임베딩만 (벡터 검색)
      if (clientParsedPrice) {
        parsed.filters.min_price = min_price;
        parsed.filters.max_price = max_price;
      }
      embedding = OPENAI_API_KEY ? await generateEmbedding(query, OPENAI_API_KEY) : null;
      console.log(`벡터 검색만: ${Date.now() - startTime}ms`);
    }

    // ★ 날짜 필터 계산
    const dateCutoff = getDateCutoff(parsed.filters?.date_filter);

    // ★ 후처리 필터 개수에 따라 DB 요청량 동적 조절
    let postFilterCount = 0;
    if (parsed.filters?.trade_status) postFilterCount++;
    if (dateCutoff) postFilterCount++;
    if (parsed.filters?.min_area || parsed.filters?.max_area) postFilterCount++;
    if (parsed.filters?.rooms) postFilterCount++;
    if (parsed.filters?.location) postFilterCount++;
    if (parsed.features?.length) postFilterCount++;
    const multiplier = postFilterCount <= 1 ? 3 : postFilterCount <= 3 ? 5 : 10;

    // ★ 클라이언트가 직접 보낸 필터가 있으면 우선 사용
    const finalTradeType = trade_type || parsed.filters?.trade_type || null;
    const finalPropertyType = property_type || parsed.filters?.property_type || null;

    let results: any[] = [];
    let searchMethod = 'rpc';

    // ★ 구조화된 필터가 충분하면 SQL 직접 검색 (빠르고 정확)
    if (!embedding && (finalTradeType || finalPropertyType || parsed.filters?.min_price || parsed.filters?.max_price)) {
      searchMethod = 'sql';
      let sqlQuery = supabase
        .from('cards')
        .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number, agent_comment')
        .eq('agent_id', agent_id)
        .neq('property->>type', '손님');

      if (finalTradeType) sqlQuery = sqlQuery.eq('property->>type', finalTradeType);
      if (finalPropertyType) sqlQuery = sqlQuery.eq('property->>category', finalPropertyType);
      if (parsed.filters?.min_price) sqlQuery = sqlQuery.gte('price_number', parsed.filters.min_price);
      if (parsed.filters?.max_price) sqlQuery = sqlQuery.lte('price_number', parsed.filters.max_price);

      sqlQuery = sqlQuery.order('created_at', { ascending: false }).limit(limit * multiplier);
      const { data: sqlData, error: sqlError } = await sqlQuery;

      if (sqlError) {
        console.error('SQL 검색 에러:', sqlError.message);
      } else {
        results = (sqlData || []).map(r => ({ ...r, similarity: 0 }));
      }
      console.log(`SQL 직접 검색: ${results.length}건 | ${Date.now() - startTime}ms`);
    }

    // ★ SQL 결과 없거나 벡터 검색 모드면 RPC 사용
    if (results.length === 0) {
      searchMethod = embedding ? 'vector' : 'rpc';
      const { data, error } = await supabase.rpc('search_cards_advanced', {
        p_agent_id: agent_id || '',
        p_search_text: null,
        p_embedding: embedding,
        p_property_type: finalPropertyType,
        p_trade_type: finalTradeType,
        p_min_price: min_price || parsed.filters?.min_price || null,
        p_max_price: max_price || parsed.filters?.max_price || null,
        p_days_ago: null,
        p_limit: limit * multiplier,
        p_search_mode: search_mode
      });

      if (error) {
        console.error('DB 검색 에러:', error.message);
        throw new Error('매물 검색에 실패했습니다');
      }
      results = data || [];
      console.log(`RPC 검색: ${results.length}건 | ${Date.now() - startTime}ms`);
    }

    // ★ RPC 결과 0건이면 property_type 완화 후 재시도
    if (results.length === 0 && finalPropertyType) {
      console.log(`RPC 0건 → property_type '${finalPropertyType}' 제거 후 재검색`);
      const { data: retryData } = await supabase.rpc('search_cards_advanced', {
        p_agent_id: agent_id || '',
        p_search_text: null,
        p_embedding: embedding,
        p_property_type: null,  // 카테고리 필터 제거
        p_trade_type: finalTradeType,
        p_min_price: min_price || parsed.filters?.min_price || null,
        p_max_price: max_price || parsed.filters?.max_price || null,
        p_days_ago: null,
        p_limit: limit * multiplier,
        p_search_mode: search_mode
      });
      if (retryData && retryData.length > 0) {
        results = retryData;
        console.log(`재시도 결과: ${results.length}건 (카테고리 필터 제거)`);
      }
    }

    // ★ 하이브리드: 벡터 결과가 3건 미만이면 키워드 폴백 추가
    if (results.length < 3 && query.length >= 2) {
      console.log(`벡터 결과 ${results.length}건 → 키워드 폴백 실행`);
      // 검색어 확장: 단지명, 카테고리 한글명 등
      const kwSearchTerms: string[] = [query];
      if (parsed.semantic && parsed.semantic !== query) kwSearchTerms.unshift(parsed.semantic);
      // 카테고리 한글명으로도 폴백 ("원룸" → "원투룸"도 검색)
      const catKoMap: Record<string, string[]> = {
        'room': ['원룸', '투룸', '원투룸', '빌라'],
        'apartment': ['아파트'],
        'officetel': ['오피스텔'],
        'commercial': ['상가'],
        'office': ['사무실'],
      };
      if (finalPropertyType && catKoMap[finalPropertyType]) {
        for (const catKw of catKoMap[finalPropertyType]) {
          if (!kwSearchTerms.includes(catKw)) kwSearchTerms.push(catKw);
        }
      }

      for (const kwTerm of kwSearchTerms) {
        if (results.length >= 3) break;
        let kwQuery = supabase
          .from('cards')
          .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number')
          .eq('agent_id', agent_id)
          .neq('property->>type', '손님')
          .ilike('search_text', `%${kwTerm}%`)
          .order('created_at', { ascending: false })
          .limit(limit * 3);
        if (finalTradeType) kwQuery = kwQuery.eq('property->>type', finalTradeType);
        if (finalPropertyType) kwQuery = kwQuery.eq('property->>category', finalPropertyType);
        const { data: kwData } = await kwQuery;

        if (kwData && kwData.length > 0) {
          const existingIds = new Set(results.map(r => r.id));
          const newResults = kwData.filter(r => !existingIds.has(r.id)).map(r => ({ ...r, similarity: 0 }));
          results = [...results, ...newResults];
          console.log(`키워드 폴백 '${kwTerm}': +${newResults.length}건 추가 (총 ${results.length}건)`);
        }
      }
    }

    // ★ 단지명 텍스트 매칭 (항상 키워드 검색 수행 → 벡터보다 정확)
    if (parsed.semantic && parsed._local) {
      const brandName = parsed.semantic;
      // 항상 키워드로 단지명 검색
      console.log(`단지명 '${brandName}' 키워드 검색`);
      let brandQuery = supabase
        .from('cards')
        .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number')
        .eq('agent_id', agent_id)
        .neq('property->>type', '손님')
        .ilike('search_text', `%${brandName}%`)
        .order('created_at', { ascending: false })
        .limit(limit * 5);
      if (finalTradeType) brandQuery = brandQuery.eq('property->>type', finalTradeType);
      const { data: brandData } = await brandQuery;

      if (brandData && brandData.length > 0) {
        // 단지명 매칭 결과를 최상위로, 기존 벡터 결과는 아래로
        const brandIds = new Set(brandData.map(r => r.id));
        const brandResults = brandData.map(r => ({ ...r, similarity: 1 })); // 높은 유사도 부여
        const existingNotBrand = results.filter(r => !brandIds.has(r.id));
        results = [...brandResults, ...existingNotBrand];
        console.log(`단지명 매칭: ${brandData.length}건 최상위 배치`);
      } else {
        // 키워드 결과도 없으면 기존 벡터 결과에서 필터
        const brandMatched = results.filter(r => {
          const st = r.search_text || '';
          const complex = r.property?.complex || '';
          return st.includes(brandName) || complex.includes(brandName);
        });
        if (brandMatched.length > 0) {
          const notMatched = results.filter(r => !brandMatched.some(b => b.id === r.id));
          results = [...brandMatched, ...notMatched];
        }
      }
    }

    // ★ 거래상태 필터
    if (parsed.filters?.trade_status) {
      const ts = parsed.filters.trade_status;
      results = results.filter(r => {
        const cardStatus = r.trade_status || r.status || '계약가능';
        return cardStatus === ts;
      });
    }

    // ★ 날짜 필터
    if (dateCutoff) {
      results = results.filter(r => {
        return r.created_at && new Date(r.created_at) >= new Date(dateCutoff);
      });
    }

    // ★ 면적 필터 (평수↔㎡ 양방향 매칭)
    if (parsed.filters?.min_area || parsed.filters?.max_area) {
      // Convert search pyeong to sqm range too
      const searchMinPyeong = parsed.filters.min_area || null;
      const searchMaxPyeong = parsed.filters.max_area || null;
      const searchMinSqm = searchMinPyeong ? Math.round(searchMinPyeong * 3.305785 * 0.8) : null;
      const searchMaxSqm = searchMaxPyeong ? Math.round(searchMaxPyeong * 3.305785 * 1.2) : null;

      results = results.filter(r => {
        const { pyeong, sqm } = extractAreaNumbers(r.property?.area);
        // Check pyeong match
        if (pyeong) {
          if (searchMinPyeong && pyeong < searchMinPyeong) return false;
          if (searchMaxPyeong && pyeong > searchMaxPyeong) return false;
          return true;
        }
        // Check sqm match
        if (sqm) {
          if (searchMinSqm && sqm < searchMinSqm) return false;
          if (searchMaxSqm && sqm > searchMaxSqm) return false;
          return true;
        }
        return false;
      });
    }

    // ★ 방 수 필터
    if (parsed.filters?.rooms) {
      const targetRooms = String(parsed.filters.rooms);
      results = results.filter(r => {
        const room = r.property?.room || '';
        const searchText = r.search_text || '';
        return room.includes(targetRooms) || searchText.includes(targetRooms + '룸') || searchText.includes('방' + targetRooms);
      });
    }

    // 위치 필터 (★ 좌표 우선 → 텍스트 폴백)
    if (parsed.filters?.location) {
      const loc = parsed.filters.location;
      const coordInfo = DISTRICT_COORDS[loc];

      if (coordInfo) {
        // ★ 좌표 기반 필터 (정확도 높음)
        const coordFiltered = results.filter(r => {
          if (!r.lat || !r.lng) return false;
          return haversineDistance(coordInfo.lat, coordInfo.lng, r.lat, r.lng) <= coordInfo.radius;
        });
        if (coordFiltered.length > 0) {
          results = coordFiltered;
          console.log(`좌표 필터 '${loc}': ${coordFiltered.length}건 (반경 ${coordInfo.radius}km)`);
        } else {
          // 벡터 결과에 해당 지역이 없으면 → 텍스트 매칭 폴백
          const textFiltered = results.filter(r => {
            const st = r.search_text || '';
            const pLoc = r.property?.location || '';
            return st.includes(loc) || pLoc.includes(loc);
          });
          if (textFiltered.length > 0) {
            results = textFiltered;
            console.log(`텍스트 폴백 '${loc}': ${textFiltered.length}건`);
          } else {
            // 마지막 수단: 키워드 직접 검색
            console.log(`위치 매칭 0건 → '${loc}' DB 키워드 재검색`);
            let locQuery1 = supabase
              .from('cards')
              .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number')
              .eq('agent_id', agent_id)
              .neq('property->>type', '손님')
              .ilike('search_text', `%${loc}%`)
              .order('created_at', { ascending: false })
              .limit(limit * multiplier);
            if (finalTradeType) locQuery1 = locQuery1.eq('property->>type', finalTradeType);
            if (finalPropertyType) locQuery1 = locQuery1.eq('property->>category', finalPropertyType);
            const { data: locData } = await locQuery1;
            if (locData && locData.length > 0) {
              results = locData.map(r => ({ ...r, similarity: 0 }));
            } else {
              results = [];
            }
          }
        }
      } else {
        // 좌표 사전에 없는 지역 → 텍스트 매칭만
        const locFiltered = results.filter(r => {
          const st = r.search_text || '';
          const pLoc = r.property?.location || '';
          return st.includes(loc) || pLoc.includes(loc);
        });
        if (locFiltered.length > 0) {
          results = locFiltered;
        } else {
          let locQuery2 = supabase
            .from('cards')
            .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number')
            .eq('agent_id', agent_id)
            .neq('property->>type', '손님')
            .ilike('search_text', `%${loc}%`)
            .order('created_at', { ascending: false })
            .limit(limit * multiplier);
          if (finalTradeType) locQuery2 = locQuery2.eq('property->>type', finalTradeType);
          if (finalPropertyType) locQuery2 = locQuery2.eq('property->>category', finalPropertyType);
          const { data: locData } = await locQuery2;
          if (locData && locData.length > 0) {
            results = locData.map(r => ({ ...r, similarity: 0 }));
          } else {
            results = [];
          }
        }
      }
    }

    // ★ 근처 검색 (역/학교 좌표 기반 — facilities 테이블)
    if (parsed.filters?.nearby && parsed.filters?.nearby_type) {
      const nearbyName = parsed.filters.nearby;
      const nearbyType = parsed.filters.nearby_type;
      const RADIUS_KM = 2.0; // 반경 2km (이전: 1.5km)

      try {
        // facilities 테이블에서 해당 시설 좌표 찾기
        const { data: facilityData } = await supabase
          .from('facilities')
          .select('latitude, longitude, name')
          .eq('type', nearbyType)
          .ilike('name', `%${nearbyName.replace(/역$|대$|대학$|학교$/, '')}%`)
          .limit(3);

        if (facilityData && facilityData.length > 0) {
          const facility = facilityData[0];
          const fLat = facility.latitude;
          const fLng = facility.longitude;
          console.log(`근처 검색: ${facility.name} (${fLat}, ${fLng}) 반경 ${RADIUS_KM}km`);

          // 반경 내 매물 필터
          const nearbyFiltered = results.filter(r => {
            if (!r.lat || !r.lng) return false;
            return haversineDistance(fLat, fLng, r.lat, r.lng) <= RADIUS_KM;
          });

          if (nearbyFiltered.length > 0) {
            results = nearbyFiltered;
            console.log(`근처 검색 결과: ${nearbyFiltered.length}건`);
          }
        }
      } catch(e) {
        console.warn('근처 검색 실패:', e);
      }
    }

    // features 필터 (소프트: 매칭되는 걸 상위로, 없으면 유지)
    if (parsed.features && parsed.features.length > 0) {
      const withFeat: any[] = [];
      const withoutFeat: any[] = [];
      for (const r of results) {
        const st = r.search_text || '';
        const feats = (r.property?.features || []).join(' ');
        const all = (st + ' ' + feats).toLowerCase();
        if (parsed.features.some(f => all.includes(f.toLowerCase()))) {
          withFeat.push(r);
        } else {
          withoutFeat.push(r);
        }
      }
      // 특징 매칭된 것을 상위로, 나머지는 뒤에 (제거하지 않음)
      results = [...withFeat, ...withoutFeat];
    }

    // ★ 필터 완화: 후처리 필터 후 결과 0건이면 단계적으로 풀기
    if (results.length === 0 && (finalTradeType || finalPropertyType)) {
      console.log('후처리 필터 후 0건 → 키워드 폴백 (필터 완화)');
      // 검색어 핵심 키워드로 재검색 (필터 없이)
      const fallbackTerms = [query];
      if (parsed.semantic) fallbackTerms.unshift(parsed.semantic);
      for (const term of fallbackTerms) {
        if (results.length > 0) break;
        const { data: fbData } = await supabase
          .from('cards')
          .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number')
          .eq('agent_id', agent_id)
          .neq('property->>type', '손님')
          .ilike('search_text', `%${term}%`)
          .order('created_at', { ascending: false })
          .limit(limit * 3);
        if (fbData && fbData.length > 0) {
          results = fbData.map(r => ({ ...r, similarity: 0 }));
          console.log(`필터 완화 폴백 '${term}': ${results.length}건`);
        }
      }
    }

    // ★ 점수 기반 랭킹 (조건이 많을수록 정밀 랭킹, 적으면 최신순)
    let autoSort: string | null = null;
    const hasRankingConditions = !!(
      parsed.filters?.min_price || parsed.filters?.max_price ||
      parsed.filters?.min_area || parsed.filters?.max_area ||
      parsed.filters?.rooms || parsed.filters?.location
    );

    if (hasRankingConditions && results.length > 1) {
      // 점수 계산용 기준값
      const targetPrice = parsed.filters?.max_price || parsed.filters?.min_price || null;
      const targetArea = parsed.filters?.min_area || parsed.filters?.max_area || null;
      const targetRooms = parsed.filters?.rooms || null;
      const locCoord = parsed.filters?.location ? DISTRICT_COORDS[parsed.filters.location] : null;

      results = results.map(r => {
        let score = 0;
        let factors = 0;

        // ① 가격 근접도 (0~40점)
        if (targetPrice && r.price_number) {
          factors++;
          const priceDiff = Math.abs(r.price_number - targetPrice) / targetPrice;
          if (priceDiff <= 0.05) score += 40;       // ±5% → 만점
          else if (priceDiff <= 0.15) score += 32;   // ±15%
          else if (priceDiff <= 0.30) score += 20;   // ±30%
          else if (priceDiff <= 0.50) score += 10;   // ±50%
          // 예산 초과 페널티
          if (parsed.filters?.max_price && r.price_number > parsed.filters.max_price) {
            const overRate = (r.price_number - parsed.filters.max_price) / parsed.filters.max_price;
            score -= Math.min(20, Math.round(overRate * 40));
          }
        }

        // ② 크기/면적 근접도 (0~25점)
        if (targetArea) {
          factors++;
          const area = extractAreaNumber(r.property?.area);
          if (area) {
            const areaDiff = Math.abs(area - targetArea) / targetArea;
            if (areaDiff <= 0.1) score += 25;        // ±10% → 만점
            else if (areaDiff <= 0.25) score += 18;
            else if (areaDiff <= 0.50) score += 10;
            else score += 3;
          }
        }

        // ③ 방 수 일치 (0~20점)
        if (targetRooms) {
          factors++;
          const roomStr = r.property?.room || r.search_text || '';
          const roomNum = parseInt(roomStr.match(/(\d)/)?.[1] || '0');
          if (roomNum === targetRooms) score += 20;          // 정확 일치
          else if (Math.abs(roomNum - targetRooms) === 1) score += 10; // ±1
        }

        // ④ 위치 근접도 (0~15점)
        if (locCoord && r.lat && r.lng) {
          factors++;
          const dist = haversineDistance(locCoord.lat, locCoord.lng, r.lat, r.lng);
          if (dist <= 0.5) score += 15;         // 500m 이내
          else if (dist <= 1.0) score += 12;    // 1km
          else if (dist <= 2.0) score += 8;     // 2km
          else if (dist <= 3.0) score += 4;     // 3km
        }

        // ⑤ 최신 가산점 (0~5점) — 7일 이내 등록
        if (r.created_at) {
          const daysSince = (Date.now() - new Date(r.created_at).getTime()) / (1000*60*60*24);
          if (daysSince <= 1) score += 5;
          else if (daysSince <= 3) score += 3;
          else if (daysSince <= 7) score += 1;
        }

        return { ...r, _score: score, _factors: factors };
      });

      // 점수 내림차순 정렬 (동점이면 최신순)
      results.sort((a, b) => {
        const diff = (b._score || 0) - (a._score || 0);
        if (diff !== 0) return diff;
        return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
      });
      console.log(`랭킹 적용: ${results.length}건 | 상위: ${results[0]?._score}점 | 하위: ${results[results.length-1]?._score}점`);
    } else {
      // 조건이 적으면 → 명시적 sort 또는 최신순
      autoSort = parsed.filters?.sort || null;
      if (!autoSort) {
        if (parsed.filters?.date_filter) autoSort = 'newest';
        else autoSort = 'newest'; // 조건 없으면 기본 최신순
      }
      results = sortResults(results, autoSort);
    }

    results = results.slice(0, limit);

    // ★ 적용된 필터 요약 (클라이언트 표시용)
    const appliedFilters = [];
    if (parsed.filters?.trade_type) appliedFilters.push(parsed.filters.trade_type);
    if (parsed.filters?.property_type) appliedFilters.push(parsed.filters.property_type);
    if (parsed.filters?.trade_status) appliedFilters.push(parsed.filters.trade_status);
    if (parsed.filters?.location) appliedFilters.push(parsed.filters.location);
    if (parsed.filters?.min_price || parsed.filters?.max_price) {
      const min = parsed.filters.min_price ? `${(parsed.filters.min_price/10000).toFixed(1)}억` : '';
      const max = parsed.filters.max_price ? `${(parsed.filters.max_price/10000).toFixed(1)}억` : '';
      if (min && max) appliedFilters.push(`${min}~${max}`);
      else if (max) appliedFilters.push(`${max} 이하`);
      else if (min) appliedFilters.push(`${min} 이상`);
    }
    if (parsed.filters?.date_filter) {
      const df = parsed.filters.date_filter;
      if (df === 'today') appliedFilters.push('오늘');
      else if (df === 'week') appliedFilters.push('이번 주');
      else if (df === 'month') appliedFilters.push('이번 달');
      else if (typeof df === 'number') appliedFilters.push(`최근 ${df}일`);
    }
    if (parsed.filters?.min_area || parsed.filters?.max_area) {
      const min = parsed.filters.min_area || '';
      const max = parsed.filters.max_area || '';
      if (min && max) appliedFilters.push(`${min}~${max}평`);
      else if (max) appliedFilters.push(`${max}평 이하`);
      else if (min) appliedFilters.push(`${min}평 이상`);
    }
    if (parsed.filters?.rooms) appliedFilters.push(`${parsed.filters.rooms}룸`);
    if (parsed.filters?.nearby) appliedFilters.push(`${parsed.filters.nearby} 근처`);
    if (parsed.features?.length) appliedFilters.push(...parsed.features);
    if (autoSort) {
      const sortLabels = { newest: '최신순', price_asc: '가격↓', price_desc: '가격↑', views: '인기순' };
      appliedFilters.push(sortLabels[autoSort] || '');
    }

    console.log(`총 소요: ${Date.now() - startTime}ms | 결과: ${results.length}건 | mode: ${search_mode} | filters: ${appliedFilters.join(', ')}`);

    return new Response(JSON.stringify({
      success: true,
      query,
      parsed,
      results,
      count: results.length,
      search_mode,
      applied_filters: appliedFilters,
      ranking: hasRankingConditions ? 'score' : 'newest',
      search_method: searchMethod,
      top_score: results[0]?._score ?? null
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('search-property 에러:', error.message);
    return new Response(JSON.stringify({ error: '검색 중 오류가 발생했습니다' }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
