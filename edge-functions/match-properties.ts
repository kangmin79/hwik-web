import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

    const { client_card_id, agent_id, limit = 20, threshold = 0.2 } = await req.json();
    if (!client_card_id) throw new Error('client_card_id가 필요합니다');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const startTime = Date.now();

    // 1. 손님 카드 조회
    const { data: clientCard, error: clientError } = await supabase
      .from('cards')
      .select('id, property, private_note, embedding, agent_id')
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
      const embedText = [cp.type, cp.price, cp.location, cp.complex, cp.area, ...(cp.features || []), memo].filter(Boolean).join(' ');

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

    // ★ 보안: 본인 손님만 조회 가능
    if (agent_id && clientCard.agent_id !== agent_id) {
      throw new Error('권한이 없습니다');
    }

    // 2. ★ 손님 조건 상세 분석 (모든 텍스트에서 추출)
    const cp = clientCard.property || {};
    const memo = clientCard.private_note?.memo || '';
    const allText = [cp.price, cp.location, cp.complex, cp.area, memo, ...(cp.features || [])].filter(Boolean).join(' ');

    // 거래유형
    let wantedTradeType: string | null = null;
    if (/매매|매도|분양/.test(allText)) wantedTradeType = '매매';
    else if (/전세/.test(allText)) wantedTradeType = '전세';
    else if (/월세|임대/.test(allText)) wantedTradeType = '월세';

    // 카테고리
    let wantedCategory: string | null = null;
    if (/사무실|오피스$|코워킹/.test(allText)) wantedCategory = 'office';
    else if (/상가|점포|매장|카페|음식점|식당/.test(allText)) wantedCategory = 'commercial';
    else if (/오피스텔/.test(allText)) wantedCategory = 'officetel';
    else if (/원룸|투룸|빌라|다세대|주택|쓰리룸/.test(allText)) wantedCategory = 'room';
    else if (/아파트|주상복합/.test(allText)) wantedCategory = 'apartment';

    // 가격 범위
    let minPrice: number | null = null;
    let maxPrice: number | null = null;

    // "3억 이내/이하" → maxPrice
    const maxMatch = allText.match(/(\d+)\s*억\s*(?:\d*천?)?\s*(?:이내|이하|미만|까지)/);
    if (maxMatch) {
      maxPrice = parseInt(maxMatch[1]) * 10000;
      const chunMatch = allText.match(/(\d+)\s*억\s*(\d+)\s*천/);
      if (chunMatch) maxPrice = parseInt(chunMatch[1]) * 10000 + parseInt(chunMatch[2]) * 1000;
    }
    // "3억~5억" → min, max
    const rangeMatch = allText.match(/(\d+)\s*억\s*~\s*(\d+)\s*억/);
    if (rangeMatch) {
      minPrice = parseInt(rangeMatch[1]) * 10000;
      maxPrice = parseInt(rangeMatch[2]) * 10000;
    }
    // 월세: "월세 80 이하" → maxPrice (월세 기준)
    if (wantedTradeType === '월세') {
      const monthlyMax = allText.match(/월(?:세)?\s*(\d+)\s*이하/);
      if (monthlyMax) maxPrice = parseInt(monthlyMax[1]);
    }

    // 지역 (구 단위)
    let wantedLocation: string | null = null;
    const guMatch = allText.match(/(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)/);
    if (guMatch) wantedLocation = guMatch[1];

    const effectiveAgentId = agent_id || clientCard.agent_id || '';

    console.log(`매칭 조건: trade=${wantedTradeType} cat=${wantedCategory} loc=${wantedLocation} price=${minPrice}~${maxPrice}`);

    // 3. ★ 벡터 검색 (넓게) + 후필터 (정확하게)
    const { data: matches, error: matchError } = await supabase.rpc('match_properties_for_client', {
      p_client_embedding: clientCard.embedding,
      p_agent_id: effectiveAgentId,
      p_trade_type: wantedTradeType,
      p_threshold: threshold,
      p_limit: limit * 5  // 넓게 가져와서 후필터
    });

    let results = matches || [];

    if (matchError) {
      // 폴백
      console.warn('RPC 실패, 폴백:', matchError.message);
      const { data: fbData } = await supabase.rpc('search_cards_advanced', {
        p_agent_id: effectiveAgentId,
        p_search_text: null,
        p_embedding: clientCard.embedding,
        p_property_type: wantedCategory,
        p_trade_type: wantedTradeType,
        p_min_price: minPrice,
        p_max_price: maxPrice,
        p_days_ago: null,
        p_limit: limit * 3,
        p_search_mode: 'my'
      });
      results = (fbData || []).filter((r: any) => r.property?.type !== '손님');
    }

    // 4. ★ 후필터: 카테고리, 가격, 지역
    if (wantedCategory) {
      const catFiltered = results.filter((r: any) => r.property?.category === wantedCategory);
      if (catFiltered.length >= 3) results = catFiltered; // 3개 이상이면 필터 적용
    }

    if (maxPrice && wantedTradeType !== '월세') {
      const priceFiltered = results.filter((r: any) => {
        const pn = r.price_number || 0;
        if (minPrice && pn < minPrice) return false;
        if (maxPrice && pn > maxPrice * 1.2) return false; // 20% 여유
        return true;
      });
      if (priceFiltered.length >= 2) results = priceFiltered;
    }

    if (wantedLocation) {
      const locFiltered = results.filter((r: any) => {
        const loc = r.property?.location || '';
        return loc.includes(wantedLocation);
      });
      if (locFiltered.length >= 2) results = locFiltered;
    }

    // ★ 계약가능 매물만 (계약중/완료 제외 — 손님에게 추천 가능한 매물만)
    results = results.filter((r: any) => {
      const status = r.trade_status || '계약가능';
      return status === '계약가능';
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
