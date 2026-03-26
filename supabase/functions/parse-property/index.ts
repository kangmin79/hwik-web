import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// ========== ㎡ → 평 변환 ==========
function sqmToPyeong(sqm: number): number {
  return Math.round(sqm / 3.305785 * 10) / 10;
}

function extractAndConvertArea(areaStr: string): { original: string; pyeong: string | null } {
  if (!areaStr) return { original: areaStr, pyeong: null };
  const sqmMatch = areaStr.match(/(\d+\.?\d*)\s*㎡/);
  if (sqmMatch) {
    const sqm = parseFloat(sqmMatch[1]);
    const pyeong = sqmToPyeong(sqm);
    return { original: areaStr, pyeong: `${pyeong}평 (${sqm}㎡)` };
  }
  return { original: areaStr, pyeong: null };
}

// ========== 임베딩 ==========
async function generateEmbedding(text: string): Promise<number[] | null> {
  const OPENAI_API_KEY = Deno.env.get('OPENAI_API_KEY');
  if (!OPENAI_API_KEY) return null;
  try {
    const response = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${OPENAI_API_KEY}` },
      body: JSON.stringify({ input: text, model: 'text-embedding-3-small' })
    });
    const data = await response.json();
    return data.data?.[0]?.embedding || null;
  } catch (error) { return null; }
}

// ========== 실거래가 조회 (국토부 RTMS API) ==========
async function fetchRecentSales(complex: string, lawdCd: string, months = 12): Promise<any[]> {
  const GOV_SERVICE_KEY = Deno.env.get('GOV_SERVICE_KEY');
  if (!GOV_SERVICE_KEY || !complex || !lawdCd) return [];

  const SALES_API = 'http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev';
  const allData: any[] = [];
  const now = new Date();
  const keywords = [complex.replace(/\s/g, '').slice(0, 4)];
  if (complex.replace(/\s/g, '').length > 4) {
    keywords.push(complex.replace(/\s/g, '').slice(2, 6));
  }

  for (let i = 0; i < months; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const ym = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`;
    try {
      const url = `${SALES_API}?serviceKey=${encodeURIComponent(GOV_SERVICE_KEY)}&LAWD_CD=${lawdCd}&DEAL_YMD=${ym}&pageNo=1&numOfRows=9999`;
      const resp = await fetch(url, { headers: { 'Accept': 'application/xml' } });
      if (!resp.ok) continue;
      const text = await resp.text();
      const items = text.match(/<item>([\s\S]*?)<\/item>/g) || [];
      for (const item of items) {
        const get = (tag: string) => item.match(new RegExp(`<${tag}>(.*?)<\/${tag}>`))?.[1]?.trim() || '';
        const aptNm = get('aptNm').replace(/\s/g, '');
        if (keywords.some(kw => aptNm.includes(kw))) {
          allData.push({
            year: get('dealYear'),
            month: get('dealMonth'),
            day: get('dealDay'),
            amount: get('dealAmount'),
            area: get('excluUseAr'),
            floor: get('floor'),
            aptNm: get('aptNm'),
          });
        }
      }
    } catch (e) { continue; }
  }
  return allData;
}

// ========== lawdCd 추출 (bjdCode 앞 5자리) ==========
const KAKAO_API_KEY = Deno.env.get('KAKAO_API_KEY') || '';

async function getLawdCd(address: string): Promise<string | null> {
  if (!address) return null;
  try {
    const url = `https://dapi.kakao.com/v2/local/search/address.json?query=${encodeURIComponent(address)}`;
    const res = await fetch(url, { headers: { 'Authorization': `KakaoAK ${KAKAO_API_KEY}` } });
    const data = await res.json();
    const bCode = data.documents?.[0]?.address?.b_code || '';
    return bCode.slice(0, 5) || null;
  } catch (e) { return null; }
}

// ========== agent_comment 생성 (실거래가 기반) ==========
async function generateAgentComment(parsedResult: any, salesData: any[], anthropicKey: string): Promise<string | null> {
  if (parsedResult.type === '손님') return null;

  let salesContext = '';
  if (salesData.length > 0) {
    const recent = salesData.slice(0, 5).map(s =>
      `${s.year}.${s.month}.${s.day} | ${s.area}㎡(${sqmToPyeong(parseFloat(s.area))}평) | ${s.amount}만원 | ${s.floor}층`
    ).join('\n');
    salesContext = `\n\n최근 실거래가:\n${recent}`;
  }

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': anthropicKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-3-5-haiku-20241022',
        max_tokens: 150,
        messages: [{
          role: 'user',
          content: `부동산 중개사가 손님에게 보내는 매물 소개 한 줄 코멘트를 작성해주세요.
이모지 1개로 시작하고, 30자 이내로 간결하게.
실거래가 데이터가 있으면 시세 대비 언급해주세요.
코멘트만 반환하세요.

매물: ${parsedResult.type} ${parsedResult.price} ${parsedResult.location} ${parsedResult.complex || ''} ${parsedResult.area || ''}${salesContext}`
        }]
      })
    });
    const data = await response.json();
    return data.content?.[0]?.text?.trim() || null;
  } catch (e) { return null; }
}

