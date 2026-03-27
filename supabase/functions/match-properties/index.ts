import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',  // TODO: 프로덕션에서 'https://hwik.kr'로 제한
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

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

    const { client_card_id, agent_id, limit = 10, threshold = 0.15 } = await req.json();
    if (!client_card_id) throw new Error('client_card_id가 필요합니다');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // ★ 인증 확인
    const authHeader = req.headers.get('Authorization');
    if (authHeader) {
      try {
        const token = authHeader.replace('Bearer ', '');
        const { data: { user } } = await supabase.auth.getUser(token);
        if (user && agent_id && user.id !== agent_id) {
          throw new Error('권한이 없습니다');
        }
      } catch(e) {
        if (e.message === '권한이 없습니다') throw e;
      }
    }

    const startTime = Date.now();

    // 1. 손님 카드 조회
    const { data: clientCard, error: clientError } = await supabase
      .from('cards')
      .select('id, property, private_note, embedding, agent_id, wanted_trade_type, move_in_date')
      .eq('id', client_card_id)
      .single();

    if (clientError || !clientCard) throw new Error('손님 카드를 찾을 수 없습니다');
    if (clientCard.property?.type !== '손님') throw new Error('손님 카드가 아닙니다');

    // ★ 임베딩 없으면 즉시 생성
    if (!clientCard.embedding) {
      const OPENAI_API_KEY = Deno.env.get('OPENAI_API_KEY');
      if (!OPENAI_API_KEY) throw new Error('임베딩 생성 불가 (API 키 없음)');

      const cp = clientCard.property || {};
      const memo = clientCard.private_note?.memo || '';
      const catKo = {apartment:'아파트',officetel:'오피스텔',room:'원투룸',commercial:'상가',office:'사무실'}[cp.category] || '';
      const embedText = [cp.type, catKo, cp.price, cp.location, cp.complex, cp.area, cp.floor, cp.room, (cp.features||[]).join(' '), cp.moveIn, memo].filter(Boolean).join(' ');

      const embedResp = await fetch('https://api.openai.com/v1/embeddings', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: 'text-embedding-3-small', input: embedText })
      });
      const embedData = await embedResp.json();
      const embedding = embedData.data?.[0]?.embedding;
      if (!embedding) throw new Error('임베딩 생성 실패');

      // DB 업데이트
      await supabase.from('cards').update({ embedding, search_text: embedText }).eq('id', client_card_id);
      clientCard.embedding = embedding;
      console.log('임베딩 즉시 생성 완료');
    }

    // ★ 보안: 본인 손님만 조회 가능 (agent_id 필수)
    if (!agent_id) {
      throw new Error('agent_id가 필요합니다');
    }
    if (clientCard.agent_id !== agent_id) {
      throw new Error('권한이 없습니다');
    }

    // 2. ★ 손님 조건 상세 분석 (모든 텍스트에서 추출)
    const cp = clientCard.property || {};
    const memo = clientCard.private_note?.memo || '';
    let allText = [cp.price, cp.location, cp.complex, cp.area, memo, ...(cp.features || [])].filter(Boolean).join(' ');

    // ★ 오타/한글숫자 교정
    const typoMap: Record<string, string> = {
      // 한글 숫자 → 아라비아 숫자
      '일억':'1억','이억':'2억','삼억':'3억','사억':'4억','오억':'5억',
      '육억':'6억','칠억':'7억','팔억':'8억','구억':'9억','십억':'10억',
      '일천':'1천','이천':'2천','삼천':'3천','사천':'4천','오천':'5천',
      '육천':'6천','칠천':'7천','팔천':'8천','구천':'9천',
      // 거래유형 오타
      'ㅈㅅ':'전세','젼세':'전세','ㅁㅁ':'매매','ㅇㅅ':'월세','웜세':'월세','웜ㄴ세':'월세',
      // 카테고리 오타
      '아빠트':'아파트','옵텔':'오피스텔','오피스탤':'오피스텔','상과':'상가',
      // 기타
      '안넘게':'이하','안쪽':'이하','안됨':'이하','미만':'이하','까지':'이하','이해':'이하',
    };
    for (const [typo, fix] of Object.entries(typoMap)) {
      if (allText.includes(typo)) allText = allText.replace(new RegExp(typo, 'g'), fix);
    }

    // 거래유형 — DB에 wanted_trade_type 있으면 우선 사용
    let wantedTradeType: string | null = (clientCard as any).wanted_trade_type || null;
    if (!wantedTradeType) {
      if (/매매|매도|분양|ㅁㅁ/.test(allText)) wantedTradeType = '매매';
      else if (/전세|ㅈㅅ|젼세/.test(allText)) wantedTradeType = '전세';
      else if (/월세|임대|ㅇㅅ|웜세/.test(allText)) wantedTradeType = '월세';
    }

    // 카테고리 (더 많은 패턴)
    let wantedCategory: string | null = null;
    if (/사무실|오피스(?!텔)|코워킹/.test(allText)) wantedCategory = 'office';
    else if (/상가|점포|매장|카페|음식점|식당|치킨|베이커리|미용/.test(allText)) wantedCategory = 'commercial';
    else if (/오피스텔|옵텔/.test(allText)) wantedCategory = 'officetel';
    else if (/원룸|투룸|빌라|다세대|주택|쓰리룸|방\s?\d|룸/.test(allText)) wantedCategory = 'room';
    else if (/아파트|아빠트|apt/i.test(allText)) wantedCategory = 'apartment';
    // property.category가 이미 있으면 우선
    if (cp.category && !wantedCategory) wantedCategory = cp.category;

    // 가격 범위 (더 정밀한 파싱)
    let minPrice: number | null = null;
    let maxPrice: number | null = null;

    // "3억5천 이내/이하/미만/까지/밑으로/내로" → 35000
    const priceMatch1 = allText.match(/(\d+)\s*억\s*(\d+)?\s*천?\s*(?:이내|이하|미만|까지|밑으로|내로|안넘는|못넘는)/);
    if (priceMatch1) {
      maxPrice = parseInt(priceMatch1[1]) * 10000 + (priceMatch1[2] ? parseInt(priceMatch1[2]) * 1000 : 0);
    }
    // "3억 이상/초과/넘는/부터/위로" → minPrice
    if (!minPrice) {
      const minMatch = allText.match(/(\d+)\s*억\s*(?:이상|초과|넘는|부터|위로|넘게)/);
      if (minMatch) minPrice = parseInt(minMatch[1]) * 10000;
    }
    // "3억~5억"
    const rangeMatch = allText.match(/(\d+)\s*억\s*~\s*(\d+)\s*억/);
    if (rangeMatch) {
      minPrice = parseInt(rangeMatch[1]) * 10000;
      maxPrice = parseInt(rangeMatch[2]) * 10000;
    }
    // "5천만원 이내"
    const chun = allText.match(/(\d+)\s*천\s*(?:만원?)?\s*(?:이내|이하|밑으로)/);
    if (chun && !maxPrice) maxPrice = parseInt(chun[1]) * 1000;
    // "3억 정도/쯤/선/대/내외/안팎/전후" → ±15%
    const approx = allText.match(/(\d+)\s*억\s*(?:정도|쯤|선|대|내외|안팎|전후|언저리)/);
    if (approx && !maxPrice && !minPrice) {
      const base = parseInt(approx[1]) * 10000;
      minPrice = Math.round(base * 0.85);
      maxPrice = Math.round(base * 1.15);
    }
    // 가격만 단독 ("3억" 키워드만) → ±15%
    if (!maxPrice && !minPrice) {
      const barePrice = allText.match(/(\d+)\s*억/);
      if (barePrice) {
        const base = parseInt(barePrice[1]) * 10000;
        minPrice = Math.round(base * 0.85);
        maxPrice = Math.round(base * 1.15);
      }
    }
    // 월세: "월세 80 이하" or "월 50"
    if (wantedTradeType === '월세') {
      const monthlyMax = allText.match(/월(?:세)?\s*(\d+)\s*(?:이하|이내|밑으로|만원)?/);
      if (monthlyMax) maxPrice = parseInt(monthlyMax[1]);
      const depositMatch = allText.match(/보증금\s*(\d+)/);
      if (depositMatch && !maxPrice) maxPrice = parseInt(depositMatch[1]);
    }

    // 지역 (구 + 동 + 유명지역)
    let wantedLocation: string | null = null;
    // cp.location을 먼저 확인
    if (cp.location) {
      const guFromProp = cp.location.match(/(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)/);
      if (guFromProp) wantedLocation = guFromProp[1];
    }
    if (!wantedLocation) {
      const guMatch = allText.match(/(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)/);
      if (guMatch) wantedLocation = guMatch[1];
    }

    // 평수/면적
    let wantedMinArea: number | null = null;
    let wantedMaxArea: number | null = null;
    const areaMatch = allText.match(/(\d+)\s*평/);
    if (areaMatch) {
      const pyeong = parseInt(areaMatch[1]);
      if (/대/.test(allText.slice(allText.indexOf(areaMatch[0])))) {
        wantedMinArea = pyeong;
        wantedMaxArea = pyeong + 9;
      } else {
        wantedMinArea = pyeong - 5;
        wantedMaxArea = pyeong + 5;
      }
    }

    // 방 수
    let wantedRooms: number | null = null;
    if (/원룸|1룸/.test(allText)) wantedRooms = 1;
    else if (/투룸|2룸/.test(allText)) wantedRooms = 2;
    else if (/쓰리룸|3룸|방\s*3/.test(allText)) wantedRooms = 3;
    else if (/4룸|방\s*4/.test(allText)) wantedRooms = 4;

    // 입주시기 파싱
    let wantedMoveBy: string | null = null; // YYYY-MM
    const now = new Date();
    const thisYear = now.getFullYear();
    const thisMonth = now.getMonth() + 1;
    if (/급구|바로|즉시|이번\s*달|이달|당장/.test(allText)) {
      wantedMoveBy = `${thisYear}-${String(thisMonth).padStart(2, '0')}`;
    } else if (/다음\s*달|내달/.test(allText)) {
      const next = thisMonth === 12 ? 1 : thisMonth + 1;
      const nextY = thisMonth === 12 ? thisYear + 1 : thisYear;
      wantedMoveBy = `${nextY}-${String(next).padStart(2, '0')}`;
    } else if (/내년/.test(allText)) {
      const mm = allText.match(/(\d{1,2})\s*월/);
      wantedMoveBy = mm ? `${thisYear+1}-${String(parseInt(mm[1])).padStart(2,'0')}` : `${thisYear+1}-06`;
    } else {
      const dateM = allText.match(/(20\d{2})\s*[년.\-/]\s*(\d{1,2})/);
      if (dateM) wantedMoveBy = `${dateM[1]}-${String(parseInt(dateM[2])).padStart(2,'0')}`;
      else {
        const monM = allText.match(/(\d{1,2})\s*월\s*(?:까지|이내|입주|만기)/);
        if (monM) {
          const m = parseInt(monM[1]);
          const y = m < thisMonth ? thisYear + 1 : thisYear;
          wantedMoveBy = `${y}-${String(m).padStart(2,'0')}`;
        }
      }
    }

    const effectiveAgentId = agent_id || clientCard.agent_id || '';

    // 구조화 조건 개수 확인
    const structuredCount = [wantedTradeType, wantedCategory, minPrice || maxPrice, wantedLocation].filter(Boolean).length;
    console.log(`매칭 조건: trade=${wantedTradeType} cat=${wantedCategory} loc=${wantedLocation} price=${minPrice}~${maxPrice} area=${wantedMinArea}~${wantedMaxArea} (구조화 ${structuredCount}개)`);

    let results: any[] = [];

    // 3. ★ 구조화 조건 2개 이상이면 SQL 직접 검색 (정확하고 빠름)
    if (structuredCount >= 2) {
      let sqlQuery = supabase
        .from('cards')
        .select('id, property, agent_comment, price_number, trade_status, photos, lat, lng, created_at, search_text, contact_name, contact_phone')
        .eq('agent_id', effectiveAgentId)
        .neq('property->>type', '손님')
        .eq('trade_status', '계약가능');

      if (wantedTradeType) sqlQuery = sqlQuery.eq('property->>type', wantedTradeType);
      if (wantedCategory) sqlQuery = sqlQuery.eq('property->>category', wantedCategory);
      if (minPrice) sqlQuery = sqlQuery.gte('price_number', minPrice);
      if (maxPrice) sqlQuery = sqlQuery.lte('price_number', Math.round(maxPrice * 1.1)); // 10% 여유
      // ★ 위치 필터 — property.location 텍스트로 직접 필터 (bounding box 대신)
      if (wantedLocation) {
        sqlQuery = sqlQuery.or(`property->>location.ilike.%${wantedLocation}%,search_text.ilike.%${wantedLocation}%`);
      }
      sqlQuery = sqlQuery.order('created_at', { ascending: false }).limit(limit * 5);

      const { data: sqlData, error: sqlError } = await sqlQuery;
      if (!sqlError && sqlData && sqlData.length > 0) {
        results = sqlData.map((r: any) => ({ ...r, similarity: 0 }));
        console.log(`SQL 직접 매칭: ${results.length}건 | ${Date.now() - startTime}ms`);
      }
    }

    // SQL 결과 부족하면 벡터 검색 보조
    if (results.length < 3 && clientCard.embedding) {
      const { data: matches, error: matchError } = await supabase.rpc('match_properties_for_client', {
        p_client_embedding: clientCard.embedding,
        p_agent_id: effectiveAgentId,
        p_trade_type: wantedTradeType,
        p_threshold: threshold,
        p_limit: limit * 5
      });

      if (!matchError && matches && matches.length > 0) {
        const existingIds = new Set(results.map(r => r.id));
        let newResults = matches.filter((r: any) => !existingIds.has(r.id));
        // ★ 벡터 결과에도 위치 필터 적용 (엉뚱한 지역 방지)
        if (wantedLocation && DISTRICT_COORDS[wantedLocation]) {
          const lc = DISTRICT_COORDS[wantedLocation];
          newResults = newResults.filter((r: any) => {
            if (!r.lat || !r.lng) {
              const loc = r.property?.location || '';
              return loc.includes(wantedLocation);
            }
            return haversineDistance(lc.lat, lc.lng, r.lat, r.lng) <= 5; // 5km
          });
        }
        results = [...results, ...newResults];
        console.log(`벡터 보조: +${newResults.length}건 (총 ${results.length}건)`);
      } else if (matchError) {
        console.warn('RPC 실패:', matchError.message);
      }
    }

    // ★ Fix 8: 거래유형 하드필터 (벡터 보조 후 재확인)
    if (wantedTradeType) {
      results = results.filter((r: any) => r.property?.type === wantedTradeType);
    }

    // 4. ★ 후필터: 카테고리, 가격, 지역
    if (wantedCategory) {
      const catFiltered = results.filter((r: any) => r.property?.category === wantedCategory);
      if (catFiltered.length >= 1) results = catFiltered; // 1개 이상이면 필터 적용
    }

    if (maxPrice) {
      const priceFiltered = results.filter((r: any) => {
        const pn = r.price_number || 0;
        if (minPrice && pn < minPrice) return false;
        if (maxPrice && pn > maxPrice * 1.2) return false; // 20% 여유
        return true;
      });
      if (priceFiltered.length >= 1) results = priceFiltered;
    }

    if (wantedLocation) {
      const coordInfo = DISTRICT_COORDS[wantedLocation];

      if (coordInfo) {
        // ★ 좌표 기반 점진적 반경 확대 (해당구 → 인근구 → 빈 결과)
        const radiusSteps = [coordInfo.radius, 5, 8]; // 2.5km → 5km → 8km
        let locFound = false;

        for (const radius of radiusSteps) {
          const coordFiltered = results.filter((r: any) => {
            if (!r.lat || !r.lng) return false;
            return haversineDistance(coordInfo.lat, coordInfo.lng, r.lat, r.lng) <= radius;
          });
          if (coordFiltered.length >= 1) {
            results = coordFiltered;
            console.log(`좌표 필터 '${wantedLocation}': ${coordFiltered.length}건 (반경 ${radius}km)`);
            locFound = true;
            break;
          }
        }

        if (!locFound) {
          // 좌표 매칭 없으면 DB 직접 검색 (점진적 반경)
          console.log(`결과 내 위치 매칭 0건 → '${wantedLocation}' DB 재검색 (점진적 반경)`);
          for (const radius of [5, 8]) {
            let locQuery = supabase
              .from('cards')
              .select('id, property, agent_comment, price_number, trade_status, photos, lat, lng, created_at, search_text, contact_name, contact_phone')
              .eq('agent_id', effectiveAgentId)
              .neq('property->>type', '손님')
              .eq('trade_status', '계약가능')
              .order('created_at', { ascending: false })
              .limit(limit * 5);
            if (wantedTradeType) locQuery = locQuery.eq('property->>type', wantedTradeType);
            if (wantedCategory) locQuery = locQuery.eq('property->>category', wantedCategory);
            const { data: locData } = await locQuery;

            if (locData && locData.length > 0) {
              // 좌표 거리로 필터
              const nearby = locData.filter((r: any) => {
                if (!r.lat || !r.lng) return false;
                return haversineDistance(coordInfo.lat, coordInfo.lng, r.lat, r.lng) <= radius;
              });
              if (nearby.length > 0) {
                results = nearby.map((r: any) => ({ ...r, similarity: 0 }));
                console.log(`DB 재검색: ${results.length}건 (반경 ${radius}km)`);
                break;
              }
            }
          }
          // 8km까지도 없으면 빈 결과 (엉뚱한 지역 보여주지 않음)
          if (results.length === 0 || (coordInfo && results.every((r: any) => {
            if (!r.lat || !r.lng) return true;
            return haversineDistance(coordInfo.lat, coordInfo.lng, r.lat, r.lng) > 8;
          }))) {
            results = [];
            console.log(`${wantedLocation} 반경 8km 내 매물 없음 → 빈 결과`);
          }
        }
      } else {
        // 좌표 사전에 없는 지역 → 텍스트만
        const locFiltered = results.filter((r: any) => {
          const loc = r.property?.location || '';
          const st = r.search_text || '';
          return loc.includes(wantedLocation) || st.includes(wantedLocation);
        });
        if (locFiltered.length >= 1) results = locFiltered;
      }
    }

    // 면적 필터
    if (wantedMinArea || wantedMaxArea) {
      const areaFiltered = results.filter((r: any) => {
        const areaStr = r.property?.area || '';
        const pyeongMatch = areaStr.match(/(\d+)평/);
        const sqmMatch = areaStr.match(/(\d+)㎡/);
        const pyeong = pyeongMatch ? parseInt(pyeongMatch[1]) : (sqmMatch ? Math.round(parseInt(sqmMatch[1]) / 3.305785) : null);
        if (!pyeong) return true; // 면적 정보 없으면 통과
        if (wantedMinArea && pyeong < wantedMinArea - 3) return false;
        if (wantedMaxArea && pyeong > wantedMaxArea + 3) return false;
        return true;
      });
      if (areaFiltered.length >= 1) results = areaFiltered;
    }

    // 방 수 필터
    if (wantedRooms) {
      const roomFiltered = results.filter((r: any) => {
        const room = r.property?.room || r.search_text || '';
        const roomNum = parseInt(room.match(/(\d)/)?.[1] || '0');
        return roomNum === 0 || Math.abs(roomNum - wantedRooms!) <= 1; // ±1 허용
      });
      if (roomFiltered.length >= 1) results = roomFiltered;
    }

    // ★ 계약가능 매물만 (계약중/완료 제외 — 손님에게 추천 가능한 매물만)
    results = results.filter((r: any) => {
      const status = r.trade_status || '계약가능';
      return status === '계약가능';
    });

    // ★ 중개사 실전 랭킹 (예산이하&가까운순 → 넓은순 → 최신순 → 계약가능)
    results = results.map((r: any) => {
      let score = 0;
      const pn = r.price_number || 0;

      // ① 가격 (0~50점) — 예산 이하가 핵심
      if (maxPrice && pn > 0) {
        if (pn <= maxPrice) {
          const ratio = pn / maxPrice;
          if (ratio >= 0.90) score += 50;
          else if (ratio >= 0.75) score += 42;
          else if (ratio >= 0.50) score += 30;
          else score += 15;
        } else {
          const overRate = (pn - maxPrice) / maxPrice;
          if (overRate <= 0.05) score += 20;
          else if (overRate <= 0.10) score += 5;
          else score -= 30;
        }
      } else if (minPrice && pn > 0) {
        if (pn >= minPrice) {
          const overRate = (pn - minPrice) / minPrice;
          if (overRate <= 0.15) score += 50;
          else if (overRate <= 0.30) score += 35;
          else score += 20;
        } else score -= 20;
      }

      // ② 가성비 (0~20점) — 같은 가격이면 넓은 게 좋음
      const areaStr = r.property?.area || '';
      const pyeongMatch = areaStr.match(/(\d+)평/);
      const sqmMatch = areaStr.match(/(\d+)㎡/);
      const pyeong = pyeongMatch ? parseInt(pyeongMatch[1]) : (sqmMatch ? Math.round(parseInt(sqmMatch[1]) / 3.305785) : 0);
      if ((wantedMinArea || wantedMaxArea) && pyeong > 0) {
        const targetArea = wantedMinArea || wantedMaxArea!;
        const areaDiff = Math.abs(pyeong - targetArea) / targetArea;
        if (areaDiff <= 0.1) score += 20;
        else if (areaDiff <= 0.25) score += 14;
        else if (areaDiff <= 0.50) score += 7;
      } else if (pn > 0 && pyeong > 0) {
        const ppPrice = pn / pyeong;
        if (ppPrice < 500) score += 15;
        else if (ppPrice < 1000) score += 10;
        else if (ppPrice < 2000) score += 5;
      }

      // ③ 위치 근접도 (0~10점)
      if (wantedLocation && DISTRICT_COORDS[wantedLocation] && r.lat && r.lng) {
        const coord = DISTRICT_COORDS[wantedLocation];
        const dist = haversineDistance(coord.lat, coord.lng, r.lat, r.lng);
        if (dist <= 0.5) score += 10;
        else if (dist <= 1.0) score += 8;
        else if (dist <= 2.0) score += 5;
        else if (dist <= 3.0) score += 2;
      }

      // ④ 계약가능 (0~8점)
      const status = r.trade_status || '계약가능';
      if (status === '계약가능') score += 8;

      // ⑤ 최신 등록 (0~7점)
      if (r.created_at) {
        const days = (Date.now() - new Date(r.created_at).getTime()) / (1000*60*60*24);
        if (days <= 1) score += 7;
        else if (days <= 3) score += 5;
        else if (days <= 7) score += 3;
        else if (days <= 14) score += 1;
      }

      // ⑥ 입주시기 매칭 (0~15점, -10점)
      if (wantedMoveBy) {
        const moveIn = r.property?.moveIn || '';
        // 매물의 moveIn을 YYYY-MM으로 변환
        let propDate: string | null = null;
        if (/즉시|공실|바로/.test(moveIn)) {
          propDate = `${thisYear}-${String(thisMonth).padStart(2,'0')}`;
        } else if (/협의/.test(moveIn)) {
          propDate = wantedMoveBy; // 협의 = 맞춰줄 수 있음 → 매칭
        } else {
          const dm = moveIn.match(/(20\d{2})\s*[년.\-/]\s*(\d{1,2})/);
          if (dm) propDate = `${dm[1]}-${String(parseInt(dm[2])).padStart(2,'0')}`;
          else {
            const mm = moveIn.match(/(\d{1,2})\s*월/);
            if (mm) { const m=parseInt(mm[1]); propDate=`${m<thisMonth?thisYear+1:thisYear}-${String(m).padStart(2,'0')}`; }
          }
        }
        if (propDate) {
          if (propDate <= wantedMoveBy) score += 15;   // 입주 가능일 ≤ 손님 희망 → 가능!
          else {
            // 몇 개월 초과인지
            const pY=parseInt(propDate.slice(0,4)), pM=parseInt(propDate.slice(5));
            const wY=parseInt(wantedMoveBy.slice(0,4)), wM=parseInt(wantedMoveBy.slice(5));
            const diff = (pY-wY)*12 + (pM-wM);
            if (diff <= 1) score += 5;     // 1개월 초과 — 봐줄만함
            else if (diff <= 3) score -= 5; // 2~3개월 초과
            else score -= 10;               // 3개월+ 초과 — 의미없음
          }
        }
      }

      // ⑦ 벡터 유사도 보너스 (0~5점)
      score += Math.round((r.similarity || 0) * 5);

      return { ...r, _score: score };
    });

    results.sort((a: any, b: any) => {
      const diff = (b._score || 0) - (a._score || 0);
      if (diff !== 0) return diff;
      const aArea = parseInt((a.property?.area || '').match(/(\d+)평/)?.[1] || '0');
      const bArea = parseInt((b.property?.area || '').match(/(\d+)평/)?.[1] || '0');
      if (bArea !== aArea) return bArea - aArea;
      return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
    });

    // ★ 점수 컷오프 (가격 조건 있을 때만 — 없으면 전부 보여줌)
    if (minPrice || maxPrice) {
      results = results.filter((r: any) => (r._score || 0) >= 30);
    }

    // ★ 최종 검증: 엉뚱한 매물 절대 방지
    results = results.filter((r: any) => {
      const p = r.property || {};
      if (wantedTradeType && p.type && p.type !== wantedTradeType) return false;
      if (wantedCategory && p.category && p.category !== wantedCategory) return false;
      if (wantedLocation) {
        const pLoc = p.location || '';
        const st = r.search_text || '';
        if (!pLoc.includes(wantedLocation) && !st.includes(wantedLocation)) return false;
      }
      if (maxPrice && r.price_number && r.price_number > maxPrice * 1.2) return false;
      return true;
    });

    // 상위 N개
    results = results.slice(0, limit).map((r: any) => ({
      id: r.id,
      property: r.property,
      agent_comment: r.agent_comment,
      price_number: r.price_number,
      trade_status: r.trade_status,
      photos: r.photos,
      lat: r.lat,
      lng: r.lng,
      created_at: r.created_at,
      contact_name: r.contact_name || null,
      contact_phone: r.contact_phone || null,
      _score: r._score || null,
      _scoreDetail: r._scoreDetail || null,
      similarity: r.similarity ? Math.round(r.similarity * 100) / 100 : null
    }));

    console.log(`매칭 완료: ${Date.now() - startTime}ms | ${results.length}건`);

    return new Response(JSON.stringify({
      success: true,
      client_card_id,
      wanted_trade_type: wantedTradeType,
      wanted_category: wantedCategory,
      wanted_location: wantedLocation,
      wanted_price: { min: minPrice, max: maxPrice },
      wanted_area: { min: wantedMinArea, max: wantedMaxArea },
      wanted_rooms: wantedRooms,
      wanted_move_by: wantedMoveBy,
      results,
      count: results.length,
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error: any) {
    console.error('match-properties 에러:', error.message);
    return new Response(JSON.stringify({ error: error.message || '매칭 중 오류가 발생했습니다' }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
