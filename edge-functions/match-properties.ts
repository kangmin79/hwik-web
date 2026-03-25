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

    const { client_card_id, agent_id, limit = 20, threshold = 0.3 } = await req.json();
    if (!client_card_id) throw new Error('client_card_id가 필요합니다');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const startTime = Date.now();

    // 1. 손님 카드 조회 (임베딩 + property 포함)
    const { data: clientCard, error: clientError } = await supabase
      .from('cards')
      .select('id, property, embedding, agent_id')
      .eq('id', client_card_id)
      .single();

    if (clientError || !clientCard) throw new Error('손님 카드를 찾을 수 없습니다');
    if (clientCard.property?.type !== '손님') throw new Error('손님 카드가 아닙니다');
    if (!clientCard.embedding) throw new Error('손님 카드에 임베딩이 없습니다');

    // 2. 손님의 원하는 거래유형 파악 (property.price 텍스트에서 추출)
    const clientProperty = clientCard.property || {};
    const clientText = [
      clientProperty.price, clientProperty.rawText,
      ...(clientProperty.features || [])
    ].filter(Boolean).join(' ');

    let wantedTradeType: string | null = null;
    if (/매매|매도|분양/.test(clientText)) wantedTradeType = '매매';
    else if (/전세/.test(clientText)) wantedTradeType = '전세';
    else if (/월세|임대/.test(clientText)) wantedTradeType = '월세';

    // 3. 벡터 유사도 검색 (RPC 사용)
    //    match_properties_for_client 함수가 DB에 없을 수 있으므로
    //    search_cards_advanced를 활용하거나 직접 쿼리
    const effectiveAgentId = agent_id || clientCard.agent_id || '';

    // pgvector cosine distance 검색: 1 - (embedding <=> target) as similarity
    // cards 테이블에서 매물만 검색
    const { data: matches, error: matchError } = await supabase.rpc('match_properties_for_client', {
      p_client_embedding: clientCard.embedding,
      p_agent_id: effectiveAgentId,
      p_trade_type: wantedTradeType,
      p_threshold: threshold,
      p_limit: limit
    });

    if (matchError) {
      // RPC가 없으면 폴백: search_cards_advanced 활용
      console.warn('match_properties_for_client RPC 없음, 폴백 사용:', matchError.message);

      const { data: fallbackData, error: fbError } = await supabase.rpc('search_cards_advanced', {
        p_agent_id: effectiveAgentId,
        p_search_text: null,
        p_embedding: clientCard.embedding,
        p_property_type: null,
        p_trade_type: wantedTradeType,
        p_min_price: null,
        p_max_price: null,
        p_days_ago: null,
        p_limit: limit * 2,
        p_search_mode: 'my'
      });

      if (fbError) throw new Error('매칭 검색 실패: ' + fbError.message);

      // 손님 카드 제외 + 유사도 필터
      const filtered = (fallbackData || [])
        .filter((r: any) => {
          if (r.property?.type === '손님') return false;
          if (r.similarity !== undefined && r.similarity < threshold) return false;
          return true;
        })
        .slice(0, limit)
        .map((r: any) => ({
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

      console.log(`매칭 완료 (폴백): ${Date.now() - startTime}ms | ${filtered.length}건`);

      return new Response(JSON.stringify({
        success: true,
        client_card_id,
        wanted_trade_type: wantedTradeType,
        results: filtered,
        count: filtered.length,
        mode: 'fallback'
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // RPC 성공 시
    const results = (matches || []).map((r: any) => ({
      id: r.id,
      property: r.property,
      agent_comment: r.agent_comment,
      price_number: r.price_number,
      trade_status: r.trade_status,
      photos: r.photos,
      lat: r.lat,
      lng: r.lng,
      created_at: r.created_at,
      similarity: Math.round(r.similarity * 100) / 100
    }));

    console.log(`매칭 완료: ${Date.now() - startTime}ms | ${results.length}건 | 거래유형: ${wantedTradeType || '전체'}`);

    return new Response(JSON.stringify({
      success: true,
      client_card_id,
      wanted_trade_type: wantedTradeType,
      results,
      count: results.length,
      mode: 'rpc'
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
