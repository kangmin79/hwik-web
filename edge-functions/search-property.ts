import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// ========== 1. Claude Haiku로 검색어 파싱 ==========
async function parseSearchQuery(query, anthropicKey) {
  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': anthropicKey,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: 'claude-3-5-haiku-20241022',
        max_tokens: 512,
        messages: [{
          role: 'user',
          content: `부동산 매물 검색어를 분석해서 JSON으로 반환해주세요.

■ 중요: 반드시 JSON만 반환하고, 다른 설명은 하지 마세요.

■ 분석할 항목:
1. semantic: 벡터 검색이 필요한 의미적 키워드
2. filters: SQL 필터로 정확히 처리할 조건들
3. features: 정확 매칭이 필요한 매물 특성 태그들

■ 가격 변환 (만원 단위): "3억"→30000, "3억5천"→35000, "1000만원"→1000
■ "3억 정도/쯤/근처" → min_price: 25000, max_price: 35000 (±15% 범위)
■ "5억~7억" → min_price: 50000, max_price: 70000
■ "3억 이하" → max_price: 30000 (min_price는 null)
■ "3억 이상" → min_price: 30000 (max_price는 null)

■ 월세 가격:
- "월세 50만원 이하" → trade_type: "월세", max_price: 50 (월세금 기준)
- "보증금 1억 월세 100" → trade_type: "월세", deposit: 10000, max_price: 100
- 일반 매매/전세는 기존대로 처리

■ 거래유형: "매매", "전세", "월세"
■ 매물유형: "apartment", "officetel", "room", "commercial", "office"

■ 거래상태 (trade_status):
- "계약가능/계약가능한/거래가능/활성/available" → "계약가능"
- "계약중/거래중/진행중" → "계약중"
- "완료/거래완료/계약완료" → "완료"
- 언급 없으면 null (전체)

■ 날짜 필터 (date_filter):
- "오늘/오늘 등록" → "today"
- "어제/어제 등록" → 1
- "이번주/이번 주/금주" → "week"
- "이번달/이번 달/이달" → "month"
- "최근 3일/3일 이내" → 3 (숫자)
- "최근 일주일" → 7
- "최근 한달" → 30
- 언급 없으면 null

■ 면적 필터:
- "20평대" → min_area: 20, max_area: 29
- "30평 이상" → min_area: 30
- "10~20평" → min_area: 10, max_area: 20
- 언급 없으면 null

■ 방 수 필터:
- "원룸/1룸/스튜디오" → rooms: 1, property_type도 "room"으로
- "투룸/2룸" → rooms: 2
- "쓰리룸/3룸/방3개" → rooms: 3
- 언급 없으면 null

■ 정렬 (sort):
- "최신순/최근/새로운" → "newest"
- "가격 낮은순/싼순/저렴한" → "price_asc"
- "가격 높은순/비싼" → "price_desc"
- "조회 많은/인기순/많이 본" → "views"
- 언급 없으면 null (유사도 기본)

■ features 태그: 애견가능, 풀옵션, 올수리, 루프탑, 테라스, 남향, 동향, 서향, 북향, 남동향, 남서향, 한강뷰, 시티뷰, 주차가능, 신축, 복층, 고층, 저층, 1층, 정원, 학군, 역세권, 즉시입주, 엘리베이터, 베란다확장
■ "강아지/반려동물/펫" → ["애견가능"]
■ "옥상" → ["루프탑"], "풀옵" → ["풀옵션"]
■ "바로 입주/즉시/빠른입주" → ["즉시입주"]
■ "학교/학군/학교근처/교육/학원가" → features에 ["학군"] 추가하고, semantic에도 "학군좋은" 포함
■ "역 근처/역세권/지하철" → ["역세권"]
■ "핫플/핫한/인기/뜨는" 같은 추상어는 무시하고 지역명만 location에 추출

■ location 추출 규칙:
- "성수동" → "성수", "합정동" → "합정", "잠실동" → "잠실" ("동" 제거)
- "강남역 근처" → "강남", "여의도역" → "여의도" ("역" 제거)
- "마포구" → "마포", "서초구" → "서초" ("구" 제거)
- 단, 동탄/구리/구로/동대문 등 지명 자체인 경우는 그대로 유지

■ nearby (근처 검색 - 역/학교/대학 등):
- "합정역 근처" → nearby: "합정역", nearby_type: "subway"
- "서울대 근처" → nearby: "서울대", nearby_type: "school"
- "강남역" → nearby: "강남역", nearby_type: "subway"
- "~~역", "~~역 근처/주변/앞" → subway
- "~~대/~~대학/~~학교/~~초등/~~중학/~~고등" → school
- 역이나 학교가 아니면 null
- nearby가 있으면 location도 같이 추출

{
  "semantic": "의미 검색 키워드 (없으면 null)",
  "filters": {
    "property_type": null,
    "trade_type": null,
    "min_price": null,
    "max_price": null,
    "location": null,
    "nearby": null,
    "nearby_type": null,
    "trade_status": null,
    "date_filter": null,
    "min_area": null,
    "max_area": null,
    "rooms": null,
    "sort": null
  },
  "features": null
}

검색어: ${query}`
        }]
      })
    });

    const data = await response.json();
    if (data.error) {
      console.error('Anthropic API 에러:', JSON.stringify(data.error));
      throw new Error('파싱 실패');
    }

    let jsonText = data.content[0].text || '';
    jsonText = jsonText.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
    const firstBrace = jsonText.indexOf('{');
    const lastBrace = jsonText.lastIndexOf('}');
    if (firstBrace !== -1 && lastBrace !== -1) jsonText = jsonText.slice(firstBrace, lastBrace + 1);

    return JSON.parse(jsonText);
  } catch (e) {
    // ★ 파싱 실패 시 폴백: 원본 쿼리를 semantic으로 사용
    console.warn('파싱 폴백:', e.message);
    return {
      semantic: query,
      filters: {},
      features: null
    };
  }
}