// ========== AI 크롤링용 public_data 생성 ==========
function createPublicData(parsedResult: any, salesData: any[]): object {
  const avgPrice = salesData.length > 0
    ? Math.round(salesData.reduce((sum, s) => {
        const amt = parseInt(s.amount.replace(/,/g, '')) || 0;
        return sum + amt;
      }, 0) / salesData.length)
    : null;

  return {
    schema_version: '1.0',
    property_type: parsedResult.category,
    trade_type: parsedResult.type,
    location: parsedResult.location,
    complex_name: parsedResult.complex,
    price: parsedResult.price,
    area: parsedResult.area,
    floor: parsedResult.floor,
    features: parsedResult.features || [],
    move_in: parsedResult.moveIn,
    recent_avg_price: avgPrice ? `${avgPrice.toLocaleString()}만원` : null,
    recent_trade_count: salesData.length,
    data_source: 'hwik',
    updated_at: new Date().toISOString(),
  };
}

// ========== 민감 키워드 ==========
const SENSITIVE_KEYWORDS = [
  '집주인', '세입자', '오너', '건물주', '관리실', '소유자', '임대인', '매도인', '임차인', '관리인', '현세입자', '전세입자',
  '관리사무소', '관리소', '관리팀', '융자', '근저당', '가압류', '대출', '대출승계', '담보', '실투자금', '선순위', '후순위',
  '호가', '시세', 'KB시세', '감정가', '공시가', '공시지가', '실거래가', '매매가', '전세가',
  '월수익', '순수익', '순이익', '월순익', '연수익', '예상수익', '임대수익',
  '이혼', '이혼정리', '상속', '상속정리', '이민', '급매', '급전세', '급월세', '급처분', '투자금회수',
  '계약일', '계약만료', '잔금', '잔금일', '만기', '만기일',
  '하자', '곰팡이', '누수', '누수이력', '벌레', '바퀴', '층간소음', '침수', '침수이력',
  '여성전용', '남성전용', '외국인불가', '네고', '협의가능', '가격협의', '권리금', '수익률',
  '월매출', '공실', '연체', '실입주만',
];

function createSearchTextPublic(parsed: any, rawText: string): string {
  let sanitized = rawText;
  sanitized = sanitized.replace(/(010|011|02|0[3-6][1-9])[-.\s]?\d{3,4}[-.\s]?\d{4}/g, '');
  sanitized = sanitized.replace(/\d{2,4}호/g, '');
  for (const kw of SENSITIVE_KEYWORDS) {
    sanitized = sanitized.replace(new RegExp(kw + '[\\d억천만원%개월있음없음중가능불가]*', 'gi'), '');
  }
  const catKoMap: Record<string, string> = {apartment:'아파트',officetel:'오피스텔',room:'원투룸',commercial:'상가',office:'사무실'};
  const catKo = catKoMap[parsed.category] || '';
  const parts = [
    parsed.type, parsed.price, parsed.location, parsed.complex,
    parsed.area, parsed.floor, parsed.room,
    ...(parsed.features || []), parsed.moveIn, parsed.category, catKo,
    sanitized.replace(/\s+/g, ' ').trim()
  ].filter(Boolean);
  return parts.join(' ').replace(/\s+/g, ' ').trim();
}

function createSearchTextPrivate(parsed: any, rawText: string): string {
  const catKoMap: Record<string, string> = {apartment:'아파트',officetel:'오피스텔',room:'원투룸',commercial:'상가',office:'사무실'};
  const catKo = catKoMap[parsed.category] || '';
  const parts = [
    parsed.type, parsed.price, parsed.location, parsed.complex,
    parsed.area, parsed.floor, parsed.room,
    ...(parsed.features || []), parsed.moveIn, parsed.memo, parsed.category, catKo, rawText
  ].filter(Boolean);
  return parts.join(' ');
}

