import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// 새 매물 등록 시 자동으로 손님과 매칭 체크
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

    const { card_id, agent_id } = await req.json();
    if (!card_id || !agent_id) throw new Error('card_id, agent_id 필요');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const startTime = Date.now();

    // 1. 새 매물 조회
    const { data: card, error: cardErr } = await supabase
      .from('cards')
      .select('id, property, embedding, agent_id, price_number')
      .eq('id', card_id)
      .single();

    if (cardErr || !card) throw new Error('매물을 찾을 수 없습니다');

    // ★ 임베딩 없으면 즉시 생성
    if (!card.embedding) {
      const OPENAI_API_KEY = Deno.env.get('OPENAI_API_KEY');
      if (!OPENAI_API_KEY) {
        return new Response(JSON.stringify({ success: true, matched: 0, reason: '임베딩 생성 불가' }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
      const cp = card.property || {};
      const embedText = [cp.type, cp.price, cp.location, cp.complex, cp.area, cp.floor, cp.room, cp.category, ...(cp.features || [])].filter(Boolean).join(' ');
      const embedResp = await fetch('https://api.openai.com/v1/embeddings', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: 'text-embedding-3-small', input: embedText })
      });
      const embedData = await embedResp.json();
      const embedding = embedData.data?.[0]?.embedding;
      if (!embedding) {
        return new Response(JSON.stringify({ success: true, matched: 0, reason: '임베딩 생성 실패' }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
      await supabase.from('cards').update({ embedding, search_text: embedText }).eq('id', card_id);
      card.embedding = embedding;
      console.log('매물 임베딩 즉시 생성 완료');
    }

    const p = card.property || {};
    const tradeType = p.type; // 매매/전세/월세
    if (!tradeType || tradeType === '손님') {
      return new Response(JSON.stringify({ success: true, matched: 0, reason: '매물 아님' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 2. 해당 중개사의 손님 카드 조회 (스마트 필터)
    //    - type = 손님
    //    - 같은 agent_id
    //    - 임베딩 있는 것만
    const { data: clients, error: clientErr } = await supabase
      .from('cards')
      .select('id, property, private_note, embedding, price_number')
      .eq('agent_id', agent_id)
      .eq('property->>type', '손님')
      .not('embedding', 'is', null)
      .limit(100);

    if (clientErr || !clients || clients.length === 0) {
      return new Response(JSON.stringify({ success: true, matched: 0, reason: '손님 없음' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    console.log(`자동 매칭: 매물 ${card_id} → 손님 ${clients.length}명 체크`);

    // 3. 스마트 필터: 거래유형 매칭되는 손님만
    const filteredClients = clients.filter(c => {
      const cp = c.property || {};
      const memo = c.private_note?.memo || '';
      const allText = [cp.price, cp.location, memo, ...(cp.features || [])].filter(Boolean).join(' ');

      // 거래유형 체크
      if (tradeType === '매매' && !/매매|매도/.test(allText)) return false;
      if (tradeType === '전세' && !/전세/.test(allText)) return false;
      if (tradeType === '월세' && !/월세|임대/.test(allText)) return false;

      // 지역 체크 (구 단위)
      const cardLoc = p.location || '';
      const guMatch = cardLoc.match(/(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)/);
      if (guMatch) {
        const gu = guMatch[1];
        // 손님이 특정 지역을 원하는데 다른 지역이면 제외
        const clientLoc = [cp.location, memo].join(' ');
        const clientGuMatch = clientLoc.match(/(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)/);
        if (clientGuMatch && clientGuMatch[1] !== gu) return false;
      }

      return true;
    });

    console.log(`필터 후: ${filteredClients.length}명`);

    if (filteredClients.length === 0) {
      return new Response(JSON.stringify({ success: true, matched: 0, reason: '조건 매칭 손님 없음' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 4. 벡터 유사도 계산 (코사인 유사도)
    const cardEmb = card.embedding;
    const THRESHOLD = 0.35;
    const matches: { clientId: string; similarity: number }[] = [];

    for (const client of filteredClients) {
      if (!client.embedding) continue;

      // 코사인 유사도 계산
      let dotProduct = 0;
      let normA = 0;
      let normB = 0;
      for (let i = 0; i < cardEmb.length; i++) {
        dotProduct += cardEmb[i] * client.embedding[i];
        normA += cardEmb[i] * cardEmb[i];
        normB += client.embedding[i] * client.embedding[i];
      }
      const similarity = dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));

      if (similarity >= THRESHOLD) {
        matches.push({ clientId: client.id, similarity: Math.round(similarity * 100) / 100 });
      }
    }

    console.log(`매칭 결과: ${matches.length}건 (threshold: ${THRESHOLD})`);

    // 5. 알림 저장 (중복 방지)
    let saved = 0;
    for (const match of matches) {
      const { error: insertErr } = await supabase
        .from('match_notifications')
        .upsert({
          agent_id: agent_id,
          card_id: card_id,
          client_card_id: match.clientId,
          similarity: match.similarity,
          is_read: false,
        }, {
          onConflict: 'agent_id,card_id,client_card_id',
          ignoreDuplicates: true
        });

      if (!insertErr) saved++;
    }

    console.log(`자동 매칭 완료: ${Date.now() - startTime}ms | ${saved}건 알림 저장`);

    return new Response(JSON.stringify({
      success: true,
      matched: matches.length,
      saved: saved,
      filtered_clients: filteredClients.length,
      total_clients: clients.length,
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error: any) {
    console.error('auto-match 에러:', error.message);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
