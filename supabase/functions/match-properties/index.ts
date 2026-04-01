import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'
import { DISTRICT_COORDS, haversineDistance } from '../_shared/geo.ts'
import { fixTypos } from '../_shared/typo.ts'
import { getAuthUserId } from '../_shared/auth.ts'
import { generateTags, TAG_WEIGHTS, extractExcludedTags } from '../_shared/tags.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': 'https://hwik.kr',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

    const { client_card_id, limit = 10, threshold = 0.15 } = await req.json();
    if (!client_card_id) throw new Error('client_card_id가 필요합니다');
    const agent_id = getAuthUserId(req);
    if (!agent_id) throw new Error('인증이 필요합니다');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // 권한은 agent_id로 검증 (손님 카드 소유자 확인은 아래에서)
    const startTime = Date.now();

    // 1. 손님 카드 조회
    const { data: clientCard, error: clientError } = await supabase
      .from('cards')
      .select('id, property, private_note, embedding, agent_id, wanted_trade_type, wanted_categories, wanted_conditions, move_in_date, tags, required_tags, price_number, deposit, monthly_rent')
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
    allText = fixTypos(allText);

    // 거래유형 — wanted_conditions에서 복수 추출, fallback: wanted_trade_type
    const wantedConds: any[] = (clientCard as any).wanted_conditions || [];
    let wantedTradeTypes: string[] = wantedConds.length ? [...new Set(wantedConds.map((c: any) => c.trade_type))] : [];
    if (!wantedTradeTypes.length && (clientCard as any).wanted_trade_type) wantedTradeTypes = [(clientCard as any).wanted_trade_type];
    if (!wantedTradeTypes.length) {
      if (/매매|매도|분양|ㅁㅁ/.test(allText)) wantedTradeTypes.push('매매');
      if (/전세|ㅈㅅ|젼세/.test(allText)) wantedTradeTypes.push('전세');
      if (/월세|임대|ㅇㅅ|웜세/.test(allText)) wantedTradeTypes.push('월세');
    }
    const wantedTradeType = wantedTradeTypes[0] || null;

    // 카테고리 (복수 지원)
    let wantedCats: string[] = [];
    // DB에 wanted_categories 배열이 있으면 우선 사용
    if ((clientCard as any).wanted_categories?.length) {
      wantedCats = (clientCard as any).wanted_categories;
    } else {
      // 텍스트에서 복수 추출
      if (/사무실|오피스(?!텔)|코워킹/.test(allText)) wantedCats.push('office');
      if (/상가|점포|매장|카페|음식점|식당|치킨|베이커리|미용/.test(allText)) wantedCats.push('commercial');
      if (/오피스텔|옵텔/.test(allText)) wantedCats.push('officetel');
      if (/원룸|투룸|빌라|다세대|주택|쓰리룸|방\s?\d|룸/.test(allText)) wantedCats.push('room');
      if (/아파트|아빠트|apt/i.test(allText)) wantedCats.push('apartment');
      if (!wantedCats.length && cp.category) wantedCats = [cp.category];
    }
    const wantedCategory = wantedCats[0] || null;

    // 가격 범위 (더 정밀한 파싱)
    let minPrice: number | null = null;
    let maxPrice: number | null = null;

    // 가격 파싱 헬퍼 (억+천 조합)
    function _parseKorPrice(s: string): number {
      let total = 0;
      const ek = s.match(/(\d+\.?\d*)\s*억/);
      const ch = s.match(/(\d+)\s*천/);
      const mn = s.match(/(\d+)\s*만/);
      if (ek) total += parseFloat(ek[1]) * 10000;
      if (ch) total += parseInt(ch[1]) * 1000;
      if (mn) total += parseInt(mn[1]);
      if (total > 0) return total;
      const n = parseInt(s.replace(/[^\d]/g, ''));
      return isNaN(n) ? 0 : n;
    }

    // ★ "3억 3억5천까지 가능/괜찮" (희망가 + 최대가)
    const dualPrice = allText.match(/(\d+\.?\d*억(?:\s*\d+천)?)\s+(\d+\.?\d*억(?:\s*\d+천)?)\s*(?:까지|이하|이내|도|면)?\s*(?:가능|괜찮|OK|ok|됩니다|돼요|상관없|무방)/i);
    if (dualPrice) {
      minPrice = _parseKorPrice(dualPrice[1]);
      maxPrice = _parseKorPrice(dualPrice[2]);
      if (minPrice > maxPrice) { const t = minPrice; minPrice = maxPrice; maxPrice = t; }
    }
    // "3억~5억" / "3억에서 5억"
    if (!maxPrice) {
      const rangeMatch = allText.match(/(\d+\.?\d*)\s*억\s*(?:~|에서|부터)\s*(\d+\.?\d*)\s*억/);
      if (rangeMatch) {
        minPrice = parseFloat(rangeMatch[1]) * 10000;
        maxPrice = parseFloat(rangeMatch[2]) * 10000;
      }
    }
    // "3억5천 이내/이하/미만/까지/밑으로/내로/안넘는/넘지않게"
    if (!maxPrice) {
      const maxMatch = allText.match(/(\d+\.?\d*)\s*억\s*(\d+)?\s*천?\s*(?:이내|이하|미만|까지|밑으로|내로|안넘는|못넘는|넘지\s*않게|안넘게|초과\s*안)/);
      if (maxMatch) maxPrice = parseFloat(maxMatch[1]) * 10000 + (maxMatch[2] ? parseInt(maxMatch[2]) * 1000 : 0);
    }
    // "5천만원 이내" / "5천 이하"
    if (!maxPrice) {
      const chun = allText.match(/(\d+)\s*천\s*(?:만원?)?\s*(?:이내|이하|밑으로|까지|넘지\s*않게)/);
      if (chun) maxPrice = parseInt(chun[1]) * 1000;
    }
    // "2억에서 3억 사이"
    if (!maxPrice) {
      const betw = allText.match(/(\d+\.?\d*)\s*억\s*(?:에서|부터)\s*(\d+\.?\d*)\s*억\s*(?:사이|까지)/);
      if (betw) { minPrice = parseFloat(betw[1]) * 10000; maxPrice = parseFloat(betw[2]) * 10000; }
    }
    // "3억 이상/초과/넘는/부터/위로"
    if (!minPrice) {
      const minMatch = allText.match(/(\d+\.?\d*)\s*억\s*(?:이상|초과|넘는|부터|위로|넘게)/);
      if (minMatch) minPrice = parseFloat(minMatch[1]) * 10000;
    }
    // "3억선" / "3억대" / "3억 정도/쯤/내외/안팎/전후/언저리" → ±15%
    if (!maxPrice && !minPrice) {
      const approx = allText.match(/(\d+\.?\d*)\s*억\s*(?:\d*천?\s*)?(?:정도|쯤|선에서|선|대|내외|안팎|전후|언저리)/);
      if (approx) {
        const base = parseFloat(approx[1]) * 10000;
        minPrice = Math.round(base * 0.85);
        maxPrice = Math.round(base * 1.15);
      }
    }
    // 가격만 단독 ("3억") → 희망가 ±15%
    if (!maxPrice && !minPrice) {
      const barePrice = allText.match(/(\d+\.?\d*)\s*억/);
      if (barePrice) {
        const base = parseFloat(barePrice[1]) * 10000;
        minPrice = Math.round(base * 0.85);
        maxPrice = Math.round(base * 1.15);
      }
    }
    // 월세: 보증금과 월세금 — DB 필드 우선, 없으면 텍스트 파싱
    let wantedDeposit: number | null = (clientCard as any).deposit || null;
    let wantedMonthly: number | null = (clientCard as any).monthly_rent || null;
    let maxDeposit: number | null = null;
    let maxMonthly: number | null = null;
    if (wantedTradeType === '월세') {
      // "보증금 1000~2000" 범위
      const depRange = allText.match(/보증금\s*(\d+)\s*[~에서]\s*(\d+)/);
      if (depRange) { wantedDeposit = parseInt(depRange[1]); maxDeposit = parseInt(depRange[2]); }
      // "월세 30~50" 범위
      const monRange = allText.match(/월(?:세)?\s*(\d+)\s*[~에서]\s*(\d+)/);
      if (monRange) { wantedMonthly = parseInt(monRange[1]); maxMonthly = parseInt(monRange[2]); }
      // 단일 보증금
      if (!wantedDeposit) {
        const depMatch = allText.match(/보증금\s*(\d+)/);
        if (depMatch) wantedDeposit = parseInt(depMatch[1]);
      }
      // 단일 월세
      if (!wantedMonthly) {
        const monMatch = allText.match(/월(?:세)?\s*(\d+)/);
        if (monMatch) wantedMonthly = parseInt(monMatch[1]);
      }
      // "1000/50" 패턴
      if (!wantedDeposit && !wantedMonthly) {
        const slashMatch = allText.match(/(\d+)\s*\/\s*(\d+)/);
        if (slashMatch) {
          wantedDeposit = parseInt(slashMatch[1]);
          wantedMonthly = parseInt(slashMatch[2]);
        }
      }
      // "1000/50 2000/40도 가능" — 두 번째 조건이 max
      const dualSlash = allText.match(/(\d+)\s*\/\s*(\d+)\s+(\d+)\s*\/\s*(\d+)\s*(?:도|면|까지)?\s*(?:가능|괜찮|OK)/i);
      if (dualSlash) {
        wantedDeposit = parseInt(dualSlash[1]);
        wantedMonthly = parseInt(dualSlash[2]);
        maxDeposit = parseInt(dualSlash[3]);
        maxMonthly = parseInt(dualSlash[4]);
      }
      // "무보증" / "보증금 없이"
      if (/무보증|보증금\s*없|보증금\s*0/.test(allText)) { wantedDeposit = 0; maxDeposit = 0; }
      // "보증금 2000 이하/까지/이내/넘지않게"
      if (!maxDeposit) {
        const depMax = allText.match(/보증금\s*(\d+)\s*(?:이하|까지|이내|넘지\s*않게|미만)/);
        if (depMax) maxDeposit = parseInt(depMax[1]);
      }
      // "월세 50 이하/까지"
      if (!maxMonthly) {
        const monMax = allText.match(/월(?:세)?\s*(\d+)\s*(?:이하|까지|이내|넘지\s*않게|미만)/);
        if (monMax) maxMonthly = parseInt(monMax[1]);
      }
      maxPrice = null;
      minPrice = null;
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

    // ★ 태그 기반 매칭 — 필수 태그로 1차 필터 (GIN 인덱스)
    const mustTags: string[] = [];
    if (wantedLocation) mustTags.push(wantedLocation);
    // 거래유형과 카테고리는 SQL IN으로 처리 (태그 @> 는 AND 연산이라)
    console.log(`태그 매칭: must=[${mustTags}] trades=[${wantedTradeTypes}] cats=[${wantedCats}] price=${minPrice}~${maxPrice}`);

    let results: any[] = [];

    // 3. ★ 태그 + 숫자 필터 SQL 검색
    {
      let sqlQuery = supabase
        .from('cards')
        .select('id, property, agent_id, agent_comment, price_number, deposit, monthly_rent, trade_status, photos, lat, lng, created_at, search_text, tags')
        .eq('agent_id', effectiveAgentId)
        .neq('property->>type', '손님')
        .eq('trade_status', '계약가능');

      // ★ 태그 필수 필터 (GIN 인덱스 — 초고속)
      if (mustTags.length) {
        sqlQuery = sqlQuery.contains('tags', mustTags);
      }
      // 거래유형 (태그 OR — SQL IN으로)
      if (wantedTradeTypes.length === 1) sqlQuery = sqlQuery.contains('tags', wantedTradeTypes);
      else if (wantedTradeTypes.length > 1) {
        // 복수 거래유형: property->>type IN 으로 fallback (tags @> 는 AND라서)
        sqlQuery = sqlQuery.in('property->>type', wantedTradeTypes);
      }
      // 카테고리 (OR 지원 위해 property->>category 유지)
      if (wantedCats.length === 1) sqlQuery = sqlQuery.eq('property->>category', wantedCats[0]);
      else if (wantedCats.length > 1) sqlQuery = sqlQuery.in('property->>category', wantedCats);
      // 가격 숫자 직접 비교 (태그 아님)
      if (wantedTradeType === '월세') {
        // 월세: 보증금 + 월세금 SQL 필터
        const effMaxDep = maxDeposit || (wantedDeposit ? Math.round(wantedDeposit * 1.3) : 0);
        const effMaxMon = maxMonthly || (wantedMonthly ? Math.round(wantedMonthly * 1.3) : 0);
        if (effMaxDep > 0) sqlQuery = sqlQuery.lte('deposit', effMaxDep);
        if (effMaxMon > 0) sqlQuery = sqlQuery.lte('monthly_rent', effMaxMon);
      } else {
        if (minPrice) sqlQuery = sqlQuery.gte('price_number', minPrice);
        if (maxPrice) sqlQuery = sqlQuery.lte('price_number', Math.round(maxPrice * 1.1));
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

    // ★ Fix 8: 거래유형 하드필터 (벡터 보조 후 재확인, 복수 허용)
    if (wantedTradeTypes.length) {
      results = results.filter((r: any) => wantedTradeTypes.includes(r.property?.type));
    }

    // 4. ★ 후필터: 카테고리 (복수 OR), 가격, 지역
    if (wantedCats.length) {
      const catFiltered = results.filter((r: any) => wantedCats.includes(r.property?.category));
      if (catFiltered.length >= 1) results = catFiltered;
    }

    if (maxPrice && wantedTradeType !== '월세') {
      const priceFiltered = results.filter((r: any) => {
        const pn = r.price_number || 0;
        if (minPrice && pn < minPrice) return false;
        if (maxPrice && pn > maxPrice * 1.2) return false;
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
              .select('id, property, agent_id, agent_comment, price_number, deposit, monthly_rent, trade_status, photos, lat, lng, created_at, search_text, tags')
              .eq('agent_id', effectiveAgentId)
              .neq('property->>type', '손님')
              .eq('trade_status', '계약가능')
              .order('created_at', { ascending: false })
              .limit(limit * 5);
            if (wantedTradeTypes.length === 1) locQuery = locQuery.eq('property->>type', wantedTradeTypes[0]);
            else if (wantedTradeTypes.length > 1) locQuery = locQuery.in('property->>type', wantedTradeTypes);
            if (wantedCats.length === 1) locQuery = locQuery.eq('property->>category', wantedCats[0]);
            else if (wantedCats.length > 1) locQuery = locQuery.in('property->>category', wantedCats);
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

    // ★ 손님 태그 (DB 또는 실시간 생성)
    const clientTags: string[] = (clientCard as any).tags?.length
      ? (clientCard as any).tags
      : generateTags(clientCard);
    const clientRequired: string[] = (clientCard as any).required_tags || [];
    const clientExcluded: string[] = (clientCard as any).excluded_tags?.length
      ? (clientCard as any).excluded_tags
      : extractExcludedTags(allText);

    // ★ 중개사 실전 랭킹 — 태그 매칭 + 숫자 비교
    results = results.map((r: any) => {
      let score = 0;
      const pn = r.price_number || 0;

      // ⓪ 태그 매칭 (0~50점)
      const propTags: string[] = r.tags?.length ? r.tags : generateTags(r);
      // required_tags 체크 — 하나라도 없으면 제외
      if (clientRequired.length) {
        const missingRequired = clientRequired.filter((t: string) => !propTags.includes(t));
        if (missingRequired.length) { r._score = -1; return r; }
      }
      // excluded_tags 체크 — 하나라도 있으면 제외
      if (clientExcluded.length) {
        const hasExcluded = clientExcluded.some((t: string) => propTags.includes(t));
        if (hasExcluded) { r._score = -1; return r; }
      }
      // 겹치는 태그 수 (시설/환경 태그)
      const facilityEnvTags = clientTags.filter((t: string) =>
        !['서울','매매','전세','월세','반전세','아파트','오피스텔','빌라','원룸','투룸','쓰리룸','주택','상가','사무실','건물','토지','공장창고'].includes(t) &&
        !t.includes('구') && !t.includes('동') && !t.includes('억') && !t.includes('평') && !t.includes('보증금') && !t.includes('월세')
      );
      const matchedFacility = facilityEnvTags.filter((t: string) => propTags.includes(t));
      score += matchedFacility.length * 10; // 각 태그당 10점

      // ① 가격 (0~50점)
      if (wantedTradeType === '월세' && (wantedDeposit || wantedMonthly)) {
        // 월세: DB 필드 우선, 없으면 텍스트 파싱 폴백
        let propDeposit = r.deposit || 0;
        let propMonthly = r.monthly_rent || 0;
        if (!propDeposit && !propMonthly) {
          const priceStr = (r.property?.price || '').replace(/,/g,'');
          const slashM = priceStr.match(/(\d+)\s*\/\s*(?:월?\s*)?(\d+)/);
          if (slashM) { propDeposit = parseInt(slashM[1]); propMonthly = parseInt(slashM[2]); }
        }

        let depScore = 25, monScore = 25; // 기본 만점
        const effMaxDep = maxDeposit || (wantedDeposit ? wantedDeposit * 1.1 : 0);
        const effMaxMon = maxMonthly || (wantedMonthly ? wantedMonthly * 1.1 : 0);
        // 보증금 비교
        if (wantedDeposit && propDeposit > 0) {
          if (propDeposit <= effMaxDep) depScore = 25;           // 최대 범위 이내
          else if (propDeposit <= effMaxDep * 1.2) depScore = 15; // 약간 초과
          else depScore = -10;
        }
        // 월세금 비교
        if (wantedMonthly && propMonthly > 0) {
          if (propMonthly <= effMaxMon) monScore = 25;
          else if (propMonthly <= effMaxMon * 1.2) monScore = 15;
          else monScore = -10;
        }
        score += depScore + monScore;
      } else if (maxPrice && pn > 0) {
        // 매매/전세: 기존 로직
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
      if (wantedTradeTypes.length && p.type && !wantedTradeTypes.includes(p.type)) return false;
      if (wantedCats.length && p.category && !wantedCats.includes(p.category)) return false;
      if (wantedLocation) {
        const pLoc = p.location || '';
        const st = r.search_text || '';
        if (!pLoc.includes(wantedLocation) && !st.includes(wantedLocation)) return false;
      }
      if (maxPrice && wantedTradeType !== '월세' && r.price_number && r.price_number > maxPrice * 1.2) return false;
      return true;
    });

    // required_tags 미충족 제외
    results = results.filter((r: any) => (r._score || 0) >= 0);

    // 상위 N개
    results = results.slice(0, limit).map((r: any) => ({
      id: r.id,
      property: r.property,
      agent_id: r.agent_id || null,
      agent_comment: r.agent_comment,
      price_number: r.price_number,
      trade_status: r.trade_status,
      photos: r.photos,
      lat: r.lat,
      lng: r.lng,
      created_at: r.created_at,
      tags: r.tags || [],
      _score: r._score || null,
      similarity: r.similarity ? Math.round(r.similarity * 100) / 100 : null
    }));

    console.log(`매칭 완료: ${Date.now() - startTime}ms | ${results.length}건`);

    return new Response(JSON.stringify({
      success: true,
      client_card_id,
      wanted_trade_types: wantedTradeTypes,
      wanted_categories: wantedCats,
      wanted_location: wantedLocation,
      wanted_price: { min: minPrice, max: maxPrice },
      wanted_area: { min: wantedMinArea, max: wantedMaxArea },
      wanted_rooms: wantedRooms,
      wanted_move_by: wantedMoveBy,
      wanted_deposit: wantedDeposit,
      wanted_monthly: wantedMonthly,
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