function parsePriceNumber(priceStr: string): number | null {
  if (!priceStr) return null;
  try {
    let price = priceStr.replace(/[\s,]/g, '');
    if (price.includes('/')) return parsePriceNumber(price.split('/')[0]);
    if (price.includes('억')) {
      const parts = price.split('억');
      return (parseInt(parts[0]) || 0) * 10000 + (parseInt(parts[1]) || 0);
    }
    if (price.includes('만')) return parseInt(price.replace('만', '')) || null;
    const num = parseInt(price);
    if (!isNaN(num)) return num <= 100 ? num * 10000 : num;
  } catch (e) {}
  return null;
}

function normalizeType(type: string): string {
  const typeMap: Record<string, string> = {
    '반전세': '월세', '보증금 월세': '월세', '보증금월세': '월세', '월세': '월세',
    '전세': '전세', '매매': '매매', '매도': '매매', '분양': '매매', '임대': '월세', '손님': '손님'
  };
  return typeMap[type] || type;
}

function normalizeText(text?: string): string | null {
  return text?.replace(/\s+/g, ' ').trim() || null;
}

// ========== 메인 ==========
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  const authHeader = req.headers.get('Authorization');
  if (!authHeader) {
    return new Response(JSON.stringify({ error: '로그인이 필요합니다.' }), {
      status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }

  const token = authHeader.replace('Bearer ', '');
  const supabase = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
  const { data: { user }, error: authError } = await supabase.auth.getUser(token);
  if (authError || !user) {
    return new Response(JSON.stringify({ error: '로그인이 필요합니다.' }), {
      status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }

  try {
    const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY');
    if (!ANTHROPIC_API_KEY) throw new Error('서버 설정 오류입니다.');

    const { text } = await req.json();
    if (!text || text.trim().length < 10)
      return new Response(JSON.stringify({ error: '매물 정보가 너무 짧습니다. 최소 10자 이상 입력해주세요.' }), {
        status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    if (text.length > 3000)
      return new Response(JSON.stringify({ error: '입력 텍스트가 너무 깁니다 (최대 3000자)' }), {
        status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });

    console.log('INPUT:', text);
    const startTime = Date.now();

    // ★ Claude 파싱 (좌표 조회 제거 → 클라이언트에서 처리)
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1024,
        messages: [{
          role: 'user',
          content: `당신은 부동산 매물 정보를 분석하는 전문가입니다.
아래 매물 정보를 분석해서 JSON으로 반환해주세요.

■ 중요: 반드시 JSON만 반환하고, 다른 설명은 하지 마세요.

■ type 판단 기준 (최우선):
먼저 이 입력이 "매물 등록"인지 "손님 요청"인지 판단하세요.
기본값은 "매물 등록"입니다. 확실한 손님 요청 근거가 없으면 매물로 처리하세요.

★ 매물 등록의 특징:
- 구체적 가격: "15억", "3억5000", "1000/80"
- 구체적 층/동: "15층", "101동"
- 구체적 단지명+면적: "래미안 32평"
- "내놓습니다", "올립니다", "팝니다", "구해드립니다"
- 초성/축약: ㅁㅁ=매매, ㅈㅅ=전세, ㅇㅅ=월세

★ 손님 요청의 특징:
- 구합니다, 구해요, 찾습니다, 원합니다 등 요청 동사
- 예산 ~, 손님 요청, 이사 예정
- 예산/희망가 표현: 예산 5억, ~이하로

⚠️ 오분류 방지:
1. "구해드립니다" = 매물 등록
2. 확신 없으면 매물로 처리
3. 호수(~호)는 절대 비공개 → memo에만

■ ㎡ → 평 자동변환:
area 필드에 ㎡가 있으면 평수도 함께 표기 (예: "84.8㎡(25.7평)")

■ category:
- apartment: 아파트, 주상복합
- officetel: 오피스텔, 도시형생활주택
- room: 원룸, 투룸, 빌라, 다세대, 주택
- commercial: 상가, 점포, 식당
- office: 사무실, 지식산업센터

■ features 화이트리스트:
[시설] 올수리, 풀옵션, 신축, 리모델링, 시스템에어컨, 드레스룸, 베란다확장
[방향] 남향, 동향, 서향, 북향, 남동향, 남서향, 정남향
[위치] 역세권, 초역세권, 더블역세권, 학군좋음, 학원가, 대로변
[주차] 주차가능, 주차1대, 주차2대, 주차무료
[뷰/구조] 한강뷰, 공원뷰, 산뷰, 시티뷰, 탁트인전망, 복층, 테라스, 루프탑, 고층, 저층, 로얄층
[편의] 애견가능, 엘리베이터, 경비실
[입주] 즉시입주, 입주협의, 공실

■ memo (비공개): 호수, 연락처, 거래조건, 네고가능, 급매, 사람정보, 기타

■ agent_comment:
- 💬 이모지로 시작하는 줄이 있으면 추출
- 없으면 null (실거래가 기반으로 서버에서 생성)
- type이 "손님"이면 null

{
  "type": "매매/전세/월세/손님 중 하나",
  "price": "가격",
  "location": "지역 (구+동, 예: 마포구 합정동)",
  "address": "도로명주소 (있으면 추출, 예: 서울시 마포구 양화로 123. 없으면 null)",
  "complex": "단지명 (없으면 null)",
  "area": "면적 (㎡있으면 평수 병기)",
  "floor": "동+층만",
  "room": "방 구조",
  "features": ["화이트리스트 특징만"],
  "moveIn": "입주일",
  "memo": "비공개 정보",
  "agent_comment": "중개사 코멘트 (없으면 null)",
  "category": "apartment/officetel/room/commercial/office"
}

매물 정보:
${text}`
        }]
      })
    });

    const claudeData = await response.json();
    if (claudeData.error) throw new Error(claudeData.error.message);

    let parsedResult: any;
    try {
      let jsonText = claudeData.content[0].text || '';
      jsonText = jsonText.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const firstBrace = jsonText.indexOf('{');
      const lastBrace = jsonText.lastIndexOf('}');
      if (firstBrace !== -1 && lastBrace !== -1) jsonText = jsonText.slice(firstBrace, lastBrace + 1);
      parsedResult = JSON.parse(jsonText);
    } catch (e) {
      throw new Error('파싱 결과를 처리할 수 없습니다');
    }

    parsedResult.features = [...new Set(parsedResult.features || [])];
    parsedResult.type = normalizeType(parsedResult.type);
    parsedResult.location = normalizeText(parsedResult.location);
    parsedResult.complex = normalizeText(parsedResult.complex);
    if (parsedResult.floor) {
      parsedResult.floor = parsedResult.floor.replace(/\s+/g, ' ').replace(/\d*호/g, '').trim();
    }

    // ㎡ → 평 변환 보완
    if (parsedResult.area) {
      const converted = extractAndConvertArea(parsedResult.area);
      if (converted.pyeong && !parsedResult.area.includes('평')) {
        parsedResult.area = converted.pyeong;
      }
    }

    const requiredFields = parsedResult.type === '손님'
      ? ['type', 'location', 'category']
      : ['type', 'price', 'location', 'category'];
    for (const field of requiredFields) {
      if (!parsedResult[field]) throw new Error(`필수 정보 누락: ${field}`);
    }

    console.log(`PARSED (${Date.now() - startTime}ms):`, parsedResult);

    const searchText = createSearchTextPublic(parsedResult, text);
    const searchTextPrivate = createSearchTextPrivate(parsedResult, text);
    const embeddingText = parsedResult.type === '손님' ? searchTextPrivate : searchText;

    // ★ 임베딩 + lawdCd 병렬 처리 (좌표 조회 제거됨)
    const [embedding, lawdCd] = await Promise.all([
      generateEmbedding(embeddingText),
      getLawdCd(parsedResult.location || ''),
    ]);

    console.log(`임베딩+lawdCd (${Date.now() - startTime}ms)`);

    // 실거래가 조회 (매물이고 단지명+lawdCd 있을 때)
    let salesData: any[] = [];
    if (parsedResult.type !== '손님' && parsedResult.complex && lawdCd) {
      salesData = await fetchRecentSales(parsedResult.complex, lawdCd, 12);
      console.log(`실거래가: ${salesData.length}건 (${Date.now() - startTime}ms)`);
    }

    // agent_comment 생성 (실거래가 기반)
    if (!parsedResult.agent_comment && parsedResult.type !== '손님') {
      parsedResult.agent_comment = await generateAgentComment(parsedResult, salesData, ANTHROPIC_API_KEY);
    }

    // AI 크롤링용 public_data
    const publicData = createPublicData(parsedResult, salesData);

    const priceNumber = parsePriceNumber(parsedResult.price);

    const result = {
      ...parsedResult,
      // ★ 좌표는 클라이언트에서 DB 매칭 + 카카오 API 폴백으로 처리
      lat: null,
      lng: null,
      coord_type: 'none',
      embedding,
      search_text: searchText,
      search_text_private: searchTextPrivate,
      price_number: priceNumber,
      lawd_cd: lawdCd,
      recent_sales: salesData.slice(0, 5),
      recent_sales_count: salesData.length,
      public_data: publicData,
    };

    console.log(`총 소요: ${Date.now() - startTime}ms`);
    console.log('OUTPUT:', { ...result, embedding: embedding ? `[${embedding.length}d]` : null });

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error: any) {
    console.error('ERROR:', error.message);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
