import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'
import { DISTRICT_COORDS, haversineDistance } from '../_shared/geo.ts'
import { fixTypos } from '../_shared/typo.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': 'https://hwik.kr',
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

    // 권한은 agent_id + 매물 소유자 확인으로 검증 (아래에서)
    const startTime = Date.now();

    // 1. 새 매물 조회
    const { data: card, error: cardErr } = await supabase
      .from('cards')
      .select('id, property, embedding, agent_id, price_number, lat, lng')
      .eq('id', card_id)
      .single();

    if (cardErr || !card) throw new Error('매물을 찾을 수 없습니다');
    // ★ 보안: 본인 매물인지 확인
    if (card.agent_id !== agent_id) throw new Error('본인 매물만 매칭 가능합니다');

    // ★ 임베딩 없으면 즉시 생성
    if (!card.embedding) {
      const OPENAI_API_KEY = Deno.env.get('OPENAI_API_KEY');
      if (!OPENAI_API_KEY) {
        return new Response(JSON.stringify({ success: true, matched: 0, reason: '임베딩 생성 불가' }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
      const cp = card.property || {};
      const catKo = {apartment:'아파트',officetel:'오피스텔',room:'원투룸',commercial:'상가',office:'사무실'}[cp.category] || '';
      const embedText = [cp.type, catKo, cp.price, cp.location, cp.complex, cp.area, cp.floor, cp.room, (cp.features||[]).join(' '), cp.moveIn].filter(Boolean).join(' ');
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

    // 3. 스마트 필터: 거래유형 + 카테고리 + 지역 + 가격
    const cardCategory = p.category || '';
    const cardPrice = card.price_number || 0;
    const cardLat = card.lat || null;  // need to fetch lat/lng
    const cardLng = card.lng || null;

    const filteredClients = clients.filter(c => {
      const cp = c.property || {};
      const memo = c.private_note?.memo || '';
      let allText = [cp.price, cp.location, memo, ...(cp.features || [])].filter(Boolean).join(' ');
      // ★ 오타/한글숫자 교정
      allText = fixTypos(allText);

      // 거래유형 체크
      if (tradeType === '매매' && !/매매|매도|분양|ㅁㅁ/.test(allText)) return false;
      if (tradeType === '전세' && !/전세|ㅈㅅ|젼세/.test(allText)) return false;
      if (tradeType === '월세' && !/월세|임대|ㅇㅅ|웜세/.test(allText)) return false;

      // 카테고리 체크 (손님이 특정 카테고리를 원하면)
      if (cp.category && cardCategory && cp.category !== cardCategory) return false;

      // 지역 체크 — 좌표 기반 (3km 이내) 또는 텍스트 매칭
      const clientLoc = [cp.location, memo].join(' ');
      const clientGuMatch = clientLoc.match(/(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)/);

      if (clientGuMatch) {
        const clientGu = clientGuMatch[1];
        const coordInfo = DISTRICT_COORDS[clientGu];

        if (coordInfo && cardLat && cardLng) {
          // 좌표 기반: 손님 원하는 구의 중심에서 매물까지 거리
          const dist = haversineDistance(coordInfo.lat, coordInfo.lng, cardLat, cardLng);
          if (dist > 5.0) return false; // 5km 넘으면 제외
        } else {
          // 텍스트 폴백
          const cardLoc = p.location || '';
          const cardGuMatch = cardLoc.match(/(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)/);
          if (cardGuMatch && cardGuMatch[1] !== clientGu) return false;
        }
      }

      // 가격 체크 (손님 예산 범위 확인, 천 단위 포함)
      if (cardPrice > 0) {
        const maxMatch = allText.match(/(\d+)\s*억\s*(\d+)?\s*천?\s*(?:이내|이하|미만|까지)/);
        if (maxMatch) {
          const clientMax = parseInt(maxMatch[1]) * 10000 + (maxMatch[2] ? parseInt(maxMatch[2]) * 1000 : 0);
          if (cardPrice > clientMax * 1.3) return false; // 30% 초과하면 제외
        }
        // "5천 이하" 패턴
        const chunMatch = allText.match(/(\d+)\s*천\s*(?:만원?)?\s*(?:이내|이하)/);
        if (chunMatch && !maxMatch) {
          const clientMax = parseInt(chunMatch[1]) * 1000;
          if (cardPrice > clientMax * 1.3) return false;
        }
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
    const THRESHOLD = 0.25;
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

      // 추가 점수: 카테고리/가격 매칭 보너스
      let bonus = 0;
      const clientCat = client.property?.category;
      if (clientCat && clientCat === cardCategory) bonus += 0.1;

      const finalScore = similarity + bonus;

      if (finalScore >= THRESHOLD) {
        matches.push({ clientId: client.id, similarity: Math.round(finalScore * 100) / 100 });
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
