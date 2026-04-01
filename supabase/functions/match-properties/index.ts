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

    const { client_card_id, agent_id: bodyAgentId, limit = 10, threshold = 0.15 } = await req.json();
    if (!client_card_id) throw new Error('client_card_id가 필요합니다');
    const agent_id = getAuthUserId(req) || bodyAgentId || null;
    if (!agent_id) throw new Error('인증이 필요합니다');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // 권한은 agent_id로 검증 (손님 카드 소유자 확인은 아래에서)
    const startTime = Date.now();

    // 1. 손님 카드 조회
    const { data: clientCard, error: clientError } = await supabase
      .from('cards')
      .select('id, property, private_note, agent_id, wanted_trade_type, wanted_categories, wanted_conditions, move_in_date, tags, required_tags, excluded_tags, price_number, deposit, monthly_rent')
      .eq('id', client_card_id)
      .single();

    if (clientError || !clientCard) throw new Error('손님 카드를 찾을 수 없습니다');
    if (clientCard.property?.type !== '손님') throw new Error('손님 카드가 아닙니다');

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
      // "천에 50" / "오백에 30" 패턴 (말하듯 입력)
      if (!wantedDeposit && !wantedMonthly) {
        const koMatch = allText.match(/([\d]+천|[\d]+백|[\d]+억|천|오백|이천|삼천|오천)\s*에\s*(\d+)/);
        if (koMatch) {
          let dep = koMatch[1];
          if (dep === '천') dep = '1000';
          else if (dep === '오백') dep = '500';
          else if (dep === '이천') dep = '2000';
          else if (dep === '삼천') dep = '3000';
          else if (dep === '오천') dep = '5000';
          else if (dep.includes('억')) dep = String(parseInt(dep) * 10000);
          else if (dep.includes('천')) dep = String(parseInt(dep) * 1000);
          else if (dep.includes('백')) dep = String(parseInt(dep) * 100);
          wantedDeposit = parseInt(dep);
          wantedMonthly = parseInt(koMatch[2]);
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
      const guFromProp = cp.location.match(/(강남구|서초구|송파구|마포구|용산구|성동구|광진구|영등포구|강동구|동작구|관악구|종로구|중구|강서구|양천구|구로구|노원구|서대문구|은평구|중랑구|도봉구|동대문구|성북구|금천구|강북구)/);
      if (guFromProp) wantedLocation = guFromProp[1];
    }
    if (!wantedLocation) {
      const guMatch = allText.match(/(강남구|서초구|송파구|마포구|용산구|성동구|광진구|영등포구|강동구|동작구|관악구|종로구|중구|강서구|양천구|구로구|노원구|서대문구|은평구|중랑구|도봉구|동대문구|성북구|금천구|강북구)/);
      if (guMatch) wantedLocation = guMatch[1];
    }
    // "구" 없이 입력된 경우 보정 (마포→마포구)
    if (!wantedLocation) {
      const guShort = (cp.location + ' ' + allText).match(/(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)/);
      if (guShort) wantedLocation = guShort[1] + '구';
    }

    // 평수/면적
    let wantedMinArea: number | null = null;
    let wantedMaxArea: number | null = null;
    // "30평대" → 30~39
    const areaDaeMatch = allText.match(/(\d+)\s*평\s*대/);
    if (areaDaeMatch) { wantedMinArea = parseInt(areaDaeMatch[1]); wantedMaxArea = parseInt(areaDaeMatch[1]) + 9; }
    // "25평 내외" → ±10%
    if (!wantedMinArea) { const areaNaeMatch = allText.match(/(\d+)\s*평\s*내외/); if (areaNaeMatch) { const p = parseInt(areaNaeMatch[1]); wantedMinArea = Math.round(p * 0.9); wantedMaxArea = Math.round(p * 1.1); } }
    // "20평 이상" / "최소 20평" / "적어도 25평" / "20평 넘는"
    if (!wantedMinArea) { const areaMinMatch = allText.match(/(?:최소|적어도)?\s*(\d+)\s*평\s*(?:이상|넘는|넘게)/); if (areaMinMatch) wantedMinArea = parseInt(areaMinMatch[1]); }
    if (!wantedMinArea) { const areaMinMatch2 = allText.match(/(?:최소|적어도)\s*(\d+)\s*평/); if (areaMinMatch2) wantedMinArea = parseInt(areaMinMatch2[1]); }
    // "20평 이하" / "최대 25평"
    if (!wantedMaxArea) { const areaMaxMatch = allText.match(/(?:최대)?\s*(\d+)\s*평\s*(?:이하|까지|미만)/); if (areaMaxMatch) wantedMaxArea = parseInt(areaMaxMatch[1]); }
    if (!wantedMaxArea) { const areaMaxMatch2 = allText.match(/최대\s*(\d+)\s*평/); if (areaMaxMatch2) wantedMaxArea = parseInt(areaMaxMatch2[1]); }
    // "20평~30평" / "20평에서 30평 사이"
    if (!wantedMinArea && !wantedMaxArea) { const areaRange = allText.match(/(\d+)\s*평\s*[~에서]\s*(\d+)\s*평/); if (areaRange) { wantedMinArea = parseInt(areaRange[1]); wantedMaxArea = parseInt(areaRange[2]); } }
    // "넓은 집" → 30평 이상 / "소형" → 15평 이하
    if (!wantedMinArea && !wantedMaxArea) {
      if (/넓은\s*집|넓은\s*곳/.test(allText)) wantedMinArea = 30;
      else if (/소형|작은\s*집/.test(allText)) wantedMaxArea = 15;
    }
    // 숫자만 ("25평") → ±5
    if (!wantedMinArea && !wantedMaxArea) { const areaMatch = allText.match(/(\d+)\s*평/); if (areaMatch) { const p = parseInt(areaMatch[1]); wantedMinArea = Math.max(p - 5, 1); wantedMaxArea = p + 5; } }

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

    // ★ 공유방 멤버(중개사) 목록 조회 (공유방 매물 = 다른 중개사 매물)
    let sharedAgentIds: string[] = [];
    {
      const { data: myRooms } = await supabase
        .from('share_room_members')
        .select('room_id')
        .eq('member_id', effectiveAgentId)
        .eq('status', 'accepted');
      if (myRooms?.length) {
        const roomIds = myRooms.map((r: any) => r.room_id);
        // 같은 방 멤버들 = 매물 공유 대상 중개사
        const { data: members } = await supabase
          .from('share_room_members')
          .select('member_id')
          .in('room_id', roomIds)
          .eq('status', 'accepted')
          .neq('member_id', effectiveAgentId);
        if (members?.length) {
          sharedAgentIds = [...new Set(members.map((m: any) => m.member_id))];
        }
      }
      console.log(`공유방 중개사: ${sharedAgentIds.length}명`);
    }

    // ★ 태그 기반 매칭 — 필수 태그로 1차 필터 (GIN 인덱스)
    const mustTags: string[] = [];
    if (wantedLocation) mustTags.push(wantedLocation);
    // 거래유형과 카테고리는 SQL IN으로 처리 (태그 @> 는 AND 연산이라)
    console.log(`태그 매칭: must=[${mustTags}] trades=[${wantedTradeTypes}] cats=[${wantedCats}] price=${minPrice}~${maxPrice}`);

    let results: any[] = [];
    const selectCols = 'id, property, agent_id, agent_comment, price_number, deposit, monthly_rent, trade_status, photos, lat, lng, created_at, search_text, tags';

    // 공통 필터 적용 헬퍼
    function applyFilters(q: any, tagsOnly = false) {
      q = q.neq('property->>type', '손님').eq('trade_status', '계약가능');
      // 태그: 지역 + 거래유형을 하나의 배열로 합쳐서 한번에 @>
      const allMust = [...mustTags];
      if (wantedTradeTypes.length === 1) allMust.push(wantedTradeTypes[0]);
      if (allMust.length) q = q.filter('tags', 'cs', JSON.stringify(allMust));
      if (wantedTradeTypes.length > 1) q = q.in('property->>type', wantedTradeTypes);
      if (!tagsOnly) {
        if (wantedCats.length === 1) q = q.eq('property->>category', wantedCats[0]);
        else if (wantedCats.length > 1) q = q.in('property->>category', wantedCats);
        if (wantedTradeType === '월세') {
          const effMaxDep = maxDeposit || (wantedDeposit ? Math.round(wantedDeposit * 1.3) : 0);
          const effMaxMon = maxMonthly || (wantedMonthly ? Math.round(wantedMonthly * 1.3) : 0);
          if (effMaxDep > 0) q = q.lte('deposit', effMaxDep);
          if (effMaxMon > 0) q = q.lte('monthly_rent', effMaxMon);
        } else {
          if (maxPrice) q = q.lte('price_number', Math.round(maxPrice * 1.1));
        }
      }
      return q.order('created_at', { ascending: false }).limit(limit * 10);
    }

    // 3. ★ 태그 + 숫자 필터 SQL 검색 (내 매물 + 공유방 매물 병렬)
    {
      // 내 매물
      const myQuery = applyFilters(supabase.from('cards').select(selectCols).eq('agent_id', effectiveAgentId));
      const myPromise = myQuery.then(({ data, error }: any) => { if(error) console.error('myQuery error:', JSON.stringify(error)); return (!error && data) ? data : []; });

      // 공유방 매물 (공유 중개사의 매물)
      let sharedPromise = Promise.resolve([] as any[]);
      if (sharedAgentIds.length) {
        const sq = applyFilters(supabase.from('cards').select(selectCols).in('agent_id', sharedAgentIds));
        sharedPromise = sq.then(({ data, error }: any) => { if(error) console.error('sharedQuery error:', JSON.stringify(error)); return (!error && data) ? data : []; });
      }

      const [myData, sharedData] = await Promise.all([myPromise, sharedPromise]);
      const seen = new Set<string>();
      const merged: any[] = [];
      // 내 매물 우선
      for (const r of myData) { if (!seen.has(r.id)) { seen.add(r.id); merged.push({ ...r, _source: 'my', similarity: 0 }); } }
      for (const r of sharedData) { if (!seen.has(r.id)) { seen.add(r.id); merged.push({ ...r, _source: 'shared', similarity: 0 }); } }
      results = merged;
      console.log(`SQL 매칭: 내매물 ${myData.length}건 + 공유 ${sharedData.length}건 = ${results.length}건 | ${Date.now() - startTime}ms`);
    }

    // SQL 결과 부족하면 — 태그 조건 완화 (지역만으로 재검색, 내매물+공유방)
    if (results.length < 3 && mustTags.length) {
      const existingIds = new Set(results.map(r => r.id));
      // 내 매물
      const { data: fbMy } = await supabase.from('cards').select(selectCols)
        .eq('agent_id', effectiveAgentId).neq('property->>type', '손님').eq('trade_status', '계약가능')
        .filter('tags', 'cs', JSON.stringify(mustTags)).order('created_at', { ascending: false }).limit(limit * 3);
      // 공유방 매물
      let fbShared: any[] = [];
      if (sharedAgentIds.length) {
        const { data } = await supabase.from('cards').select(selectCols)
          .in('agent_id', sharedAgentIds).neq('property->>type', '손님').eq('trade_status', '계약가능')
          .filter('tags', 'cs', JSON.stringify(mustTags)).order('created_at', { ascending: false }).limit(limit * 3);
        if (data) fbShared = data;
      }
      const allFb = [...(fbMy || []), ...fbShared];
      const newResults = allFb.filter((r: any) => !existingIds.has(r.id)).map((r: any) => ({ ...r, similarity: 0 }));
      results = [...results, ...newResults];
      if (newResults.length) console.log(`태그 완화 재검색: +${newResults.length}건`);
    }

    // ★ 임베딩 보조 (보험 — 태그로 못 잡는 케이스 보완, 결과 3건 미만일 때만)
    if (results.length < 3 && clientCard.embedding) {
      try {
        const { data: embMatches } = await supabase.rpc('match_properties_for_client', {
          p_client_embedding: clientCard.embedding,
          p_agent_id: effectiveAgentId,
          p_trade_type: wantedTradeType,
          p_threshold: threshold,
          p_limit: limit * 3
        });
        if (embMatches?.length) {
          const existingIds = new Set(results.map(r => r.id));
          const newResults = embMatches.filter((r: any) => !existingIds.has(r.id)).map((r: any) => ({ ...r, similarity: r.similarity || 0 }));
          results = [...results, ...newResults];
          console.log(`임베딩 보조(보험): +${newResults.length}건`);
        }
      } catch(e) { console.warn('임베딩 보조 실패 (무시):', (e as Error).message); }
    }

    // ★ 거래유형 하드필터 (복수 허용)
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
      const coordInfo = DISTRICT_COORDS[wantedLocation] || DISTRICT_COORDS[wantedLocation.replace(/구$/, '')];

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
          console.log(`결과 내 위치 매칭 0건 → '${wantedLocation}' DB 재검색 (점진적 반경, 내매물+공유방)`);
          for (const radius of [5, 8]) {
            // 내 매물 + 공유방 매물 동시 검색
            const buildLocQ = (base: any) => {
              let q = base.neq('property->>type', '손님').eq('trade_status', '계약가능')
                .order('created_at', { ascending: false }).limit(limit * 5);
              if (wantedTradeTypes.length === 1) q = q.eq('property->>type', wantedTradeTypes[0]);
              else if (wantedTradeTypes.length > 1) q = q.in('property->>type', wantedTradeTypes);
              if (wantedCats.length === 1) q = q.eq('property->>category', wantedCats[0]);
              else if (wantedCats.length > 1) q = q.in('property->>category', wantedCats);
              return q;
            };
            const locMyQ = buildLocQ(supabase.from('cards').select(selectCols).eq('agent_id', effectiveAgentId));
            let locSharedQ = Promise.resolve({ data: null as any });
            if (sharedAgentIds.length) {
              locSharedQ = buildLocQ(supabase.from('cards').select(selectCols).in('agent_id', sharedAgentIds));
            }
            const [{ data: locMyData }, { data: locShData }] = await Promise.all([locMyQ, locSharedQ]);
            const locData = [...(locMyData || []), ...(locShData || [])];

            if (locData.length > 0) {
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

    // ═══════════════════════════════════════════════════════════
    // ★ 125점 만점 매칭 점수 (중개사 14년 실전 기반)
    // ═══════════════════════════════════════════════════════════
    results = results.map((r: any) => {
      let score = 0;
      const pn = r.price_number || 0;
      const propTags: string[] = r.tags?.length ? r.tags : generateTags(r);

      // ── 사전 체크: required_tags / excluded_tags ──
      if (clientRequired.length) {
        if (clientRequired.some((t: string) => !propTags.includes(t))) { r._score = -1; return r; }
      }
      if (clientExcluded.length) {
        if (clientExcluded.some((t: string) => propTags.includes(t))) { r._score = -50; return r; }
      }

      // ① 거래유형 (40점) — 불일치 시 0점 즉시 리턴
      const propType = r.property?.type || '';
      if (wantedTradeTypes.length && wantedTradeTypes.includes(propType)) {
        score += 40;
      } else if (wantedTradeTypes.length) {
        r._score = 0; return r; // Hard Filter — 전세 찾는데 월세 추천 금지
      }

      // ② 가격 적합도 (30점) — 예산 범위 내 포함 여부
      if (wantedTradeType === '월세' && (wantedDeposit || wantedMonthly)) {
        let propDep = r.deposit || 0, propMon = r.monthly_rent || 0;
        if (!propDep && !propMon) {
          const ps = (r.property?.price || '').replace(/,/g, '');
          const sm = ps.match(/(\d+)\s*\/\s*(\d+)/);
          if (sm) { propDep = parseInt(sm[1]); propMon = parseInt(sm[2]); }
        }
        const effMaxDep = maxDeposit || (wantedDeposit ? wantedDeposit * 1.1 : 999999);
        const effMaxMon = maxMonthly || (wantedMonthly ? wantedMonthly * 1.1 : 999999);
        let priceScore = 30;
        // 보증금 초과 감점
        if (propDep > effMaxDep) { const over = (propDep - effMaxDep) / effMaxDep; priceScore -= Math.min(Math.round(over * 60), 30); }
        // 월세 초과 감점
        if (propMon > effMaxMon) { const over = (propMon - effMaxMon) / effMaxMon; priceScore -= Math.min(Math.round(over * 60), 30); }
        score += Math.max(priceScore, 0);
      } else if (maxPrice && pn > 0) {
        if (pn <= maxPrice) {
          score += 30;
        } else {
          const overPct = ((pn - maxPrice) / maxPrice) * 100;
          score += Math.max(30 - Math.round(overPct), 0); // 5% 초과마다 5점 감점
        }
      } else if (minPrice && pn > 0) {
        if (pn >= minPrice) score += 30;
        else score += Math.max(30 - Math.round(((minPrice - pn) / minPrice) * 60), 0);
      }

      // ③ 위치/입지 (20점) — 동 일치 20점, 인접 15점, 3km 10점
      if (wantedLocation) {
        const propLoc = r.property?.location || '';
        if (propLoc.includes(wantedLocation)) {
          score += 20; // 동/구 완전 일치
        } else if (r.lat && r.lng && (DISTRICT_COORDS[wantedLocation] || DISTRICT_COORDS[wantedLocation.replace(/구$/, '')])) {
          const coord = DISTRICT_COORDS[wantedLocation] || DISTRICT_COORDS[wantedLocation.replace(/구$/, '')];
          const dist = haversineDistance(coord.lat, coord.lng, r.lat, r.lng);
          if (dist <= 1) score += 15;
          else if (dist <= 3) score += 10;
          else if (dist <= 5) score += 5;
        }
      }

      // ④ 매물유형 (15점) — 아파트/빌라/오피스텔 일치
      if (wantedCats.length) {
        const propCat = r.property?.category || '';
        const catMatch = wantedCats.includes(propCat) || wantedCats.some((c: string) => propTags.includes(c));
        if (catMatch) score += 15;
      }

      // ⑤ 특수조건 태그 (20점, 캡) — 태그당 5점, HUG 10점
      const specialTags = clientTags.filter((t: string) =>
        !['서울','매매','전세','월세','반전세','아파트','오피스텔','원투룸','빌라','원룸','투룸','쓰리룸','주택','상가','사무실','건물','토지','공장창고'].includes(t) &&
        !t.includes('구') && !t.includes('동') && !t.includes('억') && !t.includes('평') && !t.includes('보증금') && !t.includes('월세')
      );
      let tagScore = 0;
      for (const t of specialTags) {
        if (propTags.includes(t)) {
          tagScore += (t === 'HUG가능' || t === '무융자') ? 10 : 5;
        }
      }
      score += Math.min(tagScore, 20); // 캡 20점

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

      // ⑦ 임베딩 보너스 (보험 — 최대 5점)
      if (r.similarity) score += Math.min(Math.round(r.similarity * 5), 5);

      // ★ 80점 이상 = 강추 매물
      return { ...r, _score: score, _recommend: score >= 80 };
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
    results = results.slice(0, limit);

    // ★ 중개사 프로필 조회 (공유 매물에 중개사 정보 첨부)
    const otherAgentIds = [...new Set(results.filter((r: any) => r.agent_id && r.agent_id !== effectiveAgentId).map((r: any) => r.agent_id))];
    let agentProfiles: Record<string, any> = {};
    if (otherAgentIds.length) {
      const { data: profiles } = await supabase.from('profiles').select('id, business_name, phone').in('id', otherAgentIds);
      if (profiles) {
        for (const p of profiles) agentProfiles[p.id] = p;
      }
    }
    // 공유방 이름 조회 (어떤 공유방에서 온 매물인지)
    let cardRoomNames: Record<string, string> = {};
    if (otherAgentIds.length) {
      const myRoomIds = (await supabase.from('share_room_members').select('room_id').eq('member_id', effectiveAgentId).eq('status', 'accepted')).data?.map((r: any) => r.room_id) || [];
      if (myRoomIds.length) {
        const resultIds = results.map((r: any) => r.id);
        const { data: shares } = await supabase.from('card_shares').select('card_id, room_id').in('card_id', resultIds).in('room_id', myRoomIds);
        if (shares?.length) {
          const roomIds = [...new Set(shares.map((s: any) => s.room_id))];
          const { data: rooms } = await supabase.from('share_rooms').select('id, name').in('id', roomIds);
          const roomMap: Record<string, string> = {};
          if (rooms) for (const rm of rooms) roomMap[rm.id] = rm.name;
          for (const s of shares) {
            if (!cardRoomNames[s.card_id] && roomMap[s.room_id]) cardRoomNames[s.card_id] = roomMap[s.room_id];
          }
        }
      }
    }

    results = results.map((r: any) => {
      const isMine = r.agent_id === effectiveAgentId;
      const profile = !isMine ? agentProfiles[r.agent_id] : null;
      return {
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
        _recommend: r._recommend || false,
        _agent: profile ? { name: profile.business_name, phone: profile.phone } : null,
        _room: cardRoomNames[r.id] || null
      };
    });

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
      // _debug: { sharedAgentIds: sharedAgentIds.length, mustTags, ..._debugSql },
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
