import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'
import { DISTRICT_COORDS } from '../_shared/geo.ts'
import { getAuthUserId } from '../_shared/auth.ts'

// LIKE 와일드카드 이스케이프
function escapeLike(s: string): string {
  return s.replace(/[%_\\]/g, '\\$&');
}

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

    const agent_id = await getAuthUserId(req);
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
          .ilike('name', `%${escapeLike(stationName)}%`)
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
            .ilike('name', `%${escapeLike(m[1])}%`)
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

    // 7. ★ 좌표 기반 단지 매칭 (주소 → 카카오 geocode → apartments.doro_lat/lon or jibun_lat/lon 반경 매칭)
    //    대원칙: 매칭 정확 못하면 kapt_code NULL (danji 연결 금지, False positive 방지)
    let kaptCode: string | null = null;
    let kaptName: string | null = null;
    const RADIUS_M = 50;  // 50m 반경 — 같은 주소 geocode는 거의 0m, 50m 여유
    const addrRoad = (p.address_road || '').trim();
    const addrJibun = (p.address_jibun || '').trim();
    // 하위 호환: 기존 property.address 필드 (도로명이었음)
    const addrLegacy = (p.address || '').trim();

    async function matchByAddress(addr: string, addrType: 'doro' | 'jibun'): Promise<{ code: string; name: string; lat: number; lng: number; sgg?: string; umd_nm?: string } | null> {
      if (!addr || !KAKAO_API_KEY) return null;
      const coord = await kakaoGeocode(addr, KAKAO_API_KEY);
      if (!coord) {
        console.log(`geocode 실패: "${addr}"`);
        return null;
      }
      const { data: matches } = await supabase.rpc('match_apartment_by_coord', {
        p_lat: coord.lat,
        p_lng: coord.lng,
        p_radius_m: RADIUS_M,
        p_addr_type: addrType,
      });
      if (!matches?.length) {
        console.log(`반경 ${RADIUS_M}m 내 단지 없음: "${addr}" (${addrType})`);
        return null;
      }
      // complex 이름 토큰 정규화
      const complexNorm = (p.complex || '').replace(/\s+/g, '').replace(/아파트|오피스텔/g, '');
      const nameContains = (dbName: string): boolean => {
        if (complexNorm.length < 2) return false;
        const n = (dbName || '').replace(/\s+/g, '');
        const token = complexNorm.slice(0, Math.min(3, complexNorm.length));
        return n.includes(token) || complexNorm.slice(0, 2).length >= 2 && n.includes(complexNorm.slice(0, 2));
      };

      // ★ 이름 토큰 일치하는 것만 후보 (False positive 방지)
      const validMatches = complexNorm.length >= 2
        ? matches.filter((m: any) => nameContains(m.kapt_name))
        : matches;  // complex 없으면 모든 반경 내 결과 허용 (중개사가 단지명 안 쓴 케이스)

      if (!validMatches.length) {
        console.log(`이름 불일치 거부: "${addr}" complex="${complexNorm}" 반경 내 ${matches.length}개 전부 이름 mismatch`);
        return null;
      }
      // ★ 공식 K-apt A코드 우선 (같은 단지가 공식 A + 비공식 apt-* 중복 등록된 경우 정답은 공식)
      const officialOnly = validMatches.filter((m: any) => /^A\d/i.test(m.kapt_code));
      const finalMatches = officialOnly.length > 0 ? officialOnly : validMatches;
      if (finalMatches.length > 1) {
        console.log(`다중 매칭 거부 (${finalMatches.length}개): "${addr}" → 모호`);
        return null;
      }
      const best = finalMatches[0];
      if (!/^(a\d|apt-|offi-)/i.test(best.kapt_code || '')) {
        console.log(`code 형식 불일치: ${best.kapt_code}`);
        return null;
      }
      return {
        code: best.kapt_code,
        name: best.kapt_name,
        lat: best.target_lat,
        lng: best.target_lon,
        sgg: best.sgg,
        umd_nm: best.umd_nm,
      };
    }

    // Step 3: 이름+지역 fallback (도로명/지번 매칭 실패 시)
    async function matchByNameRegion(): Promise<{ code: string; name: string; lat: number; lng: number; sgg?: string; umd_nm?: string } | null> {
      const complex = (p.complex || '').trim();
      const location = p.location || '';
      const pickSgg = (t: string): string | null => {
        if (!t) return null;
        const all = [...t.matchAll(/([가-힣]+(?:구|시|군))/g)].map(m => m[1]);
        return all.find(s => s.endsWith('구')) || all.find(s => s.endsWith('시')) || all[0] || null;
      };
      const sgg = pickSgg(location) || pickSgg(fullText);
      const umdMatch = location.match(/([가-힣]+(?:동|읍|면|리))\b/) || fullText.match(/([가-힣]+(?:동|읍|면|리))\b/);
      const umd = umdMatch ? umdMatch[1] : null;

      if (!complex || !sgg || !umd) {
        console.log(`Step3 조건 미충족: complex="${complex}" sgg="${sgg}" umd="${umd}"`);
        return null;
      }

      const { data: matches } = await supabase.rpc('match_apartment_by_name_region', {
        p_complex: complex.replace(/아파트|오피스텔/g, '').trim(),
        p_sgg: sgg,
        p_umd: umd,
        p_lat: finalLat,
        p_lng: finalLng,
      });
      if (!matches?.length) {
        console.log(`Step3 이름+지역 매칭 없음: complex="${complex}" ${sgg} ${umd}`);
        return null;
      }
      // 공식 A코드 우선
      const officialOnly = matches.filter((m: any) => /^A\d/i.test(m.kapt_code));
      const finalList = officialOnly.length > 0 ? officialOnly : matches;
      if (finalList.length > 1) {
        console.log(`Step3 다중 매칭 거부 (${finalList.length}개): "${complex}" in ${sgg} ${umd}`);
        return null;
      }
      const best = finalList[0];
      if (!/^(a\d|apt-|offi-)/i.test(best.kapt_code || '')) return null;
      // 좌표 힌트 있으면 반경 5km 이내 보조 검증
      if (finalLat && finalLng && best.distance_km != null && best.distance_km > 5) {
        console.log(`Step3 거리 보조검증 실패 (${best.distance_km.toFixed(2)}km): "${complex}"`);
        return null;
      }
      console.log(`Step3 이름+지역 매칭 성공: "${complex}" → ${best.kapt_name} (${best.sgg} ${best.umd_nm})`);
      return {
        code: best.kapt_code,
        name: best.kapt_name,
        lat: best.target_lat,
        lng: best.target_lon,
        sgg: best.sgg,
        umd_nm: best.umd_nm,
      };
    }

    try {
      // Waterfall: 도로명 → 지번 → legacy address → 이름+지역 fallback
      let result = null;
      if (addrRoad) result = await matchByAddress(addrRoad, 'doro');
      if (!result && addrJibun) result = await matchByAddress(addrJibun, 'jibun');
      if (!result && addrLegacy && !addrRoad && !addrJibun) result = await matchByAddress(addrLegacy, 'doro');
      // Step 3: 좌표 매칭 전부 실패 → 이름+지역 fallback
      if (!result) result = await matchByNameRegion();

      if (result) {
        kaptCode = result.code.toLowerCase();
        kaptName = result.name;
        if (!finalLat && !finalLng) {
          finalLat = result.lat;
          finalLng = result.lng;
          source = 'apartment_match';
        }
        if (result.sgg && !addedTags.includes(result.sgg)) addedTags.push(result.sgg);
        if (result.umd_nm && !addedTags.includes(result.umd_nm)) addedTags.push(result.umd_nm);
        console.log(`단지 매칭 확정: ${kaptName} (${result.sgg} ${result.umd_nm}) code=${kaptCode}`);
      } else {
        console.log(`단지 매칭 실패 — kapt_code NULL 유지 (addr_road="${addrRoad}" addr_jibun="${addrJibun}" complex="${p.complex}")`);
      }
    } catch (e) {
      console.warn('단지 매칭 에러 (무시):', (e as Error).message);
    }

    // 8. ★ 좌표 기반 근처 역/학교 자동 탐지 (반경 500m 역, 1km 학교)
    if (finalLat && finalLng) {
      try {
        // 근처 역 조회 (하버사인 근사: 위도 1도≈111km, 경도 1도≈88km@37°N)
        const latRange500m = 0.0045; // ~500m
        const lngRange500m = 0.0057;
        const { data: nearbyStations } = await supabase
          .from('stations')
          .select('name, lat, lon')
          .gte('lat', finalLat - latRange500m)
          .lte('lat', finalLat + latRange500m)
          .gte('lon', finalLng - lngRange500m)
          .lte('lon', finalLng + lngRange500m)
          .limit(5);

        if (nearbyStations?.length) {
          for (const st of nearbyStations) {
            // 정밀 거리 계산
            const dLat = (st.lat - finalLat) * 111000;
            const dLng = (st.lon - finalLng) * 88000;
            const dist = Math.sqrt(dLat * dLat + dLng * dLng);
            if (dist <= 500) {
              const tag = `${st.name}역`;
              if (!addedTags.includes(tag)) addedTags.push(tag);
            }
          }
          console.log(`근처 역: ${nearbyStations.map(s => s.name).join(', ')}`);
        }

        // 근처 학교 조회 (반경 1km)
        const latRange1km = 0.009;
        const lngRange1km = 0.0114;
        const { data: nearbySchools } = await supabase
          .from('schools')
          .select('name, lat, lon')
          .gte('lat', finalLat - latRange1km)
          .lte('lat', finalLat + latRange1km)
          .gte('lon', finalLng - lngRange1km)
          .lte('lon', finalLng + lngRange1km)
          .limit(10);

        if (nearbySchools?.length) {
          for (const sc of nearbySchools) {
            const dLat = (sc.lat - finalLat) * 111000;
            const dLng = (sc.lon - finalLng) * 88000;
            const dist = Math.sqrt(dLat * dLat + dLng * dLng);
            if (dist <= 1000) {
              const tag = sc.name;
              if (!addedTags.includes(tag)) addedTags.push(tag);
            }
          }
          console.log(`근처 학교: ${nearbySchools.map(s => s.name).join(', ')}`);
        }
      } catch (e) {
        console.warn('근처 역/학교 탐지 실패 (무시):', (e as Error).message);
      }
    }

    // 9. tags merge 후 cards 업데이트
    const existingTags: string[] = Array.isArray(card.tags) ? card.tags : [];
    const mergedTags = [...new Set([...existingTags, ...addedTags])];

    const updatePayload: Record<string, any> = { tags: mergedTags };
    if (finalLat && finalLng) {
      updatePayload.lat = finalLat;
      updatePayload.lng = finalLng;
    }
    if (kaptCode) {
      updatePayload.kapt_code = kaptCode;
    }

    const { error: updateErr } = await supabase
      .from('cards')
      .update(updatePayload)
      .eq('id', card_id);

    if (updateErr) throw new Error(`카드 업데이트 실패: ${updateErr.message}`);

    // 10. 결과 반환
    return new Response(JSON.stringify({
      success: true,
      lat: finalLat,
      lng: finalLng,
      source,
      kapt_code: kaptCode,
      kapt_name: kaptName,
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
