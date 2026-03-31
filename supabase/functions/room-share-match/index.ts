import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'
import { DISTRICT_COORDS, haversineDistance } from '../_shared/geo.ts'
import { fixTypos } from '../_shared/typo.ts'
import { getAuthUserId } from '../_shared/auth.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': 'https://hwik.kr',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// 공유방에 매물 공유 시 → 방 멤버들의 손님과 자동 매칭
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    const { card_id, room_id } = await req.json();
    if (!card_id || !room_id) throw new Error('card_id, room_id 필요');
    const shared_by = getAuthUserId(req);
    if (!shared_by) throw new Error('인증이 필요합니다');

    const startTime = Date.now();

    // ★ 보안: 요청자가 해당 방의 멤버인지 확인
    const { data: membership } = await supabase
      .from('share_room_members')
      .select('member_id')
      .eq('room_id', room_id)
      .eq('member_id', shared_by)
      .single();
    if (!membership) throw new Error('공유방 멤버가 아닙니다');

    // 1. 공유된 매물 조회
    const { data: card, error: cardErr } = await supabase
      .from('cards')
      .select('id, property, embedding, agent_id, price_number, lat, lng')
      .eq('id', card_id)
      .single();

    if (cardErr || !card) throw new Error('매물을 찾을 수 없습니다');

    const p = card.property || {};
    const tradeType = p.type;
    if (!tradeType || tradeType === '손님') {
      return new Response(JSON.stringify({ success: true, matched: 0, reason: '매물 카드 아님' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 임베딩 없으면 생성
    if (!card.embedding) {
      const OPENAI_API_KEY = Deno.env.get('OPENAI_API_KEY');
      if (!OPENAI_API_KEY) {
        return new Response(JSON.stringify({ success: true, matched: 0, reason: '임베딩 생성 불가' }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
      const cp = card.property || {};
      const catKo = ({apartment:'아파트',officetel:'오피스텔',room:'원투룸',commercial:'상가',office:'사무실'} as Record<string,string>)[cp.category] || '';
      const cardMemo = cp.memo || '';
      const embedText = [cp.type, catKo, cp.price, cp.location, cp.complex, cp.area, cp.floor, cp.room, (cp.features||[]).join(' '), cp.moveIn, cardMemo].filter(Boolean).join(' ');
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
    }

    // 2. 방 멤버 조회 (공유한 사람 제외)
    const { data: members } = await supabase
      .from('share_room_members')
      .select('member_id')
      .eq('room_id', room_id)
      .neq('role', 'pending');

    if (!members || members.length === 0) {
      return new Response(JSON.stringify({ success: true, matched: 0, reason: '방 멤버 없음' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 공유한 사람 제외
    const memberIds = members.map(m => m.member_id).filter(id => id !== shared_by);
    if (memberIds.length === 0) {
      return new Response(JSON.stringify({ success: true, matched: 0, reason: '다른 멤버 없음' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    console.log(`공유방 매칭: 매물 ${card_id} → ${memberIds.length}명 멤버 체크`);

    // 3. 멤버들의 손님 카드 일괄 조회
    const { data: clients } = await supabase
      .from('cards')
      .select('id, agent_id, property, embedding, price_number, wanted_trade_type, search_text')
      .in('agent_id', memberIds)
      .eq('property->>type', '손님')
      .not('embedding', 'is', null)
      .limit(500);

    if (!clients || clients.length === 0) {
      return new Response(JSON.stringify({ success: true, matched: 0, reason: '손님 카드 없음' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 4. 스마트 필터
    const cardCategory = p.category || '';
    const cardPrice = card.price_number || 0;
    const cardLat = card.lat || null;
    const cardLng = card.lng || null;

    const filteredClients = clients.filter(c => {
      const cp = c.property || {};
      const st = (c as any).search_text || '';
      let allText = [cp.price, cp.location, st, ...(cp.features || [])].filter(Boolean).join(' ');
      allText = fixTypos(allText);

      // 거래유형 체크
      const clientWanted = (c as any).wanted_trade_type || '';
      if (clientWanted) {
        if (clientWanted !== tradeType) return false;
      } else {
        if (tradeType === '매매' && !/매매|매도|분양|ㅁㅁ/.test(allText)) return false;
        if (tradeType === '전세' && !/전세|ㅈㅅ|젼세/.test(allText)) return false;
        if (tradeType === '월세' && !/월세|임대|ㅇㅅ|웜세/.test(allText)) return false;
      }

      if (cp.category && cardCategory && cp.category !== cardCategory) return false;

      // 지역 체크
      const clientLoc = [cp.location, memo].join(' ');
      const guPattern = /(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)/;
      const clientGuMatch = clientLoc.match(guPattern);
      if (clientGuMatch) {
        const clientGu = clientGuMatch[1];
        const coordInfo = DISTRICT_COORDS[clientGu];
        if (coordInfo && cardLat && cardLng) {
          const dist = haversineDistance(coordInfo.lat, coordInfo.lng, cardLat, cardLng);
          if (dist > 5.0) return false;
        } else {
          const cardGuMatch = (p.location || '').match(guPattern);
          if (cardGuMatch && cardGuMatch[1] !== clientGu) return false;
        }
      }

      // 가격 체크
      if (cardPrice > 0) {
        const maxMatch = allText.match(/(\d+)\s*억\s*(\d+)?\s*천?\s*(?:이내|이하|미만|까지)/);
        if (maxMatch) {
          const clientMax = parseInt(maxMatch[1]) * 10000 + (maxMatch[2] ? parseInt(maxMatch[2]) * 1000 : 0);
          if (cardPrice > clientMax * 1.3) return false;
        }
        const chunMatch = allText.match(/(\d+)\s*천\s*(?:만원?)?\s*(?:이내|이하)/);
        if (chunMatch && !maxMatch) {
          const clientMax = parseInt(chunMatch[1]) * 1000;
          if (cardPrice > clientMax * 1.3) return false;
        }
      }

      return true;
    });

    if (filteredClients.length === 0) {
      return new Response(JSON.stringify({ success: true, matched: 0, reason: '조건 매칭 손님 없음' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 5. 벡터 유사도
    const cardEmb = card.embedding;
    const THRESHOLD = 0.25;
    const matches: { clientId: string; agentId: string; similarity: number }[] = [];

    for (const client of filteredClients) {
      if (!client.embedding) continue;
      let dotProduct = 0, normA = 0, normB = 0;
      for (let i = 0; i < cardEmb.length; i++) {
        dotProduct += cardEmb[i] * client.embedding[i];
        normA += cardEmb[i] * cardEmb[i];
        normB += client.embedding[i] * client.embedding[i];
      }
      const similarity = dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
      let bonus = 0;
      if (client.property?.category && client.property.category === cardCategory) bonus += 0.1;
      const finalScore = similarity + bonus;
      if (finalScore >= THRESHOLD) {
        matches.push({ clientId: client.id, agentId: client.agent_id, similarity: Math.round(finalScore * 100) / 100 });
      }
    }

    // 6. 알림 저장
    let saved = 0;
    for (const match of matches) {
      const { error } = await supabase
        .from('match_notifications')
        .upsert({
          agent_id: match.agentId,
          card_id: card_id,
          client_card_id: match.clientId,
          similarity: match.similarity,
          is_read: false,
        }, { onConflict: 'agent_id,card_id,client_card_id', ignoreDuplicates: true });
      if (!error) saved++;
    }

    console.log(`공유방 매칭 완료: ${Date.now() - startTime}ms | ${matches.length}매칭 / ${saved}저장`);

    return new Response(JSON.stringify({
      success: true, matched: matches.length, saved,
      members_checked: memberIds.length, clients_total: clients.length, clients_filtered: filteredClients.length,
    }), { headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

  } catch (error: any) {
    console.error('room-share-match 에러:', error.message);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
