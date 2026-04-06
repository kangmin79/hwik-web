import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'
import { DISTRICT_COORDS } from '../_shared/geo.ts'
import { getAuthUserId } from '../_shared/auth.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': 'https://hwik.kr',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// 카카오 Geocoding API 호출
async function kakaoGeocode(query: string, apiKey: string): Promise<{ lat: number; lng: number } | null> {
  if (!query?.trim()) return null;
  try {
    const url = `https://dapi.kakao.com/v2/local/search/address.json?query=${encodeURIComponent(query)}&size=1`;
    const resp = await fetch(url, { headers: { Authorization: `KakaoAK ${apiKey}` } });
    if (!resp.ok) return null;
    const data = await resp.json();
    const doc = data.documents?.[0];
    if (doc) return { lat: parseFloat(doc.y), lng: parseFloat(doc.x) };
  } catch {
    // geocoding 실패 시 null 반환
  }
  return null;
}

// 카카오 키워드 검색 API 호출 (단지명 검색)
async function kakaoKeywordSearch(query: string, apiKey: string): Promise<{ lat: number; lng: number } | null> {
  if (!query?.trim()) return null;
  try {
    const url = `https://dapi.kakao.com/v2/local/search/keyword.json?query=${encodeURIComponent(query)}&size=1`;
    const resp = await fetch(url, { headers: { Authorization: `KakaoAK ${apiKey}` } });
    if (!resp.ok) return null;
    const data = await resp.json();
    const doc = data.documents?.[0];
    if (doc) return { lat: parseFloat(doc.y), lng: parseFloat(doc.x) };
  } catch {
    // 키워드 검색 실패 시 null 반환
  }
  return null;
}

// DISTRICT_COORDS에서 텍스트 키워드 매칭
function fallbackFromDistrict(text: string): { lat: number; lng: number; key: string } | null {
  // 긴 키워드 우선 (더 구체적인 지역 먼저)
  const keys = Object.keys(DISTRICT_COORDS).sort((a, b) => b.length - a.length);
  for (const key of keys) {
    if (text.includes(key)) {
      const coord = DISTRICT_COORDS[key];
      return { lat: coord.lat, lng: coord.lng, key };
    }
  }
  return null;
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const KAKAO_API_KEY = Deno.env.get('KAKAO_API_KEY') || '';

    const { card_id } = await req.json();
    if (!card_id) throw new Error('card_id 필요');

    const agent_id = getAuthUserId(req);
    if (!agent_id) throw new Error('인증이 필요합니다');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // 1. 카드 조회
    const { data: card, error: cardErr } = await supabase
      .from('cards')
      .select('id, agent_id, property, private_note, tags, lat, lng')
      .eq('id', card_id)
      .single();

    if (cardErr || !card) throw new Error('카드를 찾을 수 없습니다');
    if (card.agent_id !== agent_id) throw new Error('본인 카드만 처리 가능합니다');

    const p = card.property || {};
    const privateMemo = card.private_note?.memo || '';
    const rawText = p.rawText || '';

    // 2. 텍스트 합치기
    const fullText = [p.location, p.complex, rawText, privateMemo].filter(Boolean).join(' ');

    const addedTags: string[] = [];
    let finalLat: number | null = card.lat || null;
    let finalLng: number | null = card.lng || null;
    let source = 'existing';

    // 3. 역 감지 → stations 테이블 조회
    const stationMatches = [...new Set(
      [...fullText.matchAll(/([가-힣a-zA-Z0-9]{1,10})역/g)].map(m => m[1])
    )];

    for (const stationName of stationMatches) {
      try {
        const { data: stations } = await supabase
          .from('stations')
          .select('name, lat, lon')
          .ilike('name', `%${stationName}%`)
          .limit(1);

        if (stations && stations.length > 0) {
          const st = stations[0];
          addedTags.push(`${stationName}역`);
          // 카드에 좌표가 없으면 역 좌표 사용
          if (!finalLat && !finalLng && st.lat && st.lon) {
            finalLat = st.lat;
            finalLng = st.lon;
            source = 'station';
          }
        }
      } catch {
        // 역 조회 실패 무시
      }
    }

    // 4. 학교 감지 → schools 테이블 조회
    const schoolPatterns = [
      /([가-힣]{2,10})(초등학교|초교)/g,
      /([가-힣]{2,10})(중학교|중교)/g,
      /([가-힣]{2,10})(고등학교|고교)/g,
      /([가-힣]{2,10})(대학교|대학)/g,
    ];

    for (const pattern of schoolPatterns) {
      const matches = [...fullText.matchAll(pattern)];
      for (const m of matches) {
        const schoolName = m[1] + m[2];
        try {
          const { data: schools } = await supabase
            .from('schools')
            .select('name, lat, lon')
            .ilike('name', `%${m[1]}%`)
            .limit(1);

          if (schools && schools.length > 0) {
            addedTags.push(schoolName);
          } else {
            // DB에 없어도 텍스트에서 발견한 학교명 태그 추가
            addedTags.push(schoolName);
          }
        } catch {
          addedTags.push(schoolName);
        }
      }
    }

    // 5. 카카오 Geocoding (좌표가 없거나 개선이 필요할 때)
    if ((!finalLat || !finalLng) && KAKAO_API_KEY) {
      // complex + location 조합 시도
      if (p.complex && p.location) {
        const coord = await kakaoGeocode(`${p.location} ${p.complex}`, KAKAO_API_KEY);
        if (coord) {
          finalLat = coord.lat;
          finalLng = coord.lng;
          source = 'kakao_geocode';
        }
      }

      // location만 시도
      if (!finalLat && p.location) {
        const coord = await kakaoGeocode(p.location, KAKAO_API_KEY);
        if (coord) {
          finalLat = coord.lat;
          finalLng = coord.lng;
          source = 'kakao_location';
        }
      }

      // complex만 키워드 검색
      if (!finalLat && p.complex) {
        const coord = await kakaoKeywordSearch(p.complex, KAKAO_API_KEY);
        if (coord) {
          finalLat = coord.lat;
          finalLng = coord.lng;
          source = 'kakao_keyword';
        }
      }
    }

    // 6. DISTRICT_COORDS fallback
    if (!finalLat || !finalLng) {
      const fallback = fallbackFromDistrict(fullText);
      if (fallback) {
        finalLat = fallback.lat;
        finalLng = fallback.lng;
        source = `district_fallback:${fallback.key}`;
        // 지역 태그 추가
        if (!addedTags.includes(fallback.key)) {
          addedTags.push(fallback.key);
        }
      }
    }

    // 7. tags merge 후 cards 업데이트
    const existingTags: string[] = Array.isArray(card.tags) ? card.tags : [];
    const mergedTags = [...new Set([...existingTags, ...addedTags])];

    const updatePayload: Record<string, any> = { tags: mergedTags };
    if (finalLat && finalLng) {
      updatePayload.lat = finalLat;
      updatePayload.lng = finalLng;
    }

    const { error: updateErr } = await supabase
      .from('cards')
      .update(updatePayload)
      .eq('id', card_id);

    if (updateErr) throw new Error(`카드 업데이트 실패: ${updateErr.message}`);

    // 8. 결과 반환
    return new Response(JSON.stringify({
      success: true,
      lat: finalLat,
      lng: finalLng,
      source,
      added_tags: addedTags,
      total_tags: mergedTags,
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error: any) {
    console.error('locate-card 에러:', error.message);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