// ========== 2. OpenAI 임베딩 ==========
async function generateEmbedding(text, openaiKey) {
  try {
    const response = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${openaiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'text-embedding-3-small', input: text }),
    });
    const data = await response.json();
    return data.data?.[0]?.embedding || null;
  } catch (e) { return null; }
}

// ========== 3. 날짜 필터 → 날짜 계산 ==========
function getDateCutoff(dateFilter) {
  if (!dateFilter) return null;
  const now = new Date();

  if (dateFilter === 'today') {
    const cutoff = new Date(now);
    cutoff.setHours(0, 0, 0, 0);
    return cutoff.toISOString();
  } else if (dateFilter === 'week') {
    const cutoff = new Date(now);
    cutoff.setDate(cutoff.getDate() - 7);
    return cutoff.toISOString();
  } else if (dateFilter === 'month') {
    const cutoff = new Date(now);
    cutoff.setDate(cutoff.getDate() - 30);
    return cutoff.toISOString();
  } else if (typeof dateFilter === 'number' && dateFilter > 0) {
    const cutoff = new Date(now);
    cutoff.setDate(cutoff.getDate() - dateFilter);
    return cutoff.toISOString();
  }
  return null;
}

// ========== 4. 면적에서 숫자 추출 ==========
function extractAreaNumber(areaStr) {
  if (!areaStr) return null;
  const match = areaStr.match(/(\d+)/);
  return match ? parseInt(match[1]) : null;
}

