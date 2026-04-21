import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'
import { DISTRICT_COORDS, haversineDistance } from '../_shared/geo.ts'
import { fixTypos } from '../_shared/typo.ts'
import { getAuthUserId } from '../_shared/auth.ts'
import { parsePriceCondition, parseAreaCondition, isPriceMatch, isAreaMatch } from '../_shared/price.ts'
import { SELF_SELECT, CLIENT_SELECT, PROPERTY_SELECT } from '../_shared/card-fields.ts'

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

    const { card_id } = await req.json();
    if (!card_id) throw new Error('card_id 필요');
    const agent_id = await getAuthUserId(req);
    if (!agent_id) throw new Error('인증이 필요합니다');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // 권한은 agent_id + 매물 소유자 확인으로 검증 (아래에서)
    const startTime = Date.now();

    // 1. 새 매물 조회 (손님일 수도 있음 → wanted_* / required_tags / excluded_tags / tags 필수)
    const { data: card, error: cardErr } = await supabase
      .from('cards')
      .select(SELF_SELECT)
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
      const cardMemo = card.private_note?.memo || card.property?.memo || '';
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
      console.log('매물 임베딩 즉시 생성 완료');
    }

    const p = card.property || {};
    const isClient = p.type === '손님';
    const ACTIVE_CLIENT_STATUSES = ['탐색중', '급해요', '협의중'];

    // ── 방향 결정: 매물→손님 or 손님→매물 ──
    let targets: any[] = [];
    if (isClient) {
      // 자기 손님 상태가 활성이 아니면 매칭 불필요 (연락두절/계약완료)
      if (card.client_status && !ACTIVE_CLIENT_STATUSES.includes(card.client_status)) {
        return new Response(JSON.stringify({ success: true, matched: 0, reason: `손님 상태 ${card.client_status}` }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
      // 손님 카드 → 기존 매물과 매칭
      const { data, error } = await supabase
        .from('cards')
        .select(PROPERTY_SELECT)
        .eq('agent_id', agent_id)
        .neq('property->>type', '손님')
        .eq('trade_status', '계약가능')
        .not('embedding', 'is', null)
        .limit(200);
      if (error || !data?.length) {
        return new Response(JSON.stringify({ success: true, matched: 0, reason: '매물 없음' }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
      targets = data;
      console.log(`자동 매칭: 손님 ${card_id} → 매물 ${targets.length}건 체크`);
    } else {
      const tradeType = p.type;
      if (!tradeType) {
        return new Response(JSON.stringify({ success: true, matched: 0, reason: '거래유형 없음' }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
      // 자기 매물 상태가 계약가능이 아니면 매칭 불필요 (계약중/완료)
      if (card.trade_status && card.trade_status !== '계약가능') {
        return new Response(JSON.stringify({ success: true, matched: 0, reason: `매물 상태 ${card.trade_status}` }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
      // 매물 카드 → 기존 손님과 매칭 (탐색중/급해요/협의중만)
      const { data, error } = await supabase
        .from('cards')
        .select(CLIENT_SELECT)
        .eq('agent_id', agent_id)
        .eq('property->>type', '손님')
        .in('client_status', ACTIVE_CLIENT_STATUSES)
        .not('embedding', 'is', null)
        .limit(100);
      if (error || !data?.length) {
        return new Response(JSON.stringify({ success: true, matched: 0, reason: '손님 없음' }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
      targets = data;
      console.log(`자동 매칭: 매물 ${card_id} → 손님 ${targets.length}명 체크`);
    }

    // ── 스마트 필터 ──
    // 서울 25구 + 경기 주요 도시 + 인천 주요 구
    const GU_RE = /(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북|수원|성남|고양|용인|부천|안산|안양|남양주|화성|의정부|시흥|평택|광명|하남|김포|군포|의왕|과천|구리|오산|파주|양주|안성|포천|이천|광주시|여주|연수|부평|계양|미추홀|서구|남동)/;

    function filterMatch(property: any, client: any): boolean {
      const prop = property.property || {};
      const cp = client.property || {};
      const memo = client.private_note?.memo || '';
      const rawText = client.private_note?.rawText || cp.rawText || '';
      let allText = [rawText, cp.price, cp.location, cp.complex, cp.area, memo, ...(cp.features || [])].filter(Boolean).join(' ');
      allText = fixTypos(allText);

      const tradeType = prop.type;
      // 거래유형 체크 — wanted_conditions에 복수 거래유형 저장 가능 ("매매나 전세")
      const wantedTradeTypes: string[] = [];
      if (client.wanted_trade_type) wantedTradeTypes.push(client.wanted_trade_type);
      if (Array.isArray(client.wanted_conditions)) {
        for (const c of client.wanted_conditions) {
          if (c?.trade_type && !wantedTradeTypes.includes(c.trade_type)) wantedTradeTypes.push(c.trade_type);
        }
      }
      if (wantedTradeTypes.length > 0) {
        if (!wantedTradeTypes.includes(tradeType)) return false;
      } else {
        if (tradeType === '매매' && !/매매|매도|분양|ㅁㅁ/.test(allText)) return false;
        if (tradeType === '전세' && !/전세|ㅈㅅ|젼세/.test(allText)) return false;
        if (tradeType === '월세' && !/월세|임대|ㅇㅅ|웜세/.test(allText)) return false;
      }

      // 카테고리 체크 — wanted_categories 명시 시만 체크 (빈 배열이면 모든 카테고리 허용)
      const wantedCats = client.wanted_categories || [];
      if (wantedCats.length > 0 && prop.category && !wantedCats.includes(prop.category)) return false;

      // 지역 체크 — 구 이름 양쪽 다 있으면 엄격 비교 우선, 매물 구 미상일 때만 좌표 폴백
      const clientLoc = [cp.location, memo].join(' ');
      const clientGuMatch = clientLoc.match(GU_RE);
      if (clientGuMatch) {
        const clientGu = clientGuMatch[1];
        const propGuMatch = (prop.location || '').match(GU_RE);
        if (propGuMatch) {
          // 1순위: 양쪽 구 이름 엄격 비교 (다른 구는 거리 무관 탈락)
          if (propGuMatch[1] !== clientGu) return false;
        } else {
          // 2순위: 매물 구 미상 → 좌표 거리 5km 폴백
          const coordInfo = DISTRICT_COORDS[clientGu];
          const pLat = property.lat || null;
          const pLng = property.lng || null;
          if (coordInfo && pLat && pLng) {
            const dist = haversineDistance(coordInfo.lat, coordInfo.lng, pLat, pLng);
            if (dist > 5.0) return false;
          }
        }
      }

      // ★ 제외 태그 체크: 손님이 싫어하는 조건이 매물에 있으면 제외
      const propTags = property.tags || [];
      const excludedTags = client.excluded_tags || [];
      if (excludedTags.length && propTags.length) {
        if (excludedTags.some((t: string) => propTags.includes(t))) return false;
      }
      // ★ 필수 태그 체크: 손님이 꼭 원하는 조건이 매물에 없으면 제외
      const requiredTags = client.required_tags || [];
      if (requiredTags.length && propTags.length) {
        if (!requiredTags.every((t: string) => propTags.includes(t))) return false;
      }

      // 가격 체크 (정밀 파싱: 이하/이상/그쯤/범위/보월 전부 지원)
      const tradeTypeStr = prop.type || client.wanted_trade_type || '';
      const priceCondition = parsePriceCondition(allText, tradeTypeStr);
      // 월세는 DB에 저장된 wanted 값(손님 입력 구조화된 보증금/월세)을 우선
      if (tradeTypeStr === '월세') {
        if (!priceCondition.maxMonthly && !priceCondition.monthly && client.monthly_rent) {
          priceCondition.monthly = client.monthly_rent;
        }
        if (!priceCondition.maxDeposit && !priceCondition.deposit && client.deposit) {
          priceCondition.deposit = client.deposit;
        }
      } else {
        // 매매/전세도 DB wanted_conditions가 있으면 활용 (maxPrice 덮어쓰기는 하지 않고 fallback만)
        if (!priceCondition.maxPrice && !priceCondition.minPrice && client.price_number) {
          priceCondition.maxPrice = client.price_number;
        }
      }
      if (!isPriceMatch(
        property.price_number || 0,
        priceCondition,
        tradeTypeStr,
        property.deposit,
        property.monthly_rent,
      )) return false;

      // 면적 체크
      const areaCondition = parseAreaCondition(allText);
      if (!isAreaMatch(prop.area, areaCondition)) return false;

      return true;
    }

    // 필터 적용
    let filteredTargets: any[];
    if (isClient) {
      // 손님 기준: 각 매물이 이 손님 조건에 맞는지
      filteredTargets = targets.filter(prop => filterMatch(prop, card));
    } else {
      // 매물 기준: 각 손님이 이 매물에 맞는지
      filteredTargets = targets.filter(client => filterMatch(card, client));
    }

    console.log(`필터 후: ${filteredTargets.length}건`);

    if (filteredTargets.length === 0) {
      return new Response(JSON.stringify({ success: true, matched: 0, reason: '조건 매칭 없음' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // ── 벡터 유사도 계산 ──
    // pgvector는 PostgREST select 시 문자열 '[0.1,0.2,...]'로 반환 → 배열로 파싱 필요
    const parseEmb = (e: any): number[] | null => {
      if (Array.isArray(e)) return e;
      if (typeof e === 'string') { try { return JSON.parse(e); } catch { return null; } }
      return null;
    };
    const cardEmb = parseEmb(card.embedding);
    if (!cardEmb) {
      return new Response(JSON.stringify({ success: true, matched: 0, reason: 'embedding 파싱 실패' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    const THRESHOLD = 0.25;
    const matches: { propertyId: string; clientId: string; similarity: number }[] = [];

    for (const target of filteredTargets) {
      const targetEmb = parseEmb(target.embedding);
      if (!targetEmb || targetEmb.length !== cardEmb.length) continue;
      let dotProduct = 0, normA = 0, normB = 0;
      for (let i = 0; i < cardEmb.length; i++) {
        dotProduct += cardEmb[i] * targetEmb[i];
        normA += cardEmb[i] * cardEmb[i];
        normB += targetEmb[i] * targetEmb[i];
      }
      const denom = Math.sqrt(normA) * Math.sqrt(normB);
      if (denom === 0) continue;
      const similarity = dotProduct / denom;
      let bonus = 0;
      const targetCat = target.property?.category;
      const cardCat = p.category || '';
      if (targetCat && cardCat && targetCat === cardCat) bonus += 0.1;

      // 거리 점수 (좌표 둘 다 있을 때)
      let distBonus = 0;
      const propLat = isClient ? target.lat : card.lat;
      const propLng = isClient ? target.lng : card.lng;
      const cliLat = isClient ? card.lat : target.lat;
      const cliLng = isClient ? card.lng : target.lng;
      if (propLat && propLng && cliLat && cliLng) {
        const dist = haversineDistance(propLat, propLng, cliLat, cliLng);
        if (dist <= 0.5) distBonus = 0.25;
        else if (dist <= 1.0) distBonus = 0.20;
        else if (dist <= 2.0) distBonus = 0.12;
        else if (dist <= 5.0) distBonus = 0.05;
      }

      // ★ 동일 단지(kapt_code) 보너스
      let kaptBonus = 0;
      const cardKapt = card.kapt_code;
      const targetKapt = target.kapt_code;
      if (cardKapt && targetKapt && cardKapt === targetKapt) kaptBonus = 0.20;

      const finalScore = similarity + bonus + distBonus + kaptBonus;

      if (finalScore >= THRESHOLD) {
        if (isClient) {
          matches.push({ propertyId: target.id, clientId: card_id, similarity: Math.round(finalScore * 100) / 100 });
        } else {
          matches.push({ propertyId: card_id, clientId: target.id, similarity: Math.round(finalScore * 100) / 100 });
        }
      }
    }

    console.log(`매칭 결과: ${matches.length}건 (threshold: ${THRESHOLD})`);

    // ── 알림 저장 (중복 방지) ──
    let saved = 0;
    for (const match of matches) {
      const { error: insertErr } = await supabase
        .from('match_notifications')
        .upsert({
          agent_id: agent_id,
          card_id: match.propertyId,
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
      filtered_targets: filteredTargets.length,
      total_targets: targets.length,
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
