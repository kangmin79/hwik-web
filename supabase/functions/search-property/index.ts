import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'
import { DISTRICT_COORDS, haversineDistance } from '../_shared/geo.ts'
import { TYPO_MAP, fixTypos } from '../_shared/typo.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',  // TODO: 프로덕션에서 'https://hwik.kr'로 제한
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// ========== 0. 로컬 빠른 파서 (Claude 없이 즉시 처리) ==========
function localParseQuery(query: string) {
  // ★ 오타/한글숫자 교정
  let q = fixTypos(query.trim());
  const filters: Record<string, any> = {};
  let semantic: string | null = null;
  let features: string[] | null = null;
  let remaining = q;

  // 거래유형
  const tradeTypes: Record<string, string> = { '매매': '매매', '전세': '전세', '월세': '월세' };
  for (const [keyword, value] of Object.entries(tradeTypes)) {
    if (q.includes(keyword)) { filters.trade_type = value; remaining = remaining.replace(keyword, ''); break; }
  }

  // 매물 카테고리
  const categoryMap: Record<string, string> = {
    '아파트': 'apartment', 'apt': 'apartment',
    '오피스텔': 'officetel',
    '원룸': 'room', '투룸': 'room', '쓰리룸': 'room', '빌라': 'room', '주택': 'room',
    '상가': 'commercial', '점포': 'commercial', '매장': 'commercial',
    '사무실': 'office', '오피스': 'office',
  };
  for (const [keyword, value] of Object.entries(categoryMap)) {
    if (q.includes(keyword)) { filters.property_type = value; remaining = remaining.replace(keyword, ''); break; }
  }

  // 방 수
  const roomMatch = q.match(/(원룸|1룸|스튜디오|투룸|2룸|쓰리룸|3룸|방\s*(\d))/);
  if (roomMatch) {
    if (roomMatch[0].includes('원') || roomMatch[0].includes('1') || roomMatch[0].includes('스튜')) filters.rooms = 1;
    else if (roomMatch[0].includes('투') || roomMatch[0].includes('2')) filters.rooms = 2;
    else if (roomMatch[0].includes('쓰리') || roomMatch[0].includes('3')) filters.rooms = 3;
    else if (roomMatch[2]) filters.rooms = parseInt(roomMatch[2]);
  }

  // 지역 (구/동/역/유명지역)
  const guList = [
    '강남','서초','마포','용산','성동','송파','영등포','강서','노원','관악',
    '동작','광진','종로','중구','강동','강북','구로','금천','도봉','동대문',
    '서대문','성북','양천','은평','중랑'
  ];
  // 유명 지역명 (동이 안 붙는 이름들)
  const knownPlaces: Record<string, string> = {
    '잠실': '잠실', '여의도': '여의도', '성수': '성수', '합정': '합정', '망원': '망원',
    '연남': '연남', '이태원': '이태원', '한남': '한남', '청담': '청담', '압구정': '압구정',
    '삼성': '삼성', '대치': '대치', '역삼': '역삼', '논현': '논현', '신사': '신사',
    '반포': '반포', '방배': '방배', '양재': '양재', '잠원': '잠원',
    '서교': '서교', '상수': '상수', '공덕': '공덕', '옥수': '옥수', '왕십리': '왕십리',
    '가락': '가락', '문정': '문정', '석촌': '석촌', '당산': '당산',
    '화곡': '화곡', '마곡': '마곡', '발산': '발산', '등촌': '등촌',
    '상계': '상계', '중계': '중계', '신림': '신림', '봉천': '봉천',
    '노량진': '노량진', '상도': '상도', '흑석': '흑석', '사당': '사당',
    '구의': '구의', '자양': '자양', '천호': '천호', '길동': '길동', '둔촌': '둔촌', '고덕': '고덕',
    '혜화': '혜화', '평창': '평창', '명동': '명동', '신당': '신당',
    '개포': '개포', '도곡': '도곡', '목동': '목동',
  };
  // 동 단위 (XX동) — 구 이름(성동, 강동 등)은 제외
  const dongMatch = q.match(/([\uAC00-\uD7A3]{1,4})동(?:\s|$)/);
  if (dongMatch) {
    const dongBase = dongMatch[1]; // "성" from "성동", "역삼" from "역삼동"
    const fullText = dongBase + '동'; // "성동", "역삼동"
    // Skip if this is a 구 name (성동구, 강동구 etc.)
    if (!guList.includes(fullText)) {
      filters.location = dongBase;
      remaining = remaining.replace(dongMatch[0], '');
    }
  }
  // 유명 지역명
  if (!filters.location) {
    for (const [place, locName] of Object.entries(knownPlaces)) {
      if (q.includes(place)) {
        filters.location = locName;
        remaining = remaining.replace(place, '');
        break;
      }
    }
  }
  // 구 단위
  if (!filters.location) {
    for (const gu of guList) {
      const guRegex = new RegExp(gu + '(?:구)?(?:\\s|$)');
      if (guRegex.test(q) || q.includes(gu)) {
        filters.location = gu;
        remaining = remaining.replace(new RegExp(gu + '구?'), '');
        break;
      }
    }
  }

  // 역/학교 근처
  const nearbyMatch = q.match(/([\uAC00-\uD7A3]+)(역|대학교|대학|학교|초등|중학|고등)\s*(근처|주변|앞)?/);
  if (nearbyMatch) {
    filters.nearby = nearbyMatch[1] + nearbyMatch[2];
    filters.nearby_type = nearbyMatch[2] === '역' ? 'subway' : 'school';
    if (!filters.location) filters.location = nearbyMatch[1];
  }

  // 가격 파싱
  const isWolse = filters.trade_type === '월세';
  const pricePatterns = [
    // "3억5천" / "3억" / "5천" / "1000" / "2000만원"
    { regex: /(\d+)\s*억\s*(\d+)?\s*천?/, parse: (m: RegExpMatchArray) => (parseInt(m[1]) * 10000) + (m[2] ? parseInt(m[2]) * 1000 : 0) },
    { regex: /(\d+)\s*천\s*만?\s*원?/, parse: (m: RegExpMatchArray) => parseInt(m[1]) * 1000 },
    { regex: /(\d{3,})(?:\s*만?\s*원?)?/, parse: (m: RegExpMatchArray) => parseInt(m[1]) },
    // 소액 (월세금): "80", "50", "100" (만원 단위, 1~999)
    { regex: /(\d{1,3})(?:\s*만?\s*원?)?\s*(?:이하|이상|미만|초과)/, parse: (m: RegExpMatchArray) => parseInt(m[1]) },
  ];

  let priceValue: number | null = null;
  for (const pp of pricePatterns) {
    const pm = q.match(pp.regex);
    if (pm) { priceValue = pp.parse(pm); break; }
  }

  if (priceValue !== null) {
    if (/이하|미만|아래|까지|밑으로|내로|안넘는|못넘는/.test(q)) {
      filters.max_price = priceValue;
    } else if (/이상|초과|넘는|부터|위로|넘게/.test(q)) {
      filters.min_price = priceValue;
    } else if (/정도|쯤|선|대|내외|안팎|전후|언저리/.test(q) && !/역|학교|대학|동$/.test(q)) {
      filters.min_price = Math.round(priceValue * 0.85);
      filters.max_price = Math.round(priceValue * 1.15);
    } else {
      // 가격만 단독이면 "정도"로 처리 (±15% 범위)
      // "4억" = 3.4~4.6억, "전세 3억" = 2.55~3.45억
      filters.min_price = Math.round(priceValue * 0.85);
      filters.max_price = Math.round(priceValue * 1.15);
    }
  }

  // 범위 가격: "1억 이상 3억 이하" / "5억~7억"
  const rangeMatch = q.match(/(\d+)\s*억?\s*~\s*(\d+)\s*억/);
  if (rangeMatch) {
    filters.min_price = parseInt(rangeMatch[1]) * 10000;
    filters.max_price = parseInt(rangeMatch[2]) * 10000;
  }
  const rangeMatch2 = q.match(/(\d+)\s*억.*이상.*(\d+)\s*억.*이하/);
  if (rangeMatch2) {
    filters.min_price = parseInt(rangeMatch2[1]) * 10000;
    filters.max_price = parseInt(rangeMatch2[2]) * 10000;
  }

  // 면적 - only apply 이하/이상 to area if there's no price keyword nearby
  const areaMatch = q.match(/(\d+)\s*평/);
  if (areaMatch) {
    const pyeong = parseInt(areaMatch[1]);
    const afterArea = q.slice(q.indexOf(areaMatch[0]) + areaMatch[0].length);
    const hasPrice = /\d+\s*억|천|만원|\d{3,}/.test(q.replace(areaMatch[0], ''));
    if (/대/.test(afterArea.slice(0, 3))) {
      filters.min_area = pyeong;
      filters.max_area = pyeong + 9;
    } else if (/이상/.test(afterArea.slice(0, 5)) && !hasPrice) {
      filters.min_area = pyeong;
    } else if (/이하/.test(afterArea.slice(0, 5)) && !hasPrice) {
      filters.max_area = pyeong;
    } else {
      // Default: ±3평 range
      filters.min_area = pyeong - 3;
      filters.max_area = pyeong + 3;
    }
  }

  // 특징 (features)
  const featureKeywords: Record<string, string> = {
    '올수리': '올수리', '풀옵션': '풀옵션', '풀옵': '풀옵션',
    '남향': '남향', '동향': '동향', '서향': '서향', '북향': '북향', '남동향': '남동향', '남서향': '남서향',
    '역세권': '역세권', '주차': '주차가능', '주차가능': '주차가능',
    '한강뷰': '한강뷰', '시티뷰': '시티뷰', '공원뷰': '공원뷰',
    '신축': '신축', '복층': '복층', '루프탑': '루프탑', '옥상': '루프탑',
    '테라스': '테라스', '베란다확장': '베란다확장',
    '애견가능': '애견가능', '반려동물': '애견가능', '강아지': '애견가능', '펫': '애견가능',
    '즉시입주': '즉시입주', '바로입주': '즉시입주', '빠른입주': '즉시입주',
    '학군': '학군', '학교': '학군', '교육': '학군',
    '엘리베이터': '엘리베이터', '고층': '고층', '저층': '저층',
  };
  const foundFeatures: string[] = [];
  for (const [keyword, tag] of Object.entries(featureKeywords)) {
    if (q.includes(keyword) && !foundFeatures.includes(tag)) {
      foundFeatures.push(tag);
      remaining = remaining.replace(keyword, '');
    }
  }
  if (foundFeatures.length > 0) features = foundFeatures;

  // 단지명 (아파트 브랜드)
  const aptBrands = ['래미안','자이','힐스테이트','푸르지오','더샵','아이파크','롯데캐슬',
    'e편한세상','SK뷰','엘크루','포레나','트리지움','리센츠','헬리오시티','파크리오',
    '센트레빌','두산위브','한화포레나','금호어울림'];
  for (const brand of aptBrands) {
    if (q.includes(brand)) {
      if (!filters.property_type) filters.property_type = 'apartment';
      semantic = brand;
      break;
    }
  }

  // 거래상태
  if (/계약가능|거래가능/.test(q)) filters.trade_status = '계약가능';
  else if (/계약중|거래중|진행중/.test(q)) filters.trade_status = '계약중';
  else if (/완료|거래완료|계약완료/.test(q)) filters.trade_status = '완료';

  // 정렬
  if (/최신|최근|새로운/.test(q)) filters.sort = 'newest';
  else if (/싼|저렴|낮은/.test(q)) filters.sort = 'price_asc';
  else if (/비싼|높은/.test(q)) filters.sort = 'price_desc';

  // 날짜
  if (/오늘/.test(q)) filters.date_filter = 'today';
  else if (/어제/.test(q)) filters.date_filter = 1;
  else if (/이번\s?주|금주/.test(q)) filters.date_filter = 'week';
  else if (/이번\s?달|이달/.test(q)) filters.date_filter = 'month';
  else { const dayMatch = q.match(/최근\s*(\d+)\s*일/); if (dayMatch) filters.date_filter = parseInt(dayMatch[1]); }

  // semantic 텍스트 (남은 의미 키워드를 벡터 검색에 사용)
  remaining = remaining.replace(/[이하이상미만초과근처주변앞까지부터정도쯤내외]/g, '').replace(/\d+억?\s*천?\s*만?\s*원?/g, '').trim();
  if (!semantic && remaining.length >= 2) semantic = remaining;

  // 필터가 하나라도 있으면 로컬 파싱 성공
  const hasFilters = Object.keys(filters).length > 0 || features !== null;

  return hasFilters ? { semantic, filters, features, _local: true } : null;
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
        model: 'claude-haiku-4-5-20251001',
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
■ "3억 이하/미만/아래/까지" → max_price: 30000 (min_price는 null)
■ "3억 이상/초과/넘는/부터" → min_price: 30000 (max_price는 null)

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

function extractAreaNumbers(areaStr: string): { pyeong: number | null; sqm: number | null } {
  if (!areaStr) return { pyeong: null, sqm: null };
  const sqmMatch = areaStr.match(/(\d+)㎡/);
  const pyeongMatch = areaStr.match(/(\d+)평/);
  return {
    sqm: sqmMatch ? parseInt(sqmMatch[1]) : null,
    pyeong: pyeongMatch ? parseInt(pyeongMatch[1]) : null
  };
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

    const { query, agent_id, limit = 10, search_mode = 'my', trade_type = null, property_type = null, min_price = null, max_price = null } = await req.json();
    if (!query) throw new Error('검색어가 필요합니다');
    if (query.length < 2) throw new Error('검색어는 2글자 이상 입력하세요');

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // ★ 인증 확인 (선택적 — 공유매물 검색은 비인증 허용)
    const authHeader = req.headers.get('Authorization');
    let authUser: string | null = null;
    if (authHeader && authHeader !== `Bearer ${Deno.env.get('SUPABASE_ANON_KEY')}`) {
      try {
        const token = authHeader.replace('Bearer ', '');
        const { data: { user } } = await supabase.auth.getUser(token);
        if (user) authUser = user.id;
      } catch(e) { /* anon access allowed */ }
    }

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

    // ★ 1단계: 로컬 빠른 파서 시도 (0ms)
    const clientParsedPrice = min_price !== null || max_price !== null;
    let parsed: any = { semantic: null, filters: {}, features: null };
    let embedding = null;

    const localResult = localParseQuery(query);

    if (localResult) {
      // 로컬 파서 성공 → Claude 불필요 (빠름!)
      parsed = localResult;
      // 클라이언트가 보낸 가격이 있으면 덮어쓰기
      if (clientParsedPrice) {
        if (min_price !== null) parsed.filters.min_price = min_price;
        if (max_price !== null) parsed.filters.max_price = max_price;
      }
      // ★ 구조화된 필터가 2개 이상이면 임베딩 생략 (SQL만으로 충분)
      // 클라이언트가 보낸 필터도 포함 (my_cards.html에서 미리 파싱해서 보냄)
      const structuredFilterCount = [
        trade_type || parsed.filters.trade_type,
        property_type || parsed.filters.property_type,
        min_price || max_price || parsed.filters.min_price || parsed.filters.max_price,
        parsed.filters.location
      ].filter(Boolean).length;
      if (structuredFilterCount >= 2) {
        embedding = null; // SQL 직접 검색 모드
        console.log(`SQL 직접 검색: ${Date.now() - startTime}ms | filters: ${JSON.stringify(parsed.filters)} (임베딩 생략)`);
      } else {
        embedding = OPENAI_API_KEY ? await generateEmbedding(parsed.semantic || query, OPENAI_API_KEY) : null;
        console.log(`로컬 파싱 + 벡터: ${Date.now() - startTime}ms | filters: ${JSON.stringify(parsed.filters)}`);
      }
    } else if (!clientParsedPrice && query.length >= 6) {
      // 로컬 파서 실패 + 긴 쿼리 → Claude에게 맡기기
      const [parsedResult, earlyEmbedding] = await Promise.all([
        parseSearchQuery(query, ANTHROPIC_API_KEY),
        OPENAI_API_KEY ? generateEmbedding(query, OPENAI_API_KEY) : Promise.resolve(null)
      ]);
      parsed = parsedResult;
      embedding = earlyEmbedding;
      if (parsed.semantic && parsed.semantic !== query && OPENAI_API_KEY) {
        embedding = await generateEmbedding(parsed.semantic, OPENAI_API_KEY);
      }
      console.log(`Claude 파싱: ${Date.now() - startTime}ms | filters: ${JSON.stringify(parsed.filters)}`);
    } else {
      // 짧은 미인식 쿼리 → 임베딩만 (벡터 검색)
      if (clientParsedPrice) {
        parsed.filters.min_price = min_price;
        parsed.filters.max_price = max_price;
      }
      embedding = OPENAI_API_KEY ? await generateEmbedding(query, OPENAI_API_KEY) : null;
      console.log(`벡터 검색만: ${Date.now() - startTime}ms`);
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

    // ★ 클라이언트가 직접 보낸 필터가 있으면 우선 사용
    const finalTradeType = trade_type || parsed.filters?.trade_type || null;
    const finalPropertyType = property_type || parsed.filters?.property_type || null;

    // ★ 위치 없으면 중개사 사무실 주소에서 구 자동 추출
    if (!parsed.filters?.location && agent_id) {
      try {
        const { data: profile } = await supabase
          .from('profiles')
          .select('address')
          .eq('id', agent_id)
          .single();
        if (profile?.address) {
          const guList = ['강남','서초','송파','마포','용산','성동','광진','영등포','강동','동작','관악','종로','중구','강서','양천','구로','노원','서대문','은평','중랑','도봉','동대문','성북','금천','강북'];
          for (const gu of guList) {
            if (profile.address.includes(gu)) {
              parsed.filters.location = gu;
              console.log(`위치 없음 → 사무실 주소에서 '${gu}' 자동 적용`);
              break;
            }
          }
        }
      } catch(e) { /* 프로필 조회 실패 무시 */ }
    }

    let results: any[] = [];
    let searchMethod = 'rpc';

    // ★ 구조화된 필터가 충분하면 SQL 직접 검색 (빠르고 정확)
    if (!embedding && (finalTradeType || finalPropertyType || parsed.filters?.min_price || parsed.filters?.max_price)) {
      // ★ shared 모드면 SQL 직접 검색 건너뛰기 (RPC가 share_rooms 처리)
      if (search_mode === 'shared') {
        searchMethod = 'rpc_shared';
        console.log('공유 매물 → RPC 경로로 전환');
      } else {
        searchMethod = 'sql';
      }
    }

    if (searchMethod === 'sql') {
      // ★ 검색어 단어별 AND 매칭 (구/동/단지명 전부 커버)
      // "역삼 래미안 전세" → search_text에 "역삼" AND "래미안" AND "전세" 포함
      const searchWords = query.split(/\s+/).filter(w => w.length >= 1);

      let sqlQuery = supabase
        .from('cards')
        .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number, agent_comment')
        .eq('agent_id', agent_id)
        .neq('property->>type', '손님');

      // 구조화 필터 (파서가 추출한 것)
      if (finalTradeType) sqlQuery = sqlQuery.eq('property->>type', finalTradeType);
      if (finalPropertyType) sqlQuery = sqlQuery.eq('property->>category', finalPropertyType);
      if (parsed.filters?.min_price) sqlQuery = sqlQuery.gte('price_number', parsed.filters.min_price);
      if (parsed.filters?.max_price) sqlQuery = sqlQuery.lte('price_number', Math.round(parsed.filters.max_price * 1.1));

      // ★ 검색어 단어별 텍스트 매칭 (AND)
      for (const word of searchWords) {
        // 거래유형/카테고리/가격 키워드는 이미 구조화 필터로 처리됨 → 스킵
        if (['매매','전세','월세','아파트','오피스텔','원룸','투룸','빌라','상가','사무실','원투룸'].includes(word)) continue;
        if (/^\d+억|^\d+천|^\d+이하|^\d+이상/.test(word)) continue;
        if (word.length < 2) continue;
        // 나머지 단어 = 지역명/단지명/특징 → search_text에서 매칭
        sqlQuery = sqlQuery.ilike('search_text', `%${word}%`);
      }

      sqlQuery = sqlQuery.order('created_at', { ascending: false }).limit(limit * multiplier);
      const { data: sqlData, error: sqlError } = await sqlQuery;

      if (sqlError) {
        console.error('SQL 검색 에러:', sqlError.message);
      } else {
        results = (sqlData || []).map(r => ({ ...r, similarity: 0 }));
      }

      // ★ AND로 0건이면 OR로 재시도 ("강남 서초" → 강남 OR 서초)
      if (results.length === 0 && searchWords.filter(w => w.length >= 2 && !['매매','전세','월세','아파트','오피스텔','원룸','투룸','빌라','상가','사무실','원투룸'].includes(w) && !/^\d/.test(w)).length >= 2) {
        const locWords = searchWords.filter(w => w.length >= 2 && !['매매','전세','월세','아파트','오피스텔','원룸','투룸','빌라','상가','사무실','원투룸'].includes(w) && !/^\d/.test(w));
        const orCondition = locWords.map(w => `search_text.ilike.%${w}%`).join(',');
        console.log(`AND 0건 → OR 재시도: ${orCondition}`);
        let orQuery = supabase
          .from('cards')
          .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number, agent_comment')
          .eq('agent_id', agent_id)
          .neq('property->>type', '손님');
        if (finalTradeType) orQuery = orQuery.eq('property->>type', finalTradeType);
        if (finalPropertyType) orQuery = orQuery.eq('property->>category', finalPropertyType);
        if (parsed.filters?.min_price) orQuery = orQuery.gte('price_number', parsed.filters.min_price);
        if (parsed.filters?.max_price) orQuery = orQuery.lte('price_number', Math.round(parsed.filters.max_price * 1.1));
        orQuery = orQuery.or(orCondition);
        orQuery = orQuery.order('created_at', { ascending: false }).limit(limit * multiplier);
        const { data: orData } = await orQuery;
        if (orData && orData.length > 0) {
          results = orData.map(r => ({ ...r, similarity: 0 }));
          console.log(`OR 재시도: ${results.length}건`);
        }
      }

      console.log(`SQL 검색: ${results.length}건 | ${Date.now() - startTime}ms`);
    }

    // ★ SQL 결과 없거나 벡터/공유 검색 모드면 RPC 사용
    if (results.length === 0 || searchMethod === 'rpc_shared') {
      searchMethod = embedding ? 'vector' : 'rpc';
      const { data, error } = await supabase.rpc('search_cards_advanced', {
        p_agent_id: agent_id || '',
        p_search_text: null,
        p_embedding: embedding,
        p_property_type: finalPropertyType,
        p_trade_type: finalTradeType,
        p_min_price: min_price || parsed.filters?.min_price || null,
        p_max_price: max_price || parsed.filters?.max_price || null,
        p_days_ago: null,
        p_limit: limit * multiplier,
        p_search_mode: search_mode
      });

      if (error) {
        console.error('DB 검색 에러:', error.message);
        throw new Error('매물 검색에 실패했습니다');
      }
      results = data || [];
      console.log(`RPC 검색: ${results.length}건 | ${Date.now() - startTime}ms`);
    }

    // ★ RPC 결과 0건이면 property_type 완화 후 재시도
    if (results.length === 0 && finalPropertyType) {
      console.log(`RPC 0건 → property_type '${finalPropertyType}' 제거 후 재검색`);
      const { data: retryData } = await supabase.rpc('search_cards_advanced', {
        p_agent_id: agent_id || '',
        p_search_text: null,
        p_embedding: embedding,
        p_property_type: null,  // 카테고리 필터 제거
        p_trade_type: finalTradeType,
        p_min_price: min_price || parsed.filters?.min_price || null,
        p_max_price: max_price || parsed.filters?.max_price || null,
        p_days_ago: null,
        p_limit: limit * multiplier,
        p_search_mode: search_mode
      });
      if (retryData && retryData.length > 0) {
        results = retryData;
        console.log(`재시도 결과: ${results.length}건 (카테고리 필터 제거)`);
      }
    }

    // ★ 하이브리드: 벡터 결과가 limit 미만이면 키워드 폴백으로 항상 보충 (브랜드명 등)
    if (results.length < limit && query.length >= 2) {
      console.log(`벡터 결과 ${results.length}건 < limit(${limit}) → 키워드 폴백 실행`);
      // 검색어 확장: 단지명, 카테고리 한글명 등
      const kwSearchTerms: string[] = [query];
      if (parsed.semantic && parsed.semantic !== query) kwSearchTerms.unshift(parsed.semantic);
      // 카테고리 한글명으로도 폴백 ("원룸" → "원투룸"도 검색)
      const catKoMap: Record<string, string[]> = {
        'room': ['원룸', '투룸', '원투룸', '빌라'],
        'apartment': ['아파트'],
        'officetel': ['오피스텔'],
        'commercial': ['상가'],
        'office': ['사무실'],
      };
      if (finalPropertyType && catKoMap[finalPropertyType]) {
        for (const catKw of catKoMap[finalPropertyType]) {
          if (!kwSearchTerms.includes(catKw)) kwSearchTerms.push(catKw);
        }
      }

      for (const kwTerm of kwSearchTerms) {
        if (results.length >= limit) break;
        let kwQuery = supabase
          .from('cards')
          .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number')
          .eq('agent_id', agent_id)
          .neq('property->>type', '손님')
          .ilike('search_text', `%${kwTerm}%`)
          .order('created_at', { ascending: false })
          .limit(limit * 3);
        if (finalTradeType) kwQuery = kwQuery.eq('property->>type', finalTradeType);
        if (finalPropertyType) kwQuery = kwQuery.eq('property->>category', finalPropertyType);
        const { data: kwData } = await kwQuery;

        if (kwData && kwData.length > 0) {
          const existingIds = new Set(results.map(r => r.id));
          const newResults = kwData.filter(r => !existingIds.has(r.id)).map(r => ({ ...r, similarity: 0 }));
          results = [...results, ...newResults];
          console.log(`키워드 폴백 '${kwTerm}': +${newResults.length}건 추가 (총 ${results.length}건)`);
        }
      }
    }

    // ★ 단지명 텍스트 매칭 (항상 키워드 검색 수행 → 벡터보다 정확)
    if (parsed.semantic && parsed._local) {
      const brandName = parsed.semantic;
      // 항상 키워드로 단지명 검색
      console.log(`단지명 '${brandName}' 키워드 검색`);
      let brandQuery = supabase
        .from('cards')
        .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number')
        .eq('agent_id', agent_id)
        .neq('property->>type', '손님')
        .ilike('search_text', `%${brandName}%`)
        .order('created_at', { ascending: false })
        .limit(limit * 5);
      if (finalTradeType) brandQuery = brandQuery.eq('property->>type', finalTradeType);
      const { data: brandData } = await brandQuery;

      if (brandData && brandData.length > 0) {
        // 단지명 매칭 결과를 최상위로, 기존 벡터 결과는 아래로
        const brandIds = new Set(brandData.map(r => r.id));
        const brandResults = brandData.map(r => ({ ...r, similarity: 1 })); // 높은 유사도 부여
        const existingNotBrand = results.filter(r => !brandIds.has(r.id));
        results = [...brandResults, ...existingNotBrand];
        console.log(`단지명 매칭: ${brandData.length}건 최상위 배치`);
      } else {
        // 키워드 결과도 없으면 기존 벡터 결과에서 필터
        const brandMatched = results.filter(r => {
          const st = r.search_text || '';
          const complex = r.property?.complex || '';
          return st.includes(brandName) || complex.includes(brandName);
        });
        if (brandMatched.length > 0) {
          const notMatched = results.filter(r => !brandMatched.some(b => b.id === r.id));
          results = [...brandMatched, ...notMatched];
        }
      }
    }

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

    // ★ 면적 필터 (평수↔㎡ 양방향 매칭)
    if (parsed.filters?.min_area || parsed.filters?.max_area) {
      // Convert search pyeong to sqm range too
      const searchMinPyeong = parsed.filters.min_area || null;
      const searchMaxPyeong = parsed.filters.max_area || null;
      const searchMinSqm = searchMinPyeong ? Math.round(searchMinPyeong * 3.305785 * 0.8) : null;
      const searchMaxSqm = searchMaxPyeong ? Math.round(searchMaxPyeong * 3.305785 * 1.2) : null;

      results = results.filter(r => {
        const { pyeong, sqm } = extractAreaNumbers(r.property?.area);
        // Check pyeong match
        if (pyeong) {
          if (searchMinPyeong && pyeong < searchMinPyeong) return false;
          if (searchMaxPyeong && pyeong > searchMaxPyeong) return false;
          return true;
        }
        // Check sqm match
        if (sqm) {
          if (searchMinSqm && sqm < searchMinSqm) return false;
          if (searchMaxSqm && sqm > searchMaxSqm) return false;
          return true;
        }
        // ★ Fix 1: 면적 정보 없는 매물은 통과 (조용히 제외하지 않음)
        return true;
      });
    }

    // ★ 방 수 필터
    if (parsed.filters?.rooms) {
      const targetRooms = String(parsed.filters.rooms);
      results = results.filter(r => {
        const room = r.property?.room || '';
        const searchText = r.search_text || '';
        // ★ Fix 2: 방 정보 없으면 통과 (제외하지 않음)
        if (!room && !searchText.match(/\d룸|방\d/)) return true;
        return room.includes(targetRooms) || searchText.includes(targetRooms + '룸') || searchText.includes('방' + targetRooms);
      });
    }

    // 위치 필터 (★ 점진적 반경 확대: 해당구 → 인근 5km → 인근 8km → 빈 결과)
    if (parsed.filters?.location) {
      const loc = parsed.filters.location;
      const coordInfo = DISTRICT_COORDS[loc];

      if (coordInfo) {
        const radiusSteps = [coordInfo.radius, 5, 8];
        let locFound = false;

        for (const radius of radiusSteps) {
          const parsedLoc = loc;
          const coordFiltered = results.filter(r => {
            if (!r.lat || !r.lng) {
              // ★ Fix 7: 좌표 없으면 텍스트 매칭으로 대체
              const propLoc = r.property?.location || '';
              return propLoc.includes(parsedLoc);
            }
            return haversineDistance(coordInfo.lat, coordInfo.lng, r.lat, r.lng) <= radius;
          });
          if (coordFiltered.length > 0) {
            results = coordFiltered;
            console.log(`좌표 필터 '${loc}': ${coordFiltered.length}건 (반경 ${radius}km)`);
            locFound = true;
            break;
          }
        }

        if (!locFound) {
          // DB 직접 검색 (점진적 반경)
          console.log(`결과 내 위치 매칭 0건 → '${loc}' DB 재검색`);
          for (const radius of [5, 8]) {
            let locQuery1 = supabase
              .from('cards')
              .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number')
              .eq('agent_id', agent_id)
              .neq('property->>type', '손님')
              .order('created_at', { ascending: false })
              .limit(limit * multiplier * 2);
            if (finalTradeType) locQuery1 = locQuery1.eq('property->>type', finalTradeType);
            if (finalPropertyType) locQuery1 = locQuery1.eq('property->>category', finalPropertyType);
            const { data: locData } = await locQuery1;
            if (locData && locData.length > 0) {
              const nearby = locData.filter(r => {
                if (!r.lat || !r.lng) return false;
                return haversineDistance(coordInfo.lat, coordInfo.lng, r.lat, r.lng) <= radius;
              });
              if (nearby.length > 0) {
                results = nearby.map(r => ({ ...r, similarity: 0 }));
                console.log(`DB 재검색: ${results.length}건 (반경 ${radius}km)`);
                locFound = true;
                break;
              }
            }
          }
          if (!locFound) {
            results = [];
            console.log(`${loc} 반경 8km 내 매물 없음 → 빈 결과`);
          }
        }
      } else {
        // 좌표 사전에 없는 지역 → 텍스트 매칭만
        const locFiltered = results.filter(r => {
          const st = r.search_text || '';
          const pLoc = r.property?.location || '';
          return st.includes(loc) || pLoc.includes(loc);
        });
        if (locFiltered.length > 0) {
          results = locFiltered;
        } else {
          let locQuery2 = supabase
            .from('cards')
            .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number')
            .eq('agent_id', agent_id)
            .neq('property->>type', '손님')
            .ilike('search_text', `%${loc}%`)
            .order('created_at', { ascending: false })
            .limit(limit * multiplier);
          if (finalTradeType) locQuery2 = locQuery2.eq('property->>type', finalTradeType);
          if (finalPropertyType) locQuery2 = locQuery2.eq('property->>category', finalPropertyType);
          const { data: locData } = await locQuery2;
          if (locData && locData.length > 0) {
            results = locData.map(r => ({ ...r, similarity: 0 }));
          } else {
            results = [];
          }
        }
      }
    }

    // ★ 근처 검색 (역: stations 테이블, 학교: schools 테이블)
    if (parsed.filters?.nearby && parsed.filters?.nearby_type) {
      const nearbyName = parsed.filters.nearby;
      const nearbyType = parsed.filters.nearby_type;
      const RADIUS_KM = 2.0;

      try {
        let facilityData: any[] | null = null;
        const searchName = nearbyName.replace(/역$|대$|대학$|학교$/, '');

        if (nearbyType === 'subway') {
          // stations 테이블 (컬럼: name, lat, lon)
          const { data } = await supabase
            .from('stations')
            .select('name, lat, lon')
            .ilike('name', `%${searchName}%`)
            .limit(3);
          facilityData = data?.map(d => ({ name: d.name, latitude: d.lat, longitude: d.lon })) || null;
        } else {
          // schools 테이블 (컬럼: name, lat, lon)
          const { data } = await supabase
            .from('schools')
            .select('name, lat, lon')
            .ilike('name', `%${searchName}%`)
            .limit(3);
          facilityData = data?.map(d => ({ name: d.name, latitude: d.lat, longitude: d.lon })) || null;
        }

        if (facilityData && facilityData.length > 0) {
          const facility = facilityData[0];
          const fLat = facility.latitude;
          const fLng = facility.longitude;
          console.log(`근처 검색: ${facility.name} (${fLat}, ${fLng}) 반경 ${RADIUS_KM}km`);

          // 반경 내 매물 필터
          const nearbyFiltered = results.filter(r => {
            if (!r.lat || !r.lng) return false;
            return haversineDistance(fLat, fLng, r.lat, r.lng) <= RADIUS_KM;
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

    // features 필터 (소프트: 매칭되는 걸 상위로, 없으면 유지)
    if (parsed.features && parsed.features.length > 0) {
      const withFeat: any[] = [];
      const withoutFeat: any[] = [];
      for (const r of results) {
        const st = r.search_text || '';
        const feats = (r.property?.features || []).join(' ');
        const all = (st + ' ' + feats).toLowerCase();
        if (parsed.features.some(f => all.includes(f.toLowerCase()))) {
          withFeat.push(r);
        } else {
          withoutFeat.push(r);
        }
      }
      // 특징 매칭된 것을 상위로, 나머지는 뒤에 (제거하지 않음)
      results = [...withFeat, ...withoutFeat];
    }

    // ★ 필터 완화: 후처리 필터 후 결과 0건이면 단계적으로 풀기
    if (results.length === 0 && (finalTradeType || finalPropertyType)) {
      console.log('후처리 필터 후 0건 → 키워드 폴백 (필터 완화)');
      // 검색어 핵심 키워드로 재검색 (필터 없이)
      const fallbackTerms = [query];
      if (parsed.semantic) fallbackTerms.unshift(parsed.semantic);
      for (const term of fallbackTerms) {
        if (results.length > 0) break;
        let fbQuery = supabase
          .from('cards')
          .select('id, property, agent, agent_id, search_text, lat, lng, created_at, photos, trade_status, price_number')
          .eq('agent_id', agent_id)
          .neq('property->>type', '손님')
          .ilike('search_text', `%${term}%`)
          .order('created_at', { ascending: false })
          .limit(limit * 3);
        // ★ Fix 16: 폴백에서도 거래유형 필터 유지
        if (finalTradeType) fbQuery = fbQuery.eq('property->>type', finalTradeType);
        const { data: fbData } = await fbQuery;
        if (fbData && fbData.length > 0) {
          results = fbData.map(r => ({ ...r, similarity: 0 }));
          console.log(`필터 완화 폴백 '${term}': ${results.length}건`);
        }
      }
    }

    // ★ 중개사 실전 랭킹 시스템
    // 원칙: 예산 이하 & 가까운 순 → 같은 가격이면 넓은 순 → 최신순 → 계약가능 우선
    let autoSort: string | null = null;
    const hasRankingConditions = !!(
      parsed.filters?.min_price || parsed.filters?.max_price ||
      parsed.filters?.min_area || parsed.filters?.max_area ||
      parsed.filters?.rooms || parsed.filters?.location
    );

    if (hasRankingConditions && results.length > 1) {
      const targetMaxPrice = parsed.filters?.max_price || null;
      const targetMinPrice = parsed.filters?.min_price || null;
      const targetArea = parsed.filters?.min_area || parsed.filters?.max_area || null;
      const targetRooms = parsed.filters?.rooms || null;
      const locCoord = parsed.filters?.location ? DISTRICT_COORDS[parsed.filters.location] : null;

      results = results.map(r => {
        let score = 0;
        const pn = r.price_number || 0;
        const detail: Record<string, any> = {}; // 항목별 점수 상세

        // ① 가격 (0~50점)
        let priceScore = 0;
        let priceReason = '';
        if (targetMaxPrice && pn > 0) {
          if (pn <= targetMaxPrice) {
            const ratio = pn / targetMaxPrice;
            if (ratio >= 0.90) { priceScore = 50; priceReason = '예산 90~100% (딱 맞음)'; }
            else if (ratio >= 0.75) { priceScore = 42; priceReason = '예산 75~90%'; }
            else if (ratio >= 0.50) { priceScore = 30; priceReason = '예산 50~75% (여유)'; }
            else { priceScore = 15; priceReason = '예산 50% 미만 (많이 싸다)'; }
          } else {
            const overRate = (pn - targetMaxPrice) / targetMaxPrice;
            if (overRate <= 0.05) { priceScore = 20; priceReason = '예산 5% 초과'; }
            else if (overRate <= 0.10) { priceScore = 5; priceReason = '예산 10% 초과'; }
            else { priceScore = -30; priceReason = '예산 10%+ 초과 (탈락)'; }
          }
        } else if (targetMinPrice && pn > 0) {
          if (pn >= targetMinPrice) {
            const overRate = (pn - targetMinPrice) / targetMinPrice;
            if (overRate <= 0.15) { priceScore = 50; priceReason = '최소가 근접'; }
            else if (overRate <= 0.30) { priceScore = 35; priceReason = '최소가 30% 이내'; }
            else { priceScore = 20; priceReason = '최소가 초과'; }
          } else { priceScore = -20; priceReason = '최소가 미달'; }
        }
        score += priceScore;
        detail.price = { score: priceScore, reason: priceReason, value: pn };

        // ② 가성비 (0~20점)
        const areaStr = r.property?.area || '';
        const pyeongMatch = areaStr.match(/(\d+)평/);
        const sqmMatch = areaStr.match(/(\d+)㎡/);
        const pyeong = pyeongMatch ? parseInt(pyeongMatch[1]) : (sqmMatch ? Math.round(parseInt(sqmMatch[1]) / 3.305785) : 0);
        let areaScore = 0;
        let areaReason = '';
        if (targetArea && pyeong > 0) {
          const areaDiff = Math.abs(pyeong - targetArea) / targetArea;
          if (areaDiff <= 0.1) { areaScore = 20; areaReason = `${pyeong}평 (요청 ${targetArea}평 ±10%)`; }
          else if (areaDiff <= 0.25) { areaScore = 14; areaReason = `${pyeong}평 (±25%)`; }
          else if (areaDiff <= 0.50) { areaScore = 7; areaReason = `${pyeong}평 (±50%)`; }
          else { areaReason = `${pyeong}평 (범위 밖)`; }
        } else if (pn > 0 && pyeong > 0) {
          const ppPrice = Math.round(pn / pyeong);
          if (ppPrice < 500) { areaScore = 15; areaReason = `평당 ${ppPrice}만 (가성비↑)`; }
          else if (ppPrice < 1000) { areaScore = 10; areaReason = `평당 ${ppPrice}만`; }
          else if (ppPrice < 2000) { areaScore = 5; areaReason = `평당 ${ppPrice}만`; }
          else { areaReason = `평당 ${ppPrice}만 (비쌈)`; }
        }
        score += areaScore;
        detail.area = { score: areaScore, reason: areaReason, pyeong };

        // ③ 방 수 (0~10점)
        let roomScore = 0;
        let roomReason = '';
        if (targetRooms) {
          const roomStr = r.property?.room || r.search_text || '';
          const roomNum = parseInt(roomStr.match(/(\d)/)?.[1] || '0');
          if (roomNum === targetRooms) { roomScore = 10; roomReason = `${roomNum}룸 (일치)`; }
          else if (roomNum > 0 && Math.abs(roomNum - targetRooms) === 1) { roomScore = 4; roomReason = `${roomNum}룸 (±1)`; }
          else { roomReason = roomNum > 0 ? `${roomNum}룸 (불일치)` : '정보없음'; }
        }
        score += roomScore;
        detail.room = { score: roomScore, reason: roomReason };

        // ④ 위치 — 위치 검색이면 항상 높은 가중치 (가격과 무관하게)
        const locWeight = 4; // 항상 4배 — 위치를 검색했으면 위치가 가장 중요
        let locScore = 0;
        let locReason = '';
        if (locCoord && r.lat && r.lng) {
          const dist = haversineDistance(locCoord.lat, locCoord.lng, r.lat, r.lng);
          const distKm = Math.round(dist * 10) / 10;
          if (dist <= 0.5) { locScore = 10 * locWeight; locReason = `${distKm}km (매우 가까움)`; }
          else if (dist <= 1.0) { locScore = 8 * locWeight; locReason = `${distKm}km`; }
          else if (dist <= 2.0) { locScore = 5 * locWeight; locReason = `${distKm}km`; }
          else if (dist <= 3.0) { locScore = 2 * locWeight; locReason = `${distKm}km (먼 편)`; }
          else { locScore = -10 * locWeight; locReason = `${distKm}km (다른 지역)`; }
        }
        score += locScore;
        detail.location = { score: locScore, reason: locReason };

        // ⑤ 계약가능 (0~8점)
        const status = r.trade_status || '계약가능';
        let statusScore = 0;
        if (status === '계약가능') statusScore = 8;
        else if (status === '계약중') statusScore = 0;
        else statusScore = -5;
        score += statusScore;
        detail.status = { score: statusScore, value: status };

        // ⑥ 최신 (0~7점)
        let freshScore = 0;
        let freshReason = '';
        if (r.created_at) {
          const daysSince = Math.round((Date.now() - new Date(r.created_at).getTime()) / (1000*60*60*24));
          if (daysSince <= 1) { freshScore = 7; freshReason = '오늘'; }
          else if (daysSince <= 3) { freshScore = 5; freshReason = `${daysSince}일 전`; }
          else if (daysSince <= 7) { freshScore = 3; freshReason = `${daysSince}일 전`; }
          else if (daysSince <= 14) { freshScore = 1; freshReason = `${daysSince}일 전`; }
          else { freshReason = `${daysSince}일 전 (오래됨)`; }
        }
        score += freshScore;
        detail.fresh = { score: freshScore, reason: freshReason };

        // ⑦ 특징 (0~5점)
        let featScore = 0;
        let featReason = '';
        if (parsed.features && parsed.features.length > 0) {
          const st = r.search_text || '';
          const feats = (r.property?.features || []).join(' ');
          const all = (st + ' ' + feats).toLowerCase();
          const matched = parsed.features.filter(f => all.includes(f.toLowerCase()));
          featScore = Math.min(5, matched.length * 2);
          featReason = matched.length > 0 ? matched.join(',') : '없음';
        }
        score += featScore;
        detail.features = { score: featScore, reason: featReason };

        return { ...r, _score: score, _scoreDetail: detail };
      });

      // 점수 내림차순 정렬 (동점이면 넓은 순 → 최신순)
      results.sort((a, b) => {
        const diff = (b._score || 0) - (a._score || 0);
        if (diff !== 0) return diff;
        // 동점이면 넓은 순
        const aArea = parseInt((a.property?.area || '').match(/(\d+)평/)?.[1] || '0');
        const bArea = parseInt((b.property?.area || '').match(/(\d+)평/)?.[1] || '0');
        if (bArea !== aArea) return bArea - aArea;
        // 그래도 동점이면 최신순
        return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
      });
      console.log(`랭킹 적용: ${results.length}건 | 상위: ${results[0]?._score}점 | 하위: ${results[results.length-1]?._score}점`);
    } else {
      // 조건이 적으면 → 명시적 sort 또는 최신순
      autoSort = parsed.filters?.sort || null;
      if (!autoSort) {
        if (parsed.filters?.date_filter) autoSort = 'newest';
        else autoSort = 'newest';
      }
      results = sortResults(results, autoSort);
    }

    // ★ 점수 컷오프 (가격 조건 있을 때만 적용 — 없으면 전부 보여줌)
    const hasPriceCondition = !!(parsed.filters?.min_price || parsed.filters?.max_price || min_price || max_price);
    if (hasRankingConditions && hasPriceCondition) {
      results = results.filter(r => (r._score || 0) >= 30);
    }

    // ★ 최종 검증: 결과 반환 직전 하드 체크 (엉뚱한 매물 절대 방지)
    const beforeFinal = results.length;
    results = results.filter(r => {
      const p = r.property || {};
      // 거래유형 불일치 제거
      if (finalTradeType && p.type && p.type !== finalTradeType) return false;
      // 카테고리 불일치 제거
      if (finalPropertyType && p.category && p.category !== finalPropertyType) return false;
      // 위치 불일치 제거 (텍스트 매칭)
      if (parsed.filters?.location) {
        const loc = parsed.filters.location;
        const pLoc = p.location || '';
        const st = r.search_text || '';
        if (!pLoc.includes(loc) && !st.includes(loc)) return false;
      }
      // 가격 범위 초과 제거 (20% 여유)
      if (parsed.filters?.max_price && r.price_number) {
        if (r.price_number > parsed.filters.max_price * 1.2) return false;
      }
      if (parsed.filters?.min_price && r.price_number) {
        if (r.price_number < parsed.filters.min_price * 0.8) return false;
      }
      return true;
    });
    if (beforeFinal !== results.length) {
      console.log(`최종 검증: ${beforeFinal}건 → ${results.length}건 (${beforeFinal - results.length}건 제거)`);
    }

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
      appliedFilters.push(sortLabels[autoSort] || '');
    }

    console.log(`총 소요: ${Date.now() - startTime}ms | 결과: ${results.length}건 | mode: ${search_mode} | filters: ${appliedFilters.join(', ')}`);

    return new Response(JSON.stringify({
      success: true,
      query,
      parsed,
      results,
      count: results.length,
      search_mode,
      applied_filters: appliedFilters,
      ranking: hasRankingConditions ? 'score' : 'newest',
      search_method: searchMethod,
      top_score: results[0]?._score ?? null
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