// ========== 5. 정렬 함수 ==========
function sortResults(results, sortType) {
  if (!sortType) return results; // 기본: 유사도순 (DB에서 이미 정렬됨)

  const sorted = [...results];
  switch (sortType) {
    case 'newest':
      sorted.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
      break;
    case 'price_asc':
      sorted.sort((a, b) => (a.price_number || 999999999) - (b.price_number || 999999999));
      break;
    case 'price_desc':
      sorted.sort((a, b) => (b.price_number || 0) - (a.price_number || 0));
      break;
    case 'views':
      sorted.sort((a, b) => (b.view_count || 0) - (a.view_count || 0));
      break;
  }
  return sorted;
}

// ========== 6. 손님 카드 검색 (client 모드) ==========
async function searchClientCards(supabase, agentId, embedding, query, limit) {
  try {
    if (embedding) {
      const { data, error } = await supabase.rpc('search_client_cards', {
        p_agent_id: agentId,
        p_embedding: embedding,
        p_limit: limit
      });
      if (!error && data && data.length > 0) {
        return data.map(r => ({ ...r, _cat: 'client' }));
      }
    }

    const { data, error } = await supabase
      .from('cards_view')
      .select('id, property, created_at, agent_id, trade_status, search_text')
      .eq('agent_id', agentId)
      .eq('property->>type', '손님')
      .order('created_at', { ascending: false })
      .limit(limit * 2);

    if (error || !data) return [];

    const q = query.toLowerCase();
    const filtered = data.filter(r => {
      const st = (r.search_text || '').toLowerCase();
      const p = r.property || {};
      const combined = [st, p.location, p.price, p.area, ...(p.features || [])].filter(Boolean).join(' ').toLowerCase();
      return combined.includes(q) || q.split(' ').some(w => w.length > 1 && combined.includes(w));
    });

    return (filtered.length > 0 ? filtered : data.slice(0, limit)).map(r => ({ ...r, _cat: 'client' }));
  } catch (e) {
    console.error('손님 검색 오류:', e);
    return [];
  }
}

