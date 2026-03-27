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

// 새 매물 등록 시 자동으로 손님과 매칭 체크
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

    const { card_id, agent_id } = await req.json();
    if (!card_id || !agent_id) throw new Error('card_id, agent_id 필요');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // ★ 인증 확인 (선택적 — anon key도 허용)
    const authHeader = req.headers.get('Authorization');
    if (authHeader) {
      try {
        const token = authHeader.replace('Bearer ', '');
        const payload = JSON.parse(atob(token.split('.')[1] || '{}'));
        if (payload.role !== 'anon') {
          const { data: { user } } = await supabase.auth.getUser(token);
          if (user && agent_id && user.id !== agent_id) {
            throw new Error('권한이 없습니다');
          }
        }
      } catch(e) {
        if (e.message === '권한이 없습니다') throw e;
      }
    }

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
      const typoFix: Record<string, string> = {
        '일억':'1억','이억':'2억','삼억':'3억','사억':'4억','오억':'5억',
        '육억':'6억','칠억':'7억','팔억':'8억','구억':'9억','십억':'10억',
        '일천':'1천','이천':'2천','삼천':'3천','사천':'4천','오천':'5천',
        '육천':'6천','칠천':'7천','팔천':'8천','구천':'9천',
        'ㅈㅅ':'전세','젼세':'전세','ㅁㅁ':'매매','ㅇㅅ':'월세','웜세':'월세','웜ㄴ세':'월세',
        '아빠트':'아파트','옵텔':'오피스텔','오피스탤':'오피스텔','상과':'상가',
        '안넘게':'이하','안쪽':'이하',
      };
      for (const [t,f] of Object.entries(typoFix)) { if (allText.includes(t)) allText = allText.replace(new RegExp(t,'g'), f); }

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