// ========== 메인 ==========
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY');
    const OPENAI_API_KEY = Deno.env.get('OPENAI_API_KEY');
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL');
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');

    if (!ANTHROPIC_API_KEY) throw new Error('서버 설정 오류');

    const { query, agent_id, limit = 10, search_mode = 'my' } = await req.json();
    if (!query) throw new Error('검색어가 필요합니다');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const startTime = Date.now();

    // ★ 손님 모드 — 별도 처리
    if (search_mode === 'client') {
      const embedding = OPENAI_API_KEY ? await generateEmbedding(query, OPENAI_API_KEY) : null;
      const results = await searchClientCards(supabase, agent_id, embedding, query, limit);
      console.log(`손님 검색: ${Date.now() - startTime}ms | ${results.length}건`);
      return new Response(JSON.stringify({
        success: true, query, results, count: results.length, search_mode
      }), { headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    }

    // ★ 기존 my / shared 모드
    const [parsed, earlyEmbedding] = await Promise.all([
      parseSearchQuery(query, ANTHROPIC_API_KEY),
      OPENAI_API_KEY ? generateEmbedding(query, OPENAI_API_KEY) : Promise.resolve(null)
    ]);

    console.log('PARSED:', JSON.stringify(parsed));
    console.log(`파싱+임베딩 동시: ${Date.now() - startTime}ms`);

    let embedding = earlyEmbedding;
    if (parsed.semantic && parsed.semantic !== query && OPENAI_API_KEY) {
      embedding = await generateEmbedding(parsed.semantic, OPENAI_API_KEY);
    }

    // ★ 날짜 필터 계산
    const dateCutoff = getDateCutoff(parsed.filters?.date_filter);

    // ★ 후처리 필터 개수에 따라 DB 요청량 동적 조절
    let postFilterCount = 0;
    if (parsed.filters?.trade_status) postFilterCount++;
    if (dateCutoff) postFilterCount++;
    if (parsed.filters?.min_area || parsed.filters?.max_area) postFilterCount++;
    if (parsed.filters?.rooms) postFilterCount++;
    if (parsed.filters?.location) postFilterCount++;
    if (parsed.features?.length) postFilterCount++;
    const multiplier = postFilterCount <= 1 ? 3 : postFilterCount <= 3 ? 5 : 10;

    const { data, error } = await supabase.rpc('search_cards_advanced', {
      p_agent_id: agent_id || '',
      p_search_text: null,
      p_embedding: embedding,
      p_property_type: parsed.filters?.property_type || null,
      p_trade_type: parsed.filters?.trade_type || null,
      p_min_price: parsed.filters?.min_price || null,
      p_max_price: parsed.filters?.max_price || null,
      p_days_ago: null,
      p_limit: limit * multiplier,
      p_search_mode: search_mode
    });

    if (error) {
      console.error('DB 검색 에러:', error.message);
      throw new Error('매물 검색에 실패했습니다');
    }

    let results = data || [];

    // ★ 거래상태 필터
    if (parsed.filters?.trade_status) {
      const ts = parsed.filters.trade_status;
      results = results.filter(r => {
        const cardStatus = r.trade_status || r.status || '계약가능';
        return cardStatus === ts;
      });
    }

    // ★ 날짜 필터
    if (dateCutoff) {
      results = results.filter(r => {
        return r.created_at && new Date(r.created_at) >= new Date(dateCutoff);
      });
    }

    // ★ 면적 필터
    if (parsed.filters?.min_area || parsed.filters?.max_area) {
      results = results.filter(r => {
        const area = extractAreaNumber(r.property?.area);
        if (!area) return false;
        if (parsed.filters.min_area && area < parsed.filters.min_area) return false;
        if (parsed.filters.max_area && area > parsed.filters.max_area) return false;
        return true;
      });
    }

    // ★ 방 수 필터
    if (parsed.filters?.rooms) {
      const targetRooms = String(parsed.filters.rooms);
      results = results.filter(r => {
        const room = r.property?.room || '';
        const searchText = r.search_text || '';
        return room.includes(targetRooms) || searchText.includes(targetRooms + '룸') || searchText.includes('방' + targetRooms);
      });
    }

    // 위치 필터
    if (parsed.filters?.location) {
      const loc = parsed.filters.location;
      const locFiltered = results.filter(r => {
        const st = r.search_text || '';
        const pLoc = r.property?.location || '';
        const pComplex = r.property?.complex || '';
        return st.includes(loc) || pLoc.includes(loc) || pComplex.includes(loc);
      });
      if (locFiltered.length > 0) results = locFiltered;
    }

    // ★ 근처 검색 (역/학교 좌표 기반 — facilities 테이블)
    if (parsed.filters?.nearby && parsed.filters?.nearby_type) {
      const nearbyName = parsed.filters.nearby;
      const nearbyType = parsed.filters.nearby_type;
      const RADIUS_KM = 1.5; // 반경 1.5km

      try {
        // facilities 테이블에서 해당 시설 좌표 찾기
        const { data: facilityData } = await supabase
          .from('facilities')
          .select('latitude, longitude, name')
          .eq('type', nearbyType)
          .ilike('name', `%${nearbyName.replace(/역$|대$|대학$|학교$/, '')}%`)
          .limit(3);

        if (facilityData && facilityData.length > 0) {
          const facility = facilityData[0];
          const fLat = facility.latitude;
          const fLng = facility.longitude;
          console.log(`근처 검색: ${facility.name} (${fLat}, ${fLng}) 반경 ${RADIUS_KM}km`);

          // 반경 내 매물 필터 (Haversine 근사)
          const nearbyFiltered = results.filter(r => {
            if (!r.lat || !r.lng) return false;
            const dLat = (r.lat - fLat) * Math.PI / 180;
            const dLng = (r.lng - fLng) * Math.PI / 180;
            const a = Math.sin(dLat/2)**2 + Math.cos(fLat*Math.PI/180) * Math.cos(r.lat*Math.PI/180) * Math.sin(dLng/2)**2;
            const dist = 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            return dist <= RADIUS_KM;
          });

          if (nearbyFiltered.length > 0) {
            results = nearbyFiltered;
            console.log(`근처 검색 결과: ${nearbyFiltered.length}건`);
          }
        }
      } catch(e) {
        console.warn('근처 검색 실패:', e);
      }
    }

    // features 필터
    if (parsed.features && parsed.features.length > 0) {
      const featFiltered = results.filter(r => {
        const st = r.search_text || '';
        const feats = (r.property?.features || []).join(' ');
        const all = (st + ' ' + feats).toLowerCase();
        return parsed.features.some(f => all.includes(f.toLowerCase()));
      });
      if (featFiltered.length > 0) results = featFiltered;
    }

    // ★ 정렬 적용 — 명시적 sort 없으면 필터 기반 자동 정렬
    let autoSort = parsed.filters?.sort || null;
    if (!autoSort) {
      if (parsed.filters?.date_filter) autoSort = 'newest';
      else if (parsed.filters?.min_price || parsed.filters?.max_price) autoSort = 'price_asc';
    }
    results = sortResults(results, autoSort);

    results = results.slice(0, limit);

    // ★ 적용된 필터 요약 (클라이언트 표시용)
    const appliedFilters = [];
    if (parsed.filters?.trade_type) appliedFilters.push(parsed.filters.trade_type);
    if (parsed.filters?.property_type) appliedFilters.push(parsed.filters.property_type);
    if (parsed.filters?.trade_status) appliedFilters.push(parsed.filters.trade_status);
    if (parsed.filters?.location) appliedFilters.push(parsed.filters.location);
    if (parsed.filters?.min_price || parsed.filters?.max_price) {
      const min = parsed.filters.min_price ? `${(parsed.filters.min_price/10000).toFixed(1)}억` : '';
      const max = parsed.filters.max_price ? `${(parsed.filters.max_price/10000).toFixed(1)}억` : '';
      if (min && max) appliedFilters.push(`${min}~${max}`);
      else if (max) appliedFilters.push(`${max} 이하`);
      else if (min) appliedFilters.push(`${min} 이상`);
    }
    if (parsed.filters?.date_filter) {
      const df = parsed.filters.date_filter;
      if (df === 'today') appliedFilters.push('오늘');
      else if (df === 'week') appliedFilters.push('이번 주');
      else if (df === 'month') appliedFilters.push('이번 달');
      else if (typeof df === 'number') appliedFilters.push(`최근 ${df}일`);
    }
    if (parsed.filters?.min_area || parsed.filters?.max_area) {
      const min = parsed.filters.min_area || '';
      const max = parsed.filters.max_area || '';
      if (min && max) appliedFilters.push(`${min}~${max}평`);
      else if (max) appliedFilters.push(`${max}평 이하`);
      else if (min) appliedFilters.push(`${min}평 이상`);
    }
    if (parsed.filters?.rooms) appliedFilters.push(`${parsed.filters.rooms}룸`);
    if (parsed.filters?.nearby) appliedFilters.push(`${parsed.filters.nearby} 근처`);
    if (parsed.features?.length) appliedFilters.push(...parsed.features);
    if (autoSort) {
      const sortLabels = { newest: '최신순', price_asc: '가격↓', price_desc: '가격↑', views: '인기순' };
      appliedFilters.push(sortLabels[parsed.filters.sort] || '');
    }

    console.log(`총 소요: ${Date.now() - startTime}ms | 결과: ${results.length}건 | mode: ${search_mode} | filters: ${appliedFilters.join(', ')}`);

    return new Response(JSON.stringify({
      success: true,
      query,
      parsed,
      results,
      count: results.length,
      search_mode,
      applied_filters: appliedFilters
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('search-property 에러:', error.message);
    return new Response(JSON.stringify({ error: '검색 중 오류가 발생했습니다' }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
